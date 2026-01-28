from odoo import models, fields


class ResPartnerReference(models.Model):
    _name = 'res.partner.reference'
    _description = 'Referencia personal del cliente'

    partner_id = fields.Many2one('res.partner', ondelete='cascade', required=True)
    name = fields.Char(string="Nombre completo", required=True)
    phone = fields.Char(string="Celular", required=True)
