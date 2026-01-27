from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    expediente_ids = fields.One2many(
        'adt.expediente',
        'cliente_id',
        string='Expedientes'
    )
