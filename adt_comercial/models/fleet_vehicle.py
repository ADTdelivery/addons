from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTFleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    cuenta_ids = fields.One2many(
        'adt.comercial.cuentas', 'vehiculo_id', string="Cuentas")

    disponible = fields.Boolean(string='Disponible', default=True)

    def action_new_cuenta(self):
        self.ensure_one()
        ctx = {
            'default_vehiculo_id': self.id,
        }
        # set default partner from driver if available
        if getattr(self, 'driver_id', False):
            ctx['default_partner_id'] = self.driver_id.id
        return {
            'name': 'Crear Cuenta',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.comercial.cuentas',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }
