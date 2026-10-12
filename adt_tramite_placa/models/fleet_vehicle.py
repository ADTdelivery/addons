# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .tramite_placa import ESTADOS_TRAMITE, plate_is_ready


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    adt_tramite_placa_id = fields.Many2one(
        'adt.tramite.placa', string='Trámite de placa', compute='_compute_adt_tramite_placa_id')
    adt_tramite_placa_state = fields.Selection(
        ESTADOS_TRAMITE, string='Estado trámite placa', compute='_compute_adt_tramite_placa_id')

    def _adt_tramites_placa(self):
        return self.env['adt.tramite.placa'].sudo().search([('vehicle_id', 'in', self.ids)])

    def _compute_adt_tramite_placa_id(self):
        por_vehiculo = {t.vehicle_id.id: t for t in self._adt_tramites_placa()}
        for vehicle in self:
            tramite = por_vehiculo.get(vehicle.id)
            vehicle.adt_tramite_placa_id = tramite.id if tramite else False
            vehicle.adt_tramite_placa_state = tramite.state if tramite else False

    def _adt_crear_tramite_placa(self, solo_facturados=True):
        """Crea el trámite (Pendiente) de las motos sin placa real que aún no lo tienen.

        Por defecto solo las que vienen de una factura; la carga de existentes pasa solo_facturados=False.
        """
        con_tramite = self._adt_tramites_placa().vehicle_id
        candidatos = self.filtered(
            lambda v: (v.x_id_facturacion or not solo_facturados)
            and v not in con_tramite and not plate_is_ready(v.license_plate))
        return self.env['adt.tramite.placa'].sudo().create([{'vehicle_id': v.id} for v in candidatos])

    @api.model_create_multi
    def create(self, vals_list):
        vehicles = super().create(vals_list)
        vehicles._adt_crear_tramite_placa()
        return vehicles

    def action_ver_adt_tramite_placa(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trámite de placa'),
            'res_model': 'adt.tramite.placa',
            'res_id': self.adt_tramite_placa_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
