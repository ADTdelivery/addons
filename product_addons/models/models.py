# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductAddons(models.Model):
    _inherit = 'product.template'

    x_comision = fields.Monetary('Comisión')
    x_line_comision = fields.Monetary(related='')


#     _name = 'product_addons.product_addons'
#     _description = 'product_addons.product_addons'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
