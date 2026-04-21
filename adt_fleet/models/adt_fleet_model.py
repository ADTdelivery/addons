# This file will contain the models for the adt_fleet module
# -*- coding: utf-8 -*-
from odoo import models, fields

class AdtFleetVehicleModel(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type = fields.Selection(
        selection_add=[('mototaxi', 'Mototaxi')],
        ondelete={'mototaxi': lambda recs: recs.write({'vehicle_type': False})},
    )


class FieldModels(models.Model):
    _inherit = 'fleet.vehicle'

    tarjeta_propiedad_attachment = fields.Binary(
        string="Tarjeta de Propiedad (PDF/Imagen)",
        attachment=True,
        help="Adjunte la Tarjeta de Propiedad en formato PDF o imagen."
    )
    chip_gnv_attachment = fields.Binary(
        string="Chip GNV (PDF/Imagen)",
        attachment=True,
        help="Adjunte el documento del Chip GNV en formato PDF o imagen."
    )
    soat_attachment = fields.Binary(
        string="SOAT (PDF/Imagen)",
        attachment=True,
        help="Adjunte el SOAT en formato PDF o imagen."
    )

    tarjeta_propiedad_filename = fields.Char(string="Nombre archivo Tarjeta")
    chip_gnv_filename = fields.Char(string="Nombre archivo Chip GNV")
    soat_filename = fields.Char(string="Nombre archivo SOAT")