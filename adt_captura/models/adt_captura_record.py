# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta

import logging

_logger = logging.getLogger(__name__)


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

    # Evidencia
    evidencia_archivos = fields.Many2many('ir.attachment',
                                               'adt_captura_evidencia_rel',
                                               'captura_id', 'attachment_id',
                                               string='Evidencias (Fotos/Videos)',
                                               help='Adjunta imágenes o videos como evidencia de la captura')

    notes = fields.Text(string='Observaciones', tracking=True)

    # Deuda de intervención
    intervention_fee = fields.Float(string='Monto Intervención (S/)',
                                    default=50.0, required=True, tracking=True)

    # Estado de captura
    state = fields.Selection([
        ('capturado', 'Capturado'),
        ('liberado', 'Liberado'),
        ('retenido', 'Vehículo Retenido'),
        ('cancelado', 'Cancelado'),
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

    # Retención
    retention_reason = fields.Text(string='Motivo de Retención', tracking=True)
    retention_date = fields.Date(string='Fecha de Retención', tracking=True)

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

    @api.depends('evidencia_archivos')
    def _compute_evidence_count(self):
        for record in self:
            record.evidence_count = len(record.evidencia_archivos)

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
            record.es_estado_final = record.state in ['liberado', 'retenido', 'cancelado']

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
                    ('state', 'in', ['capturado', 'retenido'])  # Solo activas o retenidas
                ])

                record.capturas_anteriores_ids = capturas_previas
                record.tiene_deuda_anterior = len(capturas_previas) > 0
                record.monto_deuda_anterior = sum(capturas_previas.mapped('intervention_fee'))
            else:
                record.capturas_anteriores_ids = False
                record.tiene_deuda_anterior = False
                record.monto_deuda_anterior = 0.0

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('adt.captura.record') or _('New')


        # Validar fecha compromiso si es tipo compromiso
        if vals.get('capture_type') == 'compromiso':
            if not vals.get('commitment_date'):
                raise ValidationError('Debe especificar una fecha de compromiso.')
            commitment_date = fields.Date.from_string(vals['commitment_date'])
            if commitment_date <= fields.Date.today():
                raise ValidationError('La fecha de compromiso debe ser futura.')

        return super(ADTCapturaRecord, self).create(vals)

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
            if record.state == 'retenido' and not record.retention_reason:
                raise ValidationError('El motivo de retención es obligatorio.')

    def action_registrar_pago(self):
        """Abre wizard para registrar el pago"""
        self.ensure_one()

        if self.state != 'capturado':
            raise UserError('Solo puede registrar pago en estado Capturado.')

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
        """Libera el vehículo (el pago puede estar pendiente o pagado)"""
        self.ensure_one()

        if not self.env.user.has_group('adt_captura.group_captura_supervisor'):
            raise UserError('Solo los supervisores pueden liberar vehículos.')

        if self.state != 'capturado':
            raise UserError('Solo se pueden liberar capturas en estado Capturado.')

        self.write({
            'state': 'liberado',
            'supervisor_id': self.env.user.id,
        })

        mensaje = f"Vehículo liberado por {self.env.user.name}"
        if self.payment_state == 'pendiente':
            mensaje += " - NOTA: Pago aún está pendiente"

        self.message_post(body=mensaje)

        return True

    def action_retener(self):
        """Retiene el vehículo (requiere motivo)"""
        self.ensure_one()

        if not self.env.user.has_group('adt_captura.group_captura_supervisor'):
            raise UserError('Solo los supervisores pueden retener vehículos.')

        if self.state != 'capturado':
            raise UserError('Solo se pueden retener capturas en estado Capturado.')

        return {
            'name': 'Retener Vehículo',
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

        if not self.env.user.has_group('adt_captura.group_captura_supervisor'):
            raise UserError('Solo los supervisores pueden cancelar capturas.')

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
