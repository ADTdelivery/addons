# API Gerencia v1

API de solo lectura para la app móvil de la gerencia. Base: `https://<servidor>/api/gerencia/v1`.

## Acceso

Solo entran los usuarios de Odoo con el grupo **App de gerencia / Acceso a la app de gerencia**
(Ajustes › Usuarios). El permiso se revisa en cada llamada: si se le quita el grupo al usuario,
su sesión deja de funcionar al instante. Las sesiones abiertas se ven y se revocan en
Ajustes › Usuarios y compañías › Sesiones app de gerencia.

1. `POST /auth/login` con usuario y contraseña de Odoo → devuelve un token válido 30 días.
2. Enviar en todas las demás llamadas: `Authorization: Bearer <token>`.
3. `POST /auth/logout` invalida el token.

Se puede enviar `Content-Type: application/json` en todas las llamadas.

### moduloAdmin en /web/session/authenticate

El login estándar de Odoo (`POST /web/session/authenticate`) incluye en `result` el campo
`moduloAdmin`: `true` si el usuario tiene el grupo de la app de gerencia, `false` si no. Sirve
para que la app decida al iniciar sesión si muestra la sección de gerencia. No confundir con
`is_admin` de Odoo, que indica administrador del sistema.

## Formato

```json
{"ok": true,  "data": { ... }, "meta": { ... }}
{"ok": false, "error": {"codigo": "NO_AUTORIZADO", "mensaje": "..."}}
```

| HTTP | código | cuándo |
|---|---|---|
| 400 | `JSON_INVALIDO`, `DATOS_INCOMPLETOS`, `PARAMETRO_INVALIDO` | cuerpo o parámetros mal formados |
| 401 | `CREDENCIALES_INVALIDAS` | usuario o contraseña incorrectos |
| 401 | `NO_AUTORIZADO` | token ausente, vencido, revocado o el usuario perdió el permiso |
| 403 | `SIN_PERMISO` | el usuario no tiene el grupo de la app de gerencia |
| 500 | `ERROR_INTERNO` | error al calcular (queda en el log del servidor) |

Montos en soles (PEN) con dos decimales. Porcentajes de 0 a 100. Fechas `YYYY-MM-DD` (hora de Lima).
La cartera considera solo cuentas **en curso**. Las cifras coinciden con los reportes de Odoo
(Cartera y financieras, Reporte de Cobranzas, Dashboard de Clientes).

## Endpoints

### POST /auth/login
```json
{"login": "gerente@adt.pe", "password": "...", "dispositivo": "iPhone de Ana", "app_version": "1.0.0"}
```
Respuesta: `token`, `tipo` ("Bearer"), `expira`, `usuario {id, nombre, login}`.

### POST /auth/logout
Revoca el token enviado en el header.

### GET /me
Usuario de la sesión.

### GET /resumen
Portada de la app: 14 indicadores en 4 secciones. Parámetro opcional `financiera_id`
(0 = sin financiera) para ver solo esa financiera.

```json
{"fecha_corte": "2026-10-16", "mes": "2026-10", "moneda": "PEN", "simbolo": "S/",
 "filtro_financiera_id": null, "financieras": [{"id": 0, "nombre": "Sin financiera"}],
 "secciones": [{"clave": "dinero", "nombre": "Dinero", "indicadores": [
   {"clave": "deuda_vencida", "nombre": "Deuda vencida", "descripcion": "...", "tipo": "soles",
    "disponible": true, "valor": 252.0,
    "secundario": {"nombre": "Cuentas", "tipo": "entero", "valor": 1},
    "desglose": [{"clave": "1_30", "nombre": "1 a 30 días", "valor": 252.0}],
    "por_financiera": [{"financiera_id": 6, "nombre": "Financiera X", "valor": 252.0}]}]}]}
```

- `valor`: la cifra principal (`tipo`: `soles` o `entero`).
- `secundario` (opcional): una segunda cifra que acompaña a la principal.
- `desglose` (opcional): la cifra repartida por estado, tramo o etapa. Sus claves son los valores
  de `filtro` en el detalle.
- `por_financiera`: la misma cifra separada por financiera, de mayor a menor. Las motos sin crédito
  (stock, fibra) y los expedientes de clientes nuevos van en "Sin financiera".
- `disponible: false`: el módulo de origen no está instalado en el servidor (`valor` = null).

| sección | clave | indicador | valor | desglose / filtro |
|---|---|---|---|---|
| dinero | `nos_deben_total` | Nos deben los clientes (vencido + por vencer) | soles · secundario: vencido | |
| dinero | `deuda_vencida` | Deuda vencida | soles · secundario: cuentas | tramo: `1_30`, `31_60`, `61_90`, `91_mas` |
| dinero | `clientes_deben` | Clientes con cuotas vencidas | clientes · secundario: vencido | tramo |
| dinero | `debemos_financiera` | Debemos a las financieras | soles | |
| dinero | `ganancia` | Posición neta: nos deben − debemos a financieras | soles | |
| flota | `flota_total` | Flota total | motos | estado: `financiado`, `stock`, `asignado` |
| flota | `stock` | Stock disponible (sin cliente) | motos | |
| flota | `placas_tramite` | Placas en trámite | motos | estado: `pendiente`, `en_tramite`, `observado` |
| flota | `ciclo_fibra` | Motos en el ciclo de fibra (recojo, almacén, taller) · secundario: demoradas | motos | etapa: `recojo`, `almacen`, `fibra`, `listo` |
| incidencias | `papeletas_vencidas` | Papeletas vencidas sin pagar · secundario: monto pendiente | papeletas | |
| incidencias | `capturas` | Motos capturadas | capturas | |
| incidencias | `disoluciones` | Disoluciones de contrato | capturas | |
| crecimiento | `candidatos` | Listos para otro préstamo · secundario: colocación potencial | clientes | |
| crecimiento | `expedientes_nuevos` | Expedientes creados este mes | expedientes | estado: `por_revisar`, `incompleto_expediente`, `incompleto_fase_final`, `completo`, `aprobado_sin_desembolso`, `rechazado` |

En `ciclo_fibra` el valor cuenta las motos que siguen en recojo, almacén o taller; el desglose
muestra además las que ya están listas para asignar.

### GET /resumen/{clave}
Detalle de un indicador: las filas que suman su valor. Parámetros: `financiera_id`, `filtro`
(una clave del desglose), `buscar`, `pagina`, `por_pagina` (máx. 100).

Respuesta: `data.indicador` (igual que en `/resumen`, ya filtrado por financiera) y `data.filas`.
`meta` trae la paginación y `valor_filtrado` (la cifra del indicador con `filtro` y `buscar` aplicados).

| clave | cada fila | se busca por |
|---|---|---|
| `nos_deben_total` | cuenta, cliente, placa, financiera, por cobrar, vencido, por vencer, cuotas restantes | cliente, documento, placa, cuenta |
| `deuda_vencida` | igual que `/deudores` + `tramo_nombre` | cliente, documento, placa, cuenta |
| `clientes_deben` | cliente, placas, cuentas, vencido, mora, por cobrar, días de atraso, tramo, estado de cobranza | cliente, documento, placa |
| `debemos_financiera` | cuenta, cliente, financiera, deuda con la financiera, monto para cancelar hoy | cliente, documento, placa, cuenta |
| `ganancia` | cuenta, cliente, nos debe, debemos a la financiera, posición neta | cliente, documento, placa, cuenta |
| `flota_total`, `stock` | moto, placa (null si no tiene), trámite de placa, etapa de fibra, modelo, chasis, cliente, cuenta, estado | placa, modelo, cliente, chasis |
| `placas_tramite` | trámite, moto, chasis, estado, inicio, días de trámite, días sin iniciar, observaciones | trámite, chasis, modelo, cliente |
| `ciclo_fibra` | moto, etapa, taller, envío a fibra, días en la etapa, días totales, demorada | placa, chasis, modelo, taller, cliente |
| `papeletas_vencidas` | papeleta, placa, cliente, vencimiento, días vencida, monto, pendiente, fraccionada | papeleta, placa, cliente |
| `capturas`, `disoluciones` | captura, cuenta, cliente, placa, fecha, días capturada, días de mora, cuotas vencidas, monto de intervención | captura, cliente, placa, cuenta |
| `candidatos` | igual que `/candidatos` | nombre, documento |
| `expedientes_nuevos` | cliente, documento, asesora, fecha, estado, vehículo, motivo de rechazo | cliente, documento, asesora |

### GET /dashboard
Todos los indicadores en una llamada. Parámetro opcional `financiera_id` (0 = sin financiera)
para ver solo esa financiera (los vehículos son siempre de toda la flota).

| sección | contenido |
|---|---|
| `titulares` | Indicadores principales para la portada: `clave`, `nombre`, `valor`, `tipo` (`soles`, `entero`, `porcentaje`), `detalle` y, si aplica, `variacion_pct` frente al mes anterior. Claves: `vehiculos`, `por_cobrar`, `vencido`, `par30`, `recaudo_mes`, `posicion_neta`, `candidatos`, `traspasos`. |
| `alertas` | Lista ordenada por gravedad (`critico`, `atencion`, `info`) con `codigo`, `mensaje` y `valor`. Códigos: `PAR30_ALTO`, `ATRASO_MAS_90`, `RECAUDO_BAJO`, `FINANCIERA_MORA_ALTA`, `CONCENTRACION`, `TRASPASOS_ESTANCADOS`, `TRASPASOS_POR_INICIAR`. |
| `vehiculos` | `total`, `financiados` (con cuenta en curso), `disponibles`, `capturados`, `sin_placa`, `por_estado`. |
| `cartera` | Tamaño (`cuentas`, `clientes`, `monto_financiado`, `cobrado`, `por_cobrar`, `por_vencer`, `ticket_promedio`), calidad (`vencido`, `mora_pendiente`, `morosidad_pct`, `par30_pct`, `par60_pct`, `par90_pct`, `cuentas_con_atraso`), `tramos_atraso` (monto y cuentas por tramo), `estados` de cobranza (al día, con cuotas vencidas, con orden de captura, capturada) y `concentracion_top10_pct`. |
| `top_deudores` | Los 10 que más deben (mismo formato que `/deudores`). |
| `por_financiera` | Por financiera: cuentas, por cobrar, vencido, % de mora, deuda con la financiera y posición neta. |
| `flujo` | `mes_actual` (cobrado, mora cobrada, programado del mes y a la fecha, cumplimiento a la fecha), `mes_anterior`, `variacion_cobrado_pct`, `proximos_dias` (lo que vence en 30 días) y `tendencia` de 12 meses. |
| `posicion_financieras` | Lo que nos deben los clientes, lo que debemos a las financieras, posición neta, costo de cancelar hoy a las financieras y ganancia esperada / realizada / por realizar. |
| `candidatos` | Clientes por `segmentos`, `listos` y `monto_potencial`, `pipeline_90_dias` (buenos pagadores que terminan pronto), `tasa_recompra_pct` y `top` 10 candidatos. |
| `traspasos` | Motos por `etapas`, `en_tramite_por_estado`, `pagados_sin_iniciar`, `por_preparar_60_dias`, `completados_mes`, `duracion_promedio_dias` y `estancados`. |

### GET /deudores
Quiénes deben (cuentas con cuotas vencidas).
Parámetros: `financiera_id`, `tramo` (`1_30`, `31_60`, `61_90`, `91_mas`), `estado` (`al_dia`, `deuda`,
`orden`, `capturada`), `buscar` (cliente, DNI, placa o cuenta), `orden` (`vencido` por defecto, `dias`,
`cliente`), `pagina`, `por_pagina` (máx. 100).
Cada fila: cuenta, cliente, documento, teléfono, placa, financiera, asesor, estado de cobranza, vencido,
mora pendiente, por cobrar, días de atraso, cuotas vencidas y tramo. `meta.total_vencido` suma todo el filtro.

### GET /candidatos
Clientes para un nuevo préstamo. Parámetros: `segmento` (`apto` por defecto, `evaluar`, `pagando_bien`,
`pagando_alerta`, `no_prestar`; vacío = todos), `financiera_id`, `buscar`, `pagina`, `por_pagina`.
Cada fila: puntaje (0-100), puntualidad, atraso promedio, créditos, último monto, cuándo terminó o
termina, si ya volvió a sacar, motivos de bloqueo y estado del seguimiento comercial.

### GET /traspasos
Motos por pasar a nombre del cliente. Parámetros: `etapa` (`preparar`, `listo`, `en_tramite`,
`completado`), `financiera_id`, `buscar`, `pagina`, `por_pagina`.
Cada fila: cuenta, cliente, placa, etapa y estado del trámite, notaría, fechas, responsable,
días sin avance y alertas (papeleta impaga, cuotas atrasadas, moto sin placa…).

## Umbrales de alertas

Se cambian en Ajustes › Técnico › Parámetros del sistema:

| parámetro | por defecto |
|---|---|
| `adt_gerencia_api.umbral_par30` | 10 (%) |
| `adt_gerencia_api.umbral_cumplimiento` | 85 (%) |
| `adt_gerencia_api.umbral_traspaso_dias` | 30 (días) |
