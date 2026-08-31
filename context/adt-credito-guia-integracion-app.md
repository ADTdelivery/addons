# Guía de integración — Crédito (`adt_credito`) en la app móvil

Especificación funcional para el equipo de la app. Objetivo: que un cliente pueda ver sus
contratos de crédito (productos comprados a plazos), su cronograma de pagos y simular una
compra a crédito antes de confirmarla, todo contra el mismo backend Odoo que ya consume el
resto de la app.

Este documento no reemplaza al [mapa de pantallas](./mapa-pantallas-servicios-odoo.md), es
el detalle de los endpoints nuevos que expone el módulo `adt_credito`.

---

## 1. Qué es `adt_credito`

Módulo Odoo independiente (no depende de `adt_comercial`) que permite vender **cualquier
producto** marcado como "financiable" en cuotas fijas (sin interés), con cronograma
automático, mora y refinanciamiento. Cada contrato financia **un solo producto** (no hay
carritos con varios productos por contrato). Vive junto a `adt_comercial` en el mismo servidor, y
para exponer sus datos a la app reutiliza exactamente el mismo esquema de autenticación
que ya usan los demás endpoints `/v1/...`: header `Authorization: Bearer <token>`, token
emitido por el login existente y validado contra el modelo `mobile.token` de
`adt_comercial`.

> Si algún día `adt_credito` se instalara en un servidor sin `adt_comercial`, estos
> endpoints devuelven `501 MOBILE_AUTH_NOT_AVAILABLE` en vez de fallar — pero en el
> despliegue de ADT ambos módulos están instalados juntos, así que en la práctica esto no
> aplica.

---

## 2. Autenticación

Igual que el resto de la app: la pantalla de login ya obtiene un token vía el endpoint de
`adt_comercial` (`/v1/auth/...`). Ese mismo token se reenvía en cada llamada:

```
Authorization: Bearer <token>
```

Errores comunes:

| HTTP | code | Motivo |
|---|---|---|
| 401 | `TOKEN_MISSING` | No se envió el header `Authorization` |
| 401 | `TOKEN_INVALID` | Token inexistente o revocado |
| 401 | `TOKEN_EXPIRED` | Token vencido |
| 403 | `TOKEN_WITHOUT_PARTNER` | El token no tiene cliente asociado |
| 501 | `MOBILE_AUTH_NOT_AVAILABLE` | `adt_comercial` no está instalado en este servidor |

---

## 3. Endpoints

### 3.1 `GET /v1/credit/contracts`

Lista los contratos de crédito del cliente autenticado (todos los estados).

**Respuesta 200**
```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": [
    {
      "id": 12,
      "referencia": "CR00012",
      "estado": "activo",
      "semaforo": "verde",
      "productId": 45,
      "productName": "Batería 12V",
      "frecuencia": "mensual",
      "numeroCuotas": 12,
      "montoTotal": 1200.0,
      "enganche": 200.0,
      "montoFinanciado": 1000.0,
      "montoCuota": 83.33,
      "fechaInicio": "2026-09-01",
      "saldoPendiente": 833.34,
      "moraTotal": 0.0,
      "cuotasVencidas": 0,
      "cuotasPagadas": 2,
      "pctPagado": 16.67,
      "pctAtraso": 0.0,
      "moneda": "PEN"
    }
  ],
  "meta": { "timestamp": "2026-08-30T15:00:00Z", "requestId": "..." }
}
```

`estado` (enum): `borrador`, `activo`, `en_mora`, `pagado`, `refinanciado`, `cancelado`.
`frecuencia` (enum): `diario`, `semanal`, `quincenal`, `mensual`.
`semaforo` (enum): `verde` (al día), `amarillo` (cuotas vencidas pero aún sin mora — dentro
de los días de gracia), `rojo` (ya se le está cobrando mora). Es el campo pensado
específicamente para pintar el indicador visual en la tarjeta del crédito.
`pctPagado` / `pctAtraso`: 0–100, para las barras de progreso — `pctPagado` es cuánto del
monto financiado ya se pagó, `pctAtraso` es qué porcentaje de las cuotas totales están
vencidas.

Pantalla sugerida: dentro de "Mi Vehículo" o una sección nueva "Mis créditos" en el menú
inferior, listando estas tarjetas — usar `semaforo` para el color del punto/badge y
`pctPagado`/`pctAtraso` para las barras de progreso, en vez de recalcular esta lógica en
la app.

### 3.2 `GET /v1/credit/contracts/<id>`

Detalle de un contrato del cliente autenticado (404 si el contrato no existe o no le
pertenece), incluyendo el cronograma completo.

**Respuesta 200** — mismos campos que el listado, más:
```json
{
  "...": "...",
  "cronograma": [
    {
      "id": 101,
      "numeroCuota": 1,
      "fechaVencimiento": "2026-09-01",
      "monto": 83.33,
      "montoPagado": 83.33,
      "saldo": 0.0,
      "estado": "pagada",
      "diasMora": 0,
      "moraMonto": 0.0,
      "moraPagada": 0.0,
      "moraPendiente": 0.0
    },
    {
      "id": 102,
      "numeroCuota": 2,
      "fechaVencimiento": "2026-10-01",
      "monto": 83.33,
      "montoPagado": 0.0,
      "saldo": 83.33,
      "estado": "vencida",
      "diasMora": 5,
      "moraMonto": 5.0,
      "moraPagada": 0.0,
      "moraPendiente": 5.0
    }
  ]
}
```

`estado` de cuota (enum): `pendiente`, `parcial`, `pagada`, `vencida`, `condonada`.

Pantalla sugerida: detalle de "Mi crédito" con la tabla de cuotas — usar `moraPendiente`
(no `moraMonto`) para mostrar cuánto le falta pagar de mora, ya que `moraMonto` es el total
acumulado a la fecha y `moraPagada` puede ya cubrir parte de él.

### 3.3 `POST /v1/credit/simulate`

Simula un cronograma **sin crear ningún contrato** — para la pantalla de "Tienda y
Repuesto" cuando el cliente elige "Comprar a crédito" sobre un producto y quiere ver antes
las cuotas.

**Request**
```json
{
  "productId": 45,
  "cantidad": 1,
  "enganche": 200.0,
  "frecuencia": "mensual",
  "numeroCuotas": 12
}
```

**Respuesta 200**
```json
{
  "success": true,
  "data": {
    "productId": 45,
    "productName": "Batería 12V",
    "montoTotal": 1200.0,
    "enganche": 200.0,
    "montoFinanciado": 1000.0,
    "frecuencia": "mensual",
    "numeroCuotas": 12,
    "montoCuota": 83.33,
    "cronograma": [
      { "numeroCuota": 1, "fechaVencimiento": "2026-08-30", "monto": 83.33 },
      { "numeroCuota": 2, "fechaVencimiento": "2026-09-30", "monto": 83.33 }
    ]
  }
}
```

Errores: `422 VALIDATION_ERROR` (falta `productId`, frecuencia inválida, `numeroCuotas` ≤ 0,
o el enganche es mayor o igual al monto total) y `404 PRODUCT_NOT_FINANCIABLE` (el producto
no existe o no está marcado como financiable en Odoo).

> Este endpoint **no crea el contrato**. La creación real del contrato (después de que el
> cliente confirma la simulación) todavía se hace desde Odoo por un asesor comercial —
> si más adelante se quiere que el cliente confirme la compra a crédito directo desde la
> app, ese es un endpoint nuevo a definir (`POST /v1/credit/contracts`), fuera del alcance
> de esta primera versión.

---

## 4. Dónde se administra esto en Odoo

Menú **Crédito** (nuevo, junto a Comercial; "Contratos" es la primera pantalla al entrar):

| Submenú | Para qué |
|---|---|
| Contratos | Crear/confirmar contratos, ver cronograma y pagos, registrar pago, refinanciar |
| Cobranza | Todas las cuotas de todos los contratos, filtrables por vencidas/pendientes |
| Pagos | Historial de pagos registrados (cuota o mora) |
| Productos financiables | Filtro rápido de `product.template` con `es_financiable = True` |
| Configuración | Tipo de mora (fijo/% diario), valor, días de gracia, tope máximo |
| Dashboard | KPIs de cartera, mora, recaudo y ganancia por producto (pestaña aparte, fuera del layout de Odoo) — al final del menú |

Para que un producto aparezca disponible a crédito (y por lo tanto sea válido en
`POST /v1/credit/simulate`), un administrador debe marcar `Disponible a crédito` en la
pestaña "Ventas" de la ficha del producto — al marcarlo, además se crea automáticamente un
submenú con el nombre de ese producto dentro de Contratos/Cobranza/Pagos, para no mezclar
la cartera de productos distintos en una sola lista.

Al elegir el cliente en un contrato, Odoo muestra un panel con su historial: créditos
activos, puntualidad de pago, y una validación cruzada contra `adt.comercial.cuentas`
(préstamos de vehículo) si ese módulo está instalado — información hoy solo visible en
Odoo, no expuesta todavía por la API (ver pendientes).

El cronograma también se puede imprimir en PDF desde Odoo (botón Imprimir del contrato) —
no está expuesto todavía como descarga desde la app.

---

## 5. Pendiente / fuera de esta versión

- Endpoint para que el cliente **confirme la compra a crédito** desde la app (hoy solo
  simula).
- Descarga del PDF de cronograma desde la app.
- Notificaciones push de cuotas próximas a vencer (la app ya tiene el mecanismo genérico de
  `mobile.notification` en `adt_comercial`; conectarlo con el cron de mora de
  `adt_credito` es un paso natural a futuro).
