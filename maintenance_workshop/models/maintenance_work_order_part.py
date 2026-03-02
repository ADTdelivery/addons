# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class MaintenanceWorkOrderPart(models.Model):
    _name = 'maintenance.work.order.part'
    _description = 'Repuestos de Orden de Trabajo'

    work_order_id = fields.Many2one('maintenance.work.order', string='Orden', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto')
    quantity = fields.Float(string='Cantidad', default=1.0)
    unit_price = fields.Float(string='Precio Unitario')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
    notes = fields.Char(string='Notas')

    @api.depends('quantity','unit_price')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = (rec.quantity or 0.0) * (rec.unit_price or 0.0)
