# Pagos y documentos desde Flota 360

En Crédito y cuotas, los accesos de pago individual, pago en cascada y pago de mora abren el popup JavaScript de Flota 360. Las acciones existentes de ADT Comercial se mantienen como fuente de la información y del registro contable.

El formulario muestra capital pendiente, mora a la fecha e importe a recibir. Permite elegir fecha, operación y diario de la empresa, registrar abonos parciales y ajustar manualmente la mora. En cascada, permite pagar todo o introducir un abono para distribuir desde la cuota más antigua. El diario de cascada se determina por la lógica existente de ADT Comercial.

Los importes y la mora automática se recalculan en el servidor al guardar. Se validan permisos, vehículo, empresa, estado de la cuenta, diario, operación e importe; se rechazan operaciones duplicadas y se serializan los pagos de una cuenta. La interfaz bloquea envíos repetidos mientras registra el pago. Los errores quedan dentro del popup y la ficha se actualiza al terminar.

En Resumen, **Imprimir documentos** da acceso directo a **Acta de entrega vehicular** y **Contrato TVS**, usando los reportes existentes de `adt_fleet`. Si ese módulo no está disponible, las opciones no se muestran.

Actualizar `adt_flota_360`, reiniciar Odoo y recargar los recursos del navegador para instalar el cambio. No se modifican las plantillas de los documentos ni las reglas de distribución de pagos.
