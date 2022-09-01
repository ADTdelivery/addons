from odoo import models, fields, api


class FieldModels(models.Model):
    _inherit = 'fleet.vehicle'

    contrato_vehicular = fields.Binary(string="Contrato vehicular")


class FleetGPS(models.Model):
    _inherit = 'fleet.vehicle'

    x_imei = fields.Char(string="IMEI")
    x_chip = fields.Char(string='Chip')
    x_puerto_gps1 = fields.Selection([('5001', '5001 / resume123456'),
                                      ('5002', '5002 / supplyelec123456'),
                                      ('5013', '5013 / 9410000'),
                                      ], 'Reanudar GPS')
    x_puerto_gps2 = fields.Selection([
        ('5001', '5001 / stop123456'),
        ('5002', '5002 / stopelec123456'),
        ("5013", '5013 / 9400000'),
    ], 'Detener GPS')

    numero_celular = fields.Char(string="Celular")
    puerto = fields.Char(string="Puerto")


class ModelVehicle(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type = fields.Selection([
        ('car', 'Automóvil'),
        ('motorcycle', 'Motocicleta'),
        ('bike', 'Bicicleta'),
        ('mototaxi', 'Mototaxi'),
    ])
