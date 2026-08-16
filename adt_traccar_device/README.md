# adt_traccar_device

Registra vehículos en Traccar (placa + IMEI), crea un usuario Traccar
individual por vehículo, y expone un endpoint REST para que la app obtenga
esas credenciales y se conecte directamente al websocket de Traccar.

Módulo autocontenido: no depende de `fleet_addons` (en desuso) ni de
ningún otro módulo para el campo IMEI — `x_imei` se define directamente
acá (`models/fleet_vehicle.py`) y se edita desde la pestaña "Traccar / GPS"
en la ficha del vehículo.

**El password Traccar se guarda en texto plano** (`traccar_password`),
decisión explícita para no depender de una clave de cifrado externa. El
campo está restringido por el grupo `adt_traccar_device.group_traccar_credentials_admin`
en las vistas de Odoo (por defecto, solo el admin lo ve ahí). El endpoint
REST que lo entrega a la app acepta el mismo Bearer token que usa el resto
de la API móvil **o** directamente `?plate=ABC-123` sin token (mismo
criterio que `POST /v1/auth/login` en `adt_comercial`) — ver "Uso" abajo.

Diseño completo: `../plan-adt-traccar-device.md`.

## Requisitos de deploy

1. **Configuración de Traccar admin** (`Ajustes → Traccar`): la misma que ya
   usa el módulo `adt_traccar` (`adt_traccar.url` / `.email` / `.password`).
   Este módulo usa esas credenciales solo para hablar con la API de Traccar
   como administrador (crear devices/users/permissions); no crea un usuario
   admin nuevo.

Nada más — no hay variables de entorno ni paquetes Python adicionales que
instalar.

## Uso

- **Individual**: en la ficha de un vehículo (Flota), botón "Traccar" en el
  header → wizard → confirmar. Requiere que el vehículo tenga IMEI, una
  cuenta comercial activa (`adt.comercial.cuentas` en `en_curso`/`aprobado`)
  y que el cliente tenga email en Contactos.
- **Masivo (selección manual)**: en la vista de lista de Flota, seleccionar
  vehículos → menú "Acción" → "Sincronizar con Traccar".
- **Masivo (toda la flota, sin seleccionar nada)**: menú **Traccar GPS →
  Sincronizar toda la flota con Traccar** — resuelve internamente todos los
  vehículos activos y corre la misma sincronización. Pensado para poner al
  día de una sola vez todos los vehículos que ya existían antes de instalar
  el módulo.
  - Ambas variantes: los que no califiquen todavía se omiten (se informa
    por qué) sin interrumpir el resto del lote. Es idempotente por IMEI:
    correrlas varias veces sobre el mismo vehículo no genera usuarios
    Traccar nuevos si el IMEI no cambió. Se autentican **una sola vez**
    contra Traccar y reutilizan esa sesión para todo el lote (no hay un
    login por vehículo), para que sincronizar la flota completa no sea
    lento ni sature Traccar de logins.
- **App**: `GET /v1/app/traccar-credentials` devuelve `traccar_url`,
  `traccar_ws_url`, `email`, `password`, `device_id` y `plate`. Dos formas
  de pedirlo:
  - Con `Authorization: Bearer <mobile.token>` → el vehículo sale del token
    (flujo original).
  - Con `?plate=ABC-123` (sin token) → busca directo por placa, mismo
    criterio de seguridad que ya usa `POST /v1/auth/login` en
    `adt_comercial` (la placa alcanza, sin más credenciales). Pensado para
    apps que ya resuelven todo por placa sin manejar sesión.
  - Si se mandan ambos, la placa debe coincidir con el vehículo del token
    (si no, 403).
- **Estado GPS puntual**: botón "Actualizar" (en el vehículo o en la
  credencial) que consulta a Traccar en el momento del click: estado
  (`En línea`/`Desconectado`/`Desconocido`), último reporte, velocidad
  (km/h), batería (%, si el dispositivo la reporta), latitud/longitud y
  link a Google Maps. También hay una acción masiva ("Actualizar estado
  GPS") desde la lista de vehículos.
- **Mapa embebido con posición casi en vivo**: en la misma pestaña
  "Traccar / GPS", arriba de los campos de detalle, un mapa (Leaflet,
  OpenStreetMap) con un marcador que se mueve solo mientras la ficha está
  abierta — hace polling cada 8 segundos contra el propio Odoo
  (`/adt_traccar_device/live_position`), que a su vez le pregunta a
  Traccar server-side (mismo código que el botón "Actualizar"). **No** es
  un websocket directo navegador↔Traccar (se evaluó y se descartó por
  riesgo de CORS no verificable desde acá — ver plan, sección 4.6); si se
  confirma que Traccar permite CORS desde el dominio de Odoo, se puede
  migrar a websocket directo más adelante. Leaflet se carga perezosamente
  desde CDN (`unpkg.com`) solo al abrir esa pestaña, no en todo el backend.
