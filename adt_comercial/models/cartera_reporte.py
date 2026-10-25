from collections import defaultdict

from odoo import _, api, fields, models

from .cartera_calculo import (
    TRAMOS_ATRASO, cents, mes, posicion, resumen_cliente, resumen_financiera_manual,
    resumen_financiera_pdf,
)

# La cartera activa son los créditos en curso (filtro por defecto del reporte). Los demás estados
# también se envían para poder filtrarlos por estado del cronograma; sus totales van aparte.
ESTADO_ACTIVO = 'en_curso'

CAMPOS_CUENTA = [
    'reference_no', 'state', 'partner_id', 'partner_document', 'moto_placa', 'tipo_financiera_id',
    'periodicidad', 'fecha_desembolso',
    # Financiera manual (pestaña antigua) / sincronizada desde el PDF
    'fin_fecha_inicio', 'fin_es_mensual', 'fin_fecha_fin', 'fin_monto_cuota', 'fin_monto_total',
    'fin_cancelada_manual',
    # Cronograma de la financiera leído del PDF (es del vehículo; lo lleva una sola de sus cuentas)
    'cf_estado', 'cf_dni', 'cf_tasa_interes_anual', 'cf_fecha_desembolso', 'cf_monto_cuota',
    'vehiculo_id', 'fin_desde_vehiculo', 'recuperado',
]


class AdtCarteraReporte(models.TransientModel):
    """Datos del reporte "Cartera y financieras" (reporte JS: adt_cartera_reporte).

    Los montos viajan al navegador en céntimos enteros; el JS solo suma enteros y da formato.
    """
    _name = 'adt.comercial.cartera.reporte'
    _description = 'Reporte de cartera por cobrar y deuda con financieras'

    @api.model
    def get_report_data(self):
        hoy = fields.Date.context_today(self)
        Cuenta = self.env['adt.comercial.cuentas']
        cuentas = Cuenta.search_read([], CAMPOS_CUENTA, order='id')
        ids = [c['id'] for c in cuentas]

        cuotas_por_cuenta = defaultdict(list)
        cuenta_de_cuota = {}
        for q in self.env['adt.comercial.cuotas'].search_read(
                [('cuenta_id', 'in', ids), ('type', '=', 'cuota')],
                ['cuenta_id', 'monto', 'saldo', 'fecha_cronograma', 'state']):
            cuenta_de_cuota[q['id']] = q['cuenta_id'][0]
            cuotas_por_cuenta[q['cuenta_id'][0]].append({
                'monto': q['monto'], 'saldo': q['saldo'], 'fecha': q['fecha_cronograma'],
                'state': q['state']})

        # Cobros reales: pagos publicados de cuotas, por mes de la fecha de pago
        # (mismo criterio que el Reporte de Cobranzas: la mora se cobra aparte en el campo 'mora').
        cobros_por_cuenta = defaultdict(lambda: defaultdict(lambda: {'cobrado': 0, 'mora': 0}))
        for pago in self.env['account.payment'].search_read(
                [('cuota_id', 'in', list(cuenta_de_cuota)), ('state', '=', 'posted')],
                ['cuota_id', 'date', 'amount', 'mora', 'mora_state']):
            m = cobros_por_cuenta[cuenta_de_cuota[pago['cuota_id'][0]]][mes(pago['date'])]
            m['cobrado'] += cents(pago['amount'])
            if pago['mora_state'] == 'paid':
                m['mora'] += cents(pago['mora'])

        # El plan de la financiera es del vehículo: se asigna solo a la cuenta que lo lleva
        # (fin_desde_vehiculo), para no contar dos veces la misma deuda.
        cuenta_del_vehiculo = {c['vehiculo_id'][0]: c['id'] for c in cuentas
                               if c['vehiculo_id'] and c['fin_desde_vehiculo']}
        cronograma_por_cuenta = defaultdict(list)
        for f in self.env['adt.comercial.cuentas.cronograma.fin'].search_read(
                [('vehicle_id', 'in', list(cuenta_del_vehiculo))],
                ['vehicle_id', 'nro_cuota', 'fecha_vencimiento', 'capital', 'interes', 'total'],
                order='vehicle_id, nro_cuota'):
            cronograma_por_cuenta[cuenta_del_vehiculo[f['vehicle_id'][0]]].append({
                'nro': f['nro_cuota'], 'fecha': f['fecha_vencimiento'], 'capital': f['capital'],
                'interes': f['interes'], 'total': f['total']})

        # Motos que ya volvieron a colocarse: su financiera la paga el nuevo cliente.
        vehiculos_vigentes = {c['vehiculo_id'][0] for c in cuentas
                              if c['vehiculo_id'] and c['state'] in ('aprobado', ESTADO_ACTIVO)}
        filas = []
        excluidas = {}
        recuperadas = {}
        for c in cuentas:
            cuotas = cuotas_por_cuenta.get(c['id'], [])
            cronograma = cronograma_por_cuenta.get(c['id'], [])
            if cronograma:
                fin = resumen_financiera_pdf(
                    hoy, cronograma, c['cf_tasa_interes_anual'], c['cf_fecha_desembolso'],
                    c['cf_monto_cuota'])
            else:
                fin = resumen_financiera_manual(
                    hoy, c['fin_fecha_inicio'], c['fin_es_mensual'], c['fin_fecha_fin'],
                    c['fin_monto_cuota'], c['fin_monto_total'], c['fin_cancelada_manual'])
            if not cuotas and fin['fuente'] == 'sin_datos':
                continue
            if c['state'] != ESTADO_ACTIVO:
                # Moto recuperada sin nuevo crédito vigente: el cliente ya no paga, pero ADT sigue
                # pagando a la financiera. Una fila por moto (la última cuenta recuperada).
                # Se listan como recuperadas (punto 4), no como crédito, para no contar dos veces su deuda.
                vehiculo = c['vehiculo_id'] and c['vehiculo_id'][0]
                if c['state'] == 'cancelado' and c['recuperado']:
                    if fin['pendiente'] > 0 and vehiculo not in vehiculos_vigentes:
                        recuperadas[vehiculo or -c['id']] = self._fila_recuperada(c, fin)
                        continue
                elif fin['pendiente'] > 0:
                    e = excluidas.setdefault(c['state'], {'estado': c['state'], 'cantidad': 0, 'deuda': 0})
                    e['cantidad'] += 1
                    e['deuda'] += fin['pendiente']
            cli = resumen_cliente(hoy, cuotas)
            pos = posicion(cli, fin)
            filas.append(self._fila(hoy, c, cli, fin, pos, cobros_por_cuenta.get(c['id'], {})))

        recuperadas = list(recuperadas.values())
        con_financiera = filas + recuperadas
        financieras = self.env['adt.comercial.financiera'].with_context(active_test=False).search_read(
            [('id', 'in', list({f['financiera_id'] for f in con_financiera if f['financiera_id']}))], ['name'])
        if any(not f['financiera_id'] for f in con_financiera):
            financieras.append({'id': 0, 'name': _('Sin financiera')})

        moneda = self.env.company.currency_id
        return {
            'hoy': fields.Date.to_string(hoy),
            'moneda': {'simbolo': moneda.symbol, 'posicion': moneda.position},
            'financieras': sorted(financieras, key=lambda f: f['name']),
            'tramos': [clave for clave, _d, _h in TRAMOS_ATRASO],
            # Estados del cronograma de pagos (cuenta), en el orden del campo.
            'estados': [{'id': k, 'name': v} for k, v in Cuenta._fields['state']._description_selection(self.env)],
            'estado_activo': ESTADO_ACTIVO,
            'cuentas': filas,
            # Créditos no activos que todavía tienen cuotas pendientes con la financiera (céntimos).
            'excluidas_con_deuda': list(excluidas.values()),
            # Motos recuperadas cuyo préstamo con la financiera ADT sigue pagando (céntimos).
            'recuperadas': recuperadas,
        }

    def _fila_recuperada(self, c, fin):
        return {
            'id': c['id'],
            'referencia': c['reference_no'] or '',
            'cliente': c['partner_id'][1] if c['partner_id'] else _('Sin cliente'),
            'documento': c['partner_document'] or c['cf_dni'] or '',
            'placa': c['moto_placa'] or '',
            'financiera_id': c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0,
            'fin': self._fecha(fin['fecha_fin']),
            'proxima_fecha': self._fecha(fin['proxima_fecha']),
            'cuota': fin['cuota'] if fin['cuotas_pendientes'] else 0,
            'cuotas_pendientes': fin['cuotas_pendientes'],
            'pendiente': fin['pendiente'],
            'pagado': fin['pagado'],
            'para_liquidar': fin['para_liquidar'],
        }

    @staticmethod
    def _fecha(valor):
        return fields.Date.to_string(valor) if valor else None

    @staticmethod
    def _mensual(hoy, fin, cobros):
        """Meses ya cerrados (antes del mes actual), en céntimos: cobrado real, mora cobrada
        y cuotas pagadas a la financiera (por mes de vencimiento)."""
        actual = mes(hoy)
        meses = defaultdict(lambda: {'cobrado': 0, 'mora': 0, 'pago': 0})
        for m, v in cobros.items():
            if m < actual:
                meses[m]['cobrado'] += v['cobrado']
                meses[m]['mora'] += v['mora']
        for m, monto in fin['calendario'].items():
            if m < actual:
                meses[m]['pago'] += monto
        return dict(meses)

    def _fila(self, hoy, c, cli, fin, pos, cobros):
        alertas = list(pos['cuadre'])
        if sum(v['cobrado'] for v in cobros.values()) != cli['cobrado']:
            alertas.append(_('Lo cobrado según pagos publicados no coincide con el saldo de las cuotas'))
        if fin['fuente'] == 'sin_datos':
            alertas.append(_('Sin cronograma de la financiera'))
        elif fin['fuente'] == 'manual':
            alertas.append(_('Financiera cargada a mano: sin monto para liquidar'))
        if fin['fuente'] == 'pdf' and c['cf_estado'] == 'observado':
            alertas.append(_('PDF de la financiera observado'))
        if fin['pagado_estimado']:
            alertas.append(_('Cuotas a la financiera anteriores al PDF estimadas'))
        if cli['sin_fecha']:
            alertas.append(_('Cuotas del cliente sin fecha'))
        if not cli['total']:
            alertas.append(_('Sin cronograma del cliente'))
        return {
            'id': c['id'],
            'referencia': c['reference_no'] or '',
            'estado': c['state'],
            'cliente': c['partner_id'][1] if c['partner_id'] else _('Sin cliente'),
            'documento': c['partner_document'] or c['cf_dni'] or '',
            'placa': c['moto_placa'] or '',
            'financiera_id': c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0,
            'periodicidad': c['periodicidad'] or '',
            'inicio': self._fecha(c['fin_fecha_inicio'] or c['fecha_desembolso']),
            'fin': self._fecha(fin['fecha_fin']),
            'cliente_resumen': {k: v for k, v in cli.items() if k != 'por_mes'},
            'mensual': self._mensual(hoy, fin, cobros),
            'financiera': dict(
                {k: v for k, v in fin.items() if k not in ('por_mes', 'calendario', 'proxima_fecha', 'fecha_fin')},
                proxima_fecha=self._fecha(fin['proxima_fecha'])),
            'posicion': {k: v for k, v in pos.items() if k != 'cuadre'},
            'cuadre_ok': not pos['cuadre'],
            'alertas': alertas,
        }
