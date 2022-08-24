from odoo import models, fields, api


class FieldModels(models.Model):
    _inherit = 'fleet.vehicle'

    contrato_vehicular = fields.Binary(string="Contrato vehicular")
