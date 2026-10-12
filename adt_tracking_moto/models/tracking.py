# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from collections import defaultdict
from datetime import timedelta

from .tools import (
    ESTADOS_GLOBAL, ESTADOS_PLACA, FECHA_POR_ETAPA, MIN_MUESTRAS_HISTORIA, ORDEN_ETAPA, VENTANA_HISTORIA_DIAS,
    percentil, plate_is_ready,
)

GRUPO_MANAGER = 'adt_tracking_moto.group_tracking_manager'


class AdtMotoTracking(models.Model):
    """Seguimiento de una moto: flujo logístico y flujo de placa en paralelo."""
    _name = 'adt.moto.tracking'
    _description = 'Tracking de moto'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Referencia', readonly=True, copy=False, default='Nuevo')
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Moto', required=True, ondelete='restrict', index=True, tracking=True,
    )
    factura_id = fields.Many2one(related='vehicle_id.x_id_facturacion', string='Factura', store=True)
    modelo_id = fields.Many2one(related='vehicle_id.model_id', string='Modelo', store=True)
    chasis = fields.Char(related='vehicle_id.vin_sn', string='Chasis')
    motor = fields.Char(related='vehicle_id.x_motor_sn', string='Motor')
    color = fields.Char(related='vehicle_id.color', string='Color')
    license_plate = fields.Char(related='vehicle_id.license_plate', string='Placa')
    partner_id = fields.Many2one(related='vehicle_id.driver_id', string='Cliente', store=True)
    fecha_entrega = fields.Date(related='vehicle_id.fecha_entrega', string='Fecha de entrega', store=True)

    # ── Flujo 1: logística ──────────────────────────────────────────────────
    etapa_id = fields.Many2one(
        'adt.moto.tracking.etapa', string='Etapa', required=True, index=True, tracking=True,
        ondelete='restrict', default=lambda self: self._etapa('recojo'), group_expand='_read_group_etapa_ids',
    )
    etapa_codigo = fields.Selection(related='etapa_id.codigo', store=True)
    taller_fibra_id = fields.Many2one('adt.moto.tracking.taller', string='Taller de fibra', tracking=True)
    fecha_etapa = fields.Datetime(string='En la etapa desde', readonly=True)
    fecha_recojo = fields.Datetime(string='Recojo en distribuidor', readonly=True)
    fecha_ingreso_almacen = fields.Datetime(string='Ingreso a almacén', readonly=True)
    fecha_envio_fibra = fields.Datetime(string='Envío a fibra', readonly=True)
    fecha_listo = fields.Datetime(string='Listo para asignar', readonly=True)

    # ── Flujo 2: placa (sincronizado con adt.tramite.placa) ─────────────────
    estado_placa = fields.Selection(
        ESTADOS_PLACA, string='Estado de placa', default='pendiente', required=True, readonly=True, tracking=True,
    )
    tramite_placa_id = fields.Many2one('adt.tramite.placa', string='Trámite de placa', readonly=True)
    fecha_inicio_tramite = fields.Datetime(string='Inicio de trámite', readonly=True)
    fecha_placa_ok = fields.Datetime(string='Placa finalizada', readonly=True)
    cant_observaciones = fields.Integer(
        related='tramite_placa_id.cant_observaciones', string='Observaciones de placa')
    motivo_observacion = fields.Text(related='tramite_placa_id.motivo_observacion', string='Motivo de observación')

    # ── Hitos y estado global ───────────────────────────────────────────────
    fecha_asignacion = fields.Datetime(string='Asignada a cliente', readonly=True)
    asignado_antes_listo = fields.Boolean(string='Asignada antes de estar lista', readonly=True)
    estado_global = fields.Selection(
        ESTADOS_GLOBAL, string='Estado', compute='_compute_estado_global', store=True, tracking=True,
    )
    fecha_cierre = fields.Datetime(string='Cerrado el', compute='_compute_fecha_cierre', store=True)
    dias_totales = fields.Float(string='Días totales', compute='_compute_dias', digits=(16, 1))
    dias_etapa = fields.Float(string='Días en la etapa', compute='_compute_dias', digits=(16, 1))
    demorado = fields.Boolean(string='Demorado', compute='_compute_demorado', search='_search_demorado')
    log_ids = fields.One2many('adt.moto.tracking.log', 'tracking_id', string='Historial', readonly=True)

    _sql_constraints = [
        ('vehicle_unique', 'unique(vehicle_id)', 'La moto ya tiene un tracking.'),
    ]

    # ── Helpers ─────────────────────────────────────────────────────────────

    @api.model
    def _etapa(self, codigo):
        return self.env['adt.moto.tracking.etapa'].search([('codigo', '=', codigo)], limit=1)

    @api.model
    def _read_group_etapa_ids(self, etapas, domain, order):
        return etapas.search([], order=order)

    def _es_manager(self):
        return self.env.su or self.env.user.has_group(GRUPO_MANAGER)

    @staticmethod
    def _label_placa(estado):
        return dict(ESTADOS_PLACA).get(estado, '')

    def _sla_horas(self):
        self.ensure_one()
        if self.etapa_codigo == 'fibra' and self.taller_fibra_id.sla_horas:
            return self.taller_fibra_id.sla_horas
        return self.etapa_id.sla_horas

    # ── Computes ────────────────────────────────────────────────────────────

    @api.depends('partner_id', 'etapa_codigo', 'estado_placa', 'fecha_entrega')
    def _compute_estado_global(self):
        for rec in self:
            if not rec.partner_id:
                rec.estado_global = 'listo_asignar' if rec.etapa_codigo == 'listo' else 'en_proceso'
            elif rec.estado_placa != 'finalizado':
                rec.estado_global = 'asignado_sin_placa'
            elif rec.fecha_entrega:
                rec.estado_global = 'entregado'
            else:
                rec.estado_global = 'asignado_con_placa'

    @api.depends('estado_global')
    def _compute_fecha_cierre(self):
        for rec in self:
            if rec.estado_global != 'entregado':
                rec.fecha_cierre = False
            elif not rec.fecha_cierre:
                rec.fecha_cierre = fields.Datetime.now()

    @api.depends('fecha_recojo', 'fecha_etapa', 'fecha_cierre')
    def _compute_dias(self):
        ahora = fields.Datetime.now()
        for rec in self:
            fin = rec.fecha_cierre or ahora
            inicio = rec.fecha_recojo or rec.create_date
            rec.dias_totales = (fin - inicio).total_seconds() / 86400 if inicio else 0
            rec.dias_etapa = (fin - rec.fecha_etapa).total_seconds() / 86400 if rec.fecha_etapa else 0

    @api.depends('fecha_etapa', 'etapa_id.sla_horas', 'taller_fibra_id.sla_horas', 'estado_global', 'partner_id')
    @api.model
    def _p85_historico_horas(self):
        """P85 (horas) por etapa logística con los casos cerrados recientes; mismo criterio que el dashboard."""
        desde = fields.Datetime.now() - timedelta(days=VENTANA_HISTORIA_DIAS)
        duraciones = defaultdict(list)
        for log in self.env['adt.moto.tracking.log'].sudo().search(
                [('flujo', '=', 'logistica'), ('fecha_fin', '>=', desde)]):
            duraciones[log.codigo_hasta].append((log.fecha_fin - log.fecha_inicio).total_seconds() / 3600)
        # "listo" no se cierra al asignar: su historia es lo que tardó en asignarse.
        for t in self.sudo().search([('fecha_listo', '!=', False), ('fecha_asignacion', '>=', desde),
                                     ('asignado_antes_listo', '=', False)]):
            if t.fecha_asignacion >= t.fecha_listo:
                duraciones['listo'].append((t.fecha_asignacion - t.fecha_listo).total_seconds() / 3600)
        return {codigo: percentil(valores, 85) for codigo, valores in duraciones.items()
                if len(valores) >= MIN_MUESTRAS_HISTORIA}

    def _compute_demorado(self):
        ahora = fields.Datetime.now()
        historico = None
        for rec in self:
            sla = rec._sla_horas()
            if not sla:
                if historico is None:
                    historico = self._p85_historico_horas()
                sla = historico.get(rec.etapa_codigo)
            # Una vez asignada, la etapa "listo" ya no corre contra el SLA.
            logistica_terminada = rec.etapa_codigo == 'listo' and rec.partner_id
            rec.demorado = bool(
                sla and rec.fecha_etapa and not logistica_terminada and rec.estado_global != 'entregado'
                and (ahora - rec.fecha_etapa).total_seconds() / 3600 > sla
            )

    def _search_demorado(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_('Operador no soportado.'))
        ids = self.search([('estado_global', '!=', 'entregado')]).filtered('demorado').ids
        positivo = (operator == '=') == bool(value)
        return [('id', 'in' if positivo else 'not in', ids)]

    # ── ORM ─────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        ahora = fields.Datetime.now()
        Etapa = self.env['adt.moto.tracking.etapa']
        Taller = self.env['adt.moto.tracking.taller']
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('adt.moto.tracking') or 'Nuevo'
            etapa = Etapa.browse(vals['etapa_id']) if vals.get('etapa_id') else self._etapa('recojo')
            if etapa.codigo == 'fibra' and not Taller.browse(vals.get('taller_fibra_id')).exists():
                raise UserError(_('Para iniciar el tracking en la etapa de fibra hay que indicar el taller.'))
            vals['etapa_id'] = etapa.id
            vals['fecha_etapa'] = ahora
            vals[FECHA_POR_ETAPA[etapa.codigo]] = ahora
        records = super().create(vals_list)
        for rec in records:
            rec._registrar_log('logistica', False, rec.etapa_id)
            rec._registrar_log('placa', False, rec._label_placa(rec.estado_placa), codigo=rec.estado_placa)
        records._sync_estado_placa()
        return records

    def write(self, vals):
        if 'etapa_id' not in vals:
            return super().write(vals)

        nueva = self.env['adt.moto.tracking.etapa'].browse(vals['etapa_id'])
        cambian = self.filtered(lambda r: r.etapa_id != nueva)
        sin_cambio = self - cambian
        res = True
        if sin_cambio:
            res = super(AdtMotoTracking, sin_cambio).write(vals)
        if not cambian:
            return res

        if 'taller_fibra_id' in vals:
            taller = self.env['adt.moto.tracking.taller'].browse(vals['taller_fibra_id'])
        anteriores = {}
        for rec in cambian:
            rec._validar_cambio_etapa(nueva, taller if 'taller_fibra_id' in vals else rec.taller_fibra_id)
            anteriores[rec.id] = rec.etapa_id

        ahora = fields.Datetime.now()
        vals = dict(vals, fecha_etapa=ahora)
        vals[FECHA_POR_ETAPA[nueva.codigo]] = ahora
        res = super(AdtMotoTracking, cambian).write(vals) and res
        for rec in cambian:
            rec._registrar_log('logistica', anteriores[rec.id], nueva)
        return res

    def _validar_cambio_etapa(self, nueva, taller):
        self.ensure_one()
        if self.estado_global == 'entregado' and not self._es_manager():
            raise UserError(_('La moto %s ya fue entregada; su tracking está cerrado.') % self.vehicle_id.display_name)
        if nueva.codigo == 'fibra' and not taller:
            raise UserError(_('Para enviar la moto a fibra hay que elegir el taller: use el botón «Enviar a fibra».'))
        salto = ORDEN_ETAPA[nueva.codigo] - ORDEN_ETAPA[self.etapa_codigo]
        if salto != 1 and not self._es_manager():
            raise UserError(_(
                'La moto %(moto)s está en «%(actual)s»; solo puede pasar a la siguiente etapa. '
                'Saltar o retroceder etapas requiere permisos de administrador del tracking.',
                moto=self.vehicle_id.display_name, actual=self.etapa_id.name,
            ))

    # ── Historial ───────────────────────────────────────────────────────────

    def _registrar_log(self, flujo, desde, hasta, codigo=None, nota=None):
        """Cierra la línea abierta del flujo y abre una nueva.

        `desde` / `hasta` pueden ser una etapa (record) o un texto. Los hitos son instantáneos.
        """
        self.ensure_one()
        Log = self.env['adt.moto.tracking.log'].sudo()
        ahora = fields.Datetime.now()
        if flujo != 'hito':
            Log.search([
                ('tracking_id', '=', self.id), ('flujo', '=', flujo), ('fecha_fin', '=', False),
            ]).write({'fecha_fin': ahora})
        etapa = hasta if isinstance(hasta, models.BaseModel) else False
        Log.create({
            'tracking_id': self.id,
            'flujo': flujo,
            'etapa_desde': desde.name if isinstance(desde, models.BaseModel) else (desde or False),
            'etapa_hasta': etapa.name if etapa else hasta,
            'codigo_hasta': etapa.codigo if etapa else codigo,
            'etapa_id': etapa.id if etapa else False,
            'taller_fibra_id': self.taller_fibra_id.id if etapa and etapa.codigo == 'fibra' else False,
            'fecha_inicio': ahora,
            'fecha_fin': ahora if flujo == 'hito' else False,
            'user_id': self.env.uid,
            'nota': nota,
        })

    def _verificar_cierre(self):
        """Al quedar entregada (con placa), se cierran las líneas abiertas del historial."""
        ahora = fields.Datetime.now()
        for rec in self.filtered(lambda r: r.estado_global == 'entregado'):
            rec.log_ids.sudo().filtered(lambda l: not l.fecha_fin).write({'fecha_fin': ahora})

    # ── Sincronización con flota y adt.tramite.placa ────────────────────────

    def _calcular_estado_placa(self):
        """El trámite manda; sin trámite, una placa real en el vehículo cuenta como finalizada."""
        self.ensure_one()
        tramite = self.env['adt.tramite.placa'].sudo().search([('vehicle_id', '=', self.vehicle_id.id)], limit=1)
        if tramite:
            # Historial = finalizado que ya salió de la vista diaria.
            estado = 'finalizado' if tramite.state == 'historial' else tramite.state
        elif plate_is_ready(self.vehicle_id.license_plate):
            estado = 'finalizado'
        else:
            estado = 'pendiente'
        return estado, tramite

    def _sync_estado_placa(self):
        ahora = fields.Datetime.now()
        for rec in self:
            estado, tramite = rec._calcular_estado_placa()
            vals = {}
            if rec.tramite_placa_id != tramite:
                vals['tramite_placa_id'] = tramite.id
            anterior = rec.estado_placa
            if estado != anterior:
                vals['estado_placa'] = estado
                if estado == 'en_tramite' and not rec.fecha_inicio_tramite:
                    vals['fecha_inicio_tramite'] = ahora
                if estado == 'finalizado':
                    vals['fecha_placa_ok'] = ahora
            if not vals:
                continue
            rec.write(vals)
            if estado != anterior:
                nota = tramite.motivo_observacion if estado == 'observado' else False
                rec._registrar_log('placa', rec._label_placa(anterior), rec._label_placa(estado),
                                   codigo=estado, nota=nota)
        self._verificar_cierre()

    def _registrar_asignacion(self):
        ahora = fields.Datetime.now()
        for rec in self:
            if rec.partner_id:
                antes_de_listo = rec.etapa_codigo != 'listo'
                rec.write({'fecha_asignacion': ahora, 'asignado_antes_listo': antes_de_listo})
                rec._registrar_log('hito', False, _('Asignada a %s') % rec.partner_id.display_name)
                if antes_de_listo:
                    rec.message_post(body=_(
                        'La moto se asignó al cliente %(cliente)s estando en la etapa «%(etapa)s», '
                        'antes de estar lista.', cliente=rec.partner_id.display_name, etapa=rec.etapa_id.name))
            else:
                rec.write({'fecha_asignacion': False, 'asignado_antes_listo': False})
                rec._registrar_log('hito', False, _('Cliente desasignado'))

    def _registrar_entrega(self):
        for rec in self.filtered('fecha_entrega'):
            rec._registrar_log('hito', False, _('Entregada al cliente'))
        self._verificar_cierre()

    # ── Acciones ────────────────────────────────────────────────────────────

    def action_llevar_almacen(self):
        self.write({'etapa_id': self._etapa('almacen').id})

    def action_regreso_fibra(self):
        self.write({'etapa_id': self._etapa('listo').id})

    def action_enviar_fibra(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar a fibra'),
            'res_model': 'adt.moto.tracking.fibra.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids},
        }

    def action_iniciar_tramite(self):
        """Inicia el trámite de placa (lo crea si la moto no vino de una factura)."""
        self.ensure_one()
        tramite = self.tramite_placa_id or self.env['adt.tramite.placa'].create({'vehicle_id': self.vehicle_id.id})
        tramite.action_iniciar()

    def action_ver_tramite(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trámite de placa'),
            'res_model': 'adt.tramite.placa',
            'res_id': self.tramite_placa_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
