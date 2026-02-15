DOCUMENTO FUNCIONAL
Sistema de Gestión de Órdenes de Mantenimiento
Especializado en Motocicletas y Mototaxis
Versión 2.0 – Adaptado a Orden de Mantenimiento Física

1️⃣ OBJETIVO DEL SISTEMA
Digitalizar, controlar y optimizar el proceso completo de mantenimiento y reparación de motocicletas y mototaxis, garantizando:
Trazabilidad técnica


Control financiero


Control de inventario


Control de garantías


Seguimiento de mantenimiento periódico


Validación documental y contractual



2️⃣ ALCANCE
El sistema cubrirá:
Registro de orden de mantenimiento


Inspección técnica estructurada


Gestión de crédito financiero


Cotización y aprobación


Control de ejecución


Control de calidad post-servicio


Control de costos


Programación de próxima revisión



3️⃣ ESTRUCTURA FUNCIONAL BASADA EN TU FORMATO

MÓDULO 1: ORDEN DE MANTENIMIENTO
3.1 Información General
Campos obligatorios:
Número de Orden (autogenerado)


Fecha y hora de ingreso


Tipo de servicio:


Preventivo


Correctivo


Predictivo


Emergencia


Garantía


Nivel de prioridad:


Baja


Media


Alta


Crítica


Sucursal


Asesor de servicio



🔒 Reglas de negocio:
No puede crearse orden sin vehículo registrado.


Si es tipo Garantía → debe validar orden anterior.


Si es Emergencia → prioridad automática Alta o Crítica.


Toda orden debe tener asesor responsable.



MÓDULO 2: DATOS DEL VEHÍCULO
El sistema debe permitir:
Tipo: Motocicleta / Mototaxi


Marca


Modelo


Año


Color


Placa


VIN / Chasis


Motor


Kilometraje


Combustible


Cilindraje



🔒 Reglas críticas:
El kilometraje no puede ser menor al último registrado.


Si el vehículo tiene historial previo → mostrar alertas.


Si el vehículo tiene crédito activo → mostrar estado financiero.



MÓDULO 3: CLIENTE Y CRÉDITO
3.3 Datos del propietario
Debe permitir:
Registro completo


Asociación con múltiples vehículos


Historial financiero acumulado



3.4 Control de crédito
Si aplica financiamiento:
Empresa financiera


Número de contrato


Estado de pagos


🔒 Reglas:
Si estado = Atrasado → alerta roja.


Si contrato Cancelado → bloquear crédito.


Permitir reporte por financiera.



MÓDULO 4: INSPECCIÓN DE INGRESO
Este módulo es crítico para evitar reclamos.
4.1 Evaluación por sistemas:
Motor


Transmisión


Frenos


Suspensión


Sistema eléctrico


Llantas


Carrocería


Accesorios


Cada uno debe registrar:
Estado (Bueno / Regular / Malo)


Observaciones


Evidencia fotográfica (opcional)



🔒 Reglas:
No se puede avanzar a diagnóstico sin inspección completa.


Si se marca "Malo" → sugerir acción automática.


Guardar registro como respaldo legal.



MÓDULO 5: CONTROL DE FLUIDOS
Debe registrar:
Nivel


Estado


Tipo de fluido



🔒 Lógica:
Si:
Aceite contaminado → sugerir cambio automático.


Refrigerante bajo → alerta preventiva.


Líquido frenos bajo → alerta seguridad.



MÓDULO 6: DIAGNÓSTICO Y TRABAJOS
Debe permitir:
Descripción libre del motivo del cliente.


Agregar múltiples trabajos.


Clasificar tipo:


Preventivo


Correctivo



🔒 Lógica avanzada:
Si el trabajo es Preventivo:
→ Se sugiere próxima fecha automática.
Si Correctivo:
→ Se vincula a falla detectada.

MÓDULO 7: REPUESTOS Y MATERIALES
Campos:
Código


Descripción


Cantidad


Precio unitario


Subtotal



🔒 Reglas:
Validar stock disponible.


Reservar inventario al aprobar.


Si no hay stock → generar solicitud de compra.


Registrar lote si aplica.



MÓDULO 8: MANO DE OBRA
Campos:
Descripción


Horas estimadas


Precio por hora


Subtotal



🔒 Reglas:
Registrar horas reales.


Calcular eficiencia:

Eficiencia = Horas estimadas / Horas reales


Impacta evaluación del mecánico.



MÓDULO 9: MECÁNICO RESPONSABLE
Debe registrar:
Nombre


DNI


Especialidad


Firma digital



🔒 Reglas:
Solo mecánicos activos pueden asignarse.


Si especialidad no coincide → advertencia.


Registrar comisión automática si aplica.



MÓDULO 10: CONTROL DE CALIDAD
Checklist obligatorio post-mantenimiento:
Encendido correcto


Frenos funcionales


Luces operativas


Sin fugas


Prueba de manejo



🔒 Regla crítica:
No se puede cerrar orden sin control de calidad completado.

MÓDULO 11: ESTADO FINAL
Estados posibles:
Excelente


Bueno


Aceptable


Requiere revisión adicional



🔒 Lógica:
Si "Requiere revisión adicional":
→ No permitir facturación.
→ Volver a estado En proceso.

MÓDULO 12: COSTOS Y FACTURACIÓN
Cálculo automático:
Total Repuestos
Total Mano de Obra


Descuentos


Impuestos
= TOTAL A PAGAR



🔒 Validaciones:
No facturar si no está Finalizada.


Si es Garantía → total = 0 (según reglas).


Permitir pago parcial.


Registrar método de pago.



MÓDULO 13: PRÓXIMA REVISIÓN
Debe permitir:
Fecha recomendada


Kilometraje recomendado


Tipo de mantenimiento futuro



🔒 Lógica automática:
Si mantenimiento preventivo:
→ Generar recordatorio automático.
Si motocicleta de reparto:
→ Intervalo reducido sugerido.

MÓDULO 14: CONDICIONES Y AUTORIZACIONES
Debe registrar:
Autorización trabajos


Autorización tipo repuestos


Aceptación costos


Firma digital cliente obligatoria antes de ejecutar trabajos.

4️⃣ ESTADOS COMPLETOS DE LA ORDEN
Registrada


En inspección


En diagnóstico


Cotización pendiente


Esperando aprobación


Aprobada


En proceso


Control de calidad


Lista para entrega


Facturada


Entregada


Cerrada


Cancelada



5️⃣ ALERTAS OPERATIVAS
Vehículo con crédito atrasado


Kilometraje excedido vs último servicio


OT sin movimiento > 24h


Garantía próxima a vencer


Cliente frecuente inactivo


Stock bajo repuestos críticos


Mantenimiento preventivo pendiente



6️⃣ KPIs ESPECIALIZADOS PARA MOTOS Y MOTOTAXIS
Frecuencia promedio mantenimiento


Vida útil promedio de repuestos


Rentabilidad por tipo vehículo


Repuestos más cambiados


Fallas recurrentes por modelo


Tasa de retrabajo


Ticket promedio


Utilidad por orden



7️⃣ DIFERENCIADORES ESTRATÉGICOS
Este sistema:
✔ Reduce reclamos legales (inspección documentada)
✔ Controla crédito financiero
✔ Controla calidad antes de entrega
✔ Programa mantenimiento futuro
✔ Genera historial técnico real
✔ Permite análisis por modelo de moto

