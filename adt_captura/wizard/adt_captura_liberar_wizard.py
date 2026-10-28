from odoo import api, fields, models, _

from ..models.adt_captura_record import LIBERACION_TIPOS


class AdtCapturaLiberarWizard(models.TransientModel):
    _name = 'adt.captura.liberar.wizard'
    _description = 'Wizard para Liberar Vehículo'

    liberacion_tipo = fields.Selection(LIBERACION_TIPOS, string='Tipo de Liberación', required=True)

    observaciones = fields.Text(string='Observaciones')

    def confirmar_liberacion(self):
        captura = self.env['adt.captura.record'].browse(self.env.context.get('active_id')).exists()
        if captura:
            captura.liberar_vehiculo(self.liberacion_tipo, self.observaciones)
        return {'type': 'ir.actions.act_window_close'}
