from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .cliente_seguimiento import CLASIFICACION_MANUAL, ESTADO_SEGUIMIENTO

TOLERANCIA_DIAS = 3          # una cuota pagada hasta 3 días después de su fecha cuenta como puntual
PUNTAJE_APTO = 75
PUNTAJE_MINIMO = 50
DIAS_PROXIMOS_A_TERMINAR = 90
ESTADOS_CAPTURA_GRAVE = ('disolucion_contrato',)

SEGMENTOS = {
    'apto': 'Listo para nuevo préstamo',
    'evaluar': 'Evaluar antes de prestar',
    'pagando_bien': 'Pagando, buen pagador',
    'pagando_alerta': 'Pagando, con alertas',
    'no_prestar': 'No prestar',
}
GRUPOS_ACCESO = (
    'adt_comercial.group_access_adt_comercial',
    'adt_comercial.group_access_adt_comercial_gerencia',
    'base.group_system',
)
CAMPOS_SEGUIMIENTO = ('clasificacion_manual', 'motivo_manual', 'estado', 'proximo_contacto', 'notas')


def calcular_puntaje(h):
    """Puntaje de comportamiento 0-100 con sus factores (cada factor: texto y puntos).

    h: historial agregado del cliente (ver _historial_clientes).
    Devuelve (puntaje, factores, motivos_bloqueo).
    """
    factores = []
    bloqueos = []

    def restar(puntos, texto):
        if puntos > 0:
            factores.append({'texto': texto, 'puntos': -round(puntos)})
        return puntos

    total = 100.0
    if h['cuotas_vencidas_hist']:
        puntualidad = h['cuotas_puntuales'] / h['cuotas_vencidas_hist']
        total -= restar((1 - puntualidad) * 40, 'Pagó a tiempo el %d%% de sus cuotas' % round(puntualidad * 100))
    atraso = h['atraso_promedio']
    total -= restar(min(atraso, 30) / 30 * 20, 'Atraso promedio de %.0f días por cuota' % atraso)
    if h['atraso_maximo'] > 60:
        total -= restar(15, 'Llegó a atrasarse %d días' % h['atraso_maximo'])
    elif h['atraso_maximo'] > 30:
        total -= restar(10, 'Llegó a atrasarse %d días' % h['atraso_maximo'])
    if h['capturas']:
        total -= restar(min(h['capturas'] * 15, 30), 'Tuvo %d captura(s) de moto' % h['capturas'])
    if h['capturas'] >= 2:
        bloqueos.append('Capturas repetidas (%d)' % h['capturas'])
    if h['disoluciones']:
        total -= restar(40, 'Disolución de contrato')
        bloqueos.append('Disolución de contrato')
    if h['recuperadas']:
        total -= restar(50, 'Se le recuperó la moto')
        bloqueos.append('Moto recuperada')
    if h['papeletas']:
        total -= restar(min(h['papeletas'] * 5, 15), '%d papeleta(s) durante sus créditos' % h['papeletas'])
    if h['papeletas_impagas']:
        total -= restar(10, 'Papeleta sin pagar')
    if h['deuda_dias'] > 30:
        total -= restar(20, 'Hoy debe cuotas con %d días de atraso' % h['deuda_dias'])
    puntaje = max(0, round(total))
    if puntaje < PUNTAJE_MINIMO and not bloqueos:
        bloqueos.append('Puntaje bajo (%d/100)' % puntaje)
    return puntaje, factores, bloqueos


class AdtClientesDashboard(models.AbstractModel):
    """Datos del Dashboard de Clientes (JS: adt_clientes_dashboard): recompra y riesgo."""
    _name = 'adt.comercial.clientes.dashboard'
    _description = 'Dashboard de clientes: recompra y riesgo'

    def _check_acceso(self):
        if not any(self.env.user.has_group(g) for g in GRUPOS_ACCESO):
            raise AccessError(_("No tienes acceso al dashboard de clientes."))

    # ------------------------------------------------------------------ historial por cuenta
    def _resumen_cuotas(self, cuenta_ids, hoy):
        """Puntualidad y atrasos por cuenta, calculados en SQL (puede haber decenas de miles de cuotas)."""
        if not cuenta_ids:
            return {}
        self.env['adt.comercial.cuotas'].flush(['cuenta_id', 'fecha_cronograma', 'state', 'type', 'monto', 'saldo'])
        self.env['account.payment'].flush(['cuota_id', 'move_id'])
        self.env['account.move'].flush(['date', 'state'])
        self.env.cr.execute("""
            WITH pago AS (
                SELECT ap.cuota_id, MAX(am.date) AS fecha
                  FROM account_payment ap
                  JOIN account_move am ON am.id = ap.move_id
                 WHERE am.state = 'posted' AND ap.cuota_id IS NOT NULL
                 GROUP BY ap.cuota_id
            ), cuota AS (
                SELECT q.cuenta_id, q.state, q.saldo, q.fecha_cronograma,
                       -- Días de atraso: pagada -> fecha del último pago; impaga -> hoy.
                       GREATEST(COALESCE(p.fecha,
                                         CASE WHEN q.state = 'pagado' THEN q.fecha_cronograma ELSE %(hoy)s::date END)
                                - q.fecha_cronograma, 0) AS atraso
                  FROM adt_comercial_cuotas q
                  LEFT JOIN pago p ON p.cuota_id = q.id
                 WHERE q.type = 'cuota' AND q.state != 'anulada' AND q.cuenta_id = ANY(%(ids)s)
            )
            SELECT cuenta_id,
                   COUNT(*) FILTER (WHERE fecha_cronograma <= %(hoy)s) AS vencidas_hist,
                   COUNT(*) FILTER (WHERE fecha_cronograma <= %(hoy)s AND atraso <= %(tol)s
                                      AND state = 'pagado') AS puntuales,
                   COALESCE(SUM(atraso) FILTER (WHERE fecha_cronograma <= %(hoy)s), 0) AS atraso_total,
                   COALESCE(MAX(atraso) FILTER (WHERE fecha_cronograma <= %(hoy)s), 0) AS atraso_max,
                   COUNT(*) FILTER (WHERE state IN ('pendiente', 'a_cuenta', 'retrasado')) AS restantes,
                   COALESCE(MAX(atraso) FILTER (WHERE state IN ('pendiente', 'a_cuenta', 'retrasado')
                                                   AND fecha_cronograma < %(hoy)s), 0) AS deuda_dias,
                   MAX(fecha_cronograma) AS ultima_fecha
              FROM cuota
             GROUP BY cuenta_id
        """, {'ids': list(cuenta_ids), 'hoy': hoy, 'tol': TOLERANCIA_DIAS})
        return {r['cuenta_id']: r for r in self.env.cr.dictfetchall()}

    def _capturas_por_cuenta(self, cuenta_ids):
        if 'adt.captura.record' not in self.env or not cuenta_ids:
            return {}
        out = defaultdict(lambda: {'capturas': 0, 'disoluciones': 0})
        for r in self.env['adt.captura.record'].with_context(active_test=False).search_read(
                [('cuenta_id', 'in', list(cuenta_ids))], ['cuenta_id', 'state']):
            d = out[r['cuenta_id'][0]]
            d['capturas'] += 1
            d['disoluciones'] += r['state'] in ESTADOS_CAPTURA_GRAVE
        return out

    def _papeletas_por_cuenta(self, cuentas, hoy):
        """Papeletas del vehículo mientras estuvo a nombre del cliente (desde el desembolso hasta su última cuota)."""
        if 'adt.papeleta' not in self.env:
            return {}
        vehiculos = {c['vehiculo_id'][0] for c in cuentas if c['vehiculo_id']}
        papeletas = defaultdict(list)
        for p in self.env['adt.papeleta'].search_read(
                [('vehicle_id', 'in', list(vehiculos))], ['vehicle_id', 'fecha_papeleta', 'state']):
            papeletas[p['vehicle_id'][0]].append(p)
        out = {}
        for c in cuentas:
            if not c['vehiculo_id']:
                continue
            desde = c['fecha_desembolso']
            hasta = c['_ultima_fecha'] or hoy
            ps = [p for p in papeletas[c['vehiculo_id'][0]]
                  if p['fecha_papeleta'] and (not desde or p['fecha_papeleta'] >= desde) and p['fecha_papeleta'] <= hasta]
            out[c['id']] = {'papeletas': len(ps), 'impagas': sum(1 for p in ps if p['state'] != 'pagado')}
        return out

    # ------------------------------------------------------------------ datos
    @api.model
    def get_dashboard_data(self):
        self._check_acceso()
        seguimiento_model = self.env['adt.cliente.seguimiento']
        self = self.sudo()
        hoy = fields.Date.context_today(self)

        # Cuentas que forman historial: en curso, pagadas y canceladas con moto recuperada.
        cuentas = self.env['adt.comercial.cuentas'].search_read(
            ['|', ('state', 'in', ['en_curso', 'pagado']), '&', ('state', '=', 'cancelado'), ('recuperado', '=', True)],
            ['reference_no', 'partner_id', 'partner_document', 'mobile', 'state', 'recuperado', 'tipo_financiera_id',
             'monto_total', 'fecha_desembolso', 'moto_modelo', 'moto_placa', 'vehiculo_id'],
            order='fecha_desembolso asc, id asc')
        cuentas = [c for c in cuentas if c['partner_id']]
        ids = [c['id'] for c in cuentas]
        cuotas = self._resumen_cuotas(ids, hoy)
        for c in cuentas:
            c['_ultima_fecha'] = cuotas.get(c['id'], {}).get('ultima_fecha')
        capturas = self._capturas_por_cuenta(ids)
        papeletas = self._papeletas_por_cuenta(cuentas, hoy)

        financieras = {f['id']: f['name'] for f in self.env['adt.comercial.financiera'].with_context(
            active_test=False).search_read([], ['name'])}
        estados_cuenta = dict(self.env['adt.comercial.cuentas']._fields['state']._description_selection(self.env))

        por_cliente = defaultdict(list)
        for c in cuentas:
            por_cliente[c['partner_id'][0]].append(c)

        seguimientos = {s['partner_id'][0]: s for s in seguimiento_model.sudo().search_read(
            [('partner_id', 'in', list(por_cliente))],
            ['partner_id', 'clasificacion_manual', 'motivo_manual', 'estado', 'proximo_contacto', 'notas', 'user_id',
             'write_date'])}

        clientes = []
        for partner_id, cs in por_cliente.items():
            h = defaultdict(int)
            creditos = []
            for c in cs:
                q = cuotas.get(c['id'], {})
                cap = capturas.get(c['id'], {})
                pap = papeletas.get(c['id'], {})
                h['cuotas_vencidas_hist'] += q.get('vencidas_hist', 0)
                h['cuotas_puntuales'] += q.get('puntuales', 0)
                h['atraso_total'] += q.get('atraso_total', 0)
                h['atraso_maximo'] = max(h['atraso_maximo'], q.get('atraso_max', 0))
                h['capturas'] += cap.get('capturas', 0)
                h['disoluciones'] += cap.get('disoluciones', 0)
                h['recuperadas'] += c['state'] == 'cancelado' and c['recuperado']
                h['papeletas'] += pap.get('papeletas', 0)
                h['papeletas_impagas'] += pap.get('impagas', 0)
                if c['state'] == 'en_curso':
                    h['deuda_dias'] = max(h['deuda_dias'], q.get('deuda_dias', 0))
                vencidas = q.get('vencidas_hist', 0)
                creditos.append({
                    'id': c['id'],
                    'referencia': c['reference_no'] or '',
                    'moto': ' · '.join(filter(None, [c['moto_modelo'], c['moto_placa']])),
                    'estado': c['state'],
                    'estado_texto': 'Moto recuperada' if c['state'] == 'cancelado' else estados_cuenta.get(c['state'], ''),
                    'financiera': financieras.get(c['tipo_financiera_id'] and c['tipo_financiera_id'][0], ''),
                    'monto': c['monto_total'],
                    'desembolso': fields.Date.to_string(c['fecha_desembolso']) if c['fecha_desembolso'] else None,
                    'fin': fields.Date.to_string(q['ultima_fecha']) if q.get('ultima_fecha') else None,
                    'restantes': q.get('restantes', 0),
                    'puntualidad': round(q.get('puntuales', 0) * 100.0 / vencidas) if vencidas else None,
                    'capturas': cap.get('capturas', 0),
                })
            h['atraso_promedio'] = h['atraso_total'] / h['cuotas_vencidas_hist'] if h['cuotas_vencidas_hist'] else 0.0
            puntaje, factores, bloqueos = calcular_puntaje(h)

            terminados = [c for c in creditos if c['estado'] == 'pagado']
            en_curso = [c for c in creditos if c['estado'] == 'en_curso']
            seg = seguimientos.get(partner_id)
            manual = seg and seg['clasificacion_manual']
            if manual == 'no_prestar':
                bloqueos.insert(0, 'Marcado como no prestar' + (': ' + seg['motivo_manual'] if seg['motivo_manual'] else ''))
            if bloqueos:
                segmento = 'no_prestar'
            elif en_curso:
                segmento = 'pagando_bien' if puntaje >= PUNTAJE_APTO else 'pagando_alerta'
            elif manual in ('apto', 'evaluar'):
                segmento = manual
            else:
                segmento = 'apto' if puntaje >= PUNTAJE_APTO else 'evaluar'

            ultimo = creditos[-1]
            fin_en_curso = max((c['fin'] for c in en_curso if c['fin']), default=None)
            clientes.append({
                'id': partner_id,
                'nombre': cs[0]['partner_id'][1],
                'documento': cs[-1]['partner_document'] or '',
                'telefono': cs[-1]['mobile'] or '',
                'financiera_id': cs[-1]['tipo_financiera_id'][0] if cs[-1]['tipo_financiera_id'] else 0,
                'financiera': ultimo['financiera'],
                'segmento': segmento,
                'puntaje': puntaje,
                'factores': factores,
                'bloqueos': bloqueos,
                'puntualidad': round(h['cuotas_puntuales'] * 100.0 / h['cuotas_vencidas_hist']) if h['cuotas_vencidas_hist'] else None,
                'atraso_promedio': round(h['atraso_promedio'], 1),
                'atraso_maximo': h['atraso_maximo'],
                'capturas': h['capturas'],
                'papeletas': h['papeletas'],
                'creditos': creditos,
                'n_creditos': len(creditos),
                'n_terminados': len(terminados),
                # Volvió a sacar: tiene un crédito desembolsado después de otro que ya terminó de pagar.
                'recompra': any(c['desembolso'] and t['desembolso'] and c['desembolso'] > t['desembolso']
                                for t in terminados for c in creditos),
                'ultimo_monto': ultimo['monto'],
                'termino': max((c['fin'] for c in terminados if c['fin']), default=None),
                'termina': fin_en_curso,
                'seguimiento': self._seguimiento_dict(seg),
            })

        moneda = self.env.company.currency_id
        return {
            'hoy': fields.Date.to_string(hoy),
            'moneda': {'simbolo': moneda.symbol, 'posicion': moneda.position},
            'segmentos': SEGMENTOS,
            'clasificaciones': dict(CLASIFICACION_MANUAL),
            'estados_seguimiento': dict(ESTADO_SEGUIMIENTO),
            'financieras': sorted(
                [{'id': i, 'nombre': financieras.get(i) or _('Sin financiera')} for i in {c['financiera_id'] for c in clientes}],
                key=lambda f: f['nombre']),
            'umbral_apto': PUNTAJE_APTO,
            'umbral_minimo': PUNTAJE_MINIMO,
            'dias_proximos': DIAS_PROXIMOS_A_TERMINAR,
            'clientes': clientes,
            'vista_cuenta': self.env.ref('adt_comercial.adt_comercial_cuentas_form').id,
        }

    @staticmethod
    def _seguimiento_dict(seg):
        if not seg:
            return None
        return {
            'id': seg['id'],
            'clasificacion_manual': seg['clasificacion_manual'] or '',
            'motivo_manual': seg['motivo_manual'] or '',
            'estado': seg['estado'],
            'proximo_contacto': fields.Date.to_string(seg['proximo_contacto']) if seg['proximo_contacto'] else None,
            'notas': seg['notas'] or '',
            'responsable': seg['user_id'][1] if seg['user_id'] else '',
            'actualizado': fields.Datetime.to_string(seg['write_date']) if seg['write_date'] else None,
        }

    @api.model
    def guardar_seguimiento(self, partner_id, valores):
        """Crea o actualiza el seguimiento del cliente. Usa los permisos del usuario (queda en el historial)."""
        self._check_acceso()
        if not isinstance(valores, dict):
            raise UserError(_("Datos de seguimiento inválidos."))
        vals = {k: valores[k] or False for k in CAMPOS_SEGUIMIENTO if k in valores}
        if vals.get('clasificacion_manual') == 'no_prestar' and not (vals.get('motivo_manual') or '').strip():
            raise UserError(_("Indica el motivo para marcar al cliente como 'No prestar'."))
        Seguimiento = self.env['adt.cliente.seguimiento']
        registro = Seguimiento.search([('partner_id', '=', int(partner_id))], limit=1)
        if registro:
            registro.write(vals)
        else:
            vals.setdefault('estado', 'por_contactar')
            registro = Seguimiento.create(dict(vals, partner_id=int(partner_id)))
        return self._seguimiento_dict(registro.read(
            ['partner_id', 'clasificacion_manual', 'motivo_manual', 'estado', 'proximo_contacto', 'notas', 'user_id',
             'write_date'])[0])
