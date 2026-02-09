# -*- coding: utf-8 -*-
"""
Notification Service - Simple HTTP integration

Servicio simple para enviar notificaciones push a través de un endpoint HTTP local.
"""

import logging
import requests

_logger = logging.getLogger(__name__)


class NotificationService:
    """
    Servicio simple para envío de notificaciones push vía HTTP.

    Uso:
        notification_service = NotificationService(env)
        notification_service.send_notification(
            token='token_del_movil',
            title='Título',
            body='Mensaje',
            data={'expediente_id': 123}
        )
    """

    def __init__(self, env):
        """
        Inicializa el servicio de notificaciones.

        Args:
            env: Environment de Odoo
        """
        self.env = env
        self.notification_url = 'http://192.168.100.5:8030/send'

    def send_notification(self, token, title, body, data=None):
        """
        Envía notificación push a un dispositivo.

        Args:
            token (str): Token FCM del dispositivo
            title (str): Título de la notificación
            body (str): Cuerpo de la notificación
            data (dict): Datos adicionales (payload)

        Returns:
            dict: Resultado del envío
        """
        if not token:
            _logger.warning('No se proporcionó token para enviar notificación')
            return {
                'success': False,
                'sent': 0,
                'failed': 1,
                'error': 'No token provided'
            }

        try:
            payload = {
                'token': token,
                'title': title,
                'body': body,
                'data': data or {}
            }

            response = requests.post(
                self.notification_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                _logger.info(f'Notificación enviada correctamente: {title}')
                return {
                    'success': True,
                    'sent': 1,
                    'failed': 0
                }
            else:
                error_msg = f'Error {response.status_code}: {response.text}'
                _logger.error(f'Error enviando notificación: {error_msg}')
                return {
                    'success': False,
                    'sent': 0,
                    'failed': 1,
                    'error': error_msg
                }

        except requests.exceptions.RequestException as e:
            error_msg = f'Error de red: {str(e)}'
            _logger.error(error_msg)
            return {
                'success': False,
                'sent': 0,
                'failed': 1,
                'error': error_msg
            }

    def send_to_user(self, user_id, title, body, data=None):
        """
        Envía notificación a todos los dispositivos activos de un usuario.

        Args:
            user_id (int): ID del usuario
            title (str): Título de la notificación
            body (str): Cuerpo de la notificación
            data (dict): Datos adicionales

        Returns:
            dict: Resultado del envío
        """
        # Obtener tokens activos del usuario
        try:
            tokens = self.env['adt.fcm.device'].sudo().get_active_tokens_for_user(user_id)

            if not tokens:
                _logger.warning(f'Usuario {user_id} no tiene dispositivos FCM registrados')
                return {
                    'success': False,
                    'sent': 0,
                    'failed': 0,
                    'error': 'User has no registered devices'
                }

            # Enviar a cada token
            sent_count = 0
            failed_count = 0

            for token in tokens:
                result = self.send_notification(token, title, body, data)
                if result.get('success'):
                    sent_count += 1
                else:
                    failed_count += 1

            # Actualizar estadísticas de dispositivos si se enviaron
            if sent_count > 0:
                devices = self.env['adt.fcm.device'].sudo().search([
                    ('user_id', '=', user_id),
                    ('token', 'in', tokens),
                    ('active', '=', True)
                ])
                for device in devices:
                    device.update_last_notification()

            return {
                'success': sent_count > 0,
                'sent': sent_count,
                'failed': failed_count
            }

        except Exception as e:
            _logger.error(f'Error enviando notificación a usuario {user_id}: {str(e)}')
            return {
                'success': False,
                'sent': 0,
                'failed': 1,
                'error': str(e)
            }

    """
    Servicio para envío de notificaciones Firebase Cloud Messaging (FCM).

    Uso:
        firebase_service = FirebaseService(env)
        firebase_service.send_notification(
            tokens=['token1', 'token2'],
            title='Título',
            body='Mensaje',
            data={'expediente_id': 123, 'action': 'rechazado'}
        )
    """

    FCM_ENDPOINT = 'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send'
    SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']

    def __init__(self, env):
        """
        Inicializa el servicio Firebase.

        Args:
            env: Environment de Odoo
        """
        self.env = env
        self._access_token = None
        self._token_expiry = None
        self._credentials = None
        self._project_id = None

    def _load_config(self):
        """Carga la configuración de Firebase desde ir.config_parameter."""
        IrConfig = self.env['ir.config_parameter'].sudo()

        service_account_path = IrConfig.get_param('firebase.service_account_path')
        self._project_id = IrConfig.get_param('firebase.project_id')

        if not service_account_path:
            raise ValueError(
                'No se encontró la configuración "firebase.service_account_path". '
                'Configúrala en Configuración > Parámetros del Sistema.'
            )

        if not self._project_id:
            raise ValueError(
                'No se encontró la configuración "firebase.project_id". '
                'Configúrala en Configuración > Parámetros del Sistema.'
            )

        return service_account_path

    def _get_access_token(self):
        """
        Obtiene un access token OAuth2 válido para Firebase.

        Returns:
            str: Access token válido
        """
        # Si ya tenemos un token válido, reutilizarlo
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._access_token

        # Cargar credenciales del service account
        try:
            service_account_path = self._load_config()

            # Crear credenciales desde el archivo JSON
            self._credentials = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=self.SCOPES
            )

            # Obtener token
            self._credentials.refresh(Request())
            self._access_token = self._credentials.token

            # Calcular expiración (los tokens duran ~1 hora, renovar 5 min antes)
            self._token_expiry = datetime.now() + timedelta(minutes=55)

            _logger.info('Firebase OAuth2 token obtenido correctamente')
            return self._access_token

        except FileNotFoundError:
            _logger.error(f'Archivo de service account no encontrado: {service_account_path}')
            raise
        except Exception as e:
            _logger.error(f'Error obteniendo access token de Firebase: {str(e)}')
            raise

    def _build_message(self, token, title, body, data=None, image_url=None):
        """
        Construye el payload del mensaje FCM.

        Args:
            token (str): Token FCM del dispositivo
            title (str): Título de la notificación
            body (str): Cuerpo de la notificación
            data (dict): Datos adicionales (payload)
            image_url (str): URL de imagen opcional

        Returns:
            dict: Mensaje formateado para FCM HTTP v1
        """
        message = {
            'message': {
                'token': token,
                'notification': {
                    'title': title,
                    'body': body,
                },
                'android': {
                    'priority': 'high',
                    'notification': {
                        'sound': 'default',
                        'click_action': 'FLUTTER_NOTIFICATION_CLICK',
                    }
                },
                'apns': {
                    'payload': {
                        'aps': {
                            'sound': 'default',
                            'badge': 1,
                        }
                    }
                }
            }
        }

        # Agregar imagen si se proporciona
        if image_url:
            message['message']['notification']['image'] = image_url

        # Agregar data payload
        if data:
            # Convertir todos los valores a string (requerido por FCM)
            data_str = {k: str(v) for k, v in data.items()}
            message['message']['data'] = data_str

        return message

    def send_notification(self, tokens, title, body, data=None, image_url=None):
        """
        Envía notificaciones push a múltiples dispositivos.

        Args:
            tokens (list): Lista de tokens FCM
            title (str): Título de la notificación
            body (str): Cuerpo de la notificación
            data (dict): Datos adicionales (payload)
            image_url (str): URL de imagen opcional

        Returns:
            dict: Resultado del envío
                {
                    'success': True/False,
                    'sent': int (cantidad enviada),
                    'failed': int (cantidad fallida),
                    'errors': list (errores encontrados)
                }
        """
        if not tokens:
            _logger.warning('No se proporcionaron tokens para enviar notificaciones')
            return {
                'success': False,
                'sent': 0,
                'failed': 0,
                'errors': ['No tokens provided']
            }

        # Asegurar que tokens sea una lista
        if isinstance(tokens, str):
            tokens = [tokens]

        try:
            # Obtener access token
            access_token = self._get_access_token()

            # Endpoint de FCM
            url = self.FCM_ENDPOINT.format(project_id=self._project_id)

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            }

            sent_count = 0
            failed_count = 0
            errors = []

            # Enviar a cada token (FCM v1 no soporta multicast directo)
            for token in tokens:
                try:
                    message = self._build_message(token, title, body, data, image_url)

                    response = requests.post(
                        url,
                        headers=headers,
                        json=message,
                        timeout=10
                    )

                    if response.status_code == 200:
                        sent_count += 1
                        _logger.info(f'Notificación enviada correctamente a token: {token[:20]}...')
                    else:
                        failed_count += 1
                        error_msg = f'Error {response.status_code}: {response.text}'
                        errors.append(error_msg)
                        _logger.error(f'Error enviando notificación: {error_msg}')

                        # Si el token es inválido, marcarlo como inactivo
                        if response.status_code in [400, 404]:
                            self._deactivate_invalid_token(token)

                except requests.exceptions.RequestException as e:
                    failed_count += 1
                    error_msg = f'Error de red: {str(e)}'
                    errors.append(error_msg)
                    _logger.error(error_msg)

            result = {
                'success': sent_count > 0,
                'sent': sent_count,
                'failed': failed_count,
                'errors': errors if errors else None
            }

            _logger.info(f'Envío de notificaciones completado: {sent_count} enviadas, {failed_count} fallidas')
            return result

        except Exception as e:
            error_msg = f'Error crítico enviando notificaciones: {str(e)}'
            _logger.error(error_msg)
            return {
                'success': False,
                'sent': 0,
                'failed': len(tokens),
                'errors': [error_msg]
            }

    def _deactivate_invalid_token(self, token):
        """
        Desactiva un token que Firebase reportó como inválido.

        Args:
            token (str): Token a desactivar
        """
        try:
            device = self.env['adt.fcm.device'].sudo().search([('token', '=', token)], limit=1)
            if device:
                device.deactivate_device()
                _logger.info(f'Token inválido desactivado: {device.id}')
        except Exception as e:
            _logger.error(f'Error desactivando token inválido: {str(e)}')

    def send_to_user(self, user_id, title, body, data=None, image_url=None):
        """
        Envía notificación a todos los dispositivos activos de un usuario.

        Args:
            user_id (int): ID del usuario
            title (str): Título de la notificación
            body (str): Cuerpo de la notificación
            data (dict): Datos adicionales
            image_url (str): URL de imagen opcional

        Returns:
            dict: Resultado del envío
        """
        # Obtener tokens activos del usuario
        tokens = self.env['adt.fcm.device'].sudo().get_active_tokens_for_user(user_id)

        if not tokens:
            _logger.warning(f'Usuario {user_id} no tiene dispositivos FCM registrados')
            return {
                'success': False,
                'sent': 0,
                'failed': 0,
                'errors': ['User has no registered devices']
            }

        # Enviar notificaciones
        result = self.send_notification(tokens, title, body, data, image_url)

        # Actualizar estadísticas de dispositivos
        if result['success']:
            devices = self.env['adt.fcm.device'].sudo().search([
                ('user_id', '=', user_id),
                ('token', 'in', tokens),
                ('active', '=', True)
            ])
            for device in devices:
                device.update_last_notification()

        return result
