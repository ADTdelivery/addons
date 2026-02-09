# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class AdtFcmController(http.Controller):
    """
    Controller para gestión de tokens FCM (Firebase Cloud Messaging).

    Endpoints:
    - POST /adt/mobile/fcm/register: Registrar/actualizar token FCM
    - POST /adt/mobile/fcm/unregister: Desactivar token FCM
    """

    def _extract_token_from_header(self):
        """Extrae el token del header Authorization."""
        auth = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
        if not auth:
            return None
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            return parts[1]
        return None

    def _authenticate_request(self):
        """
        Valida la autenticación del request usando el sistema de tokens existente.

        Returns:
            tuple: (user_sudo, error_response)
        """
        plain_token = self._extract_token_from_header()

        if not plain_token:
            return (None, {
                'success': False,
                'error': 'Authentication required',
                'message': 'No se proporcionó token de autenticación.'
            })

        # Validar token usando el modelo existente
        Token = request.env['adt.mobile.token'].sudo()

        request_info = {
            'ip': request.httprequest.remote_addr,
            'endpoint': request.httprequest.path,
            'method': request.httprequest.method,
            'user_agent': request.httprequest.headers.get('User-Agent', ''),
        }

        token_rec = Token.validate_token(plain_token, request_info)

        if not token_rec:
            _logger.warning(f'Invalid token attempted from IP {request_info.get("ip")}')
            return (None, {
                'success': False,
                'error': 'Invalid or expired token',
                'message': 'Tu sesión ha expirado. Por favor inicia sesión nuevamente.'
            })

        # Verificar usuario activo
        if not token_rec.user_id.active:
            _logger.warning(f'Attempt to use token of disabled user {token_rec.user_id.login}')
            return (None, {
                'success': False,
                'error': 'User account disabled',
                'message': 'Tu cuenta ha sido desactivada.'
            })

        return (token_rec.user_id.sudo(), None)

    @http.route('/adt/mobile/fcm/register', type='json', auth='none', methods=['POST'], csrf=False)
    def register_fcm_token(self, fcm_token=None, token=None, platform=None, device_info=None, **kwargs):
        """
        Registra o actualiza un token FCM para el usuario autenticado.

        Request:
        {
            "fcm_token": "token_fcm_del_dispositivo",  // o "token"
            "platform": "android",  // o "ios", "web"
            "device_info": {
                "device_id": "UUID-del-dispositivo",
                "device_name": "Samsung Galaxy S21",
                "device_os": "Android 12",
                "app_version": "1.0.0"
            }
        }

        Response OK:
        {
            "success": true,
            "message": "Token FCM registrado correctamente",
            "device_id": 123
        }

        Response Error:
        {
            "success": false,
            "error": "Descripción del error",
            "message": "Mensaje amigable"
        }
        """
        # Autenticar usuario
        user, error = self._authenticate_request()
        if error:
            return error

        # Extraer parámetros del JSON request (mismo patrón que mobile_api.py)
        payload = {}
        if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
            payload.update(request.jsonrequest)

        fcm_token = fcm_token or token or payload.get('fcm_token') or payload.get('token')
        platform = platform or payload.get('platform', 'android')
        device_info = device_info or payload.get('device_info', {})

        # Validar parámetros
        if not fcm_token:
            return {
                'success': False,
                'error': 'Missing fcm_token',
                'message': 'El token FCM es requerido.'
            }


        if platform not in ['android', 'ios', 'web']:
            return {
                'success': False,
                'error': 'Invalid platform',
                'message': 'Plataforma inválida. Debe ser: android, ios o web.'
            }

        try:
            # Registrar o actualizar dispositivo
            device = request.env['adt.fcm.device'].sudo().register_or_update_device(
                user_id=user.id,
                token=fcm_token,
                platform=platform,
                device_info=device_info or {}
            )

            _logger.info(f'FCM token registered for user {user.login}: device_id={device.id}')

            return {
                'success': True,
                'message': 'Token FCM registrado correctamente',
                'device_id': device.id,
                'device_name': device.device_name
            }

        except Exception as e:
            _logger.error(f'Error registering FCM token: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'message': 'Error al registrar el token FCM.'
            }

    @http.route('/adt/mobile/fcm/unregister', type='json', auth='none', methods=['POST'], csrf=False)
    def unregister_fcm_token(self, fcm_token=None, **kwargs):
        """
        Desactiva un token FCM (cuando el usuario cierra sesión o desinstala la app).

        Request:
        {
            "fcm_token": "token_fcm_del_dispositivo"
        }

        Response:
        {
            "success": true,
            "message": "Token FCM desactivado correctamente"
        }
        """
        # Autenticar usuario
        user, error = self._authenticate_request()
        if error:
            return error

        # Extraer parámetros del JSON request (mismo patrón que mobile_api.py)
        payload = {}
        if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
            payload.update(request.jsonrequest)

        fcm_token = fcm_token or payload.get('fcm_token') or payload.get('token')

        # Validar parámetros
        if not fcm_token:
            return {
                'success': False,
                'error': 'Missing fcm_token',
                'message': 'El token FCM es requerido.'
            }

        try:
            # Buscar y desactivar el dispositivo
            device = request.env['adt.fcm.device'].sudo().search([
                ('token', '=', fcm_token),
                ('user_id', '=', user.id)
            ], limit=1)

            if device:
                device.deactivate_device()
                _logger.info(f'FCM token unregistered for user {user.login}: device_id={device.id}')
                return {
                    'success': True,
                    'message': 'Token FCM desactivado correctamente'
                }
            else:
                return {
                    'success': False,
                    'error': 'Token not found',
                    'message': 'Token FCM no encontrado para este usuario.'
                }

        except Exception as e:
            _logger.error(f'Error unregistering FCM token: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'message': 'Error al desactivar el token FCM.'
            }

    @http.route('/adt/mobile/fcm/devices', type='json', auth='none', methods=['POST'], csrf=False)
    def list_user_devices(self, **kwargs):
        """
        Lista todos los dispositivos FCM del usuario autenticado.

        Response:
        {
            "success": true,
            "devices": [
                {
                    "id": 1,
                    "device_name": "iPhone 13 Pro",
                    "platform": "ios",
                    "device_os": "iOS 15.1",
                    "active": true,
                    "last_seen": "2026-02-08T10:30:00",
                    "notification_count": 45
                }
            ]
        }
        """
        # Autenticar usuario
        user, error = self._authenticate_request()
        if error:
            return error

        try:
            devices = request.env['adt.fcm.device'].sudo().search([
                ('user_id', '=', user.id)
            ])

            devices_data = []
            for device in devices:
                devices_data.append({
                    'id': device.id,
                    'device_name': device.device_name or 'Desconocido',
                    'platform': device.platform,
                    'device_os': device.device_os,
                    'active': device.active,
                    'last_seen': device.last_seen.isoformat() if device.last_seen else None,
                    'notification_count': device.notification_count,
                    'app_version': device.app_version,
                })

            return {
                'success': True,
                'devices': devices_data
            }

        except Exception as e:
            _logger.error(f'Error listing FCM devices: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'message': 'Error al listar los dispositivos.'
            }
