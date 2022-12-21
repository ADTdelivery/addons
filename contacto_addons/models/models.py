# -*- coding: utf-8 -*-

from odoo import models, fields, api


class contacto_addons(models.Model):
    _inherit = "res.partner"

    apellido_paterno = fields.Char(string="Apellido paterno")
    apellido_materno = fields.Char(string="Apellido materno")
#     _name = 'contacto_addons.contacto_addons'
#     _description = 'contacto_addons.contacto_addons'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
