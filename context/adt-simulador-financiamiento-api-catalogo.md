# Catálogo de servicios API — Simulador de financiamiento

Módulo Odoo: `adt_simulador_prospecto_financiamiento`

## Convenciones generales

- Todos los servicios son **POST** con cuerpo **JSON-RPC 2.0** de Odoo y requieren **sesión de usuario** (cookie `session_id`).
- Autenticación previa: `POST /web/session/authenticate` con `{"jsonrpc":"2.0","method":"call","params":{"db":"...","login":"...","password":"..."}}`.
- Envoltura de la petición:

```json
{ "jsonrpc": "2.0", "method": "call", "params": { ...parámetros del servicio... } }
```

- La respuesta útil viene en `result`. Todos los servicios devuelven `ok: true | false`.
- **Error de negocio** (`ok: false`):

```json
{ "ok": false, "codigo": "parametros_invalidos", "error": "Mensaje para mostrar al usuario" }
```

| codigo | Cuándo |
| --- | --- |
| `parametros_invalidos` | Falta un campo, tipo o formato incorrecto |
| `validacion` | Regla de negocio (cuota inicial ≥ importe, plazo no entero, etc.) |
| `no_encontrado` | El vehículo, cliente o simulación no existe |
| `cliente_existente` | Al crear un cliente con documento ya registrado (incluye `cliente`) |
| `pdf_no_disponible` | El servidor no pudo generar el PDF (ej. falta wkhtmltopdf) |

- La **TEA y el importe a financiar nunca viajan** en la API: los toma Odoo del vehículo configurado. La app no calcula nada.
- Fechas: `AAAA-MM-DD`. Montos: número con 2 decimales.

---

## Flujo recomendado en la app

1. `vehiculos` → elegir vehículo.
2. `clientes/buscar` → elegir cliente, o `clientes/crear` si no existe.
3. `cuotas` → enviar vehículo, cuota inicial, plazo, cliente, frecuencia y fecha de inicio. Mostrar el mensaje devuelto.
4. `simulaciones/cronograma` → mostrar el cronograma (si se envió fecha de inicio).
5. `simulaciones/<id>/pdf` → descargar el PDF con el cronograma para compartirlo con el cliente.
6. `simulaciones/listar` / `detalle` → historial.

---

## 1. Vehículos financiables

`POST /api/simulador/vehiculos` — sin parámetros.

```json
{ "ok": true, "vehiculos": [ { "id": 1, "nombre": "TVS DELUXE 200CC" } ] }
```

## 2. Buscar clientes

`POST /api/simulador/clientes/buscar`

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `texto` | string | Sí | Mínimo 2 caracteres. Busca en nombre, documento, teléfono y celular |
| `limite` | int | No | 1–50 (defecto 20) |

```json
{ "ok": true, "clientes": [
  { "id": 458, "nombre": "Juan Pérez", "documento": "12345678", "telefono": "999888777", "email": null }
] }
```

## 3. Crear cliente

`POST /api/simulador/clientes/crear`

| Parámetro | Tipo | Obligatorio |
| --- | --- | --- |
| `nombre` | string | Sí |
| `documento` | string | No (si se envía, debe ser único) |
| `telefono` | string | No |
| `email` | string | No |

Éxito:

```json
{ "ok": true, "mensaje": "Cliente registrado correctamente.",
  "cliente": { "id": 460, "nombre": "Ana Ruiz", "documento": "87654321", "telefono": null, "email": null } }
```

Si el documento ya existe: `ok: false`, `codigo: "cliente_existente"` y `cliente` con el registro existente, para relacionarlo directamente.

## 4. Detalle de cliente

`POST /api/simulador/clientes/detalle` — `{ "cliente_id": 458 }` → `{ "ok": true, "cliente": { ... } }`

## 5. Generar simulación (calcular + registrar)

`POST /api/simulador/cuotas`

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `vehiculo_id` | int | Sí | Id devuelto por `vehiculos` |
| `cuota_inicial` | número | Sí | Debe ser menor que el importe a financiar |
| `plazo_meses` | int | Sí | Entero positivo |
| `cliente_id` | int | No | Relaciona la simulación con el cliente |
| `frecuencia` | string | No | `mensual` (defecto), `semanal` o `diaria` |
| `fecha_inicio` | string | No | `AAAA-MM-DD`. Si se envía, se genera el cronograma |

Las tres cuotas se calculan siempre juntas; la app decide cuál mostrar.

```json
{
  "ok": true,
  "mensaje": "Simulación generada correctamente.",
  "simulacion_id": 12,
  "numero": "SIM-00012",
  "fecha": "2026-09-20 15:30:00",
  "origen": "app",
  "vehiculo": { "id": 1, "nombre": "TVS DELUXE 200CC" },
  "cliente": { "id": 458, "nombre": "Juan Pérez", "documento": "12345678", "telefono": null, "email": null },
  "cuota_inicial": 2000.0,
  "plazo_meses": 26,
  "frecuencia": "semanal",
  "fecha_inicio": "2026-10-01",
  "capital": 23000.0,
  "cuota_mensual": 1143.04,
  "cuota_semanal": 266.71,
  "cuota_diaria": 38.1,
  "cronograma": {
    "generado": true,
    "cantidad_cuotas": 112,
    "total_a_pagar": 29719.13,
    "primera_fecha": "2026-10-08",
    "ultima_fecha": "2028-11-23"
  }
}
```

Sin `fecha_inicio`: `cronograma.generado` es `false` y `cantidad_cuotas` es 0. `cliente` es `null` si no se relacionó ninguno.

## 6. Cronograma de una simulación

`POST /api/simulador/simulaciones/cronograma` — `{ "simulacion_id": 12 }`

```json
{
  "ok": true, "simulacion_id": 12, "numero": "SIM-00012",
  "frecuencia": "semanal", "fecha_inicio": "2026-10-01",
  "cantidad_cuotas": 112, "total_a_pagar": 29719.13,
  "cuotas": [
    { "numero": 1, "fecha": "2026-10-08", "cuota": 266.71, "saldo": 29452.42 },
    { "numero": 112, "fecha": "2028-11-23", "cuota": 114.32, "saldo": 0.0 }
  ]
}
```

### Reglas del cronograma

El `.md` del simulador no define un cronograma. Esta es la regla mínima implementada, basada en las equivalencias de la hoja (mes = 30 días, semana = 7 días) y sin reglas extra de fechas:

| Frecuencia | Cantidad de cuotas | Monto | Vencimiento de la cuota k |
| --- | --- | --- | --- |
| `mensual` | `plazo_meses` | C/ Mensual | fecha de inicio + k meses |
| `semanal` | `ceil(plazo × 30 / 7)` | C/ Semanal | fecha de inicio + 7·k días |
| `diaria` | `plazo × 30` | C/ Diaria | fecha de inicio + k días (todos los días) |

- La **última cuota se ajusta** para que la suma sea exactamente el total del crédito (`C/Mensual × plazo`).
- `saldo` = lo que falta pagar del total del crédito.
- No excluye domingos ni feriados, ni separa capital e interés.

## 7. Listar simulaciones

`POST /api/simulador/simulaciones/listar`

| Parámetro | Tipo | Descripción |
| --- | --- | --- |
| `cliente_id` | int | Filtra por cliente (opcional) |
| `limite` | int | 1–50 (defecto 20) |
| `offset` | int | Paginación (defecto 0) |

```json
{ "ok": true, "total": 37, "simulaciones": [ { ...misma estructura que el servicio 5, sin "ok" ni "mensaje"... } ] }
```

## 8. Detalle de simulación

`POST /api/simulador/simulaciones/detalle` — `{ "simulacion_id": 12 }` → misma estructura que el servicio 5.

## 9. Descargar PDF de la simulación

`GET /api/simulador/simulaciones/<simulacion_id>/pdf`

Este es el **único servicio que no es JSON-RPC**: es un GET con la misma sesión (cookie `session_id`) y devuelve el archivo directamente.

| | |
| --- | --- |
| Respuesta correcta | `200`, `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="SIM-00012.pdf"` |
| Simulación inexistente | `404` con JSON `{ "ok": false, "codigo": "no_encontrado", "error": "..." }` |
| No se pudo generar | `500` con JSON `{ "ok": false, "codigo": "pdf_no_disponible", "error": "..." }` |

Contenido del PDF:
- Logo y datos de la compañía de Odoo (encabezado estándar).
- Número y fecha de la simulación, cliente (nombre, documento, teléfono), vehículo y asesor.
- Cuota inicial, capital, plazo, frecuencia, fecha de inicio y **solo la cuota de la frecuencia elegida** (mensual, semanal o diaria).
- Total a pagar en cuotas y el **cronograma completo** (N°, fecha, cuota, saldo).
- Si la simulación no tiene fecha de inicio, el PDF se genera sin cronograma y lo indica.
- No incluye la TEA ni el importe base del vehículo.

Uso en la app (React Native): descargar con la cookie de sesión hacia un archivo local y compartirlo, por ejemplo con `react-native-blob-util` / `expo-file-system` y `Share`:

```text
GET https://<servidor>/api/simulador/simulaciones/12/pdf
Cookie: session_id=<sesión>
```

También se puede imprimir desde Odoo: botón **Imprimir PDF** en la simulación y **Descargar PDF** en la pantalla Simular cuota.
