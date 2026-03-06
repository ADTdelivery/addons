# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class MaintenanceWorkOrderPart(models.Model):
    _name = 'maintenance.work.order.part'
    _description = 'Repuestos de Orden de Trabajo'

    work_order_id = fields.Many2one('maintenance.work.order', string='Orden', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    quantity = fields.Float(string='Cantidad', default=1.0)
    unit_price = fields.Float(string='Precio Unitario')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
    notes = fields.Char(string='Notas')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            if rec.product_id:
                # Use the product's sale price (list price) as default unit price
                # Fallback to 0.0 if not set
                try:
                    rec.unit_price = rec.product_id.list_price or 0.0
                except Exception:
                    rec.unit_price = 0.0

    @api.depends('quantity','unit_price')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = (rec.quantity or 0.0) * (rec.unit_price or 0.0)

    @api.model
    def create(self, vals):
        # if unit_price not provided, try to take it from product
        if not vals.get('unit_price') and vals.get('product_id'):
            prod = self.env['product.product'].browse(vals.get('product_id'))
            if prod and prod.list_price:
                vals['unit_price'] = prod.list_price
        return super(MaintenanceWorkOrderPart, self).create(vals)

    def write(self, vals):
        # if product_id is being set/changed and unit_price not provided, autofill
        if 'product_id' in vals and not vals.get('unit_price'):
            prod = self.env['product.product'].browse(vals.get('product_id'))
            if prod and prod.list_price:
                vals['unit_price'] = prod.list_price
        return super(MaintenanceWorkOrderPart, self).write(vals)
