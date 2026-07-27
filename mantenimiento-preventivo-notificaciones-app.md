# Notificaciones Push de Mantenimiento Preventivo — Guía de Integración (App)

Documento de referencia para el equipo de app: cómo llegan las notificaciones
push del módulo **ADT Mantenimiento Preventivo**, qué formato trae el `data`,
cómo interpretar el deep link, y **la API REST para listar mantenimientos
pendientes y registrar que un mantenimiento ya se hizo** (secciones 10-13).

Fuente en el backend:
- `adt_mantenimiento_preventivo/models/notification_campaign.py` (push, deep link).
- `adt_mantenimiento_preventivo/models/vehicle_rule_state.py` (listado de pendientes).
- `adt_mantenimiento_preventivo/models/orden_atencion.py` (registro de atención).
- `adt_mantenimiento_preventivo/controllers/mobile_api.py` (los 3 endpoints REST).

---

## 1. Resumen del flujo

1. Un vehículo cruza un umbral de kilometraje de una regla de mantenimiento
   (ej. "Cambio de aceite" a los 1000km) → se crea una **campaña**.
2. La campaña envía **N notificaciones por día** durante **M días**
   (configurado por regla), respetando los horarios configurados.
3. Cada envío individual:
   - Manda un **push FCM** (`title`, `body`, `data`) al dispositivo del cliente.
   - Guarda un registro en `mobile.notification` (el feed de notificaciones
     in-app que la app ya consume para otras cosas, ej. cuotas próximas a
     vencer), con `notification_type = "MAINTENANCE"` y el deep link ya
     armado en el campo `deep_link`.

Es decir: la notificación le llega a la app por **dos canales** que traen
prácticamente la misma información:
- **Push (FCM)** → mientras el usuario tiene la app cerrada o en background.
- **Feed in-app** (`mobile.notification` / el endpoint que ya usan para
  listar notificaciones) → para cuando el usuario abre la pantalla de
  notificaciones dentro de la app.

---

## 2. Estructura del push

```json
{
  "notification": {
    "title": "🔧 Mantenimiento preventivo",
    "body": "Tu vehículo ABC-123 alcanzó 1837 km. Es momento de realizar el mantenimiento: Cambio de aceite."
  },
  "data": { "...ver sección 3..." }
}
```

⚠️ **Importante — todo en `data` llega como STRING.** FCM solo permite pares
`string → string` en el `data` payload (no objetos anidados, no números ni
booleanos nativos). El relay de push (`firebase_events/firebase_service.py`)
hace `str(valor)` sobre cada campo antes de mandarlo. Esto significa que del
lado de la app:

- `"vehicle_id": "7"` → hay que castear a int si se necesita como número.
- `"oferta_precio": "45.0"` → castear a float/decimal.
- `"es_oferta": "1"` → comparar como texto (`== "1"`), no como booleano.

---

## 3. Referencia de campos de `data`

| Campo | Tipo (como string) | Siempre presente | Descripción |
|---|---|---|---|
| `tipo` | string | Sí | Siempre `"MANTENIMIENTO_PREVENTIVO"`. Úsalo para distinguir este tipo de push de otros (`PAYMENT_DUE`, `CAPTURA`, etc.) |
| `vehicle_id` | string→int | Sí | ID del vehículo (`fleet.vehicle`) en Odoo |
| `placa` | string | Sí | Placa del vehículo, ej. `"ABC-123"` |
| `regla_id` | string→int | Sí | ID de la regla de mantenimiento disparada |
| `regla` | string | Sí | Nombre de la regla, ej. `"Cambio de aceite"` |
| `campana_id` | string→int | Sí | ID de la campaña de notificación (útil como identificador único de "este evento") |
| `link_type` | string | Sí | Siempre `"DEEP_LINK"` por ahora |
| `deep_link` | string | Sí | Ver sección 4 |
| `es_oferta` | string `"1"` / `"0"` | Sí | Si `"1"`, los campos `oferta_*` de abajo vienen poblados |
| `oferta_titulo` | string | Solo si `es_oferta="1"` | Título de la oferta |
| `oferta_descripcion` | string | Solo si `es_oferta="1"` | Descripción de la oferta |
| `oferta_precio` | string→float | Solo si `es_oferta="1"` | Precio (puede ser `"0.0"` si no tiene precio fijo) |
| `oferta_moneda` | string | Solo si `es_oferta="1"` | Código de moneda, ej. `"PEN"` |
| `oferta_dias_duracion` | string→int | Solo si `es_oferta="1"` | Días de vigencia de la oferta |
| `oferta_wsp_link` | string (URL) | Solo si `es_oferta="1"` | Link de WhatsApp ya armado (`https://wa.me/...?text=...`), listo para abrir con un `Intent`/`url_launcher` |
| `oferta_imagen_url` | string (URL) \| `""` | Solo si `es_oferta="1"` | URL pública de la **primera** imagen de la oferta (portada), lista para usar directo en un `<Image>`/`<img>`. Ver sección 6.1 — no requiere token. String vacío si la regla no tiene ninguna imagen cargada |
| `oferta_imagenes_count` | string→int | Solo si `es_oferta="1"` | Cantidad total de imágenes que tiene la oferta. Si hay más de 1, la lista completa de URLs viene en `GET /v1/mantenimiento-preventivo/pendientes` (campo `oferta_imagenes_urls`, sección 10.2) — el push solo trae la portada porque `data` no admite arrays (ver nota de la sección 2) |

---

## 4. Deep link — formato

```
adt://mantenimiento/campana/{campana_id}?vehicle_id={vehicle_id}&regla_id={regla_id}&es_oferta={0|1}
```

**Ejemplo:**
```
adt://mantenimiento/campana/42?vehicle_id=7&regla_id=3&es_oferta=1
```

- **Scheme**: `adt://` (mismo esquema usado como referencia en la colección
  Postman del proyecto: `adt://loan/installments`, `adt://refinancing`,
  `adt://promotions` — no había un contrato formal antes de esto).
- **Path**: `mantenimiento/campana/{id}` → identifica el recurso y su ID.
- **Query params**: contexto adicional para no tener que resolverlo con una
  llamada extra (`vehicle_id`, `regla_id`, `es_oferta`).

### Tabla de ruteo sugerida

| Path | Pantalla destino sugerida |
|---|---|
| `mantenimiento/campana/{id}` | Detalle de la campaña de mantenimiento del vehículo `{vehicle_id}`. Si `es_oferta=1`, mostrar también el bloque de oferta (imágenes, precio, botón WhatsApp con `oferta_wsp_link`). |

Si en el futuro se agregan otros tipos de push con deep link, deberían seguir
el mismo esquema (`adt://<recurso>/<subrecurso>/<id>?...`) para mantener
consistencia.

---

## 5. Ejemplos completos

### 5.1 Sin oferta (notificación simple de mantenimiento)

```json
{
  "tipo": "MANTENIMIENTO_PREVENTIVO",
  "vehicle_id": "7",
  "placa": "9300AD",
  "regla_id": "3",
  "regla": "Cambio de frenos",
  "campana_id": "41",
  "link_type": "DEEP_LINK",
  "deep_link": "adt://mantenimiento/campana/41?vehicle_id=7&regla_id=3&es_oferta=0",
  "es_oferta": "0"
}
```

### 5.2 Con oferta

```json
{
  "tipo": "MANTENIMIENTO_PREVENTIVO",
  "vehicle_id": "7",
  "placa": "9300AD",
  "regla_id": "3",
  "regla": "Cambio de aceite",
  "campana_id": "42",
  "link_type": "DEEP_LINK",
  "deep_link": "adt://mantenimiento/campana/42?vehicle_id=7&regla_id=3&es_oferta=1",
  "es_oferta": "1",
  "oferta_titulo": "Descuento 20% en cambio de aceite",
  "oferta_descripcion": "Válido presentando esta notificación en tienda.",
  "oferta_precio": "45.0",
  "oferta_moneda": "PEN",
  "oferta_dias_duracion": "5",
  "oferta_wsp_link": "https://wa.me/51999111222?text=Hola%2C%20quiero%20m%C3%A1s%20informaci%C3%B3n%20sobre%20la%20oferta%3A%20Descuento%2020%25%20en%20cambio%20de%20aceite",
  "oferta_imagen_url": "https://tu-dominio-odoo.com/v1/mantenimiento-preventivo/imagen/15",
  "oferta_imagenes_count": "2"
}
```

---

## 6. Imágenes de la oferta y feed de notificaciones in-app

### 6.1 Endpoint de imágenes de la oferta (público, sin token)

```
GET /v1/mantenimiento-preventivo/imagen/{imagen_id}
```

Devuelve el binario de la imagen directo (con el `Content-Type` correcto
según la extensión del archivo subido) — se puede usar tal cual como `src`
de un `<Image>`/`<img>` sin headers especiales, igual que ya hacen con
`/v1/app-images/<code>/file` para las imágenes de la app. **No requiere
`Authorization`** porque son imágenes de marketing, no datos privados del
cliente.

El `imagen_id` de la portada ya viene armado en `data.oferta_imagen_url`
(push, sección 3) y en `oferta_imagenes_urls` (listado de pendientes,
sección 10.2) — no hace falta construir la URL a mano ni pedir los IDs por
separado.

Si la imagen no existe (ID inválido o regla sin imágenes), responde `404`
sin cuerpo JSON (es una respuesta HTTP simple, no usa el envelope
`success/error` del resto de la API).

### 6.2 Feed de notificaciones in-app (`mobile.notification`)

Cada envío también queda registrado en el modelo `mobile.notification` (el
mismo que ya usan para el feed de notificaciones de la app), con estos
campos relevantes:

| Campo | Valor |
|---|---|
| `notification_type` | `"MAINTENANCE"` (nuevo, agregado por este módulo) |
| `link_type` | `"DEEP_LINK"` |
| `deep_link` | Mismo formato de la sección 4 |
| `title` / `body` | Mismo texto que el push |
| `partner_id` / `vehicle_id` | Cliente y vehículo relacionados |
| `is_read` | `false` al crearse |

Si la app ya tiene una pantalla de "Notificaciones" que lee este modelo (vía
el endpoint que ya exista para `mobile.notification`/`/v1/notifications`),
las notificaciones de mantenimiento van a aparecer ahí automáticamente y
deberían navegar igual que el push, leyendo el mismo campo `deep_link`.

---

## 7. Pseudocódigo sugerido para la app

```
al recibir push o al tocar una notificación del feed:
    data = push.data  // o el registro de mobile.notification

    if data.tipo == "MANTENIMIENTO_PREVENTIVO":
        parsear data.deep_link como URI:
            scheme = "adt"
            path   = "mantenimiento/campana/{campana_id}"
            query  = { vehicle_id, regla_id, es_oferta }

        navegar a PantallaDetalleCampana(
            campanaId: query o path .campana_id,
            vehicleId: data.vehicle_id,
            reglaId: data.regla_id,
        )

        // dentro de esa pantalla, si necesitas los datos de la oferta,
        // ya vienen en el mismo payload (data.oferta_titulo, etc.) —
        // no hace falta pedirlos a otra API.

        if data.es_oferta == "1":
            mostrar bloque de oferta:
                titulo: data.oferta_titulo
                descripcion: data.oferta_descripcion
                precio: data.oferta_precio + " " + data.oferta_moneda
                botón WhatsApp -> abrir data.oferta_wsp_link directamente
                imagenPortada: <Image src={data.oferta_imagen_url}/>  // ver sección 6.1
                // si data.oferta_imagenes_count > 1 y quieres la galería
                // completa (no solo la portada), pide GET /pendientes
                // (sección 10.2) y usa oferta_imagenes_urls
```

---

## 8. Limitaciones conocidas / pendiente de implementar

✅ **Resuelto:** las imágenes de la oferta ya tienen endpoint de descarga
(`GET /v1/mantenimiento-preventivo/imagen/{id}`, sección 6.1) y su URL ya
viaja armada tanto en el push (`oferta_imagen_url`, solo la portada) como en
el listado de pendientes (`oferta_imagenes_urls`, la lista completa —
sección 10.2).

⚠️ **No existe un endpoint para pedir el detalle completo de una campaña
por `campana_id`.** Hoy toda la información que la pantalla de destino
necesita (excepto las imágenes) ya viaja en el mismo payload del push/feed,
así que en principio no debería hacer falta una llamada adicional. Si más
adelante se requiere refrescar el estado de la campaña desde la app (por
ejemplo, para saber si ya se canceló o finalizó), también habría que
construir ese endpoint.

---

## 9. Notas técnicas adicionales

- El servicio que efectivamente dispara el push hacia FCM
  (`firebase_events/firebase_service.py`) NO requiere ningún cambio para
  todo lo anterior — ya soporta pares `string → string` arbitrarios en
  `data` sin necesidad de tocar su código.
- El link de WhatsApp (`oferta_wsp_link`) ya viene armado con el mensaje
  pre-cargado (`https://wa.me/<numero>?text=<mensaje URL-encoded>`); basta
  con abrirlo con el intent/URL launcher nativo, no hace falta construirlo
  en la app.
- `es_oferta` puede venir como `"0"` sin que existan los campos `oferta_*`
  — siempre verificar `es_oferta == "1"` antes de leerlos.

---

## 10. API REST — Mantenimientos pendientes y confirmación de atención

Además del push, hay 3 endpoints para que la app pueda: (a) mostrar una
pantalla con **todos los mantenimientos pendientes** de un vehículo (no solo
el de la última notificación), y (b) dejar que el cliente **confirme que ya
hizo el mantenimiento** en otro lado (taller externo, ADT Taller, Taller
TVS, etc.).

⚠️ **A diferencia del push (sección 2-3), estos endpoints SÍ devuelven tipos
JSON nativos** (`int`, `float`, `boolean`, `null`) — no todo viene como
string. Cada tabla de abajo indica el tipo real.

### 10.0 Autenticación (igual para los 3 endpoints)

Mismo mecanismo que ya usan el resto de endpoints `/v1/...` de la app
(`adt_comercial`): header `Authorization: Bearer <token>`, token obtenido
vía `POST /v1/auth/login` (por placa). Mismo formato de respuesta:

```json
// éxito
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": { "...": "..." },
  "meta": { "timestamp": "2026-07-26T10:00:00Z", "requestId": "uuid" }
}
```
```json
// error
{
  "success": false,
  "statusCode": 401,
  "error": { "code": "TOKEN_EXPIRED", "message": "El token ha expirado." },
  "meta": { "timestamp": "2026-07-26T10:00:00Z", "requestId": "uuid" }
}
```

Códigos de error posibles en estos 3 endpoints:

| Code | HTTP | Cuándo |
|---|---|---|
| `TOKEN_MISSING` | 401 | No se mandó el header `Authorization` |
| `TOKEN_INVALID` | 401 | El token no existe o fue revocado |
| `TOKEN_EXPIRED` | 401 | El token venció |
| `PLATE_REQUIRED` | 400 | Falta el parámetro `plate` |
| `PLATE_NOT_FOUND` | 404 | No existe un vehículo con esa placa |
| `REGLA_ID_REQUIRED` | 400 | Falta `regla_id` (solo en `/atencion`) |
| `ORIGEN_ID_REQUIRED` | 400 | Falta `origen_id` (solo en `/atencion`) |
| `REGLA_NOT_FOUND` | 404 | El `regla_id` no existe (solo en `/atencion`) |
| `ORIGEN_NOT_FOUND` | 404 | El `origen_id` no existe (solo en `/atencion`) |
| `KM_ATENCION_INVALID` | 400 | `km_atencion` no es numérico (solo en `/atencion`) |
| `INTERNAL_ERROR` | 500 | Error inesperado al registrar la atención |

---

### 10.1 `GET /v1/mantenimiento-preventivo/origenes`

Catálogo **configurable** de orígenes de atención (dónde se hizo el
mantenimiento). Úsalo para armar el selector — no lo hardcodees en la app,
porque el backoffice puede agregar/renombrar opciones en cualquier momento.

**Request**
```
GET /v1/mantenimiento-preventivo/origenes
Authorization: Bearer <token>
```

**Response 200**
```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": [
    { "id": 1, "nombre": "ADT Taller", "codigo": "ADT_TALLER" },
    { "id": 2, "nombre": "Taller TVS", "codigo": "TALLER_TVS" },
    { "id": 3, "nombre": "Otro Taller", "codigo": "OTRO_TALLER" }
  ],
  "meta": { "timestamp": "2026-07-26T10:00:00Z", "requestId": "uuid" }
}
```

| Campo (`data[]`) | Tipo | Descripción |
|---|---|---|
| `id` | int | Usar este valor como `origen_id` al llamar `/atencion` |
| `nombre` | string | Texto a mostrar en el selector |
| `codigo` | string \| null | Código interno opcional, no usar para lógica de negocio |

---

### 10.2 `GET /v1/mantenimiento-preventivo/pendientes?plate=ABC-123`

Lista **todos** los mantenimientos pendientes de confirmar para un
vehículo: cualquier regla cuyo umbral ya se disparó y todavía no fue
marcada como atendida — sin importar si la campaña de notificaciones sigue
activa o ya terminó de enviar. Ideal para una pantalla tipo "Mis
mantenimientos pendientes".

**Request**
```
GET /v1/mantenimiento-preventivo/pendientes?plate=9300AD
Authorization: Bearer <token>
```

**Response 200**
```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": [
    {
      "vehicle_rule_state_id": 12,
      "vehicle_id": 7,
      "placa": "9300AD",
      "regla_id": 3,
      "regla_nombre": "Cambio de aceite",
      "umbral_orden": 2,
      "umbral_km": 1000.0,
      "fecha_disparo": "2026-07-20T04:00:00",
      "estado": "campana_activa",
      "campana_id": 42,
      "es_oferta": true,
      "oferta_titulo": "Descuento 20% en cambio de aceite",
      "oferta_descripcion": "Válido presentando esta notificación en tienda.",
      "oferta_precio": 45.0,
      "oferta_moneda": "PEN",
      "oferta_dias_duracion": 5,
      "oferta_wsp_link": "https://wa.me/51999111222?text=...",
      "oferta_imagenes_urls": [
        "https://tu-dominio-odoo.com/v1/mantenimiento-preventivo/imagen/15",
        "https://tu-dominio-odoo.com/v1/mantenimiento-preventivo/imagen/16"
      ]
    },
    {
      "vehicle_rule_state_id": 15,
      "vehicle_id": 7,
      "placa": "9300AD",
      "regla_id": 4,
      "regla_nombre": "Cambio de frenos",
      "umbral_orden": 1,
      "umbral_km": 1000.0,
      "fecha_disparo": "2026-07-10T04:00:00",
      "estado": "campana_finalizada",
      "campana_id": null,
      "es_oferta": false,
      "oferta_titulo": null,
      "oferta_descripcion": null,
      "oferta_precio": null,
      "oferta_moneda": null,
      "oferta_dias_duracion": null,
      "oferta_wsp_link": null,
      "oferta_imagenes_urls": []
    }
  ],
  "meta": { "timestamp": "2026-07-26T10:00:00Z", "requestId": "uuid" }
}
```

| Campo (`data[]`) | Tipo | Descripción |
|---|---|---|
| `vehicle_rule_state_id` | int | ID interno del estado (no suele necesitarse en la app) |
| `vehicle_id` | int | ID del vehículo |
| `placa` | string | Placa del vehículo |
| `regla_id` | int | **Usar este valor como `regla_id` al confirmar en `/atencion`** |
| `regla_nombre` | string | Ej: `"Cambio de aceite"` |
| `umbral_orden` | int | Posición del umbral en la secuencia de la regla (1, 2, 3...) |
| `umbral_km` | float \| null | Kilometraje del umbral que disparó este pendiente |
| `fecha_disparo` | string (ISO 8601) \| null | Cuándo se disparó |
| `estado` | string | `"campana_activa"` (todavía mandando notificaciones) o `"campana_finalizada"` (ya dejó de notificar, pero sigue sin confirmarse) |
| `campana_id` | int \| null | ID de la campaña activa, si existe (`null` si `estado="campana_finalizada"`) |
| `es_oferta` | **boolean** | Si `true`, los campos `oferta_*` de abajo vienen poblados |
| `oferta_titulo` | string \| null | Título de la oferta asociada a esa regla |
| `oferta_descripcion` | string \| null | Descripción de la oferta |
| `oferta_precio` | **float** \| null | Precio de la oferta (puede ser `0.0` si no tiene precio fijo) |
| `oferta_moneda` | string \| null | Código de moneda, ej. `"PEN"` |
| `oferta_dias_duracion` | **int** \| null | Días de vigencia de la oferta |
| `oferta_wsp_link` | string \| null | Link de WhatsApp de la oferta, ya armado |
| `oferta_imagenes_urls` | **array de strings** (URLs) | Lista completa de imágenes de la oferta (ver sección 6.1), en orden. Array vacío `[]` si `es_oferta=false` o si la regla no tiene imágenes cargadas |

Si `data` es un array vacío `[]`, el vehículo no tiene mantenimientos
pendientes — mostrar el estado vacío correspondiente en la app.

---

### 10.3 `POST /v1/mantenimiento-preventivo/atencion`

Registra que el cliente ya hizo el mantenimiento de una regla. Cancela la
campaña activa (si existe) y detiene las notificaciones restantes de esa
regla para ese vehículo. Idealmente se llama desde un botón "Ya lo hice" en
cada ítem de la lista de pendientes (sección 10.2).

⚠️ **Manda el JSON plano tal cual, sin envolver en `{"jsonrpc":"2.0",...}`.**
Es un endpoint REST normal (HTTP + JSON), no JSON-RPC — si tu cliente envía
el body envuelto en el formato JSON-RPC de Odoo vas a recibir la respuesta
también envuelta en `{"jsonrpc": "2.0", "id": ..., "result": {...}}` en vez
del formato plano de abajo.

**Request**
```
POST /v1/mantenimiento-preventivo/atencion
Authorization: Bearer <token>
Content-Type: application/json
```
```json
{
  "plate": "9300AD",
  "regla_id": 3,
  "origen_id": 1,
  "observaciones": "Se hizo en el taller de la esquina, factura #123",
  "km_atencion": 1050.0,
  "fecha_atencion": "2026-07-26T09:30:00"
}
```

| Campo (body) | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `plate` | string | Sí | Placa del vehículo |
| `regla_id` | int | Sí | El `regla_id` que vino en el listado de pendientes (10.2) |
| `origen_id` | int | Sí | El `id` elegido del catálogo de orígenes (10.1) |
| `observaciones` | string | No | Texto libre |
| `km_atencion` | float | No | Kilometraje al momento de la atención |
| `fecha_atencion` | string (ISO 8601) | No | Si no se manda, se usa la fecha/hora actual del servidor |

**Response 200**
```json
{
  "success": true,
  "statusCode": 200,
  "message": "Mantenimiento registrado como atendido.",
  "data": {
    "orden_atencion_id": 88,
    "vehicle_id": 7,
    "placa": "9300AD",
    "regla_id": 3,
    "regla_nombre": "Cambio de aceite",
    "origen": "ADT Taller",
    "fecha_atencion": "2026-07-26T09:30:00"
  },
  "meta": { "timestamp": "2026-07-26T10:00:00Z", "requestId": "uuid" }
}
```

Después de una respuesta exitosa, ese ítem debería desaparecer de la
próxima llamada a `GET /v1/mantenimiento-preventivo/pendientes` — conviene
volver a pedir la lista (o quitar el ítem localmente) para refrescar la
pantalla.

---

## 11. Flujo sugerido en la app (pantalla "Mis mantenimientos")

```
al abrir la pantalla:
    GET /v1/mantenimiento-preventivo/pendientes?plate={placaDelVehiculo}
    mostrar un card por cada ítem: regla_nombre, umbral_km, fecha_disparo
    si es_oferta == true: mostrar banner de oferta con oferta_titulo y
        un botón que abra oferta_wsp_link

    en cada card, botón "Ya lo hice":
        GET /v1/mantenimiento-preventivo/origenes   (cachear, no cambia seguido)
        mostrar selector: ADT Taller / Taller TVS / Otro Taller / ...
        (opcional) pedir observaciones y/o km actual

        al confirmar:
            POST /v1/mantenimiento-preventivo/atencion {
                plate, regla_id (del card), origen_id (elegido),
                observaciones?, km_atencion?
            }
            si success: quitar el card de la lista (o volver a pedir 10.2)
            si error: mostrar error.message
```

---

## 12. Relación con el push / deep link (secciones 1-9)

- Cuando llega un push de `tipo="MANTENIMIENTO_PREVENTIVO"` (sección 3) y el
  usuario toca la notificación, **no hace falta llamar a `/pendientes`** para
  esa notificación puntual — todo lo necesario ya viene en el `data` del
  push. `/pendientes` es para la pantalla general de "todos mis
  mantenimientos", que puede incluir reglas que ya no están mandando push
  activamente (`estado="campana_finalizada"`).
- El `campana_id` que trae el push (sección 3) coincide con el `campana_id`
  que puede aparecer en `/pendientes` mientras esa campaña siga activa.

---

## 13. Limitaciones conocidas (actualización)

Con la sección 6.1 (endpoint de imágenes) y la sección 10 (pendientes /
atención), las dos limitaciones que quedaban señaladas en la sección 8 ya
están resueltas: hoy sí hay endpoint para descargar las imágenes de la
oferta, y sí hay endpoint para listar pendientes y confirmar atención.

Lo único que sigue sin implementar (ver sección 8): un endpoint para pedir
el detalle/refresh de una campaña puntual por `campana_id` — no debería
hacer falta hoy porque toda la info ya viaja en el push/feed/pendientes,
pero avisa si en algún momento lo necesitas.
