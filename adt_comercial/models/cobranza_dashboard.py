from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

ESTADOS_CUOTA_PENDIENTE = ['pendiente', 'a_cuenta', 'retrasado']
ESTADOS_CAPTURA_ACTIVA = ['capturado', 'disolucion_contrato']
MESES_HISTORIA = 12

MOTIVOS = {
    'mora': 'Cuotas vencidas',
    'papeleta': 'Papeleta vencida',
    'ambos': 'Cuotas y papeleta',
    'otro': 'Sin motivo registrado',
}
GRUPOS_ACCESO = (
    'adt_comercial.group_access_adt_comercial',
    'adt_comercial.group_access_adt_cobranzas',
    'adt_comercial.group_access_adt_comercial_gerencia',
    'base.group_system',
)


class AdtCobranzaDashboard(models.AbstractModel):
    """Datos del Reporte de Cobranzas (dashboard JS: adt_cobranza_dashboard).

    Estado de cada cuenta en curso (prioridad de mayor a menor):
      capturada  -> tiene una captura activa (capturado / disolución de contrato)
      orden      -> tiene orden de captura (prioridad normal o urgente)
      deuda      -> tiene cuotas vencidas sin pagar
      al_dia     -> no debe nada vencido
    """
    _name = 'adt.comercial.cobranza.dashboard'
    _description = 'Reporte de cobranzas'

    def _check_acceso(self):
        if not any(self.env.user.has_group(g) for g in GRUPOS_ACCESO):
            raise AccessError(_("No tienes acceso al reporte de cobranzas."))

    @staticmethod
    def _seleccion(model, campo):
        return dict(model._fields[campo]._description_selection(model.env)) if campo in model._fields else {}

    # ------------------------------------------------------------------ cartera
    def _cartera(self, hoy):
        Cuenta = self.env['adt.comercial.cuentas']
        cuentas = Cuenta.search_read([('state', '=', 'en_curso')], [
            'reference_no', 'partner_id', 'partner_document', 'mobile', 'moto_modelo', 'moto_placa',
            'user_id', 'periodicidad', 'captura_prioridad', 'tipo_financiera_id'])
        ids = [c['id'] for c in cuentas]

        deuda = defaultdict(lambda: {'pendiente': 0.0, 'vencido': 0.0, 'vencidas': 0, 'desde': None})
        for q in self.env['adt.comercial.cuotas'].search_read([
                ('cuenta_id', 'in', ids), ('type', '=', 'cuota'),
                ('state', 'in', ESTADOS_CUOTA_PENDIENTE), ('saldo', '>', 0)],
                ['cuenta_id', 'fecha_cronograma', 'saldo']):
            d = deuda[q['cuenta_id'][0]]
            d['pendiente'] += q['saldo']
            if q['fecha_cronograma'] and q['fecha_cronograma'] < hoy:
                d['vencido'] += q['saldo']
                d['vencidas'] += 1
                if not d['desde'] or q['fecha_cronograma'] < d['desde']:
                    d['desde'] = q['fecha_cronograma']

        # Motivo (cuotas / papeleta / ambos) según la vista de mora del módulo de capturas.
        motivos = {}
        if 'adt.captura.mora' in self.env:
            for m in self.env['adt.captura.mora'].search_read([('cuenta_id', 'in', ids)], ['cuenta_id', 'source_type']):
                if m['cuenta_id'] and m['source_type'] in MOTIVOS:
                    motivos[m['cuenta_id'][0]] = m['source_type']

        capturas = {}
        if 'adt.captura.record' in self.env:
            Captura = self.env['adt.captura.record']
            tipos = self._seleccion(Captura, 'capture_type')
            estados = self._seleccion(Captura, 'state')
            razones = self._seleccion(Captura, 'retention_reason')
            for r in Captura.search_read(
                    [('cuenta_id', 'in', ids), ('state', 'in', ESTADOS_CAPTURA_ACTIVA)],
                    ['cuenta_id', 'name', 'state', 'capture_type', 'source_type', 'retention_reason', 'create_date'],
                    order='create_date desc'):
                cid = r['cuenta_id'][0]
                if cid not in capturas:
                    capturas[cid] = {
                        'numero': r['name'],
                        'estado': estados.get(r['state'], ''),
                        'tipo': tipos.get(r['capture_type'], ''),
                        'source': r['source_type'],
                        'razon': razones.get(r['retention_reason'], ''),
                        'fecha': fields.Date.to_string(r['create_date'].date()) if r['create_date'] else None,
                    }

        carteras = self._seleccion(Cuenta, 'periodicidad')
        filas = []
        for c in cuentas:
            d = deuda[c['id']]
            captura = capturas.get(c['id'])
            if captura:
                estado = 'capturada'
            elif c['captura_prioridad'] in ('normal', 'urgente'):
                estado = 'orden'
            elif d['vencido'] > 0.005:
                estado = 'deuda'
            else:
                estado = 'al_dia'
            motivo = None
            if estado in ('capturada', 'orden'):
                fuente = (captura and captura['source'] if captura and captura['source'] in MOTIVOS else None) \
                    or motivos.get(c['id']) or ('mora' if d['vencido'] > 0.005 else 'otro')
                motivo = fuente if fuente in MOTIVOS else 'otro'
            filas.append({
                'id': c['id'],
                'referencia': c['reference_no'] or '',
                'cliente': c['partner_id'][1] if c['partner_id'] else '',
                'documento': c['partner_document'] or '',
                'telefono': c['mobile'] or '',
                'moto': ' · '.join(filter(None, [c['moto_modelo'], c['moto_placa']])),
                'asesor': c['user_id'][1] if c['user_id'] else '',
                'cartera': c['periodicidad'] or '',
                'financiera_id': c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0,
                'cartera_label': carteras.get(c['periodicidad'], 'Sin cartera'),
                'estado': estado,
                'prioridad': c['captura_prioridad'] or '',
                'motivo': motivo,
                'captura': captura and {k: v for k, v in captura.items() if k != 'source'},
                'saldo_pendiente': d['pendiente'],
                'vencido': d['vencido'],
                'cuotas_vencidas': d['vencidas'],
                'dias': (hoy - d['desde']).days if d['desde'] else 0,
            })
        return filas, carteras

    # ------------------------------------------------------------------ recaudo
    def _recaudo(self, desde, hasta):
        """Pagos publicados de cuotas y cuotas programadas, agregados por día y cartera."""
        Cuota = self.env['adt.comercial.cuotas']
        pagos = self.env['account.payment'].search_read([
            ('cuota_id', '!=', False), ('state', '=', 'posted'),
            ('date', '>=', desde), ('date', '<=', hasta),
        ], ['date', 'amount', 'mora', 'mora_state', 'journal_id', 'create_uid', 'cuota_id'])

        programadas = Cuota.search_read([
            ('type', '=', 'cuota'), ('state', '!=', 'anulada'),
            ('fecha_cronograma', '>=', desde), ('fecha_cronograma', '<=', hasta),
            ('cuenta_id.state', 'in', ['en_curso', 'pagado'])],
            ['fecha_cronograma', 'monto', 'cuenta_id'])

        cuota_cuenta = {q['id']: q['cuenta_id'][0] for q in Cuota.search_read(
            [('id', 'in', list({p['cuota_id'][0] for p in pagos}))], ['cuenta_id']) if q['cuenta_id']}
        ids_cuentas = set(cuota_cuenta.values()) | {q['cuenta_id'][0] for q in programadas if q['cuenta_id']}
        # Cartera y financiera de cada cuenta, para poder filtrar el recaudo por ambas.
        cuenta_info = {c['id']: (c['periodicidad'] or '', c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0)
                       for c in self.env['adt.comercial.cuentas'].search_read(
                           [('id', 'in', list(ids_cuentas))], ['periodicidad', 'tipo_financiera_id'])}

        agregados = defaultdict(lambda: {'cuota': 0.0, 'mora': 0.0, 'pagos': 0})
        for p in pagos:
            cartera, financiera = cuenta_info.get(cuota_cuenta.get(p['cuota_id'][0]), ('', 0))
            clave = (fields.Date.to_string(p['date']), cartera, financiera,
                     p['journal_id'][1] if p['journal_id'] else 'Sin forma de pago',
                     p['create_uid'][1] if p['create_uid'] else 'Sin asignar')
            a = agregados[clave]
            a['cuota'] += p['amount']
            a['mora'] += p['mora'] if p['mora_state'] == 'paid' else 0.0
            a['pagos'] += 1

        programado = defaultdict(float)
        for q in programadas:
            cartera, financiera = cuenta_info.get(q['cuenta_id'][0], ('', 0)) if q['cuenta_id'] else ('', 0)
            programado[(fields.Date.to_string(q['fecha_cronograma']), cartera, financiera)] += q['monto']

        return agregados, programado

    @api.model
    def get_dashboard_data(self):
        self._check_acceso()
        self = self.sudo()
        hoy = fields.Date.context_today(self)
        desde = (hoy - relativedelta(months=MESES_HISTORIA - 1)).replace(day=1)
        fin_mes = hoy + relativedelta(day=31)

        cuentas, carteras = self._cartera(hoy)
        agregados, programado = self._recaudo(desde, fin_mes)

        ids_financieras = {c['financiera_id'] for c in cuentas} | {p[2] for p in agregados}
        financieras = [{'id': f['id'], 'nombre': f['name']} for f in self.env['adt.comercial.financiera'].with_context(
            active_test=False).search_read([('id', 'in', [i for i in ids_financieras if i])], ['name'], order='name')]
        if 0 in ids_financieras:
            financieras.append({'id': 0, 'nombre': _('Sin financiera')})

        moneda = self.env.company.currency_id
        return {
            'financieras': financieras,
            'hoy': fields.Date.to_string(hoy),
            'desde': fields.Date.to_string(desde),
            'moneda': {'simbolo': moneda.symbol, 'posicion': moneda.position},
            'carteras': [{'codigo': k, 'nombre': v} for k, v in carteras.items()],
            'motivos': MOTIVOS,
            'cuentas': cuentas,
            'pagos': [
                {'fecha': k[0], 'cartera': k[1], 'financiera_id': k[2], 'forma': k[3], 'cobrador': k[4],
                 'cuota': v['cuota'], 'mora': v['mora'], 'pagos': v['pagos']}
                for k, v in agregados.items()],
            'programado': [
                {'fecha': k[0], 'cartera': k[1], 'financiera_id': k[2], 'monto': v} for k, v in programado.items()],
            'vista_formulario': self.env.ref('adt_comercial.adt_comercial_cuentas_form').id,
        }
