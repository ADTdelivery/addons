# MÓDULO 1: ORDEN DE MANTENIMIENTO

## Objetivo
Gestionar la información general de cada orden de mantenimiento que ingresa al taller.

## Información General

### Campos Obligatorios
- **Número de Orden**: Autogenerado por el sistema
- **Fecha y hora de ingreso**: Registro automático del momento de creación
- **Tipo de servicio**:
  - Preventivo
  - Correctivo
  - Predictivo
  - Emergencia
  - Garantía
- **Nivel de prioridad**:
  - Baja
  - Media
  - Alta
  - Crítica
- **Sucursal**: Ubicación donde se realiza el servicio
- **Asesor de servicio**: Responsable de la atención al cliente

## Reglas de Negocio

### Validaciones Críticas
1. ✅ No puede crearse orden sin vehículo registrado
2. ✅ Si es tipo "Garantía" → debe validar orden anterior
3. ✅ Si es "Emergencia" → prioridad automática Alta o Crítica
4. ✅ Toda orden debe tener asesor responsable

## Flujo de Trabajo
1. Cliente llega con vehículo
2. Asesor crea nueva orden
3. Sistema asigna número automático
4. Se registra información general
5. Se vincula con vehículo y cliente
6. Se avanza a módulo de inspección

## Alertas
- ⚠️ Vehículo sin registro previo
- ⚠️ Cliente con crédito atrasado
- ⚠️ Orden de garantía sin orden previa válida
- ⚠️ Emergencia sin prioridad alta

## Reportes Relacionados
- Órdenes por tipo de servicio
- Órdenes por prioridad
- Órdenes por asesor
- Órdenes por sucursal
- Tiempo promedio por tipo de servicio

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Crear Orden Normal
**Objetivo**: Verificar creación básica de orden de mantenimiento

**Pre-condiciones**:
- Usuario con permisos de asesor de servicio
- Vehículo registrado en el sistema
- Cliente registrado

**Pasos**:
1. Acceder a menú "Órdenes de Mantenimiento"
2. Clic en "Crear"
3. Seleccionar vehículo existente
4. Seleccionar tipo de servicio: "Preventivo"
5. Seleccionar prioridad: "Media"
6. Seleccionar sucursal
7. Guardar

**Resultado Esperado**:
- ✅ Sistema genera número de orden automáticamente (ej: OM-00001)
- ✅ Fecha y hora se registran automáticamente
- ✅ Estado inicial: "Registrada"
- ✅ Asesor se asigna automáticamente (usuario actual)
- ✅ Orden se guarda exitosamente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Validación - Orden sin Vehículo
**Objetivo**: Verificar que no se puede crear orden sin vehículo

**Pre-condiciones**:
- Usuario con permisos de asesor de servicio

**Pasos**:
1. Acceder a menú "Órdenes de Mantenimiento"
2. Clic en "Crear"
3. NO seleccionar vehículo
4. Llenar tipo de servicio: "Correctivo"
5. Llenar prioridad: "Alta"
6. Intentar guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "El vehículo es obligatorio"
- 🔴 No se permite guardar la orden
- 🔴 Usuario permanece en el formulario

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Orden de Emergencia - Prioridad Automática
**Objetivo**: Verificar que emergencia establece prioridad alta automáticamente

**Pre-condiciones**:
- Usuario con permisos de asesor de servicio
- Vehículo registrado

**Pasos**:
1. Crear nueva orden
2. Seleccionar vehículo
3. Seleccionar tipo de servicio: "Emergencia"
4. NO seleccionar prioridad manualmente
5. Guardar

**Resultado Esperado**:
- ✅ Sistema automáticamente establece prioridad: "Alta" o "Crítica"
- ⚠️ Sistema muestra alerta: "Emergencia detectada - Prioridad alta asignada"
- ✅ Orden se guarda con prioridad automática

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Orden de Garantía - Validación Orden Previa
**Objetivo**: Verificar validación de orden previa para garantía

**Pre-condiciones**:
- Vehículo con orden previa completada hace menos de X días
- Usuario con permisos

**Pasos**:
1. Crear nueva orden
2. Seleccionar vehículo con historial
3. Seleccionar tipo de servicio: "Garantía"
4. Sistema debe buscar orden previa
5. Guardar

**Resultado Esperado**:
- ✅ Sistema encuentra orden previa válida
- ✅ Sistema vincula orden de garantía con orden original
- ✅ Muestra información de orden previa
- ✅ Permite continuar

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Orden de Garantía - Sin Orden Previa Válida
**Objetivo**: Verificar rechazo de garantía sin orden previa

**Pre-condiciones**:
- Vehículo sin órdenes previas o fuera de período de garantía

**Pasos**:
1. Crear nueva orden
2. Seleccionar vehículo sin historial válido
3. Seleccionar tipo de servicio: "Garantía"
4. Intentar guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "No existe orden previa válida para garantía"
- 🔴 No permite guardar como garantía
- ⚠️ Sugiere cambiar tipo de servicio

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Alerta - Cliente con Crédito Atrasado
**Objetivo**: Verificar alerta cuando cliente tiene crédito atrasado

**Pre-condiciones**:
- Cliente con crédito financiero en estado "Atrasado"
- Vehículo asociado a ese cliente

**Pasos**:
1. Crear nueva orden
2. Seleccionar vehículo de cliente con crédito atrasado
3. Observar alertas del sistema

**Resultado Esperado**:
- ⚠️ Sistema muestra alerta roja visible: "Cliente con crédito atrasado"
- ⚠️ Muestra información del crédito y entidad financiera
- ✅ Permite continuar pero con advertencia registrada
- ✅ Alerta queda visible en toda la orden

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Numeración Automática Secuencial
**Objetivo**: Verificar que números de orden son secuenciales

**Pre-condiciones**:
- Al menos una orden existente

**Pasos**:
1. Consultar última orden creada (ej: OM-00050)
2. Crear nueva orden
3. Guardar
4. Verificar número asignado

**Resultado Esperado**:
- ✅ Nuevo número es secuencial (ej: OM-00051)
- ✅ No hay duplicados
- ✅ Formato es correcto (prefijo + número)

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Asignación Automática de Asesor
**Objetivo**: Verificar que asesor se asigna automáticamente

**Pre-condiciones**:
- Usuario logueado con rol de asesor

**Pasos**:
1. Crear nueva orden
2. Llenar campos obligatorios
3. NO seleccionar asesor manualmente
4. Guardar

**Resultado Esperado**:
- ✅ Campo "Asesor" se llena automáticamente con usuario actual
- ✅ Se puede cambiar manualmente si es necesario
- ✅ Queda registrado quién creó la orden

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Fecha y Hora Automática
**Objetivo**: Verificar registro automático de fecha/hora

**Pre-condiciones**:
- Ninguna

**Pasos**:
1. Crear nueva orden
2. Observar campo "Fecha y hora de ingreso"
3. Guardar
4. Verificar que fecha no se puede editar

**Resultado Esperado**:
- ✅ Fecha y hora se establecen automáticamente al crear
- ✅ Muestra fecha/hora actual del servidor
- ✅ Campo es de solo lectura (no editable)
- ✅ Formato correcto: DD/MM/YYYY HH:MM:SS

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Cambio de Prioridad Manual
**Objetivo**: Verificar que se puede cambiar prioridad manualmente

**Pre-condiciones**:
- Orden existente con prioridad "Baja"

**Pasos**:
1. Abrir orden existente
2. Cambiar prioridad de "Baja" a "Crítica"
3. Guardar
4. Reabrir orden
5. Verificar cambio

**Resultado Esperado**:
- ✅ Cambio se guarda correctamente
- ✅ Se registra en historial de cambios
- ✅ Se muestra quién cambió y cuándo
- ⚠️ Si aumenta a crítica, se genera alerta

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 11: Filtrado por Sucursal
**Objetivo**: Verificar filtro de órdenes por sucursal

**Pre-condiciones**:
- Órdenes existentes en diferentes sucursales

**Pasos**:
1. Ir a lista de órdenes
2. Aplicar filtro: Sucursal = "Sucursal A"
3. Observar resultados

**Resultado Esperado**:
- ✅ Solo muestra órdenes de "Sucursal A"
- ✅ Otras sucursales no aparecen
- ✅ Contador muestra número correcto

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 12: Reporte - Órdenes por Tipo de Servicio
**Objetivo**: Verificar generación de reporte agrupado

**Pre-condiciones**:
- Órdenes existentes de diferentes tipos

**Pasos**:
1. Acceder a menú de reportes
2. Seleccionar "Órdenes por Tipo de Servicio"
3. Definir rango de fechas
4. Generar reporte

**Resultado Esperado**:
- ✅ Reporte muestra agrupación por tipo
- ✅ Cuenta correcta de órdenes por tipo
- ✅ Incluye gráfico visual
- ✅ Permite exportar a PDF/Excel

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Crear Orden Normal | Funcional | Alta |
| 2 | Validación sin Vehículo | Validación | Alta |
| 3 | Emergencia - Prioridad Auto | Lógica | Alta |
| 4 | Garantía - Validación OK | Validación | Media |
| 5 | Garantía - Sin Orden Previa | Validación | Media |
| 6 | Alerta Crédito Atrasado | Alerta | Media |
| 7 | Numeración Secuencial | Sistema | Alta |
| 8 | Asesor Automático | Sistema | Media |
| 9 | Fecha/Hora Automática | Sistema | Media |
| 10 | Cambio Prioridad Manual | Funcional | Baja |
| 11 | Filtro por Sucursal | UI/UX | Baja |
| 12 | Reporte por Tipo | Reporte | Media |

**Total**: 12 casos de prueba

