from odoo import api, fields, models

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
            captura.write({
                'state': 'liberado',
                'liberacion_tipo': self.liberacion_tipo,
                'observaciones': self.observaciones
            })
        return {'type': 'ir.actions.act_window_close'}
