# -*- coding: utf-8 -*-
"""Las apps móviles envían Content-Type: application/json en todas las llamadas.

Odoo 15 decide si una petición es JSON-RPC solo por ese header (Root.get_request),
antes de saber qué ruta se llamó, y entonces rechaza las rutas type='http' de esta
API. Para las rutas /api/gerencia/ se crea siempre una petición HTTP normal: el
controlador lee el cuerpo JSON por su cuenta. El resto de Odoo no cambia.
"""
from odoo import http

PREFIJO = '/api/gerencia/'

_get_request_original = http.Root.get_request


def _get_request(self, httprequest):
    if httprequest.path.startswith(PREFIJO):
        return http.HttpRequest(httprequest)
    return _get_request_original(self, httprequest)


http.Root.get_request = _get_request
