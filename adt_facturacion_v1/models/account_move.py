# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_facturacion_chasis = fields.Char(
        string='Chasis',
    )
    x_facturacion_modelo_id = fields.Many2one(
        comodel_name='fleet.vehicle.model',
        string='Modelo',
    )
    x_facturacion_motor = fields.Char(
        string='Motor',
    )
    x_facturacion_ano_modelo = fields.Integer(
        string='Año del Modelo',
    )
    x_facturacion_color = fields.Char(
        string='Color',
    )
    x_facturacion_dua = fields.Char(
        string='DUA',
    )
    x_facturacion_adjunto_factura = fields.Binary(
        string='Adjuntar Factura',
        attachment=True,
    )
    x_facturacion_adjunto_factura_nombre = fields.Char(
        string='Nombre Factura',
    )
    x_facturacion_vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Vehículo',
        readonly=True,
        copy=False,
    )

    def _sync_fleet_vehicle(self):
        """Crea o actualiza el registro en fleet.vehicle con los datos del vehículo."""
        for move in self:
            if not move.x_facturacion_modelo_id:
                continue

            vehicle_vals = {
                'model_id': move.x_facturacion_modelo_id.id,
                'name': move.x_facturacion_modelo_id.name,
                'vin_sn': move.x_facturacion_chasis,
                'x_motor_sn': move.x_facturacion_motor,
                'model_year': move.x_facturacion_ano_modelo,
                'color': move.x_facturacion_color,
                'x_dua': move.x_facturacion_dua,
                'x_factura_adjunto': move.x_facturacion_adjunto_factura,
                'x_factura_adjunto_nombre': move.x_facturacion_adjunto_factura_nombre,
                'x_id_facturacion': move.id,
            }

            if move.x_facturacion_vehicle_id:
                move.x_facturacion_vehicle_id.write(vehicle_vals)
            else:
                vehicle = self.env['fleet.vehicle'].create(vehicle_vals)
                move.x_facturacion_vehicle_id = vehicle.id

    def action_ver_vehiculo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vehículo',
            'res_model': 'fleet.vehicle',
            'res_id': self.x_facturacion_vehicle_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_fleet_vehicle()
        return records

    def write(self, vals):
        res = super().write(vals)
        fleet_fields = {
            'x_facturacion_modelo_id', 'x_facturacion_chasis', 'x_facturacion_motor',
            'x_facturacion_ano_modelo', 'x_facturacion_color', 'x_facturacion_dua',
            'x_facturacion_adjunto_factura', 'x_facturacion_adjunto_factura_nombre',
        }
        if fleet_fields.intersection(vals.keys()):
            self._sync_fleet_vehicle()
        return res
