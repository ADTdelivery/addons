# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class MaintenanceWorkOrderService(models.Model):
    _name = 'maintenance.work.order.service'
    _description = 'Servicios / Mano de obra'

    work_order_id = fields.Many2one('maintenance.work.order', string='Orden', ondelete='cascade')
    service_template_id = fields.Many2one('maintenance.work.order.service.template', string='Servicio')
    name = fields.Char(string='Servicio')
    description = fields.Text(string='Descripción')
    unit_price = fields.Float(string='Precio Unitario')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal')

    @api.onchange('service_template_id')
    def _onchange_service_template(self):
        for rec in self:
            if rec.service_template_id:
                rec.name = rec.service_template_id.name
                rec.description = rec.service_template_id.description
                rec.unit_price = rec.service_template_id.default_unit_price

    @api.depends('unit_price')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = (rec.unit_price or 0.0)

    def action_save_as_template(self):
        self.ensure_one()
        vals = {
            'name': self.name,
            'description': self.description,
            'default_unit_price': self.unit_price,
            'company_id': self.env.company.id,
        }
        template = self.env['maintenance.work.order.service.template'].create(vals)
        return template

    @api.model
    def create(self, vals):
        # If unit_price is not provided but a template is, use template default
        if not vals.get('unit_price') and vals.get('service_template_id'):
            tmpl = self.env['maintenance.work.order.service.template'].browse(vals.get('service_template_id'))
            if tmpl and tmpl.default_unit_price:
                vals['unit_price'] = tmpl.default_unit_price
        rec = super(MaintenanceWorkOrderService, self).create(vals)
        return rec

    def write(self, vals):
        # If service_template_id is being set/changed and unit_price not provided,
        # autofill unit_price from the template
        if 'service_template_id' in vals and not vals.get('unit_price'):
            tmpl = self.env['maintenance.work.order.service.template'].browse(vals.get('service_template_id'))
            if tmpl and tmpl.default_unit_price:
                vals['unit_price'] = tmpl.default_unit_price
        return super(MaintenanceWorkOrderService, self).write(vals)
