# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PapeletaSatProgramaFinanciera(models.Model):
    """Varias financieras por programa SAT (adt_papeletas no conoce el catálogo comercial)."""
    _inherit = 'adt.papeleta.sat.programa'

    financiera_ids = fields.Many2many('adt.comercial.financiera', 'adt_papeleta_sat_programa_financiera_rel',
                                      'programa_id', 'financiera_id', string='Financieras',
                                      help='Vehículos con una cuenta comercial de alguna de estas financieras.')

    @api.depends('financiera_ids')
    def _compute_total_placas(self):
        return super()._compute_total_placas()

    def _financiera_codigos(self):
        return [c for c in self.financiera_ids.mapped('code') if c]
