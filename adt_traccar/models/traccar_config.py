# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    traccar_url = fields.Char(
        string='Traccar URL',
        config_parameter='adt_traccar.url',
        default='http://localhost:8082',
        help='URL base del servidor Traccar, e.g. http://localhost:8082',
    )
    traccar_email = fields.Char(
        string='Traccar Email',
        config_parameter='adt_traccar.email',
        help='Email del usuario administrador de Traccar',
    )
    traccar_password = fields.Char(
        string='Traccar Password',
        config_parameter='adt_traccar.password',
        help='Contraseña del usuario administrador de Traccar',
    )
