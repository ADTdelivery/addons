from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .calculo import calcular_cuotas, generar_cronograma, validar_parametros

CAMPOS_CALCULADOS = (
    'capital', 'interes_mensual', 'cuota_mensual', 'cuota_semanal',
    'cuota_diaria', 'total_credito', 'total_intereses',
)
CAMPOS_CRONOGRAMA = (
    'importe_financiar', 'tea', 'cuota_inicial', 'plazo_meses', 'frecuencia', 'fecha_inicio',
)


class FinancingSimulation(models.Model):
    _name = 'financing.simulation'
    _description = 'Simulación de financiamiento'
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Referencia', readonly=True, copy=False, default=lambda self: _('Nueva'))
    vehicle_id = fields.Many2one(
        'financing.vehicle', string='Vehículo', required=True, ondelete='restrict')
    # Parámetros del producto vigentes al momento de simular (la simulación
    # queda estable aunque luego cambie la configuración del vehículo).
    importe_financiar = fields.Float(
        string='Importe a financiar', digits=(16, 2), readonly=True)
    tea = fields.Float(string='TEA (decimal)', digits=(16, 6), readonly=True)
    cuota_inicial = fields.Float(string='Cuota inicial', digits=(16, 2), required=True)
    plazo_meses = fields.Integer(string='Plazo (meses)', required=True)

    capital = fields.Float(
        string='Capital', digits=(16, 2), compute='_compute_cuotas', store=True)
    interes_mensual = fields.Float(
        string='Interés mensual (im)', digits=(16, 10), compute='_compute_cuotas', store=True)
    cuota_mensual = fields.Float(
        string='C/ Mensual', digits=(16, 2), compute='_compute_cuotas', store=True)
    cuota_semanal = fields.Float(
        string='C/ Semanal', digits=(16, 2), compute='_compute_cuotas', store=True)
    cuota_diaria = fields.Float(
        string='C/ Diaria', digits=(16, 2), compute='_compute_cuotas', store=True)
    total_credito = fields.Float(
        string='Total del crédito', digits=(16, 2), compute='_compute_cuotas', store=True)
    total_intereses = fields.Float(
        string='Total de intereses', digits=(16, 2), compute='_compute_cuotas', store=True)

    partner_id = fields.Many2one(
        'res.partner', string='Cliente', ondelete='restrict', index=True)
    frecuencia = fields.Selection(
        [('mensual', 'Mensual'), ('semanal', 'Semanal'), ('diaria', 'Diaria')],
        string='Frecuencia de pago', default='mensual', required=True)
    fecha_inicio = fields.Date(string='Fecha de inicio del crédito')
    linea_ids = fields.One2many(
        'financing.simulation.line', 'simulation_id', string='Cronograma')
    cantidad_cuotas = fields.Integer(
        string='Cantidad de cuotas', compute='_compute_cantidad_cuotas')

    user_id = fields.Many2one(
        'res.users', string='Simulado por', default=lambda self: self.env.user,
        readonly=True, required=True)
    fecha = fields.Datetime(
        string='Fecha', default=fields.Datetime.now, readonly=True, required=True)
    origen = fields.Selection(
        [('odoo', 'Odoo'), ('app', 'App')], string='Origen', default='odoo', required=True)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        self.importe_financiar = self.vehicle_id.importe_financiar
        self.tea = self.vehicle_id.tea

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vehicle = self.env['financing.vehicle'].browse(vals.get('vehicle_id'))
            if vehicle:
                vals.setdefault('importe_financiar', vehicle.importe_financiar)
                vals.setdefault('tea', vehicle.tea)
            if vals.get('name', _('Nueva')) == _('Nueva'):
                vals['name'] = self.env['ir.sequence'].next_by_code('financing.simulation') or _('Nueva')
        simulaciones = super().create(vals_list)
        simulaciones._generar_cronograma()
        return simulaciones

    def write(self, vals):
        res = super().write(vals)
        if set(vals) & set(CAMPOS_CRONOGRAMA):
            self._generar_cronograma()
        return res

    @api.depends('linea_ids')
    def _compute_cantidad_cuotas(self):
        for rec in self:
            rec.cantidad_cuotas = len(rec.linea_ids)

    def action_imprimir_pdf(self):
        return self.env.ref(
            'adt_simulador_prospecto_financiamiento.action_report_simulacion').report_action(self)

    def _generar_cronograma(self):
        """Regenera las cuotas del cronograma (solo si hay fecha de inicio)."""
        for rec in self:
            rec.linea_ids.unlink()
            if not rec.fecha_inicio or validar_parametros(
                    rec.importe_financiar, rec.cuota_inicial, rec.tea, rec.plazo_meses):
                continue
            r = calcular_cuotas(rec.importe_financiar, rec.cuota_inicial, rec.tea, rec.plazo_meses)
            filas = generar_cronograma(
                rec.fecha_inicio, rec.frecuencia, rec.plazo_meses,
                r['cuota_mensual'], r['total_credito'])
            self.env['financing.simulation.line'].create(
                [dict(fila, simulation_id=rec.id) for fila in filas])

    @api.depends('importe_financiar', 'cuota_inicial', 'tea', 'plazo_meses')
    def _compute_cuotas(self):
        for rec in self:
            if validar_parametros(rec.importe_financiar, rec.cuota_inicial, rec.tea, rec.plazo_meses):
                resultado = dict.fromkeys(CAMPOS_CALCULADOS, 0.0)
            else:
                resultado = calcular_cuotas(
                    rec.importe_financiar, rec.cuota_inicial, rec.tea, rec.plazo_meses)
            for campo in CAMPOS_CALCULADOS:
                rec[campo] = resultado[campo]

    @api.constrains('importe_financiar', 'cuota_inicial', 'tea', 'plazo_meses')
    def _check_parametros(self):
        for rec in self:
            error = validar_parametros(
                rec.importe_financiar, rec.cuota_inicial, rec.tea, rec.plazo_meses)
            if error:
                raise ValidationError(error)
