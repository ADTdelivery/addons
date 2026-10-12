# -*- coding: utf-8 -*-
from odoo import fields, models


class AdtMotoTrackingTaller(models.Model):
    """Lugares/proveedores donde se manda a poner la fibra (PP, VES, SJM, ...)."""
    _name = 'adt.moto.tracking.taller'
    _description = 'Taller de fibra'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    codigo = fields.Char(string='Abreviatura', help='Texto corto que se muestra en el kanban (PP, VES, SJM).')
    sequence = fields.Integer(string='Secuencia', default=10)
    partner_id = fields.Many2one('res.partner', string='Proveedor')
    direccion = fields.Char(string='Dirección')
    sla_horas = fields.Float(
        string='SLA (horas)',
        help='Si se informa, reemplaza al SLA de la etapa "Fibra" para las motos enviadas a este taller.',
    )
    active = fields.Boolean(default=True)
