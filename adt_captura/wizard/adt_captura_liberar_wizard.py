from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AdtCapturaLiberarWizard(models.TransientModel):
    _name = 'adt.captura.liberar.wizard'
    _description = 'Wizard para Liberar Vehículo'

    liberacion_tipo = fields.Selection([
        ('refinanciamiento', 'Refinanciamiento'),
        ('pago_total', 'Pago Total del Pendiente'),
        ('pago_papeleta_total', 'Pago Total de la papeleta'),
        ('pago_fraccionado', 'Pago Fraccionado de la papeleta'),
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

            # If there is a pending papeleta for this vehicle, handle depending on liberacion_tipo
            try:
                papeleta = None
                if vehicle:
                    papeleta = self.env['adt.papeleta'].search([
                        ('vehicle_id', '=', vehicle.id),
                        ('state', '!=', 'pagado')
                    ], order='fecha_vencimiento_final asc, id asc', limit=1)

                    # If the selected type is NOT pago_fraccionado, mark the found papeleta as pagado
                    if papeleta and self.liberacion_tipo != 'pago_fraccionado':
                        today = fields.Date.context_today(self)
                        papeleta.write({
                            'state': 'pagado',
                            'fecha_pago': today,

                        })
                        try:
                            papeleta.message_post(body=_('Papeleta marcada como <b>Pagado</b> al liberar el vehículo por %s') % (self.env.user.display_name,))
                        except Exception:
                            _logger.exception('Failed to post chatter message for papeleta %s', papeleta.id)
            except Exception:
                _logger.exception('Error while updating papeleta for vehicle %s', getattr(vehicle, 'id', None))

            # Update captura regardless of type
            # Build data to write to captura. If the liberacion is a payment
            # (fraccionado o pago total), also unset `capturado` so quede liberada.
            captura_vals = {
                'state': 'liberado',
                'liberacion_tipo': self.liberacion_tipo,
                'observaciones': self.observaciones,
            }
            if self.liberacion_tipo in ('pago_fraccionado', 'pago_papeleta_total'):
                captura_vals['capturado'] = False

            captura.write(captura_vals)

            # If payment is fraccionado, open the papeleta form in a modal so user can manage fractions
            if self.liberacion_tipo == 'pago_fraccionado':
                # If a pending papeleta exists, open it; otherwise open a create form with defaults
                view = self.env.ref('adt_papeletas.view_adt_papeleta_form', False)
                if papeleta:
                    action = {
                        'type': 'ir.actions.act_window',
                        'name': _('Papeleta'),
                        'res_model': 'adt.papeleta',
                        'res_id': papeleta.id,
                        'view_mode': 'form',
                        'views': [(view.id, 'form')] if view else None,
                        'target': 'new',
                    }
                else:
                    today = fields.Date.context_today(self)
                    ctx = dict(self.env.context or {})
                    ctx.update({
                        'default_vehicle_id': vehicle.id if vehicle else False,
                        'default_payment_method': 'fraccionado',
                        'default_fecha_papeleta': today,
                    })
                    action = {
                        'type': 'ir.actions.act_window',
                        'name': _('Nueva Papeleta'),
                        'res_model': 'adt.papeleta',
                        'view_mode': 'form',
                        'views': [(view.id, 'form')] if view else None,
                        'target': 'new',
                        'context': ctx,
                    }
                return action
        return {'type': 'ir.actions.act_window_close'}
