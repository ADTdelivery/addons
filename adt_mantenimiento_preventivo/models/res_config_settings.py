# -*- coding: utf-8 -*-
from odoo import fields, models

from .mantenimiento_regla import HORAS_DISPONIBLES

HORAS_SELECTION = [(h, h) for h in HORAS_DISPONIBLES]


class ResConfigSettingsMantenimientoPreventivo(models.TransientModel):
    _inherit = 'res.config.settings'

    adt_mantenimiento_dias_sin_reporte = fields.Integer(
        string='Días sin reportar GPS para alertar',
        config_parameter='adt_mantenimiento.dias_sin_reporte',
        default=3,
        help='Si un vehículo no reporta posición GPS por esta cantidad de '
             'días, se publica una alerta en su ficha (chatter) para el '
             'administrador de flota.',
    )
    adt_mantenimiento_horario_ventana_inicio = fields.Selection(
        selection=HORAS_SELECTION,
        string='Ventana horaria - Inicio',
        config_parameter='adt_mantenimiento.horario_ventana_inicio',
        default='09:00',
        help='Hora Lima usada para repartir uniformemente las notificaciones '
             'del día cuando una regla no define "Horarios sugeridos" (o '
             'define menos horarios de los necesarios).',
    )
    adt_mantenimiento_horario_ventana_fin = fields.Selection(
        selection=HORAS_SELECTION,
        string='Ventana horaria - Fin',
        config_parameter='adt_mantenimiento.horario_ventana_fin',
        default='19:00',
        help='Hora Lima de fin de la ventana horaria por defecto.',
    )
