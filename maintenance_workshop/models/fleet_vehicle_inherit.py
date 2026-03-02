# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    work_order_ids = fields.One2many('maintenance.work.order', 'vehicle_id', string='Órdenes de Taller')

    def action_new_work_order(self):
        self.ensure_one()
        # Build sensible defaults: prefer driver_id if available
        defaults = {'default_vehicle_id': self.id}

        # Check if this model has a driver_id field and use its comodel to decide
        driver_field = self._fields.get('driver_id')
        if driver_field and getattr(self, 'driver_id'):
            try:
                comodel = driver_field.comodel_name
            except Exception:
                comodel = False

            if comodel == 'res.partner':
                defaults['default_client_id'] = self.driver_id.id
            elif comodel == 'res.users':
                defaults['default_mechanic_id'] = self.driver_id.id

        # Fallback to partner_id for client if not set
        if 'default_client_id' not in defaults and getattr(self, 'partner_id', False):
            defaults['default_client_id'] = self.partner_id.id

        return {
            'name': _('Nueva Orden de Taller'),
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.work.order',
            'view_mode': 'form',
            'view_id': False,
            'target': 'current',
            'context': defaults,
        }
