import logging
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

GRUPOS_ACCESO = ('adt_comercial.group_access_adt_comercial_gerencia', 'base.group_system')
MESES = 12
DIAS_ESTANCADO = 7

# Umbrales de las alertas.
PAR30_ALERTA, PAR30_CRITICO = 5.0, 10.0
COBRO_ALERTA, COBRO_CRITICO = 95.0, 85.0
COBERTURA_MIN, COBERTURA_MAX = 1.0, 4.0     # meses de ventas que cubre el stock
SIN_PLACA_ALERTA = 30.0                     # % del stock sin placa

ACCIONES = {
    'cobranza': 'adt_comercial.action_reporte_cobranzas',
    'financieras': 'adt_comercial.action_dashboard_financiera',
    'clientes': 'adt_comercial.action_dashboard_clientes',
    'flota': 'adt_dashboard_flota.action_adt_fleet_dashboard',
    'expedientes': 'adt_expedientes.action_adt_expediente_dashboard',
}


def _n(cantidad, singular, plural):
    """'1 cuenta' / '3 cuentas'."""
    return '%d %s' % (cantidad, singular if cantidad == 1 else plural)


def _pct(parte, total):
    return round(parte * 100.0 / total, 1) if total else 0.0


class AdtCeoDashboard(models.AbstractModel):
    """Dashboard Ejecutivo: resume los dashboards de cada área y genera alertas para decidir.

    Llama a los mismos métodos que usa cada dashboard, así los números coinciden siempre.
    """
    _name = 'adt.ceo.dashboard'
    _description = 'Dashboard ejecutivo'

    def _check_acceso(self):
        if not any(self.env.user.has_group(g) for g in GRUPOS_ACCESO):
            raise AccessError(_("El Dashboard Ejecutivo es solo para gerencia."))

    def _fuente(self, modelo, sudo=False):
        """Datos de un dashboard de área. Si falla, el resto del tablero sigue funcionando."""
        try:
            with self.env.cr.savepoint():
                model = self.env[modelo]
                return (model.sudo() if sudo else model).get_dashboard_data()
        except Exception:
            _logger.exception("Dashboard Ejecutivo: no se pudieron leer los datos de %s", modelo)
            return None

    # ------------------------------------------------------------------ resúmenes por área
    @staticmethod
    def _meses(hoy):
        return [(hoy - relativedelta(months=i)).strftime('%Y-%m') for i in range(MESES - 1, -1, -1)]

    def _ventas(self, hoy):
        desde = (hoy - relativedelta(months=MESES - 1)).replace(day=1)
        cuentas = self.env['adt.comercial.cuentas'].sudo().search_read(
            [('fecha_desembolso', '>=', desde), ('fecha_desembolso', '<=', hoy),
             '|', ('state', 'in', ['en_curso', 'pagado']), '&', ('state', '=', 'cancelado'), ('recuperado', '=', True)],
            ['fecha_desembolso', 'monto_total'])
        por_mes = defaultdict(lambda: {'n': 0, 'monto': 0.0})
        for c in cuentas:
            m = por_mes[c['fecha_desembolso'].strftime('%Y-%m')]
            m['n'] += 1
            m['monto'] += c['monto_total'] or 0.0
        meses = self._meses(hoy)
        serie = [{'mes': m, 'n': por_mes[m]['n'], 'monto': por_mes[m]['monto']} for m in meses]
        anteriores = serie[-4:-1]                  # los 3 meses completos anteriores
        promedio = sum(s['n'] for s in anteriores) / 3.0
        actual = serie[-1]
        dias_mes = (hoy + relativedelta(day=31)).day
        ritmo = actual['n'] * dias_mes / hoy.day   # proyección del mes al ritmo actual
        return {
            'serie': serie, 'mes_n': actual['n'], 'mes_monto': actual['monto'],
            'promedio_mensual': round(promedio, 1), 'proyeccion_mes': round(ritmo, 1),
        }

    def _cobranza(self, data, hoy):
        if not data:
            return None
        hoy_s = fields.Date.to_string(hoy)
        mes = hoy_s[:7]
        cuentas = data['cuentas']
        conteo = defaultdict(int)
        for c in cuentas:
            conteo[c['estado']] += 1
        saldo = sum(c['saldo_pendiente'] for c in cuentas)
        riesgo = sum(c['saldo_pendiente'] for c in cuentas if c['dias'] > 30)
        cobrado_mes = defaultdict(float)
        for p in data['pagos']:
            cobrado_mes[p['fecha'][:7]] += p['cuota'] + p['mora']
        programado_mes = defaultdict(float)
        vencia_hasta_hoy = 0.0
        por_vencer_mes = 0.0
        for p in data['programado']:
            programado_mes[p['fecha'][:7]] += p['monto']
            if p['fecha'][:7] == mes:
                if p['fecha'] <= hoy_s:
                    vencia_hasta_hoy += p['monto']
                else:
                    por_vencer_mes += p['monto']
        cobrado_hoy = sum(p['cuota'] + p['mora'] for p in data['pagos'] if p['fecha'] == hoy_s)
        return {
            'cuentas': len(cuentas),
            'estados': dict(conteo),
            'saldo': saldo,
            'vencido': sum(c['vencido'] for c in cuentas),
            'par30': _pct(riesgo, saldo),
            'riesgo': riesgo,
            'mas_30': sum(1 for c in cuentas if c['dias'] > 30),
            'urgentes': sum(1 for c in cuentas if c['estado'] == 'orden' and c['prioridad'] == 'urgente'),
            'cobrado_hoy': cobrado_hoy,
            'cobrado_mes': cobrado_mes[mes],
            'vencia_mes_hasta_hoy': vencia_hasta_hoy,
            'por_vencer_mes': por_vencer_mes,
            'tasa_cobro_mes': _pct(cobrado_mes[mes], vencia_hasta_hoy),
            # vencido_a_hoy: en el mes en curso solo cuenta lo que ya venció, para no castigar el % por días que faltan.
            'serie': [{'mes': m, 'cobrado': cobrado_mes[m], 'programado': programado_mes[m],
                       'vencido_a_hoy': vencia_hasta_hoy if m == mes else programado_mes[m]} for m in self._meses(hoy)],
        }

    def _financieras(self, data, hoy):
        if not data:
            return None
        mes = hoy.strftime('%Y-%m')
        siguiente = (hoy + relativedelta(months=1)).strftime('%Y-%m')
        cuentas = data['cuentas']
        desfase = [c for c in cuentas if c['semaforo'] == 'desfase']
        pagos = data['pagos_financiera']
        return {
            'cuentas': len(cuentas),
            'ganancia_actual': sum(c['ganancia_actual'] for c in cuentas),
            'ganancia_esperada': sum(c['ganancia_esperada'] for c in cuentas),
            'pendiente': sum(c['pendiente'] for c in cuentas),
            'pagado': sum(c['pagado'] for c in cuentas),
            'total': sum(c['total_financiera'] for c in cuentas),
            'pagar_mes': sum(p['monto'] for p in pagos if p['mes'] == mes),
            'pagar_siguiente': sum(p['monto'] for p in pagos if p['mes'] == siguiente),
            'desfase_cuentas': len(desfase),
            'adelantado': -sum(c['caja_neta'] for c in desfase),
        }

    def _clientes(self, data, hoy):
        if not data:
            return None
        clientes = data['clientes']
        limite = fields.Date.to_string(hoy + timedelta(days=data['dias_proximos']))
        hoy_s = fields.Date.to_string(hoy)
        conteo = defaultdict(int)
        for c in clientes:
            conteo[c['segmento']] += 1
        aptos = [c for c in clientes if c['segmento'] == 'apto']
        terminaron = [c for c in clientes if c['n_terminados']]
        return {
            'total': len(clientes),
            'segmentos': dict(conteo),
            'etiquetas': data['segmentos'],
            'aptos': len(aptos),
            'aptos_sin_contactar': sum(1 for c in aptos if not c['seguimiento'] or c['seguimiento']['estado'] == 'por_contactar'),
            'oportunidad': sum(c['ultimo_monto'] or 0.0 for c in aptos),
            'terminaron': len(terminaron),
            'recompra': _pct(sum(1 for c in terminaron if c['recompra']), len(terminaron)),
            'pronto': sum(1 for c in clientes if c['segmento'] == 'pagando_bien' and c['termina'] and c['termina'] <= limite),
            'llamar_hoy': sum(1 for c in clientes if c['seguimiento'] and c['seguimiento']['proximo_contacto']
                              and c['seguimiento']['proximo_contacto'] <= hoy_s
                              and c['seguimiento']['estado'] not in ('no_interesado', 'nuevo_prestamo')),
            'no_prestar': conteo['no_prestar'],
        }

    def _flota(self, data):
        if not data:
            return None
        vehiculos = data['vehicles']
        stock = [v for v in vehiculos if not v['has_owner']]
        placas = defaultdict(int)
        modelos = defaultdict(int)
        for v in stock:
            placas[v['plate_status']] += 1
            modelos[v['model']] += 1
        return {
            'total': len(vehiculos),
            'stock': len(stock),
            'placas': dict(placas),
            'sin_placa_pct': _pct(len(stock) - placas['lista'], len(stock)),
            'modelos': sorted(({'modelo': k, 'n': n} for k, n in modelos.items()), key=lambda x: -x['n'])[:6],
        }

    def _expedientes(self, data, hoy):
        if not data:
            return None
        grupo = {e['key']: e['grupo'] for e in data['estados']}
        xs = data['expedientes']
        hace30 = fields.Date.to_string(hoy - timedelta(days=30))
        hace90 = fields.Date.to_string(hoy - timedelta(days=90))
        ultimos90 = [x for x in xs if x['fecha'] and x['fecha'] >= hace90]
        aprob90 = sum(1 for x in ultimos90 if grupo.get(x['estado']) == 'aprobado')
        rech90 = sum(1 for x in ultimos90 if grupo.get(x['estado']) == 'rechazado')
        en_proceso = [x for x in xs if grupo.get(x['estado']) == 'en_proceso']
        por_mes = defaultdict(int)
        for x in xs:
            if x['fecha']:
                por_mes[x['fecha'][:7]] += 1
        estados = defaultdict(int)
        for x in en_proceso + [x for x in xs if x['estado'] == 'aprobado_sin_desembolso']:
            estados[x['estado']] += 1
        return {
            'etiquetas': {e['key']: e['label'] for e in data['estados']},
            'en_proceso': len(en_proceso),
            'estancados': sum(1 for x in en_proceso if x['fecha'] and
                              (hoy - fields.Date.from_string(x['fecha'])).days > DIAS_ESTANCADO),
            'sin_desembolso': sum(1 for x in xs if x['estado'] == 'aprobado_sin_desembolso'),
            'ingresados_30': sum(1 for x in xs if x['fecha'] and x['fecha'] >= hace30),
            'tasa_aprobacion_90': _pct(aprob90, aprob90 + rech90),
            'pipeline': dict(estados),
            'serie': [{'mes': m, 'n': por_mes[m]} for m in self._meses(hoy)],
        }

    # ------------------------------------------------------------------ alertas
    def _alertas(self, hoy, ventas, cob, fin, cli, flota, exp):
        """Frases cortas y accionables, ordenadas de lo más grave a lo informativo."""
        alertas = []
        simbolo = self.env.company.currency_id.symbol

        def dinero(valor):
            return '{} {:,.0f}'.format(simbolo, valor)

        def add(nivel, area, titulo, texto):
            alertas.append({'nivel': nivel, 'area': area, 'titulo': titulo, 'texto': texto})

        if cob:
            par = cob['par30']
            if par >= PAR30_CRITICO:
                add('bad', 'cobranza', 'Morosidad alta: %.1f%% de la cartera con más de 30 días' % par,
                    '%s más de 30 días. Prioriza su cobranza o captura.' % _n(cob['mas_30'], 'cuenta debe hace', 'cuentas deben hace'))
            elif par >= PAR30_ALERTA:
                add('warn', 'cobranza', 'Morosidad en vigilancia: %.1f%% con más de 30 días' % par,
                    '%s con más de 30 días de atraso.' % _n(cob['mas_30'], 'cuenta', 'cuentas'))
            else:
                add('ok', 'cobranza', 'Morosidad controlada: %.1f%% con más de 30 días' % par,
                    'La cartera en riesgo está por debajo del %d%%.' % PAR30_ALERTA)
            if cob['vencia_mes_hasta_hoy'] > 0:
                tasa = cob['tasa_cobro_mes']
                nivel = 'bad' if tasa < COBRO_CRITICO else 'warn' if tasa < COBRO_ALERTA else 'ok'
                add(nivel, 'cobranza', 'Este mes se cobró el %.0f%% de lo que vencía' % tasa,
                    'Cobrado %s de %s vencidos a la fecha.' % (dinero(cob['cobrado_mes']), dinero(cob['vencia_mes_hasta_hoy'])))
            if cob['urgentes']:
                add('warn', 'cobranza', _n(cob['urgentes'], 'orden de captura urgente', 'órdenes de captura urgentes'),
                    'Hay cuentas marcadas como urgentes para captura.')
        if fin:
            if cob and fin['pagar_mes'] > cob['por_vencer_mes']:
                add('warn', 'financieras', 'Este mes sale más de lo que entra',
                    'En lo que queda del mes se pagan %s a financieras y vencen %s de clientes.' % (
                        dinero(fin['pagar_mes']), dinero(cob['por_vencer_mes'])))
            if fin['adelantado'] > 0.5:
                add('warn', 'financieras', 'ADT adelanta %s a financieras' % dinero(fin['adelantado']),
                    '%s: se pagó a la financiera más de lo cobrado al cliente.' % _n(fin['desfase_cuentas'], 'cuenta', 'cuentas'))
        if flota and ventas:
            prom = ventas['promedio_mensual']
            if prom > 0:
                cobertura = flota['stock'] / prom
                if cobertura < COBERTURA_MIN:
                    add('bad', 'flota', 'Stock para menos de un mes de ventas',
                        '%s en stock y se venden ~%.0f al mes. Conviene reponer.' % (_n(flota['stock'], 'moto', 'motos'), prom))
                elif cobertura > COBERTURA_MAX:
                    add('warn', 'flota', 'Stock para %.1f meses de ventas' % cobertura,
                        '%s sin dueño: capital inmovilizado. Evalúa impulsar ventas o pausar compras.' % _n(flota['stock'], 'moto', 'motos'))
            if flota['stock'] and flota['sin_placa_pct'] >= SIN_PLACA_ALERTA:
                add('warn', 'flota', '%.0f%% del stock no tiene placa lista' % flota['sin_placa_pct'],
                    'Sin placa no se puede entregar la moto. Revisa los trámites pendientes.')
        # Desde el día 10: antes la proyección del mes no es confiable.
        if hoy.day >= 10 and ventas['promedio_mensual'] > 0 and ventas['proyeccion_mes'] < ventas['promedio_mensual'] * 0.7:
            add('warn', 'ventas', 'Ventas del mes por debajo del promedio',
                'Al ritmo actual cerrarías ~%.0f créditos; el promedio es %.0f.' % (
                    ventas['proyeccion_mes'], ventas['promedio_mensual']))
        if exp:
            if exp['sin_desembolso']:
                add('info', 'expedientes', _n(exp['sin_desembolso'], 'venta aprobada espera', 'ventas aprobadas esperan') + ' desembolso',
                    'Expedientes aprobados que aún no se convierten en crédito.')
            if exp['estancados']:
                add('warn', 'expedientes', '%s más de %d días en proceso' % (
                    _n(exp['estancados'], 'expediente lleva', 'expedientes llevan'), DIAS_ESTANCADO),
                    'Revisa qué documentos faltan para destrabarlos.')
        if cli and cli['aptos']:
            add('info', 'clientes', _n(cli['aptos'], 'cliente listo', 'clientes listos') + ' para un nuevo préstamo',
                'Oportunidad de %s. %d aún sin contactar.' % (dinero(cli['oportunidad']), cli['aptos_sin_contactar']))

        orden = {'bad': 0, 'warn': 1, 'info': 2, 'ok': 3}
        return sorted(alertas, key=lambda a: orden[a['nivel']])

    # ------------------------------------------------------------------ datos
    @api.model
    def get_dashboard_data(self):
        self._check_acceso()
        hoy = fields.Date.context_today(self)
        ventas = self._ventas(hoy)
        cob = self._cobranza(self._fuente('adt.comercial.cobranza.dashboard'), hoy)
        fin = self._financieras(self._fuente('adt.comercial.financiera.dashboard', sudo=True), hoy)
        cli = self._clientes(self._fuente('adt.comercial.clientes.dashboard'), hoy)
        flota = self._flota(self._fuente('adt.fleet.dashboard', sudo=True))
        exp = self._expedientes(self._fuente('adt.expediente.dashboard', sudo=True), hoy)
        if flota and ventas['promedio_mensual']:
            flota['cobertura_meses'] = round(flota['stock'] / ventas['promedio_mensual'], 1)
        moneda = self.env.company.currency_id
        return {
            'hoy': fields.Date.to_string(hoy),
            'moneda': {'simbolo': moneda.symbol, 'posicion': moneda.position},
            'ventas': ventas,
            'cobranza': cob,
            'financieras': fin,
            'clientes': cli,
            'flota': flota,
            'expedientes': exp,
            'alertas': self._alertas(hoy, ventas, cob, fin, cli, flota, exp),
            'acciones': ACCIONES,
        }
