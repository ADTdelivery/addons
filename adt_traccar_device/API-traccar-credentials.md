# API: Credenciales Traccar por vehículo

Servicio REST para que una app cliente obtenga las credenciales de Traccar
(email + password + URL) de **un vehículo específico**, y se conecte
directamente al websocket de Traccar para recibir su ubicación GPS en vivo.

Módulo: `adt_traccar_device`. Implementación: `controllers/traccar_credentials_api.py`.

---

## 1. Endpoint

```
GET /v1/app/traccar-credentials
```

- **Formato**: `type='http'`, respuesta `application/json; charset=utf-8`.
- **CORS**: habilitado (`cors='*'`).
- **CSRF**: deshabilitado.
- **HTTPS obligatorio** en producción — el response trae un password en texto plano.

### Base URL

```
https://<tu-dominio-odoo>/v1/app/traccar-credentials
```

---

## 2. Autenticación — dos formas de pedirlo

El mismo endpoint acepta **dos** formas de identificar el vehículo. Se puede usar cualquiera de las dos según lo que ya tenga la app integrada.

### 2.a) Con Bearer token (`mobile.token`)

El vehículo se resuelve automáticamente a partir del token — no hace falta mandar la placa.

```
GET /v1/app/traccar-credentials
Authorization: Bearer <token>
```

El token se obtiene antes con el login por placa ya existente en el módulo `adt_comercial`:

```
POST /v1/auth/login
Content-Type: application/json

{ "plate": "ABC-123" }
```

Respuesta relevante de ese login:
```json
{
  "success": true,
  "data": {
    "token": "a1b2c3d4...",
    "vehicleId": 42,
    "licensePlate": "ABC-123",
    "partnerId": 17,
    "partnerName": "Juan Pérez",
    "expiresAt": "2026-11-13 00:00:00"
  }
}
```
El `token` devuelto ahí es el que va en el header `Authorization: Bearer <token>` de este endpoint. Vence a los 90 días.

### 2.b) Directo por placa, sin token

```
GET /v1/app/traccar-credentials?plate=ABC-123
```

No requiere login previo ni header `Authorization`. Mismo criterio de seguridad que ya usa `POST /v1/auth/login`: **la placa alcanza** para identificar el vehículo, sin ninguna otra credencial. Pensado para apps que no manejan sesión/token y solo necesitan resolver todo a partir de la placa en el momento.

### Si se mandan ambos (token + plate)

La placa debe coincidir con el vehículo asociado al token. Si no coincide, responde `403 PLATE_TOKEN_MISMATCH` (evita que un token válido se use para "probar" placas de otros clientes).

### Si no se manda ninguno de los dos

Responde `401 UNAUTHORIZED`.

---

## 3. Parámetros

| Parámetro | Ubicación | Tipo | Requerido | Descripción |
|---|---|---|---|---|
| `Authorization` | Header | `Bearer <token>` | Uno de los dos (ver sección 2) | Token de `mobile.token`, obtenido en `POST /v1/auth/login`. |
| `plate` | Query string | string | Uno de los dos (ver sección 2) | Placa del vehículo. Formato: `[A-Z0-9]{2,4}-?[A-Z0-9]{2,4}` (ej. `ABC-123`, `ABC123`). No sensible a mayúsculas/minúsculas ni a espacios (se normaliza). |

---

## 4. Respuesta exitosa — `200 OK`

```json
{
  "success": true,
  "statusCode": 200,
  "data": {
    "traccar_url": "http://52.15.86.160:8082",
    "traccar_ws_url": "ws://52.15.86.160:8082/api/socket",
    "email": "juan@gmail.com",
    "password": "xY9k2-Qp7z1RmN0v",
    "device_id": 560,
    "unique_id": "355488987654321",
    "plate": "ABC-123"
  },
  "meta": {
    "timestamp": "2026-08-15T14:32:10Z"
  }
}
```

### Diccionario de campos (`data`)

| Campo | Tipo | Descripción |
|---|---|---|
| `traccar_url` | string | URL base HTTP(S) del servidor Traccar (config `adt_traccar.url`). Se usa para autenticar y para llamadas REST directas a Traccar si hicieran falta. |
| `traccar_ws_url` | string | URL del websocket de Traccar (`ws://` o `wss://` según `traccar_url`), ya armada con el sufijo `/api/socket`. Ver sección 6. |
| `email` | string | Login del **usuario Traccar** de este vehículo (no necesariamente igual al email del cliente en Odoo — ver nota abajo). |
| `password` | string | Password del usuario Traccar, **en texto plano**. Generado aleatoriamente por Odoo al registrar el vehículo. |
| `device_id` | integer | ID interno del dispositivo (`fleet`) dentro de Traccar. |
| `unique_id` | string | IMEI del dispositivo GPS (campo `uniqueId` en Traccar). |
| `plate` | string | Placa del vehículo, tal como quedó registrada al momento de crear la credencial. |

> **Nota sobre `email`**: si el cliente en Odoo tiene más de un vehículo registrado en Traccar, cada vehículo tiene su **propio** usuario Traccar (no se comparte), para que el login quede acotado a un solo dispositivo. El primer vehículo del cliente usa su email real; el segundo usa una variante técnica (`juanv2@dominio`), el tercero `juanv3@dominio`, etc. No asumir que `email` es igual al email de contacto del cliente en Odoo.

---

## 5. Respuestas de error

Mismo formato en todos los casos:

```json
{
  "success": false,
  "statusCode": 404,
  "error": {
    "code": "NOT_FOUND",
    "message": "Este vehículo no tiene un dispositivo Traccar registrado."
  },
  "meta": {
    "timestamp": "2026-08-15T14:32:10Z"
  }
}
```

| HTTP | `error.code` | Cuándo ocurre |
|---|---|---|
| 401 | `UNAUTHORIZED` | No se mandó ni `Authorization: Bearer` ni `plate`. |
| 422 | `VALIDATION_ERROR` | Se mandó `plate` vacío. |
| 422 | `PLATE_INVALID_FORMAT` | `plate` no matchea el formato esperado. |
| 422 | `NO_VEHICLE` | El token es válido pero no tiene ningún vehículo asociado. |
| 403 | `PLATE_TOKEN_MISMATCH` | Se mandaron token y `plate` juntos, y no corresponden al mismo vehículo. |
| 404 | `PLATE_NOT_FOUND` | No existe ningún vehículo con esa placa en Odoo. |
| 404 | `NOT_FOUND` | El vehículo existe pero no tiene una credencial Traccar activa (no se registró desde Flota, o fue revocada). |
| 500 | `INTERNAL_ERROR` | Error inesperado del servidor (ver logs de Odoo). |

Nota: por diseño, si el token no pertenece al mismo cliente dueño del vehículo, el endpoint responde `404 NOT_FOUND` (no `403`) para no revelar si el vehículo existe o no.

---

## 6. Cómo usar la respuesta para conectarse al websocket de Traccar

Esto lo hace la app, **no** este backend de Odoo:

1. Autenticar contra Traccar con las credenciales recibidas:
   ```
   POST {traccar_url}/api/session
   Content-Type: application/x-www-form-urlencoded

   email=<email>&password=<password>
   ```
   Traccar devuelve una cookie de sesión (`JSESSIONID`).

2. Abrir el websocket enviando esa cookie:
   ```
   {traccar_ws_url}
   ```
   (headers de la conexión WS deben incluir la cookie `JSESSIONID` obtenida en el paso 1).

3. Como el usuario Traccar de este vehículo solo tiene permiso sobre **su propio** `device_id`, el socket va a emitir únicamente posiciones de ese dispositivo — no hace falta filtrar nada del lado de la app.

### Ejemplo curl (paso 1, para probar manualmente)

```bash
curl -i -X POST "http://52.15.86.160:8082/api/session" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "email=juan@gmail.com&password=xY9k2-Qp7z1RmN0v"
```
La respuesta trae el header `Set-Cookie: JSESSIONID=...` a usar en el handshake del websocket.

---

## 7. Ejemplos de integración

### curl — flujo por token

```bash
# 1) Login por placa
curl -s -X POST "https://tu-dominio-odoo/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"plate": "ABC-123"}'

# 2) Credenciales Traccar con el token obtenido
curl -s "https://tu-dominio-odoo/v1/app/traccar-credentials" \
  -H "Authorization: Bearer a1b2c3d4..."
```

### curl — flujo directo por placa

```bash
curl -s "https://tu-dominio-odoo/v1/app/traccar-credentials?plate=ABC-123"
```

### JavaScript / fetch

```javascript
async function getTraccarCredentials(plate) {
  const res = await fetch(
    `https://tu-dominio-odoo/v1/app/traccar-credentials?plate=${encodeURIComponent(plate)}`
  );
  const body = await res.json();
  if (!body.success) {
    throw new Error(`${body.error.code}: ${body.error.message}`);
  }
  return body.data; // { traccar_url, traccar_ws_url, email, password, device_id, unique_id, plate }
}
```

---

## 8. Notas de seguridad / uso

- **HTTPS obligatorio**: el response entrega un password en texto plano — nunca debe viajar sobre HTTP en producción.
- **No cachear la respuesta** más de lo necesario en el cliente/app.
- **El flujo por placa sin token (2.b) es intencional**, no un descuido: replica el mismo nivel de acceso que ya tiene `POST /v1/auth/login` en `adt_comercial` para el resto de los datos del cliente (préstamos, documentos, etc.). A diferencia de esos datos, esto entrega acceso a **ubicación GPS en vivo** — si más adelante se quiere subir el nivel de seguridad (ej. exigir también el DNI del titular, rate-limit, etc.), es un cambio a evaluar en este mismo endpoint.
- El usuario Traccar devuelto **no** es administrador y solo tiene permiso sobre el dispositivo de ese vehículo — aunque alguien obtenga estas credenciales, no puede ver otros vehículos de la flota.
- El campo `password` se regenera con la acción "Regenerar password" desde Odoo (ficha de la credencial, en `Flota → Traccar → Credenciales Traccar`) — si se sospecha que una credencial fue comprometida, regenerarla invalida la anterior de inmediato en Traccar.

---

## 9. Dependencias / configuración necesaria en Odoo

- Módulo `adt_traccar_device` instalado.
- El vehículo debe estar registrado en Traccar desde Flota (botón "Traccar" en la ficha del vehículo, o la acción masiva "Sincronizar con Traccar" desde la lista) antes de que este endpoint devuelva algo distinto de `404 NOT_FOUND`.
- Configuración de Traccar admin cargada en `Ajustes → Traccar` (`adt_traccar.url`, `.email`, `.password`) — la usa Odoo internamente para crear devices/users, no es lo que se expone acá.
