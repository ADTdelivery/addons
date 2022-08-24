from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTAccountPayment(models.Model):
   _inherit = 'account.payment'
   
   cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")