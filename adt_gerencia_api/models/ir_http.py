# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request

from .gerencia_token import GRUPO


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Agrega moduloAdmin: True si el usuario tiene acceso a la app de gerencia.

        Lo devuelve /web/session/authenticate (y la carga del cliente web), así la app
        sabe al iniciar sesión si debe mostrar la sección de gerencia. No confundir con
        `is_admin` de Odoo, que indica administrador del sistema.
        """
        info = super().session_info()
        user = request.env.user
        info['moduloAdmin'] = bool(user and user._is_internal() and user.has_group(GRUPO))
        return info
