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
