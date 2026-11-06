# -*- coding: utf-8 -*-
"""Espejo de las órdenes de captura del SAT de Lima.

El agente (contenedor Docker capturas_sat) envía una consulta por placa a
/api/capturas/sat/import con el JSON que genera sat_capturas.py:

* ``tiene_capturas`` true  -> se registran/actualizan las órdenes (una por documento);
* ``tiene_capturas`` false -> las órdenes vigentes de la placa pasan a levantadas;
* ``tiene_capturas`` null  -> respuesta no reconocida (captcha, sesión): no cambia nada.

Solo una consulta con detalle completo permite decir que una orden dejó de figurar.
Cada orden nueva (o que vuelve a figurar) genera una alerta en el vehículo.
"""
import json
import logging
import re
import secrets

from odoo import _, api, fields, models
from odoo.addons.adt_papeletas.models.papeleta_sat import _fecha_hora, _fecha_lima, normalizar

_logger = logging.getLogger(__name__)

PARAM_TOKEN = 'adt_captura_sat.token'

CON_ORDEN = 'con_orden'
SIN_ORDEN = 'sin_orden'


def _resultado(tiene):
    if tiene is True:
        return CON_ORDEN
    if tiene is False:
        return SIN_ORDEN
    return 'indeterminado'


def mensaje_de(payload):
    """Mensaje del SAT para la placa; si el agente no lo envía, se toma de respuesta_sat."""
    if payload.get('mensaje') or payload.get('error'):
        return payload.get('mensaje') or payload.get('error')
    for linea in (payload.get('respuesta_sat') or '').splitlines():
        if re.match(r'El veh[ií]culo de placa\s', linea, re.I):
            return linea.strip()
    return ''


def _monto(valor):
    try:
        return float(valor or 0.0)
    except (TypeError, ValueError):
        return 0.0


class ADTCapturaSat(models.Model):
    _name = 'adt.captura.sat'
    _description = 'Orden de captura SAT Lima'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'vigente desc, primera_vez_visto desc, id desc'

    name = fields.Char(string='Documento', required=True, index=True, readonly=True,
                       help='Identificador del documento publicado por el SAT.')
    placa = fields.Char(string='Placa', required=True, index=True, readonly=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', index=True, tracking=True, ondelete='set null')
    driver_id = fields.Many2one(related='vehicle_id.driver_id', string='Conductor', store=False)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)

    # Datos del SAT
    anio = fields.Integer(string='Año', readonly=True)
    concepto = fields.Char(string='Concepto', readonly=True)
    placa_original = fields.Char(string='Placa original', readonly=True)
    referencia = fields.Char(string='Referencia', readonly=True)
    monto = fields.Monetary(string='Monto en captura', readonly=True, tracking=True)
    fecha_actualizacion_sat = fields.Date(string='Informe SAT al', readonly=True)

    # Seguimiento entre consultas
    vigente = fields.Boolean(string='Orden vigente', default=True, readonly=True, tracking=True, index=True,
                             help='Falso cuando la orden dejó de figurar en una consulta completa del SAT.')
    primera_vez_visto = fields.Datetime(string='Detectada', readonly=True)
    ultima_vez_visto = fields.Datetime(string='Última consulta', readonly=True)
    levantada_en = fields.Datetime(string='Dejó de figurar', readonly=True)
    consulta_id = fields.Many2one('adt.captura.sat.consulta', string='Última consulta SAT', readonly=True,
                                  ondelete='set null')
    dias = fields.Integer(string='Días vigente', compute='_compute_dias')

    # Gestión interna
    gestion = fields.Selection([
        ('nueva', 'Nueva'),
        ('en_gestion', 'En gestión'),
        ('resuelta', 'Resuelta'),
    ], string='Gestión', default='nueva', required=True, tracking=True, index=True)
    responsable_id = fields.Many2one('res.users', string='Responsable', tracking=True)
    notas = fields.Text(string='Notas')

    _sql_constraints = [
        ('documento_placa_uniq', 'unique(placa, name)', 'La orden de captura ya existe para esta placa.'),
    ]

    @api.depends('primera_vez_visto', 'levantada_en', 'vigente')
    def _compute_dias(self):
        hoy = fields.Date.context_today(self)
        for rec in self:
            if not rec.primera_vez_visto:
                rec.dias = 0
                continue
            hasta = _fecha_lima(rec.levantada_en) if not rec.vigente and rec.levantada_en else hoy
            rec.dias = (hasta - _fecha_lima(rec.primera_vez_visto)).days

    def name_get(self):
        return [(rec.id, '%s · %s' % (rec.placa, rec.name)) for rec in self]

    # ------------------------------------------------------------------ setup
    @api.model
    def _init_parametros(self):
        """Llamado desde data/: genera el token de la API una sola vez."""
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param(PARAM_TOKEN):
            icp.set_param(PARAM_TOKEN, secrets.token_urlsafe(32))

    @api.model
    def _buscar_vehiculo(self, placa):
        return self.env['adt.papeleta.sat']._buscar_vehiculo(placa)

    # --------------------------------------------------------- sincronización
    @api.model
    def _procesar_consulta(self, payload, consulta):
        """Aplica una consulta del agente (una placa). Devuelve contadores."""
        placa = normalizar(payload.get('placa'))
        tiene = payload.get('tiene_capturas')
        cuando = _fecha_hora(payload.get('fecha_consulta_utc') or payload.get('consultado_en'))
        res = {'nuevas': 0, 'actualizadas': 0, 'levantadas': 0}

        vehiculo = self._buscar_vehiculo(placa)
        meta_vehicle = (payload.get('metadata') or {}).get('vehicle_id')
        if not vehiculo and str(meta_vehicle or '').isdigit():
            vehiculo = self.env['fleet.vehicle'].browse(int(meta_vehicle)).exists()
        consulta.vehicle_id = vehiculo

        if tiene not in (True, False) or not placa:
            consulta.state = 'omitido'
            return res

        fecha_sat = False
        try:
            fecha_sat = fields.Date.to_date(payload.get('fecha_actualizacion_sat') or False)
        except ValueError:
            pass

        vistos, alertar = set(), self.browse()
        if tiene:
            for datos in payload.get('capturas') or []:
                documento = str(datos.get('documento') or '').strip()
                if not documento:
                    continue
                vistos.add(documento)
                rec, estado = self._upsert(documento, placa, vehiculo, datos, cuando, fecha_sat, consulta)
                if estado == 'nueva':
                    res['nuevas'] += 1
                    alertar |= rec
                elif estado == 'reaparece':
                    res['nuevas'] += 1
                    alertar |= rec
                elif estado == 'actualizada':
                    res['actualizadas'] += 1

        completa = tiene is False or bool(payload.get('detalle_completo'))
        if completa:
            previas = self.search([
                ('placa', '=', placa), ('vigente', '=', True), ('name', 'not in', list(vistos)),
                '|', ('ultima_vez_visto', '=', False), ('ultima_vez_visto', '<', cuando),
            ])
            for rec in previas:
                rec._levantar(cuando)
                res['levantadas'] += 1

        estado_previo = vehiculo.captura_sat_estado if vehiculo else False
        aplicado = bool(vehiculo) and vehiculo._captura_sat_registrar(tiene, cuando, consulta)
        if alertar or (tiene and aplicado and estado_previo != CON_ORDEN):
            self._alertar(placa, vehiculo, alertar, consulta, payload)
        return res

    @api.model
    def _upsert(self, documento, placa, vehiculo, datos, cuando, fecha_sat, consulta):
        """Devuelve (registro, 'nueva' | 'reaparece' | 'actualizada' | 'antigua')."""
        rec = self.search([('placa', '=', placa), ('name', '=', documento)], limit=1)
        anio = datos.get('anio')
        valores = {
            'anio': int(anio) if str(anio or '').isdigit() else False,
            'concepto': datos.get('concepto') or False,
            'placa_original': datos.get('placa_original') or False,
            'referencia': datos.get('referencia') or False,
            'monto': _monto(datos.get('monto_en_captura')),
            'fecha_actualizacion_sat': fecha_sat,
            'consulta_id': consulta.id,
        }
        if rec and ((rec.ultima_vez_visto and rec.ultima_vez_visto > cuando)
                    or (rec.levantada_en and rec.levantada_en >= cuando)):
            return rec, 'antigua'  # reenvío antiguo: no pisa datos más recientes
        valores.update({'vigente': True, 'ultima_vez_visto': cuando, 'levantada_en': False})
        if vehiculo and (not rec or not rec.vehicle_id):
            valores['vehicle_id'] = vehiculo.id
        if not rec:
            valores.update({'name': documento, 'placa': placa, 'primera_vez_visto': cuando})
            return self.create(valores), 'nueva'
        reaparece = not rec.vigente
        if reaparece:
            valores.update({'gestion': 'nueva', 'primera_vez_visto': cuando})
        rec.write(valores)
        if reaparece:
            rec.message_post(body=_('La orden de captura volvió a figurar en el SAT.'))
            return rec, 'reaparece'
        return rec, 'actualizada'

    def _levantar(self, cuando):
        self.ensure_one()
        self.write({'vigente': False, 'levantada_en': cuando, 'gestion': 'resuelta'})
        self.message_post(body=_('Ya no figura en el SAT Lima (consulta del %s): orden levantada.')
                          % _fecha_lima(cuando).strftime('%d/%m/%Y'))

    # ---------------------------------------------------------------- alertas
    @api.model
    def _usuarios_alerta(self, consulta):
        grupo = self.env.ref('adt_captura_sat.group_captura_sat_alertas', raise_if_not_found=False)
        usuarios = grupo.users if grupo else self.env['res.users']
        ejecucion = consulta.ejecucion_id
        if ejecucion:
            usuarios |= ejecucion.programa_id.responsable_ids | ejecucion.usuario_id
        root = self.env.ref('base.user_root')
        return usuarios.filtered(lambda u: u.active and not u.share and u != root)

    @api.model
    def _alertar(self, placa, vehiculo, ordenes, consulta, payload):
        """Mensaje + actividad en el vehículo (o en la orden, si no hay vehículo)."""
        monto = payload.get('monto_total_en_captura')
        if monto is None:
            monto = sum(self.search([('placa', '=', placa), ('vigente', '=', True)]).mapped('monto'))
        detalle = ''.join('<li>%s · %s · S/ %.2f</li>' % (o.name, o.concepto or '-', o.monto) for o in ordenes)
        texto = _('<p><b>Orden de captura SAT</b> para la placa <b>%s</b>. Monto total en captura: S/ %.2f.</p>') \
            % (placa, _monto(monto))
        if detalle:
            texto += '<ul>%s</ul>' % detalle
        else:
            texto += _('<p>El SAT indica orden de captura pero no se pudo interpretar el detalle; '
                       'revise la consulta %s.</p>') % consulta.name
        resumen = _('Orden de captura SAT: %s') % placa
        destino = vehiculo or ordenes[:1]
        if not destino:
            _logger.warning('Orden de captura SAT para %s sin vehículo ni detalle; ver consulta %s',
                            placa, consulta.id)
            return
        usuarios = self._usuarios_alerta(consulta)
        destino.message_post(body=texto, subject=resumen, partner_ids=usuarios.mapped('partner_id').ids,
                             subtype_xmlid='mail.mt_comment')
        for usuario in usuarios:
            try:
                destino.activity_schedule('mail.mail_activity_data_todo', user_id=usuario.id,
                                          summary=resumen, note=texto)
            except Exception:  # noqa: BLE001 - la alerta no debe impedir guardar la consulta
                _logger.exception('No se pudo programar la actividad de captura SAT para %s', placa)

    # ----------------------------------------------------------------- botones
    def action_en_gestion(self):
        self.write({'gestion': 'en_gestion', 'responsable_id': self.env.user.id})
        return True

    def action_resuelta(self):
        self.write({'gestion': 'resuelta'})
        return True

    def action_vincular_vehiculo(self):
        for rec in self.filtered(lambda r: not r.vehicle_id):
            rec.vehicle_id = self._buscar_vehiculo(rec.placa)
        return True


class ADTCapturaSatConsulta(models.Model):
    _name = 'adt.captura.sat.consulta'
    _description = 'Consulta de capturas SAT'
    _order = 'id desc'

    name = fields.Char(string='Referencia', required=True)
    placa = fields.Char(string='Placa', index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', index=True, ondelete='set null')
    consultado_en = fields.Datetime(string='Consultado en')
    resultado = fields.Selection([
        (CON_ORDEN, 'Con orden de captura'),
        (SIN_ORDEN, 'Sin orden de captura'),
        ('indeterminado', 'No determinado'),
    ], string='Resultado SAT', index=True)
    mensaje = fields.Char(string='Mensaje SAT')
    fecha_actualizacion_sat = fields.Char(string='Informe SAT al')
    cantidad = fields.Integer(string='Órdenes')
    monto_total = fields.Float(string='Monto total en captura')
    detalle_completo = fields.Boolean(string='Detalle completo')
    filas_no_interpretadas = fields.Text(string='Filas no interpretadas')
    respuesta_sat = fields.Text(string='Respuesta SAT')
    nuevas = fields.Integer(string='Nuevas')
    actualizadas = fields.Integer(string='Actualizadas')
    levantadas = fields.Integer(string='Levantadas')
    state = fields.Selection([
        ('ok', 'Procesada'),
        ('omitido', 'Omitida (consulta fallida)'),
        ('error', 'Error'),
    ], string='Estado', default='ok', index=True)
    error = fields.Text(string='Error')
    payload = fields.Text(string='Payload')
    ejecucion_id = fields.Many2one('adt.captura.sat.ejecucion', string='Ejecución', index=True,
                                   ondelete='set null', readonly=True)

    @api.model
    def registrar(self, payload):
        """Guarda la consulta y la aplica. Un error no deja cambios a medias."""
        placa = normalizar(payload.get('placa'))
        cuando = payload.get('fecha_consulta_utc') or payload.get('consultado_en')
        filas = payload.get('filas_no_interpretadas') or []
        consulta = self.create({
            'name': '%s · %s' % (placa or '?', (cuando or '')[:19]),
            'placa': placa,
            'consultado_en': _fecha_hora(cuando),
            'resultado': _resultado(payload.get('tiene_capturas')),
            'mensaje': mensaje_de(payload)[:250] or False,
            'fecha_actualizacion_sat': payload.get('fecha_actualizacion_sat') or False,
            'cantidad': payload.get('cantidad_capturas') or len(payload.get('capturas') or []),
            'monto_total': _monto(payload.get('monto_total_en_captura')),
            'detalle_completo': bool(payload.get('detalle_completo')),
            'filas_no_interpretadas': '\n'.join(str(f) for f in filas) or False,
            'respuesta_sat': payload.get('respuesta_sat') or False,
            'payload': json.dumps({k: v for k, v in payload.items() if k != 'respuesta_sat'},
                                  ensure_ascii=False, indent=1),
        })
        consulta._aplicar(payload)
        consulta._informar_ejecucion(payload)
        return consulta

    def _aplicar(self, payload):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                res = self.env['adt.captura.sat']._procesar_consulta(payload, self)
            self.write(dict(res, error=False, state=self.state if self.state == 'omitido' else 'ok'))
        except Exception as exc:  # noqa: BLE001 - se registra y se informa al agente
            _logger.exception('Error importando consulta de capturas SAT %s', self.name)
            self.write({'state': 'error', 'error': '%s: %s' % (type(exc).__name__, exc)})

    def _informar_ejecucion(self, payload):
        self.ensure_one()
        ejecucion_id = (payload.get('metadata') or {}).get('ejecucion_id')
        if not str(ejecucion_id or '').isdigit():
            return
        ejecucion = self.env['adt.captura.sat.ejecucion'].browse(int(ejecucion_id)).exists()
        if not ejecucion:
            return
        self.ejecucion_id = ejecucion
        try:
            with self.env.cr.savepoint():
                ejecucion._registrar_consulta(self, payload)
        except Exception:  # noqa: BLE001 - el informe nunca debe impedir guardar las órdenes
            _logger.exception('No se pudo actualizar la ejecución %s con %s', ejecucion_id, self.name)

    def action_reprocesar(self):
        for rec in self:
            payload = json.loads(rec.payload or '{}')
            payload['respuesta_sat'] = rec.respuesta_sat
            rec.state = 'ok'
            rec._aplicar(payload)
        return True
