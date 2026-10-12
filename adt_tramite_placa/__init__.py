# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

from . import models
from . import wizard


def post_init_hook(cr, registry):
    """Crea el trámite de las motos facturadas que ya existían sin placa."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    vehiculos = env['fleet.vehicle'].search([('x_id_facturacion', '!=', False)])
    vehiculos._adt_crear_tramite_placa()
