# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """El tracking ahora sigue a adt.tramite.placa en lugar de procedure_plate: volver a sincronizar."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['adt.moto.tracking'].search([])._sync_estado_placa()
