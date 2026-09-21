from odoo import fields, models


class FinancingSimulationLine(models.Model):
    _name = 'financing.simulation.line'
    _description = 'Cuota del cronograma de simulación'
    _order = 'simulation_id, numero'

    simulation_id = fields.Many2one(
        'financing.simulation', string='Simulación', required=True, ondelete='cascade', index=True)
    numero = fields.Integer(string='N°', required=True)
    fecha = fields.Date(string='Fecha de pago', required=True)
    cuota = fields.Float(string='Cuota', digits=(16, 2), required=True)
    saldo = fields.Float(string='Saldo', digits=(16, 2), required=True)
