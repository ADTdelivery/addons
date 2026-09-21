from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .calculo import calcular_cuotas


class FinancingVehicle(models.Model):
    _name = 'financing.vehicle'
    _description = 'Producto financiable'
    _order = 'name'

    name = fields.Char(string='Vehículo', required=True)
    importe_financiar = fields.Float(
        string='Importe a financiar', digits=(16, 2), required=True)
    tea = fields.Float(
        string='TEA (decimal)', digits=(16, 6), required=True,
        help='Tasa efectiva anual en decimal. Ej.: 26.82% = 0.2682')
    tea_porcentaje = fields.Float(
        string='TEA (%)', digits=(16, 4), compute='_compute_tea_porcentaje')
    active = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Ya existe un producto financiable con ese nombre.'),
    ]

    @api.depends('tea')
    def _compute_tea_porcentaje(self):
        for rec in self:
            rec.tea_porcentaje = rec.tea * 100

    @api.constrains('importe_financiar', 'tea')
    def _check_valores(self):
        for rec in self:
            if rec.importe_financiar <= 0:
                raise ValidationError(_('El importe a financiar debe ser mayor que cero.'))
            if rec.tea <= 0:
                raise ValidationError(_('La TEA debe ser mayor que cero.'))

    def calcular(self, cuota_inicial, plazo_meses):
        """Ejecuta la cadena de fórmulas con los parámetros del producto."""
        self.ensure_one()
        return calcular_cuotas(self.importe_financiar, cuota_inicial, self.tea, plazo_meses)
