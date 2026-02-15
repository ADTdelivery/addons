# MÓDULO 8: MANO DE OBRA

## Objetivo
Registrar, calcular y controlar los costos de mano de obra asociados a cada trabajo realizado, además de evaluar la eficiencia de los mecánicos.

## Información de Mano de Obra

### Campos Principales
- **Descripción**: Detalle del trabajo de mano de obra
- **Horas estimadas**: Tiempo calculado para el trabajo
- **Horas reales**: Tiempo efectivamente empleado
- **Precio por hora**: Tarifa según tipo de trabajo
- **Subtotal**: Horas × Precio por hora (calculado)
- **Mecánico asignado**: Responsable del trabajo
- **Tipo de trabajo**: Preventivo / Correctivo / Diagnóstico
- **Complejidad**: Baja / Media / Alta / Experta
- **Fecha inicio**: Cuándo comenzó el trabajo
- **Fecha fin**: Cuándo terminó el trabajo

## Cálculo de Eficiencia

### Fórmula Principal
```
Eficiencia = (Horas estimadas / Horas reales) × 100%
```

### Interpretación
- **> 100%**: Trabajo realizado más rápido de lo esperado ✅
- **= 100%**: Trabajo dentro del tiempo estimado ✅
- **< 100%**: Trabajo demoró más de lo esperado ⚠️
- **< 80%**: Requiere análisis (posible problema) 🔴

## Reglas de Negocio

### Validaciones Críticas

#### 1. Registro de Horas Reales
- ✅ Obligatorio registrar al completar trabajo
- ✅ No puede ser cero
- ✅ Validar rango razonable
- ✅ Alertar si difiere mucho de estimado

#### 2. Cálculo de Eficiencia
- ✅ Calculado automáticamente
- ✅ Impacta evaluación del mecánico
- ✅ Afecta futuras estimaciones
- ✅ Genera alertas si es muy baja

#### 3. Evaluación del Mecánico
- ✅ Eficiencia promedio acumulada
- ✅ Historial de trabajos
- ✅ Especialización por tipo de trabajo
- ✅ Cantidad de retrabajos
- ✅ Calificación de clientes

## Tipos de Mano de Obra

### Clasificación por Complejidad

#### Nivel Básico
- Cambio de aceite
- Cambio de filtros
- Ajustes menores
- Limpieza
- **Tarifa**: Estándar

#### Nivel Intermedio
- Cambio de pastillas de freno
- Ajuste de cadena y piñones
- Cambio de bujías
- Limpieza de carburador
- **Tarifa**: Estándar + 20%

#### Nivel Avanzado
- Reparación de motor
- Cambio de embrague
- Reparación sistema eléctrico
- Sincronización
- **Tarifa**: Estándar + 50%

#### Nivel Experto
- Rectificación de motor
- Programación de ECU
- Diagnóstico complejo
- Trabajos especializados
- **Tarifa**: Estándar + 100%

## Funcionalidades Especiales

### Tarifas Dinámicas
- Por tipo de trabajo
- Por complejidad
- Por mecánico (nivel de experiencia)
- Por horario (normal / nocturno / festivo)
- Por tipo de cliente (normal / VIP / flota)

### Control de Tiempo
- Registro de inicio/fin real
- Tiempo en pausa (interrupciones)
- Tiempo efectivo de trabajo
- Alertas de tiempo excedido
- Comparativo estimado vs real

### Análisis de Productividad
- Trabajos completados por día
- Eficiencia promedio
- Tiempo promedio por tipo de trabajo
- Identificar cuellos de botella
- Comparación entre mecánicos

## Validaciones Adicionales

### Controles de Calidad
1. ✅ Horas reales no pueden exceder 2× las estimadas sin justificación
2. ✅ Precio por hora debe estar dentro del rango establecido
3. ✅ Mecánico debe estar activo y disponible
4. ✅ Trabajo debe estar asignado antes de iniciar
5. ✅ No permitir finalizar sin registrar horas reales

## Alertas del Sistema

### Alertas de Eficiencia
- 🔴 Eficiencia < 70% (crítico)
- 🟡 Eficiencia entre 70-90% (revisar)
- 🟢 Eficiencia > 100% (excelente)
- ⚠️ Tiempo excedido significativamente

### Alertas de Productividad
- 📊 Mecánico con baja productividad
- 🎯 Meta de eficiencia alcanzada
- 🏆 Mecánico destacado del mes
- ⏰ Trabajo en proceso hace más de tiempo estimado

### Alertas de Costo
- 💰 Costo de mano de obra excede presupuesto
- 📈 Aumento inusual en horas
- 🔔 Trabajo requiere aprobación (alto costo)

## Comisiones y Bonificaciones

### Sistema de Incentivos
- Comisión por trabajo completado
- Bonificación por eficiencia
- Bonificación por calidad (sin retrabajo)
- Bonificación por satisfacción del cliente
- Penalización por retrabajo

### Cálculo de Comisiones
```
Comisión = Base × Factor eficiencia × Factor calidad
```

## Vinculación con Otros Módulos

### Integración con:
- **Trabajos**: Cada trabajo tiene su mano de obra
- **Mecánicos**: Evaluación y seguimiento
- **Costos**: Cálculo de rentabilidad
- **Facturación**: Desglose de mano de obra
- **Recursos Humanos**: Productividad y pago

## Historial y Aprendizaje

### Mejora Continua
- Análisis de tiempos históricos
- Ajuste de estimaciones futuras
- Identificación de trabajos problemáticos
- Optimización de procesos
- Capacitación basada en datos

## Reportes Relacionados
- Eficiencia por mecánico
- Productividad diaria/semanal/mensual
- Horas trabajadas vs estimadas
- Análisis de costos de mano de obra
- Trabajos más rentables
- Comparativo entre mecánicos
- Evolución de eficiencia en el tiempo
- Comisiones ganadas
- Análisis de especialización
- Tiempos promedio por tipo de trabajo

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Registrar Mano de Obra con Estimación
**Objetivo**: Verificar registro de trabajo con tiempo estimado

**Pre-condiciones**:
- Trabajo "Cambio de frenos" creado

**Pasos**:
1. Agregar mano de obra
2. Descripción: "Cambio de pastillas de freno"
3. Horas estimadas: 1.5
4. Precio por hora: S/. 30
5. Mecánico: Juan Pérez
6. Guardar

**Resultado Esperado**:
- ✅ Mano de obra registrada
- ✅ Subtotal calculado: 1.5 × 30 = S/. 45
- ✅ Mecánico asignado
- ✅ Estado: Pendiente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Registrar Horas Reales y Calcular Eficiencia
**Objetivo**: Verificar cálculo automático de eficiencia

**Pre-condiciones**:
- Trabajo completado
- Horas estimadas: 2 hrs
- Horas reales: 1.8 hrs

**Pasos**:
1. Registrar horas reales: 1.8
2. Guardar
3. Ver cálculo de eficiencia

**Resultado Esperado**:
- ✅ Eficiencia = (2 / 1.8) × 100% = 111%
- ✅ Indicador verde (> 100%)
- ✅ Mecánico trabajó más rápido
- ✅ Eficiencia registrada en historial

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Alerta - Eficiencia Baja (<70%)
**Objetivo**: Verificar alerta cuando eficiencia es crítica

**Pre-condiciones**:
- Horas estimadas: 2 hrs
- Horas reales: 3 hrs

**Pasos**:
1. Registrar horas reales
2. Sistema calcula: (2/3) × 100% = 67%
3. Observar alertas

**Resultado Esperado**:
- 🔴 Alerta crítica: "Eficiencia < 70%"
- ⚠️ Requiere análisis
- ⚠️ Sugiere revisión del proceso
- ✅ Notificación a supervisor

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Validación - Horas Reales Obligatorias
**Objetivo**: Verificar que no se puede completar sin horas reales

**Pre-condiciones**:
- Trabajo en proceso

**Pasos**:
1. Intentar marcar trabajo como completado
2. NO registrar horas reales
3. Guardar

**Resultado Esperado**:
- 🔴 Error: "Debe registrar horas reales antes de completar"
- 🔴 No permite finalizar
- ⚠️ Campo horas reales obligatorio

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Tarifas Dinámicas por Complejidad
**Objetivo**: Verificar aplicación de tarifa según nivel

**Pre-condiciones**:
- Configuración de tarifas

**Pasos**:
1. Trabajo básico: S/. 30/hora
2. Trabajo avanzado: S/. 45/hora (Estándar +50%)
3. Ver aplicación

**Resultado Esperado**:
- ✅ Tarifa correcta según complejidad
- ✅ Cálculo automático de subtotal
- ✅ Diferenciación visible en cotización

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Cálculo de Comisión por Eficiencia
**Objetivo**: Verificar bonificación por buen desempeño

**Pre-condiciones**:
- Mecánico con eficiencia 105%
- Comisión base: 10% del valor mano de obra

**Pasos**:
1. Completar trabajo
2. Sistema calcula comisión
3. Ver monto

**Resultado Esperado**:
- ✅ Comisión base calculada
- ✅ Bonificación por eficiencia > 100%
- ✅ Total de comisión correcto
- ✅ Registrado para pago

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Alerta - Tiempo Excedido Significativamente
**Objetivo**: Verificar alerta cuando se excede estimación

**Pre-condiciones**:
- Horas estimadas: 1 hr
- Horas reales: 2.5 hrs (250% del estimado)

**Pasos**:
1. Registrar horas reales
2. Observar alertas

**Resultado Esperado**:
- ⚠️ Alerta: "Tiempo excedido más del doble"
- ⚠️ Requiere justificación
- ⚠️ Campo observaciones obligatorio
- ✅ Registro para análisis

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Control de Tiempo con Pausas
**Objetivo**: Verificar registro de tiempo efectivo

**Pre-condiciones**:
- Trabajo en proceso

**Pasos**:
1. Inicio: 09:00
2. Pausa: 10:30-11:00 (30 min)
3. Fin: 12:00
4. Calcular tiempo efectivo

**Resultado Esperado**:
- ✅ Tiempo total: 3 hrs
- ✅ Tiempo en pausa: 0.5 hrs
- ✅ Tiempo efectivo: 2.5 hrs
- ✅ Solo tiempo efectivo cuenta para eficiencia

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Reporte - Eficiencia por Mecánico
**Objetivo**: Verificar análisis comparativo

**Pre-condiciones**:
- 3 mecánicos con trabajos completados

**Pasos**:
1. Acceder a reportes
2. "Eficiencia por Mecánico"
3. Período: Último mes
4. Generar

**Resultado Esperado**:
- ✅ Lista de mecánicos con eficiencia promedio
- ✅ Comparación visual (gráfico)
- ✅ Ranking de desempeño
- ✅ Identificar mejores y áreas de mejora

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Ajuste de Estimaciones Futuras
**Objetivo**: Verificar aprendizaje del sistema

**Pre-condiciones**:
- Trabajo "Cambio de aceite" realizado 10 veces
- Tiempo real promedio: 25 minutos

**Pasos**:
1. Crear nueva orden con "Cambio de aceite"
2. Ver tiempo estimado sugerido

**Resultado Esperado**:
- ✅ Sistema sugiere 25 min (basado en histórico)
- ✅ No usa estimación genérica
- ✅ Mejora precisión con el tiempo
- ✅ Considera histórico del taller

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Registrar Mano de Obra | Funcional | Alta |
| 2 | Calcular Eficiencia | Cálculo | Alta |
| 3 | Alerta Eficiencia Baja | Alerta | Alta |
| 4 | Validación Horas Reales | Validación | Alta |
| 5 | Tarifas Dinámicas | Lógica | Media |
| 6 | Cálculo Comisión | Cálculo | Media |
| 7 | Alerta Tiempo Excedido | Alerta | Media |
| 8 | Control Tiempo con Pausas | Funcional | Media |
| 9 | Reporte Eficiencia | Reporte | Media |
| 10 | Ajuste Estimaciones | Análisis | Baja |

**Total**: 10 casos de prueba

