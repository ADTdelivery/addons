# Propuesta: módulo `adt_tracking_moto`

Seguimiento de cada moto desde que se recoge en el almacén de compra (Gambeta) hasta que se entrega al cliente, con dos flujos en paralelo (**logística/armado** y **trámite de placa**) y tiempos por etapa.

> Documento de diseño previo a codificar. Odoo 15.

---

## 1. Contexto actual (lo que ya existe)

| Pieza | Dónde | Relevancia |
|---|---|---|
| Creación automática de la moto | `adt_facturacion_v1/models/account_move.py` → `_sync_fleet_vehicle()` | Al crear/editar una factura con tipo "vehículo" se crea un `fleet.vehicle` **sin placa y sin conductor**. Guarda `x_id_facturacion` (Many2one a `account.move`). |
| Dueño de la moto | `fleet.vehicle.driver_id` | Si está vacío, la moto está en stock (mismo criterio que `adt_dashboard_flota`). |
| Placa | `fleet.vehicle.license_plate` | Puede tener valores "basura" (`S/P`, `EN TRAMITE`, `-`…). `adt_dashboard_flota` ya tiene `plate_is_ready()` para detectarlos. |
| Trámite de placa | `procedure_plate` → `procedure.plate.model` | Estados: borrador, notaría, SUNARP, inscrito, observado, tachado. Tiene `vehiculo_id`. |
| Cuenta comercial | `adt_comercial` → `adt.comercial.cuentas.vehiculo_id` | Al aprobar/iniciar una cuenta se asigna la moto al cliente. |
| Fecha de entrega | `adt_fleet` → `fleet.vehicle.fecha_entrega` | Hito final de entrega. |

---

## 2. Flujos de negocio a modelar

```
                 ┌──────────────────── FLUJO 1: LOGÍSTICA / ARMADO (4 etapas fijas) ─────────────────────┐
Factura ──► Moto │ 1. Recojo almacén ─► 2. Almacén de ─► 3. Fibra en proveedor ─► 4. Base con fibra       │──► LISTA PARA ASIGNAR
 creada          │    distribuidor        la empresa       [taller: PP | VES |      (listo para asignar)  │
                 │    ("Gambeta")         ("Base")          SJM | …otros]                                │
                 └────────────────────────────────────────────────────────────────────────────────────────┘
   │
   │             ┌──────────── FLUJO 2: TRÁMITE DE PLACA ───────────────┐
   └────────────►│ Pendiente ─► En trámite ─► Tramitada ✔                │
                 │                    └─────► Rechazada ✘ ─► En trámite… │
                 └──────────────────────────────────────────────────────┘

Hitos transversales:  Asignada a cliente (driver_id)  ─►  Entregada (fecha_entrega)
```

- El flujo 1 tiene **siempre 4 etapas**; no se crean ni se borran, pero **su nombre se puede personalizar** (ej. "Gambeta" en vez de "Recojo almacén distribuidor").
- La etapa 3 es una sola; **dónde** se pone la fibra (PP, VES, SJM u otro almacén/proveedor) es un dato aparte: el **taller de fibra**, que es un catálogo abierto donde se pueden agregar más.
- Ambos flujos avanzan **en paralelo** e independientes.
- La moto **puede asignarse al cliente** cuando el flujo 1 llega a "Base con fibra", **aunque la placa aún esté en trámite**.
- El tracking se cierra cuando la moto está **entregada** y la **placa tramitada**.

---

## 3. Criterio de ingreso al tracking

Requisito: *"leer todos los vehículos de flota que no tengan placa y no tengan dueño"*.

Ese criterio aplica **solo para entrar** al tracking. Una vez dentro, la moto permanece aunque luego se le asigne dueño (porque la placa puede seguir pendiente).

Dominio de ingreso:

```python
[('driver_id', '=', False), ('active', '=', True)]
# + placa vacía o placeholder (se filtra en Python con plate_is_ready)
```

Formas de ingreso:

1. **Automática al crear la moto**: herencia de `fleet.vehicle.create()`. Si la moto nace sin placa real y sin `driver_id` → se crea su registro de tracking en etapa inicial (Gambeta) y placa "Pendiente". Esto cubre el caso de la factura sin tocar `adt_facturacion_v1`.
2. **Botón / cron "Sincronizar vehículos"**: recorre `fleet.vehicle` con el dominio de ingreso y crea el tracking a las que no lo tengan (carga inicial de motos ya existentes y red de seguridad).

Restricción: **un solo tracking activo por vehículo** (`_sql_constraints` unique sobre `vehicle_id`).

---

## 4. Modelos propuestos

### 4.1 `adt.moto.tracking.etapa` — las 4 etapas fijas (nombre editable)

Es un modelo (no `Selection`) **solo para poder renombrar** las etapas y configurar su SLA. La lógica nunca depende del nombre, sino del `codigo`, que es fijo.

| Campo | Tipo | Notas |
|---|---|---|
| `codigo` | Selection, readonly | `recojo`, `almacen`, `fibra`, `listo`. Único (`_sql_constraints`). |
| `name` | Char, translate | **Editable** por el administrador |
| `sequence` | Integer | Orden fijo 1–4 en el kanban |
| `sla_horas` | Float | Tiempo objetivo en la etapa (para alertas de demora) |
| `descripcion` | Text | Ayuda para el usuario |

Datos iniciales (XML `noupdate="1"` para que un renombrado no se pise al actualizar el módulo):

| seq | codigo | Nombre por defecto | Significado |
|---|---|---|---|
| 1 | `recojo` | Gambeta | Recojo en el almacén del distribuidor (moto en cajón, sin armar) |
| 2 | `almacen` | Base | Moto en el almacén de la empresa, sin armar |
| 3 | `fibra` | Fibra | Moto armada, enviada a un taller/proveedor a poner fibra |
| 4 | `listo` | Base con fibra | De vuelta en el almacén con fibra → **lista para asignar cliente** |

Para que las etapas sigan siendo 4:

- Permisos: nadie tiene `create` ni `unlink` sobre el modelo; el grupo manager solo tiene `write`.
- En la vista: `create="0" delete="0"` y `codigo` de solo lectura.
- `unlink()` sobrescrito para lanzar `UserError` (por si acaso, incluso con sudo desde la interfaz).

### 4.1.b `adt.moto.tracking.taller` — talleres / proveedores de fibra (catálogo abierto)

Aquí es donde se agregan PP, VES, SJM y cualquier otro almacén o proveedor nuevo.

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char | "Fibra PP", "Fibra VES", "Fibra SJM", … |
| `codigo` | Char | Abreviatura corta para el kanban (PP, VES, SJM) |
| `partner_id` | Many2one `res.partner` | Proveedor (opcional) |
| `direccion` | Char | |
| `sla_horas` | Float | Opcional: si se llena, tiene prioridad sobre el SLA de la etapa "Fibra" |
| `active` | Boolean | Archivar en vez de borrar (no rompe el historial) |

Datos iniciales: Fibra PP, Fibra VES, Fibra SJM (`noupdate="1"`).

### 4.2 `adt.moto.tracking` — un registro por moto

`_inherit = ['mail.thread', 'mail.activity.mixin']` para chatter e historial.

**Identificación**

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char | Secuencia `TRK/2026/00001` |
| `vehicle_id` | Many2one `fleet.vehicle` | required, unique, `ondelete='restrict'` |
| `factura_id` | Many2one `account.move` | related `vehicle_id.x_id_facturacion` |
| `modelo_id`, `chasis`, `motor`, `color` | related | desde el vehículo |
| `partner_id` | Many2one `res.partner` | related `vehicle_id.driver_id`, store |
| `cuenta_id` | Many2one `adt.comercial.cuentas` | compute: última cuenta del vehículo |

**Flujo 1 — Logística**

| Campo | Tipo | Notas |
|---|---|---|
| `etapa_id` | Many2one `adt.moto.tracking.etapa` | `group_expand` (siempre se ven las 4 columnas), `tracking=True` |
| `etapa_codigo` | Selection | related `etapa_id.codigo`, store (para dominios y lógica) |
| `taller_fibra_id` | Many2one `adt.moto.tracking.taller` | **Obligatorio al pasar a la etapa `fibra`**; se conserva después para saber dónde se hizo |
| `fecha_etapa` | Datetime | Cuándo entró a la etapa actual |
| `fecha_recojo` | Datetime | Entrada a la etapa `recojo` |
| `fecha_envio_fibra` | Datetime | Entrada a la etapa `fibra` |
| `fecha_listo` | Datetime | Entrada a la etapa `listo` |

**Flujo 2 — Placa**

| Campo | Tipo | Notas |
|---|---|---|
| `estado_placa` | Selection | `pendiente`, `en_tramite`, `rechazado`, `tramitado` |
| `fecha_inicio_tramite` | Datetime | |
| `fecha_placa_ok` | Datetime | |
| `num_placa` | Char | Al marcar "tramitado" se escribe en `vehicle_id.license_plate` |
| `motivo_rechazo` | Text | Obligatorio al rechazar (wizard) |
| `cant_rechazos` | Integer | compute desde el log |
| `procedure_plate_id` | Many2one `procedure.plate.model` | Opcional, ver §7 |

**Hitos y estado global**

| Campo | Tipo | Notas |
|---|---|---|
| `fecha_asignacion` | Datetime | Se llena cuando el vehículo recibe `driver_id` |
| `fecha_entrega` | Date | related `vehicle_id.fecha_entrega` (adt_fleet) |
| `estado_global` | Selection (compute, store) | ver tabla abajo |
| `dias_totales` | Float (compute) | desde `fecha_recojo` hasta entrega o ahora |
| `dias_etapa_actual` | Float (compute) | ahora − `fecha_etapa` |
| `demorado` | Boolean (compute) | `dias_etapa_actual` > `sla_horas` de la etapa |
| `log_ids` | One2many `adt.moto.tracking.log` | |

`estado_global` (calculado a partir de ambos flujos):

| Valor | Condición |
|---|---|
| `en_proceso` | etapa ≠ listo y sin dueño |
| `listo_asignar` | etapa = "Base con fibra" y sin dueño |
| `asignado_sin_placa` | con dueño y placa ≠ tramitado |
| `asignado_con_placa` | con dueño y placa = tramitado, sin entregar |
| `entregado` | `fecha_entrega` informada y placa = tramitado → **cerrado** |

### 4.3 `adt.moto.tracking.log` — historial con tiempos

Una línea por cada cambio de etapa (en cualquiera de los dos flujos). Es la base de todos los reportes de tiempos.

| Campo | Tipo | Notas |
|---|---|---|
| `tracking_id` | Many2one | cascade |
| `vehicle_id` | related store | para reportes |
| `flujo` | Selection | `logistica`, `placa`, `hito` |
| `etapa_desde` / `etapa_hasta` | Char | Nombre que tenía la etapa en ese momento (si luego se renombra, el historial no cambia) |
| `etapa_id` | Many2one etapa | Solo flujo logística |
| `taller_fibra_id` | Many2one taller | Solo cuando la etapa es `fibra` (para medir tiempos por taller) |
| `fecha_inicio` | Datetime | Entrada a `etapa_hasta` |
| `fecha_fin` | Datetime | Se llena al salir de la etapa |
| `duracion_horas` | Float (compute, store) | `fecha_fin − fecha_inicio` |
| `user_id` | Many2one `res.users` | Quién hizo el cambio |
| `nota` | Text | Observación / motivo de rechazo |

Regla: al cambiar de etapa → se cierra la línea abierta del mismo flujo (`fecha_fin = now`) y se abre una nueva.

---

## 5. Lógica principal

```python
# fleet.vehicle (herencia)
@api.model_create_multi
def create(self, vals_list):
    vehicles = super().create(vals_list)
    vehicles._adt_crear_tracking_si_aplica()
    return vehicles

def write(self, vals):
    res = super().write(vals)
    if 'driver_id' in vals:
        self._adt_tracking_registrar_asignacion()   # fecha_asignacion + log 'hito'
    if 'license_plate' in vals:
        self._adt_tracking_sincronizar_placa()      # si es placa real → tramitado
    if 'fecha_entrega' in vals:
        self._adt_tracking_registrar_entrega()
    return res
```

```python
# adt.moto.tracking
def action_mover_etapa(self, etapa):     # usado por botones y por drag&drop del kanban
def action_enviar_fibra(self):           # wizard: elegir taller → etapa 'fibra'
def action_iniciar_tramite(self):        # pendiente/rechazado → en_tramite
def action_rechazar_tramite(self):       # abre wizard con motivo → rechazado
def action_placa_tramitada(self):        # wizard con num_placa → tramitado + escribe license_plate
def _cron_sincronizar_vehiculos(self):   # backfill diario
def _cron_alertar_demoras(self):         # crea mail.activity al responsable si demorado
```

Validaciones:

- No permitir `driver_id` en el vehículo si su tracking no está en la etapa `listo` → **¿bloquear o solo advertir?** (ver §7).
- Orden secuencial por `codigo`: `recojo → almacen → fibra → listo`. Saltar o retroceder etapas solo lo puede hacer el grupo manager, y queda en el log.
- Pasar a `fibra` exige `taller_fibra_id`. Si se mueve por drag & drop en el kanban sin taller, se abre el wizard para elegirlo.
- Nada se basa en el **nombre** de la etapa; siempre en `codigo`.
- Rechazo exige motivo.

---

## 6. Vistas y menús

Menú: **Flota → Tracking de motos**

| Vista | Descripción |
|---|---|
| **Kanban** (por defecto) | Siempre 4 columnas (las etapas, con el nombre que se les haya puesto). Tarjeta: modelo, chasis, días en etapa (rojo si demorado), badge del estado de placa, badge del taller de fibra (PP/VES/SJM…), cliente si ya está asignada. Drag & drop mueve de etapa y registra log. |
| **Lista** | Moto, chasis, factura, etapa, taller de fibra, estado placa, estado global, cliente, días totales, días en etapa. Filtros: *Sin dueño*, *Listas para asignar*, *Asignadas sin placa*, *Placa rechazada*, *Demoradas*. Agrupar por etapa / taller de fibra / estado placa / estado global. |
| **Formulario** | Cabecera con `statusbar` de etapas + botones de placa. Dos bloques lado a lado: *Logística* y *Placa*. Pestaña *Historial* (log con duraciones). Chatter. |
| **Reporte de tiempos** (pivot/graph sobre `adt.moto.tracking.log`) | Promedio de horas por etapa, por taller de fibra, por mes de factura; nº de rechazos de placa. |
| **Smart button en `fleet.vehicle`** | "Tracking" → abre el registro de la moto. |
| **Configuración → Etapas** | Lista de las 4 etapas: solo se puede editar nombre, descripción y SLA (sin crear ni borrar). |
| **Configuración → Talleres de fibra** | Lista de `adt.moto.tracking.taller`: crear, editar y archivar libremente. |

Seguridad (`ir.model.access.csv` + grupos):

- `group_tracking_user`: ver y mover etapas / placa; solo lectura en etapas y talleres.
- `group_tracking_manager`: renombrar etapas, administrar talleres de fibra, saltar etapas, reabrir trackings cerrados.

---

## 7. Decisiones (estado de la implementación)

| # | Tema | Decisión |
|---|---|---|
| 1 | Trámite de placa | **Módulo propio `adt_tramite_placa`** (reemplaza a `procedure_plate` en el tracking). Se crea en *Pendiente* al crear la moto desde la factura. Estados: Pendiente → En trámite (inicio manual) → Observado ⇄ En trámite → Finalizado. Al finalizar, la placa y la tarjeta de propiedad pasan al vehículo. El estado de placa del tracking es el mismo del trámite y cada cambio queda en el historial. |
| 2 | Asignar cliente antes de la etapa 4 | **Solo advertir**: aviso en el formulario del vehículo (onchange) y la asignación queda marcada (`asignado_antes_listo`) + nota en el chatter. |
| 3 | Volver a fibra (retrabajo) | Permitido solo al grupo Administrador (botón «Reenviar a fibra»), queda en el historial. |
| 4 | SLA por etapa | Campo `sla_horas` en etapa y en taller (0 = sin control). Filtro «Demoradas» y cinta roja. Sin cron de alertas por ahora. |
| 5 | Vehículos que no son motos | Sin filtro por tipo: entra todo vehículo de flota sin placa ni dueño (pendiente de confirmar). |
| 6 | Carga inicial | Wizard «Sincronizar vehículos»: el administrador elige la etapa (por defecto etapa 2, Base). |
| 7 | API para la app | Fuera de alcance de esta versión. |

---

## 8. Estructura del módulo

```
adt_tracking_moto/
├── __init__.py
├── __manifest__.py            # depends: fleet, mail, account, adt_tramite_placa, adt_facturacion_v1, adt_fleet
├── data/
│   ├── tracking_etapa_data.xml   # las 4 etapas (noupdate)
│   ├── tracking_taller_data.xml  # PP, VES, SJM (noupdate)
│   ├── ir_sequence_data.xml
│   └── ir_cron_data.xml
├── security/
│   ├── tracking_groups.xml
│   └── ir.model.access.csv
├── models/
│   ├── __init__.py
│   ├── tracking_etapa.py
│   ├── tracking_taller.py
│   ├── tracking.py
│   ├── tracking_log.py
│   └── fleet_vehicle.py       # create/write hooks + smart button
├── wizard/
│   ├── enviar_fibra_wizard.py
│   ├── rechazo_placa_wizard.py
│   └── placa_tramitada_wizard.py
└── views/
    ├── tracking_views.xml     # kanban, lista, form, search
    ├── tracking_log_views.xml # pivot / graph
    ├── tracking_etapa_views.xml
    ├── tracking_taller_views.xml
    ├── fleet_vehicle_views.xml
    └── menus.xml
```

---

## 9. Plan de implementación

1. Modelos + datos de etapas y talleres de fibra + seguridad.
2. Hooks en `fleet.vehicle` (creación automática, asignación, placa, entrega) + cron de sincronización.
3. Vistas kanban / lista / form + wizards de placa.
4. Log de tiempos y reporte pivot.
5. Integración con `procedure_plate` (si se confirma §7.1).
6. Alertas de demora (si se confirma §7.4).
7. Pruebas: crear factura de vehículo → verifica tracking creado; mover etapas → verifica duraciones; asignar cliente sin placa → estado `asignado_sin_placa`; tramitar placa → `license_plate` actualizado.
