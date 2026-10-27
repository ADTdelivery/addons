# -*- coding: utf-8 -*-
"""Indicadores de la flota para gerencia (acción JS: adt_flota_360_indicadores).

Cuatro recuadros con los mismos cálculos y filtros que la consulta de vehículos, así
cada cifra coincide con la lista que abre al hacer clic.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .flota_360 import MAX_ANALISIS

GRUPO_GERENCIA = 'adt_comercial.group_access_adt_comercial_gerencia'


class AdtFlota360Indicadores(models.AbstractModel):
    _inherit = 'adt.flota360'

    @api.model
    def indicadores(self, financiera=None, estado=None, clientes=None):
        if not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(_('Solo gerencia puede ver los indicadores de la flota.'))
        vehiculos = self.env['fleet.vehicle'].search([], limit=MAX_ANALISIS)
        f = self._filtrar(self._resumenes(vehiculos), financiera, estado, clientes=clientes or 'todos')
        resumenes = f['resumenes']
        modulo = lambda r, key: next((m for m in r['modulos'] if m['key'] == key), {})
        con = lambda filtro: [r for r in resumenes if filtro in r['filtros']]

        papeletas = con('papeletas')
        deudores = con('mora')
        return {
            'fecha': fields.Date.to_string(fields.Date.context_today(self)),
            'total': len(resumenes),
            'financieras': f['financieras'],
            'estados': f['estados'],
            'clientes': f['clientes'],
            'papeletas': {
                'monto': sum(modulo(r, 'papeletas').get('monto', 0.0) for r in papeletas),
                'vehiculos': len(papeletas),
                'coactiva': len(con('coactiva')),
            },
            'gps': {'vehiculos': len(con('gps_off'))},
            'deuda': {
                'monto': sum(modulo(r, 'cuentas').get('vencido', 0.0) for r in deudores),
                'vehiculos': sum(1 for r in deudores if modulo(r, 'cuentas').get('vencido')),
            },
            'mora': {
                'monto': sum(modulo(r, 'cuentas').get('mora', 0.0) for r in deudores),
                'vehiculos': sum(1 for r in deudores if modulo(r, 'cuentas').get('mora')),
            },
        }
