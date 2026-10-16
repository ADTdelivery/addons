# App de gerencia · Resumen (guía para el front)

Servicios para la pantalla **Resumen** de la app de gerencia: 14 indicadores en 4 secciones.
Cada indicador se puede ver por financiera y abre su propio detalle.

- Base: `http://<servidor>/api/gerencia/v1` (hoy: `http://192.168.100.97:8069/api/gerencia/v1`)
- Solo lectura. Todas las respuestas son JSON en UTF-8.
- Montos en soles (PEN) con dos decimales. Fechas `YYYY-MM-DD` (hora de Lima).

---

## 1. Acceso

Solo entran los usuarios de Odoo con el grupo **Acceso a la app de gerencia**. Hay dos formas de
autenticarse; elijan una.

### Opción A: sesión de Odoo (si la app ya usa el login estándar)

```http
POST /web/session/authenticate
Content-Type: application/json

{"jsonrpc": "2.0", "params": {"db": "<base>", "login": "usuario", "password": "clave"}}
```

- La respuesta trae `result.moduloAdmin`: `true` si el usuario puede ver la sección de gerencia.
  Si es `false`, no muestren el Resumen.
- Odoo devuelve la cookie `session_id`. Envíenla en cada llamada a `/api/gerencia/v1/...`.
- No confundan `moduloAdmin` con `is_admin`: `is_admin` indica administrador del sistema, no permiso de gerencia.

### Opción B: token (recomendada para la app móvil)

```http
POST /api/gerencia/v1/auth/login
Content-Type: application/json

{"login": "usuario", "password": "clave", "dispositivo": "iPhone de Ana", "app_version": "1.0.0"}
```

```json
{"ok": true, "data": {"token": "xxxx", "tipo": "Bearer", "expira": "2026-11-15 14:00:00",
  "usuario": {"id": 12, "nombre": "Ana Pérez", "login": "ana@adt.pe"}}}
```

- En todas las demás llamadas, enviar el header `Authorization: Bearer <token>`.
- El token vale 30 días. Para cerrar sesión: `POST /api/gerencia/v1/auth/logout` con el mismo header.
- Si se envía un `Authorization: Bearer`, se usa el token y se ignora la cookie.

### Permisos

El permiso se revisa en cada llamada. Si a un usuario le quitan el grupo o le revocan la sesión,
la siguiente llamada devuelve **401**. Entonces la app debe volver al login.

---

## 2. Formato de respuesta y errores

```json
{"ok": true,  "data": { ... }, "meta": { ... }}
{"ok": false, "error": {"codigo": "NO_AUTORIZADO", "mensaje": "Texto listo para mostrar"}}
```

| HTTP | `error.codigo` | Qué hacer en el front |
|---|---|---|
| 400 | `PARAMETRO_INVALIDO`, `JSON_INVALIDO`, `DATOS_INCOMPLETOS` | Error de programación: revisar los parámetros. `mensaje` indica las opciones válidas. |
| 401 | `CREDENCIALES_INVALIDAS` | Login: usuario o clave incorrectos. |
| 401 | `NO_AUTORIZADO` | Sesión vencida, revocada o sin permiso: ir al login. |
| 403 | `SIN_PERMISO` | Login: el usuario no tiene acceso a la app de gerencia. |
| 500 | `ERROR_INTERNO` | Mostrar `mensaje` y ofrecer reintentar. |

---

## 3. GET /resumen

```http
GET /api/gerencia/v1/resumen
GET /api/gerencia/v1/resumen?financiera_id=6
```

| Parámetro | Tipo | Descripción |
|---|---|---|
| `financiera_id` | entero, opcional | Muestra solo esa financiera. `0` = "Sin financiera". Si no se envía, se muestra toda la empresa. |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "fecha_corte": "2026-10-16",
    "mes": "2026-10",
    "moneda": "PEN",
    "simbolo": "S/",
    "filtro_financiera_id": null,
    "financieras": [
      {"id": 0, "nombre": "Sin financiera"},
      {"id": 6, "nombre": "Financiera X"}
    ],
    "secciones": [
      {
        "clave": "dinero",
        "nombre": "Dinero",
        "indicadores": [
          {
            "clave": "deuda_vencida",
            "nombre": "Deuda vencida",
            "descripcion": "Cuotas cuya fecha ya pasó y siguen sin pagar.",
            "tipo": "soles",
            "disponible": true,
            "valor": 252.0,
            "secundario": {"nombre": "Cuentas", "tipo": "entero", "valor": 1},
            "desglose": [
              {"clave": "1_30",   "nombre": "1 a 30 días",    "valor": 252.0},
              {"clave": "31_60",  "nombre": "31 a 60 días",   "valor": 0.0},
              {"clave": "61_90",  "nombre": "61 a 90 días",   "valor": 0.0},
              {"clave": "91_mas", "nombre": "Más de 90 días", "valor": 0.0}
            ],
            "por_financiera": [
              {"financiera_id": 6, "nombre": "Financiera X", "valor": 252.0}
            ]
          }
        ]
      }
    ]
  }
}
```

### Campos de cada indicador

| Campo | Tipo | Siempre | Descripción |
|---|---|---|---|
| `clave` | string | sí | Identificador; se usa para pedir el detalle. |
| `nombre` | string | sí | Título de la tarjeta. |
| `descripcion` | string | sí | Texto de ayuda (tooltip o "i"). |
| `tipo` | `soles` \| `entero` | sí | Cómo formatear `valor`: `soles` → `S/ 1,492.00`; `entero` → `14`. |
| `disponible` | bool | sí | `false` si el módulo de origen no está instalado en el servidor. |
| `valor` | number \| null | sí | Cifra principal. Es `null` si `disponible` es `false`. |
| `mensaje` | string | solo si `disponible` es `false` | Motivo. Mostrar la tarjeta en gris con "No disponible". |
| `secundario` | objeto | no | Segunda cifra para mostrar debajo de la principal (`nombre`, `tipo`, `valor`). |
| `desglose` | lista | no | Reparto por estado, tramo o etapa (`clave`, `nombre`, `valor`). Cada `clave` sirve como `filtro` en el detalle. |
| `por_financiera` | lista | sí si está disponible | Misma cifra separada por financiera, de mayor a menor (`financiera_id`, `nombre`, `valor`). Si está vacía, no hay datos. |

**Reglas para el front**
- Rendericen las secciones y los indicadores en el orden en que llegan.
- Los textos (`nombre`, `descripcion`, nombres del desglose) ya vienen listos para mostrar.
- El selector de financiera se arma con `data.financieras`. Al elegir una, vuelvan a llamar a `/resumen?financiera_id=<id>`.
- Para ver la empresa completa repartida por financiera, usen `por_financiera` de cada indicador, sin filtrar.

---

## 4. Catálogo de indicadores

| Sección | `clave` | Nombre | `tipo` | `secundario` | `desglose` (filtro) |
|---|---|---|---|---|---|
| dinero | `nos_deben_total` | Nos deben los clientes | soles | Vencido (soles) | — |
| dinero | `deuda_vencida` | Deuda vencida | soles | Cuentas (entero) | tramo: `1_30`, `31_60`, `61_90`, `91_mas` |
| dinero | `clientes_deben` | Clientes que nos deben | entero | Vencido (soles) | tramo: `1_30`, `31_60`, `61_90`, `91_mas` |
| dinero | `debemos_financiera` | Debemos a las financieras | soles | — | — |
| dinero | `ganancia` | Ganancia (posición neta) | soles | — | — |
| flota | `flota_total` | Flota total | entero | — | estado: `financiado`, `stock`, `asignado` |
| flota | `stock` | Stock disponible | entero | — | — |
| flota | `placas_tramite` | Placas en trámite | entero | — | estado: `pendiente`, `en_tramite`, `observado` |
| flota | `ciclo_fibra` | Ciclo de fibra | entero | Demoradas (entero) | etapa: `recojo`, `almacen`, `fibra`, `listo` |
| incidencias | `papeletas_vencidas` | Papeletas vencidas sin pagar | entero | Monto pendiente (soles) | — |
| incidencias | `capturas` | Motos capturadas | entero | — | — |
| incidencias | `disoluciones` | Disoluciones de contrato | entero | — | — |
| crecimiento | `candidatos` | Candidatos a otro préstamo | entero | Colocación potencial (soles) | — |
| crecimiento | `expedientes_nuevos` | Expedientes nuevos del mes | entero | — | estado: `por_revisar`, `incompleto_expediente`, `incompleto_fase_final`, `completo`, `aprobado_sin_desembolso`, `rechazado` |

Notas:
- **ganancia** = nos deben los clientes − debemos a las financieras. Puede ser negativa: muéstrenla en rojo.
- **ciclo_fibra**: el `valor` cuenta las motos que siguen en recojo, almacén o taller. El desglose
  muestra además `listo` (listas para asignar), que no se suma al valor.
- **clientes_deben**: si un cliente tiene cuentas en dos financieras, en `por_financiera` aparece en
  ambas, pero en el total se cuenta una sola vez.
- **expedientes_nuevos**: solo los creados en el mes de `data.mes`.
- Las motos sin crédito (stock, fibra) y los clientes nuevos sin cuenta van en "Sin financiera" (`id` 0).

---

## 5. GET /resumen/{clave} (detalle)

```http
GET /api/gerencia/v1/resumen/deuda_vencida?financiera_id=6&filtro=31_60&buscar=quispe&pagina=1&por_pagina=20
```

| Parámetro | Tipo | Descripción |
|---|---|---|
| `financiera_id` | entero, opcional | Igual que en `/resumen`. |
| `filtro` | string, opcional | Una `clave` del `desglose`. Solo en los indicadores que tienen desglose; en los demás devuelve 400. |
| `buscar` | string, opcional | Texto libre; no distingue mayúsculas. Campos de búsqueda en la tabla de abajo. |
| `pagina` | entero, opcional | Desde 1. Por defecto 1. |
| `por_pagina` | entero, opcional | Por defecto 20, máximo 100. |

### Respuesta

```json
{
  "ok": true,
  "data": {
    "indicador": { "...": "mismo objeto que en /resumen, con el filtro de financiera aplicado" },
    "filas": [ { "...": "ver campos por indicador" } ]
  },
  "meta": {
    "pagina": 1, "por_pagina": 20, "total": 37, "paginas": 2,
    "filtro": "31_60", "buscar": "quispe",
    "valor_filtrado": 1840.5
  }
}
```

- `data.indicador` sirve para la cabecera del detalle: título, cifra, chips de desglose y financieras.
- `meta.total` es la cantidad de filas después del filtro y la búsqueda; `meta.paginas`, el total de páginas.
- `meta.valor_filtrado` es la cifra del indicador con el filtro y la búsqueda aplicados. Por ejemplo, el monto vencido solo del tramo elegido.
- Las filas ya vienen ordenadas, con lo más importante primero.
- Cualquier campo de texto puede venir como `""` y los opcionales como `null`.
- Todas las filas traen `financiera_id` (entero, 0 = sin financiera) y `financiera` (nombre).

### Campos de las filas por indicador

**`nos_deben_total`**: orden: mayor por cobrar. Búsqueda: cliente, documento, placa, referencia.

| Campo | Tipo | Descripción |
|---|---|---|
| `cuenta_id` | int | Id de la cuenta |
| `referencia` | string | Código de la cuenta (ej. CC00001) |
| `cliente_id` | int | Id del cliente |
| `cliente` | string | Nombre |
| `documento` | string | DNI / documento |
| `telefono` | string | |
| `placa` | string | |
| `asesor` | string | |
| `por_cobrar` | soles | Saldo total pendiente |
| `vencido` | soles | Parte vencida |
| `por_vencer` | soles | Parte aún no vencida |
| `cuotas_restantes` | int | |
| `fin_credito` | fecha \| null | Fecha de la última cuota |

**`deuda_vencida`**: una fila por cuenta con atraso. Orden: mayor vencido. Búsqueda: cliente, documento, placa, referencia.

| Campo | Tipo | Descripción |
|---|---|---|
| `cuenta_id`, `referencia`, `cliente_id`, `cliente`, `documento`, `telefono`, `placa`, `asesor` | | Igual que arriba |
| `estado_cobranza` | `al_dia` \| `deuda` \| `orden` \| `capturada` | Situación de cobranza |
| `estado_cobranza_nombre` | string | Texto para mostrar |
| `vencido` | soles | |
| `mora_pendiente` | soles | |
| `por_cobrar` | soles | |
| `dias_atraso` | int | Días de la cuota más atrasada |
| `cuotas_vencidas` | int | |
| `tramo` | `1_30` \| `31_60` \| `61_90` \| `91_mas` | Tramo de atraso |
| `tramo_nombre` | string | |

**`clientes_deben`**: una fila por cliente (y financiera). Orden: mayor vencido. Búsqueda: cliente, documento, placas.

| Campo | Tipo | Descripción |
|---|---|---|
| `cliente_id`, `cliente`, `documento`, `telefono` | | |
| `placas` | string | Placas separadas por coma |
| `cuentas` | int | Cuentas con atraso |
| `vencido`, `mora_pendiente`, `por_cobrar` | soles | Suma de sus cuentas |
| `dias_atraso` | int | El mayor atraso |
| `cuotas_vencidas` | int | |
| `tramo`, `tramo_nombre` | | El tramo más grave |
| `estado_cobranza`, `estado_cobranza_nombre` | | La situación más grave |

**`debemos_financiera`**: orden: mayor deuda. Búsqueda: cliente, documento, placa, referencia.

| Campo | Tipo | Descripción |
|---|---|---|
| `cuenta_id`, `referencia`, `cliente_id`, `cliente`, `documento`, `telefono`, `placa`, `asesor` | | |
| `deuda_financiera` | soles | Lo que falta pagar a la financiera por esa cuenta |
| `cancelar_hoy` | soles \| null | Monto para cancelar hoy; `null` si no hay dato |
| `fuente` | string | Origen del dato del cronograma (`sin_datos` = la cuenta no tiene cronograma de financiera) |

**`ganancia`**: orden: mayor posición. Búsqueda: cliente, documento, placa, referencia.

| Campo | Tipo | Descripción |
|---|---|---|
| `cuenta_id`, `referencia`, `cliente_id`, `cliente`, `documento`, `telefono`, `placa`, `asesor` | | |
| `nos_debe` | soles | |
| `debemos_financiera` | soles | |
| `posicion_neta` | soles | `nos_debe − debemos_financiera` (puede ser negativa) |

**`flota_total` y `stock`**: búsqueda: placa, modelo, cliente, chasis (en `stock`: placa, modelo, chasis, color).

| Campo | Tipo | Descripción |
|---|---|---|
| `vehiculo_id` | int | |
| `placa` | string \| null | `null` si todavía no tiene placa real |
| `placa_lista` | bool | Tiene placa o el trámite ya terminó |
| `tramite_placa` | string \| null | `pendiente`, `en_tramite`, `observado`, `finalizado`, `historial` |
| `etapa_fibra` | string \| null | `recojo`, `almacen`, `fibra`, `listo` si sigue en logística |
| `modelo`, `chasis`, `color` | string | |
| `cliente_id` | int \| null | |
| `cliente` | string | |
| `cuenta` | string \| null | Referencia de la cuenta |
| `estado` | `financiado` \| `stock` \| `asignado` | |
| `estado_nombre` | string | |
| `estado_flota` | string | Estado en el módulo de flota de Odoo |

**`placas_tramite`**: orden: más días de trámite. Búsqueda: referencia, chasis, modelo, cliente.

| Campo | Tipo | Descripción |
|---|---|---|
| `tramite_id` | int | |
| `referencia` | string | Ej. PLC/2026/00002 |
| `vehiculo_id` | int | |
| `chasis`, `modelo`, `cliente` | string | |
| `estado` | `pendiente` \| `en_tramite` \| `observado` | |
| `estado_nombre` | string | |
| `fecha_inicio` | fecha \| null | Inicio del trámite |
| `dias_tramite` | number | |
| `dias_sin_iniciar` | number \| null | Solo si está pendiente |
| `observaciones` | int | Veces que fue observado |
| `motivo_observacion` | string | |

**`ciclo_fibra`**: orden: por etapa y luego más días en la etapa. Búsqueda: placa, chasis, modelo, taller, cliente.

| Campo | Tipo | Descripción |
|---|---|---|
| `tracking_id`, `vehiculo_id` | int | |
| `placa` | string \| null | |
| `chasis`, `modelo`, `color` | string | |
| `etapa` | `recojo` \| `almacen` \| `fibra` \| `listo` | |
| `etapa_nombre` | string | |
| `taller` | string | Taller de fibra |
| `fecha_envio_fibra` | fecha \| null | |
| `dias_etapa` | number | Días en la etapa actual |
| `dias_totales` | number | Días desde el recojo |
| `demorado` | bool | Superó el tiempo esperado de la etapa: márquenlo en rojo |
| `cliente` | string | Si ya se asignó |

**`papeletas_vencidas`**: orden: más días vencida. Búsqueda: papeleta, placa, cliente.

| Campo | Tipo | Descripción |
|---|---|---|
| `papeleta_id` | int | |
| `papeleta` | string | Número de papeleta |
| `vehiculo_id` | int | |
| `placa`, `cliente` | string | |
| `fecha_papeleta` | fecha | |
| `vencimiento` | fecha | |
| `dias_vencida` | int | |
| `monto` | soles | Monto total |
| `pendiente` | soles | Lo que falta pagar |
| `fraccionada` | bool | |
| `cuotas_vencidas` | int \| null | Solo si está fraccionada |
| `capturada` | bool | |

**`capturas` y `disoluciones`**: orden: más días capturada. Búsqueda: captura, cliente, placa, referencia.

| Campo | Tipo | Descripción |
|---|---|---|
| `captura_id` | int | |
| `captura` | string | Ej. CAP-00001 |
| `cuenta_id` | int | |
| `referencia` | string | Cuenta |
| `cliente_id` | int | |
| `cliente`, `placa` | string | |
| `fecha` | fecha \| null | Inicio de la captura |
| `dias_capturada` | int \| null | |
| `dias_mora` | int | |
| `cuotas_vencidas` | int | |
| `monto_intervencion` | soles | |
| `pago_intervencion` | `pendiente` \| `pagado` | |
| `capturador` | string | |

**`candidatos`**: orden: mayor puntaje. Búsqueda: nombre, documento.

| Campo | Tipo | Descripción |
|---|---|---|
| `cliente_id` | int | |
| `nombre`, `documento`, `telefono` | string | |
| `segmento`, `segmento_nombre` | string | Siempre `apto` en este detalle |
| `puntaje` | int | 0 a 100 |
| `puntualidad_pct` | number | 0 a 100 |
| `atraso_promedio_dias` | number | |
| `creditos`, `creditos_terminados` | int | |
| `ultimo_monto` | soles | |
| `termino` | fecha \| null | Cuándo terminó su último crédito |
| `termina` | fecha \| null | Cuándo termina el crédito actual |
| `recompra` | bool | Ya volvió a sacar otro crédito |
| `bloqueos` | lista de string | Motivos que impiden prestar |
| `seguimiento` | string \| null | Estado del seguimiento comercial |

**`expedientes_nuevos`**: orden: los más recientes primero. Búsqueda: cliente, documento, asesora.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | int | Id del expediente |
| `cliente_id` | int | |
| `cliente`, `documento`, `telefono` | string | |
| `asesora` | string | |
| `fecha` | fecha | |
| `estado` | ver desglose | |
| `estado_nombre` | string | |
| `vehiculo` | string | Moto que quiere financiar |
| `motivo_rechazo` | string | Solo si fue rechazado |

---

## 6. Flujo de pantallas sugerido

1. **Login** (opción A o B). Si `moduloAdmin` es `false` o el login devuelve 403, ocultar Gerencia.
2. **Resumen**: `GET /resumen`. Selector de financiera arriba, armado con `data.financieras`, y fecha de corte.
   Por cada sección, una grilla de tarjetas con `nombre`, `valor` formateado según `tipo` y `secundario` debajo.
   Si `disponible` es `false`, tarjeta en gris.
3. **Detalle**: al tocar una tarjeta, `GET /resumen/{clave}` con la misma `financiera_id`.
   - Cabecera: `data.indicador` (cifra, `descripcion`).
   - Chips de `desglose`: al tocar uno, volver a pedir con `filtro=<clave>`. Al quitarlo, sin `filtro`.
   - Barra "por financiera" con `data.indicador.por_financiera`.
   - Buscador con `buscar` (aplicar unos 300 ms después de que el usuario deja de escribir) y scroll infinito con `pagina` hasta `meta.paginas`.
4. **Volver a cargar**: los datos se calculan en el momento. Recomendamos pull-to-refresh y no guardar caché más de 5 minutos.

## 7. Ejemplos con curl

```bash
# Login
curl -X POST http://192.168.100.97:8069/api/gerencia/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"usuario","password":"clave","dispositivo":"Postman"}'

# Resumen completo
curl http://192.168.100.97:8069/api/gerencia/v1/resumen -H 'Authorization: Bearer <token>'

# Resumen de una financiera
curl 'http://192.168.100.97:8069/api/gerencia/v1/resumen?financiera_id=6' -H 'Authorization: Bearer <token>'

# Detalle: motos en el taller de fibra
curl 'http://192.168.100.97:8069/api/gerencia/v1/resumen/ciclo_fibra?filtro=fibra' -H 'Authorization: Bearer <token>'

# Detalle: clientes con más de 90 días de atraso, página 2
curl 'http://192.168.100.97:8069/api/gerencia/v1/resumen/clientes_deben?filtro=91_mas&pagina=2' -H 'Authorization: Bearer <token>'
```
