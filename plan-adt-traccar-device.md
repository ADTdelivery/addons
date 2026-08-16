# Plan: Módulo `adt_traccar_device` — Registro de dispositivo GPS + credenciales Traccar por cliente

## 0. Decisiones ya confirmadas

1. **Módulo nuevo e independiente**: `adt_traccar_device`. No se modifica el flujo actual de `adt_traccar` (usuario admin compartido `userId=8` que reasigna permisos en `traccar_controller.py`). El nuevo módulo solo reutiliza la configuración de conexión al servidor Traccar (`adt_traccar.url`, credenciales admin) para hablar con la API de Traccar como administrador.
2. **Disparo manual**: botón "Registrar en Traccar" en el formulario de `fleet.vehicle`, que pide placa (ya existe `license_plate`) e IMEI (ya existe `x_imei` en `fleet_addons`). Antes de permitir el registro valida que el vehículo tenga una **cuenta activa** en `adt.comercial.cuentas` (`state` en `en_curso` o `aprobado`), replicando el criterio ya usado en `adt_fleet/models/adt_fleet_model.py::_get_cuenta_for_report`.
3. ~~Password cifrada en reposo (Fernet/AES con clave fuera de la BD)~~ — **revertido, ver sección 8**: por pedido explícito del cliente ("mejor pasalo a texto plano y no nos compliquemos"), la contraseña generada se guarda en **texto plano** en el campo `traccar_password`, sin cifrado ni variable de entorno. Se protege únicamente con el grupo de seguridad `group_traccar_credentials_admin` en las vistas de Odoo (no queda visible para cualquier usuario interno) y con el Bearer token del endpoint REST del lado de la app.
4. **Módulo de cuentas de referencia: `adt_comercial`** (no `adt_comercial_v2`). `cuenta_id` apunta a `adt.comercial.cuentas`, y la validación de "cuenta activa" reutiliza el mismo criterio que `adt_fleet/models/adt_fleet_model.py::_get_cuenta_for_report` (`state` en `en_curso`/`aprobado`) pero contra ese modelo.
5. **Un usuario Traccar por vehículo, no por cliente**: si un mismo `partner_id` tiene varios vehículos registrados, cada uno obtiene su propio usuario Traccar (para que el permiso quede acotado a un solo device y la app no reciba de golpe todos los vehículos del cliente en un mismo login). Para no repetir el email real de contacto en Traccar, se deriva un email técnico por vehículo a partir del email del contacto: el **primer** vehículo del partner usa el email tal cual (`juan@gmail.com`); el **segundo** usa `juanv2@gmail.com`; el **tercero** `juanv3@gmail.com`; etc. (número de secuencia pegado al local-part, antes del `@`). Ver detalle en 3.1 y 4.2.

---

## 1. Objetivo

Desde Odoo Flota, permitir:
1. Registrar un dispositivo GPS en Traccar identificado por **placa** (nombre del device) e **IMEI** (`uniqueId`).
2. Crear en Traccar un **usuario individual** (email + password) para el cliente dueño de ese vehículo, usando el email del contacto (`res.partner`) ya vinculado por Flota.
3. Asignarle a ese usuario Traccar **permiso únicamente sobre su dispositivo** (no ve la flota completa).
4. Exponer un **servicio REST** (llamado desde la app) que devuelva esas credenciales (URL de Traccar, email, password, deviceId) para que la app se conecte directamente al **websocket de Traccar** y reciba solo la ubicación de ese dispositivo.

Esto reemplaza, para el caso de app-cliente, el modelo actual de "un solo admin que se reasigna" por "un usuario Traccar por cliente con visibilidad acotada a su propio dispositivo" — más correcto cuando varios clientes deben ver su GPS al mismo tiempo.

---

## 2. Lo que ya existe y se reutiliza (no se reinventa)

| Pieza | Dónde está | Uso en este plan |
|---|---|---|
| Config de conexión a Traccar (`url`, `email` admin, `password` admin) | `adt_traccar/models/traccar_config.py` (`res.config.settings`, `ir.config_parameter`) | Se reutiliza tal cual para autenticar como admin y poder crear devices/users/permissions vía API. |
| Patrón de auth por sesión Traccar (`POST /api/session` → cookie `JSESSIONID`) | `adt_traccar/controllers/traccar_controller.py` | Se replica el helper `_traccar_authenticate` para el nuevo controller. |
| Campo IMEI en vehículo | `fleet.vehicle.x_imei`, definido en **este mismo módulo** (`models/fleet_vehicle.py`) — ver actualización en sección 8: se descartó depender de `fleet_addons/models/fieldmodels.py` (módulo en desuso, con una vista rota) | Se usa como `uniqueId` del device en Traccar. Editable desde la pestaña "Traccar / GPS" del vehículo. |
| Placa del vehículo | `fleet.vehicle.license_plate` (núcleo Odoo Fleet) | Se usa como `name` del device en Traccar. |
| Cuenta activa del cliente | `adt.comercial.cuentas` (`state` en `en_curso`/`aprobado`), helper `_get_cuenta_for_report()` en `adt_fleet` | Condición obligatoria para permitir el registro: el vehículo debe tener una cuenta activa (evita crear credenciales para vehículos sin cliente asignado). |
| Contacto del cliente (email) | `res.partner` vinculado vía `fleet.vehicle.driver_id` o `cuenta.partner_id` | Fuente del email para el usuario Traccar — no se pide de nuevo, se usa el mismo email de Contactos. |
| Patrón de token/bearer para la app | `adt_comercial/models/mobile_models.py::MobileToken` + `adt_comercial/controllers/mobile_api.py` (header `Authorization: Bearer <token>`, revocación, `device_id`, etc.) | El nuevo endpoint de credenciales Traccar se protege igual: requiere `Bearer <token>` de `mobile.token`, y ese token ya está asociado a `partner_id` y `vehicle_id`, así que de ahí se deduce qué credenciales devolver (no se pasa la placa como parámetro público). |
| Formato de respuesta JSON estándar (`success/statusCode/data/meta`) | `adt_comercial/controllers/mobile_api.py` (`_success`, `_error`, `_json_response`) | Se reutiliza el mismo formato para el nuevo endpoint, por consistencia con el resto de la API que ya consume la app. |
| Cliente Traccar ya implementado (otro caso de uso) | `adt_mantenimiento_preventivo/models/traccar_client.py` (`adt.mantenimiento.traccar.client`, `AbstractModel`) + `fleet.vehicle.traccar_device_id` (Integer, ya existe) | **No se reutiliza directamente** (ese cliente solo lee posiciones/km, no crea devices/users). Sirve como referencia de estilo (logging con prefijo, manejo de errores) y, sobre todo, deja marcado que el campo `traccar_device_id` en `fleet.vehicle` **ya está ocupado** por ese módulo — `adt_traccar_device` no debe redefinirlo; el id de device de este plan vive en `adt.traccar.device.credential.traccar_device_id` (modelo propio, sin colisión). |

---

## 3. Modelo de datos nuevo

### 3.1 `adt.traccar.device.credential` (modelo nuevo, en `adt_traccar_device`)

| Campo | Tipo | Notas |
|---|---|---|
| `vehicle_id` | `Many2one('fleet.vehicle')` | único (constraint `unique`) — un set de credenciales activo por vehículo. |
| `partner_id` | `Many2one('res.partner')` | dueño de las credenciales (para filtrar por `mobile.token.partner_id`). |
| `cuenta_id` | `Many2one('adt.comercial.cuentas')` | referencia a la cuenta activa que habilitó el registro (auditoría). |
| `plate` | `Char` | copia de `license_plate` al momento del registro (histórico si luego cambia la placa). |
| `imei` | `Char` | copia de `x_imei` al momento del registro. |
| `traccar_device_id` | `Integer` | id del device en Traccar (`/api/devices`). |
| `traccar_user_id` | `Integer` | id del user en Traccar (`/api/users`) — **uno por vehículo**, nunca compartido entre dos `adt.traccar.device.credential`. |
| `partner_email_base` | `Char` | email real del contacto (`partner_id.email`), tal cual está en Contactos — se guarda aparte para poder recalcular la secuencia sin depender de parsear `traccar_email`. |
| `email_sequence` | `Integer` | posición de este vehículo entre los vehículos registrados del mismo `partner_id` (1, 2, 3…). Define el sufijo del email técnico. |
| `traccar_email` | `Char` | email técnico usado para el login Traccar de este vehículo. `email_sequence == 1` → igual a `partner_email_base`; `email_sequence >= 2` → local-part de `partner_email_base` + `v{email_sequence}` + dominio (ej. `juan@gmail.com` → `juanv2@gmail.com`, `juanv3@gmail.com`…). Ver 4.2. |
| `traccar_password` | `Char` | password en **texto plano** (ver 0.3 — cifrado revertido a pedido del cliente). No se expone en vistas normales (`groups` restringido). En el formulario se ve ofuscado por defecto (puntos), con un botón de "ojo" integrado en el mismo campo para revelarlo/ocultarlo — como un login típico. Ver widget `adt_password_toggle` en sección 8 (séptimo hallazgo). |
| `state` | `Selection` | `borrador` / `activo` / `error` / `revocado`. |
| `last_error` | `Text` | último error de la API de Traccar, para depurar sin exponer credenciales admin en logs de negocio. |
| `active` | `Boolean` | soft-delete estándar Odoo. |

Reglas:
- `sql_constraint` único por `vehicle_id` mientras `active=True` (un dispositivo Traccar vigente por vehículo).
- `sql_constraint` único por `traccar_email` (evita colisión de emails técnicos entre vehículos).
- `email_sequence` se calcula al crear el registro como `1 + count(adt.traccar.device.credential existentes o inactivos de ese partner_id)` — se cuentan también los inactivos/revocados para que, si se revoca y se vuelve a registrar un vehículo, nunca se reutilice un sufijo ya usado (evita reciclar un email técnico que Traccar todavía recuerde).
- El password se guarda en texto plano (`traccar_password`) y no se loguea nunca (ver 0.3).

### 3.2 ~~Utilidad de cifrado~~ (eliminada)

`tools/crypto.py` existió brevemente (Fernet + `ADT_TRACCAR_CRED_KEY`) y se **eliminó del módulo** a pedido del cliente — ver hallazgo en sección 8. No hay ninguna dependencia de `cryptography` ni variable de entorno adicional.

### 3.3 Fuente de "cuenta activa": `adt_comercial`

Confirmado: el módulo de referencia para `cuenta_id` y la validación de cuenta activa es **`adt_comercial`** (`adt.comercial.cuentas`), no `adt_comercial_v2`. `adt_traccar_device` depende de `adt_comercial` en el manifest.

---

## 4. Flujo funcional

### 4.1 Sincronización (funciona igual para vehículos existentes y nuevos)

La misma acción de negocio ("registrar/sincronizar con Traccar") se expone en **dos entradas**, ambas llamando al mismo método `adt.traccar.device.credential.register_vehicle(vehicle)` — no hay lógica distinta para "vehículo viejo" vs "vehículo nuevo": el criterio de elegibilidad (cuenta activa + IMEI + email de contacto) es el mismo siempre, así que un vehículo que ya existía desde antes de instalar el módulo se sincroniza exactamente igual que uno creado hoy.

**a) Botón individual, en el formulario de `fleet.vehicle`** (sirve tanto para el primer registro como para re-sincronizar uno puntual):
```
Usuario (admin/asesor) abre el vehículo en Flota
  → click "Registrar / Sincronizar con Traccar" (botón inteligente en el header)
  → wizard pide/confirma: placa (prellenada), IMEI (prellenado desde x_imei, editable)
  → Validar:
      - IMEI no vacío
      - Vehículo tiene cuenta con state in ('en_curso', 'aprobado')  [bloquea si no]
      - driver_id (o cuenta.partner_id) tiene email                  [bloquea si no]
      - Si ya existe un adt.traccar.device.credential activo para este vehículo,
        se muestra su estado (email/placa/IMEI actuales) y confirmar vuelve a
        sincronizar (crea uno nuevo y revoca el anterior; útil si cambió el IMEI)
  → Confirmar
```

**b) Acción masiva, desde la lista de vehículos** (pensada para sincronizar de una vez todos los vehículos que ya existían antes de este módulo, y también reutilizable después para lotes de vehículos nuevos):
```
Usuario entra a Flota → vista de lista → selecciona N vehículos
  → menú "Acción" → "Sincronizar con Traccar"
  → Por cada vehículo seleccionado, internamente llama a register_vehicle():
      - si no tiene IMEI               → se omite (se informa en el resumen)
      - si no tiene cuenta activa      → se omite (se informa en el resumen)
      - si no tiene email de contacto  → se omite (se informa en el resumen)
      - si todo OK                     → se registra/sincroniza igual que en (a)
  → Al terminar, notificación con: sincronizados / omitidos / con error
```

No hace falta filtrar de antemano "solo nuevos" o "solo existentes" en la vista de lista: el usuario simplemente selecciona los vehículos que quiere sincronizar (puede ser toda la flota) y la acción se encarga de saltarse silenciosamente (con aviso) los que no califican todavía.

### 4.2 Creación en Traccar (server-side, como admin)

```
1. POST /api/session (admin) → JSESSIONID   [reusa _traccar_authenticate]

2. Buscar si ya existe un device con uniqueId == imei
     GET /api/devices  (filtrar en memoria, igual que _find_device_by_plate
     pero por uniqueId)
   - si existe → reutilizar su id
   - si no existe → POST /api/devices { name: placa, uniqueId: imei }

3. Calcular email técnico (SIEMPRE se crea un usuario Traccar nuevo, uno
   por vehículo — nunca se reutiliza un traccar_user_id existente):
     email_sequence = 1 + count(
         adt.traccar.device.credential.search(
             [('partner_id', '=', partner.id)],
             active_test=False  # cuenta también revocados/inactivos
         )
     )
     traccar_email = partner.email                         si email_sequence == 1
                    = local_part + "v" + email_sequence + "@" + domain
                                                             si email_sequence >= 2
     (local_part/domain = partner.email.split("@", 1))

   Antes de crear, verificar contra GET /api/users que ese traccar_email no
   exista ya en Traccar (choque improbable pero posible si un registro se
   creó y luego se borró el credential sin borrar el user en Traccar) — si
   choca, incrementar email_sequence y reintentar.

4. Generar password aleatoria segura (secrets.token_urlsafe)
   POST /api/users { name: partner.name, email: traccar_email, password,
                      administrator: false }
   → nuevo traccar_user_id, exclusivo de este vehículo.

5. POST /api/permissions { userId: <traccar_user_id>, deviceId: <traccar_device_id> }
   (el device puede en teoría tener otros permisos si fue reutilizado en el
   paso 2, pero el USER es nuevo y solo tendrá este único permiso — así
   queda garantizado que este login Traccar ve exactamente un dispositivo)

6. Cifrar password → guardar adt.traccar.device.credential
   (partner_email_base, email_sequence, traccar_email, traccar_user_id,
   traccar_device_id, state='activo')
```

Nota: como cada vehículo tiene su propio `traccar_user_id`, un cliente con 2 vehículos maneja **dos logins Traccar distintos** (uno por placa) — la app debe usar el que corresponda al vehículo que se está consultando (el token `mobile.token` ya trae `vehicle_id`, así que el endpoint 4.3 ya resuelve esto sin ambigüedad).

### 4.3 Consulta desde la app (servicio REST)

Dos formas de pedirlo — **mismo endpoint**, `GET /v1/app/traccar-credentials`:

**a) Con Bearer token** (flujo original, sección 4.3 original):
```
Headers: Authorization: Bearer <mobile.token>

1. Resolver token → mobile.token (validar no revocado, no expirado)
2. token.vehicle_id → ese es el vehículo. Si además viene ?plate=..., debe
   coincidir con token.vehicle_id (si no, 403 PLATE_TOKEN_MISMATCH).
3. Buscar adt.traccar.device.credential activo de ese vehicle_id
   (y validar que token.partner_id == credential.partner_id, por seguridad)
4. Si no existe -> 404 "Vehículo sin dispositivo Traccar registrado"
```

**b) Directo por placa, sin token** (agregado a pedido: "devolver las credenciales... por placa"):
```
GET /v1/app/traccar-credentials?plate=ABC-123     (sin header Authorization)

1. Validar formato de placa (mismo PLATE_RE que adt_comercial/mobile_api.py)
2. Buscar fleet.vehicle por license_plate (=ilike)
3. Buscar adt.traccar.device.credential activo de ese vehicle_id
4. Si no existe -> 404
```
Mismo nivel de exposición que el `POST /v1/auth/login` ya existente en `adt_comercial` (login solo con la placa, sin más secreto) — no es una superficie de riesgo nueva en este backend, es consistente con lo que la app ya hace para el resto de los datos del cliente. Se documenta explícitamente acá porque, a diferencia de préstamos/documentos, esto entrega acceso a **ubicación GPS en vivo** — vale la pena que quede claro y decidido a propósito, no como default accidental.

**Respuesta (ambos flujos, igual)**:
```json
{
  "success": true,
  "data": {
    "traccar_url": "...",
    "traccar_ws_url": "wss://.../api/socket",
    "email": "...",
    "password": "...",
    "device_id": 123,
    "unique_id": "<imei>",
    "plate": "ABC-123"
  }
}
```

**Importante**: este endpoint solo debe viajar sobre HTTPS. No cachear la respuesta en el cliente más de lo necesario.

### 4.4 Uso del websocket (referencia, fuera del backend Odoo)

La app, con las credenciales devueltas:
1. `POST {traccar_url}/api/session` con `email`/`password` → obtiene cookie de sesión Traccar (igual que hace el backend).
2. Abre `wss://{traccar_host}/api/socket` enviando esa cookie.
3. Como el usuario Traccar solo tiene permiso sobre su device (paso 4.2.4), el socket solo emitirá posiciones de ese dispositivo — no hace falta filtrar del lado de la app.

Esto es responsabilidad de la app / no se implementa en Odoo, pero se documenta aquí para que quede claro por qué el paso 4.2.4 (permiso acotado, sin verlo todo) es la pieza que garantiza el aislamiento.

### 4.5 Estado GPS en vivo, desde Odoo (botón "Actualizar")

A diferencia de 4.3/4.4 (consumido por la app externa), esto es para uso interno desde Flota — un administrador/asesor que quiere ver rápido cómo está un vehículo sin salir de Odoo:

```
Usuario abre el vehículo → pestaña "Traccar / GPS" → click "Actualizar"
  → (as admin) GET /api/devices?id=<traccar_device_id>
       → status (online/offline/unknown), lastUpdate, positionId
  → si hay positionId: GET /api/positions?id=<positionId>
       → latitude, longitude, speed (nudos → se multiplica ×1.852 para km/h),
         address (si Traccar tiene geocoding inverso configurado),
         attributes.batteryLevel (si el dispositivo lo reporta)
  → se guarda todo en adt.traccar.device.credential (campos gps_*)
  → fleet.vehicle lo muestra vía campos related (mismo patrón que
    traccar_credential_state)
```

Es un snapshot manual, no hay cron ni websocket abierto del lado de Odoo — cada click en "Actualizar" es una llamada real y puntual a Traccar. También existe una acción masiva desde la lista de vehículos ("Actualizar estado GPS") que corre esto sobre todos los seleccionados. `gps_maps_url` (link a Google Maps) fue la primera forma de "ver la ubicación" antes de construir el mapa embebido (ver 4.6) — se mantiene como respaldo si el mapa no carga por algún motivo.

### 4.6 Mapa embebido con posición "casi en vivo" (décimo agregado)

Pedido explícito posterior: mapa embebido en la propia ficha del vehículo, que se actualice solo (no solo con el botón manual de 4.5).

**Decisión de arquitectura — polling contra Odoo, no websocket directo navegador↔Traccar:**

Se evaluaron dos caminos:
1. El navegador de Odoo abre `wss://{traccar_host}/api/socket` directo (como hace la app en 4.4). Requiere que `POST {traccar_url}/api/session` (llamado desde JS, origen = dominio de Odoo) tenga CORS habilitado en el servidor Traccar para ese origen — dato que no se puede verificar desde acá (no hay forma de abrir un navegador contra el Traccar real del cliente). Si CORS no está habilitado, esto falla en silencio con un error de CORS en la consola del navegador, sin ningún aviso del lado de Odoo.
2. El navegador solo habla con Odoo (mismo origen, sin problema de CORS posible). Odoo, server-side, le pregunta a Traccar reusando el código ya probado de 4.5 (`action_refresh_gps_status`). El navegador hace polling contra Odoo cada 8 segundos.

**Se eligió la opción 2** por ser la única que se puede entregar con confianza de que funciona, dado que reusa una ruta de código (autenticación admin + `get_device_by_id` + `get_position`) que ya se confirmó funcionando en producción (log real del cliente al registrar el vehículo `0766PC`). Si más adelante se confirma que Traccar permite CORS desde el dominio de Odoo, la opción 1 es la mejora natural (websocket real en vez de polling).

**Implementación:**
- `controllers/traccar_live_position.py`: `POST /adt_traccar_device/live_position` (`type='json'`, `auth='user'` — requiere sesión de Odoo, distinto de `/v1/app/traccar-credentials` que es público para la app). Recibe `credential_id`, llama a `action_refresh_gps_status()` (mismo método que el botón "Actualizar") y devuelve el snapshot en JSON.
- `static/src/js/live_map_field.js`: widget `adt_live_map`, registrado en `field_registry`, "colgado" del campo `traccar_credential_active_id` (un Many2one) solo para tener acceso a `this.recordData` (los demás campos `gps_*`) y a `this.value.res_id` (id de la credencial) — no se usa como selector de Many2one, se reemplaza toda su renderización por un mapa Leaflet + panel de estado. Hace `setInterval` cada 8s llamando al controller de arriba y moviendo el marcador.
- **Leaflet se carga perezosamente desde CDN** (`unpkg.com/leaflet@1.9.4`) la primera vez que se abre la pestaña "Traccar / GPS" — deliberadamente NO se agregó como asset global de `web.assets_backend` (eso cargaría ~150KB de JS/CSS en *todas* las páginas del backend para *todos* los usuarios, todo el tiempo, incluso quienes nunca miran un vehículo). Ver `ensureLeafletLoaded()` en el widget.
- Se manejó explícitamente el problema clásico de Leaflet dentro de un tab oculto (`display:none` al momento de inicializar el mapa → tamaño 0 → mapa roto): `invalidateSize()` con delay tras crear el mapa, más un listener de click sobre los tabs del formulario que vuelve a llamar `invalidateSize()` por si la pestaña se activa después.

**Riesgo/dependencia nueva a tener presente**: el navegador de quien mire esta pestaña necesita poder llegar a `unpkg.com` (CDN público) para cargar Leaflet. Es una dependencia externa nueva que el módulo no tenía antes (todo lo demás solo habla con el propio Traccar del cliente). Si en algún momento se prefiere no depender de un CDN externo (ej. políticas de seguridad más estrictas), la alternativa es empaquetar Leaflet como archivo estático propio del módulo — no se hizo en esta iteración porque no había forma de descargar y verificar la integridad del archivo minificado desde este entorno.

### 4.7 Reorganización del layout (undécimo agregado)

Pedido posterior: reordenar la pestaña "Traccar / GPS", que había quedado con información duplicada (el mapa ya trae su propio panel con estado/velocidad/batería/último reporte, y debajo se repetían esos mismos datos como campos sueltos de Odoo). Se eligió, entre dos mockups presentados, el layout de **mapa a todo el ancho arriba, franja de detalle angosta abajo**:

```
IMEI [___________]                          [Actualizar]
(alerta si no hay credencial activa)

┌──────────────────────────────────────────────────┐
│ 🟢 En línea   85 km/h   67%   hace 2 min          │  ← panel propio del widget (live_map_field.js)
│ ┌────────────────────────────────────────────────┐│
│ │                MAPA (ancho completo)            ││
│ └────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘

Lat / Lon / [Ver en Google Maps]     Dirección / Actualizado en Odoo

Historial de credenciales Traccar (tabla)
```

La franja de detalle de abajo quedó reducida a **solo lo que el panel del mapa no muestra**: `gps_latitude`, `gps_longitude`, `gps_maps_url`, `gps_address`, `gps_status_refreshed_at` — se sacaron `gps_status`, `gps_speed_kmh`, `gps_battery_level` y `gps_last_update` de ahí porque ya están en el panel integrado del mapa (evita repetir la misma info dos veces en la misma pantalla). El botón "Actualizar" subió a la franja superior, junto al IMEI.

---

## 5. Seguridad

- El usuario Traccar creado **no** debe ser `administrator: true`.
- El endpoint REST de credenciales exige Bearer token válido y cruza `partner_id` del token contra el dueño del credential — un cliente no puede pedir las credenciales de otro vehículo cambiando un parámetro.
- **Password en texto plano** (`traccar_password`, ver 0.3): no hay clave de cifrado que proteger. La única barrera en Odoo es el grupo de seguridad de las vistas.
- Los campos `traccar_password` y `traccar_email` en la vista de Odoo van con `groups="adt_traccar_device.group_traccar_credentials_admin"` para que ni siquiera un usuario interno cualquiera los vea en el formulario.
- Logs: nunca loguear el password en claro (ni en `_logger.info`, ni en `last_error` si el error de Traccar llegara a incluirlo — sanitizar antes de guardar).
- Regenerar password: acción explícita ("Regenerar credenciales") que hace `PUT /api/users/<id>` en Traccar con password nueva y actualiza `traccar_password` — nunca se regenera automáticamente sin acción del usuario, porque invalidaría sesiones activas de la app.

---

## 6. Estructura de archivos propuesta (`adt_traccar_device/`)

```
adt_traccar_device/
  __init__.py
  __manifest__.py                 # depends: base, fleet, adt_traccar, adt_comercial, mail
  models/
    __init__.py
    traccar_device_credential.py  # modelo 3.1 + register_vehicle() (orquestador 4.2)
    fleet_vehicle.py              # botón individual (4.1.a) + acción masiva de lista (4.1.b)
  services/
    traccar_client.py             # wrapper de la API Traccar: authenticate, get_devices,
                                   # get_device_by_unique_id, create_device, get_users,
                                   # get_user_by_email, create_user, add_permission
                                   # (reescrito acá para no acoplar con el controller de adt_traccar)
  wizard/
    __init__.py
    traccar_register_device_wizard.py   # wizard del botón 4.1
    traccar_register_device_wizard_views.xml
  controllers/
    __init__.py
    traccar_credentials_api.py    # GET /v1/app/traccar-credentials (4.3)
  security/
    ir.model.access.csv
    security_groups.xml           # group_traccar_credentials_admin
  views/
    fleet_vehicle_views.xml       # botón "Registrar en Traccar" / "Ver credenciales"
    traccar_device_credential_views.xml
  static/src/
    js/password_toggle_field.js   # widget adt_password_toggle (7º hallazgo, sección 8)
    scss/password_toggle_field.scss
  __manifest__.py
```

---

## 7. Pasos de implementación (orden sugerido)

1. Crear el manifest y esqueleto del módulo `adt_traccar_device` (depende de `base`, `fleet`, `adt_traccar`, `adt_comercial`, `mail`).
2. ~~Implementar `tools/crypto.py`~~ — descartado, ver sección 8 (password en texto plano).
3. Implementar `services/traccar_client.py` (capa de API Traccar reutilizable, con los métodos de la sección 4.2, incluyendo `get_user_by_email` para el chequeo anti-colisión del email técnico).
4. Implementar el modelo `adt.traccar.device.credential` (incluye el cálculo de `email_sequence`/`traccar_email`) + vistas + seguridad de grupos.
5. Implementar el wizard de registro + botón en `fleet.vehicle`, con las validaciones de 4.1.
6. Implementar el controller REST `GET /v1/app/traccar-credentials`, reusando el patrón de `mobile_api.py` (formato de respuesta, validación de `mobile.token`).
7. Acción "Regenerar credenciales" (`PUT /api/users/<id>` en Traccar) — mantiene el mismo `traccar_email`, solo cambia el password.
8. Pruebas manuales end-to-end contra un Traccar de staging:
   - Registrar vehículo sin cuenta activa → debe bloquear.
   - Registrar vehículo con cuenta activa e IMEI → crea device + user + permission en Traccar, credential queda `activo`.
   - Repetir registro para vehículo ya registrado → debe ofrecer "ver/regenerar", no duplicar.
   - Mismo cliente con un **segundo** vehículo → confirmar que se crea un `traccar_user_id` nuevo con email `<local>v2@dominio>` y que ese login solo ve ese segundo device (no el primero).
   - Un **tercer** vehículo del mismo cliente → email `<local>v3@dominio`.
   - Revocar y volver a registrar un vehículo del mismo cliente → el nuevo `email_sequence` no debe repetir un sufijo ya usado antes (se cuentan también los credentials inactivos).
   - Llamar al endpoint REST con el bearer token del cliente dueño (para ese `vehicle_id`) → recibe las credenciales de ESE vehículo, no las de otro vehículo del mismo cliente.
   - Llamar al endpoint con un token de otro cliente/vehículo → 404 (no filtra credenciales ajenas).
9. ~~Documentar la variable de entorno de cifrado~~ — no aplica (ver sección 8).

---

## 8. Hallazgo durante la instalación (resuelto)

Al instalar por primera vez `adt_traccar_device` con `fleet_addons` como dependencia (por ser el módulo que define `fleet.vehicle.x_imei`), la instalación falló:

```
ValidationError: while parsing fleet_addons/views/view_gps.xml:50
El elemento '<xpath expr="//page[@name='model_page']">' no puede ser localizado en la vista padre
```

`fleet_addons` no estaba instalado en este entorno — su vista `view_gps.xml` quedó desactualizada contra la vista actual de `fleet.vehicle` y rompe cualquier instalación que lo arrastre como dependencia (el mismo motivo por el que `adt_mantenimiento_preventivo`, que también necesitaría IMEI, tampoco depende de `fleet_addons`).

**Corrección aplicada**: `adt_traccar_device` ya **no depende de `fleet_addons`** (módulo en desuso). El campo `x_imei` en `fleet.vehicle` se define directamente en este módulo (`models/fleet_vehicle.py`), con su propia pestaña "Traccar / GPS" en el formulario del vehículo — sin ninguna dependencia externa para esto. (Se descartó la alternativa intermedia de leer/escribir `x_imei` de forma defensiva solo si existía, porque el objetivo explícito es no depender en absoluto de módulos que ya no se usan.)

Pendiente real (fuera del alcance de este módulo, y ya no bloqueante): arreglar el xpath roto de `fleet_addons/views/view_gps.xml:50` si en algún momento se quiere reinstalar ese módulo.

También hubo un segundo hallazgo, ya corregido: con `'application': False` en el manifest, Odoo intenta renderizar `description` como reStructuredText al instalar/actualizar el módulo, y el texto libre usado ahí no es RST válido (`docutils.utils.SystemMessage: Unexpected section title`). Se cambió a `'application': True` (mismo valor que `adt_traccar` y `adt_mantenimiento_preventivo`), lo que evita ese renderizado por completo.

Un tercer hallazgo, de vista: `wizard/traccar_register_device_wizard_views.xml` usaba `existing_credential_id` en un `attrs` sin declarar ese campo como `<field>` en la vista (Odoo exige que todo campo referenciado en `attrs` esté presente, aunque sea `invisible="1"`). Se agregó el `<field name="existing_credential_id" invisible="1"/>` faltante.

Un cuarto hallazgo, de diseño (no de instalación): `register_vehicle()` creaba un usuario Traccar nuevo **cada vez que se llamaba**, incluso si el vehículo ya tenía credencial activa para el mismo IMEI — lo que hacía insegura la sincronización masiva (correrla dos veces sobre la misma flota generaba usuarios Traccar huérfanos en cada corrida). Se corrigió para que sea **idempotente por IMEI**: si ya existe una credencial activa con el mismo IMEI, se reutiliza tal cual (a lo sumo se renombra el device si cambió la placa); solo se emite un usuario/password nuevo cuando el IMEI cambió o no había credencial previa. Ver docstring de `register_vehicle` en `models/traccar_device_credential.py`.

Un quinto hallazgo, real en producción (primer registro probado sin `ADT_TRACCAR_CRED_KEY` configurada): `register_vehicle()` validaba la clave de cifrado (`TraccarCredentialCipher.instance()`) **al final**, después de ya haber creado el device, el usuario y el permiso en Traccar. Como esas llamadas HTTP no son parte de la transacción de Odoo, un `RuntimeError` por falta de la clave dejaba esos recursos **huérfanos en Traccar** (sin ningún registro local en Odoo) — y un reintento posterior, al no encontrar credencial local previa, creaba un email técnico nuevo (`v2`) en vez de reutilizar el ya creado, dejando un usuario Traccar abandonado. Se corrigió moviendo la validación de la clave al inicio de `register_vehicle()` (y de `action_regenerate_password()`), antes de tocar la API de Traccar — así, si falta la clave, falla rápido y sin efectos secundarios remotos.

**Limpieza manual pendiente en el Traccar de este intento**: quedó un usuario huérfano `arriechi@gmail.com` (userId=9) con permiso sobre el device `0766PC` (uniqueId=1231, deviceId=560) — se creó correctamente pero Odoo no llegó a guardar la credencial. Antes de reintentar el registro de ese vehículo conviene revisar en Traccar si ese usuario quedó sin uso y decidir si se borra o se reutiliza manualmente.

**Sexto hallazgo — decisión del cliente, no bug**: para evitar el hallazgo anterior (y en general, simplificar el deploy) el cliente pidió explícitamente eliminar el cifrado ("mejor pasalo a texto plano y no nos compliquemos"). Se revirtió por completo: se eliminó `tools/crypto.py`, la dependencia de `cryptography` del manifest, y la variable de entorno `ADT_TRACCAR_CRED_KEY` ya no existe. El campo pasó a llamarse `traccar_password` (antes `traccar_password_encrypted`) y guarda el password tal cual. La única protección restante es el grupo `group_traccar_credentials_admin` en las vistas de Odoo y el Bearer token del endpoint REST — trade-off aceptado conscientemente por el cliente.

**Séptimo hallazgo — UX del campo password**: la primera versión usó `password="True"` (oculta siempre, sin forma de revelar) y luego un truco de "campo duplicado + checkbox `show_password` aparte" (mismo patrón que `adt_traccar/views/adt_traccar_views.xml`, necesario porque el atributo `password` no admite `attrs` dinámicos). El cliente pidió el patrón de login estándar: un solo campo, ofuscado por defecto, con un botón de "ojo" integrado que alterna a texto plano y de vuelta. Se implementó un widget de campo propio (`adt_password_toggle`) en `static/src/js/password_toggle_field.js` (extiende el `FieldChar` legacy de Odoo 15, alterna `type="password"/"text"` del `<input>` igual que hace internamente el atributo `password` nativo, agregando el botón dentro del mismo elemento). Se registró en el manifest bajo `assets/web.assets_backend` (JS + SCSS). El campo `show_password` se eliminó del modelo — ya no hace falta.

**Octavo hallazgo/decisión — servicio "por placa"**: el cliente pidió un servicio para la app que devuelva las credenciales Traccar "por placa". Al revisar `adt_comercial/controllers/mobile_api.py` se confirmó que la app ya tiene ese mismo patrón para todo lo demás: `POST /v1/auth/login` genera un `mobile.token` a partir de **solo la placa**, sin ninguna otra autenticación ("No real authentication – designed for internal/partner use", literal en el código). Se extendió `GET /v1/app/traccar-credentials` para aceptar `?plate=ABC-123` **sin** Bearer token, con el mismo nivel de exposición que ese login — no se inventó una superficie de riesgo nueva, se igualó a lo que ya existe. Se mantiene también el flujo con Bearer token (con validación cruzada placa↔token si se mandan ambos). Ver sección 4.3 actualizada. Se documentó todo en `adt_traccar_device/API-traccar-credentials.md`, pensado para pasarle a un equipo externo que integre la app sin tener que leer el código.

**Noveno agregado — estado GPS en vivo (sección 4.5)**: se pidió poder ver, desde la ficha del vehículo en Flota, el estado actual del dispositivo (ubicación, velocidad, batería, si está reportando) con un botón "Actualizar". Se implementó como un snapshot manual (no hay cron/auto-refresh — cada click hace una llamada real a Traccar):
- `services/traccar_client.py` sumó `get_device_by_id()` (estado online/offline/unknown + `lastUpdate` + `positionId`) y `get_position()` (última posición: lat/lon, velocidad, `attributes` con batería si el dispositivo la reporta), más un helper `parse_traccar_datetime()`.
- Campos nuevos en `adt.traccar.device.credential`: `gps_status`, `gps_last_update` (reloj del dispositivo), `gps_latitude`, `gps_longitude`, `gps_speed_kmh` (Traccar reporta velocidad en **nudos** — se convierte ×1.852 al guardar), `gps_battery_level`, `gps_address`, `gps_maps_url` (computado, link directo a Google Maps), `gps_status_refreshed_at` (reloj de Odoo — cuándo se apretó "Actualizar", distinto del reloj del dispositivo). Acción `action_refresh_gps_status()`.
- `fleet.vehicle` refleja todo eso vía campos `related` (mismo patrón que `traccar_credential_state`) + `action_refresh_traccar_status()` (botón individual) + `action_refresh_traccar_status_bulk()` (acción de lista "Actualizar estado GPS", análoga a "Sincronizar con Traccar").
- **No se implementó un mapa embebido** (Leaflet/Google Maps incrustado en la vista) — se evaluó y se descartó por ahora por ser una pieza de UI bastante más grande (widget JS + carga de tiles + no se puede probar visualmente desde acá); en su lugar, `gps_maps_url` abre Google Maps en una pestaña nueva con un click. Si más adelante se quiere el mapa embebido, es la continuación natural de este punto. *(Nota: el mapa embebido sí se terminó implementando después — ver sección 4.6.)*

**Duodécimo agregado — sincronizar toda la flota sin selección manual**: pedido explícito ("sincronizar de forma masiva todos los vehículos que ya están en flota"). Ya existía `action_sync_traccar_bulk` (opción (b), lista + selección manual de filas), pero eso requiere saber que hay que seleccionar todo primero. Se agregó:
- `fleet.vehicle.action_sync_traccar_all_fleet()`: resuelve `self.search([])` (todos los vehículos activos) y delega en `action_sync_traccar_bulk`. Acción de menú **Traccar GPS → Sincronizar toda la flota con Traccar** (`views/menu.xml`), sin `binding_model_id`/`binding_view_types` (no aparece en el menú "Acción" de la lista — ese sigue siendo el de selección manual).
- **Optimización de paso**: `register_vehicle()` ahora acepta un `client` opcional (instancia de `TraccarClient` ya autenticada). `action_sync_traccar_bulk` crea y autentica el cliente **una sola vez** al principio del lote y lo reutiliza para todos los vehículos, en vez de loguearse contra Traccar por cada uno — antes, sincronizar 100 vehículos hacía 100 logins; ahora hace 1. Si la autenticación inicial falla (Traccar caído/mal configurado), se corta todo el lote de entrada con un mensaje claro, en vez de fallar vehículo por vehículo con el mismo error repetido 100 veces.

---

## 9. Riesgos / puntos abiertos para resolver durante implementación

- **Emails técnicos no reales**: `juanv2@gmail.com` puede no existir como buzón real (o puede coincidir por accidente con la cuenta real de otra persona si el dominio la registra). Como Traccar nunca envía correos a este address en el flujo normal (solo se usa como login), el riesgo funcional es bajo, pero si Traccar tiene features que sí envían mail a ese usuario (ej. reseteo de password vía email, alertas por correo) hay que desactivarlas para estos usuarios técnicos o coordinarlo — **validar contra la config real de Traccar antes de habilitar notificaciones por email a nivel de usuario**.
- **Partner sin email**: si `partner.email` está vacío no hay base para derivar ningún `traccar_email` (ni el primero ni los `vN`) — el wizard debe bloquear con un mensaje claro pidiendo completar el email en Contactos antes de registrar.
- **Traccar API real**: los endpoints exactos (`POST /api/devices`, `POST /api/users`, `PUT /api/users/<id>` para reset de password, formato exacto del payload) deben verificarse contra la versión de Traccar en uso (la doc REST de Traccar puede variar entre versiones) — el `traccar_controller.py` existente ya confirma que `/api/session`, `/api/devices` y `/api/permissions` funcionan tal cual contra este servidor; falta confirmar `/api/users` (crear/editar) de la misma forma antes de dar por buena la sección 4.2.
