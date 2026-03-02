# -*- coding: utf-8 -*-
from odoo import http


class AdtTvsMantenimientoController(http.Controller):
    @http.route('/adt_tvs_mantenimiento/hello', auth='public', type='http')
    def hello(self, **kw):
        return "ADT TVS Mantenimiento module is installed."
