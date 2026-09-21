from odoo import _, fields, models

from ..models.financing_simulation import CAMPOS_CALCULADOS


class FinancingSimulationWizard(models.TransientModel):
    _name = 'financing.simulation.wizard'
    _description = 'Asistente: Simular cuota'

    vehicle_id = fields.Many2one(
        'financing.vehicle', string='Vehículo', required=True,
        domain=[('active', '=', True)])
    importe_financiar = fields.Float(
        related='vehicle_id.importe_financiar', string='Importe a financiar', digits=(16, 2))
    tea = fields.Float(related='vehicle_id.tea', string='TEA (decimal)', digits=(16, 6))
    cuota_inicial = fields.Float(string='Cuota inicial', digits=(16, 2), required=True)
    plazo_meses = fields.Integer(string='Plazo (meses)', required=True)

    partner_id = fields.Many2one('res.partner', string='Cliente')
    frecuencia = fields.Selection(
        [('mensual', 'Mensual'), ('semanal', 'Semanal'), ('diaria', 'Diaria')],
        string='Frecuencia de pago', default='mensual', required=True)
    fecha_inicio = fields.Date(string='Fecha de inicio del crédito')

    calculado = fields.Boolean(readonly=True)
    capital = fields.Float(string='Capital', digits=(16, 2), readonly=True)
    interes_mensual = fields.Float(string='Interés mensual (im)', digits=(16, 10), readonly=True)
    cuota_mensual = fields.Float(string='C/ Mensual', digits=(16, 2), readonly=True)
    cuota_semanal = fields.Float(string='C/ Semanal', digits=(16, 2), readonly=True)
    cuota_diaria = fields.Float(string='C/ Diaria', digits=(16, 2), readonly=True)
    total_credito = fields.Float(string='Total del crédito', digits=(16, 2), readonly=True)
    total_intereses = fields.Float(string='Total de intereses', digits=(16, 2), readonly=True)
    simulation_id = fields.Many2one('financing.simulation', string='Simulación', readonly=True)
    cronograma_ids = fields.One2many(
        related='simulation_id.linea_ids', string='Cronograma', readonly=True)
    cantidad_cuotas = fields.Integer(
        related='simulation_id.cantidad_cuotas', string='Cantidad de cuotas')

    def action_calcular(self):
        self.ensure_one()
        simulacion = self.env['financing.simulation'].create({
            'vehicle_id': self.vehicle_id.id,
            'cuota_inicial': self.cuota_inicial,
            'plazo_meses': self.plazo_meses,
            'partner_id': self.partner_id.id,
            'frecuencia': self.frecuencia,
            'fecha_inicio': self.fecha_inicio,
            'origen': 'odoo',
        })
        vals = {campo: simulacion[campo] for campo in CAMPOS_CALCULADOS}
        vals.update(calculado=True, simulation_id=simulacion.id)
        self.write(vals)
        # Muestra el aviso y luego recarga este mismo formulario con el resultado.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Simulación generada'),
                'message': _('Se generó la simulación %s correctamente.') % simulacion.name,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            },
        }

    def action_imprimir(self):
        self.ensure_one()
        return self.simulation_id.action_imprimir_pdf()

    def action_nuevo(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'adt_simulador_prospecto_financiamiento.action_financing_simulation_wizard')
