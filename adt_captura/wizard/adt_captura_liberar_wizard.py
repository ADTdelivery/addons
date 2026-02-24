from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

class AdtCapturaLiberarWizard(models.TransientModel):
    _name = 'adt.captura.liberar.wizard'
    _description = 'Wizard para Liberar Vehículo'

    liberacion_tipo = fields.Selection([
        ('refinanciamiento', 'Refinanciamiento'),
        ('pago_total', 'Pago Total del Pendiente')
    ], string='Tipo de Liberación', required=True)

    observaciones = fields.Text(string='Observaciones')

    def confirmar_liberacion(self):
        active_id = self.env.context.get('active_id')
        captura = self.env['adt.captura.record'].browse(active_id)
        if captura:
            # Log the state for debugging
            _logger.info('Searching for fleet.vehicle.state with name Recolocada')
            state = self.env['fleet.vehicle.state'].search([
                ('name', '=', 'Prestamo en Progreso')
            ], limit=1)
            _logger.info('Found state: %s', state)

            # Retrieve the vehicle_id from the captura record
            vehicle = captura.vehicle_id
            if vehicle:
                vehicle.write({
                    'state_id': state.id
                })

            captura.write({
                'state': 'liberado',
                'liberacion_tipo': self.liberacion_tipo,
                'observaciones': self.observaciones
            })
        return {'type': 'ir.actions.act_window_close'}
