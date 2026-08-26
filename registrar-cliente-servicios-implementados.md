# Mobile API — Contrato IMPLEMENTADO: Registro, Login y Beneficios

Este documento reemplaza a `registrar-cliente-servicio-propuesto.md` como referencia para el
front: describe el contrato **tal como quedó implementado** en `adt_comercial` (no la
propuesta original — hay diferencias, marcadas más abajo con ⚠️).

Todos los endpoints viven en el mismo host que `NetworkConstants.BASE_URL` (mismo backend que
`MOBILE_API_PAPELETAS.md` y el resto de `/v1/...`), excepto donde se indique lo contrario.

Servicios:

| Método | Ruta | Auth | Body |
|---|---|---|---|
| POST | `/v1/customers/register` | No | JSON |
| GET  | `/v1/customers/register/{solicitudId}` | No | — |
| POST | `/v1/auth/login-email` | No | JSON |
| POST | `/v1/auth/login` | No | JSON (⚠️ ahora pide `password`) |
| GET  | `/v1/beneficios` | Opcional (no se valida) | — |

---

## ⚠️ Léase primero — 3 cosas que cambiaron o son fáciles de pasar por alto

### 1. El registro ya deja al usuario logueado (auto-login)

`POST /v1/customers/register` **ya no solo crea la solicitud**: en la misma respuesta viene
`token` + `expiresAt` + `tipoUsuario: "INVITADO"`, exactamente como si el front hubiera llamado
a `POST /v1/auth/login-email` justo después. **No hace falta un segundo request de login luego
de registrarse.** Tampoco hace falta esperar ninguna aprobación del equipo — la aprobación
(`estado`) es solo seguimiento interno en Odoo, nunca bloquea el login.

### 2. `POST /v1/auth/login` (placa) es el ÚNICO endpoint que va envuelto en JSON-RPC

Es una diferencia de implementación (preexistente, no la introdujimos ahora) que vale la pena
remarcar porque rompe el parseo si el front asume el mismo shape que el resto:

- **Todos los demás endpoints de este documento** (`register`, `login-email`,
  `GET .../register/{id}`, `beneficios`) son controladores HTTP "planos": el body de la
  respuesta **es directamente** el envelope `{success, statusCode, data/error, meta}` de abajo,
  y el **status code HTTP real coincide** con `statusCode` (401 → HTTP 401, 404 → HTTP 404, etc.).
- **`POST /v1/auth/login`** (por placa) es `type="json"` (JSON-RPC): la respuesta HTTP siempre
  llega con **status HTTP 200**, y el envelope de arriba viene adentro de un campo `result`:

  ```json
  {
    "jsonrpc": "2.0",
    "id": null,
    "result": {
      "success": false,
      "statusCode": 401,
      "error": { "code": "INVALID_CREDENTIALS", "message": "Placa o contraseña incorrecta." },
      "meta": { "timestamp": "...", "requestId": "..." }
    }
  }
  ```

  → Para saber si `POST /v1/auth/login` fue exitoso, **el front tiene que mirar
  `result.success` / `result.statusCode` del body, no el status HTTP de la respuesta**, que
  siempre va a ser 200. El **request** sí se manda plano, sin ningún wrapper
  (`{ "plate": "ABC-123", "password": "..." }` directo, no hace falta armar el sobre
  `jsonrpc/params`).

### 3. `GET /v1/beneficios` no valida el header `Authorization` todavía

Se puede mandar `Authorization: Bearer <token>` o no mandar nada — el backend hoy no lo lee en
absoluto (ni para autorizar ni para personalizar la respuesta). Queda como posible mejora
futura (ver sección 4).

---

## Envelope común (todos los endpoints excepto `/v1/auth/login`, ver arriba)

**Éxito:**

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": { "...": "..." },
  "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "5b2e1c1a-....-...." }
}
```

**Error:**

```json
{
  "success": false,
  "statusCode": 401,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Correo o contraseña incorrectos.",
    "details": [ { "field": "email", "issue": "...", "rejectedValue": "..." } ]
  },
  "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "..." }
}
```

`error.details` solo aparece en los errores `400 VALIDATION_ERROR` (uno o más objetos
`{field, issue, rejectedValue}`); el resto de los errores no lo trae.

## Headers

Ninguno de estos 5 servicios requiere `Authorization`. Se siguen mandando los headers de
dispositivo estándar del resto del backend (los inyecta `createHttpClient`, no hace falta
armarlos a mano) — hoy solo se usan para quedar registrados en el token de sesión
(`mobile.token`), ninguno es obligatorio para que el request funcione:

```http
X-Device-Model: <fabricante modelo>
X-Device-OS: Android <version> | iOS <version>
X-Device-ID: <uuid persistente del dispositivo>
X-App-Version: <version de la app>
X-Platform: android | ios
```

Para los `POST`:

```http
Content-Type: application/json
```

---

## 1) `POST /v1/customers/register`

### Request

```json
{
  "nombres": "Juan Carlos",
  "apellidoPaterno": "Pérez",
  "apellidoMaterno": "Gómez",
  "fechaNacimiento": "1998-04-12",
  "email": "juan.perez@ejemplo.com",
  "password": "MiClave123",
  "provincia": "Lima",
  "distrito": "San Juan de Lurigancho",
  "selfie": "<base64_jpeg>"
}
```

| Campo | Tipo | Requerido | Notas |
|---|---|:---:|---|
| `nombres` | string | sí | |
| `apellidoPaterno` | string | sí | |
| `apellidoMaterno` | string | sí | |
| `fechaNacimiento` | string | sí | `YYYY-MM-DD`. Se revalida edad 18–100 años en backend. |
| `email` | string | sí | único (409 si ya existe). También es el login. |
| `password` | string | sí | mínimo 8 caracteres. Se hashea, nunca se guarda ni se devuelve en texto plano. |
| `provincia` | string | sí | texto libre (nombre, no código INEI). |
| `distrito` | string | sí | texto libre. |
| `selfie` | string | sí | base64 JPEG, con o sin prefijo `data:image/jpeg;base64,` (se limpia solo). Límite 5&nbsp;MB decodificado. |

### Response `201 Created`

```json
{
  "success": true,
  "statusCode": 201,
  "message": "Solicitud de registro recibida correctamente.",
  "data": {
    "solicitudId": 482,
    "partnerId": 913,
    "estado": "PENDIENTE",
    "email": "juan.perez@ejemplo.com",
    "nombres": "Juan Carlos",
    "apellidoPaterno": "Pérez",
    "apellidoMaterno": "Gómez",
    "creadoEn": "2026-08-25T15:04:00Z",
    "tipoUsuario": "INVITADO",
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expiresAt": "2026-11-23T15:04:00Z"
  },
  "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "..." }
}
```

⚠️ `token`/`expiresAt`/`tipoUsuario` **son nuevos respecto a la propuesta original** — antes el
registro no logueaba. Guardar el `token` tal cual se guardaría el de
`POST /v1/auth/login-email` (mismo `SessionManager`, mismo `isGuestUser()` en `true`).

⚠️ `partnerId` **ya no viaja `null`** — el `res.partner` se crea automáticamente en el mismo
registro (ya no hace falta ninguna aprobación del equipo para que exista). Lo único que ese
`partner_id` todavía no tiene es documento de identidad ni vehículo/placa asignados — eso
sigue siendo un paso manual aparte, y es justo lo que mantiene a la persona como `INVITADO`
en los logins hasta que se le asignen.

### Errores

| HTTP | `error.code` | Motivo |
|---|---|---|
| 400 | `BAD_REQUEST` | el body no es un JSON válido/objeto |
| 400 | `VALIDATION_ERROR` | falta o está mal algún campo — `error.details[]` trae uno por campo (`nombres`, `apellidoPaterno`, `apellidoMaterno`, `fechaNacimiento`, `email`, `password`, `provincia`, `distrito`) |
| 413 | `SELFIE_MUY_GRANDE` | la selfie decodificada supera 5&nbsp;MB — **corta el request ahí mismo**, no se combina con otros errores de `VALIDATION_ERROR` |
| 422 | `SELFIE_INVALIDA` | el base64 no decodifica a una imagen — mismo comportamiento: corta el request, no se combina con otros campos |
| 409 | `EMAIL_DUPLICADO` | ya existe una solicitud o credencial con ese correo |
| 500 | `INTERNAL_ERROR` | |

**Nota de orden:** si la selfie es inválida/muy pesada, el backend responde con ese error
apenas lo detecta, **incluso si además faltan otros campos** — el front no va a recibir ambos
problemas juntos en un solo `VALIDATION_ERROR`. Si `nombres`/`email`/etc. faltan, sí se
acumulan todos en un único `400 VALIDATION_ERROR` con varios `details[]`.

---

## 2) `GET /v1/customers/register/{solicitudId}`

Sin body. `solicitudId` es el que devolvió el registro (arriba).

### Response `200 OK`

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "solicitudId": 482,
    "partnerId": 913,
    "estado": "EN_REVISION",
    "email": "juan.perez@ejemplo.com",
    "creadoEn": "2026-08-25T15:04:00Z",
    "actualizadoEn": "2026-08-25T09:12:00Z",
    "placaAsignada": null,
    "motivoRechazo": null
  },
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

`estado` ∈ `PENDIENTE | EN_REVISION | APROBADO | RECHAZADO` — **ninguno de estos 4 valores
afecta si la persona puede loguearse** (ver punto 1 de arriba); es puramente informativo para
mostrar en la app ("tu solicitud está en revisión", etc.). `APROBADO` ya no lo pone ningún
botón/flujo automático — quedó como marca manual opcional del equipo, no hay que esperarlo
para nada. `partnerId` viene con valor desde el registro (ver punto 1); `placaAsignada` sigue
`null` hasta que alguien le asigne un vehículo desde Flota.

### Errores

| HTTP | `error.code` |
|---|---|
| 404 | `SOLICITUD_NOT_FOUND` |
| 500 | `INTERNAL_ERROR` |

---

## 3) `POST /v1/auth/login-email`

### Request

```json
{ "email": "juan.perez@ejemplo.com", "password": "MiClave123" }
```

### Response `200 OK` — caso `PLACA` (cliente real de Odoo, con vehículo)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "tipoUsuario": "PLACA",
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expiresAt": "2026-11-23T15:04:00Z",
    "vehicleId": 10,
    "licensePlate": "ABC123",
    "partnerId": 55,
    "partnerName": "Juan Carlos Pérez Gómez"
  },
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

Para este caso, la contraseña **no es la que la persona haya elegido en ningún lado**: es su
número de documento de identidad (DNI/CE) tal cual está cargado en Odoo (`res.partner.vat`).
Ver sección "Modelo de autenticación" más abajo.

### Response `200 OK` — caso `INVITADO` (registrado por el servicio 1, con o sin aprobar)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "tipoUsuario": "INVITADO",
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expiresAt": "2026-11-23T15:04:00Z",
    "solicitudId": 482,
    "estadoSolicitud": "EN_REVISION",
    "partnerName": "Juan Carlos Pérez Gómez"
  },
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

Sin `vehicleId`/`licensePlate`/`partnerId` (no existen todavía). `partnerName` acá se arma
concatenando `nombres + apellidoPaterno + apellidoMaterno` de la solicitud (no viene de un
`res.partner`, porque puede no haber ninguno todavía).

### Errores

| HTTP | `error.code` | Motivo |
|---|---|---|
| 400 | `BAD_REQUEST` | body no es JSON válido |
| 401 | `INVALID_CREDENTIALS` | correo no existe (en ninguna de las 2 fuentes), formato de correo inválido, falta `password`, o la contraseña no matchea — **siempre el mismo código y mensaje**, a propósito, para no revelar si un correo existe |
| 500 | `INTERNAL_ERROR` | |

No hay `429 RATE_LIMIT_EXCEEDED` implementado todavía (no hay throttling de intentos en este
endpoint — si lo necesitan para el lanzamiento, avisar, no está armado).

---

## 4) `POST /v1/auth/login` (placa) — ⚠️ cambio de contrato

⚠️ Ver la sección 2 de "léase primero": este endpoint es JSON-RPC (`result.*`, siempre HTTP
200). Todo lo de abajo describe el contenido de `result`.

### Request

```json
{ "plate": "ABC-123", "password": "MiClave123" }
```

`password` **ahora es obligatorio** (antes no se pedía). Es el mismo valor que en el caso
`PLACA` de `login-email`: el número de documento de identidad de la persona en Odoo.

### Response — éxito

```json
{
  "success": true,
  "statusCode": 200,
  "message": "Token generado correctamente.",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "vehicleId": 10,
    "licensePlate": "ABC123",
    "partnerId": 55,
    "partnerName": "Juan Carlos Pérez Gómez",
    "expiresAt": "2026-11-23T15:04:00Z"
  },
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

(Sin `tipoUsuario` acá — a diferencia de `login-email`, este endpoint siempre es placa, no hace
falta distinguir.)

### Errores (dentro de `result`, no cambian el status HTTP)

| `statusCode` | `error.code` | Motivo |
|---|---|---|
| 422 | `VALIDATION_ERROR` | falta `plate` o `password`, o la placa no tiene formato válido |
| 401 | `INVALID_CREDENTIALS` | placa no encontrada **o** contraseña incorrecta — mismo código para ambos casos (no revela si la placa existe) |
| 500 | `INTERNAL_ERROR` | |

### Modelo de autenticación (por qué la contraseña es el documento)

Para no depender de una migración de "passwords de portal" que nunca existieron para los
clientes actuales, la contraseña de un usuario `PLACA` **siempre es su número de documento de
identidad vigente en Odoo**, y se resincroniza sola en cada login si el documento cambia. No
hay ningún flujo de "elegir contraseña" para este tipo de usuario — si el cliente no tiene
documento cargado en Odoo, no puede loguearse (ni por placa ni por correo) hasta que se lo
carguen ahí.

---

## 5) `GET /v1/beneficios`

Sin body. Query param opcional `?categoria=vial` (filtra server-side; si se omite, trae todo).

### Response `200 OK`

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": [
    {
      "id": "auxilio-grua",
      "categoria": "vial",
      "proveedor": { "nombre": "Los Andes Cooperativa", "logoUrl": null },
      "titulo": "Auxilio mecánico y grúa",
      "imagenCard": "https://tu-dominio/web/content/123/imagen.jpg?access_token=...",
      "descripcionCorta": "Traslado en grúa (1 vez al mes) y auxilio mecánico en ruta.",
      "multimedia": [
        { "tipo": "IMAGEN", "url": "https://..." },
        { "tipo": "VIDEO", "url": "https://..." }
      ],
      "staff": [
        { "nombre": "Julio Cárdenas", "especialidad": "Técnico mecánico",
          "whatsapp": "51999333444", "avatarUrl": null }
      ],
      "cubre": [
        { "icono": "🚗", "texto": "Traslado en grúa hasta 1 vez al mes" }
      ],
      "recomendaciones": [
        { "icono": "📞", "titulo": "Llama antes de moverte",
          "texto": "Coordina con el técnico antes de mover el vehículo tú mismo" }
      ]
    }
  ],
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

Cada campo corresponde 1:1 con `domain/model/Beneficio.kt` (`Beneficio`, `Proveedor`,
`MediaBeneficio`, `StaffBeneficio`, `CoberturaBeneficio`, `RecomendacionBeneficio`) — no
debería hacer falta ningún mapeo del lado del cliente. `data` viene `[]` si no hay beneficios
cargados en Odoo todavía (no es un error). `staff`/`multimedia`/`cubre`/`recomendaciones`
pueden venir vacíos (`[]`) individualmente.

### Errores

| HTTP | `error.code` |
|---|---|
| 500 | `INTERNAL_ERROR` |

---

## Resumen para el front

1. Después de `POST /v1/customers/register`, guardar el `token` de la respuesta directamente —
   no hace falta llamar a `login-email` después. `isGuestUser()` = `true`.
2. `POST /v1/auth/login` es el único que va con status HTTP 200 siempre; mirar
   `result.data.success` / `result.data.statusCode` del body para saber si falló.
3. Ambos logins (`login` y `login-email`) devuelven `401 INVALID_CREDENTIALS` genérico ante
   cualquier combinación de correo/placa/contraseña inválida — no hay forma de distinguir
   "no existe" de "contraseña mal" desde la respuesta, es a propósito.
4. `estado`/`estadoSolicitud` es solo informativo — nunca bloquea poder loguearse.
