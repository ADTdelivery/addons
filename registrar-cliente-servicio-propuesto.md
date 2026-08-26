# Mobile API - Servicios propuestos: Registro de cliente, login y beneficios

Este documento propone el contrato de los servicios backend para tres piezas de la app que hoy no tienen
ningún endpoint real (todo mockeado/simulado en el cliente móvil):

1. **Registrar cliente** — flujo accesible desde el login vía "¿No estás registrado? Únete a la flota"
   (`feature/registration/`).
2. **Login con correo y contraseña** — para que un usuario "invitado" (registrado por (1), sin placa/vehículo
   todavía) pueda volver a entrar a la app, y para distinguirlo de un usuario real de Odoo con vehículo.
3. **Beneficios** — el módulo "Beneficios" de la app (`feature/vehiclehome/presentation/BenefitsHubScreen`),
   100% mockeado hoy en `BeneficiosRepositoryImpl`.

Sigue el mismo formato/envelope que `MOBILE_API_PAPELETAS.md` y el resto de servicios de este backend
(`v1/...`, mismo host que `NetworkConstants.BASE_URL`, no el host aparte de reportes de incidentes).

Servicios propuestos:

- `POST /v1/customers/register` — crear la solicitud de registro de un invitado
- `GET /v1/customers/register/{solicitudId}` — consultar el estado de una solicitud
- `POST /v1/auth/login-email` — login por correo/contraseña, distingue invitado vs. usuario con placa
- `GET /v1/beneficios` — listado de beneficios del módulo "Beneficios"

**Cambio a un endpoint EXISTENTE** (no es un servicio nuevo, es una modificación — ver sección "Modelo de
autenticación" abajo):

- `POST /v1/auth/login` (login por placa, ya implementado) — pasa a requerir `password` en el request,
  igual que el login por correo. Hoy no la pide.

---

## ⚠️ Modelo de autenticación (actualizado 2026-08-25)

La versión anterior de este documento dejaba abierta una decisión: ¿el registro deja una cuenta activa de
inmediato, o solo una solicitud pendiente de revisión? El usuario pidió ahora explícitamente un login por
correo/contraseña que **valide entre usuarios de Odoo (con placa) y usuarios invitados** — eso implica la
respuesta: **sí hace falta login propio (antes "opción 2"), pero combinado con "opción 1"**, no una cosa u
otra:

- El registro (`POST /v1/customers/register`) sigue creando una **solicitud pendiente de revisión** — eso
  no cambia, sigue calzando con el copy "nuestro equipo revisará tus datos" que ya tiene la app.
- Pero ese mismo registro **también deja credenciales utilizables de inmediato** para loguearse — el
  invitado puede volver a entrar a la app con su correo/contraseña mientras su solicitud sigue pendiente.
  "Tener cuenta" y "estar aprobado en la flota" son dos cosas distintas: la primera existe desde el
  registro, la segunda solo cuando el equipo aprueba.

### ⚠️ Actualización 2026-08-25: la contraseña se pide en AMBOS casos, no solo en correo

Pedido explícito: **tanto el login por placa como el login por correo van a requerir contraseña.** No es
solo el nuevo `POST /v1/auth/login-email` — el `POST /v1/auth/login` **existente** (por placa) también pasa
a pedirla. Los dos flujos terminan validando contra la misma credencial (la que se crea en el registro, o la
que se le asigne/migre a un partner de Odoo ya existente):

- **`POST /v1/auth/login` (placa) — cambio de contrato propuesto:**

  ```json
  // Antes (hoy, implementado):
  { "plate": "ABC123" }

  // Propuesto:
  { "plate": "ABC123", "password": "MiClave123" }
  ```

  El resto del contrato (`JsonRpcResponse<LoginApiResult>`, `LoginDataDto` con `token`/`vehicleId`/
  `licensePlate`/`partnerId`/`partnerName`/`expiresAt`) no cambia — solo se agrega `password` al request y
  la validación correspondiente en el backend. Si la placa existe pero la contraseña no coincide (o no está
  configurada todavía, ver punto de migración más abajo), responder con el mismo código que usaría un
  intento fallido de `login-email` (`401 INVALID_CREDENTIALS`) en vez de `PLATE_NOT_FOUND` — no revelar si
  la placa existe o no a partir del tipo de error.

- **`POST /v1/auth/login-email` (correo) — sin cambios respecto a la versión anterior de este documento**,
  ver contrato completo en la sección 3 más abajo. Intenta validar el correo/contraseña contra **dos
  fuentes posibles**, en este orden sugerido:
  1. Un usuario de Odoo real (partner/conductor con vehículo asignado) — si existe y la contraseña
     coincide, responde como usuario **`PLACA`** (mismo shape que devuelve `POST /v1/auth/login`).
  2. Si no matchea contra Odoo, la tabla de solicitudes de registro (invitados) — si existe y la contraseña
     coincide, responde como usuario **`INVITADO`** (sin placa/vehículo, con el estado de su solicitud).

**Del lado del cliente**: el toggle "Placa / Correo" ya existe en `LoginScreen.kt` (los dos campos de
contraseña son visuales por ahora, `passwordInput`/`emailInput` locales, sin conectar a ningún ViewModel
todavía) — conectar ambos modos a estos dos endpoints (el existente modificado + el nuevo) es trabajo de
cliente pendiente, explícitamente fuera del alcance de este documento por ahora.

### ⚠️ Punto a confirmar con el equipo de backend/Odoo antes de implementar — ahora bloqueante para los DOS logins

El login actual por placa (`POST /v1/auth/login`) **nunca pidió contraseña** — no hay evidencia de que los
partners/conductores existentes en Odoo tengan hoy una contraseña de portal configurada. Como ahora la
contraseña se exige también en el login por placa (no solo en el nuevo login-email), este punto deja de ser
opcional/diferible y hay que resolverlo **antes** de lanzar el cambio en `POST /v1/auth/login`, no después:

- ¿Los partners de Odoo ya tienen usuario de portal (`res.users`) con contraseña? Si no, hace falta un plan
  de migración (ej. "primera vez que entras con tu placa, te pedimos crear una contraseña", o un correo/SMS
  masivo pidiendo que la configuren antes de la fecha de corte) — no algo que este documento pueda resolver
  solo, es una decisión de producto + una migración de datos.
- Mientras esa migración no esté lista, **no desplegar el cambio de contrato en `POST /v1/auth/login`** —
  haría que ningún usuario con placa pueda loguearse. `POST /v1/auth/login-email` sí puede lanzarse antes,
  funcionando **solo para invitados** (que sí tienen contraseña desde el registro) — es un subconjunto
  seguro de implementar ya, sin depender de la migración de los usuarios con placa.

---

## Autenticación (headers comunes)

Ninguno de los servicios de registro/login requiere `Authorization: Bearer <token>` — se llaman **antes**
de que exista sesión. `GET /v1/beneficios` sí puede llamarse con o sin sesión (ver sección 4). Todos llevan,
como cualquier request de este backend, los headers de dispositivo que ya inyecta `createHttpClient`
automáticamente (no hace falta armarlos a mano en el cliente):

```http
X-Device-Model: <fabricante modelo>
X-Device-OS: Android <version> | iOS <version>
X-Device-ID: <uuid persistente del dispositivo>
X-App-Version: <version de la app>
X-Platform: android | ios
X-Device-Brand: <marca>
X-Screen-Resolution: <ancho>x<alto>
X-Network-Type: <wifi|cellular|...>
```

Para `POST` usar también:

```http
Content-Type: application/json
```

---

## 1) Registrar cliente (invitado)

**Endpoint**

```http
POST /v1/customers/register
```

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

### Campos

| Campo             | Tipo   | Requerido | Notas |
|--------------------|--------|:---------:|-------|
| `nombres`          | string | sí        | tal cual lo tipea el usuario, sin trim adicional necesario (el cliente ya hace `.trim()`) |
| `apellidoPaterno`  | string | sí        | |
| `apellidoMaterno`  | string | sí        | |
| `fechaNacimiento`  | string | sí        | formato `YYYY-MM-DD`. El cliente ya valida edad 18–100 años antes de enviar, pero **revalidar en backend** (nunca confiar solo en la validación del cliente) |
| `email`            | string | sí        | debe ser único — ver `409 EMAIL_DUPLICADO` más abajo. Es también la credencial de login (`POST /v1/auth/login-email`, sección 3) |
| `password`         | string | sí        | el cliente ya exige mínimo 8 caracteres; el backend debe **hashear** (bcrypt/argon2), nunca persistir en texto plano ni devolverla en ninguna respuesta. Es la misma contraseña que se usa después en el login-email |
| `provincia`        | string | sí        | nombre tal cual aparece en el dataset de ubigeo del cliente (`ubigeo_peru.json`, 196 provincias) — no se manda código INEI, solo el nombre |
| `distrito`         | string | sí        | idem, nombre del distrito dentro de la provincia elegida |
| `selfie`           | string | sí        | imagen JPEG codificada en base64 (sin prefijo `data:image/jpeg;base64,`), mismo patrón que `RegisterPapeletaRequest.fotos`/`UploadVoucherRequest.voucher_image`. Es una **selfie** — la app restringe la captura a cámara frontal/frontal-preferida, no permite subir desde galería, así que no debería llegar una foto de documento |

**Nota sobre `provincia`/`distrito` como texto libre:** el cliente los manda como nombre (no código
ubigeo) porque el dataset que usa es puramente local (JSON embebido en la app, sin codificar contra un
catálogo del backend). Si el backend necesita el código INEI para reportes u otros sistemas, conviene
resolverlo del lado del servidor (hay datasets públicos de ubigeo Perú) en vez de pedirle a la app que
mande un código que hoy no tiene.

### Mapeo sugerido hacia Odoo

Dos formas razonables de modelarlo — la decisión final es del equipo de backend, esto es una propuesta:

**Opción A (recomendada) — modelo custom separado, no toca `res.partner` todavía.**
Crear un modelo nuevo, p. ej. `adt.solicitud.cliente` (`nombres`, `apellido_paterno`, `apellido_materno`,
`fecha_nacimiento`, `email`, `password_hash`, `provincia`, `distrito`, `selfie` como `Binary`/adjunto,
`estado` selection `pendiente/en_revision/aprobado/rechazado`, `partner_id` — `Many2one` a `res.partner`,
vacío hasta que se apruebe). Ventaja: un invitado que nunca es aprobado no ensucia la tabla de partners
reales de Odoo; el registro es barato de crear y descartar. Cuando el equipo aprueba la solicitud, ahí
recién se crea (o vincula) el `res.partner` real + su vehículo, y se completa `partner_id`.

**Opción B — crear el `res.partner` de una vez, marcado como invitado.**
Crear el `res.partner` inmediatamente con dos campos nuevos: `x_es_invitado` (boolean, `True`) y
`x_estado_solicitud` (selection, igual que el `estado` de la opción A). Ventaja: un solo modelo, no hay que
mapear entre dos tablas al aprobar. Desventaja: la tabla de partners se llena de registros que quizás nunca
se aprueben.

Este documento asume la **opción A** en los ejemplos de response de abajo (`solicitudId` referencia al
modelo custom, `partnerId` queda `null` hasta la aprobación) — pero cualquiera de las dos funciona con el
mismo contrato JSON hacia la app, solo cambia qué pasa puertas adentro en Odoo.

### Response 201 (Created)

```json
{
  "success": true,
  "statusCode": 201,
  "message": "Solicitud de registro recibida correctamente.",
  "data": {
    "solicitudId": 482,
    "partnerId": null,
    "estado": "PENDIENTE",
    "email": "juan.perez@ejemplo.com",
    "nombres": "Juan Carlos",
    "apellidoPaterno": "Pérez",
    "apellidoMaterno": "Gómez",
    "creadoEn": "2026-08-25T15:04:00Z"
  },
  "meta": {
    "timestamp": "2026-08-25T15:04:00Z",
    "requestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

`data` deliberadamente **no** incluye `password` ni ningún token de sesión — el registro por sí solo no
loguea a la persona; para eso está el login-email (sección 3), llamado aparte con las mismas credenciales
recién creadas. `solicitudId` es lo que el cliente guardaría para poder consultar el estado después
(servicio 2). `partnerId` viaja `null` hasta que la solicitud se apruebe (opción A de arriba) — si el
backend usa la opción B, `partnerId` podría venir seteado desde el inicio; ajustar este campo según cuál se
implemente.

### Errores comunes

- `400 VALIDATION_ERROR` — algún campo obligatorio falta o no cumple formato. Usar `error.details` (array de
  `{field, issue, rejectedValue}`, mismo shape que `ErrorDetail` ya usa el cliente) para que la app pueda
  mostrar el error debajo del campo correspondiente en vez de un mensaje genérico:

  ```json
  {
    "success": false,
    "statusCode": 400,
    "message": "Hay errores de validación.",
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Uno o más campos no son válidos.",
      "details": [
        { "field": "email", "issue": "formato inválido", "rejectedValue": "no-es-un-correo" },
        { "field": "fechaNacimiento", "issue": "el cliente debe ser mayor de 18 años" }
      ]
    },
    "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "..." }
  }
  ```

- `409 EMAIL_DUPLICADO` — ya existe una solicitud/cuenta con ese correo (o un partner de Odoo con ese
  correo, si se decide validar cruzado — ver nota de unicidad en la sección de login).
- `413 SELFIE_MUY_GRANDE` — la imagen decodificada supera el límite que defina el backend (sugerido: 5 MB;
  la app no comprime la selfie hoy, así que conviene validar/comprimir server-side o pedirle al cliente que
  redimensione antes de enviar si esto resulta un problema en la práctica).
  Este código no viene de `MOBILE_API_PAPELETAS.md` — es una recomendación nueva de este documento.
- `422 SELFIE_INVALIDA` — el base64 no decodifica a una imagen válida.
- `429 RATE_LIMIT_EXCEEDED` — mismo código que ya usa el cliente para el login por placa
  (`ApiErrorCodes.RATE_LIMIT_EXCEEDED`), reusar en vez de inventar uno nuevo.
- `500 INTERNAL_ERROR`

---

## 2) Consultar estado de una solicitud

Pensado para que la app pueda mostrarle a la persona si su solicitud ya fue revisada — sin esto, "nuestro
equipo se pondrá en contacto contigo" es una promesa que la persona no puede verificar por su cuenta. No
está conectado a ninguna pantalla del cliente todavía.

**Endpoint**

```http
GET /v1/customers/register/{solicitudId}
```

### Ejemplo Request

```http
GET /v1/customers/register/482
```

### Response 200 (OK)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "solicitudId": 482,
    "partnerId": null,
    "estado": "EN_REVISION",
    "email": "juan.perez@ejemplo.com",
    "creadoEn": "2026-08-25T15:04:00Z",
    "actualizadoEn": "2026-08-25T09:12:00Z",
    "placaAsignada": null,
    "motivoRechazo": null
  },
  "meta": {
    "timestamp": "2026-08-25T09:20:00Z",
    "requestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

`estado` propuesto (4 valores):

| Estado         | Significado |
|----------------|-------------|
| `PENDIENTE`    | recién creada, nadie la revisó todavía |
| `EN_REVISION`  | el equipo la está evaluando |
| `APROBADO`     | aprobada — `placaAsignada`/`partnerId` deberían venir seteados. La persona sigue logueándose igual (login-email con el mismo correo/contraseña), pero ahora el login-email la reconoce como `PLACA` en vez de `INVITADO` (ver sección 3) |
| `RECHAZADO`    | rechazada — `motivoRechazo` explica por qué |

### Errores comunes

- `404 SOLICITUD_NOT_FOUND`
- `500 INTERNAL_ERROR`

---

## 3) Login con correo y contraseña

Nuevo — pedido explícito para distinguir, en un solo login, entre un usuario real de Odoo (con placa) y un
invitado (registrado por el servicio 1). No reemplaza a `POST /v1/auth/login` (placa) — convive con él. El
cliente ya tiene un campo de contraseña en la pantalla de login por placa, pero hoy es **puramente visual,
sin lógica** (`LoginScreen.kt`, `passwordInput` local, no se envía a ningún lado) — conectar ese campo (o
agregar un flujo de "entrar con correo" separado) a este endpoint es trabajo de cliente pendiente, fuera del
alcance de este documento.

**Endpoint**

```http
POST /v1/auth/login-email
```

### Request

```json
{
  "email": "juan.perez@ejemplo.com",
  "password": "MiClave123"
}
```

### Response 200 (OK) — caso `PLACA` (usuario real de Odoo, con vehículo)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "tipoUsuario": "PLACA",
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expiresAt": "2026-09-25T15:04:00Z",
    "vehicleId": 10,
    "licensePlate": "ABC123",
    "partnerId": 55,
    "partnerName": "Juan Carlos Pérez Gómez"
  },
  "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "..." }
}
```

Mismo shape que `LoginDataDto` (lo que ya devuelve `POST /v1/auth/login` hoy) más `tipoUsuario`, para que el
cliente reutilice exactamente la misma lógica de guardado de sesión que ya tiene en `LoginViewModel`.

### Response 200 (OK) — caso `INVITADO` (sin vehículo todavía)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "tipoUsuario": "INVITADO",
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expiresAt": "2026-09-25T15:04:00Z",
    "solicitudId": 482,
    "estadoSolicitud": "EN_REVISION",
    "partnerName": "Juan Carlos Pérez Gómez"
  },
  "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "..." }
}
```

Sin `vehicleId`/`licensePlate`/`partnerId` — el cliente ya tiene una property `SessionManager.isGuestUser()`
para justo este caso (hoy la setea localmente al simular el registro; con este endpoint real pasaría a
setearse en base a `tipoUsuario == "INVITADO"`). `estadoSolicitud` deja que la app muestre el estado de la
solicitud sin una llamada aparte al servicio 2.

**Nota de seguridad:** si `estado` de la solicitud es `RECHAZADO`, decidir explícitamente si igual se
permite el login (mostrando el rechazo dentro de la app) o si se bloquea con un error propio
(`403 SOLICITUD_RECHAZADA`) — no asumido en este documento, es una decisión de producto.

### Errores comunes

- `401 INVALID_CREDENTIALS` — correo no existe (ni en Odoo ni en solicitudes) **o** contraseña incorrecta.
  **Usar el mismo código para ambos casos** (no un `EMAIL_NOT_FOUND` separado) — es una práctica de
  seguridad estándar para no dejarle saber a un atacante si un correo está registrado o no.
- `429 RATE_LIMIT_EXCEEDED` — mismo código que el resto de la app; recomendado limitar intentos por
  correo/IP dado que ahora hay contraseña de por medio (algo que el login por placa no necesitaba tanto).
- `500 INTERNAL_ERROR`

---

## 4) Beneficios

Módulo "Beneficios" de la app (`BenefitsHubScreen`/`BenefitDetailScreen`, ícono de categorías + tarjetas con
imagen). Hoy 100% mockeado en `BeneficiosRepositoryImpl` (3 beneficios de ejemplo: auxilio mecánico/grúa,
apoyo legal, plan de salud) — el modelo de datos del cliente (`domain/model/Beneficio.kt`) ya está
diseñado para recibir esto de un backend sin cambiar UI, solo falta el endpoint real.

**Endpoint**

```http
GET /v1/beneficios
```

### Query params (opcionales)

- `categoria` — si se manda, filtra server-side (`"vial" | "legal" | "salud" | ...`, abierto, lo define el
  backend). Hoy el cliente filtra client-side sobre la lista completa (`BeneficiosViewModel.categoriaSeleccionada`)
  porque no hay backend — si el catálogo crece mucho, mover el filtro al servidor es una optimización futura,
  no un requisito para el primer lanzamiento de este endpoint.

### ¿Requiere sesión?

Puede llamarse **con o sin** `Authorization: Bearer <token>` — no hay nada en el modelo `Beneficio` que sea
específico de un usuario. Si a futuro se quiere personalizar contenido por tipo de usuario (`PLACA` vs.
`INVITADO`, ver sección 3), este es el endpoint natural para hacerlo — no está en el alcance de esta primera
versión.

### Response 200 (OK)

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
      "imagenCard": "https://tu-dominio/web/content/beneficios/auxilio-grua-card.jpg",
      "descripcionCorta": "Traslado en grúa (1 vez al mes) y auxilio mecánico en ruta, convenio con Los Andes Cooperativa.",
      "multimedia": [
        { "tipo": "IMAGEN", "url": "https://tu-dominio/web/content/beneficios/auxilio-grua-1.jpg" },
        { "tipo": "VIDEO", "url": "https://tu-dominio/web/content/beneficios/auxilio-grua-video.mp4" }
      ],
      "staff": [
        {
          "nombre": "Julio Cárdenas",
          "especialidad": "Técnico mecánico",
          "whatsapp": "51999333444",
          "avatarUrl": null
        }
      ],
      "cubre": [
        { "icono": "🚗", "texto": "Traslado en grúa hasta 1 vez al mes" },
        { "icono": "🔧", "texto": "Auxilio mecánico en ruta sin costo adicional" }
      ],
      "recomendaciones": [
        { "icono": "📞", "titulo": "Llama antes de moverte", "texto": "Coordina con el técnico antes de intentar mover el vehículo tú mismo" }
      ]
    }
  ],
  "meta": { "timestamp": "2026-08-25T15:04:00Z", "requestId": "..." }
}
```

Cada campo corresponde 1:1 con `domain/model/Beneficio.kt` (`Beneficio`, `Proveedor`, `MediaBeneficio`,
`StaffBeneficio`, `CoberturaBeneficio`, `RecomendacionBeneficio`) — no hace falta ningún mapeo/adaptación
del lado del cliente si el backend respeta estos nombres de campo exactamente. `multimedia[].tipo` es
`"IMAGEN" | "VIDEO"` (string, mismo valor que el enum `TipoMediaBeneficio` del cliente). `staff` puede venir
vacío (`[]`) para beneficios que no se coordinan por WhatsApp con una persona específica (ej. el plan de
salud) — el cliente ya maneja ese caso ocultando esa sección.

### Errores comunes

- `500 INTERNAL_ERROR`
- `503 SERVICE_UNAVAILABLE`

---

## Resumen de lo que asume este documento (para revisar con el equipo de backend)

1. **Modelo de autenticación**: registro crea una solicitud pendiente de revisión (como antes) **y**
   además deja credenciales de login inmediatas — el login-email distingue `PLACA` (usuario real de Odoo)
   de `INVITADO` (solicitud, con o sin aprobar) en la misma respuesta. **La contraseña se exige en AMBOS
   logins** — no solo en el nuevo `POST /v1/auth/login-email`, también en el `POST /v1/auth/login` (placa)
   existente, que pasa a requerir `password` en el request (cambio de contrato, no un endpoint nuevo).
   Bloqueante antes de desplegar ese cambio: confirmar con el equipo de backend/Odoo si los partners
   existentes ya tienen contraseña de portal o hace falta un plan de migración — mientras tanto, el
   login-email puede lanzarse solo para invitados sin depender de esa migración.
2. `provincia`/`distrito` viajan como texto (nombre), no código INEI — el cliente no tiene ese código hoy.
3. La selfie viaja como base64 dentro del JSON (igual que voucher/papeletas en este mismo backend), no
   como `multipart/form-data` ni URL prefirmada de S3 (ese patrón sí existe, pero en el backend *distinto*
   del módulo de reportes de incidentes — no aplica acá).
4. El registro se modela en Odoo como un registro separado (`adt.solicitud.cliente`, opción A) que solo se
   convierte en `res.partner` real al aprobarse — alternativa (opción B, `res.partner` desde el día uno con
   flags custom) documentada arriba, a elección del equipo de backend.
5. El servicio de consulta de estado (`GET .../register/{id}`) es una propuesta nueva, no está conectado a
   ninguna pantalla de la app todavía.
6. `GET /v1/beneficios` no requiere sesión — el modelo `Beneficio` no tiene hoy nada específico por usuario.
