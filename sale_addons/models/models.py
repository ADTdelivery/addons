# -*- coding: utf-8 -*-

from odoo import models, fields, api
import json


class SaleAddons(models.Model):
    _inherit = "sale.order"

    total_comision = fields.Monetary("Margin", compute='_compute_commission', store=True)

    @api.depends('order_line', 'amount_untaxed')
    def _compute_commission(self):
        if not all(self._ids):
            for order in self:
                order.total_comision = sum(order.order_line.mapped('new_comision'))


class SaleLineAddons(models.Model):
    _inherit = "sale.order.line"

    new_comision = fields.Monetary('sale.order.line', related='product_id.x_comision')
