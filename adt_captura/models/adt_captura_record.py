# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta

import logging

_logger = logging.getLogger(__name__)

# Origen de la captura: cuotas vencidas del cronograma, papeletas del SAT Lima o ambos.
SOURCE_TYPES = [
    ('mora', 'Mora (Cuotas)'),
    ('papeleta', 'Papeleta SAT'),
    ('ambos', 'Mora y Papeleta SAT'),
    ('none', 'Ninguno'),
]
LIBERACION_TIPOS = [
    ('refinanciamiento', 'Refinanciamiento'),
    ('pago_total', 'Pago Total del Pendiente'),
    ('pago_papeleta_sat', 'Pago de las papeletas SAT'),
]
RETENCION_MOTIVOS = [
    ('motivo1', 'El cliente no se comunicó por más de 3 días'),
    ('motivo2', 'El cliente decidio no continuar pagando el credito'),
    ('otro', 'Otro'),
]
GRUPO_SUPERVISOR = 'adt_captura.group_captura_supervisor'
# Evidencias y documentos de la captura se guardan tal como se subieron: sin esto Odoo
# reduce las imágenes a 1920 px y las recomprime (base.image_autoresize_max_px).
SIN_REDIMENSIONAR = {'image_no_postprocess': True}


class ADTCapturaRecord(models.Model):
    _name = 'adt.captura.record'
    _description = 'Registro de Captura de Vehículo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Número', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'), tracking=True)

    # Datos principales
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True,
                                 tracking=True, domain=[('customer_rank', '>', 0)])
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta',
                                required=True, tracking=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo',
                                 related='cuenta_id.vehiculo_id', store=True, readonly=True)

    # Tipo de captura
    capture_type = fields.Selection([
        ('inmediata', 'Inmediata'),
        ('compromiso', 'Compromiso de Pago'),
    ], string='Tipo de Captura', required=True, default='inmediata', tracking=True)

    commitment_date = fields.Date(string='Fecha Compromiso', tracking=True,
                                   help='Fecha comprometida para el pago (solo si tipo = compromiso)')

    # Persistent upload status shared by all Odoo workers.
    evidencias_status = fields.Selection([
        ('pending', 'Pendiente'), ('processing', 'Procesando'),
        ('completed', 'Completado'), ('failed', 'Fallido'),
    ], default='pending', required=True, copy=False, readonly=True)

    # Evidencia
    evidencia_archivos = fields.Many2many('ir.attachment',
                                               'adt_captura_evidencia_rel',
                                               'captura_id', 'attachment_id',
                                               string='Evidencias (Fotos/Videos)',
                                               help='Adjunta imágenes o videos como evidencia de la captura')

    notes = fields.Text(string='Observaciones', tracking=True)
    comentarios_captura = fields.Text(string='Comentarios de Captura', tracking=True)

    # Deuda de intervención
    intervention_fee = fields.Float(string='Monto Intervención (S/)',
                                    default=50.0, required=True, tracking=True)

    # Estado de captura
    state = fields.Selection([
        ('capturado', 'Capturado'),
        ('liberado', 'Liberado'),
        ('disolucion_contrato', 'Iniciar Disolución Contrato'),
        ('cancelado', 'Cancelado'),
        ('recolocada', 'Recolocada'),
    ], string='Estado', default='capturado', required=True, tracking=True)

    # Estado de pago
    payment_state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado'),
    ], string='Estado Pago', default='pendiente', required=True, tracking=True)

    # Información de pago
    voucher_file = fields.Binary(string='Voucher', attachment=True)
    voucher_filename = fields.Char(string='Nombre Archivo Voucher')
    voucher_number = fields.Char(string='Número de Voucher', tracking=True)
    payment_date = fields.Date(string='Fecha de Pago', tracking=True)
    motivo_no_pago = fields.Text(string='Motivo de no pago', readonly=True)
    pagar_monto = fields.Boolean(string='¿Pagar monto?', default=True)

    # Retención
    retention_reason = fields.Selection(RETENCION_MOTIVOS, string='Motivo', tracking=True)

    retention_date = fields.Date(string='Fecha de inicio', tracking=True)
    notes = fields.Text(string='Observaciones Adicionales', readonly=True)

    # Información de mora
    dias_mora = fields.Integer(string='Días de Mora', compute='_compute_mora_info', store=True)
    numero_cuotas_vencidas = fields.Integer(string='# Cuotas Vencidas', compute='_compute_mora_info', store=True)
    tipo_cartera = fields.Selection([
        ('qorilazo', 'Qorilazo'),
        ('los_andes', 'Los Andes'),
    ], string='Tipo Cartera', related='cuenta_id.periodicidad', store=True)

    # Trazabilidad
    capturador_id = fields.Many2one('res.users', string='Capturador',
                                    default=lambda self: self.env.user, tracking=True)
    supervisor_id = fields.Many2one('res.users', string='Supervisor', tracking=True)

    # Computed fields para controles
    puede_liberar = fields.Boolean(string='Puede Liberar', compute='_compute_puede_liberar')
    es_estado_final = fields.Boolean(string='Es Estado Final', compute='_compute_es_estado_final')

    # Alerta de deuda anterior
    tiene_deuda_anterior = fields.Boolean(string='Tiene Deuda Anterior', compute='_compute_deuda_anterior', store=False)
    monto_deuda_anterior = fields.Float(string='Monto Deuda Anterior', compute='_compute_deuda_anterior', store=False)
    capturas_anteriores_ids = fields.Many2many('adt.captura.record',
                                                'adt_captura_deuda_rel',
                                                'captura_actual_id',
                                                'captura_anterior_id',
                                                string='Capturas Anteriores Sin Pagar',
                                                compute='_compute_deuda_anterior',
                                                store=False)

    # Cuotas Pendientes
    cuotas_pendientes_ids = fields.One2many(
        comodel_name='adt.comercial.cuotas',
        inverse_name='cuenta_id',
        string='Cuotas Pendientes',
        compute='_compute_cuotas_pendientes',
        store=False
    )

    # Días de retraso en compromiso
    commitment_delay_days = fields.Integer(
        string='Días de Retraso (Compromiso)',
        compute='_compute_commitment_delay_days',
        store=False
    )

    # Maintenance info: show if vehicle has a maintenance in_progress
    maintenance_start_date = fields.Datetime(
        string='Fecha inicio mantenimiento',
        compute='_compute_maintenance_taller',
        store=False
    )
    maintenance_days_in_taller = fields.Integer(
        string='Días en taller (mantenimiento)',
        compute='_compute_maintenance_taller',
        store=False
    )
    maintenance_taller_message = fields.Char(
        string='Mensaje mantenimiento',
        compute='_compute_maintenance_taller',
        store=False
    )

    # Nuevo: Campos para recogida de moto
    moto_recogida = fields.Boolean(string='¿Moto recogida?', default=False, tracking=True)
    motivo_no_recogida = fields.Text(string='Motivo si no se recogió', tracking=True)

    liberacion_tipo = fields.Selection(LIBERACION_TIPOS, string='Tipo de Liberación', tracking=True)

    observaciones = fields.Text(string='Observaciones', tracking=True)

    source_type = fields.Selection(SOURCE_TYPES, string='Origen', tracking=True)

    # Papeletas del SAT Lima pendientes al momento de la captura. Su pago lo confirma
    # la sincronización con el SAT (adt_papeletas), no la captura.
    papeleta_sat_ids = fields.Many2many(
        'adt.papeleta.sat', 'adt_captura_papeleta_sat_rel', 'captura_id', 'papeleta_sat_id',
        string='Papeletas SAT', readonly=True)
    papeletas_sat_pendientes = fields.Integer(
        string='Papeletas SAT pendientes', compute='_compute_deuda_sat',
        help='Papeletas SAT de la captura que el SAT aún muestra pendientes de pago.')
    deuda_sat = fields.Monetary(
        string='Deuda SAT pendiente', compute='_compute_deuda_sat', currency_field='company_currency_id')

    company_currency_id = fields.Many2one('res.currency', string='Moneda', related='company_id.currency_id', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    retention_wizard_ids = fields.One2many(
        'adt.captura.retencion.wizard', 'captura_id', string='Retenciones')

    # Nuevos campos para apelación
    appeal_ids = fields.One2many(
        'adt.captura.appeal', 'captura_id', string='Apelaciones'
    )
    documento_desafiliacion = fields.Binary(string='Documento de Desafiliación')
    evidencia_entrega = fields.Binary(string='Evidencia de la Entrega')

    @api.depends('papeleta_sat_ids.estado_pago', 'papeleta_sat_ids.deuda')
    def _compute_deuda_sat(self):
        for record in self:
            pendientes = record.papeleta_sat_ids.filtered(lambda p: p.estado_pago == 'pendiente')
            record.papeletas_sat_pendientes = len(pendientes)
            record.deuda_sat = sum(pendientes.mapped('deuda'))

    @api.depends('cuenta_id', 'cuenta_id.cuota_ids')
    def _compute_mora_info(self):
        for record in self:
            if record.cuenta_id:
                # Calcular días de mora desde la cuota más antigua vencida
                cuotas_vencidas = record.cuenta_id.cuota_ids.filtered(
                    lambda c: c.state in ['pendiente', 'retrasado'] and c.fecha_cronograma < fields.Date.today()
                )
                if cuotas_vencidas:
                    cuota_mas_antigua = min(cuotas_vencidas, key=lambda c: c.fecha_cronograma)
                    dias = (fields.Date.today() - cuota_mas_antigua.fecha_cronograma).days
                    record.dias_mora = dias
                    record.numero_cuotas_vencidas = len(cuotas_vencidas)
                else:
                    record.dias_mora = 0
                    record.numero_cuotas_vencidas = 0
            else:
                record.dias_mora = 0
                record.numero_cuotas_vencidas = 0

    @api.depends('payment_state', 'state')
    def _compute_puede_liberar(self):
        for record in self:
            # Puede liberar si está en estado capturado, independientemente del pago
            record.puede_liberar = record.state == 'capturado'

    @api.depends('state')
    def _compute_es_estado_final(self):
        for record in self:
            record.es_estado_final = record.state in ['liberado', 'disolucion_contrato', 'cancelado']

    @api.depends('cuenta_id', 'partner_id')
    def _compute_deuda_anterior(self):
        for record in self:
            # Si el registro es nuevo (no tiene ID real), no calcular deuda anterior
            if not record.id or isinstance(record.id, models.NewId):
                record.capturas_anteriores_ids = False
                record.tiene_deuda_anterior = False
                record.monto_deuda_anterior = 0.0
                continue

            if record.cuenta_id:
                # Buscar capturas anteriores sin pagar de la misma cuenta
                capturas_previas = self.search([
                    ('cuenta_id', '=', record.cuenta_id.id),
                    ('payment_state', '=', 'pendiente'),
                    ('id', '!=', record.id),
                    ('state', 'in', ['capturado', 'disolucion_contrato'])  # Solo activas o disolución
                ])

                record.capturas_anteriores_ids = capturas_previas
                record.tiene_deuda_anterior = len(capturas_previas) > 0
                record.monto_deuda_anterior = sum(capturas_previas.mapped('intervention_fee'))
            else:
                record.capturas_anteriores_ids = False
                record.tiene_deuda_anterior = False
                record.monto_deuda_anterior = 0.0

    @api.depends('cuenta_id', 'cuenta_id.cuota_ids')
    def _compute_cuotas_pendientes(self):
        for record in self:
            if record.cuenta_id and hasattr(record.cuenta_id, 'cuota_ids'):
                record.cuotas_pendientes_ids = record.cuenta_id.cuota_ids.filtered(
                    lambda c: c.state in ['pendiente', 'retrasado']
                )
            else:
                record.cuotas_pendientes_ids = False

    @api.depends('vehicle_id')
    def _compute_maintenance_taller(self):
        for record in self:
            record.maintenance_start_date = False
            record.maintenance_days_in_taller = 0
            record.maintenance_taller_message = False

            if not record.vehicle_id:
                continue

            maint = self.env['adt.tvs.mantenimiento'].search([
                ('vehicle_id', '=', record.vehicle_id.id),
                ('state', '=', 'in_progress')
            ], order='date_inicio_revision asc', limit=1)

            if not maint:
                continue

            start = maint.date_inicio_revision
            if not start:
                continue

            try:
                start_dt = fields.Datetime.from_string(start)
                now_dt = fields.Datetime.from_string(fields.Datetime.now())
            except Exception:
                # don't fail compute; just skip
                continue

            days = max(0, (now_dt - start_dt).days)

            record.maintenance_start_date = start
            record.maintenance_days_in_taller = days
            # Format date as YYYY-MM-DD for readability
            try:
                date_str = start_dt.strftime('%Y-%m-%d')
            except Exception:
                date_str = str(start)

            record.maintenance_taller_message = f"El cliente lleva {days} días en el taller desde la fecha {date_str}."

    @api.depends('capture_type', 'commitment_date')
    def _compute_commitment_delay_days(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.capture_type == 'compromiso' and record.commitment_date:
                delay = (today - record.commitment_date).days
                record.commitment_delay_days = delay if delay > 0 else 0
            else:
                record.commitment_delay_days = 0

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('adt.captura.record') or _('New')

        type = 'Captura Inmediata'
        if vals.get('capture_type') == 'compromiso':
            type = 'Compromiso de Pago'
        # Retrieve the vehicle_id from cuenta_id if not directly provided
        cuenta = self.env['adt.comercial.cuentas'].browse(vals.get('cuenta_id'))
        if not vals.get('vehicle_id') and cuenta:
            vals['vehicle_id'] = cuenta.vehiculo_id.id

        vehicle_id = vals.get('vehicle_id')
        if vehicle_id:
            self._set_vehicle_state(self.env['fleet.vehicle'].browse(vehicle_id), type)

        # Origen y papeletas SAT pendientes, tal como figuran en la lista de posibles capturas.
        if cuenta and 'adt.captura.mora' in self.env:
            mora = self.env['adt.captura.mora'].sudo().search([('cuenta_id', '=', cuenta.id)], limit=1)
            if not vals.get('source_type'):
                vals['source_type'] = mora.source_type or 'none'
            if 'papeleta_sat_ids' not in vals and mora.papeletas_sat:
                vals['papeleta_sat_ids'] = [(6, 0, self._papeletas_sat_pendientes(cuenta).ids)]

        # Validar fecha compromiso si es tipo compromiso
        if vals.get('capture_type') == 'compromiso':
            if not vals.get('commitment_date'):
                raise ValidationError('Debe especificar una fecha de compromiso.')
            commitment_date = fields.Date.from_string(vals['commitment_date'])
            if commitment_date <= fields.Date.today():
                raise ValidationError('La fecha de compromiso debe ser futura.')

        return super(ADTCapturaRecord, self).create(vals)

    @api.model
    def _papeletas_sat_pendientes(self, cuenta):
        """Papeletas SAT pendientes de la cuenta, con el mismo criterio que adt.captura.mora."""
        Sat = self.env['adt.papeleta.sat'].sudo()
        if not cuenta.vehiculo_id or cuenta.state not in ('aprobado', 'en_curso'):
            return Sat
        domain = [('vehicle_id', '=', cuenta.vehiculo_id.id), ('estado_pago', '=', 'pendiente')]
        if cuenta.fecha_desembolso:
            domain += ['|', ('fecha_infraccion', '=', False), ('fecha_infraccion', '>=', cuenta.fecha_desembolso)]
        return Sat.search(domain, order='fecha_infraccion asc, id asc')

    @api.model
    def _set_vehicle_state(self, vehicle, nombre):
        """Pasa el vehículo al estado de flota `nombre` (si existe)."""
        state = self.env['fleet.vehicle.state'].search([('name', '=', nombre)], limit=1)
        if vehicle and state:
            vehicle.write({'state_id': state.id})
        elif vehicle:
            _logger.warning('No existe el estado de flota "%s"; el vehículo %s no cambia de estado.', nombre, vehicle.id)

    def _check_supervisor(self, accion):
        if not self.env.user.has_group(GRUPO_SUPERVISOR):
            raise UserError(_('Solo los supervisores pueden %s.') % accion)

    # ------------------------------------------------------------------
    # Pasos del proceso (los usan los asistentes y la vista de Flota 360)
    # ------------------------------------------------------------------

    def registrar_pago_intervencion(self, monto, payment_date, voucher_number=False, voucher_file=False,
                                    voucher_filename=False, pagar_monto=True, motivo_no_pago=False):
        """Paso "Cobrar": registra el pago de la intervención (o la exoneración con su motivo)."""
        self.ensure_one()
        if self.state not in ('capturado', 'disolucion_contrato'):
            raise UserError(_('Solo puede registrar pago en estado Capturado o Disolución de Contrato.'))
        payment_date = fields.Date.to_date(payment_date)
        if not payment_date:
            raise ValidationError(_('Indique la fecha de pago.'))
        if payment_date > fields.Date.context_today(self):
            raise ValidationError(_('La fecha de pago no puede ser futura.'))
        if pagar_monto:
            if not monto or monto <= 0:
                raise ValidationError(_('El monto debe ser mayor a cero.'))
            if not voucher_number or not voucher_file:
                raise ValidationError(_('Indique el número de voucher y adjunte el voucher de pago.'))
        elif not (motivo_no_pago or '').strip():
            raise UserError(_('Debe especificar un motivo para no realizar el pago.'))
        self.with_context(**SIN_REDIMENSIONAR).write({
            'payment_state': 'pagado',
            'voucher_file': voucher_file if pagar_monto else False,
            'voucher_filename': voucher_filename if pagar_monto else False,
            'voucher_number': voucher_number if pagar_monto else False,
            'payment_date': payment_date,
            'intervention_fee': monto if pagar_monto else self.intervention_fee,
            'motivo_no_pago': False if pagar_monto else motivo_no_pago,
            'pagar_monto': pagar_monto,
        })
        if pagar_monto:
            mensaje = _('<p><strong>Pago Registrado</strong></p><ul><li>Monto: S/ %.2f</li><li>N° Voucher: %s</li>'
                        '<li>Fecha: %s</li></ul>') % (monto, voucher_number, payment_date)
        else:
            mensaje = _('<p><strong>Intervención sin pago</strong></p><p>Motivo: %s</p>') % motivo_no_pago
        self.message_post(body=mensaje, subject=_('Pago Registrado'))
        return True

    def liberar_vehiculo(self, liberacion_tipo, observaciones=False):
        """Paso "Cerrar": libera el vehículo y lo devuelve a préstamo en progreso."""
        self.ensure_one()
        self._check_supervisor(_('liberar vehículos'))
        if self.state != 'capturado':
            raise UserError(_('Solo se pueden liberar capturas en estado Capturado.'))
        if liberacion_tipo not in dict(LIBERACION_TIPOS):
            raise ValidationError(_('Indique el tipo de liberación.'))
        self._set_vehicle_state(self.vehicle_id, 'Prestamo en Progreso')
        self.write({
            'state': 'liberado',
            'liberacion_tipo': liberacion_tipo,
            'observaciones': observaciones,
            'supervisor_id': self.env.user.id,
        })
        mensaje = _('Vehículo liberado por %s (%s).') % (self.env.user.name, dict(LIBERACION_TIPOS)[liberacion_tipo])
        if liberacion_tipo == 'pago_papeleta_sat' and self.papeletas_sat_pendientes:
            mensaje += _(' El SAT aún muestra %s papeleta(s) pendiente(s) por S/ %.2f: el pago se confirmará '
                         'en la próxima consulta al SAT.') % (self.papeletas_sat_pendientes, self.deuda_sat)
        self.message_post(body=mensaje)
        return True

    def iniciar_disolucion(self, retention_reason, retention_date, notes=False):
        """Paso "Cerrar": retiene el vehículo e inicia la disolución del contrato."""
        self.ensure_one()
        self._check_supervisor(_('retener vehículos'))
        if self.state != 'capturado':
            raise UserError(_('Solo se pueden retener capturas en estado Capturado.'))
        retention_date = fields.Date.to_date(retention_date)
        if retention_reason not in dict(RETENCION_MOTIVOS):
            raise ValidationError(_('Indique el motivo de la retención.'))
        if not retention_date or retention_date > fields.Date.context_today(self):
            raise ValidationError(_('La fecha de retención no puede ser futura.'))
        if retention_reason == 'otro' and len((notes or '').strip()) < 10:
            raise ValidationError(_('Las observaciones deben tener al menos 10 caracteres cuando el motivo es "Otro".'))
        self.write({
            'state': 'disolucion_contrato',
            'retention_reason': retention_reason,
            'retention_date': retention_date,
            'notes': notes,
            'supervisor_id': self.env.user.id,
        })
        self._set_vehicle_state(self.vehicle_id, 'Disolución de contrato')
        mensaje = _('<p><strong>Vehículo Retenido</strong></p><p><strong>Motivo:</strong> %s</p>'
                    '<p><strong>Fecha:</strong> %s</p><p><strong>Supervisor:</strong> %s</p>') % (
            dict(RETENCION_MOTIVOS)[retention_reason], retention_date, self.env.user.name)
        if notes:
            mensaje += _('<p><strong>Observaciones:</strong> %s</p>') % notes
        self.message_post(body=mensaje, subject=_('Vehículo Retenido'))
        return True

    def recolocar_vehiculo(self, documento_desafiliacion, evidencia_entrega):
        """Último paso de la disolución: cancela la cuenta y marca el vehículo como recolocado."""
        self.ensure_one()
        self._check_supervisor(_('recolocar vehículos'))
        if self.state != 'disolucion_contrato':
            raise UserError(_('Solo se pueden recolocar vehículos en estado Disolución de Contrato.'))
        if not documento_desafiliacion or not evidencia_entrega:
            raise ValidationError(_('Adjunte el documento de desafiliación y la evidencia de la entrega.'))
        self.with_context(**SIN_REDIMENSIONAR).write({
            'state': 'recolocada',
            'documento_desafiliacion': documento_desafiliacion,
            'evidencia_entrega': evidencia_entrega,
        })
        if self.cuenta_id:
            self.cuenta_id.write({'state': 'cancelado'})
        self._set_vehicle_state(self.vehicle_id, 'Recolocada')
        self.message_post(body=_('Vehículo recolocado por %s; la cuenta %s pasó a cancelada.')
                          % (self.env.user.name, self.cuenta_id.reference_no or ''))
        return True

    @api.constrains('commitment_date', 'capture_type')
    def _check_commitment_date(self):
        for record in self:
            if record.capture_type == 'compromiso':
                if not record.commitment_date:
                    raise ValidationError('Debe especificar una fecha de compromiso.')
                if record.commitment_date <= fields.Date.today():
                    raise ValidationError('La fecha de compromiso debe ser futura.')

    @api.constrains('retention_reason')
    def _check_retention_reason(self):
        for record in self:
            if record.state == 'disolucion_contrato' and not record.retention_reason:
                raise ValidationError('El motivo de retención es obligatorio.')

    def action_registrar_pago(self):
        """Abre wizard para registrar el pago"""
        self.ensure_one()

        if self.state not in ['capturado', 'disolucion_contrato']:
            raise UserError('Solo puede registrar pago en estado Capturado o Disolución de Contrato.')

        return {
            'name': 'Registrar Pago de Intervención',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.pago.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_captura_id': self.id,
                'default_monto': self.intervention_fee,
            }
        }

    def action_liberar(self):
        """Libera el vehículo (requiere motivo)"""
        self.ensure_one()

        if not self.env.user.has_group('adt_captura.group_captura_supervisor'):
            raise UserError('Solo los supervisores pueden liberar vehículos.')

        return {
            'name': 'Liberar Vehículo',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.liberar.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_captura_id': self.id,
            }
        }

    def action_retener(self):
        """Retiene el vehículo (requiere motivo)"""
        self.ensure_one()

        if not self.env.user.has_group('adt_captura.group_captura_supervisor'):
            raise UserError('Solo los supervisores pueden retener vehículos.')

        if self.state != 'capturado':
            raise UserError('Solo se pueden retener capturas en estado Capturado.')

        return {
            'name': 'Disolución de Contrato',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.retencion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_captura_id': self.id,
            }
        }

    def action_cancelar(self):
        """Cancela la captura"""
        self.ensure_one()
        self._check_supervisor(_('cancelar capturas'))

        if self.es_estado_final:
            raise UserError('No se puede cancelar una captura en estado final.')

        self.write({
            'state': 'cancelado',
            'supervisor_id': self.env.user.id,
        })

        self.message_post(body=f"Captura cancelada por {self.env.user.name}")

        return True

    def action_ver_evidencia(self):
        """Abre las evidencias adjuntas"""
        self.ensure_one()

        return {
            'name': 'Evidencia de Captura',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', self.evidencia_archivos.ids)],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
            }
        }

    def action_ver_cuenta(self):
        """Abre la cuenta asociada"""
        self.ensure_one()

        return {
            'name': f'Cuenta {self.cuenta_id.reference_no}',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.comercial.cuentas',
            'view_mode': 'form',
            'res_id': self.cuenta_id.id,
        }

    def action_ver_mantenimientos(self):
        """Abre un popup mostrando los mantenimientos relacionados con el vehículo de esta captura.

        Solo filtra por vehicle_id; no combina otra lógica adicional.
        """
        self.ensure_one()
        if not self.vehicle_id:
            raise UserError('No hay vehículo asociado a esta captura.')

        return {
            'name': 'Mantenimientos del Vehículo',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.tvs.mantenimiento',
            'view_mode': 'tree,form',
            'target': 'new',
            'domain': [('vehicle_id', '=', self.vehicle_id.id)],
            'context': {'create': False},
        }

    def action_recolocar(self):
        """Recoloca el vehículo"""
        self.ensure_one()

        if not self.env.user.has_group('adt_captura.group_captura_supervisor'):
            raise UserError('Solo los supervisores pueden recolocar vehículos.')

        if self.state != 'disolucion_contrato':
            raise UserError('Solo se pueden recolocar vehículos en estado Disolución de Contrato.')

        return {
            'name': 'Recolocar Vehículo',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.recolocar.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_captura_id': self.id,
            }
        }

    @api.depends('state')
    def _compute_visibility_fields(self):
        for record in self:
            record.show_desafiliacion_fields = record.state == 'recolocada'

    show_desafiliacion_fields = fields.Boolean(string="Show Desafiliacion Fields", compute="_compute_visibility_fields")

    def action_open_in_modal(self):
        """Open this captura in a modal form view."""
        self.ensure_one()
        view = self.env.ref('adt_captura.view_adt_captura_record_form', False)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Captura'),
            'res_model': 'adt.captura.record',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')] if view else None,
            'target': 'new',
        }


class ADTCapturaAppeal(models.Model):
    _name = 'adt.captura.appeal'
    _description = 'Apelación de Disolución de Contrato'

    captura_id = fields.Many2one(
        'adt.captura.record', string='Captura', required=True, ondelete='cascade'
    )
    appeal_reason = fields.Char(string='Motivo de Apelación', required=True)
    appeal_evidence = fields.Binary(string='Evidencia de Apelación', attachment=True)


class ADTCapturaRecolocarWizard(models.TransientModel):
    _name = 'adt.captura.recolocar.wizard'
    _description = 'Recolocar Wizard'

    captura_id = fields.Many2one('adt.captura.record', string='Captura')
    # attachment=False: el archivo pasa a la captura sin que Odoo lo redimensione.
    documento_desafiliacion = fields.Binary(string='Documento de Desafiliación', required=True, attachment=False)
    evidencia_entrega = fields.Binary(string='Evidencia de la Entrega', required=True, attachment=False)

    def confirmar_recolocacion(self):
        """Confirm recolocacion and perform necessary actions."""
        self.ensure_one()
        self.captura_id.recolocar_vehiculo(self.documento_desafiliacion, self.evidencia_entrega)
        return {'type': 'ir.actions.act_window_close'}
