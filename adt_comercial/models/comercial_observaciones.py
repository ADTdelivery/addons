from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTComercialObservaciones(models.Model):
    _name = 'adt.comercial.observaciones'
    _description = 'ADT Módulo comercial - Observaciones'

    fecha = fields.Date(string="Fecha", default=fields.Date.today)
    comentario = fields.Text(string='Comentario')
    attachment_ids = fields.Many2many("ir.attachment", string="Adjuntos")
    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")
