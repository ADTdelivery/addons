# API: Items de Contenido Configurable (HU-014)

Servicio REST para que la app móvil pida listas de "items" configurables
desde Odoo — cada uno puede traer imagen, teléfono, link, deep link y/o
botón, según lo que se cargue. Pensado para pantallas tipo "Ayuda",
"Contáctanos", "Accesos rápidos", banners informativos, etc., sin tener
que programar una pantalla nueva por cada caso: se agregan/editan items
desde Odoo y la app los renderiza dinámicamente.

Módulo: `adt_comercial`. Modelo: `mobile.content.item`. Implementación:
`controllers/mobile_api.py` (HU-014), `models/mobile_models.py` (HU-014).

---

## 1. Configuración desde Odoo

Menú: **Móvil → Configuración → Items de Contenido**.

Cada item tiene:

| Campo Odoo | Para qué sirve |
|---|---|
| `section` | Código que la app usa para pedir un grupo de items (ej. `ayuda`, `contactos`, `accesos_rapidos`). Varios items con la misma sección forman una lista. Solo letras, números y `_`. |
| `title` / `subtitle` / `description` | Contenido textual del item. |
| `icon` | Nombre de ícono o emoji, libre — la app decide cómo interpretarlo. |
| `image` | Imagen opcional (se sube desde Odoo como cualquier campo imagen). |
| `item_type` | Qué acción principal dispara el item al tocarlo: `IMAGE`, `TEXT`, `PHONE`, `WHATSAPP`, `LINK`, `DEEP_LINK`, `BUTTON`. |
| `phone` | Usado si `item_type` es `PHONE` o `WHATSAPP`. |
| `link_url` | Usado si `item_type` es `LINK`. |
| `deep_link` | Usado si `item_type` es `DEEP_LINK`. |
| `button_label` / `button_color` | Texto/color de un botón — se puede usar como CTA principal (`BUTTON`) o secundario junto a cualquier otro tipo. |
| `active_from` / `active_to` | Vigencia opcional (si no se cargan, el item no vence nunca). |
| `extra_data` | JSON libre para lo que este modelo no contempla (ej. `{"badge": "Nuevo", "color_fondo": "#FFAA00"}`) — se devuelve tal cual parseado en la respuesta. |
| `sequence` | Orden dentro de su sección. |

No hay límite de items por sección ni de secciones — es de propósito general.

---

## 2. Endpoint: listar items

```
GET /v1/content-items
GET /v1/content-items?section=ayuda
```

- **Auth**: ninguna (`auth='none'`) — igual criterio que `GET /v1/app-images`: es contenido de configuración de la app, no datos del cliente, y puede consumirse antes del login.
- **CORS**: habilitado.

### Parámetros (query string)

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `section` | string | No | Filtra por sección (case-insensitive). Sin este parámetro, devuelve **todos** los items activos y vigentes de todas las secciones. |
| `page` | int | No (default `1`) | Página, base 1. |
| `pageSize` | int | No (default `50`, máx `100`) | Tamaño de página. |

### Filtro de vigencia (automático, sin parámetro)

Solo se devuelven items con `active = true` y, si tienen `active_from`/`active_to` cargados, que la fecha/hora actual esté dentro de ese rango. Items sin fechas cargadas siempre se consideran vigentes.

### Respuesta — `200 OK`

```json
{
  "success": true,
  "statusCode": 200,
  "data": {
    "items": [
      {
        "id": "5",
        "section": "contactos",
        "title": "Atención al cliente",
        "subtitle": "Lunes a viernes, 9am - 6pm",
        "description": "Escríbenos por WhatsApp para cualquier consulta.",
        "icon": "whatsapp",
        "imageUrl": "https://tu-dominio-odoo/v1/content-items/5/image",
        "itemType": "WHATSAPP",
        "phone": "51999888777",
        "linkUrl": null,
        "deepLink": null,
        "buttonLabel": "Escribir por WhatsApp",
        "buttonColor": "#25D366",
        "actionUrl": "https://wa.me/51999888777?text=Hola%2C+Escribir+por+WhatsApp",
        "extra": { "badge": "Nuevo" },
        "sequence": 10,
        "activeFrom": null,
        "activeTo": null
      },
      {
        "id": "8",
        "section": "contactos",
        "title": "Oficina Miraflores",
        "subtitle": null,
        "description": "Av. Larco 123, Miraflores, Lima",
        "icon": "map-pin",
        "imageUrl": null,
        "itemType": "LINK",
        "phone": null,
        "linkUrl": "https://maps.google.com/?q=-12.1211,-77.0296",
        "deepLink": null,
        "buttonLabel": "Ver en mapa",
        "buttonColor": null,
        "actionUrl": "https://maps.google.com/?q=-12.1211,-77.0296",
        "extra": null,
        "sequence": 20,
        "activeFrom": null,
        "activeTo": null
      }
    ]
  },
  "meta": {
    "timestamp": "2026-08-15T14:32:10Z",
    "requestId": "…",
    "pagination": {
      "page": 1,
      "pageSize": 50,
      "totalItems": 2,
      "totalPages": 1,
      "hasNext": false,
      "hasPrev": false
    }
  }
}
```

### Diccionario de campos (cada item)

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | Id del item (string por consistencia con el resto de la API). |
| `section` | string | Sección a la que pertenece. |
| `title` | string | Título. |
| `subtitle` | string \| null | Subtítulo. |
| `description` | string \| null | Descripción larga. |
| `icon` | string \| null | Ícono/emoji configurado. |
| `imageUrl` | string \| null | URL directa a la imagen (ver sección 3), `null` si no tiene imagen cargada. |
| `itemType` | string | Uno de: `IMAGE`, `TEXT`, `PHONE`, `WHATSAPP`, `LINK`, `DEEP_LINK`, `BUTTON`. Le dice a la app qué acción disparar al tocar el item. |
| `phone` | string \| null | Teléfono, **normalizado a solo dígitos** (sin espacios/guiones/`+`) por el propio servicio — presente si `itemType` es `PHONE`/`WHATSAPP` (puede venir igual aunque el tipo sea otro, si se cargó). |
| `linkUrl` | string \| null | URL externa, relevante si `itemType == LINK`. |
| `deepLink` | string \| null | Deep link interno de la app, relevante si `itemType == DEEP_LINK`. |
| `buttonLabel` | string \| null | Texto de un botón (CTA principal o secundario). |
| `buttonColor` | string \| null | Color HEX del botón, ej. `#25D366`. |
| `actionUrl` | string \| null | **La URL lista para abrir tal cual**, según `itemType` — no hay que armar nada del lado de la app. `WHATSAPP` → `https://wa.me/<telefono>?text=<mensaje precargado>`; `PHONE` → `tel:<telefono>`; `LINK` → el valor de `linkUrl`; `DEEP_LINK` → el valor de `deepLink`; para `IMAGE`/`TEXT`/`BUTTON` viene `null` (no hay una única acción — un `BUTTON` se combina con otro tipo si necesita acción). |
| `extra` | object \| null | Lo que se haya cargado en `extra_data` (Odoo), ya parseado como JSON. `null` si no se cargó nada o el JSON era inválido. |
| `sequence` | integer | Orden sugerido dentro de la sección. |
| `activeFrom` / `activeTo` | string \| null | Vigencia, formato `dd/mm/yyyy HH:MM:SS` (mismo formato que el resto de la API), `null` si no se configuró. |

### Errores

| HTTP | Caso |
|---|---|
| 400 | `page`/`pageSize` no son números válidos. |
| 500 | Error inesperado del servidor. |

---

## 3. Endpoint: imagen del item

```
GET /v1/content-items/<id>/image
```

Sirve el binario de la imagen directamente (sin `access_token` ni pasar por `/web/content`), pensado para usarse tal cual en un `<img src="...">` / `Image.network(...)` / `Coil` de la app — mismo patrón que ya usa `GET /v1/app-images/<code>/file`.

- **Auth**: ninguna.
- Si el item no existe, está inactivo, o no tiene imagen cargada → `404`.
- Headers de la respuesta: `Content-Type` (mimetype real del archivo subido), `Content-Disposition: inline`, `Cache-Control: public, max-age=3600`.

No hace falta llamarlo manualmente: el campo `imageUrl` de la respuesta de la sección 2 ya viene armado con esta URL.

---

## 4. Ejemplos de integración

### curl

```bash
# Todos los items de la sección "ayuda"
curl -s "https://tu-dominio-odoo/v1/content-items?section=ayuda"

# Todos los items, todas las secciones
curl -s "https://tu-dominio-odoo/v1/content-items"
```

### JavaScript / fetch

```javascript
async function getContentItems(section) {
  const url = new URL('https://tu-dominio-odoo/v1/content-items');
  if (section) url.searchParams.set('section', section);

  const res = await fetch(url);
  const body = await res.json();
  if (!body.success) {
    throw new Error(`${body.error.code}: ${body.error.message}`);
  }
  return body.data.items;
}

// Uso: la app NO arma ninguna URL, solo abre item.actionUrl si existe
const items = await getContentItems('contactos');
items.forEach((item) => {
  if (item.actionUrl) {
    // WHATSAPP -> abre WhatsApp con el mensaje ya precargado
    // PHONE    -> abre el marcador telefónico (tel:)
    // LINK / DEEP_LINK -> abre la URL tal cual
    // window.open(item.actionUrl) / Linking.openURL(item.actionUrl) en RN
  } else {
    // IMAGE / TEXT / BUTTON sin tipo secundario: solo mostrar contenido,
    // sin acción al tocar (o usar item.buttonLabel como CTA visual)
  }
});
```

---

## 5. Notas

- El endpoint es **de solo lectura** para la app — la administración de items se hace exclusivamente desde Odoo (Móvil → Configuración → Items de Contenido).
- Un mismo item puede traer varios campos de acción a la vez a propósito (ej. teléfono **y** botón con texto propio) — la app decide qué mostrar según `itemType`, pero los demás campos quedan disponibles por si se quiere un diseño mixto (ej. una tarjeta con imagen + botón, aunque el tipo principal sea `LINK`).
- `extra` existe para no tener que pedir un cambio de modelo/API cada vez que la app necesite un dato puntual nuevo — se carga como JSON libre en Odoo y llega parseado.
- No requiere sesión ni token: si en algún momento se necesita contenido **personalizado por cliente** (no genérico), ese es un caso distinto (como `mobile.notification`, que sí es por `partner_id`/`vehicle_id`), no este endpoint.
- **Importante sobre `phone`/`actionUrl` en WhatsApp**: el servicio normaliza el teléfono (le saca espacios/guiones/`+`), pero **no adivina el código de país** si falta. Al cargar el item en Odoo, el campo `phone` debe llevar el código de país completo (ej. `51999888777`, no `999888777`) — si falta, `actionUrl` va a armar un link de WhatsApp roto (le va a faltar el "51" adelante). Revisá esto en los items ya cargados.
