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

    # Campos relacionados para mostrar en la pestaña de flota
    x_facturacion_motor = fields.Char(
        related='x_id_facturacion.x_facturacion_motor',
        string='Motor',
        readonly=True,
    )
    x_facturacion_ano_modelo = fields.Integer(
        related='x_id_facturacion.x_facturacion_ano_modelo',
        string='Año del Modelo',
        readonly=True,
    )
    x_facturacion_color = fields.Char(
        related='x_id_facturacion.x_facturacion_color',
        string='Color',
        readonly=True,
    )
    x_facturacion_dua = fields.Char(
        related='x_id_facturacion.x_facturacion_dua',
        string='DUA',
        readonly=True,
    )
    x_facturacion_adjunto_factura = fields.Binary(
        related='x_id_facturacion.x_facturacion_adjunto_factura',
        string='Factura Adjunta',
        readonly=True,
    )
    x_facturacion_adjunto_factura_nombre = fields.Char(
        related='x_id_facturacion.x_facturacion_adjunto_factura_nombre',
        string='Nombre Factura',
        readonly=True,
    )
