from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTAccountPaymentV2(models.Model):
   _inherit = 'account.payment'
   
   cuota_id = fields.Many2one('adt.comercial.cuotas.v2', string="Id de cuota")