"""Cálculos del reporte "Cartera y financieras" (sin ORM, para poder probarlos aislados).

Reglas de precisión
-------------------
* Todo monto se convierte a céntimos enteros (int) con redondeo HALF_UP al entrar.
  Las sumas se hacen sobre enteros, así que los totales cuadran al céntimo con las filas.
* Una cuota de la financiera cuenta como pagada desde su fecha de vencimiento (mismo criterio
  que calcular_resumen en financiera_resumen.py): ADT paga a la financiera siempre a tiempo.
* Interés devengado para liquidar hoy: saldo_capital · ((1 + TEA)^(días/360) − 1), la misma
  fórmula con la que la financiera arma su cronograma (verificada al céntimo en el PDF).

Identidades que se verifican en cada cuenta (cuadre)
----------------------------------------------------
  cliente:     total_cronograma = cobrado + por_cobrar
               por_cobrar       = vigente + vencido = Σ tramos de atraso + vigente
  financiera:  total            = pagado + pendiente
               pendiente        = capital + interés + otros cargos   (solo con cronograma PDF)
  ganancia:    esperada         = realizada + por_realizar
"""
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from .financiera_resumen import cantidad_cuotas, fechas_cuotas

TRAMOS_ATRASO = (('1_30', 1, 30), ('31_60', 31, 60), ('61_90', 61, 90), ('91_mas', 91, None))
ATRASADO = 'atrasado'


def cents(valor):
    """Monto en soles -> céntimos enteros, redondeo HALF_UP (el contable, no el bancario)."""
    if not valor:
        return 0
    return int(Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * 100)


def mes(fecha):
    return fecha.strftime('%Y-%m')


def tramo_atraso(dias):
    for clave, desde, hasta in TRAMOS_ATRASO:
        if dias >= desde and (hasta is None or dias <= hasta):
            return clave
    return None


# --------------------------------------------------------------------------- cliente -> ADT

def resumen_cliente(hoy, cuotas):
    """cuotas: [{'monto', 'saldo', 'fecha', 'state'}] de tipo 'cuota' de una cuenta.

    Devuelve lo que el cliente debe a ADT, en céntimos.
    """
    r = {
        'total': 0, 'por_cobrar': 0, 'vencido': 0, 'vigente': 0, 'dias_atraso': 0,
        'cuotas_restantes': 0, 'cuotas_vencidas': 0, 'sin_fecha': 0, 'cuota': 0,
        'tramos': {clave: 0 for clave, _d, _h in TRAMOS_ATRASO},
        'por_mes': {},
    }
    montos_pendientes = {}
    for q in cuotas:
        if q['state'] == 'anulada':
            continue
        monto = cents(q['monto'])
        saldo = min(max(cents(q['saldo']), 0), monto)
        r['total'] += monto
        if saldo <= 0:
            continue
        r['por_cobrar'] += saldo
        r['cuotas_restantes'] += 1
        montos_pendientes[monto] = montos_pendientes.get(monto, 0) + 1
        fecha = q['fecha']
        if not fecha:
            # Sin fecha no se puede saber si está vencida: se reporta aparte como vigente.
            r['sin_fecha'] += saldo
            r['vigente'] += saldo
            continue
        if fecha < hoy:
            dias = (hoy - fecha).days
            r['vencido'] += saldo
            r['cuotas_vencidas'] += 1
            r['tramos'][tramo_atraso(dias)] += saldo
            r['dias_atraso'] = max(r['dias_atraso'], dias)
            clave = ATRASADO
        else:
            r['vigente'] += saldo
            clave = mes(fecha)
        r['por_mes'][clave] = r['por_mes'].get(clave, 0) + saldo
    r['cobrado'] = r['total'] - r['por_cobrar']
    if montos_pendientes:
        # Cuota del cliente = el monto que más se repite entre las pendientes.
        r['cuota'] = max(montos_pendientes.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return r


# --------------------------------------------------------------------------- ADT -> financiera

def _vacio_financiera(fuente):
    return {
        'fuente': fuente, 'total': 0, 'pagado': 0, 'pagado_estimado': 0, 'pendiente': 0,
        'capital': None, 'interes': None, 'otros': None, 'interes_devengado': None,
        'para_liquidar': None, 'cuota': 0, 'proxima_fecha': None, 'proxima_monto': 0,
        'cuotas_pendientes': 0, 'dia_cierre': None, 'fecha_fin': None, 'por_mes': {},
        # Todas las cuotas a la financiera (pagadas y por pagar) por mes de vencimiento.
        'calendario': {},
    }


def _sumar_mes(mapa, fecha, monto):
    mapa[mes(fecha)] = mapa.get(mes(fecha), 0) + monto


def resumen_financiera_pdf(hoy, filas, tea, fecha_desembolso, monto_cuota_pdf):
    """filas: cronograma leído del PDF [{'nro', 'fecha', 'capital', 'interes', 'total'}], ordenado.

    Las cuotas anteriores a la primera del PDF ya estaban pagadas al emitirse: se estiman con la
    cuota del PDF y se informan aparte en 'pagado_estimado'.
    """
    r = _vacio_financiera('pdf')
    if not filas:
        return r
    r['capital'] = r['interes'] = r['otros'] = 0
    r['dia_cierre'] = filas[0]['fecha'].day
    r['fecha_fin'] = filas[-1]['fecha']
    ultima_vencida = None
    for f in filas:
        total = cents(f['total'])
        r['total'] += total
        _sumar_mes(r['calendario'], f['fecha'], total)
        if f['fecha'] <= hoy:
            r['pagado'] += total
            ultima_vencida = f['fecha']
            continue
        capital, interes = cents(f['capital']), cents(f['interes'])
        r['pendiente'] += total
        r['capital'] += capital
        r['interes'] += interes
        r['otros'] += total - capital - interes
        r['cuotas_pendientes'] += 1
        r['por_mes'][mes(f['fecha'])] = r['por_mes'].get(mes(f['fecha']), 0) + total
        if r['proxima_fecha'] is None:
            r['proxima_fecha'], r['proxima_monto'] = f['fecha'], total

    previas = filas[0]['nro'] - 1
    r['pagado_estimado'] = previas * cents(monto_cuota_pdf)
    for k in range(1, previas + 1):
        # Cuotas anteriores al PDF: mismo día, un mes antes cada una (estimadas).
        _sumar_mes(r['calendario'], filas[0]['fecha'] - relativedelta(months=k), cents(monto_cuota_pdf))
    r['pagado'] += r['pagado_estimado']
    r['total'] += r['pagado_estimado']
    r['cuota'] = r['proxima_monto'] or cents(monto_cuota_pdf)

    if r['cuotas_pendientes']:
        # Interés corrido desde el último vencimiento (o desde el desembolso / un mes antes de la
        # primera cuota del PDF) hasta hoy, sobre el saldo de capital.
        if ultima_vencida:
            desde = ultima_vencida
        elif filas[0]['nro'] == 1 and fecha_desembolso:
            desde = fecha_desembolso
        else:
            desde = filas[0]['fecha'] - relativedelta(months=1)
        dias = max((hoy - desde).days, 0)
        factor = (1 + (tea or 0.0) / 100.0) ** (dias / 360.0) - 1
        devengado = cents(r['capital'] / 100.0 * factor)
        r['interes_devengado'] = devengado
        r['para_liquidar'] = r['capital'] + devengado
    else:
        r['interes_devengado'] = r['para_liquidar'] = 0
    return r


def resumen_financiera_manual(hoy, fecha_inicio, es_mensual, fecha_fin, monto_cuota, monto_total,
                              cancelada_manual):
    """Datos cargados a mano en la pestaña Financiera antigua: solo montos nominales."""
    r = _vacio_financiera('manual')
    total, cuota = cents(monto_total), cents(monto_cuota)
    if total <= 0 or cuota <= 0:
        return _vacio_financiera('sin_datos')
    cantidad = cantidad_cuotas(cuota, total)
    montos = [min(cuota, total - k * cuota) for k in range(cantidad)]
    montos[-1] = total - (cantidad - 1) * cuota
    fechas = fechas_cuotas(fecha_inicio, es_mensual, fecha_fin, cantidad)
    r['total'], r['cuota'] = total, cuota
    for fecha, monto in zip(fechas, montos):
        _sumar_mes(r['calendario'], fecha, monto)
    if cancelada_manual:
        r['pagado'] = total
        return r
    if not fechas:
        # Sin fecha de inicio no se sabe qué está pagado: todo se considera pendiente.
        r['pendiente'] = total
        r['cuotas_pendientes'] = cantidad
        return r
    r['dia_cierre'] = fechas[0].day
    r['fecha_fin'] = fechas[-1]
    for fecha, monto in zip(fechas, montos):
        if fecha <= hoy:
            r['pagado'] += monto
            continue
        r['pendiente'] += monto
        r['cuotas_pendientes'] += 1
        r['por_mes'][mes(fecha)] = r['por_mes'].get(mes(fecha), 0) + monto
        if r['proxima_fecha'] is None:
            r['proxima_fecha'], r['proxima_monto'] = fecha, monto
    return r


# --------------------------------------------------------------------------- posición

def posicion(cli, fin):
    """Lo que le queda a ADT: cartera del cliente menos la deuda con la financiera (céntimos)."""
    p = {
        'neto_nominal': cli['por_cobrar'] - fin['pendiente'],
        'neto_liquidar': (cli['por_cobrar'] - fin['para_liquidar']
                          if fin['para_liquidar'] is not None else None),
        'ganancia_esperada': cli['total'] - fin['total'],
        'ganancia_realizada': cli['cobrado'] - fin['pagado'],
        'ganancia_por_realizar': cli['por_cobrar'] - fin['pendiente'],
    }
    p['cuadre'] = verificar_cuadre(cli, fin, p)
    return p


def verificar_cuadre(cli, fin, p):
    """Lista de identidades que NO cuadran (vacía = todo cuadra al céntimo)."""
    errores = []
    if cli['total'] != cli['cobrado'] + cli['por_cobrar']:
        errores.append('cliente: total ≠ cobrado + por cobrar')
    if cli['por_cobrar'] != cli['vigente'] + cli['vencido']:
        errores.append('cliente: por cobrar ≠ vigente + vencido')
    if cli['vencido'] != sum(cli['tramos'].values()):
        errores.append('cliente: vencido ≠ Σ tramos de atraso')
    if fin['total'] != fin['pagado'] + fin['pendiente']:
        errores.append('financiera: total ≠ pagado + pendiente')
    if fin['capital'] is not None and fin['pendiente'] != fin['capital'] + fin['interes'] + fin['otros']:
        errores.append('financiera: pendiente ≠ capital + interés + otros')
    if p['ganancia_esperada'] != p['ganancia_realizada'] + p['ganancia_por_realizar']:
        errores.append('ganancia: esperada ≠ realizada + por realizar')
    return errores
