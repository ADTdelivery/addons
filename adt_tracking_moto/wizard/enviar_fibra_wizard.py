# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdtMotoTrackingFibraWizard(models.TransientModel):
    _name = 'adt.moto.tracking.fibra.wizard'
    _description = 'Enviar motos a fibra'

    tracking_ids = fields.Many2many('adt.moto.tracking', string='Motos', required=True)
    taller_id = fields.Many2one('adt.moto.tracking.taller', string='Taller de fibra', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'adt.moto.tracking':
            res['tracking_ids'] = [(6, 0, self.env.context.get('active_ids', []))]
        return res

    def action_confirmar(self):
        self.ensure_one()
        self.tracking_ids.write({
            'etapa_id': self.env['adt.moto.tracking']._etapa('fibra').id,
            'taller_fibra_id': self.taller_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}
