# -*- coding: utf-8 -*-

from odoo import models, fields


class FleetVehicleFacturacion(models.Model):
    _inherit = 'fleet.vehicle'

    x_motor_sn = fields.Char(string='Motor')
    x_dua = fields.Char(string='DUA')
    x_factura_adjunto = fields.Binary(string='Factura Adjunta', attachment=True)
    x_factura_adjunto_nombre = fields.Char(string='Nombre Factura')
    x_id_facturacion = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        readonly=True,
        copy=False,
    )

    def action_ver_factura(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Factura',
            'res_model': 'account.move',
            'res_id': self.x_id_facturacion.id,
            'view_mode': 'form',
            'target': 'current',
        }
