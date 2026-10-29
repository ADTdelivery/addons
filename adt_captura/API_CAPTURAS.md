# API de Capturas — app móvil

Referencia de los endpoints que usa la app de capturas, en el orden del flujo:
autenticarse → listar a quién capturar → ver la cuenta y el expediente → ubicar el GPS →
registrar la captura → subir evidencias.

| # | Módulo | Método y ruta | Para qué |
|---|---|---|---|
| 1 | Autenticación | `POST /adt_expedientes/mobile/token/create` | Generar token |
| 2 | Capturas | `GET /api/adt/captura/mora` | Listar vehículos a capturar, **del que más debe al que menos** |
| 3 | Capturas | `GET /api/adt/captura/mora/detail/cuenta` | Detalle de la cuenta y sus cuotas |
| 4 | Capturas | `GET /api/adt/captura/mora/detail/expediente` | Expediente del cliente: **un solo documento (URL)** |
| 4b | Capturas | `GET /api/adt/expediente/{id}/documento` | Abrir/descargar ese documento (la URL la da el punto 4) |
| 5 | GPS | `GET /api/adt/traccar/device/by-plate` | Buscar el dispositivo GPS por placa |
| 6 | Capturas | `POST /api/adt/captura/record` | Registrar la captura |
| 7 | Capturas | `POST /api/adt/captura/record/{id}/evidencias` | Subir evidencias (fotos / videos) |
| 7b | Capturas | `GET /api/adt/captura/record/{id}/evidencias/status` | Consultar si terminó la subida |

**Base URL:** `https://<servidor-odoo>` (en los ejemplos, `{{base}}`).

---

## Cambios de esta versión

| Endpoint | Cambio | ¿Rompe la app? |
|---|---|---|
| `GET /mora` | Aplica el **filtro de posibles capturas** configurado en Odoo (Capturas > Configuración): por cronograma solo entran las cuentas con más de N días de mora **y** más de M cuotas vencidas (inicial: 7 días, 1 cuota); con papeletas SAT pendientes entran todas. Nuevo campo `filtro_captura` con los valores vigentes. | No. Solo cambian las filas que llegan. |
| `GET /mora` | Orden por defecto: **lo que debe cada uno** (`monto_vencido + deuda_sat`) de mayor a menor. Nuevo campo `deuda_total`. Nuevo parámetro `order` (`monto` \| `dias`). | No. Antes ordenaba por días de mora; con `order=dias` se mantiene ese orden. |
| `GET /mora/detail/expediente` | Ya **no** devuelve una URL por foto (`documento_identidad`, `licencia`, `domicilio`, …). Devuelve `record.documento` con **una sola URL** al expediente completo (PDF o Word). | **Sí.** La pantalla de expediente debe leer `record.documento.url`. |
| `GET /api/adt/expediente/{id}/documento` | **Nuevo.** Entrega el documento del expediente con una URL firmada que vence a las 24 h. | — |
| `POST /record` | Nuevo campo `fecha_compromiso`, **obligatorio** si `tipo_captura = "compromiso"`. Antes un compromiso de pago siempre fallaba, porque el modelo exige esa fecha. | No (corrige un error). |
| `GET /mora/detail` (legado, por `cuenta_id`) | Su bloque `expediente_id` usa el mismo formato de documento único. | Sí, si la app aún lo usa. |

---

## 1. Generar token

`POST /adt_expedientes/mobile/token/create` · `Content-Type: application/json`

Es un endpoint JSON-RPC de Odoo: la respuesta llega dentro de `result`.

```json
{
  "jsonrpc": "2.0",
  "params": {
    "db": "adt_produccion",
    "login": "capturador@adt.pe",
    "password": "********",
    "device_info": {
      "device_id": "UUID-del-dispositivo",
      "device_name": "Galaxy A54",
      "device_os": "Android 14",
      "app_version": "1.4.0"
    },
    "days_valid": 30
  }
}
```

Respuesta OK:

```json
{
  "jsonrpc": "2.0",
  "id": null,
  "result": {
    "success": true,
    "data": {
      "token": "<token de 64 caracteres>",
      "expiry": "2026-11-26 10:30:00",
      "user": {"id": 7, "name": "Juan Pérez", "login": "capturador@adt.pe"},
      "device_bound": true,
      "message": "Token generado exitosamente. Guárdalo de forma segura."
    }
  }
}
```

- El token se devuelve **una sola vez**. Guárdalo de forma segura en el dispositivo.
- `user.id` es el valor que va en `registrado_por` al registrar una captura (punto 6).
- Se envía en cada llamada con el header `Authorization: Bearer <token>`.
- Error: `result.success = false` y `result.error` (`"Invalid credentials"`, `"Missing required fields"`, …).

> ⚠️ **Importante:** hoy los endpoints de capturas (`/api/adt/captura/...`) **no validan el token**
> (están con `auth='none'`), y el de GPS es público. La app debe enviar el header igual, para
> que el día que se active la validación no haya que cambiar nada. Ver "Pendientes" al final.

---

## 2. Listar vehículos a capturar

`GET /api/adt/captura/mora`

Una fila por cuenta con cuotas vencidas y/o papeletas SAT pendientes, según el filtro de
Capturas > Configuración (el mismo de la lista "Clientes en Mora" de Odoo): las cuotas vencidas
cuentan solo si la más antigua tiene más de `dias_mora_mayor_a` días **y** son más de
`cuotas_vencidas_mayor_a`; las papeletas SAT pendientes cuentan siempre. Una cuenta con cuotas
bajo el filtro y papeletas sale con `source_type = "papeleta"`. Por defecto, **ordenada
por lo que debe cada uno**: `deuda_total = monto_vencido + deuda_sat`, de mayor a menor. Si dos
cuentas deben lo mismo, va primero la de más días de mora.

### Parámetros (query)

| Parámetro | Valores | Por defecto | Descripción |
|---|---|---|---|
| `order` | `monto` \| `dias` | `monto` | `monto`: deuda total, de mayor a menor. `dias`: días de mora, de mayor a menor (orden anterior). |
| `source_type` | `mora` \| `papeleta` \| `ambos` \| `none` | — | Origen: cuotas vencidas, papeletas SAT o ambos. |
| `captura_prioridad` | `normal` \| `urgente` | — | Prioridad marcada en la cuenta. |
| `captura_existente` | `0` \| `1` \| `todos` | `0` | Por defecto **excluye** las cuentas que ya tienen una captura activa. |
| `limit` | entero | `100` | Tamaño de página. |
| `offset` | entero | `0` | Desplazamiento. El orden se aplica **antes** de paginar, así la página 2 sigue el mismo orden. |

Ejemplo: `GET {{base}}/api/adt/captura/mora?limit=20&offset=0`

### Respuesta 200

```json
{
  "count": 352,
  "filtro_captura": {"dias_mora_mayor_a": 7, "cuotas_vencidas_mayor_a": 1},
  "records": [
    {
      "client": {"id": 1532, "name": "ROSA QUISPE MAMANI"},
      "cuenta_id": {
        "id": 845,
        "reference_no": "CTA-000845",
        "state": "en_curso",
        "tipo_financiera": "Financiera Confianza",
        "periodicidad": "semanal",
        "monto_total": 9800.0,
        "monto_cuota": 180.0,
        "qty_cuotas": 52,
        "qty_cuotas_pagadas": 20,
        "qty_cuotas_restantes": 32,
        "qty_cuotas_retrasado": 6,
        "cuotas_saldo": 5760.0,
        "mora_total": 54.0,
        "fecha_desembolso": "2026-02-10"
      },
      "vehicle_id": {"id": 120, "display_name": "TVS King / ABC-123", "license_plate": "ABC-123"},
      "source_type": "ambos",
      "papeleta_id": {"id": 77, "name": "P-0458821", "monto": 462.0},
      "papeletas_sat": 2,
      "deuda_sat": 924.0,
      "dias_mora": 41,
      "numero_cuotas_vencidas": 6,
      "monto_vencido": 1080.0,
      "deuda_total": 2004.0,
      "fecha_cronograma": "2026-09-16",
      "adviser": {"id": 12, "name": "María Torres"},
      "captura_existente": false,
      "captura_prioridad": "urgente",
      "en_mantenimiento_tvs": false,
      "dias_en_mantenimiento_tvs": 0,
      "total_capturas": 1,
      "ultima_captura_hace": "3 meses"
    }
  ]
}
```

| Campo | Descripción |
|---|---|
| `deuda_total` | **Nuevo.** `monto_vencido + deuda_sat`: es el criterio del orden por defecto. |
| `monto_vencido` / `numero_cuotas_vencidas` / `dias_mora` | Cuotas vencidas del cronograma; los días se cuentan desde la cuota vencida más antigua. |
| `deuda_sat` / `papeletas_sat` / `papeleta_id` | Papeletas SAT pendientes; `papeleta_id` es la más antigua. |
| `cuenta_id.cuotas_saldo` | Todo lo que falta pagar del crédito (vencido o no). |
| `total_capturas` / `ultima_captura_hace` | Capturas anteriores del vehículo o de la cuenta. |

Error 500: `{"error": "<detalle>"}`.

---

## 3. Detalle de la cuenta

`GET /api/adt/captura/mora/detail/cuenta?vehicle_id={id}`

Toma la cuenta más reciente del vehículo.

```json
{
  "count": 1,
  "record": {
    "id": 845,
    "reference_no": "CTA-000845",
    "state": "en_curso",
    "tipo_financiera": "Financiera Confianza",
    "periodicidad": "semanal",
    "monto_total": 9800.0,
    "monto_cuota": 180.0,
    "qty_cuotas": 52,
    "qty_cuotas_pagadas": 20,
    "qty_cuotas_restantes": 32,
    "qty_cuotas_retrasado": 6,
    "cuotas_saldo": 5760.0,
    "monto_total_vencido": 1080.0,
    "mora_total": 54.0,
    "fecha_desembolso": "2026-02-10",
    "mora_pendiente": 54.0,
    "moras_dias_total": 41,
    "dias_mora": 41,
    "cuotas": [
      {
        "id": 10231,
        "name": "Cuota 21",
        "fecha_vencimiento": "2026-09-16",
        "fecha_pago": null,
        "monto_cuota": 180.0,
        "monto_pagado": 0.0,
        "monto_pendiente": 180.0,
        "payment_state": "retrasado",
        "mora": 9.0,
        "dias_mora": 41,
        "monto_mora": 9.0,
        "numero_operacion": null
      }
    ]
  }
}
```

| Estado | Respuesta |
|---|---|
| 400 | `{"error": "vehicle_id is required"}` / `"vehicle_id must be an integer"` |
| 404 | `{"error": "vehicle not found"}` / `"No cuenta found for this vehicle"` |

---

## 4. Expediente del cliente (un solo documento)

`GET /api/adt/captura/mora/detail/expediente?vehicle_id={id}`

Busca al cliente por la cuenta del vehículo (o por su conductor) y devuelve su expediente más
reciente. **El expediente completo llega como una sola URL**, sea cual sea la forma en que se
cargó:

| `documento.origen` | Cuándo | Qué entrega la URL |
|---|---|---|
| `archivo` | Se subió el expediente en un solo archivo (**PDF o Word**). Es la forma de trabajo desde ahora. | Ese mismo archivo. |
| `generado` | Expediente anterior, cargado como fotos sueltas (DNI, licencia, recibo, domicilio…). | Un **PDF generado** con todas esas fotos (el reporte del expediente). |
| `documento: null` | El expediente no tiene nada cargado. | — |

Así la app siempre hace lo mismo: abrir `documento.url`.

### Respuesta 200

```json
{
  "count": 1,
  "record": {
    "id": 311,
    "name": "EXP-000311",
    "state": "aprobado",
    "fecha": "2026-02-03",
    "cliente": {"id": 1532, "name": "ROSA QUISPE MAMANI", "vat": "45871236"},
    "asesora": {"id": 12, "name": "María Torres"},
    "documento": {
      "origen": "archivo",
      "nombre": "Expediente_Rosa_Quispe.pdf",
      "mimetype": "application/pdf",
      "estado": "aceptado",
      "observaciones": null,
      "url": "https://<servidor>/api/adt/expediente/311/documento?expira=1793212800&firma=3f9c…",
      "expira": "2026-10-28T15:20:00+00:00"
    },
    "referencias": [
      {"nombre": "Luis Quispe", "telefono": "987654321", "vinculo": "Hermano"}
    ]
  }
}
```

| Campo | Descripción |
|---|---|
| `documento.url` | URL directa al documento. No necesita sesión de Odoo ni token. |
| `documento.mimetype` | `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (.docx) o `application/msword` (.doc). |
| `documento.estado` / `observaciones` | Revisión del archivo cargado (`aceptado` / `rechazado`). `null` cuando el PDF se genera desde fotos. |
| `documento.expira` | La URL vence a las **24 h** (UTC). Pasado ese tiempo, vuelve a llamar a este endpoint para obtener una nueva. |
| `referencias` | Solo las que tienen nombre o teléfono. |

Sin cliente o sin expediente: `{"count": 0, "record": null}`.

> Ya **no** se devuelven los bloques `documento_identidad`, `licencia`, `recibo_servicios`,
> `sentinel`, `mototaxista`, `no_mototaxista` ni `domicilio` con una URL por foto. Todo está
> dentro del documento.

## 4b. Abrir o descargar el documento

`GET /api/adt/expediente/{id}/documento?expira=…&firma=…[&descargar=1]`

No armes esta URL a mano: úsala tal cual llega en `documento.url`.

- Sin `descargar`, el PDF se abre en el visor (`Content-Disposition: inline`).
- Con `&descargar=1`, se descarga como archivo. Los Word siempre se descargan.
- React Native: `Linking.openURL(url)` o un visor de PDF con `{ uri: url }`. Flutter: `url_launcher` o un visor de PDF con la URL.

| Estado | Significado |
|---|---|
| 200 | El archivo (`Content-Type` según el tipo). |
| 403 | `{"error": "Enlace inválido."}`: firma alterada o falta un parámetro. |
| 404 | Expediente inexistente o sin documentos. |
| 410 | `{"error": "El enlace venció…"}`: vuelve a pedir el expediente (punto 4). |
| 500 | No se pudo generar o leer el documento. |

---

## 5. Buscar dispositivo GPS por placa

`GET /api/adt/traccar/device/by-plate?plate={placa}`

Busca en Traccar el dispositivo cuyo nombre es la placa (sin distinguir mayúsculas).

```json
{
  "success": true,
  "plate": "ABC-123",
  "new_device_id": 534,
  "status": "online",
  "lastUpdate": "2026-10-27T09:41:12.000-05:00"
}
```

- `lastUpdate` llega en hora de Perú (UTC−5).
- 400: falta `plate`. 404: `{"success": false, "error": "No se encontró ningún dispositivo con la placa …", "total_devices_searched": <int>}`. 500: error de conexión con Traccar.

> ⚠️ **Efecto secundario:** además de buscar, este endpoint **reasigna en Traccar** el permiso
> del usuario 8 (el usuario de seguimiento de la app): quita el vehículo que tenía y le asigna
> el de esta placa. Por eso solo se debe llamar cuando el capturador va a seguir ese vehículo,
> no para consultas en lote.

---

## 6. Registrar la captura

`POST /api/adt/captura/record` · `Content-Type: application/json`

Es JSON-RPC: acepta el cuerpo plano o dentro de `params`. La respuesta llega en `result`.

```json
{
  "jsonrpc": "2.0",
  "params": {
    "tipo_captura": "compromiso",
    "vehiculo_id": 120,
    "registrado_por": 7,
    "moto_recogida": false,
    "motivo_no_recogida": "Cliente ausente",
    "fecha_compromiso": "2026-11-05",
    "comentarios_captura": "Se acordó el pago con la esposa del titular."
  }
}
```

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `tipo_captura` | `inmediata` \| `compromiso` | Sí | Captura inmediata o compromiso de pago. |
| `vehiculo_id` | int | Sí | `vehicle_id.id` del listado (punto 2). |
| `registrado_por` | int | Sí | ID del usuario capturador (`user.id` del token, punto 1). |
| `moto_recogida` | bool | No | `true` si se recogió la moto. |
| `motivo_no_recogida` | texto | Si `moto_recogida` es `false` | Por qué no se recogió. |
| `fecha_compromiso` | `YYYY-MM-DD` | **Si `tipo_captura = "compromiso"`** | **Nuevo.** Fecha comprometida para el pago; debe ser futura. |
| `comentarios_captura` | texto | No | Comentarios libres. |

La cuenta y el cliente se toman de la cuenta más reciente del vehículo. Al crear la captura:
- el vehículo cambia de estado;
- se guardan el origen (cuotas / papeletas SAT) y las papeletas pendientes;
- se envía una notificación push al cliente.

Respuesta OK:

```json
{"jsonrpc": "2.0", "id": null, "result": {"id": 958}}
```

`result.id` es el `{id}` para subir evidencias (punto 7).

Errores: llegan como error JSON-RPC (`error.data.message`), con el código entre corchetes al inicio:

| Mensaje | Causa |
|---|---|
| `[400] tipo_captura debe ser "inmediata" o "compromiso".` | Tipo inválido. |
| `[400] vehiculo_id es requerido.` / `registrado_por es requerido.` | Falta un campo. |
| `[404] El vehículo con id … no existe en el sistema.` | Vehículo inexistente. |
| `[422] motivo_no_recogida es requerido cuando moto_recogida es false.` | Falta el motivo. |
| `[422] fecha_compromiso es requerida cuando tipo_captura es "compromiso"…` | **Nuevo.** |
| `[422] fecha_compromiso debe ser una fecha futura.` | **Nuevo.** |
| `[422] No existe una cuenta comercial asociada al vehículo id=….` | Vehículo sin cuenta. |

---

## 7. Subir evidencias

`POST /api/adt/captura/record/{id}/evidencias` · `multipart/form-data`

Envía uno o más archivos en el campo `files[]` (también se acepta `files`).

| Tipo | Formatos |
|---|---|
| Imágenes | `jpg`, `jpeg`, `png`, `webp` |
| Videos | `mp4`, `mov`, `avi` |

Si el teléfono envía `application/octet-stream`, el tipo se deduce de la extensión.

La subida se procesa en segundo plano. La respuesta llega de inmediato:

```json
{"captura_id": 958, "evidencias_status": "processing", "files_received": 3}
```

| Estado | Respuesta |
|---|---|
| 202 | Recibido; se está guardando. |
| 400 | No se recibieron archivos. |
| 404 | La captura no existe. |
| 415 | Tipo de archivo no permitido; incluye `tipos_permitidos`. |

### 7b. Estado de la subida

`GET /api/adt/captura/record/{id}/evidencias/status`

```json
{"captura_id": 958, "evidencias_status": "completed"}
```

Estados: `pending` (no se subió nada), `processing`, `completed`, `failed`.

> El estado se guarda en la memoria del proceso de Odoo. Con varios workers, puede leer
> `pending` aunque la subida haya terminado en otro worker.

---

## Pendientes recomendados

1. **Validar el token en `/api/adt/captura/...`.** Hoy son públicos y devuelven datos de
   clientes (nombres, deudas, expedientes) a quien conozca la URL. El token ya existe (punto 1);
   falta exigirlo con `Authorization: Bearer <token>`. Hacerlo cuando la app ya envíe el header.
2. **GPS por placa** reasigna permisos en Traccar con un `GET`. Convendría separar la búsqueda
   (`GET`) de la asignación (`POST`).
3. **Estado de evidencias:** pasar el estado a un campo de la captura, para que funcione con
   varios workers.
