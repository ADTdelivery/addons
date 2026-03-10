# This file will contain the models for the adt_fleet module
# -*- coding: utf-8 -*-
from odoo import models, fields


class AdtFleetVehicleModel(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type = fields.Selection(
        selection_add=[('mototaxi', 'Mototaxi')],
        ondelete={'mototaxi': lambda recs: recs.write({'vehicle_type': False})},
    )
