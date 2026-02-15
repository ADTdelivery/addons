UI# MÓDULO 5: CONTROL DE FLUIDOS

## Objetivo
Verificar y documentar el estado de todos los fluidos del vehículo al momento del ingreso, detectando necesidades de mantenimiento y alertando sobre posibles fallas.

## Fluidos a Controlar

### Para cada fluido se registra:

#### 1. Aceite de Motor
- **Nivel**: Bajo / Normal / Alto
- **Estado**: Limpio / Contaminado / Muy sucio
- **Tipo de fluido**: SAE 10W-30, 20W-50, etc.
- **Última fecha de cambio**
- **Kilometraje del último cambio**

#### 2. Refrigerante
- **Nivel**: Bajo / Normal / Alto
- **Estado**: Limpio / Contaminado / Muy sucio
- **Tipo de fluido**: Tipo específico
- **Última fecha de cambio**

#### 3. Líquido de Frenos
- **Nivel**: Bajo / Normal / Alto
- **Estado**: Limpio / Contaminado / Muy sucio
- **Tipo de fluido**: DOT 3, DOT 4, etc.
- **Última fecha de cambio**

#### 4. Aceite de Transmisión
- **Nivel**: Bajo / Normal / Alto
- **Estado**: Limpio / Contaminado / Muy sucio
- **Tipo de fluido**: Tipo específico
- **Última fecha de cambio**

#### 5. Líquido de Dirección (si aplica)
- **Nivel**: Bajo / Normal / Alto
- **Estado**: Limpio / Contaminado / Muy sucio
- **Tipo de fluido**: Tipo específico

## Reglas de Negocio

### Lógica Automática

#### Si Aceite Contaminado:
- ✅ Sugerir cambio automático en cotización
- ✅ Alertar sobre posible daño al motor
- ✅ Recomendar limpieza de sistema si muy sucio

#### Si Refrigerante Bajo:
- ✅ Alerta preventiva
- ✅ Verificar posibles fugas
- ✅ Incluir en diagnóstico

#### Si Líquido de Frenos Bajo:
- ⚠️ **ALERTA DE SEGURIDAD** (Crítica)
- ✅ Verificar desgaste de pastillas
- ✅ Revisar sistema completo
- ✅ Prioridad alta en reparación

## Alertas del Sistema

### Alertas Críticas (Rojas)
- 🔴 Líquido de frenos bajo (seguridad)
- 🔴 Aceite de motor muy sucio o bajo
- 🔴 Refrigerante contaminado con aceite

### Alertas Preventivas (Amarillas)
- 🟡 Aceite próximo a cambio (por km o tiempo)
- 🟡 Refrigerante nivel bajo
- 🟡 Fluido de transmisión oscuro

### Alertas Informativas (Azules)
- 🔵 Mantenimiento preventivo sugerido
- 🔵 Historial de cambios disponible

## Funcionalidades Especiales

### Cálculo Automático
- Calcular kilometraje desde último cambio
- Calcular días desde último cambio
- Sugerir próximo cambio basado en:
  - Recomendación del fabricante
  - Tipo de uso (urbano, carretera, reparto)
  - Historial del vehículo

### Historial de Fluidos
- Registro de todos los cambios previos
- Análisis de frecuencia
- Comparación con recomendaciones
- Identificar cambios prematuros (posible fuga)

### Sugerencias Inteligentes
Basado en el estado detectado:
- Agregar automáticamente a lista de trabajos
- Calcular costo estimado
- Priorizar según criticidad

## Validaciones

### Controles de Calidad
1. ✅ No permitir nivel "Alto" sin observación
2. ✅ Si estado "Muy sucio" → cambio obligatorio
3. ✅ Validar tipo de fluido con especificaciones del fabricante
4. ✅ Alertar si tiempo desde último cambio es excesivo

## Información Complementaria

### Datos Adicionales
- Marca del fluido utilizado
- Proveedor
- Costo del servicio
- Filtros cambiados (si aplica)
- Observaciones del técnico

## Reportes Relacionados
- Consumo de fluidos por vehículo
- Frecuencia de cambios por modelo
- Análisis de calidad de fluidos
- Vehículos con cambios pendientes
- Estadísticas de contaminación
- Alertas de seguridad generadas

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Registro de Control de Fluidos Completo
**Objetivo**: Verificar registro de todos los fluidos

**Pre-condiciones**:
- Orden de mantenimiento activa

**Pasos**:
1. Acceder a "Control de Fluidos"
2. Registrar aceite motor: Nivel=Bajo, Estado=Contaminado
3. Registrar refrigerante: Nivel=Normal, Estado=Limpio
4. Registrar líquido frenos: Nivel=Bajo, Estado=Limpio
5. Registrar aceite transmisión: Nivel=Normal, Estado=Limpio
6. Guardar

**Resultado Esperado**:
- ✅ Todos los fluidos registrados
- ⚠️ Alerta: "Aceite motor bajo y contaminado"
- ⚠️ Alerta seguridad: "Líquido frenos bajo"
- ✅ Sugerencias automáticas de cambio

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Alerta Crítica - Líquido de Frenos Bajo
**Objetivo**: Verificar alerta de seguridad crítica

**Pre-condiciones**:
- Control de fluidos en proceso

**Pasos**:
1. Registrar líquido de frenos
2. Nivel: Bajo
3. Guardar

**Resultado Esperado**:
- 🔴 Alerta crítica roja: "LÍQUIDO DE FRENOS BAJO - SEGURIDAD"
- 🔴 Requiere verificación inmediata
- ✅ Se agrega a trabajos urgentes
- ⚠️ Prioridad automática: Alta

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Aceite Contaminado - Sugerencia Automática
**Objetivo**: Verificar sugerencia de cambio por contaminación

**Pre-condiciones**:
- Control de fluidos activo

**Pasos**:
1. Registrar aceite motor
2. Estado: "Muy sucio"
3. Guardar

**Resultado Esperado**:
- ✅ Sugerencia automática: "Cambio de aceite y filtro"
- ⚠️ Alerta: "Posible daño al motor si no se cambia"
- ✅ Se incluye en cotización automática
- ✅ Recomendación de limpieza de sistema

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Cálculo Automático - Próximo Cambio de Aceite
**Objetivo**: Verificar cálculo de próximo cambio

**Pre-condiciones**:
- Vehículo con kilometraje: 8,500 km
- Último cambio: 3,500 km

**Pasos**:
1. Registrar cambio de aceite actual
2. Sistema calcula intervalo
3. Observar recomendación

**Resultado Esperado**:
- ✅ Kilometraje desde último cambio: 5,000 km
- ✅ Próximo cambio sugerido: 13,500 km (actual + 5,000)
- ✅ O fecha: 3 meses desde hoy
- ✅ Lo que ocurra primero

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Historial de Cambios de Fluidos
**Objetivo**: Verificar registro histórico

**Pre-condiciones**:
- Vehículo con 5+ cambios de aceite previos

**Pasos**:
1. Abrir control de fluidos
2. Acceder a "Historial"
3. Ver cambios previos

**Resultado Esperado**:
- ✅ Lista todos los cambios previos
- ✅ Muestra fechas y kilometrajes
- ✅ Muestra tipo de fluido usado
- ✅ Análisis de frecuencia
- ✅ Comparación con recomendaciones

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Refrigerante Contaminado con Aceite
**Objetivo**: Verificar alerta crítica de contaminación cruzada

**Pre-condiciones**:
- Control de fluidos activo

**Pasos**:
1. Registrar refrigerante
2. Estado: "Contaminado con aceite"
3. Guardar

**Resultado Esperado**:
- 🔴 Alerta crítica: "Refrigerante contaminado con aceite"
- 🔴 Indica posible fuga interna grave
- ⚠️ Sugiere revisión urgente de motor
- ✅ Prioridad: Crítica

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Validación - Nivel Alto sin Observación
**Objetivo**: Verificar validación cuando nivel es anormal

**Pre-condiciones**:
- Control de fluidos en proceso

**Pasos**:
1. Registrar fluido
2. Nivel: "Alto" (anormal)
3. NO agregar observación
4. Intentar guardar

**Resultado Esperado**:
- ⚠️ Advertencia: "Nivel alto requiere observación"
- ⚠️ Solicita explicación
- ✅ Permite continuar con observación
- 🔴 No permite guardar sin justificación

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Reporte - Consumo de Fluidos por Vehículo
**Objetivo**: Verificar análisis de consumo

**Pre-condiciones**:
- Vehículo con historial de cambios

**Pasos**:
1. Acceder a "Reportes"
2. Seleccionar "Consumo por Vehículo"
3. Seleccionar vehículo
4. Generar reporte

**Resultado Esperado**:
- ✅ Muestra consumo de cada fluido
- ✅ Frecuencia de cambios
- ✅ Costo acumulado por fluido
- ✅ Comparación con promedio del modelo
- ✅ Gráfico de tendencia

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Registro Completo Fluidos | Funcional | Alta |
| 2 | Alerta Frenos Bajo | Alerta Crítica | Alta |
| 3 | Aceite Contaminado | Lógica | Alta |
| 4 | Cálculo Próximo Cambio | Cálculo | Media |
| 5 | Historial de Cambios | Análisis | Media |
| 6 | Refrigerante Contaminado | Alerta Crítica | Alta |
| 7 | Validación Nivel Alto | Validación | Media |
| 8 | Reporte Consumo | Reporte | Baja |

**Total**: 8 casos de prueba

