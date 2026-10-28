# -*- coding: utf-8 -*-
"""Vincula a las capturas activas las papeletas SAT que el SAT muestra pendientes."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Captura = env['adt.captura.record']
    for captura in Captura.search([('state', 'in', ('capturado', 'disolucion_contrato')),
                                   ('papeleta_sat_ids', '=', False)]):
        papeletas = Captura._papeletas_sat_pendientes(captura.cuenta_id)
        if papeletas:
            captura.papeleta_sat_ids = [(6, 0, papeletas.ids)]
