# Papeletas en la App del Cliente — Guía de Integración

API REST para que la app del cliente ADT muestre las papeletas (multas de
tránsito) de su vehículo: listado con resumen, estado de vencimiento, monto
pendiente, cuotas de fraccionamiento, datos del SAT Lima y evidencias.

Fuente en el backend:
- `adt_comercial/controllers/mobile_api.py` → endpoints `GET /v1/papeletas` y
  `GET /v1/papeletas/<id>` (helpers `_serialize_papeleta`, `_papeletas_resumen`,
  `_papeleta_vencimiento`, `_papeleta_resolve_vehicle`).
- `adt_papeletas/models/papeleta.py` → modelo `adt.papeleta` y `adt.papeleta.cuota`.
- `adt_papeletas/models/papeleta_sat.py` → modelo `adt.papeleta.sat` (datos del SAT Lima).

---

## 1. Resumen

| Método | Ruta | Uso en la app |
|---|---|---|
| `GET` | `/v1/papeletas` | Pantalla "Mis papeletas": resumen + lista. |
| `GET` | `/v1/papeletas/{id}` | Pantalla de detalle de una papeleta. |
| `POST` | `/v1/papeletas/register` | (Ya existente, sin cambios) El cliente registra una papeleta con fotos. |

- Son rutas **REST normales** (`type='http'`): **no** usan el sobre JSON-RPC.
- Misma autenticación que el resto de `/v1/...`:

```
Authorization: Bearer <token>
```

- Mismo formato de respuesta que el resto de la API:

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": { ... },
  "meta": { "timestamp": "2026-11-04T15:00:00Z", "requestId": "uuid" }
}
```

> **Compatibilidad:** `GET /v1/papeletas` ya existía. Los campos que devolvía
> (`id`, `numeroPapeleta`, `fechaPapeleta`, `monto`, `idVehiculo`, `fotosCount`,
> `fotoUrls`, y en `data`: `idVehiculo`, `placa`, `totalPapeletas`, `papeletas`)
> **se mantienen igual**. Todo lo demás son campos nuevos; las versiones
> anteriores de la app siguen funcionando.

---

## 2. Permisos

El token solo puede ver papeletas de:
- **Login por placa** (`/v1/auth/login`): únicamente el vehículo del token.
- **Token sin vehículo, con cliente** (ej. login por email): los vehículos cuyo
  conductor (`driver_id`) es ese cliente.

Si se pide otro vehículo → `403 FORBIDDEN`. Si se pide el detalle de una
papeleta ajena → `404 PAPELETA_NOT_FOUND` (no se revela que existe).

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
GET /v1/papeletas?estado=TODAS
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
      "vencidas": 0,
      "porVencer": 1,
      "montoPendienteTotal": 528.0,
      "proximoVencimiento": "2026-11-07"
    },
    "papeletas": [
      {
        "id": 55,
        "numeroPapeleta": "D123456789",
        "fechaPapeleta": "2026-10-08",
        "monto": 528.0,
        "idVehiculo": 10,
        "fotosCount": 1,
        "fotoUrls": ["https://.../web/content/901/papeleta_55_1.jpg?access_token=..."],
        "placa": "ABC-123",
        "estado": "PENDIENTE",
        "origen": "SAT",
        "modalidadPago": "PAGO_COMPLETO",
        "montoPendiente": 528.0,
        "moneda": "PEN",
        "fechaVencimiento": "2026-11-07",
        "diasParaVencer": 3,
        "estadoVencimiento": "POR_VENCER",
        "textoAlerta": "Vence en 3 días",
        "fechaPago": null,
        "tieneProrroga": false,
        "cuotasTotal": 0,
        "cuotasPendientes": 0,
        "falta": "G58",
        "figuraEnSat": true
      },
      {
        "id": 41,
        "numeroPapeleta": "PAP-001",
        "fechaPapeleta": "2026-05-18",
        "monto": 150.0,
        "idVehiculo": 10,
        "fotosCount": 0,
        "fotoUrls": [],
        "placa": "ABC-123",
        "estado": "PAGADO",
        "origen": "MANUAL",
        "modalidadPago": "PAGO_COMPLETO",
        "montoPendiente": 0.0,
        "moneda": "PEN",
        "fechaVencimiento": "2026-06-17",
        "diasParaVencer": null,
        "estadoVencimiento": "PAGADA",
        "textoAlerta": null,
        "fechaPago": "2026-06-10",
        "tieneProrroga": false,
        "cuotasTotal": 0,
        "cuotasPendientes": 0,
        "falta": null,
        "figuraEnSat": false
      }
    ]
  },
  "meta": { "timestamp": "2026-11-04T15:00:00Z", "requestId": "..." }
}
```

Orden: `fechaPapeleta` descendente (la más reciente primero).

> El bloque `resumen` **siempre** cuenta todas las papeletas del vehículo,
> aunque se filtre la lista con `estado`.

---

## 4. `GET /v1/papeletas/{id}` — Detalle

Devuelve **todos los campos del listado** más los siguientes:

```json
{
  "detalle": "Estacionar en zona prohibida",
  "fechaCaptura": "2026-11-07",
  "prorroga": { "dias": 15, "motivo": "Trámite de descargo" },
  "cuotas": [
    {
      "id": 301,
      "nombre": "Cuota 1",
      "fechaVencimiento": "2026-10-15",
      "monto": 176.0,
      "estado": "PAGADO",
      "vencida": false
    },
    {
      "id": 302,
      "nombre": "Cuota 2",
      "fechaVencimiento": "2026-11-15",
      "monto": 176.0,
      "estado": "PENDIENTE",
      "vencida": false
    }
  ],
  "evidenciasFraccionamientoUrls": [],
  "sat": {
    "numero": "D123456789",
    "estado": "PENDIENTE",
    "figuraEnSat": true,
    "fechaInfraccion": "2026-10-08",
    "reglamento": "D.S. 016-2009-MTC",
    "falta": "G58",
    "importe": 528.0,
    "gastosCostas": 0.0,
    "descuento": 0.0,
    "deuda": 528.0,
    "numeroCompromisoPago": null,
    "ultimaConsulta": "2026-11-04T07:10:00Z",
    "dejoDeFigurarEn": null,
    "copiasUrls": ["https://.../web/content/950/copia.png?access_token=..."]
  }
}
```

- `prorroga` es `null` si no tiene prórroga.
- `cuotas` es `[]` si no está fraccionada.
- `sat` es `null` si la papeleta no fue encontrada en el SAT Lima (ej. papeleta
  registrada a mano o de otra municipalidad).

---

## 5. Referencia de campos

### 5.1 Campos de cada papeleta

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | int | ID interno. Usar para el detalle. |
| `numeroPapeleta` | string | N° de papeleta. |
| `fechaPapeleta` | `YYYY-MM-DD` | Fecha de la infracción. |
| `monto` | number | Monto original registrado. |
| `idVehiculo` / `placa` | int / string | Vehículo. |
| `fotosCount` / `fotoUrls` | int / string[] | Fotos de la papeleta. URLs públicas, se pueden usar directo en `Image.network`. |
| `estado` | enum | `PENDIENTE` · `PAGADO`. |
| `origen` | enum | `MANUAL` (registrada en Odoo/app) · `SAT` (detectada en el SAT Lima). |
| `modalidadPago` | enum | `PAGO_COMPLETO` · `FRACCIONADO`. |
| `montoPendiente` | number | **Lo que debe mostrarse como "a pagar"**. Ver 5.3. |
| `moneda` | string | `PEN`. |
| `fechaVencimiento` | `YYYY-MM-DD` \| null | Fecha límite (30 días desde la papeleta + prórroga; si es fraccionada, la próxima cuota pendiente). |
| `diasParaVencer` | int \| null | Días hasta el vencimiento (negativo = vencida). `null` si está pagada o sin fecha. |
| `estadoVencimiento` | enum | Ver 5.2. |
| `textoAlerta` | string \| null | Texto listo para mostrar: "Vence en 3 días", "Vence hoy", "Venció hace 2 días". |
| `fechaPago` | `YYYY-MM-DD` \| null | Fecha en que se marcó pagada. |
| `tieneProrroga` | bool | Si tiene prórroga. |
| `cuotasTotal` / `cuotasPendientes` | int | Conteo de cuotas (0 si no está fraccionada). |
| `falta` | string \| null | Código de falta del SAT (ej. `G58`). |
| `figuraEnSat` | bool | `true` si en la última consulta seguía apareciendo en el SAT Lima. |

### 5.2 `estadoVencimiento`

| Valor | Cuándo | Sugerencia UI |
|---|---|---|
| `VENCIDA` | Pendiente y ya pasó la fecha. | Rojo. |
| `VENCE_HOY` | Pendiente y vence hoy. | Rojo / naranja. |
| `POR_VENCER` | Pendiente, vence en 1 a 5 días. | Naranja. |
| `AL_DIA` | Pendiente, vence en más de 5 días. | Neutro. |
| `SIN_FECHA` | Pendiente sin fecha de vencimiento. | Neutro. |
| `PAGADA` | Estado `PAGADO`. | Verde. |

Se calcula **en cada request** con la fecha del servidor (zona Lima), así que
siempre está al día.

### 5.3 Cómo se calcula `montoPendiente`

1. `PAGADO` → `0`.
2. Si figura en el SAT con deuda → `sat.deuda` (incluye gastos/costas y descuentos del SAT).
3. Si es fraccionada → suma de las cuotas `PENDIENTE`.
4. Si no → `monto`.

`resumen.montoPendienteTotal` es la suma de `montoPendiente` de las pendientes.

---

## 6. Errores

| HTTP | `error.code` | Causa |
|---|---|---|
| 401 | `TOKEN_MISSING` / `TOKEN_INVALID` / `TOKEN_EXPIRED` | Token ausente, inválido o vencido → volver al login. |
| 403 | `FORBIDDEN` | El vehículo pedido no pertenece al token. |
| 404 | `VEHICLE_NOT_FOUND` | No existe el vehículo (placa/ID). |
| 404 | `PAPELETA_NOT_FOUND` | No existe la papeleta o no es del cliente. |
| 422 | `VALIDATION_ERROR` | `estado` inválido, `idVehiculo` no numérico, o token sin vehículo y sin `plate`/`idVehiculo`. |
| 422 | `PLATE_INVALID_FORMAT` | Placa con formato inválido. |
| 500 | `INTERNAL_ERROR` | Error del servidor. |

```json
{
  "success": false,
  "statusCode": 422,
  "error": { "code": "VALIDATION_ERROR", "message": "estado debe ser PENDIENTE, PAGADO o TODAS." },
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

---

## 7. Checklist para el front

- [ ] Pantalla **Mis papeletas**: llamar `GET /v1/papeletas` (sin params con login por placa).
- [ ] Cabecera con `resumen`: pendientes, `montoPendienteTotal`, `proximoVencimiento`; destacar `vencidas` / `porVencer`.
- [ ] Tabs o filtro *Pendientes / Pagadas*: filtrar en el cliente o usar `?estado=`.
- [ ] Cada tarjeta: `numeroPapeleta`, `fechaPapeleta`, `montoPendiente`, chip de color según `estadoVencimiento` y `textoAlerta`.
- [ ] Mostrar "Fraccionada · `cuotasPendientes`/`cuotasTotal` pendientes" cuando `modalidadPago = FRACCIONADO`.
- [ ] Tap → `GET /v1/papeletas/{id}`: detalle, cuotas, prórroga, bloque SAT y galería (`fotoUrls`, `sat.copiasUrls`, `evidenciasFraccionamientoUrls`).
- [ ] Mostrar **`montoPendiente`** como monto a pagar (no `monto`), no recalcular en el front.
- [ ] Estado vacío cuando `totalPapeletas = 0`.
- [ ] Manejar 401 → logout / login.

---

## 8. Despliegue

Solo cambia el controlador de `adt_comercial` (sin modelos ni vistas nuevas):
basta con **reiniciar Odoo**. No requiere actualizar el módulo.

Prueba rápida:

```bash
curl -s -H "Authorization: Bearer <token>" "https://<host>/v1/papeletas" | jq
curl -s -H "Authorization: Bearer <token>" "https://<host>/v1/papeletas/55" | jq
```
