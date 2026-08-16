# -*- coding: utf-8 -*-
"""
Endpoint interno (NO es la API pública de la app — ver traccar_credentials_api.py)
usado por el widget de mapa embebido (static/src/js/live_map_field.js) para
hacer polling del estado GPS de un vehículo mientras el usuario tiene
abierta la ficha en Flota.

auth='user': requiere sesión de Odoo activa (usuario interno logueado), y
respeta las reglas/ACL normales de Odoo sobre adt.traccar.device.credential
— a diferencia de /v1/app/traccar-credentials (que es para la app externa
y no requiere sesión de Odoo).
"""
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class TraccarLivePosition(http.Controller):

    @http.route(
        '/adt_traccar_device/live_position',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def live_position(self, credential_id=None, **kwargs):
        """
        Body JSON-RPC: { "credential_id": <int> }

        Refresca el estado GPS (misma lógica que el botón "Actualizar":
        adt.traccar.device.credential.action_refresh_gps_status()) y
        devuelve el snapshot actualizado para que el widget de mapa
        mueva el marcador sin recargar toda la vista.
        """
        if not credential_id:
            return {'error': 'MISSING_CREDENTIAL_ID'}

        credential = request.env['adt.traccar.device.credential'].browse(int(credential_id))
        if not credential.exists():
            return {'error': 'NOT_FOUND'}
        if credential.state != 'activo':
            return {'error': 'NOT_ACTIVE'}

        try:
            credential.action_refresh_gps_status()
        except UserError as exc:
            return {'error': 'TRACCAR_ERROR', 'message': str(exc)}
        except Exception:
            _logger.exception(
                'TraccarLivePosition: error inesperado refrescando credential=%s', credential.id)
            return {'error': 'INTERNAL_ERROR'}

        return {
            'status': credential.gps_status or 'unknown',
            'last_update': credential.gps_last_update and credential.gps_last_update.isoformat(),
            'latitude': credential.gps_latitude,
            'longitude': credential.gps_longitude,
            'speed_kmh': credential.gps_speed_kmh,
            'battery_level': credential.gps_battery_level,
            'address': credential.gps_address or None,
            'refreshed_at': credential.gps_status_refreshed_at and credential.gps_status_refreshed_at.isoformat(),
            'plate': credential.plate,
        }
