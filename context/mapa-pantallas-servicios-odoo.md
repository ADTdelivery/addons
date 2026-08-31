# Mapa Pantallas ↔ Servicios ↔ Odoo

Especificación funcional para el equipo de Odoo. Objetivo: construir dentro de Odoo una
vista de navegación ("mapa de la app") donde se dibuja cada pantalla de la app móvil ADT
Client tal como la ve el cliente, y al hacer **tab/click sobre una sección de esa pantalla**,
Odoo redirige directo a la sección/menú/modelo donde un administrador carga o edita el
contenido que esa sección muestra. La idea: que quien administra contenido no tenga que
adivinar "¿dónde en Odoo se edita la imagen del login?" — lo encuentra tocando la imagen
del login en el propio mapa.

Este documento no es una implementación, es el inventario de qué pantalla consume qué
servicio, para que el equipo de Odoo decida cómo armar esa navegación con sus propias
herramientas.

---

## 1. Reglas del mapa

1. **Pantalla 100% servicio** (todo su contenido sale de un endpoint editable en Odoo):
   se dibuja completa y **toda el área es un solo punto de acceso** — un tab en cualquier
   parte de esa pantalla redirige a la sección de Odoo correspondiente.
2. **Pantalla mixta** (parte de su contenido es diseño fijo de la app, parte es un servicio
   real): se dibujan **todas** sus secciones tal como se ven hoy en la app, pero **solo se
   resaltan/habilitan como punto de acceso las secciones que en verdad traen datos desde un
   servicio**. Las demás se muestran igual (para que el mapa sea fiel a la pantalla real),
   pero sin tab activo — son imágenes fijas empaquetadas en la app, no hay nada que cargar
   desde Odoo todavía.
3. Cuando una pantalla mixta tiene una sección que a su vez abre **otra pantalla completa**
   (ej. el banner "Novedades" del Home abre la pantalla de Novedades y Noticias), esa
   sección se resalta igual y redirige al destino de esa pantalla — no hace falta que la
   sección en sí traiga el dato, alcanza con que lleve a una pantalla que sí lo trae.
4. Quedan **fuera de este mapa** las pantallas cuyo contenido no sale de Odoo. Hoy el único
   caso es todo el módulo **"Seguridad" / Reportar incidente**: corre contra un backend
   totalmente distinto (otro host, otra API key, sin relación con Odoo) — no se dibuja en
   este mapa ni se resalta ninguna redirección para él.

---

## 2. Resumen: pantalla → servicio → Odoo

| Pantalla app | Tipo | Servicio (endpoint) | Módulo / modelo Odoo |
|---|---|---|---|
| Login (imagen hero) | Sección de pantalla mixta | `GET /v1/app-images?code=LOGIN` | `adt_comercial` — modelo de imágenes de app por código (mismo patrón que `mobile.content.item`; **nombre exacto del modelo/menú a confirmar con Odoo**) |
| Home / Inicio → Banner promocional | Sección de pantalla mixta | Pendiente de implementar (ver §3.2) | A definir — candidato natural: `mobile.content.item` (`adt_comercial`) con una `section` nueva, mismo mecanismo que ya usa el carrusel de "Mi Vehículo" |
| Publicidad Full Screen (interstitial sobre Home) | Pantalla 100% servicio, drill-down del bloque "Banners Home" (ver §3.2) | `GET /v1/content-items?section=FULL_SCREEN` | `adt_comercial` — `mobile.content.item` (menú Móvil > App > Banners Home > Publicidad Full Screen, `action_mobile_content_item_fullscreen`) |
| Home / Inicio → resto de secciones (header, accesos rápidos, banner Novedades) | Sección de pantalla mixta, **sin servicio propio** | — (imágenes fijas empaquetadas en la app) | No aplica — no se resalta, ver §3.2 |
| Tienda y Repuesto (listado + detalle de producto) | Pantalla 100% servicio | `GET /v1/catalog/products`, `GET /v1/catalog/products/{id}` | Catálogo de productos (probablemente `product.template`/`product.product` estándar de Odoo — **confirmar módulo/vista exacta con Odoo**) |
| Novedades y Noticias | Pantalla 100% servicio | `GET /v1/promotions` | Módulo de promociones (**confirmar modelo/menú con Odoo**) |
| Vehículo → Beneficios (hub + detalle) | Pantalla 100% servicio, drill-down propio (ver §3.5) | `GET /v1/beneficios` | `adt_comercial` — modelo de beneficios (**nombre exacto del modelo/menú a confirmar con Odoo**; las imágenes de beneficio hoy se sirven vía `/web/content/<id>/...`, o sea que el modelo ya vive en Odoo) |
| Vehículo → Cuenta autorizada | Sección de pantalla mixta | `GET /v1/loans` (campo `paymentAccounts`) | Cuentas de pago autorizadas del cliente (**confirmar modelo/menú con Odoo** — sale del mismo registro que la "Cuota actual", no es un endpoint aparte) |
| Vehículo → Atención al cliente | Sección de pantalla mixta | `GET /v1/loans` (campo `contacts`) | Contactos de soporte del cliente (**confirmar modelo/menú con Odoo** — mismo endpoint que "Cuenta autorizada" arriba) |
| Vehículo → Documentos / Papeletas / Mantenimiento / Ubicación GPS | Sección de pantalla mixta, **sin resaltar** | `v1/documents`, `v1/papeletas`, `v1/maintenance/lines`, `v1/app/traccar-credentials` | Datos transaccionales del vehículo del cliente (SOAT, infracciones, historial técnico, GPS) — no son "contenido de app" editable tipo página, son datos operativos por vehículo. Se dibujan en el mapa por completitud, pero no se resaltan (ver §3.5) |
| Seguridad / Reportar incidente | Fuera de alcance | Backend propio, no Odoo | No aplica |

---

## 3. Detalle por pantalla

### 3.1 Login

La pantalla de login trae una sola imagen dinámica (el "hero" de fondo/cabecera), pedida
por código fijo `LOGIN` a `GET /v1/app-images?code=LOGIN`. El resto de la pantalla (campos
de usuario/contraseña, botones, textos) es diseño fijo de la app, no sale de ningún
servicio.

**En el mapa de Odoo:** dibujar la pantalla de login completa, pero el único punto de
acceso (tab) es sobre la imagen. Al tocarla, redirige a la sección de Odoo donde se carga
la imagen con código `LOGIN` (mismo mecanismo genérico de imágenes por código que ya usa el
resto de la app — hoy solo existe este uso, pero el modelo está pensado para más de un
código a futuro, así que la pantalla de Odoo debería dejar elegir/mostrar el código
`LOGIN` puntualmente, no una lista larga).

### 3.2 Home / Inicio

Pantalla mixta con 4 bloques, de arriba hacia abajo:

1. **Header** (avatar + nombre + campana de notificaciones): avatar y nombre son dato
   propio de la sesión del cliente logueado, no son "contenido de app" administrable —
   **no se resaltan**. La **campana de notificaciones sí se resalta**: no trae contenido
   propio (las notificaciones las dispara el sistema/cron o un envío manual), pero por la
   regla 3 de §1 redirige a donde se administran/envían esas notificaciones — Móvil > App >
   Notificaciones > Envío de notificaciones masivas (`mobile.notificacion.masiva.wizard`,
   historial persistente, ver `wizard/notificacion_masiva_wizard.py`).
2. **Banner promocional (carrusel superior)**: **ya tiene su servicio definido** —
   `mobile.content.item` con `section=BANNER_HOME` (menú Móvil > App > Banners Home >
   **Banner Slide**, `action_mobile_content_item`). La sección viene fija y bloqueada en
   ese menú (no editable), justamente para que la app siempre la pida con ese código:
   `GET /v1/content-items?section=BANNER_HOME`. Queda resaltado/con tab en el mapa de Odoo
   apuntando a ese menú.

   Además, dentro del mismo bloque "Banners Home" existe otra puerta de entrada al mismo
   modelo/servicio: **Publicidad Full Screen** (`action_mobile_content_item_fullscreen`),
   con `section=FULL_SCREEN` fija — pensada para un anuncio a pantalla completa
   (interstitial) que se puede mostrar por encima del Home, por ejemplo al abrir la app.
   Ya tiene su propia pantalla dibujada en el mapa (📱 Publicidad Full Screen, justo
   después de Home) con el mismo tratamiento visual que el banner de Home — solo que un
   único anuncio a la vez, a pantalla completa, con su botón de cierre (✕) simulado.
   `GET /v1/content-items?section=FULL_SCREEN`.
3. **Accesos rápidos** (3 tarjetas: "Mi Vehículo", "Seguridad", "Tienda y Repuesto"): las
   3 imágenes de las tarjetas son diseño fijo empaquetado en la app, no vienen de ningún
   servicio — **no se resaltan como tarjetas**. Pero cada una **navega** a otra pantalla:
   - "Mi Vehículo" → misma pantalla que el tab "Vehículo" del menú inferior, ver §3.5.
   - "Seguridad" → módulo de Reportar incidente, backend externo, fuera de alcance (§1,
     regla 4) — no se resalta ni redirige a nada en Odoo.
   - "Tienda y Repuesto" → misma pantalla que el tab "Tienda", ver §3.3.
4. **Banner "Novedades" (inferior)**: la imagen del banner en sí es fija, pero **navega**
   a la pantalla completa de Novedades y Noticias (§3.4), que sí es 100% servicio — por
   la regla 3 de §1, este banner **sí se resalta**, redirigiendo al mismo destino que la
   pantalla de Novedades y Noticias.

Resumen visual de qué queda resaltado en Home: **solo el banner promocional superior y el
banner de Novedades inferior**; el header y las 3 tarjetas de accesos rápidos se dibujan
pero sin tab activo (salvo que su destino sea otra pantalla resaltable, como ya se explicó).

### 3.3 Tienda y Repuesto

Listado de productos (`GET /v1/catalog/products`) y detalle de producto
(`GET /v1/catalog/products/{id}`) — el 100% de lo que se ve (imágenes, precios,
descripciones, stock) sale de estos dos servicios. **Toda la pantalla es un único punto de
acceso**: un tab en cualquier parte redirige a la sección de catálogo/productos en Odoo.

### 3.4 Novedades y Noticias

Feed de promociones/avisos (`GET /v1/promotions`), paginado. El 100% del contenido sale de
este servicio. **Toda la pantalla es un único punto de acceso**, redirige a la sección de
Odoo donde se cargan las promociones/novedades.

### 3.5 Vehículo (nueva pantalla de drill-down en el mapa de Odoo)

Al tocar el tab "Vehículo" en el mapa (mismo destino que la tarjeta "Mi Vehículo" del
Home, §3.2), **no se redirige directo a Odoo** — se abre una pantalla nueva dentro del
propio mapa que dibuja el detalle de "Mi Vehículo" con sus secciones, igual que se hizo con
Home:

- **Banner "Beneficios para tu moto"** (arriba del todo): **resaltado**. Es la puerta de
  entrada a un sub-flujo de 2 pantallas, ambas 100% servicio (`GET /v1/beneficios`):
  1. **Hub de beneficios**: grilla de tarjetas por categoría.
  2. **Detalle de un beneficio**: galería de fotos/video, contactos de staff (WhatsApp por
     persona), qué cubre y recomendaciones.

  Cualquier punto de este sub-flujo redirige a la sección de Odoo donde se administran los
  beneficios (proveedor, título, imágenes, staff, cobertura, recomendaciones — ver el
  detalle de campos en `context/registrar-cliente-servicios-implementados.md`, sección 5).
- **Grilla de 6 accesos** (2 columnas × 3 filas):
  - Documentos, Papeletas, Mantenimiento, Ubicación GPS: se dibujan, pero **no se
    resaltan** — son datos transaccionales del vehículo puntual del cliente (SOAT vigente,
    historial de infracciones, historial técnico, posición GPS), no contenido de página
    editable de forma genérica.
  - **Cuenta autorizada**: **resaltada**. Sale del mismo servicio que trae la cuota del
    préstamo (`GET /v1/loans`, campo `paymentAccounts`) — redirige a donde en Odoo se
    cargan las cuentas de pago autorizadas del cliente.
  - **Atención al cliente**: **resaltada**. Mismo servicio (`GET /v1/loans`, campo
    `contacts`) — redirige a donde en Odoo se cargan los contactos de soporte del cliente.

---

## 4. Pendiente de confirmar con Odoo

- Nombre real del modelo/menú de imágenes por código (usado hoy solo por Login, código
  `LOGIN`) — para poder armar el link directo desde el mapa.
- Nombre real del modelo/menú de beneficios (proveedor, staff, cobertura, recomendaciones).
- Nombre real del modelo/menú de catálogo de productos y de promociones/novedades.
- Dónde van a vivir "Cuenta autorizada" y "Atención al cliente" del cliente (hoy viajan
  ambos dentro de la respuesta de `GET /v1/loans`, no son un modelo aparte necesariamente).
- Qué `section` va a usar el futuro banner del Home dentro de `mobile.content.item` (o si
  se optará por un mecanismo distinto) — mientras no se implemente, el punto de acceso del
  mapa puede quedar apuntando a un placeholder y actualizarse cuando se defina.

## 5. Fuera de alcance

Todo el módulo "Seguridad" (Reportar incidente: categorías, reportes, evidencia
multimedia) corre contra un backend propio, distinto del de Odoo (host y autenticación
separados) — no se representa en este mapa.
