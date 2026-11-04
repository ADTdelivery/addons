# -*- coding: utf-8 -*-
"""Webhook de Traccar para el monitoreo GPS en tiempo real.

Traccar reenvía cada evento (y opcionalmente cada posición) en JSON a
    POST /adt_flota_360/gps/traccar/<token>
El token se genera en Odoo (Monitoreo GPS → Configuración → Tiempo real) y se
puede regenerar; sin el token correcto la llamada se rechaza.

Configuración en el servidor de Traccar (conf/traccar.xml) y reinicio de Traccar:
    <entry key='event.forward.enable'>true</entry>
    <entry key='event.forward.url'>URL_DEL_WEBHOOK</entry>
    <!-- Opcional, para geocercas al instante (envía cada posición): -->
    <entry key='forward.enable'>true</entry>
    <entry key='forward.url'>URL_DEL_WEBHOOK</entry>
    <entry key='forward.type'>json</entry>
"""
import hmac
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class Flota360GpsWebhook(http.Controller):

    # Traccar envía Content-Type: application/json, que Odoo 15 enruta como tipo 'json':
    # el cuerpo crudo de Traccar (sin sobre JSON-RPC) queda en request.jsonrequest. A
    # Traccar solo le importa el HTTP 200; el detalle va en la respuesta y en el log.
    @http.route('/adt_flota_360/gps/traccar/<string:token>', type='json', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def traccar(self, token, **kwargs):
        esperado = request.env['ir.config_parameter'].sudo().get_param('adt_flota_360.gps_webhook_token') or ''
        if not esperado or not hmac.compare_digest(esperado, token or ''):
            _logger.warning('[Flota 360][GPS] Webhook de Traccar con token inválido desde %s',
                            request.httprequest.remote_addr)
            return {'ok': False, 'error': 'token inválido'}
        datos = request.jsonrequest
        if not isinstance(datos, dict):
            return {'ok': False, 'error': 'JSON inválido'}
        try:
            return request.env['adt.flota360.gps.dispositivo'].sudo().procesar_webhook(datos)
        except Exception:
            _logger.exception('[Flota 360][GPS] Error procesando el webhook de Traccar')
            request.env.cr.rollback()
            return {'ok': False, 'error': 'error interno'}
