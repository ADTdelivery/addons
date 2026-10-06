from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .calculo import CARGO_DIARIO_DEFECTO, calcular_cuotas


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
    cuota_inicial = fields.Float(
        string='Cuota inicial', digits=(16, 2), required=True, default=0.0,
        help='Cuota inicial que se usa en todas las simulaciones de este producto.')
    cargo_diario = fields.Float(
        string='Cargo diario', digits=(16, 2), required=True, default=CARGO_DIARIO_DEFECTO,
        help='Cargo en soles por día que se propone en las simulaciones de este producto.')
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

    @api.constrains('importe_financiar', 'tea', 'cuota_inicial', 'cargo_diario')
    def _check_valores(self):
        for rec in self:
            if rec.importe_financiar <= 0:
                raise ValidationError(_('El importe a financiar debe ser mayor que cero.'))
            if rec.tea <= 0:
                raise ValidationError(_('La TEA debe ser mayor que cero.'))
            if rec.cargo_diario < 0:
                raise ValidationError(_('El cargo diario no puede ser negativo.'))
            if rec.cuota_inicial < 0:
                raise ValidationError(_('La cuota inicial no puede ser negativa.'))
            if rec.cuota_inicial >= rec.importe_financiar:
                raise ValidationError(_('La cuota inicial debe ser menor que el importe a financiar.'))

    def calcular(self, plazo_meses, cargo_diario=None):
        """Ejecuta la cadena de fórmulas con los parámetros del producto."""
        self.ensure_one()
        return calcular_cuotas(self.importe_financiar, self.cuota_inicial, self.tea,
                               plazo_meses, self.cargo_diario if cargo_diario is None else cargo_diario)
