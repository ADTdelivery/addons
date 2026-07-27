# Propuesta: Sistema de Alertas de Mantenimiento Preventivo basado en Kilometraje (Traccar)

## 1. Objetivo

Diseñar la lógica de negocio (agnóstica a lenguaje/framework) de un sistema que:

1. Lee diariamente el kilometraje acumulado de cada vehículo desde Traccar.
2. Evalúa ese kilometraje contra reglas de mantenimiento configurables (aceite, frenos, etc.).
3. Genera **campañas de notificación** para los vehículos que cumplen una regla.
4. Envía notificaciones push (Firebase) durante N días, con M notificaciones por día, ambos configurables.

Este documento es la especificación funcional para pasar luego a Claude Code como input de implementación.

---

## 2. Entidades del dominio

### 2.1 Vehículo
- `id`
- `placa` / identificador
- `traccar_device_id` (mapeo al dispositivo GPS en Traccar)
- `propietario` / `conductor` (para saber a quién notificar — token(s) de Firebase)
- `kilometraje_actual` (último valor leído)
- `kilometraje_base_por_regla` (ver 2.2 — punto de referencia por cada regla, para poder reiniciar el ciclo)

### 2.2 Regla de Mantenimiento (`MaintenanceRule`) + Umbrales (`MaintenanceThreshold`)

**Decisión de negocio confirmada:** los umbrales de una regla NO son un intervalo fijo (no es "cada 600km"). Es una **lista ordenada y extensible de umbrales** propia de cada tipo de mantenimiento, porque el primer cambio de aceite puede ser a los 600km, el segundo a los 1000km, el tercero a los 2000km, etc. Esta lista se debe poder ampliar o modificar en cualquier momento desde configuración, sin tocar código.

**`MaintenanceRule`** (el "tipo" de mantenimiento):

| Campo | Descripción | Ejemplo |
|---|---|---|
| `id` | identificador de la regla | `cambio_aceite` |
| `nombre` | texto descriptivo | "Cambio de aceite" |
| `dias_notificacion` | por cuántos días se enviarán notificaciones tras el disparo | 3 |
| `notificaciones_por_dia` | cuántas notificaciones se envían cada día de la campaña | 3 |
| `horarios_notificacion` (opcional) | franjas horarias sugeridas para distribuir las notificaciones del día | ["09:00","14:00","19:00"] |
| `mensaje_template` | plantilla del mensaje, con variables (`{placa}`, `{km_actual}`, `{regla}`) | — |
| `activa` | si la regla está habilitada | true |

**`MaintenanceThreshold`** (cada punto de la secuencia de kilometraje para esa regla):

| Campo | Descripción | Ejemplo |
|---|---|---|
| `id` | identificador del umbral | — |
| `regla_id` | a qué regla pertenece | `cambio_aceite` |
| `orden` | posición en la secuencia (1, 2, 3…) | 1 |
| `km_umbral` | kilometraje en el que se dispara | 600 |
| `activo` | permite desactivar un umbral puntual sin borrar el histórico | true |

Ejemplo de secuencia para `cambio_aceite`: `[600, 1000, 2000, 3000, ...]`. Esta tabla se puede seguir alimentando con el tiempo (agregar el umbral 4000 cuando se decida), y el motor de reglas simplemente busca "el siguiente umbral no disparado todavía" — no asume una progresión aritmética.

> Nota: si en algún momento se necesita una regla que sí sea "cada X km de forma indefinida" (para no tener que estar agregando umbrales a mano para siempre), se puede agregar más adelante un campo opcional `intervalo_km_after_last` que diga "después del último umbral definido, repetir cada X km". Por ahora no es necesario: se irán agregando/editando umbrales manualmente según lo comentado.

### 2.3 Estado de Regla por Vehículo (`VehicleRuleState`)
Esta es la entidad más importante para no repetir procesamiento. Por cada par (vehículo, regla) se guarda:

- `vehiculo_id`
- `regla_id`
- `ultimo_umbral_disparado_orden` (el `orden` del último `MaintenanceThreshold` ya disparado para ese vehículo — no el km, para que si se reordenan/insertan umbrales no se rompa la lógica)
- `estado`: `PENDIENTE_EVALUAR` | `CAMPANA_ACTIVA` | `COMPLETADA_POR_USUARIO` | `CAMPANA_FINALIZADA`
- `fecha_disparo`
- `atendida_en` (fecha en que el taller/usuario marcó el mantenimiento como realizado — campo reservado para la integración futura de la sección 9)

### 2.6 Estado de Reporte GPS (`VehicleReportStatus`)
Para poder alertar cuando un vehículo deja de reportar:

- `vehiculo_id`
- `ultima_fecha_reporte` (última vez que Traccar devolvió una posición/kilometraje válido)
- `dias_sin_reportar` (calculado en cada corrida del job)
- `alerta_sin_reporte_enviada` (para no reenviar la misma alerta todos los días; se resetea cuando vuelve a reportar)

### 2.4 Campaña de Notificación (`NotificationCampaign`)
Se crea una campaña cuando una regla se dispara para un vehículo:

- `id`
- `vehiculo_id`
- `regla_id`
- `fecha_inicio`
- `dias_totales` (copiado de la regla al momento de crear la campaña, ver 6.2)
- `notificaciones_por_dia` (copiado igual)
- `dia_actual` (contador de avance, 1..N)
- `notificaciones_enviadas_hoy`
- `estado`: `ACTIVA` | `FINALIZADA` | `CANCELADA` (si el usuario ya hizo el mantenimiento)

### 2.5 Notificación individual (`NotificationLog`)
Registro de auditoría de cada push enviado: campaña, fecha/hora, resultado del envío en Firebase (éxito/error), para trazabilidad y evitar duplicados si el job se re-ejecuta.

---

## 3. Flujo diario (Job nocturno)

Ejecutado una vez al final del día (ej. cron 23:00 o 00:30):

```
1. Obtener lista de vehículos activos (con traccar_device_id)
2. Para cada vehículo:
   a. Consultar a Traccar el kilometraje acumulado actual
      (Traccar expone esto vía reportes de "trips" o el atributo
      "totalDistance" del dispositivo/posición)
   b. Actualizar kilometraje_actual del vehículo
   c. Para cada regla activa:
      - Evaluar si corresponde disparo (ver Motor de Reglas, sección 4)
      - Si corresponde y no hay ya una campaña activa/duplicada para
        ese (vehículo, regla, umbral):
          -> Crear NotificationCampaign en estado ACTIVA
          -> Actualizar VehicleRuleState
3. Fin del job de evaluación (esto NO envía notificaciones todavía,
   solo genera/actualiza campañas)
```

## 4. Motor de Reglas (evaluación de umbral)

Dado `km_actual` del vehículo y la secuencia ordenada de `MaintenanceThreshold` de una regla:

```
siguiente_orden = vehicle_rule_state.ultimo_umbral_disparado_orden + 1
siguiente_umbral = buscar MaintenanceThreshold de esta regla
                    con orden == siguiente_orden y activo == true

si siguiente_umbral no existe:
    # todavía no se ha configurado el siguiente paso de la secuencia
    no hacer nada (queda pendiente hasta que se agregue un nuevo umbral)

si no:
    si km_actual >= siguiente_umbral.km_umbral:
        DISPARAR regla usando siguiente_umbral
        vehicle_rule_state.ultimo_umbral_disparado_orden = siguiente_umbral.orden
        # se evalúa de nuevo por si el vehículo saltó varios umbrales
        # de golpe (ej. no se procesó por varios días); se repite el
        # bucle hasta que km_actual ya no alcance el siguiente umbral
```

Esto cubre el caso real: primer cambio de aceite a los 600km, segundo a los 1000km, tercero a los 2000km, etc. — y sigue funcionando aunque se agreguen nuevos umbrales más adelante en la secuencia (el sistema simplemente encuentra "no hay siguiente umbral todavía" y espera).

### 4.1 Alerta de vehículo sin reporte

En el mismo job, además de evaluar reglas de mantenimiento, se evalúa el reporte de GPS:

```
Para cada vehículo:
    dias_sin_reportar = hoy - vehicle_report_status.ultima_fecha_reporte
    si dias_sin_reportar >= umbral_dias_sin_reporte (configurable)
       Y NO vehicle_report_status.alerta_sin_reporte_enviada:
           enviar notificación "vehículo {placa} sin reportar hace {N} días"
           vehicle_report_status.alerta_sin_reporte_enviada = true
    si el vehículo vuelve a reportar:
           vehicle_report_status.alerta_sin_reporte_enviada = false
```

Esta es una alerta operativa (para el administrador de flota), distinta de las campañas de mantenimiento del conductor.

## 5. Motor de envío de notificaciones (Job separado, o el mismo job por la mañana)

Este proceso corre **todos los días**, revisando campañas `ACTIVA`, no solo el día que se dispararon:

```
Para cada NotificationCampaign en estado ACTIVA:
   si campaña.dia_actual > campaña.dias_totales:
        marcar campaña como FINALIZADA
        continuar
   enviar campaña.notificaciones_por_dia notificaciones vía Firebase
        (distribuidas según horarios_notificacion si están definidos,
        o repartidas uniformemente en horario hábil si no)
   registrar cada envío en NotificationLog
   al cerrar el día: campaña.dia_actual += 1
```

**Cancelación anticipada:** si existe un flujo donde el usuario/taller marca el mantenimiento como "realizado", la campaña pasa a `CANCELADA` y deja de enviar, independientemente de los días que falten.

---

## 6. Decisiones de negocio confirmadas

1. **Reglas por secuencia de umbrales (no intervalo fijo):** cambio de aceite es a los 600km, luego 1000km, luego 2000km, etc., pudiendo agregar o modificar umbrales de esta secuencia progresivamente. Ver sección 2.2 / 4.

2. **Vehículo sin reporte:** sí se debe alertar cuando un vehículo deja de reportar kilometraje por X días (configurable). Ver sección 4.1.

3. **Confirmación de mantenimiento "atendido":** por ahora **no** se integra con un sistema externo (taller, orden de trabajo, etc.) que confirme que el mantenimiento ya se hizo. Se deja el campo `atendida_en` reservado en `VehicleRuleState` y un diseño de referencia para cuando se implemente (ver sección 9).

4. **Reglas simultáneas:** si un vehículo cumple varias reglas el mismo día (ej. aceite y frenos a la vez), se generan y envían **campañas independientes**, una notificación por cada regla, no agrupadas.

5. **Tenant:** por ahora el sistema es **single-tenant** (una sola flota/empresa). El modelo de datos puede dejar espacio para un `tenant_id` a futuro, pero no es un requisito de esta primera versión.

6. **Snapshot de configuración:** `dias_totales` y `notificaciones_por_dia` se copian a la campaña al momento de crearse (no se leen en vivo de la regla). Un cambio posterior en la configuración de la regla solo afecta a las campañas nuevas, no a las que ya están en curso.

---

## 7. Configuración (ejemplo agnóstico, formato JSON solo como referencia)

```json
{
  "reglas": [
    {
      "id": "cambio_aceite",
      "nombre": "Cambio de aceite",
      "dias_notificacion": 3,
      "notificaciones_por_dia": 3,
      "horarios_notificacion": ["09:00", "14:00", "19:00"],
      "mensaje_template": "Tu vehículo {placa} alcanzó {km_actual} km. Toca cambiar el aceite.",
      "activa": true,
      "umbrales": [
        { "orden": 1, "km_umbral": 600, "activo": true },
        { "orden": 2, "km_umbral": 1000, "activo": true },
        { "orden": 3, "km_umbral": 2000, "activo": true }
      ]
    },
    {
      "id": "cambio_frenos",
      "nombre": "Cambio de frenos",
      "dias_notificacion": 3,
      "notificaciones_por_dia": 3,
      "mensaje_template": "Tu vehículo {placa} alcanzó {km_actual} km. Revisa los frenos.",
      "activa": true,
      "umbrales": [
        { "orden": 1, "km_umbral": 1000, "activo": true },
        { "orden": 2, "km_umbral": 2500, "activo": true }
      ]
    }
  ],
  "configuracion_general": {
    "umbral_dias_sin_reporte": 3
  }
}
```

---

## 9. Diseño futuro: confirmación de mantenimiento "atendido"

No se implementa ahora, pero para que el modelo actual no quede reñido con esto más adelante, la idea de referencia es:

- Nueva entidad `OrdenMantenimiento`: `vehiculo_id`, `regla_id`, `umbral_id`, `fecha_atencion`, `origen` (ej. `TALLER_INTERNO`, `APP_CONDUCTOR`, `SISTEMA_EXTERNO_X`), `observaciones`.
- Un endpoint (o integración con el sistema externo) que, al recibir la confirmación, haga: `VehicleRuleState.atendida_en = fecha`, y cambie la `NotificationCampaign` activa de ese (vehículo, regla) a `CANCELADA`, deteniendo el envío de notificaciones restantes.
- Si el sistema externo no llega a tiempo (el vehículo sigue circulando y llega al siguiente umbral antes de que se confirme el anterior), el motor de reglas de la sección 4 ya maneja ese caso: simplemente avanza al siguiente umbral cuando corresponda, sin bloquear por falta de confirmación.
- Esto permite integrarlo después sin rediseñar el core: solo se agrega la entidad, el endpoint, y el trigger de cancelación de campaña — el resto de la lógica (umbrales, campañas, envío) queda igual.

---

## 10. Resumen de arquitectura sugerida (alto nivel, agnóstico)

- **Job A — Lector de kilometraje** (diario, nocturno): consulta Traccar, actualiza km, evalúa reglas, crea/actualiza campañas.
- **Job B — Emisor de notificaciones** (diario, en la mañana): recorre campañas activas y dispara los pushes de Firebase del día.
- **Servicio de Reglas**: encapsula la lógica de la sección 4, testeable de forma aislada (input: km + estado previo → output: dispara o no).
- **Servicio de Campañas**: crea, avanza y finaliza campañas.
- **Servicio de Notificaciones**: abstrae Firebase, recibe (destinatario, mensaje) y registra el log.

Separar A y B en dos jobs (aunque hoy sean el mismo cron) te da flexibilidad si luego quieres, por ejemplo, reintentar solo el envío sin re-evaluar todo el kilometraje.

---

**Siguiente paso sugerido:** este documento ya refleja las decisiones de negocio confirmadas (sección 6), por lo que queda listo para pasarlo a Claude Code junto con el detalle técnico de tu stack (Traccar API endpoints que uses, Firebase Admin SDK, base de datos, etc.).
