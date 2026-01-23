from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTResPartner(models.Model):
    _inherit = 'res.partner'

    codigo_socio = fields.Char(string="Código de socio")
    image_dni = fields.Image("Imagen DNI")
    tipo_documento = fields.Selection([("dni", "DNI"), ("ce", "CE"),],string="Tipo documento", default="dni")


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    bill_count = fields.Integer(string="Bills", compute="_compute_bill_count")

    def _compute_bill_count(self):
        for rec in self:
            rec.bill_count = 0
