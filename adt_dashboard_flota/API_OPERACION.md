# API de Operación de Motos (solo lectura)

Módulo: `adt_dashboard_flota` · Odoo 15 · Depende de `adt_tracking_moto` y `adt_tramite_placa`

Servicios **de solo lectura** para que la app consulte el **stock** y **en qué punto del proceso
está cada moto**:

- **Logística (fibra):** recojo en el distribuidor → almacén de la empresa → fibra (en un taller) → lista para asignar.
- **Trámite de placa:** pendiente → en trámite ⇄ observado → finalizado.

Usa las mismas reglas que el **Dashboard** de *Operación de motos* en Odoo, así que la app y
gerencia siempre ven los mismos números. Ningún endpoint modifica datos.

> La API de stock anterior (`/api/stock/*`, ver `API_STOCK.md`) sigue funcionando sin cambios
> de formato. Esta API es complementaria.

---

## 1. Conceptos

| Término | Definición |
|---|---|
| **Stock / disponible** | Vehículo **activo** de Flota **sin dueño** asignado. |
| **Con placa** | Placa real en el vehículo (con al menos un número; no cuentan `S/P`, `EN TRAMITE`, etc.) o trámite de placa **Finalizado**. |
| **Lista para entregar** | Disponible, con placa y con la logística terminada (fibra lista). |
| **Demorada / en riesgo** | Lleva en su etapa más que el tiempo objetivo (SLA) configurado o, si no hay SLA, más que el 85% de los casos de los últimos 90 días. |
| **Fuera del flujo** | Vehículo que nunca entró al tracking (no tiene `logistica`). |

### Códigos

**Etapa logística** (`logistica.etapa`) — el nombre visible (`etapa_texto`) lo define cada empresa:

| Código | Paso | Significado |
|---|---|---|
| `recojo` | 1 | Recojo en el almacén del distribuidor |
| `almacen` | 2 | En el almacén de la empresa, sin armar |
| `fibra` | 3 | En un taller poniéndole la fibra (`taller_fibra`) |
| `listo` | 4 | De vuelta con fibra: lista para asignar |

**Estado de placa** (`placa_proceso.estado`):

| Código | Significado |
|---|---|
| `sin_tramite` | La moto no tiene trámite de placa |
| `pendiente` | Trámite creado, aún no iniciado |
| `en_tramite` | Trámite en curso |
| `observado` | Detenido por una observación (motivo en `observacion`) |
| `finalizado` | Placa obtenida (incluye los trámites pasados a Historial) |

**Estado general** (`estado_general`):

| Código | Significado |
|---|---|
| `en_proceso` | Sin dueño y con la logística sin terminar |
| `listo_asignar` | Sin dueño y con la logística terminada |
| `asignado_sin_placa` | Ya tiene dueño pero aún no tiene placa |
| `asignado_con_placa` | Con dueño y con placa, sin entregar |
| `entregado` | Entregada al cliente y con placa |
| `fuera_del_flujo` | No tiene tracking |

---

## 2. Convenciones

- Todos los endpoints son **JSON-RPC**: método `POST`, header `Content-Type: application/json`.
- Los parámetros van dentro de `params`: `{ "jsonrpc": "2.0", "params": { ... } }`.
- La respuesta viene dentro de `result`: `{ "jsonrpc": "2.0", "id": null, "result": { "ok": true, ... } }`.
- **Autenticación:** sesión de Odoo (la misma que `/api/stock/*` y `/api/simulador/*`). Enviar la
  cookie `session_id` que devuelve el login.
- Solo pueden consultar **usuarios internos**. No se necesitan permisos de Flota.
- **Fechas en UTC**, formato `YYYY-MM-DD HH:MM:SS` (la fecha de entrega: `YYYY-MM-DD`).
  Convertir a hora de Perú (UTC−5) para mostrar.
- Si un dato no existe, viene como `null`. Días con un decimal (`2.4`).
- Cada llamada consulta Odoo en ese instante, sin caché.

### Login

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
| POST | `/api/operacion/resumen` | Pantalla principal: totales, combinaciones, carga por etapa, alertas |
| POST | `/api/operacion/motos` | Lista de motos con su proceso, filtros y paginación |
| POST | `/api/operacion/motos/detalle` | Ficha de una moto con su línea de tiempo |

### 3.1 `POST /api/operacion/resumen`

**Parámetros:** ninguno.

```json
{
  "ok": true,
  "generado": "2026-10-11 18:13:40",
  "totales": { "flota": 60, "con_placa": 34, "stock": 23, "listas": 1, "completo": 33, "alertas": 18 },
  "combinaciones": {
    "stock_sin_placa":  { "cantidad": 22, "por_estado_placa": { "pendiente": 11, "en_tramite": 7, "observado": 4 } },
    "stock_con_placa":  { "cantidad": 1,  "por_estado_placa": {} },
    "duenio_sin_placa": { "cantidad": 4,  "por_estado_placa": { "en_tramite": 3, "observado": 1 } },
    "duenio_con_placa": { "cantidad": 33, "por_estado_placa": {} }
  },
  "logistica": [
    { "etapa": "recojo",  "etapa_texto": "Gambeta",        "cantidad": 4, "en_riesgo": 2, "mediana_dias": 2.4 },
    { "etapa": "almacen", "etapa_texto": "Base",           "cantidad": 8, "en_riesgo": 1, "mediana_dias": 2.4 },
    { "etapa": "fibra",   "etapa_texto": "Fibra",          "cantidad": 7, "en_riesgo": 2, "mediana_dias": 2.3 },
    { "etapa": "listo",   "etapa_texto": "Base con fibra", "cantidad": 6, "en_riesgo": 1, "mediana_dias": 3.9 }
  ],
  "placa": [
    { "estado": "pendiente",  "estado_texto": "Pendiente",  "cantidad": 11, "en_riesgo": 9, "mediana_dias": 45.5 },
    { "estado": "en_tramite", "estado_texto": "En trámite", "cantidad": 10, "en_riesgo": 0, "mediana_dias": 12.0 },
    { "estado": "observado",  "estado_texto": "Observado",  "cantidad": 5,  "en_riesgo": 0, "mediana_dias": 3.0 },
    { "estado": "finalizado", "estado_texto": "Finalizado", "cantidad": 31, "en_riesgo": 0, "mediana_dias": null }
  ],
  "talleres_fibra": [
    { "taller": "Fibra VES", "en_fibra": 3, "en_riesgo": 1, "mediana_historica_dias": 7.8 }
  ],
  "alertas": [
    { "codigo": "placa_observada", "severidad": "critico", "titulo": "Trámites observados",
      "descripcion": "El trámite está detenido hasta levantar la observación.", "detalle": "máx. 8 d", "cantidad": 5 }
  ]
}
```

- `totales.stock` = sin dueño · `listas` = sin dueño, con placa y con la logística terminada ·
  `completo` = con dueño y con placa · `alertas` = motos que aparecen en al menos una alerta.
- `en_riesgo`: motos que superan el tiempo objetivo (SLA) de la etapa o, si no hay SLA, el tiempo
  en que se resolvió el 85% de los casos de los últimos 90 días.
- `severidad`: `critico`, `alto` o `medio`. Solo vienen las alertas con `cantidad` mayor que 0.

### 3.2 `POST /api/operacion/motos`

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `alcance` | texto | `"stock"` | `stock` (sin dueño) o `flota` (todas las activas). |
| `filtros` | objeto | `{}` | Ver tabla siguiente. |
| `limite` | número | `20` | Máximo `100`. |
| `offset` | número | `0` | Para paginar. |

| Filtro | Tipo | Valores |
|---|---|---|
| `etapa` | texto | `recojo`, `almacen`, `fibra`, `listo` |
| `estado_placa` | texto | `sin_tramite`, `pendiente`, `en_tramite`, `observado`, `finalizado` |
| `demorado` | booleano | `true`: solo las demoradas en su etapa |
| `con_duenio` | booleano | `true` / `false` (útil con `alcance: "flota"`) |
| `lista_para_entregar` | booleano | `true`: sin dueño, con placa y fibra lista |
| `modelo_id` | número | ID del modelo |
| `texto` | texto | Busca en placa, chasis, motor, modelo, marca, color, referencia del tracking y número de placa del trámite |

Orden: primero las listas para entregar, luego las más avanzadas en la logística.

```json
{ "jsonrpc": "2.0", "params": { "alcance": "stock", "filtros": { "etapa": "fibra" }, "limite": 20 } }
```

**Respuesta** (`motos[]`):

```json
{
  "ok": true, "alcance": "stock", "total": 1, "limite": 20, "offset": 0,
  "motos": [{
    "id": 6, "placa": "ABC1234", "chasis": "11111111", "motor": "12312312",
    "marca": "Audi", "modelo": "Audi/A1", "modelo_id": 13, "anio": "2026", "color": "AZUL",
    "imagen_url": "/web/image/fleet.vehicle.model/13/image_128",
    "disponible": true, "con_placa": true, "lista_para_entregar": true,
    "estado_general": "listo_asignar", "estado_general_texto": "Listo para asignar",
    "tracking_ref": "TRK/2026/00001",
    "logistica": {
      "etapa": "listo", "etapa_texto": "Base con fibra", "paso": 4, "total_pasos": 4,
      "desde": "2026-10-10 22:11:04", "dias_en_etapa": 0.8, "demorado": false, "taller_fibra": "Fibra PP",
      "fechas": { "recojo": "2026-10-10 21:43:32", "ingreso_almacen": "2026-10-10 21:44:16",
                  "envio_fibra": "2026-10-10 22:10:52", "listo": "2026-10-10 22:11:04",
                  "asignacion": null, "entrega": null }
    },
    "placa_proceso": {
      "estado": "finalizado", "estado_texto": "Finalizado", "numero": "ABC1234",
      "inicio": "2026-10-10 22:09:34", "fin": "2026-10-10 22:10:28",
      "dias_tramite": 0.0, "dias_sin_iniciar": 0.0, "veces_observado": 0, "observacion": null
    }
  }]
}
```

| Campo | Descripción |
|---|---|
| `estado_general` | `en_proceso`, `listo_asignar`, `asignado_sin_placa`, `asignado_con_placa`, `entregado`, o `fuera_del_flujo` (la moto no tiene tracking). |
| `logistica` | `null` si la moto no tiene tracking. `paso` va de 1 a 4. `dias_en_etapa` y `demorado` usan la misma regla que el dashboard. |
| `placa_proceso.estado` | `sin_tramite`, `pendiente`, `en_tramite`, `observado` o `finalizado` (un trámite en Historial se informa como `finalizado`). |
| `placa_proceso.observacion` | Motivo, solo cuando el estado es `observado`. |

### 3.3 `POST /api/operacion/motos/detalle`

**Parámetros:** `vehiculo_id` (obligatorio). Devuelve `moto` con los mismos campos que 3.2 más
`linea_de_tiempo`: cada cambio de etapa logística, de estado de placa e hitos (asignación, entrega).

```json
{
  "ok": true,
  "moto": {
    "id": 6, "...": "...",
    "linea_de_tiempo": [
      { "flujo": "logistica", "flujo_texto": "Logística", "desde": null, "hacia": "Gambeta", "codigo": "recojo",
        "taller_fibra": null, "inicio": "2026-10-10 21:43:32", "fin": "2026-10-10 21:44:16",
        "duracion_dias": 0.0, "nota": null },
      { "flujo": "placa", "flujo_texto": "Placa", "desde": null, "hacia": "Pendiente", "codigo": "pendiente",
        "taller_fibra": null, "inicio": "2026-10-10 21:43:32", "fin": "2026-10-10 22:09:34",
        "duracion_dias": 0.02, "nota": null }
    ]
  }
}
```

`flujo`: `logistica`, `placa` o `hito`. Si la etapa sigue en curso, `fin` y `duracion_dias` vienen en `null`.
La entrada que pasa a "Observado" trae el motivo en `nota`.

---

## 4. Errores

### Errores del servicio

Llegan con HTTP 200 dentro de `result`:

```json
{ "ok": false, "codigo": "parametros_invalidos", "error": "etapa debe ser uno de: recojo, almacen, fibra, listo." }
```

| `codigo` | Cuándo ocurre |
|---|---|
| `parametros_invalidos` | `alcance`, `etapa` o `estado_placa` con valor inválido; `demorado`, `con_duenio` o `lista_para_entregar` que no son `true`/`false`; `limite`/`offset`/`modelo_id` no numéricos; `filtros` que no es un objeto; falta `vehiculo_id`. |
| `no_encontrado` | El `vehiculo_id` no existe o el vehículo está archivado. |
| `sin_permiso` | El usuario no es interno (por ejemplo, un usuario portal). |

### Sesión vencida o inexistente

Odoo responde con su error estándar de JSON-RPC (sin `result`):

```json
{ "jsonrpc": "2.0", "id": null, "error": { "code": 100, "message": "Odoo Session Expired", "data": { "...": "..." } } }
```

**Qué hacer:** volver a hacer login y repetir la llamada.

---

## 5. Tipos (TypeScript)

```ts
type Etapa = 'recojo' | 'almacen' | 'fibra' | 'listo';
type EstadoPlaca = 'sin_tramite' | 'pendiente' | 'en_tramite' | 'observado' | 'finalizado';
type EstadoGeneral = 'en_proceso' | 'listo_asignar' | 'asignado_sin_placa'
  | 'asignado_con_placa' | 'entregado' | 'fuera_del_flujo';
type Severidad = 'critico' | 'alto' | 'medio';

interface Logistica {
  etapa: Etapa;
  etapa_texto: string;
  paso: 1 | 2 | 3 | 4;
  total_pasos: 4;
  desde: string | null;            // UTC
  dias_en_etapa: number;
  demorado: boolean;
  taller_fibra: string | null;
  fechas: {
    recojo: string | null;
    ingreso_almacen: string | null;
    envio_fibra: string | null;
    listo: string | null;
    asignacion: string | null;
    entrega: string | null;        // YYYY-MM-DD
  };
}

interface PlacaProceso {
  estado: EstadoPlaca;
  estado_texto: string;
  numero: string | null;
  inicio: string | null;
  fin: string | null;
  dias_tramite: number;
  dias_sin_iniciar: number;
  veces_observado: number;
  observacion: string | null;      // solo si estado === 'observado'
}

interface Moto {
  id: number;
  placa: string | null;
  chasis: string | null;
  motor: string | null;
  marca: string;
  modelo: string;
  modelo_id: number | null;
  anio: string | null;
  color: string | null;
  imagen_url: string | null;
  disponible: boolean;
  con_placa: boolean;
  lista_para_entregar: boolean;
  estado_general: EstadoGeneral;
  estado_general_texto: string;
  tracking_ref: string | null;
  logistica: Logistica | null;     // null si está fuera del flujo
  placa_proceso: PlacaProceso;
}

interface EventoLinea {
  flujo: 'logistica' | 'placa' | 'hito';
  flujo_texto: string;
  desde: string | null;
  hacia: string | null;
  codigo: string | null;
  taller_fibra: string | null;
  inicio: string;
  fin: string | null;              // null si sigue en curso
  duracion_dias: number | null;
  nota: string | null;
}

interface MotoDetalle extends Moto { linea_de_tiempo: EventoLinea[]; }

interface Resumen {
  generado: string;
  totales: { flota: number; con_placa: number; stock: number; listas: number; completo: number; alertas: number };
  combinaciones: Record<'stock_sin_placa' | 'stock_con_placa' | 'duenio_sin_placa' | 'duenio_con_placa',
    { cantidad: number; por_estado_placa: Partial<Record<EstadoPlaca, number>> }>;
  logistica: { etapa: Etapa; etapa_texto: string; cantidad: number; en_riesgo: number; mediana_dias: number | null }[];
  placa: { estado: EstadoPlaca; estado_texto: string; cantidad: number; en_riesgo: number; mediana_dias: number | null }[];
  talleres_fibra: { taller: string; en_fibra: number; en_riesgo: number; mediana_historica_dias: number | null }[];
  alertas: { codigo: string; severidad: Severidad; titulo: string; descripcion: string; detalle: string | null; cantidad: number }[];
}

type Respuesta<T> = ({ ok: true } & T) | { ok: false; codigo: string; error: string };
```

---

## 6. Flujo sugerido en la app

1. **Inicio:** `/api/operacion/resumen`.
   - Tarjetas con `totales` (stock, listas para entregar, con placa).
   - Barra de 4 pasos con `logistica[]` (cantidad por etapa y en riesgo).
   - Avisos con `alertas[]`, usando `severidad` para el color, siempre con ícono y texto.
2. **Al tocar una etapa o estado:** `/api/operacion/motos` con `filtros.etapa` o `filtros.estado_placa`.
3. **"Entrega inmediata":** `/api/operacion/motos` con `filtros.lista_para_entregar: true`.
4. **Buscar:** `filtros.texto`. Esperar unos 300 ms después de que el usuario deje de escribir.
5. **Ficha de la moto:** `/api/operacion/motos/detalle` y dibujar `linea_de_tiempo` como un timeline.
   - Si `disponible` es `false`, avisar que ya fue asignada.
6. **Paginación:** usar `total`, `limite` (máx. 100) y `offset`.

---

## 7. Ejemplos con `curl`

```bash
# Login (guarda la cookie)
curl -s -c cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"db":"<base>","login":"<usuario>","password":"****"}}' \
  https://<dominio-odoo>/web/session/authenticate

# Resumen
curl -s -b cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{}}' \
  https://<dominio-odoo>/api/operacion/resumen

# Motos del stock que están en fibra
curl -s -b cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"alcance":"stock","filtros":{"etapa":"fibra"},"limite":20}}' \
  https://<dominio-odoo>/api/operacion/motos

# Toda la flota: motos asignadas que aún no tienen placa
curl -s -b cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"alcance":"flota","filtros":{"con_duenio":true,"estado_placa":"en_tramite"}}}' \
  https://<dominio-odoo>/api/operacion/motos

# Ficha con línea de tiempo
curl -s -b cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"vehiculo_id":6}}' \
  https://<dominio-odoo>/api/operacion/motos/detalle
```

---

## 8. Código fuente

- Controlador: `adt_dashboard_flota/controllers/stock_api.py` (rutas `/api/operacion/*`)
- Lógica: `adt_dashboard_flota/models/operacion_api.py`
- Pruebas: `adt_dashboard_flota/tests/test_operacion_api.py`
