# MÓDULO 2: DATOS DEL VEHÍCULO

## Objetivo
Mantener un registro completo y actualizado de cada vehículo (motocicleta o mototaxi) que ingresa al taller.

## Información del Vehículo

### Campos Principales
- **Tipo**: Motocicleta / Mototaxi
- **Marca**: Fabricante del vehículo
- **Modelo**: Modelo específico
- **Año**: Año de fabricación
- **Color**: Color principal
- **Placa**: Número de matrícula
- **VIN / Chasis**: Número de identificación vehicular
- **Motor**: Número de motor
- **Kilometraje**: Kilometraje actual
- **Combustible**: Tipo de combustible (Gasolina, Eléctrico, etc.)
- **Cilindraje**: Capacidad del motor

## Reglas Críticas

### Validaciones Obligatorias
1. ✅ El kilometraje NO puede ser menor al último registrado
2. ✅ Si el vehículo tiene historial previo → mostrar alertas
3. ✅ Si el vehículo tiene crédito activo → mostrar estado financiero

## Funcionalidades Especiales

### Historial del Vehículo
- Visualizar todas las órdenes previas
- Última fecha de servicio
- Mantenimientos preventivos realizados
- Fallas recurrentes
- Repuestos más cambiados

### Alertas por Vehículo
- ⚠️ Kilometraje excedido para mantenimiento preventivo
- ⚠️ Garantía próxima a vencer
- ⚠️ Vehículo con historial de fallas recurrentes
- ⚠️ Crédito financiero atrasado

## Control de Calidad de Datos
- Validar formato de placa
- Validar unicidad de VIN/Chasis
- Validar unicidad de placa
- Validar año (no puede ser futuro)
- Validar kilometraje (solo aumenta)

## Información Complementaria
- Propietario actual
- Fecha de compra
- Póliza de seguro (si aplica)
- Estado de documentación

## Reportes Relacionados
- Vehículos por marca/modelo
- Frecuencia de mantenimiento por vehículo
- Análisis de fallas por modelo
- Rentabilidad por tipo de vehículo
- Historial completo por placa

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Registrar Nuevo Vehículo
**Objetivo**: Verificar registro completo de vehículo nuevo

**Pre-condiciones**:
- Usuario con permisos
- Cliente registrado

**Pasos**:
1. Acceder a "Vehículos"
2. Clic en "Crear"
3. Llenar todos los campos obligatorios:
   - Tipo: Motocicleta
   - Marca: Honda
   - Modelo: CB190R
   - Año: 2024
   - Placa: ABC-123
   - VIN: 1234567890ABCDEFG
   - Motor: MOT123456
   - Kilometraje: 1500
   - Combustible: Gasolina
   - Cilindraje: 190
4. Asociar a propietario
5. Guardar

**Resultado Esperado**:
- ✅ Vehículo se registra exitosamente
- ✅ Placa y VIN únicos (no duplicados)
- ✅ Todos los datos se guardan correctamente
- ✅ Se crea historial vacío

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Validación - Kilometraje No Puede Decrecer
**Objetivo**: Verificar que kilometraje solo puede aumentar

**Pre-condiciones**:
- Vehículo existente con kilometraje: 10,000 km

**Pasos**:
1. Abrir vehículo existente
2. Intentar cambiar kilometraje a 9,000 km (menor)
3. Guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "El kilometraje no puede ser menor al último registrado (10,000 km)"
- 🔴 No permite guardar
- ✅ Kilometraje permanece en 10,000 km

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Validación - Placa Duplicada
**Objetivo**: Verificar que no se permiten placas duplicadas

**Pre-condiciones**:
- Vehículo existente con placa: XYZ-789

**Pasos**:
1. Crear nuevo vehículo
2. Ingresar placa: XYZ-789 (ya existe)
3. Llenar otros campos
4. Intentar guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "Ya existe un vehículo con esta placa"
- 🔴 No permite guardar
- ⚠️ Opción de ver vehículo existente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Validación - VIN Duplicado
**Objetivo**: Verificar unicidad de VIN/Chasis

**Pre-condiciones**:
- Vehículo existente con VIN: ABC123XYZ456

**Pasos**:
1. Crear nuevo vehículo
2. Ingresar VIN: ABC123XYZ456 (duplicado)
3. Intentar guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "Ya existe un vehículo con este VIN"
- 🔴 No permite guardar
- ⚠️ Muestra link al vehículo existente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Validación - Año Futuro
**Objetivo**: Verificar que año no puede ser futuro

**Pre-condiciones**:
- Año actual: 2026

**Pasos**:
1. Crear nuevo vehículo
2. Ingresar año: 2027 (futuro)
3. Intentar guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "El año no puede ser futuro"
- 🔴 No permite guardar
- ⚠️ Sugiere año actual máximo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Historial del Vehículo
**Objetivo**: Verificar visualización de historial

**Pre-condiciones**:
- Vehículo con al menos 3 órdenes previas

**Pasos**:
1. Abrir vehículo
2. Acceder a pestaña "Historial"
3. Observar lista de órdenes

**Resultado Esperado**:
- ✅ Muestra todas las órdenes previas
- ✅ Ordenadas por fecha (más reciente primero)
- ✅ Muestra: número orden, fecha, tipo servicio, costo
- ✅ Link para abrir cada orden
- ✅ Muestra última fecha de servicio

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Alerta - Mantenimiento Preventivo Vencido
**Objetivo**: Verificar alerta cuando se excede kilometraje de mantenimiento

**Pre-condiciones**:
- Vehículo con último mantenimiento a 5,000 km
- Kilometraje actual: 11,000 km (excede 5,000 km de intervalo)

**Pasos**:
1. Abrir vehículo
2. Observar panel de alertas

**Resultado Esperado**:
- ⚠️ Alerta visible: "Mantenimiento preventivo vencido"
- ⚠️ Muestra km excedidos (1,000 km)
- ⚠️ Sugiere agendar mantenimiento
- ✅ Alerta en color llamativo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Alerta - Crédito Financiero Atrasado
**Objetivo**: Verificar alerta de crédito atrasado

**Pre-condiciones**:
- Vehículo con crédito activo
- Crédito en estado "Atrasado"

**Pasos**:
1. Abrir vehículo
2. Observar alertas

**Resultado Esperado**:
- 🔴 Alerta roja: "Crédito financiero atrasado"
- 🔴 Muestra entidad financiera
- 🔴 Muestra días de atraso
- ✅ Link a información del crédito

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Actualización de Kilometraje
**Objetivo**: Verificar actualización correcta de kilometraje

**Pre-condiciones**:
- Vehículo con kilometraje: 15,000 km

**Pasos**:
1. Crear nueva orden de mantenimiento
2. Ingresar nuevo kilometraje: 15,500 km
3. Completar orden
4. Verificar datos del vehículo

**Resultado Esperado**:
- ✅ Kilometraje del vehículo se actualiza a 15,500 km
- ✅ Se registra en historial
- ✅ Fecha de última actualización se guarda

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Historial de Fallas Recurrentes
**Objetivo**: Verificar detección de fallas recurrentes

**Pre-condiciones**:
- Vehículo con 3+ órdenes por mismo problema

**Pasos**:
1. Abrir vehículo
2. Acceder a "Análisis de Fallas"
3. Observar estadísticas

**Resultado Esperado**:
- ✅ Muestra fallas más frecuentes
- ✅ Cantidad de veces que ocurrió cada falla
- ⚠️ Alerta si hay falla recurrente (3+ veces)
- ✅ Gráfico de análisis

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 11: Repuestos Más Cambiados
**Objetivo**: Verificar estadística de repuestos

**Pre-condiciones**:
- Vehículo con historial de mantenimientos

**Pasos**:
1. Abrir vehículo
2. Acceder a "Repuestos"
3. Ver lista de repuestos más cambiados

**Resultado Esperado**:
- ✅ Lista ordenada por frecuencia
- ✅ Muestra: repuesto, cantidad de veces, última fecha
- ✅ Total gastado en cada repuesto
- ✅ Gráfico visual

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 12: Cambio de Propietario
**Objetivo**: Verificar cambio de propietario del vehículo

**Pre-condiciones**:
- Vehículo con propietario A
- Cliente B registrado

**Pasos**:
1. Abrir vehículo
2. Cambiar propietario de A a B
3. Registrar fecha de cambio
4. Guardar

**Resultado Esperado**:
- ✅ Propietario se actualiza a B
- ✅ Se registra fecha de cambio
- ✅ Historial muestra cambio de propietario
- ✅ Propietario anterior queda en historial

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Registrar Nuevo Vehículo | Funcional | Alta |
| 2 | Kilometraje No Decrece | Validación | Alta |
| 3 | Placa Duplicada | Validación | Alta |
| 4 | VIN Duplicado | Validación | Alta |
| 5 | Año Futuro | Validación | Media |
| 6 | Historial del Vehículo | Funcional | Alta |
| 7 | Alerta Mantenimiento Vencido | Alerta | Media |
| 8 | Alerta Crédito Atrasado | Alerta | Alta |
| 9 | Actualización Kilometraje | Funcional | Alta |
| 10 | Fallas Recurrentes | Análisis | Media |
| 11 | Repuestos Más Cambiados | Análisis | Baja |
| 12 | Cambio de Propietario | Funcional | Media |

**Total**: 12 casos de prueba

