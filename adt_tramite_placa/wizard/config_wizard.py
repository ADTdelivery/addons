# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..models.tramite_placa import PARAM_DIAS_FINALIZADO


class AdtTramitePlacaConfig(models.TransientModel):
    """Parámetros del trámite de placa (se guardan en ir.config_parameter)."""
    _name = 'adt.tramite.placa.config'
    _description = 'Parámetros del trámite de placa'

    dias_finalizado = fields.Integer(
        string='Días en Finalizado', required=True,
        default=lambda self: self.env['adt.tramite.placa']._dias_finalizado(),
        help='Días que un trámite permanece en la columna Finalizado antes de pasar a Historial. '
             '0 = pasa en la siguiente revisión automática (cada hora).',
    )

    @api.constrains('dias_finalizado')
    def _check_dias_finalizado(self):
        if any(rec.dias_finalizado < 0 for rec in self):
            raise ValidationError(_('Los días en Finalizado no pueden ser negativos.'))

    def action_guardar(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(PARAM_DIAS_FINALIZADO, self.dias_finalizado)
        return {'type': 'ir.actions.act_window_close'}
