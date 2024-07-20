from odoo import models, fields, api


class FieldModels(models.Model):
    _inherit = 'fleet.vehicle'


    #tracking=True,
    contrato_vehicular = fields.Binary(string="Contrato vehicular")
    license_plate = fields.Char(tracking=False,
                                help='License plate number of the vehicle (i = plate number for a car)')

    tmp_field = fields.Char(string="prueba")
    x_fleet_tarjeta_propiedad = fields.Binary(string="Tarjeta de propiedad")
    x_soat = fields.Binary(string="Tarjeta SOAT")
    x_licencia_final = fields.Binary(string="Licencia")

    num_months_between_dates = fields.Integer(string='Number of Months', compute='_compute_num_months_between_dates')

    @api.depends('cuenta_ids.cuota_ids.fecha_cronograma')
    def _compute_num_months_between_dates(self):
        for vehicle in self:
            first_date = last_date = None
            for cuenta in vehicle.cuenta_ids:
                if cuenta.partner_id == vehicle.driver_id:
                    cuota_dates = cuenta.cuota_ids.mapped('fecha_cronograma')
                    if cuota_dates:
                        cuota_dates.sort()
                        first_date = cuota_dates[0]
                        last_date = cuota_dates[-1]
                        break
            if first_date and last_date:
                num_months = relativedelta(last_date, first_date).years * 12 + relativedelta(last_date, first_date).months
                vehicle.num_months_between_dates = num_months
            else:
                vehicle.num_months_between_dates = 0


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



class ModelPapeleta(models.Model):
    _inherit = 'fleet.vehicle'

    infraccion_id = fields.One2many('infraccion.attributes.model', 'fleet_id', string="Papeletas")

    def agregar_papeleta(self):
        return {
            'name': 'Registrar papeleta',
            'res_model': 'infraccion.attributes.model',
            'view_mode': 'form',
            'context': {
                'active_model': 'fleet.vehicle',
                # 'active_ids': self.ids,
                # 'default_amount': self.monto,
                # 'default_fecha': date.today(),

                'default_fleet_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }
