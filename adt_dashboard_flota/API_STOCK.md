# API de Stock de Motos (app de ventas)

Módulo: `adt_dashboard_flota` · Versión: `15.0.1.1.0` · Odoo 15

Servicios para que la app de ventas consulte las motos disponibles para vender, cuáles tienen
placa lista para entrega inmediata, y los modelos, colores y años que hay en stock.

Usa las mismas reglas que el **Dashboard Stock** de Flota, así que la app y gerencia siempre ven
los mismos números.

---

## 1. Conceptos

| Término | Definición |
|---|---|
| **Stock** | Vehículo **activo** de Flota **sin conductor/dueño** asignado (`driver_id` vacío). |
| **Placa lista** | La placa tiene un valor real con al menos un número (ej. `1234-AB`). No cuentan textos como `S/P`, `EN TRAMITE` ni `PENDIENTE`. También cuenta si el trámite de placa está **Inscrito** y ya tiene número. |
| **En trámite** | No tiene placa lista, pero tiene un trámite de placa que no está **Tachado** (Borrador, Notaría, SUNARP, Observado, o Inscrito sin número de placa todavía). |
| **Sin placa** | No tiene placa lista ni trámite abierto. |

Códigos de `estado_placa`:

| Código | Texto | Significado para la vendedora |
|---|---|---|
| `lista` | Placa lista | Entrega inmediata |
| `tramite` | En trámite | Se puede vender; la entrega depende del trámite |
| `sin_placa` | Sin placa | Se puede vender; el trámite aún no empieza |

---

## 2. Convenciones

- Todos los endpoints son **JSON-RPC**: método `POST`, header `Content-Type: application/json`.
- Los parámetros van dentro de `params`:

  ```json
  { "jsonrpc": "2.0", "params": { ... } }
  ```

- La respuesta del servicio viene dentro de `result`:

  ```json
  { "jsonrpc": "2.0", "id": null, "result": { "ok": true, ... } }
  ```

- **Autenticación:** se usa la misma sesión de Odoo que los servicios del simulador
  (`/api/simulador/*`). Hay que enviar la cookie `session_id` que devuelve el login.
- Solo pueden consultar los **usuarios internos**. La vendedora **no** necesita permisos de Flota.
- Los textos de `marca`, `color` y `anio` vienen en **MAYÚSCULAS**.
- Si un dato no existe, viene como `null`.

### Login (si la app aún no tiene sesión)

```http
POST /web/session/authenticate
Content-Type: application/json

{ "jsonrpc": "2.0", "params": { "db": "<base>", "login": "<usuario>", "password": "<clave>" } }
```

La respuesta trae la cookie `session_id`. Envíala en todas las llamadas siguientes.

---

## 3. Endpoints

| Método | Ruta | Uso en la app |
|---|---|---|
| POST | [`/api/stock/resumen`](#31-post-apistockresumen) | Pantalla principal: totales, modelos y opciones de filtro |
| POST | [`/api/stock/vehiculos`](#32-post-apistockvehiculos) | Lista de motos con filtros y paginación |
| POST | [`/api/stock/vehiculos/detalle`](#33-post-apistockvehiculosdetalle) | Ficha de una moto; confirmar que sigue disponible |

### 3.1 `POST /api/stock/resumen`

Totales del stock, desglose por modelo (por color y por año) y las opciones para llenar los
filtros de la app.

**Parámetros:** ninguno.

```json
{ "jsonrpc": "2.0", "params": {} }
```

**Respuesta**

```json
{
  "ok": true,
  "totales": { "stock": 172, "placa_lista": 105, "en_tramite": 37, "sin_placa": 30 },
  "modelos": [
    {
      "modelo_id": 4,
      "modelo": "TVS APACHE RTR 160",
      "marca": "TVS",
      "imagen_url": "/web/image/fleet.vehicle.model/4/image_128",
      "stock": 73,
      "placa_lista": 41,
      "en_tramite": 15,
      "sin_placa": 17,
      "colores": [
        { "color": "NEGRO", "stock": 20, "placa_lista": 12, "en_tramite": 4, "sin_placa": 4 },
        { "color": null,    "stock": 3,  "placa_lista": 0,  "en_tramite": 1, "sin_placa": 2 }
      ],
      "anios": [
        { "anio": "2025", "stock": 23, "placa_lista": 15, "en_tramite": 5, "sin_placa": 3 },
        { "anio": "2024", "stock": 19, "placa_lista": 10, "en_tramite": 4, "sin_placa": 5 }
      ]
    }
  ],
  "filtros": {
    "modelos": [ { "id": 4, "nombre": "TVS APACHE RTR 160", "marca": "TVS" } ],
    "marcas": [ "TVS" ],
    "anios": [ "2025", "2024", "2023" ],
    "colores": [ "AZUL", "NEGRO", "ROJO" ],
    "estados_placa": [
      { "codigo": "lista",     "nombre": "Placa lista" },
      { "codigo": "tramite",   "nombre": "En trámite" },
      { "codigo": "sin_placa", "nombre": "Sin placa" }
    ]
  }
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `totales` | objeto | Conteo de todo el stock: `stock`, `placa_lista`, `en_tramite` y `sin_placa`. |
| `modelos[]` | lista | Un elemento por modelo con stock, ordenados de mayor a menor stock. |
| `modelos[].colores[]` | lista | Stock del modelo por color, de mayor a menor. `color: null` = sin color registrado. |
| `modelos[].anios[]` | lista | Stock del modelo por año, del más reciente al más antiguo. `anio: null` = sin año registrado. |
| `filtros` | objeto | Valores válidos para los filtros de `/api/stock/vehiculos`. |

---

### 3.2 `POST /api/stock/vehiculos`

Lista paginada de motos en stock. **Las motos con placa lista salen primero.** Después se ordena
por modelo, año (del más reciente al más antiguo) y color.

**Parámetros**

| Parámetro | Tipo | Obligatorio | Default | Descripción |
|---|---|---|---|---|
| `filtros` | objeto | No | `{}` | Ver tabla siguiente. |
| `limite` | entero | No | `20` | Motos por página (mínimo 1, máximo 100). |
| `offset` | entero | No | `0` | Cuántas motos saltar (para paginar). |

**Filtros** (todos opcionales y combinables)

| Filtro | Tipo | Ejemplo | Descripción |
|---|---|---|---|
| `modelo_id` | entero | `4` | ID del modelo (de `filtros.modelos[].id`). |
| `marca` | texto | `"TVS"` | Marca exacta (no distingue mayúsculas). |
| `anio` | texto o entero | `2025` | Año de modelo exacto. |
| `color` | texto | `"negro"` | Color exacto (no distingue mayúsculas). |
| `estado_placa` | texto | `"lista"` | `lista`, `tramite` o `sin_placa`. |
| `solo_placa_lista` | booleano | `true` | Atajo para `estado_placa: "lista"` (entrega inmediata). |
| `texto` | texto | `"1234"` | Búsqueda libre en placa, modelo, marca, color, año, chasis y motor. |

**Ejemplo:** motos negras 2025 con placa lista.

```json
{
  "jsonrpc": "2.0",
  "params": {
    "filtros": { "modelo_id": 4, "color": "negro", "anio": 2025, "solo_placa_lista": true },
    "limite": 20,
    "offset": 0
  }
}
```

**Respuesta**

```json
{
  "ok": true,
  "total": 12,
  "limite": 20,
  "offset": 0,
  "totales": { "stock": 12, "placa_lista": 12, "en_tramite": 0, "sin_placa": 0 },
  "vehiculos": [
    {
      "id": 118,
      "placa": "1234-AB",
      "placa_lista": true,
      "estado_placa": "lista",
      "estado_placa_texto": "Placa lista",
      "tramite_placa": null,
      "marca": "TVS",
      "modelo": "TVS APACHE RTR 160",
      "modelo_id": 4,
      "anio": "2025",
      "color": "NEGRO",
      "chasis": "9FLA1234567890123",
      "motor": "AE4K12345678",
      "tipo": "Motocicleta",
      "estado_flota": "Disponible",
      "imagen_url": "/web/image/fleet.vehicle.model/4/image_128"
    }
  ]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `total` | entero | Total de motos que cumplen los filtros, en todas las páginas. |
| `totales` | objeto | Conteo por estado de placa de las motos filtradas. |
| `vehiculos[]` | lista | Motos de la página actual. |

**Campos de cada vehículo**

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | entero | ID del vehículo en Odoo. Se usa en `/detalle`. |
| `placa` | texto \| null | Número de placa, o lo que haya registrado si aún no está lista. |
| `placa_lista` | booleano | `true` = entrega inmediata. |
| `estado_placa` | texto | `lista`, `tramite` o `sin_placa`. |
| `estado_placa_texto` | texto | Texto listo para mostrar. |
| `tramite_placa` | texto \| null | Estado del trámite de placa (ej. `SUNARP`, `Notaria`), si existe. |
| `marca`, `modelo` | texto | Marca y modelo. |
| `modelo_id` | entero \| null | ID del modelo. |
| `anio` | texto \| null | Año de modelo. |
| `color` | texto \| null | Color. |
| `chasis` | texto \| null | Número de chasis / VIN. |
| `motor` | texto \| null | Número de motor (si está registrado). |
| `tipo` | texto | Tipo de vehículo (ej. `Motocicleta`, `Mototaxi`). |
| `estado_flota` | texto | Estado en Flota (ej. `Disponible`, `Recolocada`). |
| `imagen_url` | texto \| null | Ruta relativa de la imagen del modelo. Anteponer el dominio de Odoo y enviar la cookie de sesión. |

**Paginación:** pide la siguiente página con `offset = offset + limite` mientras
`offset + limite < total`.

---

### 3.3 `POST /api/stock/vehiculos/detalle`

Ficha de una moto. Úsalo **antes de cerrar una venta** para confirmar que la moto sigue
disponible: otra vendedora pudo haberla asignado.

**Parámetros**

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `vehiculo_id` | entero | Sí | `id` obtenido de `/api/stock/vehiculos`. |

```json
{ "jsonrpc": "2.0", "params": { "vehiculo_id": 118 } }
```

**Respuesta**

```json
{
  "ok": true,
  "vehiculo": {
    "id": 118,
    "placa": "1234-AB",
    "placa_lista": true,
    "estado_placa": "lista",
    "estado_placa_texto": "Placa lista",
    "tramite_placa": null,
    "marca": "TVS",
    "modelo": "TVS APACHE RTR 160",
    "modelo_id": 4,
    "anio": "2025",
    "color": "NEGRO",
    "chasis": "9FLA1234567890123",
    "motor": "AE4K12345678",
    "tipo": "Motocicleta",
    "estado_flota": "Disponible",
    "imagen_url": "/web/image/fleet.vehicle.model/4/image_128",
    "disponible": true,
    "fecha_adquisicion": "2026-08-14",
    "kilometraje": 0.0,
    "unidad_kilometraje": "kilometers"
  }
}
```

Trae los mismos campos que la lista, más:

| Campo | Tipo | Descripción |
|---|---|---|
| `disponible` | booleano | `false` = la moto **ya tiene dueño**. No se debe ofrecer. |
| `fecha_adquisicion` | texto \| null | Fecha de compra (`YYYY-MM-DD`). |
| `kilometraje` | número | Último odómetro registrado. |
| `unidad_kilometraje` | texto | `kilometers` o `miles`. |

---

## 4. Errores

### Errores del servicio

Llegan con HTTP 200 dentro de `result`, con el mismo formato que el simulador:

```json
{ "ok": false, "codigo": "parametros_invalidos", "error": "estado_placa debe ser uno de: lista, tramite, sin_placa." }
```

| `codigo` | Cuándo ocurre |
|---|---|
| `parametros_invalidos` | Un filtro o parámetro tiene un tipo o valor inválido (ej. `limite: "abc"`, `estado_placa: "otra"`), `filtros` no es un objeto, o falta `vehiculo_id`. |
| `no_encontrado` | El `vehiculo_id` no existe o el vehículo está archivado. |
| `sin_permiso` | El usuario no es interno (por ejemplo, un usuario portal). |

### Sesión vencida o inexistente

Odoo responde con su error estándar de JSON-RPC (sin `result`):

```json
{ "jsonrpc": "2.0", "id": null, "error": { "code": 100, "message": "Odoo Session Expired", "data": { ... } } }
```

**Qué hacer:** volver a hacer login y repetir la llamada.

---

## 5. Flujo sugerido en la app

1. **Inicio de Stock:** llamar a `/api/stock/resumen`.
   - Mostrar los totales: disponibles y con placa lista.
   - Mostrar una tarjeta por modelo con su imagen, stock y cuántas tienen placa lista.
   - Llenar los filtros con `filtros`.
2. **Al tocar un modelo:** llamar a `/api/stock/vehiculos` con `{"modelo_id": X}`.
   - Mostrar chips de color y año (de `modelos[].colores` / `modelos[].anios`).
   - Añadir un switch **"Solo entrega inmediata"** que envía `solo_placa_lista: true`.
3. **Buscar:** enviar el texto en `filtros.texto`. Conviene esperar unos 300 ms después de que la
   vendedora deje de escribir antes de llamar.
4. **Al elegir una moto:** llamar a `/api/stock/vehiculos/detalle`.
   - Si `disponible` es `false`, avisar que la moto ya fue asignada y volver a cargar la lista.

---

## 6. Ejemplo con `curl`

```bash
# Login (guarda la cookie)
curl -s -c cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"db":"odoo","login":"vendedora@adt.pe","password":"****"}}' \
  https://<dominio-odoo>/web/session/authenticate

# Motos con placa lista
curl -s -b cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"filtros":{"solo_placa_lista":true},"limite":10}}' \
  https://<dominio-odoo>/api/stock/vehiculos
```

---

## 7. Notas

- **Precio y cuotas:** estos servicios **no** devuelven precio ni cuota. El catálogo del simulador
  (`/api/simulador/vehiculos`) no está enlazado con los modelos de Flota.
- **Datos al momento:** cada llamada consulta Odoo en ese instante, sin caché.
- **Código fuente:**
  - Controlador: `adt_dashboard_flota/controllers/stock_api.py`
  - Lógica: `adt_dashboard_flota/models/stock_service.py`
