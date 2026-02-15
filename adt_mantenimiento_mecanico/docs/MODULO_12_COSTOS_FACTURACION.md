# MÓDULO 12: COSTOS Y FACTURACIÓN

## Objetivo
Calcular automáticamente todos los costos asociados a la orden de trabajo y generar la facturación correspondiente con todas las validaciones necesarias.

## Estructura de Costos

### Componentes del Costo Total

#### 1. Total Repuestos
- Suma de todos los repuestos utilizados
- Cantidad × Precio unitario por cada repuesto
- Incluye consumibles y materiales
- **Cálculo automático**

#### 2. Total Mano de Obra
- Suma de todas las horas trabajadas
- Horas × Precio por hora por cada trabajo
- Diferenciado por complejidad
- **Cálculo automático**

#### 3. Descuentos
- Descuento por cliente frecuente
- Descuento promocional
- Descuento por volumen
- Descuento por tipo de cliente (VIP, flota)
- **Puede ser %  o monto fijo**

#### 4. Impuestos
- IGV (18% en Perú) o según configuración
- Otros impuestos aplicables
- Calculado sobre subtotal después de descuentos
- **Cálculo automático**

#### 5. TOTAL A PAGAR
```
Subtotal = Total Repuestos + Total Mano de Obra
Subtotal con Descuento = Subtotal - Descuentos
Impuestos = Subtotal con Descuento × Tasa Impuesto
TOTAL A PAGAR = Subtotal con Descuento + Impuestos
```

## Desglose Detallado

### Vista de Costos para el Cliente

#### Repuestos
| Código | Descripción | Cantidad | P. Unit | Subtotal |
|--------|-------------|----------|---------|----------|
| REP001 | Filtro aceite | 1 | 25.00 | 25.00 |
| REP002 | Aceite 20W-50 | 1 | 45.00 | 45.00 |
| ... | ... | ... | ... | ... |
| **Total Repuestos** | | | | **XXX.XX** |

#### Mano de Obra
| Trabajo | Horas | Tarifa/h | Subtotal |
|---------|-------|----------|----------|
| Cambio aceite | 0.5 | 30.00 | 15.00 |
| Revisión frenos | 1.0 | 30.00 | 30.00 |
| ... | ... | ... | ... |
| **Total Mano de Obra** | | | **XXX.XX** |

#### Resumen
- Subtotal: XXX.XX
- Descuento (10%): -XX.XX
- Base imponible: XXX.XX
- IGV (18%): XX.XX
- **TOTAL A PAGAR: XXX.XX**

## Reglas de Negocio

### Validaciones Críticas

#### 1. No Facturar si No Está Finalizada
- ✅ Estado debe ser "Lista para entrega" o superior
- ✅ Control de calidad aprobado
- ✅ Estado final NO puede ser "Requiere revisión"
- 🔴 Bloqueo automático si no cumple

#### 2. Si es Garantía → Total = 0
- ✅ Validar que orden previa existe
- ✅ Validar que está dentro del período de garantía
- ✅ Validar que el problema está cubierto
- ✅ Repuestos y mano de obra sin costo (según política)
- ✅ Registrar como servicio de garantía

#### 3. Permitir Pago Parcial
- ✅ Cliente puede pagar adelanto
- ✅ Registrar pagos parciales
- ✅ Calcular saldo pendiente
- ✅ Generar múltiples recibos
- ✅ No entregar vehículo hasta pago completo

#### 4. Registrar Método de Pago
- Efectivo
- Tarjeta de crédito
- Tarjeta de débito
- Transferencia bancaria
- Crédito del taller
- Financiamiento externo
- Combinación de métodos

## Tipos de Facturación

### Factura Completa
- Todos los trabajos incluidos
- Pago total al momento de entrega
- Documento fiscal completo

### Factura con Adelanto
- Cliente pagó adelanto al aprobar cotización
- Saldo restante al completar
- Dos o más comprobantes

### Factura con Crédito
- Cliente tiene línea de crédito del taller
- Pago diferido según acuerdo
- Genera cuenta por cobrar
- Seguimiento de cobranza

### Orden de Garantía
- Sin costo para el cliente
- Registrar para contabilidad interna
- No genera cobranza
- Afecta costos del taller

## Descuentos y Promociones

### Tipos de Descuento

#### Por Cliente
- Cliente frecuente: 5-10%
- Cliente VIP: 10-15%
- Cliente flota: 15-20%
- Primera visita: 5%

#### Por Volumen
- Servicio > $500: 5%
- Servicio > $1000: 10%
- Múltiples vehículos: 10-15%

#### Promocional
- Campaña del mes
- Descuento temporal
- Código promocional
- Referido

#### Especial
- Autorización del gerente
- Casos especiales
- Compensación por demora
- Fidelización

### Validaciones de Descuento
- ✅ Descuento no puede exceder límite configurado
- ✅ Descuentos especiales requieren aprobación
- ✅ Registrar motivo del descuento
- ✅ Registrar quién autorizó

## Configuración de Impuestos

### Parámetros Configurables
- Tasa de IGV/IVA
- Impuestos adicionales
- Exoneraciones
- Retenciones (si aplica)

### Aplicación de Impuestos
- Sobre repuestos
- Sobre mano de obra
- Descuentos antes de impuestos
- Cálculo automático

## Métodos de Pago

### Registro de Pagos

#### Pago Simple
- Un solo método
- Un solo monto
- Un solo comprobante

#### Pago Combinado
- Múltiples métodos en una transacción
- Ejemplo: Efectivo + Tarjeta
- Suma debe igualar total
- Registro de cada método

#### Pago Parcial
- Múltiples pagos en diferentes fechas
- Adelanto + Saldo
- Control de pendientes
- Recibo por cada pago

### Información del Pago
- Fecha y hora
- Monto
- Método
- Número de operación (si aplica)
- Banco (si aplica)
- Cajero que recibió
- Comprobante generado

## Comprobantes de Pago

### Tipos de Comprobante
- Boleta de venta
- Factura electrónica
- Recibo
- Nota de crédito
- Nota de débito

### Información Obligatoria
- Número de comprobante (correlativo)
- Fecha de emisión
- Datos del cliente
- RUC/DNI
- Detalle de servicios/productos
- Impuestos
- Total
- Forma de pago

### Integración Contable
- Registro automático en contabilidad
- Actualización de inventario
- Registro de caja
- Cuentas por cobrar (si aplica)

## Alertas del Sistema

### Alertas de Facturación
- ⚠️ Intento de facturar orden no finalizada
- 🔴 Estado "Requiere revisión" bloqueado
- 💰 Descuento excede límite permitido
- 📋 Falta método de pago
- 💳 Pago parcial pendiente

### Alertas de Cobro
- 🔔 Cliente con saldo pendiente
- ⏰ Pago vencido
- 💰 Pago pendiente de confirmación
- 📞 Recordatorio de cobranza

## Garantía Especial - Orden Tipo Garantía

### Validaciones para Garantía
1. ✅ Debe existir orden anterior
2. ✅ Validar fecha: dentro del período de garantía
3. ✅ Validar que el problema esté cubierto
4. ✅ Validar que el cliente no causó el daño

### Proceso de Garantía
- Buscar orden original
- Verificar trabajos realizados
- Confirmar que problema está relacionado
- Autorizar servicio sin costo
- Registrar como garantía
- No generar cobro al cliente
- Registrar costo interno
- Analizar causa del retrabajo

### Excepciones
- Si el problema NO está cubierto → cobro normal
- Si la garantía venció → cobro normal
- Si cliente causó el daño → cobro normal

## Reportes Relacionados
- Ingresos por período
- Desglose de ventas (repuestos vs mano de obra)
- Descuentos otorgados
- Análisis de rentabilidad
- Métodos de pago más usados
- Cuentas por cobrar
- Pagos pendientes
- Servicios de garantía (costo interno)
- Análisis de márgenes
- Ticket promedio
- Comparativo mensual
- Ranking de servicios más rentables
- Eficiencia de cobranza

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Cálculo Automático de Costos
**Objetivo**: Verificar cálculo total correcto

**Pre-condiciones**:
- Repuestos: S/. 150
- Mano de obra: S/. 100

**Pasos**:
1. Ver desglose de costos
2. Aplicar descuento: 10%
3. Calcular IGV: 18%

**Resultado Esperado**:
- ✅ Subtotal: S/. 250
- ✅ Descuento (10%): -S/. 25
- ✅ Base imponible: S/. 225
- ✅ IGV (18%): S/. 40.50
- ✅ TOTAL: S/. 265.50

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Bloqueo - No Facturar si No Está Finalizada
**Objetivo**: Verificar validación de estado

**Pre-condiciones**:
- Orden en estado "En proceso"

**Pasos**:
1. Intentar generar factura

**Resultado Esperado**:
- 🔴 Error: "No se puede facturar orden no finalizada"
- 🔴 Bloqueo automático
- ⚠️ Requiere CC aprobado y estado final

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Orden de Garantía - Total Cero
**Objetivo**: Verificar lógica para garantía

**Pre-condiciones**:
- Orden tipo: Garantía
- Orden previa válida

**Pasos**:
1. Calcular costos
2. Ver total

**Resultado Esperado**:
- ✅ Validación de garantía OK
- ✅ Repuestos: S/. 0.00
- ✅ Mano de obra: S/. 0.00
- ✅ TOTAL: S/. 0.00
- ✅ Registrado como servicio de garantía

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Pago Parcial
**Objetivo**: Verificar registro de adelanto

**Pre-condiciones**:
- Total: S/. 500

**Pasos**:
1. Registrar adelanto: S/. 200
2. Generar recibo
3. Calcular saldo

**Resultado Esperado**:
- ✅ Adelanto registrado: S/. 200
- ✅ Saldo pendiente: S/. 300
- ✅ Recibo generado
- ✅ No entregar hasta pago completo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Múltiples Métodos de Pago
**Objetivo**: Verificar pago combinado

**Pre-condiciones**:
- Total: S/. 400

**Pasos**:
1. Efectivo: S/. 250
2. Tarjeta: S/. 150
3. Guardar

**Resultado Esperado**:
- ✅ Ambos métodos registrados
- ✅ Suma correcta: S/. 400
- ✅ Comprobante único
- ✅ Desglose de métodos visible

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Validación - Descuento Excede Límite
**Objetivo**: Verificar control de descuentos

**Pre-condiciones**:
- Límite configurado: 20%
- Usuario intenta aplicar: 25%

**Pasos**:
1. Aplicar descuento 25%
2. Intentar guardar

**Resultado Esperado**:
- ⚠️ Advertencia: "Descuento excede límite permitido (20%)"
- ⚠️ Requiere autorización de supervisor
- 🔴 No permite continuar sin aprobación

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Desglose Detallado para Cliente
**Objetivo**: Verificar documento de cotización

**Pre-condiciones**:
- Orden con repuestos y mano de obra

**Pasos**:
1. Generar cotización
2. Revisar desglose

**Resultado Esperado**:
- ✅ Tabla de repuestos (código, desc, cant, precio)
- ✅ Tabla de mano de obra (trabajo, horas, tarifa)
- ✅ Subtotales por sección
- ✅ Descuentos e impuestos claros
- ✅ TOTAL destacado

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Generación de Comprobante Electrónico
**Objetivo**: Verificar emisión de factura

**Pre-condiciones**:
- Pago completo recibido

**Pasos**:
1. Generar factura electrónica
2. Incluir datos fiscales
3. Emitir

**Resultado Esperado**:
- ✅ Factura generada con número correlativo
- ✅ Datos del cliente completos
- ✅ RUC/DNI incluido
- ✅ Detalle de productos/servicios
- ✅ Formato legal válido

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Cuenta por Cobrar - Crédito del Taller
**Objetivo**: Verificar registro de deuda

**Pre-condiciones**:
- Cliente con línea de crédito
- Total: S/. 500

**Pasos**:
1. Seleccionar método: "Crédito del taller"
2. Definir plazo: 30 días
3. Generar

**Resultado Esperado**:
- ✅ Cuenta por cobrar generada
- ✅ Fecha de vencimiento: +30 días
- ✅ Cliente puede retirar vehículo
- ✅ Registrado en cobranza

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Reporte - Análisis de Rentabilidad
**Objetivo**: Verificar cálculo de márgenes

**Pre-condiciones**:
- Órdenes completadas en período

**Pasos**:
1. Acceder a reportes
2. "Análisis de Rentabilidad"
3. Período: Último mes
4. Generar

**Resultado Esperado**:
- ✅ Ingresos totales
- ✅ Costos de repuestos
- ✅ Costos de mano de obra
- ✅ Margen de utilidad: XX%
- ✅ Servicios más rentables
- ✅ Gráfico de análisis

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Cálculo Automático | Cálculo | Alta |
| 2 | Bloqueo No Finalizada | Validación | Alta |
| 3 | Orden Garantía | Lógica | Alta |
| 4 | Pago Parcial | Funcional | Alta |
| 5 | Múltiples Métodos Pago | Funcional | Media |
| 6 | Validación Descuento | Validación | Alta |
| 7 | Desglose Detallado | Funcional | Media |
| 8 | Comprobante Electrónico | Funcional | Alta |
| 9 | Cuenta por Cobrar | Funcional | Media |
| 10 | Análisis Rentabilidad | Reporte | Media |

**Total**: 10 casos de prueba

