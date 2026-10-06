from odoo import _, api, fields, models

from .financiera_resumen import cantidad_cuotas, fechas_cuotas

CAMPOS = [
    'reference_no', 'partner_id', 'partner_document', 'moto_modelo', 'moto_placa', 'tipo_financiera_id', 'fin_estado',
    'fin_semaforo', 'fin_monto_total', 'fin_pagado', 'fin_pendiente', 'fin_total_cliente',
    'fin_cobrado_cliente', 'fin_ganancia_actual', 'fin_ganancia_esperada', 'fin_caja_neta',
    'fin_fecha_inicio', 'fin_es_mensual', 'fin_fecha_fin', 'fin_monto_cuota', 'fin_cancelada_manual',
    'fin_cuotas_pagadas', 'fin_cantidad_cuotas',
]
ESTADOS_CUOTA_PENDIENTE = ['pendiente', 'a_cuenta', 'retrasado']
SIN_FECHA = 'sin_fecha'


def montos_cuotas_financiera(monto_cuota, monto_total):
    """Monto de cada cuota a la financiera; la última ajusta el redondeo para sumar el total."""
    cantidad = cantidad_cuotas(monto_cuota, monto_total)
    montos = [max(0.0, min(monto_cuota, monto_total - k * monto_cuota)) for k in range(cantidad)]
    if montos:
        montos[-1] = max(0.0, monto_total - (cantidad - 1) * monto_cuota)
    return montos


def pagos_pendientes_financiera(hoy, cuenta):
    """[(fecha | None, monto)] de las cuotas a la financiera que aún no vencen.

    Mismo criterio que calcular_resumen: una cuota cuenta como pagada desde su fecha.
    Sin fecha de inicio, lo pendiente se devuelve sin fecha.
    """
    if cuenta['fin_cancelada_manual']:
        return []
    montos = montos_cuotas_financiera(cuenta['fin_monto_cuota'], cuenta['fin_monto_total'])
    fechas = fechas_cuotas(cuenta['fin_fecha_inicio'], cuenta['fin_es_mensual'],
                           cuenta['fin_fecha_fin'], len(montos))
    if not fechas:
        pendiente = cuenta['fin_pendiente']
        return [(None, pendiente)] if pendiente > 0 else []
    return [(f, m) for f, m in zip(fechas, montos) if f > hoy and m > 0]


class AdtFinancieraDashboard(models.TransientModel):
    """Datos del Dashboard Gerencial de financieras (dashboard JS: adt_financiera_dashboard)."""
    _name = 'adt.comercial.financiera.dashboard'
    _description = 'Dashboard Gerencial de financieras'

    @staticmethod
    def _mes(fecha):
        return fecha.strftime('%Y-%m') if fecha else SIN_FECHA

    @api.model
    def get_dashboard_data(self):
        hoy = fields.Date.context_today(self)
        cuentas = self.env['adt.comercial.cuentas'].search_read([('fin_monto_total', '>', 0)], CAMPOS)

        filas = []
        pagos = {}
        for c in cuentas:
            financiera_id = c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0
            for fecha, monto in pagos_pendientes_financiera(hoy, c):
                clave = (c['id'], self._mes(fecha))
                acumulado = pagos.setdefault(clave, {'monto': 0.0, 'proxima': None})
                acumulado['monto'] += monto
                if fecha and (not acumulado['proxima'] or fecha < acumulado['proxima']):
                    acumulado['proxima'] = fecha
            filas.append({
                'id': c['id'],
                'referencia': c['reference_no'] or '',
                'cliente_id': c['partner_id'][0] if c['partner_id'] else 0,
                'cliente': c['partner_id'][1] if c['partner_id'] else _('Sin cliente'),
                'documento': c['partner_document'] or '',
                'moto': ' · '.join(filter(None, [c['moto_modelo'], c['moto_placa']])),
                'financiera_id': financiera_id,
                'estado': c['fin_estado'],
                'semaforo': c['fin_semaforo'],
                'total_financiera': c['fin_monto_total'],
                'pagado': c['fin_pagado'],
                'pendiente': c['fin_pendiente'],
                'total_cliente': c['fin_total_cliente'],
                'cobrado': c['fin_cobrado_cliente'],
                'ganancia_actual': c['fin_ganancia_actual'],
                'ganancia_esperada': c['fin_ganancia_esperada'],
                'caja_neta': c['fin_caja_neta'],
            })

        # Lo que los clientes aún deben pagar a ADT, por cuenta y mes de vencimiento.
        cobros = {}
        cuotas = self.env['adt.comercial.cuotas'].search_read([
            ('cuenta_id', 'in', [f['id'] for f in filas]),
            ('type', '=', 'cuota'),
            ('state', 'in', ESTADOS_CUOTA_PENDIENTE),
            ('saldo', '>', 0),
        ], ['cuenta_id', 'fecha_cronograma', 'saldo'])
        for q in cuotas:
            vencida = not q['fecha_cronograma'] or q['fecha_cronograma'] < hoy
            clave = (q['cuenta_id'][0], 'atrasado' if vencida else self._mes(q['fecha_cronograma']))
            cobros[clave] = cobros.get(clave, 0.0) + q['saldo']

        financieras = self.env['adt.comercial.financiera'].with_context(active_test=False).search_read(
            [('id', 'in', list({f['financiera_id'] for f in filas if f['financiera_id']}))], ['name'])
        if any(not f['financiera_id'] for f in filas):
            financieras.append({'id': 0, 'name': _('Sin financiera')})

        moneda = self.env.company.currency_id
        return {
            'hoy': fields.Date.to_string(hoy),
            'moneda': {'simbolo': moneda.symbol, 'posicion': moneda.position},
            'financieras': sorted(financieras, key=lambda f: f['name']),
            'cuentas': filas,
            'pagos_financiera': [
                {'cuenta_id': k[0], 'mes': k[1], 'monto': v['monto'],
                 'proxima': fields.Date.to_string(v['proxima']) if v['proxima'] else None}
                for k, v in pagos.items()],
            'cobros_clientes': [
                {'cuenta_id': k[0], 'mes': k[1], 'monto': v} for k, v in cobros.items()],
            'vistas': {
                'lista': self.env.ref('adt_comercial.adt_comercial_cuentas_reporte_financiera_tree').id,
                'formulario': self.env.ref('adt_comercial.adt_comercial_cuentas_form').id,
                'busqueda': self.env.ref('adt_comercial.adt_comercial_cuentas_reporte_financiera_search').id,
            },
        }
