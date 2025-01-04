from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTResPartner(models.Model):
    _inherit = 'res.partner'

    codigo_socio = fields.Char(string="Código de socio")
    image_dni = fields.Image("Imagen DNI")
    tipo_documento = fields.Selection([("dni", "DNI"), ("ce", "CE"),],string="Tipo documento", default="dni")