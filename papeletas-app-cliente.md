# Papeletas SAT y Órdenes de Captura SAT en la App del Cliente — Guía de Integración

API REST para que la app del cliente ADT muestre **solo información del SAT de
Lima** de su vehículo:

- **Papeletas SAT**: las que el monitor de papeletas encontró en el SAT Lima
  (importe, gastos/costas, descuento, deuda, estado SAT, falta, copias).
- **Órdenes de captura SAT**: las que el agente de capturas encontró en el SAT
  Lima (documento, concepto, monto en captura, vigente/levantada).

> **Importante:** ya no se devuelven las papeletas internas de ADT
> (`adt.papeleta`: registradas a mano, fraccionamientos, prórrogas, cuotas).
> Todo sale de los modelos espejo del SAT.

Fuente en el backend:

| Archivo | Qué hay |
|---|---|
| `adt_comercial/controllers/mobile_api.py` | Endpoints `GET /v1/papeletas`, `GET /v1/papeletas/<id>`, `GET /v1/capturas-sat` (helpers `_serialize_papeleta_sat`, `_papeletas_resumen`, `_papeletas_sat_ultima_consulta`, `_serialize_captura_sat`, `_captura_sat_vehiculo`, `_sat_vehicle_domain`, `_sat_record_vehicle`). |
| `adt_papeletas/models/papeleta_sat.py` | `adt.papeleta.sat` (papeleta SAT Lima) y `adt.papeleta.sat.import` (cada consulta del monitor). |
| `adt_captura_sat/models/captura_sat.py` | `adt.captura.sat` (orden de captura SAT Lima) y `adt.captura.sat.consulta`. |
| `adt_captura_sat/models/fleet_vehicle.py` | Estado de captura SAT del vehículo (`captura_sat_estado`, `captura_sat_ultima_consulta`). |

---

## 1. Resumen

| Método | Ruta | Uso en la app |
|---|---|---|
| `GET` | `/v1/papeletas` | Pantalla "Mis papeletas SAT": resumen + lista + bloque de captura SAT. |
| `GET` | `/v1/papeletas/{id}` | Detalle de una papeleta SAT. |
| `GET` | `/v1/capturas-sat` | Solo las órdenes de captura SAT (ej. alerta en el home). |

- Rutas **REST normales** (`type='http'`), no JSON-RPC.
- Misma autenticación que el resto de `/v1/...`:

```
Authorization: Bearer <token>
```

- Mismo sobre de respuesta:

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": { ... },
  "meta": { "timestamp": "2026-11-07T15:00:00Z", "requestId": "uuid" }
}
```

### De dónde salen los datos

```
Monitor papeletas (EC2) ──/api/papeletas/sat/import──▶ adt.papeleta.sat ─┐
Agente capturas (Docker) ─/api/capturas/sat/import──▶ adt.captura.sat ───┼─▶ /v1/papeletas
                                                     fleet.vehicle.captura_sat_* ┘   /v1/capturas-sat
```

Un registro SAT pertenece al vehículo si su `vehicle_id` es el vehículo **o**,
cuando el monitor no lo pudo vincular, si su placa (normalizada, sin guiones)
coincide con la del vehículo.

---

## 2. Permisos

El token solo puede ver datos SAT de:
- **Login por placa** (`/v1/auth/login`): únicamente el vehículo del token.
- **Token sin vehículo, con cliente** (ej. login por email): los vehículos cuyo
  conductor (`driver_id`) es ese cliente.

Otro vehículo → `403 FORBIDDEN`. Detalle de una papeleta SAT ajena →
`404 PAPELETA_NOT_FOUND` (no se revela que existe).

---

## 3. `GET /v1/papeletas` — Listado

### Query params (todos opcionales)

| Parámetro | Ejemplo | Descripción |
|---|---|---|
| `plate` | `ABC-123` | Placa del vehículo. |
| `idVehiculo` / `vehicle_id` | `10` | ID del vehículo (alternativa a `plate`). |
| `estado` | `PENDIENTE` | `PENDIENTE`, `PAGADO` o `TODAS` (default `TODAS`). |

Prioridad del vehículo: `plate` → `idVehiculo`/`vehicle_id` → vehículo del token.
Con login por placa basta con **no enviar nada**.

### Ejemplo

```http
GET /v1/papeletas
Authorization: Bearer 3f9c...e1
```

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "idVehiculo": 10,
    "placa": "ABC-123",
    "totalPapeletas": 2,
    "resumen": {
      "total": 2,
      "pendientes": 1,
      "pagadas": 1,
      "conAlerta": 1,
      "montoPendienteTotal": 528.0
    },
    "consultaSat": {
      "fecha": "2026-11-06T12:00:00Z",
      "resultado": "CON_PAPELETAS",
      "mensaje": null
    },
    "papeletas": [
      {
        "id": 11,
        "numeroPapeleta": "15394818",
        "fechaPapeleta": "2026-10-01",
        "monto": 528.0,
        "idVehiculo": 10,
        "fotosCount": 1,
        "fotoUrls": ["https://.../web/content/950/SAT_15394818_copia.png?access_token=..."],
        "placa": "ABC-123",
        "estado": "PENDIENTE",
        "origen": "SAT",
        "montoPendiente": 528.0,
        "moneda": "PEN",
        "falta": "G58",
        "figuraEnSat": true,
        "estadoSat": "Pendiente",
        "reglamento": "D.S. 016-2009-MTC",
        "importe": 528.0,
        "gastosCostas": 0.0,
        "descuento": 0.0,
        "deuda": 528.0,
        "diasDesdeInfraccion": 37,
        "alerta": true,
        "ultimaConsulta": "2026-11-06T12:00:00Z",
        "dejoDeFigurarEn": null
      },
      {
        "id": 12,
        "numeroPapeleta": "15201133",
        "fechaPapeleta": "2026-05-01",
        "monto": 100.0,
        "idVehiculo": 10,
        "fotosCount": 0,
        "fotoUrls": [],
        "placa": "ABC-123",
        "estado": "PAGADO",
        "origen": "SAT",
        "montoPendiente": 0.0,
        "moneda": "PEN",
        "falta": "M20",
        "figuraEnSat": false,
        "estadoSat": "Pendiente",
        "reglamento": "D.S. 016-2009-MTC",
        "importe": 100.0,
        "gastosCostas": 0.0,
        "descuento": 0.0,
        "deuda": 100.0,
        "diasDesdeInfraccion": 190,
        "alerta": false,
        "ultimaConsulta": "2026-06-02T12:00:00Z",
        "dejoDeFigurarEn": "2026-06-10T12:00:00Z"
      }
    ],
    "capturaSat": {
      "estado": "CON_ORDEN",
      "tieneOrdenCaptura": true,
      "ultimaConsulta": "2026-11-06T12:00:00Z",
      "ordenesVigentes": 1,
      "montoEnCaptura": 300.0,
      "ordenes": [
        {
          "id": 1,
          "documento": "202500123456",
          "placa": "ABC123",
          "anio": 2025,
          "concepto": "Papeleta",
          "placaOriginal": "ABC123",
          "referencia": "15000111",
          "monto": 300.0,
          "moneda": "PEN",
          "vigente": true,
          "informeSatAl": "2026-11-05",
          "detectadaEn": "2026-11-01T10:00:00Z",
          "ultimaConsulta": "2026-11-06T12:00:00Z",
          "levantadaEn": null,
          "diasVigente": 6
        }
      ]
    }
  },
  "meta": { "timestamp": "2026-11-07T15:00:00Z", "requestId": "..." }
}
```

- Orden de `papeletas`: primero las que **figuran en el SAT**, luego por fecha de
  infracción descendente.
- `resumen` **siempre** cuenta todas las papeletas SAT del vehículo, aunque se
  filtre la lista con `estado`.
- `consultaSat` es `null` si el monitor nunca consultó la placa con éxito.
- `capturaSat` es `null` si el módulo `adt_captura_sat` no está instalado.

---

## 4. `GET /v1/papeletas/{id}` — Detalle

`{id}` es el `id` de la papeleta SAT del listado. Devuelve **todos los campos
del listado** más:

```json
{
  "numeroCompromisoPago": null,
  "licenciaConducir": "Q12345678",
  "tipoDocumento": "DNI",
  "numeroDocumento": "12345678",
  "primeraVezVista": "2026-10-03T12:00:00Z",
  "urlCopiaSat": "https://www.sat.gob.pe/...",
  "sat": {
    "numero": "15394818",
    "estado": "Pendiente",
    "figuraEnSat": true,
    "fechaInfraccion": "2026-10-01",
    "reglamento": "D.S. 016-2009-MTC",
    "falta": "G58",
    "importe": 528.0,
    "gastosCostas": 0.0,
    "descuento": 0.0,
    "deuda": 528.0,
    "numeroCompromisoPago": null,
    "ultimaConsulta": "2026-11-06T12:00:00Z",
    "dejoDeFigurarEn": null,
    "copiasUrls": ["https://.../web/content/950/SAT_15394818_copia.png?access_token=..."]
  }
}
```

El bloque `sat` repite datos ya presentes arriba; se mantiene porque la app ya
lo consume (`PapeletaSat`).

---

## 5. `GET /v1/capturas-sat` — Órdenes de captura SAT

Mismos query params de vehículo que `/v1/papeletas` (`plate`, `idVehiculo`).
Devuelve el mismo objeto que `data.capturaSat` más `idVehiculo` y `placa`:

```json
{
  "success": true,
  "statusCode": 200,
  "data": {
    "idVehiculo": 10,
    "placa": "ABC-123",
    "estado": "CON_ORDEN",
    "tieneOrdenCaptura": true,
    "ultimaConsulta": "2026-11-06T12:00:00Z",
    "ordenesVigentes": 1,
    "montoEnCaptura": 300.0,
    "ordenes": [ { "...": "igual que en 3" } ]
  }
}
```

`ordenes` incluye vigentes y levantadas (historial), vigentes primero.

---

## 6. Referencia de campos

### 6.1 Papeleta SAT (`adt.papeleta.sat`)

| Campo | Tipo | Campo Odoo | Descripción |
|---|---|---|---|
| `id` | int | `id` | ID de la papeleta SAT. Usar para el detalle. |
| `numeroPapeleta` | string | `name` | N° de papeleta / código de pago SAT. |
| `fechaPapeleta` | `YYYY-MM-DD` \| null | `fecha_infraccion` | Fecha de infracción / emisión. |
| `monto` | number | `importe` | Importe de la multa (igual a `importe`). |
| `idVehiculo` / `placa` | int / string | `vehicle_id` / `placa` | Vehículo. |
| `fotosCount` / `fotoUrls` | int / string[] | adjuntos de `adt.papeleta.sat` | Copias de la papeleta descargadas del SAT (imagen/PDF). URLs públicas. |
| `estado` | enum | `estado_pago` | `PENDIENTE` · `PAGADO`. Ver 6.3. |
| `origen` | string | — | Siempre `SAT`. |
| `montoPendiente` | number | `deuda` | **Lo que se muestra como "a pagar"**: `0` si `PAGADO`; si no, `deuda` (o `importe` si el SAT no informó deuda). |
| `moneda` | string | `currency_id` | `PEN`. |
| `falta` | string \| null | `codigo_falta` | Código de falta (ej. `G58`). |
| `figuraEnSat` | bool | `vigente` | `true` si en la última consulta completa seguía en el SAT. |
| `estadoSat` | string \| null | `estado_sat` | Estado tal cual lo muestra el portal SAT (texto libre). |
| `reglamento` | string \| null | `reglamento` | Reglamento de tránsito. |
| `importe` | number | `importe` | Importe SAT. |
| `gastosCostas` | number | `gastos_costas` | Gastos / costas SAT. |
| `descuento` | number | `descuento` | Descuento SAT. |
| `deuda` | number | `deuda` | Deuda total SAT. |
| `diasDesdeInfraccion` | int | `dias` | Días desde la infracción (o desde que se vio en el SAT si no tiene fecha). |
| `alerta` | bool | `alerta_dias` | Pendiente con **más de 7 días**. |
| `ultimaConsulta` | ISO UTC \| null | `ultima_vez_visto` | Última vez vista en el SAT. |
| `dejoDeFigurarEn` | ISO UTC \| null | `resuelta_en` | Cuándo dejó de figurar. |
| **Solo detalle** | | | |
| `numeroCompromisoPago` | string \| null | `numero_compromiso_pago` | N° de compromiso de pago (fraccionamiento en el SAT). |
| `licenciaConducir` | string \| null | `licencia_conducir` | Licencia registrada en la papeleta. |
| `tipoDocumento` / `numeroDocumento` | string \| null | `tipo_documento` / `numero_documento` | Documento del infractor. |
| `primeraVezVista` | ISO UTC \| null | `primera_vez_visto` | Primera vez que el monitor la encontró. |
| `urlCopiaSat` | string \| null | `url_copia` | Enlace a la copia en el portal SAT (puede requerir sesión del SAT; preferir `fotoUrls`). |
| `sat` | object | — | Bloque compatible con la versión anterior. |

No se exponen datos internos: `revision`, `papeleta_id`, `datos_raw`,
`flag_exc`, `estado_copia`, `error_copia`.

### 6.2 `consultaSat` (`adt.papeleta.sat.import`)

| Campo | Descripción |
|---|---|
| `fecha` | Fecha/hora (UTC) de la última consulta procesada del monitor para la placa. |
| `resultado` | `CON_PAPELETAS` · `SIN_PAPELETAS` (u otro texto que envíe el monitor). |
| `mensaje` | Mensaje del SAT, si lo hubo. |

Útil para mostrar "Consultado en el SAT el 06/11/2026".

### 6.3 Cuándo una papeleta SAT es `PAGADO`

Lo calcula Odoo (`_compute_estado_pago`):
- el SAT la muestra como *pagada* / *cancelada*, **o**
- dejó de figurar en una consulta completa del SAT (`figuraEnSat = false`).

> Dejar de figurar no siempre es pago (puede ser anulación o descargo). Si la
> app quiere distinguirlo: `figuraEnSat = false` + `dejoDeFigurarEn` → "Ya no
> figura en el SAT".

### 6.4 Orden de captura SAT (`adt.captura.sat`)

| Campo | Tipo | Campo Odoo | Descripción |
|---|---|---|---|
| `id` | int | `id` | ID interno. |
| `documento` | string | `name` | Documento publicado por el SAT. |
| `placa` | string | `placa` | Placa normalizada. |
| `anio` | int \| null | `anio` | Año. |
| `concepto` | string \| null | `concepto` | Concepto (ej. papeleta, impuesto vehicular). |
| `placaOriginal` | string \| null | `placa_original` | Placa original informada por el SAT. |
| `referencia` | string \| null | `referencia` | Referencia (ej. N° de papeleta). |
| `monto` | number | `monto` | Monto en captura. |
| `moneda` | string | `currency_id` | `PEN`. |
| `vigente` | bool | `vigente` | `false` = levantada (dejó de figurar en el SAT). |
| `informeSatAl` | `YYYY-MM-DD` \| null | `fecha_actualizacion_sat` | Fecha del informe del SAT. |
| `detectadaEn` | ISO UTC \| null | `primera_vez_visto` | Cuándo se detectó. |
| `ultimaConsulta` | ISO UTC \| null | `ultima_vez_visto` | Última vez vista. |
| `levantadaEn` | ISO UTC \| null | `levantada_en` | Cuándo dejó de figurar. |
| `diasVigente` | int | `dias` | Días que lleva (o llevó) vigente. |

No se exponen datos internos de gestión: `gestion`, `responsable_id`, `notas`.

### 6.5 Bloque `capturaSat` (estado del vehículo)

| Campo | Campo Odoo | Descripción |
|---|---|---|
| `estado` | `fleet.vehicle.captura_sat_estado` | `SIN_CONSULTAR` · `SIN_ORDEN` · `CON_ORDEN` (última consulta válida). |
| `tieneOrdenCaptura` | — | `true` si `estado = CON_ORDEN`. **Mostrar alerta destacada.** |
| `ultimaConsulta` | `captura_sat_ultima_consulta` | Última consulta válida del agente. |
| `ordenesVigentes` / `montoEnCaptura` | — | Conteo y suma de las órdenes vigentes. |
| `ordenes` | — | Lista (6.4), vigentes primero. |

---

## 7. Errores

| HTTP | `error.code` | Causa |
|---|---|---|
| 401 | `TOKEN_MISSING` / `TOKEN_INVALID` / `TOKEN_EXPIRED` | Token ausente, inválido o vencido → volver al login. |
| 403 | `FORBIDDEN` | El vehículo pedido no pertenece al token. |
| 404 | `VEHICLE_NOT_FOUND` | No existe el vehículo (placa/ID). |
| 404 | `PAPELETA_NOT_FOUND` | No existe la papeleta SAT o no es del cliente. |
| 422 | `VALIDATION_ERROR` | `estado` inválido, `idVehiculo` no numérico, o token sin vehículo y sin `plate`/`idVehiculo`. |
| 422 | `PLATE_INVALID_FORMAT` | Placa con formato inválido. |
| 503 | `MODULE_NOT_INSTALLED` | `/v1/capturas-sat` sin el módulo `adt_captura_sat`. |
| 500 | `INTERNAL_ERROR` | Error del servidor. |

---

## 8. Cambios para la app (respecto a la versión anterior de este documento)

Los DTO de la app tienen valores por defecto e `ignoreUnknownKeys = true`, así
que **la app actual no se rompe**, pero hay que ajustar:

- `id` ahora es el ID de **`adt.papeleta.sat`**, no de `adt.papeleta`. Úsalo
  solo con `GET /v1/papeletas/{id}`.
- `origen` siempre es `SAT`.
- **Se eliminaron** (vienen con su default en el DTO): `modalidadPago`,
  `fechaVencimiento`, `diasParaVencer`, `estadoVencimiento`, `textoAlerta`,
  `fechaPago`, `tieneProrroga`, `cuotasTotal`, `cuotasPendientes`, `detalle`,
  `fechaCaptura`, `prorroga`, `cuotas`, `evidenciasFraccionamientoUrls`. El SAT
  no publica vencimientos ni cuotas; para alertar usar `alerta` y
  `diasDesdeInfraccion`.
- `resumen`: se quitaron `vencidas`, `porVencer`, `proximoVencimiento`; se
  agregó `conAlerta`.
- **Nuevos**: `estadoSat`, `reglamento`, `importe`, `gastosCostas`,
  `descuento`, `deuda`, `diasDesdeInfraccion`, `alerta`, `ultimaConsulta`,
  `dejoDeFigurarEn`, `consultaSat`, `capturaSat` y el endpoint
  `/v1/capturas-sat`.
- `POST /v1/papeletas/register` **no cambia**, pero crea una papeleta interna
  (`adt.papeleta`) que **no aparece** en este listado (no es del SAT).

---

## 9. Checklist para el front

- [ ] Pantalla **Mis papeletas SAT**: `GET /v1/papeletas` (sin params con login por placa).
- [ ] Banner rojo si `capturaSat.tieneOrdenCaptura` con `ordenesVigentes` y `montoEnCaptura`.
- [ ] Cabecera con `resumen`: `pendientes`, `montoPendienteTotal`, `conAlerta`; texto "Consultado en el SAT el …" con `consultaSat.fecha`.
- [ ] Tabs *Pendientes / Pagadas*: filtrar en el cliente o usar `?estado=`.
- [ ] Cada tarjeta: `numeroPapeleta`, `fechaPapeleta`, `falta`, `montoPendiente`, `estadoSat`; chip de alerta si `alerta`; "Ya no figura en el SAT" si `!figuraEnSat`.
- [ ] Tap → `GET /v1/papeletas/{id}`: desglose importe / gastos / descuento / deuda, licencia, compromiso de pago y galería `fotoUrls`.
- [ ] Sección **Órdenes de captura SAT** con `capturaSat.ordenes` (vigentes vs. levantadas).
- [ ] Mostrar **`montoPendiente`** como monto a pagar; no recalcular en el front.
- [ ] Estado vacío cuando `totalPapeletas = 0` (y `consultaSat` para decir si ya se consultó).
- [ ] Manejar 401 → logout / login.

---

## 10. Despliegue

Solo cambia el controlador de `adt_comercial` (sin modelos ni vistas nuevas):
basta con **reiniciar Odoo**. `adt_comercial` no depende de `adt_captura_sat`:
si no está instalado, `capturaSat` sale `null`.

```bash
curl -s -H "Authorization: Bearer <token>" "https://<host>/v1/papeletas" | jq
curl -s -H "Authorization: Bearer <token>" "https://<host>/v1/papeletas/11" | jq
curl -s -H "Authorization: Bearer <token>" "https://<host>/v1/capturas-sat" | jq
```
