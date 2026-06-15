# -*- coding: utf-8 -*-
from odoo import models, fields


class AdtFacturacionTipo(models.Model):
    _name = 'adt.facturacion.tipo'
    _description = 'Tipo de Facturación'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    es_vehiculo = fields.Boolean(
        string='Crea Vehículo en Flota',
        default=False,
        help='Si está activo, al guardar la factura se crea/actualiza un registro en flota.',
    )
