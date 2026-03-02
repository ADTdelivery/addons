# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime


class AdtTvsMantenimiento(models.Model):
    _name = 'adt.tvs.mantenimiento'
    _description = 'ADT TVS Mantenimiento'
    _rec_name = 'name'

    name = fields.Char(string='Número', required=True, copy=False, readonly=True, default=lambda self: _('New'))

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True)
    motivo_ingreso = fields.Char(string='Motivo de ingreso')

    date_inicio_revision = fields.Datetime(string='Fecha inicio revisión', required=True, default=fields.Datetime.now)
    date_fin_revision = fields.Datetime(string='Fecha fin revisión')
    days_in_taller = fields.Integer(string='Días en taller', compute='_compute_days_in_taller', store=True)

    attachment_ids = fields.Many2many('ir.attachment', string='Archivos')

    state = fields.Selection([
        ('in_progress', 'En taller'),
        ('done', 'Revisión finalizada')
    ], string='Estado', default='in_progress', required=True)

    active = fields.Boolean(default=True)

    @api.model
    def create(self, vals):
        # ensure new records are created with a name and start in 'in_progress'
        if vals.get('name', _('New')) == _('New') or not vals.get('name'):
            seq = self.env['ir.sequence'].next_by_code('adt.tvs.mantenimiento')
            vals['name'] = seq or vals.get('name', _('New'))
        if not vals.get('state'):
            vals['state'] = 'in_progress'
        return super(AdtTvsMantenimiento, self).create(vals)

    @api.depends('date_inicio_revision', 'date_fin_revision')
    def _compute_days_in_taller(self):
        for rec in self:
            if not rec.date_inicio_revision:
                rec.days_in_taller = 0
                continue
            # use end date if set, otherwise now
            end_dt = rec.date_fin_revision or fields.Datetime.now()
            try:
                start = fields.Datetime.from_string(rec.date_inicio_revision)
                end = fields.Datetime.from_string(end_dt)
            except Exception:
                # fallback to zero
                rec.days_in_taller = 0
                continue
            delta = end - start
            # ensure non-negative
            rec.days_in_taller = max(0, delta.days)

    def action_ingresar_taller(self):
        for rec in self:
            if not rec.date_inicio_revision:
                raise UserError(_('La fecha de inicio de revisión es obligatoria para ingresar al taller.'))
            rec.state = 'in_progress'

    def action_finalizar_revision(self):
        for rec in self:
            if not rec.date_fin_revision:
                raise UserError(_('Debe registrar la fecha de fin de revisión antes de finalizar.'))
            # Ensure date_fin >= date_inicio
            if rec.date_inicio_revision and rec.date_fin_revision:
                start = fields.Datetime.from_string(rec.date_inicio_revision)
                end = fields.Datetime.from_string(rec.date_fin_revision)
                if end < start:
                    raise ValidationError(_('La fecha fin no puede ser anterior a la fecha de inicio.'))
            rec.state = 'done'

    @api.constrains('state', 'date_fin_revision')
    def _check_finalized_has_date(self):
        for rec in self:
            if rec.state == 'done' and not rec.date_fin_revision:
                raise ValidationError(_('No se puede marcar como finalizado sin una fecha de fin.'))

    def write(self, vals):
        # prevent editing finalized records
        if any(r.state == 'done' for r in self):
            # allow only modifications that don't change content? For simplicity, block all
            raise UserError(_('No se puede modificar un registro que ya fue finalizado.'))
        return super(AdtTvsMantenimiento, self).write(vals)

    def unlink(self):
        if any(r.state == 'done' for r in self):
            raise UserError(_('No se puede eliminar un registro que ya fue finalizado.'))
        return super(AdtTvsMantenimiento, self).unlink()
