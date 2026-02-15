# MÓDULO 6: DIAGNÓSTICO Y TRABAJOS

## Objetivo
Registrar el motivo de ingreso del cliente, realizar el diagnóstico técnico y definir los trabajos necesarios a ejecutar.

## 6.1 Motivo del Cliente

### Descripción del Problema
- Campo de texto libre
- Permite que el cliente explique con sus palabras
- Registro de síntomas reportados
- Fecha y hora del reporte
- Asesor que registró la información

### Ejemplos de Motivos Comunes
- "La moto hace un ruido extraño al frenar"
- "Se apaga cuando está en ralentí"
- "Pierde aceite"
- "Mantenimiento preventivo de 5,000 km"
- "No enciende el motor"

## 6.2 Diagnóstico Técnico

### Información del Diagnóstico
- Descripción técnica del problema
- Causa raíz identificada
- Sistemas afectados
- Gravedad: Leve / Moderada / Grave / Crítica
- Mecánico que realizó el diagnóstico
- Tiempo empleado en diagnóstico
- Evidencias (fotos, videos)

### Relación con Inspección
- Vincular hallazgos de inspección inicial
- Confirmar o ampliar observaciones previas
- Detectar problemas no reportados por el cliente

## 6.3 Trabajos a Realizar

### Agregar Múltiples Trabajos
Cada trabajo debe contener:
- **Código**: Identificador único
- **Descripción**: Detalle del trabajo a realizar
- **Tipo de trabajo**:
  - Preventivo
  - Correctivo
- **Prioridad**: Baja / Media / Alta / Crítica
- **Tiempo estimado**: Horas/minutos
- **Costo estimado mano de obra**
- **Requiere repuestos**: Sí / No
- **Estado**: Pendiente / En proceso / Completado

## Reglas de Negocio

### Lógica Avanzada

#### Si el trabajo es PREVENTIVO:
- ✅ Se sugiere próxima fecha automática
- ✅ Se calcula según:
  - Kilometraje recomendado
  - Tiempo recomendado
  - Historial del vehículo
- ✅ Se programa recordatorio
- ✅ Se asocia a plan de mantenimiento

#### Si el trabajo es CORRECTIVO:
- ✅ Se vincula a falla detectada
- ✅ Se registra causa raíz
- ✅ Se evalúa si está en garantía
- ✅ Prioridad generalmente mayor
- ✅ Puede generar orden adicional si es complejo

## Clasificación de Trabajos

### Trabajos Preventivos Comunes
- Cambio de aceite y filtro
- Revisión de frenos
- Ajuste de cadena
- Limpieza de carburador/inyectores
- Cambio de bujía
- Revisión de suspensión
- Calibración de válvulas

### Trabajos Correctivos Comunes
- Reparación de motor
- Cambio de embrague
- Reparación de sistema eléctrico
- Reparación de frenos
- Cambio de llanta
- Reparación de escape
- Soldadura de chasis

## Funcionalidades Especiales

### Trabajos Sugeridos Automáticamente
Basado en:
- Kilometraje actual
- Último mantenimiento
- Historial del vehículo
- Modelo y marca
- Inspección realizada

### Paquetes de Mantenimiento
- Definir paquetes predefinidos
- Ej: "Mantenimiento 5,000 km"
- Agregar múltiples trabajos de una vez
- Precio paquete vs individual

### Estimación de Tiempo Total
- Suma automática de tiempos por trabajo
- Considerar trabajos en paralelo
- Calcular fecha estimada de entrega

## Validaciones

### Controles Obligatorios
1. ✅ Al menos un trabajo debe estar registrado
2. ✅ Trabajos críticos deben tener prioridad alta
3. ✅ No avanzar sin diagnóstico completo
4. ✅ Vincular repuestos necesarios por trabajo

## Alertas del Sistema
- ⚠️ Trabajo sin tiempo estimado
- ⚠️ Trabajo crítico sin prioridad alta
- ⚠️ Diagnóstico sin trabajos asociados
- 🔔 Trabajo similar realizado recientemente (posible retrabajo)

## Vinculación con Otros Módulos
- **Repuestos**: Listar repuestos por trabajo
- **Mano de Obra**: Calcular horas por trabajo
- **Mecánico**: Asignar responsable por trabajo
- **Garantía**: Verificar cobertura

## Reportes Relacionados
- Trabajos más frecuentes
- Tiempo promedio por tipo de trabajo
- Trabajos preventivos vs correctivos
- Eficiencia de estimación (estimado vs real)
- Análisis de retrabajos
- Rentabilidad por tipo de trabajo

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Registrar Motivo del Cliente
**Objetivo**: Verificar registro del motivo de ingreso

**Pre-condiciones**:
- Orden de mantenimiento activa
- Inspección completada

**Pasos**:
1. Acceder a "Diagnóstico"
2. Registrar motivo del cliente: "La moto hace ruido al frenar"
3. Guardar

**Resultado Esperado**:
- ✅ Motivo registrado correctamente
- ✅ Fecha y hora de registro guardadas
- ✅ Asesor que registró identificado

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Diagnóstico Técnico Completo
**Objetivo**: Verificar registro de diagnóstico profesional

**Pre-condiciones**:
- Motivo del cliente registrado

**Pasos**:
1. Realizar diagnóstico técnico
2. Descripción: "Pastillas de freno desgastadas, requieren reemplazo"
3. Causa raíz: "Desgaste normal por uso"
4. Gravedad: "Moderada"
5. Mecánico: Seleccionar técnico
6. Tiempo empleado: 30 minutos
7. Guardar

**Resultado Esperado**:
- ✅ Diagnóstico completo registrado
- ✅ Vinculado con inspección inicial
- ✅ Mecánico asignado correctamente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Agregar Múltiples Trabajos
**Objetivo**: Verificar creación de lista de trabajos

**Pre-condiciones**:
- Diagnóstico completado

**Pasos**:
1. Agregar trabajo 1:
   - Código: TRB-001
   - Descripción: "Cambio de pastillas de freno"
   - Tipo: Correctivo
   - Prioridad: Alta
   - Tiempo estimado: 1.5 hrs
2. Agregar trabajo 2:
   - Código: TRB-002
   - Descripción: "Cambio de aceite y filtro"
   - Tipo: Preventivo
   - Prioridad: Media
   - Tiempo estimado: 0.5 hrs
3. Guardar

**Resultado Esperado**:
- ✅ Ambos trabajos registrados
- ✅ Lista de trabajos visible
- ✅ Tiempo total: 2 hrs
- ✅ Permite agregar repuestos por trabajo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Trabajo Preventivo - Sugerencia de Próxima Fecha
**Objetivo**: Verificar cálculo automático de próximo mantenimiento

**Pre-condiciones**:
- Trabajo preventivo registrado

**Pasos**:
1. Crear trabajo: "Mantenimiento 5,000 km"
2. Tipo: Preventivo
3. Guardar

**Resultado Esperado**:
- ✅ Sistema sugiere próxima fecha automáticamente
- ✅ Calcula según kilometraje: actual + 5,000 km
- ✅ O según tiempo: +3 meses
- ✅ Se programa recordatorio automático

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Validación - Al Menos Un Trabajo Requerido
**Objetivo**: Verificar que no se puede avanzar sin trabajos

**Pre-condiciones**:
- Diagnóstico registrado
- Ningún trabajo agregado

**Pasos**:
1. Intentar avanzar a cotización
2. Observar respuesta

**Resultado Esperado**:
- 🔴 Sistema bloquea avance
- 🔴 Error: "Debe registrar al menos un trabajo"
- ⚠️ No permite continuar sin trabajos

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Paquete de Mantenimiento Predefinido
**Objetivo**: Verificar aplicación de paquete

**Pre-condiciones**:
- Paquete "Mantenimiento 5,000 km" configurado

**Pasos**:
1. Seleccionar paquete predefinido
2. Sistema agrega múltiples trabajos automáticamente
3. Revisar trabajos agregados

**Resultado Esperado**:
- ✅ Todos los trabajos del paquete agregados
- ✅ Precio especial de paquete aplicado
- ✅ Tiempo total calculado
- ✅ Facilita cotización rápida

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Alerta - Trabajo Similar Reciente
**Objetivo**: Verificar detección de posible retrabajo

**Pre-condiciones**:
- Vehículo con trabajo "Cambio frenos" hace 15 días

**Pasos**:
1. Agregar nuevo trabajo: "Cambio de frenos"
2. Observar alertas

**Resultado Esperado**:
- 🔔 Alerta: "Trabajo similar realizado hace 15 días"
- ⚠️ Muestra orden previa
- ⚠️ Sugiere verificar garantía
- ✅ Permite continuar pero con advertencia

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Estimación de Fecha de Entrega
**Objetivo**: Verificar cálculo automático

**Pre-condiciones**:
- 3 trabajos con tiempos: 1hr, 2hrs, 1.5hrs

**Pasos**:
1. Ver tiempo total estimado
2. Sistema calcula fecha de entrega

**Resultado Esperado**:
- ✅ Tiempo total: 4.5 hrs
- ✅ Considera disponibilidad de mecánicos
- ✅ Fecha estimada de entrega calculada
- ✅ Muestra al cliente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Vinculación con Repuestos
**Objetivo**: Verificar asociación trabajo-repuestos

**Pre-condiciones**:
- Trabajo "Cambio de frenos" creado

**Pasos**:
1. Abrir trabajo
2. Agregar repuestos necesarios:
   - Pastillas de freno x2
   - Líquido de frenos x1
3. Guardar

**Resultado Esperado**:
- ✅ Repuestos asociados al trabajo
- ✅ Verifica stock disponible
- ✅ Calcula costo total del trabajo
- ✅ Alerta si no hay stock

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Reporte - Trabajos Más Frecuentes
**Objetivo**: Verificar análisis estadístico

**Pre-condiciones**:
- Historial de trabajos en sistema

**Pasos**:
1. Acceder a reportes
2. Seleccionar "Trabajos Más Frecuentes"
3. Período: Último mes
4. Generar

**Resultado Esperado**:
- ✅ Lista ordenada por frecuencia
- ✅ Cantidad de veces realizado
- ✅ Tiempo promedio por trabajo
- ✅ Rentabilidad por trabajo
- ✅ Gráfico de barras

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Registrar Motivo Cliente | Funcional | Alta |
| 2 | Diagnóstico Técnico | Funcional | Alta |
| 3 | Múltiples Trabajos | Funcional | Alta |
| 4 | Trabajo Preventivo | Lógica | Media |
| 5 | Validación Trabajo Requerido | Validación | Alta |
| 6 | Paquete Predefinido | Funcional | Media |
| 7 | Alerta Trabajo Similar | Alerta | Media |
| 8 | Estimación Entrega | Cálculo | Media |
| 9 | Vinculación Repuestos | Funcional | Alta |
| 10 | Reporte Trabajos Frecuentes | Reporte | Baja |

**Total**: 10 casos de prueba

