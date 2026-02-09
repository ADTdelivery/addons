# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AdtFcmDevice(models.Model):
    """
    Modelo para gestionar tokens FCM (Firebase Cloud Messaging) de dispositivos móviles.

    Características:
    - Un usuario puede tener múltiples dispositivos
    - Cada dispositivo tiene un token único
    - Los tokens se actualizan automáticamente cuando la app se reconecta
    - Se desactivan automáticamente cuando el usuario es desactivado
    """
    _name = 'adt.fcm.device'
    _description = 'Dispositivo FCM para notificaciones push'
    _order = 'last_seen desc, id desc'
    _rec_name = 'device_name'

    # ======================
    # CAMPOS PRINCIPALES
    # ======================

    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
        help='Usuario propietario del dispositivo'
    )

    token = fields.Char(
        string='Token FCM',
        required=True,
        index=True,
        help='Token de Firebase Cloud Messaging'
    )

    platform = fields.Selection([
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    ], string='Plataforma',
        required=True,
        default='android',
        help='Sistema operativo del dispositivo'
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está inactivo, no se enviarán notificaciones a este dispositivo'
    )

    # ======================
    # INFORMACIÓN DEL DISPOSITIVO
    # ======================

    device_name = fields.Char(
        string='Nombre del Dispositivo',
        help='Ej: iPhone 13 Pro, Samsung Galaxy S21'
    )

    device_id = fields.Char(
        string='ID del Dispositivo',
        help='Identificador único del dispositivo (UUID)'
    )

    device_os = fields.Char(
        string='Sistema Operativo',
        help='Ej: Android 12, iOS 15.1'
    )

    app_version = fields.Char(
        string='Versión de la App',
        help='Versión de la aplicación móvil'
    )

    # ======================
    # AUDITORÍA
    # ======================

    created_at = fields.Datetime(
        string='Fecha de Registro',
        default=fields.Datetime.now,
        readonly=True
    )

    last_seen = fields.Datetime(
        string='Última Conexión',
        default=fields.Datetime.now,
        help='Última vez que el dispositivo se conectó'
    )

    last_notification_sent = fields.Datetime(
        string='Última Notificación Enviada',
        readonly=True,
        help='Fecha de la última notificación push enviada'
    )

    notification_count = fields.Integer(
        string='Total de Notificaciones',
        default=0,
        readonly=True,
        help='Contador de notificaciones enviadas a este dispositivo'
    )

    # ======================
    # CONSTRAINTS
    # ======================

    _sql_constraints = [
        ('unique_token',
         'unique(token)',
         '⚠️ Este token FCM ya está registrado para otro dispositivo.'),
    ]

    @api.constrains('token')
    def _check_token(self):
        """Valida que el token no esté vacío."""
        for record in self:
            if not record.token or not record.token.strip():
                raise ValidationError('El token FCM no puede estar vacío.')

    # ======================
    # MÉTODOS PÚBLICOS
    # ======================

    @api.model
    def register_or_update_device(self, user_id, token, platform, device_info=None):
        """
        Registra un nuevo dispositivo o actualiza uno existente.

        Args:
            user_id (int): ID del usuario
            token (str): Token FCM
            platform (str): 'android', 'ios' o 'web'
            device_info (dict): Información adicional del dispositivo

        Returns:
            recordset: Registro del dispositivo
        """
        device_info = device_info or {}

        # Buscar si ya existe el token
        existing = self.search([('token', '=', token)], limit=1)

        if existing:
            # Actualizar información
            vals = {
                'last_seen': fields.Datetime.now(),
                'active': True,
            }

            # Actualizar info del dispositivo si viene
            if device_info.get('device_name'):
                vals['device_name'] = device_info['device_name']
            if device_info.get('device_id'):
                vals['device_id'] = device_info['device_id']
            if device_info.get('device_os'):
                vals['device_os'] = device_info['device_os']
            if device_info.get('app_version'):
                vals['app_version'] = device_info['app_version']

            existing.write(vals)
            _logger.info(f'FCM device updated: {existing.id} for user {user_id}')
            return existing

        # Crear nuevo registro
        vals = {
            'user_id': user_id,
            'token': token,
            'platform': platform,
            'device_name': device_info.get('device_name'),
            'device_id': device_info.get('device_id'),
            'device_os': device_info.get('device_os'),
            'app_version': device_info.get('app_version'),
        }

        new_device = self.create(vals)
        _logger.info(f'FCM device registered: {new_device.id} for user {user_id}')
        return new_device

    def update_last_notification(self):
        """Actualiza la fecha y contador de notificaciones enviadas."""
        self.ensure_one()
        self.write({
            'last_notification_sent': fields.Datetime.now(),
            'notification_count': self.notification_count + 1,
        })

    @api.model
    def get_active_tokens_for_user(self, user_id):
        """
        Obtiene todos los tokens activos de un usuario.

        Args:
            user_id (int): ID del usuario

        Returns:
            list: Lista de tokens FCM activos
        """
        devices = self.search([
            ('user_id', '=', user_id),
            ('active', '=', True),
        ])

        return devices.mapped('token')

    @api.model
    def get_active_devices_for_user(self, user_id):
        """
        Obtiene todos los dispositivos activos de un usuario.

        Args:
            user_id (int): ID del usuario

        Returns:
            recordset: Dispositivos activos
        """
        return self.search([
            ('user_id', '=', user_id),
            ('active', '=', True),
        ])

    def deactivate_device(self):
        """Desactiva el dispositivo (no se enviarán más notificaciones)."""
        self.write({'active': False})
        _logger.info(f'FCM device deactivated: {self.ids}')

    def reactivate_device(self):
        """Reactiva el dispositivo."""
        self.write({'active': True})
        _logger.info(f'FCM device reactivated: {self.ids}')
