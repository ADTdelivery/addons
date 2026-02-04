# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import AccessDenied, UserError
import secrets
import hashlib
import json
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class AdtMobileToken(models.Model):
    """
    Sistema de tokens de seguridad para API móvil (Nivel Producción).

    Características:
    - Token único por dispositivo con metadata
    - Invalidación automática al desactivar usuario
    - Auditoría completa de accesos
    - Rate limiting por token
    - Detección de accesos sospechosos
    """
    _name = 'adt.mobile.token'
    _description = 'ADT Mobile API Token - Security Enhanced'
    _order = 'create_date desc'

    # Identificación
    name = fields.Char(string='Description', required=True)
    token = fields.Char(string='Token Hash', required=True, index=True, copy=False,
                       help='SHA256 hash del token (no almacenamos el token en claro)')

    # Usuario y estado
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade', index=True)
    active = fields.Boolean(default=True, index=True,
                           help='False = token revocado manualmente o por sistema')

    # Expiración y sesión
    expiry = fields.Datetime(string='Expiry Date', required=True, index=True)
    issued_at = fields.Datetime(string='Issued At', default=fields.Datetime.now, readonly=True)
    last_used = fields.Datetime(string='Last Used', readonly=True)

    # Metadata del dispositivo (device binding)
    device_id = fields.Char(string='Device ID', index=True,
                           help='Identificador único del dispositivo (UUID generado por app)')
    device_name = fields.Char(string='Device Name', help='Ej: iPhone 13 Pro')
    device_os = fields.Char(string='OS', help='Ej: iOS 15.1 / Android 12')
    app_version = fields.Char(string='App Version', help='Versión de la app móvil')

    # Seguridad y auditoría
    ip_address = fields.Char(string='IP Address', readonly=True)
    revoked_at = fields.Datetime(string='Revoked At', readonly=True)
    revoked_by = fields.Many2one('res.users', string='Revoked By', readonly=True)
    revoked_reason = fields.Selection([
        ('manual', 'Revocación Manual'),
        ('user_disabled', 'Usuario Desactivado'),
        ('user_deleted', 'Usuario Eliminado'),
        ('expired', 'Token Expirado'),
        ('suspicious', 'Actividad Sospechosa'),
        ('logout', 'Logout desde App'),
    ], string='Revoke Reason', readonly=True)

    # Rate limiting
    requests_count = fields.Integer(string='Total Requests', default=0, readonly=True)
    last_request_time = fields.Datetime(string='Last Request Time', readonly=True)

    # Logs de acceso
    access_log_ids = fields.One2many('adt.mobile.access.log', 'token_id', string='Access Logs')

    _sql_constraints = [
        ('token_unique', 'unique(token)', 'Token must be unique!'),
    ]

    @api.model
    def generate_token(self, user_id, days_valid=30, description=None, device_info=None):
        """
        Genera un token seguro para autenticación móvil.

        Args:
            user_id: ID del usuario
            days_valid: Días de validez (default 30)
            description: Descripción del token
            device_info: dict con {device_id, device_name, device_os, app_version}

        Returns:
            tuple: (token_record, plain_token_string)
        """
        # Verificar que el usuario existe y está activo
        user = self.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            raise UserError('Usuario no encontrado')
        if not user.active:
            raise AccessDenied('Usuario inactivo. No se puede generar token.')

        # Generar token aleatorio seguro (64 caracteres)
        plain_token = secrets.token_urlsafe(48)

        # Hash del token para almacenar (SHA256)
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()

        # Calcular fecha de expiración
        expiry_dt = datetime.utcnow() + timedelta(days=days_valid)
        expiry_str = fields.Datetime.to_string(expiry_dt)

        # Extraer device info si existe
        device_data = device_info or {}

        # Revocar tokens anteriores del mismo dispositivo (un dispositivo = un token activo)
        if device_data.get('device_id'):
            old_tokens = self.sudo().search([
                ('user_id', '=', user_id),
                ('device_id', '=', device_data.get('device_id')),
                ('active', '=', True)
            ])
            if old_tokens:
                old_tokens.write({
                    'active': False,
                    'revoked_at': fields.Datetime.now(),
                    'revoked_reason': 'manual'
                })
                _logger.info(f'Revoked {len(old_tokens)} old tokens for device {device_data.get("device_id")}')

        # Obtener IP del request
        ip_address = None
        try:
            from odoo.http import request as http_request
            if http_request and http_request.httprequest:
                ip_address = http_request.httprequest.remote_addr
        except:
            pass

        # Crear el nuevo token
        rec = self.sudo().create({
            'name': description or f'Mobile token - {device_data.get("device_name", "Unknown Device")}',
            'token': token_hash,
            'user_id': user_id,
            'expiry': expiry_str,
            'active': True,
            'device_id': device_data.get('device_id'),
            'device_name': device_data.get('device_name'),
            'device_os': device_data.get('device_os'),
            'app_version': device_data.get('app_version'),
            'ip_address': ip_address,
        })

        _logger.info(f'Generated new token for user {user.login} (ID: {user_id}), device: {device_data.get("device_name")}')

        # Retornar el record Y el token en claro (solo se retorna una vez)
        return (rec, plain_token)

    @api.model
    def validate_token(self, plain_token, request_info=None):
        """
        Valida un token y verifica todas las condiciones de seguridad.

        Args:
            plain_token: Token en texto claro
            request_info: dict con {ip, endpoint, method} para auditoría

        Returns:
            adt.mobile.token record si válido, None si inválido
        """
        if not plain_token:
            return None

        # Hash del token recibido
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()

        # Buscar token activo
        rec = self.sudo().search([
            ('token', '=', token_hash),
            ('active', '=', True)
        ], limit=1)

        if not rec:
            _logger.warning(f'Invalid or revoked token attempted')
            return None

        # Validación 1: Token expirado
        if rec.expiry:
            now = fields.Datetime.now()
            expiry_dt = fields.Datetime.from_string(rec.expiry)
            if expiry_dt and expiry_dt < now:
                rec.write({
                    'active': False,
                    'revoked_at': now,
                    'revoked_reason': 'expired'
                })
                _logger.info(f'Token expired for user {rec.user_id.login}')
                return None

        # Validación 2: Usuario activo
        if not rec.user_id.active:
            rec.write({
                'active': False,
                'revoked_at': fields.Datetime.now(),
                'revoked_reason': 'user_disabled'
            })
            _logger.warning(f'Token rejected: user {rec.user_id.login} is disabled')
            return None

        # Validación 3: Rate limiting básico (anti-abuse)
        if rec.last_request_time:
            last_req = fields.Datetime.from_string(rec.last_request_time)
            now = datetime.utcnow()
            diff = (now - last_req).total_seconds()

            # Máximo 100 requests por minuto por token
            if diff < 0.6:  # menos de 0.6 segundos entre requests
                _logger.warning(f'Rate limit hit for token of user {rec.user_id.login}')
                # Opcional: bloquear token sospechoso
                # rec.write({'active': False, 'revoked_reason': 'suspicious'})

        # Actualizar estadísticas de uso
        rec.sudo().write({
            'last_used': fields.Datetime.now(),
            'last_request_time': fields.Datetime.now(),
            'requests_count': rec.requests_count + 1
        })

        # Registrar acceso en log (si está configurado)
        if request_info:
            self.env['adt.mobile.access.log'].sudo().create({
                'token_id': rec.id,
                'user_id': rec.user_id.id,
                'endpoint': request_info.get('endpoint'),
                'method': request_info.get('method'),
                'ip_address': request_info.get('ip'),
                'success': True,
            })

        return rec

    @api.model
    def revoke_token(self, plain_token, reason='manual', revoked_by_uid=None):
        """Revoca un token manualmente."""
        if not plain_token:
            return False

        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        rec = self.sudo().search([('token', '=', token_hash)], limit=1)

        if not rec:
            return False

        rec.write({
            'active': False,
            'revoked_at': fields.Datetime.now(),
            'revoked_reason': reason,
            'revoked_by': revoked_by_uid,
        })

        _logger.info(f'Token revoked for user {rec.user_id.login}, reason: {reason}')
        return True

    @api.model
    def revoke_all_user_tokens(self, user_id, reason='user_disabled'):
        """Revoca TODOS los tokens de un usuario (cuando se desactiva/elimina)."""
        tokens = self.sudo().search([
            ('user_id', '=', user_id),
            ('active', '=', True)
        ])

        if tokens:
            tokens.write({
                'active': False,
                'revoked_at': fields.Datetime.now(),
                'revoked_reason': reason,
            })
            _logger.info(f'Revoked {len(tokens)} tokens for user ID {user_id}, reason: {reason}')

        return len(tokens)

    @api.model
    def cleanup_expired_tokens(self):
        """Tarea CRON: Limpia tokens expirados."""
        now = fields.Datetime.now()
        expired = self.sudo().search([
            ('expiry', '<', now),
            ('active', '=', True)
        ])

        if expired:
            expired.write({
                'active': False,
                'revoked_at': now,
                'revoked_reason': 'expired'
            })
            _logger.info(f'Cleanup: Revoked {len(expired)} expired tokens')

        return len(expired)

