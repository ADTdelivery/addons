# -*- coding: utf-8 -*-
"""
Extiende mobile.notification (definido en adt_comercial) con el tipo
MAINTENANCE, para que las notificaciones de mantenimiento preventivo queden
también en el feed de notificaciones in-app de la app (con deep_link
poblado), no solo como push.
"""
from odoo import fields, models


class MobileNotificationMantenimiento(models.Model):
    _inherit = 'mobile.notification'

    notification_type = fields.Selection(
        selection_add=[('MAINTENANCE', 'Mantenimiento Preventivo')],
        ondelete={'MAINTENANCE': 'set default'},
    )
