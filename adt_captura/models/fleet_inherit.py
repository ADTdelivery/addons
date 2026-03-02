# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class FleetVehicleCapturas(models.Model):
    _inherit = 'fleet.vehicle'

    adt_captura_ids = fields.One2many('adt.captura.record', 'vehicle_id', string='Capturas')

    def action_new_adt_captura(self):
        self.ensure_one()
        # Try to find a commercial account (cuenta) linked to this vehicle to prefill the capture
        cuenta = self.env['adt.comercial.cuentas'].search([('vehiculo_id', '=', self.id)], limit=1)
        ctx = {}
        if cuenta:
            ctx = {'default_cuenta_id': cuenta.id}
        else:
            # If no cuenta found, pass the vehicle id so user can complete the form
            ctx = {'default_vehicle_id': self.id}

        return {
            'name': 'Nueva Captura',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.record',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }
