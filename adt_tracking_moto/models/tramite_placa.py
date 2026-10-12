# -*- coding: utf-8 -*-
from odoo import api, models


class AdtTramitePlaca(models.Model):
    """Cada cambio del trámite de placa se refleja en el tracking de la moto."""
    _inherit = 'adt.tramite.placa'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._adt_sync_tracking()
        return records

    def write(self, vals):
        vehiculos_previos = self.mapped('vehicle_id')
        res = super().write(vals)
        if {'state', 'vehicle_id'} & vals.keys():
            self._adt_sync_tracking(vehiculos_previos)
        return res

    def _adt_sync_tracking(self, vehiculos_extra=None):
        vehiculos = self.mapped('vehicle_id') | (vehiculos_extra or self.env['fleet.vehicle'])
        self.env['adt.moto.tracking'].sudo().search([('vehicle_id', 'in', vehiculos.ids)])._sync_estado_placa()
