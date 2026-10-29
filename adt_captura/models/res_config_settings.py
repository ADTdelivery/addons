# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .adt_captura_mora import PARAM_CUOTAS_VENCIDAS, PARAM_DIAS_MORA


class ResConfigSettingsCaptura(models.TransientModel):
    _inherit = 'res.config.settings'

    # Sin config_parameter: res.config.settings borra el parámetro cuando el entero es 0
    # y el valor inicial (data/config_parameter_data.xml) volvería en la próxima actualización.
    adt_captura_dias_mora_mayor_a = fields.Integer(
        string='Días de mora mayor a',
        help='Las cuotas vencidas del cronograma ponen la cuenta en captura solo si la cuota '
             'vencida más antigua tiene más de estos días. 0 = sin límite.',
    )
    adt_captura_cuotas_vencidas_mayor_a = fields.Integer(
        string='Cuotas vencidas mayor a',
        help='Las cuotas vencidas del cronograma ponen la cuenta en captura solo si son más '
             'de esta cantidad. 0 = sin límite.',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        filtro = self.env['adt.captura.mora']._filtro_captura()
        res.update(
            adt_captura_dias_mora_mayor_a=filtro['dias_mora_mayor_a'],
            adt_captura_cuotas_vencidas_mayor_a=filtro['cuotas_vencidas_mayor_a'],
        )
        return res

    def set_values(self):
        super().set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(PARAM_DIAS_MORA, str(max(self.adt_captura_dias_mora_mayor_a or 0, 0)))
        icp.set_param(PARAM_CUOTAS_VENCIDAS, str(max(self.adt_captura_cuotas_vencidas_mayor_a or 0, 0)))
