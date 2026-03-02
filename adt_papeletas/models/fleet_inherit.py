# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FleetVehiclePapeletas(models.Model):
    _inherit = 'fleet.vehicle'

    adt_papeleta_ids = fields.One2many('adt.papeleta', 'vehicle_id', string='Papeletas')

    def action_new_adt_papeleta(self):
        self.ensure_one()
        return {
            'name': 'Crear Papeleta',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.papeleta',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': {
                'default_vehicle_id': self.id,
            },
        }
