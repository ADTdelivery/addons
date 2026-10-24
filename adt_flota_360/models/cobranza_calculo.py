"""Cálculos de "Cobranza y rentabilidad" (sin ORM, para poder probarlos aislados).

Montos en céntimos enteros (cartera_calculo.cents). Las semanas van de lunes a domingo.

Morosidad semanal
-----------------
Cada cuota del cronograma se agrupa con sus subcuotas: un pago parcial deja la cuota original
"pagada" por lo abonado y crea una subcuota con el resto (fechada el día del pago). El grupo
reconstruye la cuota original:

  esperado      = Σ monto del grupo, en la semana de la fecha de la cuota original
  pendiente hoy = Σ saldo del grupo                     (mismo dato que "Por cobrar")
  no pagado al cierre de la semana = pendiente hoy + pagos posteriores al domingo

Lo que cubre ADT
----------------
ADT paga la financiera mensual aunque el cliente no pague su semana. A cada cuota del cliente
le corresponde la parte de la financiera que se devenga en su periodo (desde la cuota anterior
hasta su fecha), repartida por días:

  ADT cubrió       = mín(no pagado al cierre, parte de la financiera de ese periodo)
  sigue cubriendo  = mín(pendiente hoy, parte)   (cubrió − sigue cubriendo = ya lo recuperó)

Lo que el cliente no paga por encima de esa parte no sale de caja: es margen que se deja de ganar.
"""
import re
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo.addons.adt_comercial.models.cartera_calculo import cents
from odoo.addons.adt_comercial.models.financiera_resumen import cantidad_cuotas, fechas_cuotas

DIAS_PERIODO = {'semanal': 7, 'quincena': 15, 'mensual': 30}


def lunes(fecha):
    return fecha - timedelta(days=fecha.weekday())


def semanas(hoy, cantidad):
    """Lunes de las últimas `cantidad` semanas cerradas más la semana en curso (la última)."""
    actual = lunes(hoy)
    return [actual - timedelta(weeks=k) for k in range(cantidad, -1, -1)]


# --------------------------------------------------------------------------- financiera

def cuotas_financiera_pdf(filas, monto_cuota_pdf):
    """[(fecha, céntimos)] del plan de la financiera leído del PDF, con las cuotas anteriores al
    PDF estimadas un mes antes cada una (mismo criterio que resumen_financiera_pdf)."""
    if not filas:
        return []
    previas = [(filas[0]['fecha'] - relativedelta(months=k), cents(monto_cuota_pdf))
               for k in range(filas[0]['nro'] - 1, 0, -1)]
    return previas + [(f['fecha'], cents(f['total'])) for f in filas]


def cuotas_financiera_manual(fecha_inicio, es_mensual, fecha_fin, monto_cuota, monto_total):
    """[(fecha, céntimos)] de la financiera cargada a mano (mismo reparto que resumen_financiera_manual)."""
    total, cuota = cents(monto_total), cents(monto_cuota)
    if total <= 0 or cuota <= 0:
        return []
    cantidad = cantidad_cuotas(cuota, total)
    montos = [cuota] * (cantidad - 1) + [total - (cantidad - 1) * cuota]
    return list(zip(fechas_cuotas(fecha_inicio, es_mensual, fecha_fin, cantidad), montos))


def devengado(fin, desde, hasta):
    """Parte de la financiera que corresponde al periodo (desde, hasta]: cada cuota se reparte por
    días entre su vencimiento anterior (un mes antes para la primera) y el suyo."""
    if not fin or hasta <= desde:
        return 0
    total = 0.0
    previo = fin[0][0] - relativedelta(months=1)
    for fecha, monto in fin:
        dias = (fecha - previo).days
        cruce = (min(fecha, hasta) - max(previo, desde)).days
        if dias > 0 and cruce > 0:
            total += monto * cruce / dias
        previo = fecha
    return int(round(total))


def pagado_financiera(fin, desde, hasta):
    """Cuotas de la financiera que vencen en (desde, hasta]: ADT las paga en su fecha."""
    return sum(m for f, m in fin if (desde is None or f > desde) and f <= hasta)


# --------------------------------------------------------------------------- cliente

def agrupar_cuotas(cuotas):
    """cuotas: [{'id', 'parent_id', 'monto', 'saldo', 'fecha', 'state'}] de tipo cuota de una cuenta.

    Devuelve los grupos (cuota original + subcuotas) ordenados por fecha:
    [{'fecha', 'esperado', 'pendiente', 'ids'}]. Las anuladas no cuentan.
    """
    grupos = {}
    fechas = {}
    for q in cuotas:
        raiz = q['parent_id'] or q['id']
        if not q['parent_id']:
            fechas[raiz] = q['fecha']
        if q['state'] == 'anulada':
            continue
        monto = cents(q['monto'])
        g = grupos.setdefault(raiz, {'esperado': 0, 'pendiente': 0, 'ids': []})
        g['esperado'] += monto
        g['pendiente'] += min(max(cents(q['saldo']), 0), monto)
        g['ids'].append(q['id'])
    salida = []
    for raiz, g in grupos.items():
        g['fecha'] = fechas.get(raiz) or min(
            (q['fecha'] for q in cuotas if q['id'] in g['ids'] and q['fecha']), default=None)
        if g['fecha'] and g['esperado'] > 0:
            salida.append(g)
    return sorted(salida, key=lambda g: g['fecha'])


def semanal_credito(hoy, lunes_semanas, grupos, pagos, fin, periodicidad, hasta=None):
    """Morosidad semana a semana de un crédito y lo que hoy cubre ADT por él.

    pagos: {id_cuota: [(fecha, céntimos)]} pagos publicados de las cuotas.
    hasta: para un crédito cerrado (moto recuperada), solo cuentan las cuotas hasta esa fecha.

    Devuelve {'semanas': {índice: [esperado, no_pagado, cubierto, sigue_cubriendo]},
              'vencido', 'cubriendo', 'cuotas_vencidas'} en céntimos.
    """
    inicio = lunes_semanas[0]
    paso = DIAS_PERIODO.get(periodicidad, 7)
    r = {'semanas': {}, 'vencido': 0, 'cubriendo': 0, 'cuotas_vencidas': 0}
    anterior = None
    for g in grupos:
        fecha = g['fecha']
        desde = anterior or fecha - timedelta(days=paso)
        anterior = fecha
        if fecha >= hoy or (hasta and fecha > hasta):
            continue
        parte = devengado(fin, desde, fecha)
        if g['pendiente'] > 0:
            r['vencido'] += g['pendiente']
            r['cubriendo'] += min(g['pendiente'], parte)
            r['cuotas_vencidas'] += 1
        if fecha < inicio:
            continue
        semana = lunes(fecha)
        cierre = min(semana + timedelta(days=6), hoy)
        pagado = g['esperado'] - g['pendiente']
        despues = min(sum(m for f, m in (p for i in g['ids'] for p in pagos.get(i, ())) if f > cierre), pagado)
        no_pagado = min(g['pendiente'] + despues, g['esperado'])
        fila = r['semanas'].setdefault((semana - inicio).days // 7, [0, 0, 0, 0])
        fila[0] += g['esperado']
        fila[1] += no_pagado
        fila[2] += min(no_pagado, parte)
        fila[3] += min(g['pendiente'], parte)
    return r


def semanal_recuperada(lunes_semanas, fin, desde, hoy):
    """Lo que ADT paga a la financiera por una moto recuperada: por semana y desde la recuperación."""
    inicio = lunes_semanas[0]
    semanas_pago = {}
    for fecha, monto in fin:
        if (desde and fecha <= desde) or fecha > hoy or fecha < inicio:
            continue
        k = (lunes(fecha) - inicio).days // 7
        semanas_pago[k] = semanas_pago.get(k, 0) + monto
    return {'semanas': semanas_pago, 'pagado_desde': pagado_financiera(fin, desde, hoy)}


# --------------------------------------------------------------------------- rentabilidad

def rentabilidad_cuenta(cuenta, cuotas, pagos_mora):
    """Lo recaudado y lo que falta cobrar de un crédito (mismo criterio que la pestaña Rentabilidad
    de Flota 360): inicial + cuotas cobradas + cargos cobrados (incluye refinanciamiento) + moras.

    cuenta: {'state', 'monto_inicial', 'monto_fraccionado'}; cuotas: [{'type', 'monto', 'saldo', 'state'}];
    pagos_mora: céntimos de mora cobrada en los pagos de sus cuotas.
    """
    validas = [q for q in cuotas if q['state'] != 'anulada']
    cronograma = [q for q in validas if q['type'] == 'cuota']
    cobrado = lambda qs: sum(max(cents(q['monto']) - cents(q['saldo']), 0) for q in qs)
    inicial = cents(cuenta['monto_inicial'])
    cuotas_cobradas = cobrado(cronograma)
    cargos = cobrado([q for q in validas if q['type'] != 'cuota']) + pagos_mora
    vigente = cuenta['state'] in ('aprobado', 'en_curso')
    return {
        'inicial': inicial,
        'cuotas': cuotas_cobradas,
        'cargos': cargos,
        'recaudado': inicial + cuotas_cobradas + cargos,
        'por_cobrar': sum(max(cents(q['saldo']), 0) for q in cronograma) if vigente else 0,
        'pactado': inicial + (sum(cents(q['monto']) for q in cronograma) if cronograma
                              else cents(cuenta['monto_fraccionado'])),
    }


def refinanciamientos(nombres_por_cuenta):
    """Refinanciamientos detectados en los créditos de un titular con una moto (en orden): una cuenta
    que repite nombres de cuotas de las anteriores, o cuotas "Cuota R.…" (como el historial de Flota 360)."""
    anteriores = set()
    coincidencias = explicitos = 0
    for nombres in nombres_por_cuenta:
        nombres = {re.sub(r'\s+', ' ', n.strip()).casefold() for n in nombres if n}
        if anteriores & nombres:
            coincidencias += 1
        if any(re.match(r'^cuota\s+r\.', n) for n in nombres):
            explicitos += 1
        anteriores |= nombres
    return max(coincidencias, explicitos)
