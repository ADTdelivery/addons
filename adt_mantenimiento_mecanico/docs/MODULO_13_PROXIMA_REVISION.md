# MÓDULO 13: PRÓXIMA REVISIÓN

## Objetivo
Programar y gestionar automáticamente las fechas y condiciones para el próximo mantenimiento del vehículo, asegurando la continuidad del servicio y la fidelización del cliente.

## Información de la Próxima Revisión

### Campos Principales

#### 1. Fecha Recomendada
- Fecha sugerida para próximo servicio
- Calculada automáticamente basada en:
  - Tipo de mantenimiento realizado
  - Especificaciones del fabricante
  - Historial del vehículo
  - Tipo de uso (urbano, carretera, reparto)
- **Formato**: DD/MM/YYYY
- **Editable** por asesor/mecánico

#### 2. Kilometraje Recomendado
- Kilometraje para próxima revisión
- Calculado basado en:
  - Kilometraje actual + intervalo estándar
  - Manual del fabricante
  - Historial de mantenimientos
- **Ejemplo**: Si actual = 8,500 km → próximo = 13,500 km (intervalo 5,000 km)
- **Editable** por asesor/mecánico

#### 3. Tipo de Mantenimiento Futuro
- Tipo de servicio sugerido:
  - **Preventivo**: Mantenimiento programado
  - **Revisión**: Inspección general
  - **Específico**: Trabajo puntual conocido
  - **Mayor**: Servicio grande programado
- Define la naturaleza del próximo servicio

#### 4. Descripción/Observaciones
- Trabajos sugeridos para próxima visita
- Recomendaciones específicas
- Notas importantes
- **Ejemplo**: "Revisar desgaste de pastillas de freno, cambiar llanta delantera"

## Cálculo Automático

### Lógica de Programación

#### Para Mantenimiento PREVENTIVO:
```
Si se realizó:
- Cambio de aceite (5,000 km)
  → Próximo: Actual + 5,000 km o +3 meses

- Mantenimiento 10,000 km
  → Próximo: Actual + 10,000 km o +6 meses

- Mantenimiento mayor (20,000 km)
  → Próximo: Actual + 20,000 km o +12 meses
```

#### Para CORRECTIVO:
```
- Reparación de motor
  → Próximo: +1 mes (revisión de garantía)

- Cambio de llantas
  → Próximo: Según desgaste estimado

- Reparación sistema eléctrico
  → Próximo: +15 días (verificación)
```

### Ajuste por Tipo de Vehículo

#### Motocicleta Personal (uso urbano)
- Intervalo estándar: 5,000 km o 6 meses
- Lo que ocurra primero

#### Motocicleta Personal (uso carretera)
- Intervalo estándar: 8,000 km o 6 meses
- Desgaste más rápido

#### Mototaxi (servicio de reparto)
- Intervalo REDUCIDO: 3,000 km o 3 meses
- Uso intensivo requiere mayor frecuencia
- **⚠️ Crítico**: Este tipo de vehículo necesita seguimiento más cercano

#### Mototaxi (servicio de pasajeros)
- Intervalo: 4,000 km o 4 meses
- Uso intensivo pero menos que reparto

## Reglas de Negocio

### Generación de Recordatorio Automático

#### Cuando programar alerta:
1. ✅ **Por fecha**: 7 días antes de fecha recomendada
2. ✅ **Por kilometraje**: Al 90% del km recomendado
3. ✅ **Por tiempo**: Si no visita en 30 días extras → alerta
4. ✅ **Por urgencia**: Si es mototaxi → alertas más frecuentes

### Notificaciones al Cliente

#### Canales de Notificación:
- 📧 Correo electrónico
- 📱 SMS/WhatsApp
- 📞 Llamada telefónica
- 🔔 Notificación push (si tiene app)

#### Contenido del Recordatorio:
```
Estimado [CLIENTE]:

Su [MODELO VEHÍCULO] con placa [PLACA] 
está próximo a su mantenimiento programado.

Fecha recomendada: [FECHA]
Kilometraje recomendado: [KM] km
Trabajos sugeridos: [DESCRIPCIÓN]

Para agendar su cita, contáctenos al [TELÉFONO]

[NOMBRE TALLER]
```

### Priorización de Recordatorios

#### Alta Prioridad (Mototaxis de reparto):
- Recordatorio 10 días antes
- Segundo recordatorio 3 días antes
- Llamada telefónica si no agenda

#### Prioridad Media (Uso intensivo):
- Recordatorio 7 días antes
- Segundo recordatorio 1 día antes

#### Prioridad Normal (Uso personal):
- Recordatorio 7 días antes
- Recordatorio el día de la fecha

## Funcionalidades Especiales

### Plan de Mantenimiento Inteligente

#### Análisis Histórico
- Revisar frecuencia real de visitas
- Ajustar recomendaciones según comportamiento
- Identificar clientes puntuales vs irregulares

#### Recomendaciones Personalizadas
Basado en:
- Historial de reparaciones
- Problemas recurrentes
- Edad del vehículo
- Estilo de conducción (inferido)

### Seguimiento de Cumplimiento

#### Indicadores
- ✅ Cliente vino en fecha sugerida
- ⚠️ Cliente vino con retraso (cuántos días)
- 🔴 Cliente no ha venido (perdido)
- 📊 Tasa de cumplimiento por cliente

### Gestión de Citas

#### Integración con Agenda
- Pre-agendar cita sugerida
- Enviar invitación de calendario
- Recordatorios automáticos
- Confirmación de asistencia

## Alertas del Sistema

### Alertas Operativas
- 🔔 Cliente próximo a mantenimiento
- ⚠️ Cliente con mantenimiento vencido
- 🔴 Mototaxi con mantenimiento crítico vencido
- 📊 Cliente no responde a recordatorios

### Alertas Comerciales
- 💎 Cliente frecuente próximo a visita
- 🆕 Cliente nuevo - primera revisión
- ⏰ Cliente inactivo - última visita hace X meses
- 🎯 Oportunidad de venta (servicio mayor próximo)

## Validaciones

### Controles Automáticos
1. ✅ Fecha próxima no puede ser anterior a fecha actual
2. ✅ Kilometraje próximo debe ser mayor al actual
3. ✅ Intervalo mínimo: 500 km o 15 días
4. ✅ Intervalo máximo: según tipo de vehículo
5. ✅ Alertar si intervalo es inusual

## Métricas y Análisis

### KPIs de Mantenimiento Preventivo
- **Tasa de retención**: % clientes que regresan
- **Cumplimiento**: % que vienen en fecha sugerida
- **Días promedio de retraso**: Análisis de puntualidad
- **Vehículos sin programación**: Oportunidades perdidas

### Por Tipo de Vehículo
- Frecuencia real de mantenimiento
- Comparación con recomendado
- Análisis de desgaste
- Patrones de uso

## Vinculación con Otros Módulos

### Integración con:
- **Orden de Trabajo**: Al finalizar orden, programar próxima
- **Cliente**: Perfil de cumplimiento
- **Vehículo**: Historial de mantenimientos
- **Marketing**: Campañas de recordatorio
- **CRM**: Gestión de relación con cliente

## Documentación de Entrega

### Incluir en Orden Final
- ✅ Fecha de próxima revisión
- ✅ Kilometraje recomendado
- ✅ Trabajos sugeridos
- ✅ Importancia del mantenimiento preventivo
- ✅ Forma de agendar cita

### Sticker Recordatorio (Opcional)
Colocar en vehículo:
```
PRÓXIMO MANTENIMIENTO:
Fecha: [FECHA]
Km: [KILOMETRAJE]
Tel: [TELÉFONO TALLER]
```

## Casos Especiales

### Vehículos de Flota
- Programación centralizada
- Recordatorios al administrador
- Descuentos por programación anticipada
- Coordinación de múltiples unidades

### Vehículos en Garantía
- Seguimiento estricto de mantenimientos
- No perder garantía por falta de servicio
- Alertas especiales
- Documentación para garantía

### Vehículos con Problemas Recurrentes
- Intervalo reducido
- Seguimiento más cercano
- Revisiones específicas
- Evaluación de causa raíz

## Reportes Relacionados
- Vehículos próximos a mantenimiento (próximos 7/15/30 días)
- Mantenimientos vencidos
- Clientes inactivos
- Tasa de cumplimiento de programación
- Análisis de intervalos reales vs recomendados
- Efectividad de recordatorios
- Clientes perdidos (no regresan)
- Proyección de demanda (servicios programados)
- Análisis por tipo de vehículo
- Oportunidades comerciales

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Programación Automática - Mantenimiento Preventivo
**Objetivo**: Verificar cálculo de próxima revisión

**Pre-condiciones**:
- Trabajo: "Mantenimiento 5,000 km"
- Kilometraje actual: 8,500 km

**Pasos**:
1. Completar trabajo preventivo
2. Sistema calcula próxima revisión

**Resultado Esperado**:
- ✅ Fecha sugerida: +3 meses
- ✅ Kilometraje sugerido: 13,500 km
- ✅ Tipo: Preventivo
- ✅ Lo que ocurra primero

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Recordatorio Automático por Fecha
**Objetivo**: Verificar alerta 7 días antes

**Pre-condiciones**:
- Próxima revisión: 15/02/2026
- Fecha actual: 08/02/2026

**Pasos**:
1. Sistema ejecuta proceso de alertas
2. Verificar notificaciones

**Resultado Esperado**:
- 🔔 Recordatorio generado
- 📧 Correo enviado al cliente
- 📱 SMS/WhatsApp enviado
- ✅ Registro de envío guardado

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Recordatorio por Kilometraje (90%)
**Objetivo**: Verificar alerta preventiva

**Pre-condiciones**:
- Próxima revisión: 15,000 km
- Kilometraje actual: 13,600 km (91%)

**Pasos**:
1. Actualizar kilometraje del vehículo
2. Sistema evalúa alertas

**Resultado Esperado**:
- 🔔 Alerta: "Próximo a mantenimiento (91%)"
- ⚠️ Sugiere agendar cita pronto
- ✅ Notificación al cliente
- ✅ 400 km restantes indicados

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Ajuste por Tipo de Vehículo - Mototaxi
**Objetivo**: Verificar intervalo reducido para uso intensivo

**Pre-condiciones**:
- Tipo: Mototaxi (servicio reparto)
- Último mantenimiento: 3,000 km

**Pasos**:
1. Completar mantenimiento
2. Ver próxima revisión sugerida

**Resultado Esperado**:
- ✅ Intervalo reducido: 3,000 km (no 5,000 km)
- ✅ Próximo: 6,000 km
- ⚠️ Alerta más frecuentes
- ✅ Seguimiento más cercano

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Cliente No Responde - Segundo Recordatorio
**Objetivo**: Verificar recordatorios escalonados

**Pre-condiciones**:
- Recordatorio enviado hace 5 días
- Cliente no respondió

**Pasos**:
1. Sistema detecta no respuesta
2. Envía segundo recordatorio

**Resultado Esperado**:
- 📞 Segundo recordatorio enviado
- ⚠️ Tono más urgente
- ✅ Opción de llamada telefónica sugerida
- ✅ Registro de intentos

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Mantenimiento Vencido - Alta Prioridad
**Objetivo**: Verificar alerta cuando se pasa la fecha

**Pre-condiciones**:
- Próxima revisión: 01/02/2026
- Fecha actual: 13/02/2026 (12 días de retraso)

**Pasos**:
1. Ver alertas del sistema
2. Revisar lista de vencidos

**Resultado Esperado**:
- 🔴 Alerta crítica: "Mantenimiento vencido (12 días)"
- 🔴 Cliente en lista de prioridad
- 📞 Llamada telefónica sugerida
- ⚠️ Riesgo de pérdida del cliente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Cliente Cumplió - Actualizar Historial
**Objetivo**: Verificar registro de cumplimiento

**Pre-condiciones**:
- Cliente agendado vino en fecha sugerida

**Pasos**:
1. Completar mantenimiento
2. Actualizar historial de cumplimiento

**Resultado Esperado**:
- ✅ Marcado como: "Cumplió en fecha"
- ✅ Tasa de cumplimiento actualizada
- 🟢 Cliente confiable identificado
- ✅ Programar próxima revisión

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Contenido del Recordatorio
**Objetivo**: Verificar personalización del mensaje

**Pre-condiciones**:
- Cliente: Juan Pérez
- Vehículo: Honda CB190R - ABC-123
- Próxima fecha: 20/02/2026

**Pasos**:
1. Generar recordatorio
2. Revisar contenido

**Resultado Esperado**:
- ✅ Saludo personalizado: "Estimado Juan"
- ✅ Datos del vehículo incluidos
- ✅ Fecha sugerida clara
- ✅ Trabajos sugeridos listados
- ✅ Contacto del taller
- ✅ Link para agendar (si aplica)

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Proyección de Demanda
**Objetivo**: Verificar análisis de servicios próximos

**Pre-condiciones**:
- Múltiples vehículos con próximas revisiones

**Pasos**:
1. Acceder a "Proyección de Demanda"
2. Ver próximos 30 días

**Resultado Esperado**:
- ✅ Cantidad de mantenimientos esperados por semana
- ✅ Tipo de servicios más frecuentes
- ✅ Carga de trabajo proyectada
- ✅ Útil para planificación de recursos
- ✅ Gráfico de distribución

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Reporte - Tasa de Cumplimiento
**Objetivo**: Verificar análisis de efectividad

**Pre-condiciones**:
- Historial de programaciones

**Pasos**:
1. Acceder a reportes
2. "Tasa de Cumplimiento"
3. Período: Último trimestre
4. Generar

**Resultado Esperado**:
- ✅ % clientes que cumplen en fecha: 75%
- ✅ Promedio días de retraso: 5 días
- ✅ Clientes puntuales vs impuntuales
- ✅ Efectividad de recordatorios: 80%
- ✅ Clientes perdidos: 3%

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Programación Automática | Cálculo | Alta |
| 2 | Recordatorio por Fecha | Funcional | Alta |
| 3 | Recordatorio por Km | Funcional | Alta |
| 4 | Ajuste Mototaxi | Lógica | Media |
| 5 | Segundo Recordatorio | Funcional | Media |
| 6 | Mantenimiento Vencido | Alerta | Alta |
| 7 | Cliente Cumplió | Funcional | Media |
| 8 | Contenido Recordatorio | Funcional | Media |
| 9 | Proyección Demanda | Análisis | Media |
| 10 | Tasa Cumplimiento | Reporte | Media |

**Total**: 10 casos de prueba

