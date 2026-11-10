# Órdenes de captura del SAT como posibles capturas

**Fecha:** 2026-11-10 · **Módulos backend:** `adt_captura` (15.0.1.4.0), `adt_flota_360`, `adt_comercial`

## Resumen

Un vehículo con **orden de captura vigente en el SAT Lima** (`adt.captura.sat`, la carga el
agente `capturas-sat`) ahora es **candidato a captura**:

- aparece en `GET /api/adt/captura/mora` (lista de la app) y en el detalle
  `GET /api/adt/captura/mora/detail`;
- aparece en Odoo, en **Capturas › Clientes en Mora**.

Cuándo cuenta una orden:

| Condición | Detalle |
|---|---|
| Orden vigente | `vigente = true` (el SAT la sigue mostrando en la última consulta completa). |
| No resuelta | La gestión interna de la orden no está en **Resuelta**. Si se marca como Resuelta en Odoo, la cuenta sale de la lista (salvo que tenga otra deuda). |
| Cuenta vigente | La cuenta del vehículo está **aprobada** o **en curso** (mismo criterio que las papeletas SAT). |
| Sin filtro de mora | Igual que las papeletas: entra **siempre**, sin pasar por el filtro de días de mora / cuotas de Ajustes. |

---

## 1. Cambios para la app (Android `adt_capture`)

### 1.1 Nuevo origen `captura_sat`

`source_type` (y `deuda.estado` en el detalle) tiene un valor nuevo:

| `source_type` | Etiqueta | Cuándo |
|---|---|---|
| `mora` | Cronograma | Solo cuotas vencidas |
| `papeleta` | Papeleta SAT | Solo papeletas SAT pendientes |
| `ambos` | Cronograma y papeleta SAT | Cuotas + papeletas |
| **`captura_sat`** | **Orden de captura SAT** | **Nuevo.** Está en la lista **solo** por la orden de captura del SAT |

> Si la cuenta además tiene cuotas o papeletas vencidas, conserva `mora` / `papeleta` /
> `ambos` y lleva `orden_captura_sat: true`. Para saber si un vehículo tiene orden SAT,
> usar siempre **`orden_captura_sat`**, no `source_type`.

### 1.2 `GET /api/adt/captura/mora`: lista

**Parámetros nuevos**

| Parámetro | Valores | Descripción |
|---|---|---|
| `source_type` | ahora también `captura_sat` (alias `orden_sat`, `orden_captura_sat`) | Solo las cuentas que están en la lista únicamente por la orden SAT. Admite varios valores separados por coma: `mora,captura_sat`. |
| `orden_captura_sat` | `1` \| `0` | **Nuevo.** `1` = solo vehículos con orden de captura SAT (cualquier origen). `0` = solo sin orden. Sin el parámetro, no filtra. |

Ejemplo: `GET {{base}}/api/adt/captura/mora?orden_captura_sat=1&limit=20`

**Respuesta: campos nuevos**

```json
{
  "count": 352,
  "filtro_captura": {"dias_mora_mayor_a": 0, "cuotas_vencidas_mayor_a": 0},
  "estados_deuda": [
    {"key": "todos", "label": "Todos", "count": 352},
    {"key": "mora", "label": "Cronograma", "count": 290},
    {"key": "papeleta", "label": "Papeleta SAT", "count": 31},
    {"key": "ambos", "label": "Cronograma y papeleta SAT", "count": 24},
    {"key": "captura_sat", "label": "Orden de captura SAT", "count": 7}
  ],
  "con_orden_captura_sat": 15,
  "records": [
    {
      "source_type": "captura_sat",
      "estado_deuda": "Orden de captura SAT",
      "orden_captura_sat": true,
      "monto_captura_sat": 862.0,
      "ordenes_captura_sat": [
        {
          "id": 41,
          "documento": "0012345678",
          "placa": "ABC123",
          "anio": 2025,
          "concepto": "Inf. Reglamento Nacional de Tránsito",
          "referencia": "D12-458",
          "monto": 862.0,
          "informe_sat_al": "2026-11-08",
          "detectada_en": "2026-11-07T18:20:11+00:00",
          "ultima_consulta": "2026-11-09T13:02:45+00:00",
          "dias_vigente": 3,
          "gestion": "nueva",
          "gestion_label": "Nueva",
          "responsable": null
        }
      ],
      "dias_mora": 0,
      "monto_vencido": 0.0,
      "deuda_sat": 0.0,
      "deuda_total": 0.0
      // ...resto de campos sin cambios
    }
  ]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `estados_deuda[]` | — | Trae un elemento más: `captura_sat`. |
| `con_orden_captura_sat` | int | **Nuevo.** Cantidad de filas con orden SAT, **de cualquier origen**, con los demás filtros aplicados. Sirve para un contador o chip "Orden SAT". |
| `records[].orden_captura_sat` | bool | **Nuevo.** `true` si el vehículo tiene al menos una orden de captura SAT vigente y no resuelta. |
| `records[].monto_captura_sat` | float | **Nuevo.** Suma del monto en captura de esas órdenes. |
| `records[].ordenes_captura_sat` | array | **Nuevo.** Detalle de cada orden (ver tabla 1.4). Lista vacía si no hay órdenes. |

> `deuda_total` **no** incluye `monto_captura_sat`: el monto en captura del SAT suele ser la
> misma deuda de las papeletas y se contaría dos veces. Por eso, ordenadas por monto, las
> filas `captura_sat` quedan al final de la lista.

### 1.3 `GET /api/adt/captura/mora/detail`: detalle

Dentro de `record.deuda` hay un bloque nuevo `orden_captura_sat`:

```json
"deuda": {
  "estado": "captura_sat",
  "estado_label": "Orden de captura SAT",
  "en_lista_de_capturas": true,
  "cronograma": { "...": "sin cambios" },
  "papeletas_sat": { "...": "sin cambios" },
  "orden_captura_sat": {
    "vigente": true,
    "cantidad": 1,
    "monto": 862.0,
    "ordenes": [ { "...": "mismo formato que ordenes_captura_sat de la lista" } ]
  },
  "total": 0.0,
  "captura_prioridad": "Normal"
}
```

Si la cuenta no está aprobada o en curso, `vigente` es `false` y `ordenes` es `[]`.

### 1.4 Formato de una orden (`ordenes_captura_sat[]` / `ordenes[]`)

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | int | ID en `adt.captura.sat` |
| `documento` | string | Número de documento publicado por el SAT |
| `placa` | string | Placa según el SAT (sin guion) |
| `anio` | int \| null | Año de la deuda |
| `concepto` | string | Concepto (infracción, impuesto vehicular, …) |
| `referencia` | string | Referencia del SAT |
| `monto` | float | Monto en captura (S/) |
| `informe_sat_al` | date \| null | Fecha del informe del SAT (`YYYY-MM-DD`) |
| `detectada_en` | datetime \| null | Primera vez que se vio la orden (ISO, UTC) |
| `ultima_consulta` | datetime \| null | Última consulta en la que figuró (ISO, UTC) |
| `dias_vigente` | int | Días desde que se detectó |
| `gestion` / `gestion_label` | string | `nueva` \| `en_gestion` (solo llegan órdenes no resueltas) |
| `responsable` | `{id, name}` \| null | Usuario de Odoo que gestiona la orden |

### 1.5 Qué hacer en la app

Archivos revisados en `adt_capture`:

- [ ] **`domain/domain_captura/.../model/Capture.kt`**: agregar `CAPTURE_SAT("captura_sat")` a
      `enum class SourceType` y su caso en `fromValue` (`"captura_sat", "orden_sat" -> CAPTURE_SAT`).
      Hoy `captura_sat` cae en `NONE`.
- [ ] **`feature/capture_list/.../CaptureListScreen.kt`**:
  - El chip `captura_sat` ya llega en `estados_deuda`, pero el `when (filter)` no lo maneja y cae
    en `else -> true`, así que mostraría **todos** los registros. Agregar
    `"captura_sat" -> it.sourceType == SourceType.CAPTURE_SAT`.
  - Agregar el mismo caso en la lista de chips de respaldo (cuando `debtStates` viene vacío).
  - El orden local (`numberOfOverdueInstallments` y luego `totalDebt`) deja estas filas al final.
    Evaluar priorizar `orderCaptureSat == true`.
- [ ] **`data/data_captura/.../dto/CaptureDto.kt`**: agregar
      `@Json(name = "orden_captura_sat") val satCaptureOrder: Boolean? = null`,
      `@Json(name = "monto_captura_sat") val satCaptureAmount: Double? = null` y
      `@Json(name = "ordenes_captura_sat") val satCaptureOrders: List<SatCaptureOrderDto>? = null`.
      Crear `SatCaptureOrderDto` con los campos de 1.4 y mapearlos en `CaptureMapper.kt`.
- [ ] **`data/data_captura/.../dto/GeneralListDto.kt`**: agregar
      `@Json(name = "con_orden_captura_sat") val withSatCaptureOrder: Int? = null`.
- [ ] **`data/data_captura/.../dto/CaptureOverviewDto.kt`**, en `DebtOverviewDto`: agregar
      `@Json(name = "orden_captura_sat") val satCaptureOrder: DebtSatCaptureOrderDto? = null`
      con `vigente`, `cantidad`, `monto` y `ordenes`.
- [ ] **`CaptureApi.getCaptureMora`** (opcional): parámetro
      `@Query("orden_captura_sat") satCaptureOrder: String? = null`.
- [ ] **UI de la tarjeta** de la lista: si `orden_captura_sat`, mostrar un pill rojo
      **"Orden de captura SAT"** con el monto (`monto_captura_sat`). Va aunque el origen sea
      `mora`, `papeleta` o `ambos`.
- [ ] **Detalle**: una sección "Orden de captura SAT" con cada orden (documento, concepto, año,
      monto, días vigente y fecha del informe SAT).
- [ ] **Al registrar la captura** (`POST` de creación): no hay cambios. El backend toma el
      `source_type` de la lista, así que puede quedar `captura_sat`.

---

## 2. Cambios en Odoo (backend)

### 2.1 `adt_captura`

| Archivo | Cambio |
|---|---|
| `__manifest__.py` | Versión `15.0.1.4.0`. **Nueva dependencia `adt_captura_sat`**. |
| `models/adt_captura_mora.py` | La vista SQL suma un `LATERAL` sobre `adt_captura_sat` (vigente, no resuelta, cuenta aprobada o en curso). Campos nuevos: `orden_captura_sat`, `ordenes_captura_sat`, `monto_captura_sat`, `fecha_captura_sat`. La condición de la lista pasa a ser `cronograma_ok OR papeletas > 0 OR ordenes_sat > 0`. `source_type = 'captura_sat'` cuando la orden SAT es el único motivo. |
| `models/adt_captura_record.py` | `SOURCE_TYPES` agrega `('captura_sat', 'Orden de captura SAT')`. La captura registrada guarda ese origen. |
| `controllers/captura_api.py` | Lista: filtro `orden_captura_sat`, alias `orden_sat`, estado `captura_sat` en `estados_deuda`, total `con_orden_captura_sat` y campos por registro. Detalle: bloque `deuda.orden_captura_sat`. |
| `controllers/captura_datos.py` | Helpers `ordenes_captura_sat_por_vehiculo()` (una consulta por página) y `orden_captura_sat_data()`. |
| `views/adt_captura_mora_views.xml` | Lista: columnas "Orden SAT", "Órdenes SAT" (opcional) y "Monto en captura SAT"; fila en rojo si tiene orden. Formulario: grupo "Orden de captura SAT". Búsqueda: filtros "Origen: Orden de captura SAT" y "Con orden de captura SAT". Kanban: etiqueta "Orden SAT" y detalle. |
| `views/adt_captura_record_views.xml` | Filtro "Origen: Orden de captura SAT" en capturas registradas. |
| `tests/test_captura_mora_sat.py` | **Nuevo.** Cubre: sin deuda, solo orden SAT, orden + cuotas vencidas, orden levantada o resuelta, cuenta cancelada. |

### 2.2 Otros módulos

| Archivo | Cambio |
|---|---|
| `adt_flota_360/models/flota_360_capturas.py` | Origen `captura_sat` en `ORIGENES`. Las filas con orden SAT se marcan como **críticas**. |
| `adt_flota_360/static/src/js/flota_360_capturas.js` | Texto "Orden de captura SAT" y chip crítico para ese origen. |
| `adt_comercial/models/cobranza_dashboard.py` | Motivo `captura_sat` en `MOTIVOS`. |

### 2.3 Despliegue

1. `adt_captura_sat` tiene que estar **instalado** (ahora es una dependencia).
2. Actualizar los módulos: `-u adt_captura,adt_flota_360,adt_comercial`. El update de
   `adt_captura` vuelve a crear la vista `adt_captura_mora`.
3. Pruebas: `--test-enable --test-tags /adt_captura`.
4. **Pendiente:** no se probó en un Odoo local. Validar en staging que la vista se crea y que
   `GET /api/adt/captura/mora?orden_captura_sat=1` devuelve los vehículos con orden.
