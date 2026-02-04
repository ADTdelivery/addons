# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AdtMobileAccessLog(models.Model):
    """
    Log de auditoría de accesos a la API móvil.
    Registra cada request para análisis de seguridad y trazabilidad.
    """
    _name = 'adt.mobile.access.log'
    _description = 'Mobile API Access Log'
    _order = 'create_date desc'
    _rec_name = 'endpoint'

    # Relaciones
    token_id = fields.Many2one('adt.mobile.token', string='Token', ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='User', required=True, index=True)

    # Detalles del request
    endpoint = fields.Char(string='Endpoint', required=True, index=True)
    method = fields.Char(string='HTTP Method', default='POST')
    ip_address = fields.Char(string='IP Address', index=True)

    # Resultado
    success = fields.Boolean(string='Success', default=True, index=True)
    error_message = fields.Text(string='Error Message')
    response_time = fields.Float(string='Response Time (ms)')

    # Metadata
    user_agent = fields.Char(string='User Agent')
    device_id = fields.Char(string='Device ID', index=True)

    # Automático
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now, required=True, index=True)

    @api.model
    def log_access(self, user_id, endpoint, method='POST', ip_address=None,
                   success=True, error=None, token_id=None, device_id=None):
        """Método helper para registrar accesos."""
        try:
            self.sudo().create({
                'user_id': user_id,
                'token_id': token_id,
                'endpoint': endpoint,
                'method': method,
                'ip_address': ip_address,
                'success': success,
                'error_message': error,
                'device_id': device_id,
            })
        except Exception as e:
            # No fallar el request principal si falla el log
            _logger.error(f'Failed to create access log: {e}')

    @api.model
    def detect_suspicious_activity(self, user_id, minutes=5, max_requests=50):
        """
        Detecta actividad sospechosa (muchos requests en poco tiempo).

        Returns:
            bool: True si hay actividad sospechosa
        """
        from datetime import datetime, timedelta

        time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
        time_str = fields.Datetime.to_string(time_threshold)

        count = self.sudo().search_count([
            ('user_id', '=', user_id),
            ('timestamp', '>=', time_str)
        ])

        if count > max_requests:
            _logger.warning(f'Suspicious activity detected: {count} requests in {minutes} minutes for user {user_id}')
            return True

        return False

    @api.model
    def cleanup_old_logs(self, days=90):
        """Tarea CRON: Limpia logs antiguos (mantener solo últimos X días)."""
        from datetime import datetime, timedelta

        threshold = datetime.utcnow() - timedelta(days=days)
        threshold_str = fields.Datetime.to_string(threshold)

        old_logs = self.sudo().search([('timestamp', '<', threshold_str)])
        count = len(old_logs)

        if old_logs:
            old_logs.unlink()
            _logger.info(f'Cleaned up {count} old access logs (older than {days} days)')

        return count
