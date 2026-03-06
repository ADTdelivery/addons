# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

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
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', tracking=True)
    entry_reason = fields.Text(string='Motivo de ingreso')
    evidence_image = fields.Binary(string='Evidencia (Imagen)', attachment=True)
    mileage = fields.Float(string='Kilometraje')

    diagnostic = fields.Text(string='Diagnóstico')

    part_ids = fields.One2many('maintenance.work.order.part', 'work_order_id', string='Repuestos')
    service_ids = fields.One2many('maintenance.work.order.service', 'work_order_id', string='Mano de obra')

    parts_total = fields.Float(string='Total Repuestos', compute='_compute_totals', store=True)
    labor_total = fields.Float(string='Total Mano de Obra', compute='_compute_totals', store=True)
    total_amount = fields.Float(string='Total General', compute='_compute_totals', store=True)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Moneda', readonly=True)

    # --- Payment responsibility fields (maintenance_workshop specific) ---
    payer_type = fields.Selection([
        ('adt', 'ADT Corporación'),
        ('cliente', 'Cliente'),
        ('ambos', 'Ambos'),
    ], string='¿Quién asume el pago?', default='cliente', tracking=True)

    # ADT contribution: user inputs a fixed amount when payer_type == 'ambos'
    adt_contribution = fields.Monetary(string='Aporte ADT', currency_field='company_currency_id', default=0.0)
    # Computed final amounts per payer
    adt_amount = fields.Monetary(string='Monto ADT', compute='_compute_payment_shares', currency_field='company_currency_id', store=True)
    client_amount = fields.Monetary(string='Monto Cliente', compute='_compute_payment_shares', currency_field='company_currency_id', store=True)
    adt_note = fields.Text(string='Nota (si ADT asume)')

    # Cronograma de pagos: número de cuotas y líneas
    payment_schedule_ids = fields.One2many('maintenance.work.order.payment', 'work_order_id', string='Cronograma de Pagos', copy=True)

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

    @api.depends('part_ids.subtotal', 'service_ids.subtotal')
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

    @api.depends('total_amount', 'payer_type', 'adt_contribution')
    def _compute_payment_shares(self):
        for rec in self:
            total = float(rec.total_amount or 0.0)
            if rec.payer_type == 'adt':
                # ADT asume todo
                rec.adt_amount = total
                rec.client_amount = 0.0
            elif rec.payer_type == 'cliente':
                # Cliente asume todo
                rec.adt_amount = 0.0
                rec.client_amount = total
            else:
                # Ambos: ADT aporta un monto fijo (adt_contribution), el resto lo paga el cliente
                contrib = float(rec.adt_contribution or 0.0)
                if contrib < 0:
                    contrib = 0.0
                if contrib > total:
                    contrib = total
                rec.adt_amount = round(contrib, 2)
                rec.client_amount = round(total - rec.adt_amount, 2)

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

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        for rec in self:
            rec.client_id = False
            vehicle = rec.vehicle_id
            if not vehicle:
                continue
            # Prefer driver_id if present
            driver_field = vehicle._fields.get('driver_id')
            if driver_field:
                try:
                    driver = getattr(vehicle, 'driver_id')
                except Exception:
                    driver = False
                if driver:
                    # if driver is a partner
                    if driver._name == 'res.partner':
                        rec.client_id = driver.id
                        continue
                    # if driver is a user, use its partner
                    if driver._name == 'res.users' and hasattr(driver, 'partner_id') and driver.partner_id:
                        rec.client_id = driver.partner_id.id
                        continue
            # Fallback to partner_id
            if getattr(vehicle, 'partner_id', False):
                rec.client_id = vehicle.partner_id.id
                continue
            # Another possible fallback: owner_id
            if getattr(vehicle, 'owner_id', False):
                rec.client_id = vehicle.owner_id.id
                continue

    def action_open_in_modal(self):
        """Return an action that opens the work order form in a modal for the current recordset (single)."""
        self.ensure_one()
        view = self.env.ref('maintenance_workshop.view_maintenance_work_order_form', False)
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Orden de Taller'),
            'res_model': 'maintenance.work.order',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')] if view else None,
            'target': 'new',
        }
        return action
