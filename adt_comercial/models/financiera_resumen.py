from datetime import timedelta

from dateutil.relativedelta import relativedelta


def cantidad_cuotas(monto_cuota, monto_total):
    """Cuotas que se pagan a la financiera (monto total / monto de cuota)."""
    if monto_cuota <= 0 or monto_total <= 0:
        return 0
    return max(1, int(round(monto_total / monto_cuota)))


def fechas_cuotas(fecha_inicio, es_mensual, fecha_fin, cantidad):
    """Fechas de pago a la financiera. La cuota 1 vence en la fecha de inicio.

    Mensual: cada mes. No mensual: repartidas en partes iguales hasta la fecha fin.
    """
    if not fecha_inicio or cantidad <= 0:
        return []
    if es_mensual or not fecha_fin or fecha_fin <= fecha_inicio or cantidad == 1:
        return [fecha_inicio + relativedelta(months=k) for k in range(cantidad)]
    paso = (fecha_fin - fecha_inicio).days / (cantidad - 1)
    return [fecha_inicio + timedelta(days=round(paso * k)) for k in range(cantidad)]


def calcular_resumen(hoy, fecha_inicio, es_mensual, fecha_fin,
                     monto_cuota, monto_total, total_cliente, cobrado_cliente,
                     cancelada_manual=False):
    """Compara lo que ADT paga a la financiera con lo que cobra al cliente.

    * La financiera se paga siempre a tiempo: una cuota cuenta como pagada desde su fecha.
    * Si la financiera se canceló manualmente (pago anticipado), todo está pagado.
    * Punto de equilibrio: cuando lo cobrado al cliente alcanza el monto total de la
      financiera. Lo que se cobra después es ganancia de ADT.
    """
    cantidad = cantidad_cuotas(monto_cuota, monto_total)
    fechas = fechas_cuotas(fecha_inicio, es_mensual, fecha_fin, cantidad)
    pagadas = cantidad if cancelada_manual else sum(1 for f in fechas if f <= hoy)
    if cantidad and pagadas >= cantidad:
        pagado = monto_total
    else:
        pagado = min(pagadas * monto_cuota, monto_total)
    return {
        'cantidad_cuotas': cantidad,
        'cuotas_pagadas': pagadas,
        'pagado': pagado,
        'pendiente': monto_total - pagado,
        'ganancia_esperada': total_cliente - monto_total,
        'ganancia_actual': max(cobrado_cliente - monto_total, 0.0),
        'faltante_equilibrio': max(monto_total - cobrado_cliente, 0.0),
        'caja_neta': cobrado_cliente - pagado,
    }
