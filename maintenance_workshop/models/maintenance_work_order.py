# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class MaintenanceWorkOrder(models.Model):
    _name = 'maintenance.work.order'
    _description = 'Orden de Trabajo - Taller'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Número', required=True, copy=False, readonly=True, default=lambda self: _('New'))

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('in_progress', 'En progreso'),
        ('blocked', 'Bloqueado'),
        ('done', 'Finalizado')
    ], string='Estado', default='pending', tracking=True)

    client_id = fields.Many2one('res.partner', string='Cliente', required=True, tracking=True)
    mechanic_id = fields.Many2one('res.users', string='Mecánico', tracking=True)
    entry_reason = fields.Text(string='Motivo de ingreso')
    evidence_image = fields.Binary(string='Evidencia (Imagen)', attachment=True)
    mileage = fields.Float(string='Kilometraje')

    diagnostic = fields.Text(string='Diagnóstico')

    part_ids = fields.One2many('maintenance.work.order.part', 'work_order_id', string='Repuestos')
    service_ids = fields.One2many('maintenance.work.order.service', 'work_order_id', string='Mano de obra')

    parts_total = fields.Float(string='Total Repuestos', compute='_compute_totals', store=True)
    labor_total = fields.Float(string='Total Mano de Obra', compute='_compute_totals', store=True)
    total_amount = fields.Float(string='Total General', compute='_compute_totals', store=True)

    start_date = fields.Datetime(string='Fecha Inicio')
    end_date = fields.Datetime(string='Fecha Fin')
    service_duration_hours = fields.Float(string='Tiempo de atención (horas)', compute='_compute_duration', store=True)
    days_in_taller = fields.Integer(string='Días en taller', compute='_compute_days_in_taller', store=True)

    final_state = fields.Selection([('optimal','Óptimo'),('with_observations','Con Observaciones'),('follow_up','Seguimiento')], string='Resultado Final')
    final_notes = fields.Text(string='Observaciones Finales')

    key_delivery_photo = fields.Binary(string='Foto Entrega', attachment=True)
    next_revision_date = fields.Date(string='Próxima Revisión')
    mechanic_signature = fields.Binary(string='Firma Mecánico', attachment=True)
    client_signature = fields.Binary(string='Firma Cliente', attachment=True)

    @api.depends('part_ids.subtotal','service_ids.subtotal')
    def _compute_totals(self):
        for rec in self:
            rec.parts_total = sum(rec.part_ids.mapped('subtotal'))
            rec.labor_total = sum(rec.service_ids.mapped('subtotal'))
            rec.total_amount = rec.parts_total + rec.labor_total

    @api.depends('start_date','end_date')
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                try:
                    delta = fields.Datetime.from_string(rec.end_date) - fields.Datetime.from_string(rec.start_date)
                    rec.service_duration_hours = delta.total_seconds() / 3600.0
                except Exception:
                    rec.service_duration_hours = 0.0
            else:
                rec.service_duration_hours = 0.0

    @api.depends('start_date')
    def _compute_days_in_taller(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.start_date:
                try:
                    start_dt = fields.Datetime.from_string(rec.start_date)
                    start_date_only = start_dt.date()
                    days = (today - start_date_only).days
                    rec.days_in_taller = days if days > 0 else 0
                except Exception:
                    rec.days_in_taller = 0
            else:
                rec.days_in_taller = 0

    def action_start(self):
        for rec in self:
            if rec.state != 'pending':
                raise ValidationError(_('Solo se puede iniciar desde estado Pendiente.'))
            rec.state = 'in_progress'
            if not rec.start_date:
                rec.start_date = fields.Datetime.now()

    def action_block(self):
        for rec in self:
            if rec.state != 'in_progress':
                raise ValidationError(_('Solo se puede bloquear desde En progreso.'))
            rec.state = 'blocked'

    def action_unblock(self):
        for rec in self:
            if rec.state != 'blocked':
                raise ValidationError(_('Solo se puede volver a En progreso desde Bloqueado.'))
            rec.state = 'in_progress'

    def action_done(self):
        for rec in self:
            if rec.state != 'in_progress':
                raise ValidationError(_('Solo se puede finalizar desde En progreso.'))
            rec.state = 'done'
            if not rec.end_date:
                rec.end_date = fields.Datetime.now()

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            seq = self.env['ir.sequence'].next_by_code('maintenance.work.order')
            vals['name'] = seq or _('New')
        return super(MaintenanceWorkOrder, self).create(vals)
