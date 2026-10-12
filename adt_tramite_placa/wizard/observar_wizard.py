# -*- coding: utf-8 -*-
from odoo import fields, models


class AdtTramitePlacaObservarWizard(models.TransientModel):
    _name = 'adt.tramite.placa.observar.wizard'
    _description = 'Observar trámite de placa'

    tramite_id = fields.Many2one('adt.tramite.placa', string='Trámite', required=True)
    motivo = fields.Text(string='Motivo', required=True)

    def action_confirmar(self):
        self.ensure_one()
        self.tramite_id._observar(self.motivo)
        return {'type': 'ir.actions.act_window_close'}
