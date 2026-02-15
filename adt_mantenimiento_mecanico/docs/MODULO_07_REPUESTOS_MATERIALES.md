# MÓDULO 7: REPUESTOS Y MATERIALES

## Objetivo
Gestionar el control de repuestos y materiales necesarios para cada orden de mantenimiento, integrando con el inventario del taller.

## Información de Repuestos

### Campos Principales
- **Código**: Código único del repuesto
- **Descripción**: Nombre y especificaciones
- **Cantidad**: Unidades requeridas
- **Precio unitario**: Costo por unidad
- **Subtotal**: Cantidad × Precio unitario (calculado)
- **Categoría**: Tipo de repuesto
- **Marca**: Fabricante del repuesto
- **Número de parte**: Part number del fabricante
- **Ubicación en almacén**: Para facilitar búsqueda
- **Proveedor**: Proveedor habitual

## Reglas de Negocio

### Validaciones Críticas

#### 1. Validar Stock Disponible
- ✅ Verificar existencia en inventario
- ✅ Mostrar cantidad disponible
- ✅ Alertar si stock es insuficiente
- ✅ Permitir continuar con reserva

#### 2. Reservar Inventario al Aprobar
- ✅ Al aprobar cotización → reservar repuestos
- ✅ Repuestos reservados no disponibles para otras órdenes
- ✅ Liberar reserva si orden se cancela
- ✅ Actualizar inventario al completar orden

#### 3. Si No Hay Stock
- ✅ Generar solicitud de compra automática
- ✅ Alertar al encargado de compras
- ✅ Registrar tiempo estimado de llegada
- ✅ Notificar al cliente sobre demora

#### 4. Registrar Lote (si aplica)
- ✅ Para repuestos con lote
- ✅ Trazabilidad completa
- ✅ Control de garantía por lote
- ✅ Fecha de vencimiento si aplica

## Tipos de Repuestos

### Categorías Principales
- **Filtros**: Aceite, aire, combustible
- **Lubricantes**: Aceites, grasas
- **Frenos**: Pastillas, discos, zapatas
- **Transmisión**: Cadena, piñones, embrague
- **Eléctrico**: Bujías, batería, focos
- **Neumáticos**: Llantas, cámaras
- **Suspensión**: Amortiguadores, resortes
- **Motor**: Pistones, anillos, válvulas
- **Carrocería**: Espejos, manijas, guardafangos
- **Consumibles**: Tornillos, abrazaderas, cables

## Funcionalidades Especiales

### Gestión de Inventario
- Stock en tiempo real
- Punto de reorden
- Stock de seguridad
- Rotación de inventario
- Análisis ABC
- Repuestos obsoletos

### Precios y Costos
- Precio de costo
- Precio de venta
- Margen de utilidad
- Descuentos por volumen
- Precios por tipo de cliente
- Historial de precios

### Repuestos Alternativos
- Listar opciones equivalentes
- Original vs genérico
- Diferentes marcas
- Comparación de precios
- Recomendación según presupuesto

### Kits y Paquetes
- Definir kits predefinidos
- Ej: "Kit de mantenimiento 5,000 km"
- Precio especial por kit
- Facilita cotización

## Validaciones Adicionales

### Controles de Calidad
1. ✅ Precio no puede ser cero (salvo garantía)
2. ✅ Cantidad debe ser positiva
3. ✅ Código debe ser único
4. ✅ Validar compatibilidad con modelo de vehículo
5. ✅ Alertar si repuesto no es original (según preferencia)

## Alertas del Sistema

### Alertas de Inventario
- 🔴 Stock agotado
- 🟡 Stock bajo (cerca del punto de reorden)
- ⚠️ Repuesto reservado para otra orden
- 📦 Pedido pendiente con proveedor
- ⏰ Repuesto próximo a vencer (si aplica)

### Alertas de Precio
- 💰 Precio fuera del rango normal
- 📊 Margen de utilidad bajo
- 💎 Repuesto premium seleccionado
- 🔄 Existe alternativa más económica

## Vinculación con Otros Módulos

### Integración con:
- **Compras**: Generar orden de compra
- **Inventario**: Control de stock
- **Contabilidad**: Valorización
- **Proveedores**: Gestión de pedidos
- **Garantías**: Seguimiento de repuestos
- **Trabajos**: Asignar repuestos por trabajo

## Trazabilidad

### Información de Seguimiento
- Fecha de instalación
- Orden de trabajo asociada
- Mecánico que instaló
- Garantía del repuesto
- Lote/serie
- Fecha de vencimiento de garantía
- Proveedor original

## Reportes Relacionados
- Repuestos más vendidos
- Análisis de rotación
- Rentabilidad por repuesto
- Stock valorizado
- Repuestos por vehículo/modelo
- Análisis de consumo
- Proveedores más utilizados
- Repuestos en garantía
- Próximos vencimientos
- Solicitudes de compra pendientes

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Agregar Repuesto con Stock Disponible
**Objetivo**: Verificar agregar repuesto desde inventario

**Pre-condiciones**:
- Orden con trabajos definidos
- Repuesto "Pastillas de freno" con stock: 10 unidades

**Pasos**:
1. Seleccionar trabajo "Cambio de frenos"
2. Agregar repuesto: Pastillas de freno
3. Cantidad: 2
4. Guardar

**Resultado Esperado**:
- ✅ Repuesto agregado correctamente
- ✅ Muestra stock disponible: 10 unidades
- ✅ Precio unitario cargado automáticamente
- ✅ Subtotal calculado: cant × precio

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Alerta - Stock Insuficiente
**Objetivo**: Verificar alerta cuando no hay stock

**Pre-condiciones**:
- Repuesto con stock: 1 unidad

**Pasos**:
1. Intentar agregar 3 unidades del repuesto
2. Observar alerta

**Resultado Esperado**:
- ⚠️ Alerta: "Stock insuficiente. Disponible: 1 unidad"
- ⚠️ Opción de generar solicitud de compra
- ⚠️ Permite reservar el disponible
- ✅ Muestra tiempo estimado de llegada

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Reservar Inventario al Aprobar Cotización
**Objetivo**: Verificar reserva automática

**Pre-condiciones**:
- Orden con repuestos agregados
- Stock disponible

**Pasos**:
1. Aprobar cotización
2. Verificar estado del inventario

**Resultado Esperado**:
- ✅ Repuestos reservados automáticamente
- ✅ Stock disponible reducido
- ✅ Repuestos no disponibles para otras órdenes
- ✅ Se libera si orden se cancela

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Generar Solicitud de Compra Automática
**Objetivo**: Verificar solicitud cuando no hay stock

**Pre-condiciones**:
- Repuesto sin stock

**Pasos**:
1. Agregar repuesto sin stock
2. Sistema detecta falta
3. Generar solicitud automática

**Resultado Esperado**:
- ✅ Solicitud de compra generada
- ✅ Alerta al encargado de compras
- ✅ Tiempo estimado de llegada registrado
- ✅ Cliente notificado de demora

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Trazabilidad por Lote
**Objetivo**: Verificar registro de lote para trazabilidad

**Pre-condiciones**:
- Repuesto con manejo de lotes

**Pasos**:
1. Agregar repuesto
2. Registrar lote: LOTE-2026-001
3. Fecha de vencimiento: 12/2027
4. Guardar

**Resultado Esperado**:
- ✅ Lote registrado correctamente
- ✅ Trazabilidad completa
- ✅ Control de garantía por lote
- ✅ Alerta si próximo a vencer

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Repuesto Alternativo - Genérico vs Original
**Objetivo**: Verificar opciones de repuestos

**Pre-condiciones**:
- Repuesto con alternativas configuradas

**Pasos**:
1. Agregar repuesto "Filtro de aceite"
2. Sistema muestra alternativas:
   - Original Honda: S/. 45
   - Genérico Premium: S/. 30
   - Genérico Estándar: S/. 20
3. Seleccionar opción

**Resultado Esperado**:
- ✅ Lista alternativas disponibles
- ✅ Comparación de precios clara
- ✅ Recomendación según presupuesto
- ✅ Cliente elige opción

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Validación - Precio No Puede Ser Cero
**Objetivo**: Verificar validación de precio

**Pre-condiciones**:
- Agregando repuesto

**Pasos**:
1. Agregar repuesto
2. Precio: 0.00 (salvo garantía)
3. Intentar guardar

**Resultado Esperado**:
- 🔴 Error: "El precio no puede ser cero"
- 🔴 Excepción: Si es orden de garantía
- ⚠️ Solicita corrección

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Actualizar Inventario al Completar Orden
**Objetivo**: Verificar descuento automático de stock

**Pre-condiciones**:
- Orden completada con repuestos
- Stock inicial: 10 unidades

**Pasos**:
1. Completar orden (usó 2 unidades)
2. Verificar inventario

**Resultado Esperado**:
- ✅ Stock actualizado: 8 unidades
- ✅ Movimiento registrado en historial
- ✅ Fecha y orden asociada
- ✅ Punto de reorden verificado

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Alerta - Stock Bajo (Punto de Reorden)
**Objetivo**: Verificar alerta de reabastecimiento

**Pre-condiciones**:
- Repuesto con punto de reorden: 5 unidades
- Stock actual: 4 unidades

**Pasos**:
1. Ver panel de alertas
2. Revisar repuestos

**Resultado Esperado**:
- 🟡 Alerta: "Stock bajo - cerca del punto de reorden"
- 🟡 Sugiere orden de compra
- ✅ Lista repuestos a reabastecer
- ✅ Cantidad sugerida de compra

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Reporte - Repuestos Más Vendidos
**Objetivo**: Verificar análisis de rotación

**Pre-condiciones**:
- Historial de ventas

**Pasos**:
1. Acceder a reportes
2. "Repuestos Más Vendidos"
3. Período: Último trimestre
4. Generar

**Resultado Esperado**:
- ✅ Lista ordenada por cantidad vendida
- ✅ Ingresos por repuesto
- ✅ Margen de utilidad
- ✅ Análisis ABC
- ✅ Gráfico de rotación

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Agregar Repuesto con Stock | Funcional | Alta |
| 2 | Alerta Stock Insuficiente | Alerta | Alta |
| 3 | Reservar Inventario | Lógica | Alta |
| 4 | Solicitud Compra Automática | Funcional | Alta |
| 5 | Trazabilidad por Lote | Funcional | Media |
| 6 | Repuesto Alternativo | Funcional | Media |
| 7 | Validación Precio Cero | Validación | Alta |
| 8 | Actualizar Inventario | Sistema | Alta |
| 9 | Alerta Punto Reorden | Alerta | Media |
| 10 | Reporte Más Vendidos | Reporte | Baja |

**Total**: 10 casos de prueba

