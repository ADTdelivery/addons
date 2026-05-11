# -*- coding: utf-8 -*-
"""
Models for Mobile App API
- AppVersion         : HU-001  – versión de la aplicación
- MobilePromotion    : HU-004  – promociones
- MobileNotification : HU-005  – notificaciones
- MobileToken        : JWT-like token storage for mobile sessions
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError
import uuid
import logging

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HU-001  App Version
# ─────────────────────────────────────────────────────────────────────────────
class MobileAppVersion(models.Model):
    _name = 'mobile.app.version'
    _description = 'Versión de la Aplicación Móvil'
    _order = 'create_date desc'

    name = fields.Char(string='Nombre / Tag', default='v1.0.0')
    platform = fields.Selection([
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('all', 'Todas'),
    ], string='Plataforma', default='all', required=True)

    latest_version = fields.Char(string='Última versión disponible', required=True)
    minimum_version = fields.Char(string='Versión mínima requerida', required=True)
    update_required = fields.Boolean(string='Actualización obligatoria', default=False)
    update_available = fields.Boolean(string='Actualización disponible', default=False)
    update_message = fields.Text(string='Mensaje de actualización')

    store_url_android = fields.Char(string='URL Tienda Android (Play Store)')
    store_url_ios = fields.Char(string='URL Tienda iOS (App Store)')

    maintenance_mode = fields.Boolean(string='Modo Mantenimiento', default=False)
    maintenance_message = fields.Text(string='Mensaje de Mantenimiento')

    active = fields.Boolean(default=True)


# ─────────────────────────────────────────────────────────────────────────────
# HU-004  Promotions
# ─────────────────────────────────────────────────────────────────────────────
class MobilePromotion(models.Model):
    _name = 'mobile.promotion'
    _description = 'Promoción Móvil'
    _order = 'priority asc, id asc'

    name = fields.Char(string='Identificador interno', required=True)
    title = fields.Char(string='Título', required=True)
    body = fields.Text(string='Descripción', required=True)
    image_url = fields.Char(string='URL Imagen')
    deep_link = fields.Char(string='Deep Link (interno)')
    external_url = fields.Char(string='URL Externa')
    link_type = fields.Selection([
        ('DEEP_LINK', 'Deep Link'),
        ('EXTERNAL', 'External URL'),
        ('WHATSAPP', 'WhatsApp'),
        ('NONE', 'Sin acción'),
    ], string='Tipo de enlace', default='NONE', required=True)
    active_from = fields.Datetime(string='Activo desde', required=True)
    active_to = fields.Datetime(string='Activo hasta', required=True)
    priority = fields.Integer(string='Prioridad', default=10,
                               help='Menor número = se muestra primero')
    active = fields.Boolean(default=True)

    @api.constrains('active_from', 'active_to')
    def _check_dates(self):
        for rec in self:
            if rec.active_from and rec.active_to and rec.active_from >= rec.active_to:
                raise ValidationError('La fecha de inicio debe ser anterior a la fecha de fin.')

    def get_button_color(self):
        if self.link_type == 'WHATSAPP':
            return 'green'
        return 'default'


# ─────────────────────────────────────────────────────────────────────────────
# HU-005  Notifications
# ─────────────────────────────────────────────────────────────────────────────
class MobileNotification(models.Model):
    _name = 'mobile.notification'
    _description = 'Notificación Móvil'
    _order = 'created_at desc'

    title = fields.Char(string='Título', required=True)
    body = fields.Text(string='Cuerpo', required=True)
    notification_type = fields.Selection([
        ('PAYMENT_DUE', 'Cuota próxima / vencida'),
        ('PROMOTION', 'Promoción'),
        ('SYSTEM', 'Sistema'),
        ('INFO', 'Información'),
    ], string='Tipo', default='INFO', required=True)

    deep_link = fields.Char(string='Deep Link')
    external_url = fields.Char(string='URL Externa')
    link_type = fields.Selection([
        ('DEEP_LINK', 'Deep Link'),
        ('EXTERNAL', 'External URL'),
        ('NONE', 'Sin acción'),
    ], string='Tipo de enlace', default='NONE')
    broadcast_all_clients = fields.Boolean(
        string='Notificación masiva (todos los clientes)',
        default=False,
        help='Si está activo, al guardar se replicará para todos los clientes con dispositivos FCM activos.'
    )

    # To which partner / user this notification belongs
    partner_id = fields.Many2one('res.partner', string='Cliente', index=True)
    # Optionally link to plate / vehicle
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', index=True)

    is_read = fields.Boolean(string='Leído', default=False, oldname='read')
    created_at = fields.Datetime(string='Fecha de creación',
                                  default=lambda self: fields.Datetime.now())
    active = fields.Boolean(default=True)

    def mark_as_read(self):
        self.write({'is_read': True})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        # Evita recursión al crear registros hijos de una notificación masiva.
        if self.env.context.get('skip_massive_expand'):
            if not self.env.context.get('skip_auto_send'):
                records._send_push_notifications()
            return records

        for rec in records:
            if rec.broadcast_all_clients:
                rec._expand_massive_notification()
            else:
                rec._send_push_notifications()
        return records

    def _expand_massive_notification(self):
        """
        Expande una notificación masiva creando una notificación por cliente
        que tenga dispositivos FCM activos.
        """
        self.ensure_one()

        DeviceModel = self.env['mobile.fcm.device'].sudo()
        partners = DeviceModel.search([('active', '=', True)]).mapped('partner_id')

        if not partners:
            _logger.warning(
                '[MobileNotification] Notificación masiva %s sin clientes con FCM activo.',
                self.id,
            )
            return

        child_vals = []
        for partner in partners:
            child_vals.append({
                'title': self.title,
                'body': self.body,
                'notification_type': self.notification_type,
                'deep_link': self.deep_link,
                'external_url': self.external_url,
                'link_type': self.link_type,
                'partner_id': partner.id,
                'vehicle_id': False,
                'broadcast_all_clients': False,
                'is_read': False,
                'active': True,
            })

        # Crea registros hijos sin volver a expandir ni enviar automáticamente.
        child_records = self.with_context(
            skip_massive_expand=True,
            skip_auto_send=True,
        ).sudo().create(child_vals)

        child_records._send_push_notifications()

    def _send_push_notifications(self):
        """
        Envía notificaciones al servicio HTTP externo /send por cada dispositivo FCM
        asociado al partner/vehicle del registro.
        """
        IrConfig = self.env['ir.config_parameter'].sudo()
        endpoint = (
            IrConfig.get_param('adt_comercial.notificaciones_endpoint')
            or IrConfig.get_param('notification.service.url')
            or 'http://localhost:8030/send'
        )

        DeviceModel = self.env['mobile.fcm.device'].sudo()

        for rec in self:
            # Las notificaciones masivas se envían mediante sus registros hijos.
            if rec.broadcast_all_clients:
                continue

            partner = rec.partner_id
            if not partner and rec.vehicle_id and rec.vehicle_id.driver_id:
                partner = rec.vehicle_id.driver_id

            if not partner:
                _logger.info(
                    '[MobileNotification] Notificación %s sin partner/vehicle destino, no se envía.',
                    rec.id,
                )
                continue

            devices = DeviceModel.search([
                ('partner_id', '=', partner.id),
                ('active', '=', True),
            ])

            if not devices:
                _logger.info(
                    '[MobileNotification] Partner %s sin dispositivos FCM activos para notificación %s.',
                    partner.id,
                    rec.id,
                )
                continue

            sent = 0
            failed = 0

            for device in devices:
                token = (device.fcm_token or '').strip()
                if not token:
                    failed += 1
                    continue

                payload = {
                    'token': token,
                    'title': rec.title or '',
                    'body': rec.body or '',
                    'data': {},
                }

                try:
                    import requests

                    response = requests.post(endpoint, json=payload, timeout=10)
                    if response.status_code == 200:
                        sent += 1
                    else:
                        failed += 1
                        _logger.error(
                            '[MobileNotification] Error %s enviando notificación %s a device=%s: %.300s',
                            response.status_code,
                            rec.id,
                            device.device_id,
                            response.text,
                        )
                except Exception as exc:
                    failed += 1
                    _logger.exception(
                        '[MobileNotification] Error enviando notificación %s a device=%s: %s',
                        rec.id,
                        device.device_id,
                        exc,
                    )

            _logger.info(
                '[MobileNotification] Envío notificación %s -> partner=%s | sent=%s | failed=%s | total=%s',
                rec.id,
                partner.id,
                sent,
                failed,
                len(devices),
            )


# ─────────────────────────────────────────────────────────────────────────────
# HU-006  Mobile Token (session management for logout blocklist)
# ─────────────────────────────────────────────────────────────────────────────
class MobileToken(models.Model):
    _name = 'mobile.token'
    _description = 'Token de sesión móvil'
    _order = 'create_date desc'

    token = fields.Char(string='Token', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Cliente')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo')
    device_id = fields.Char(string='Device ID')
    device_model = fields.Char(string='Modelo del dispositivo')
    platform = fields.Char(string='Plataforma')
    app_version = fields.Char(string='Versión App')
    revoked = fields.Boolean(string='Revocado', default=False, index=True)
    revoked_at = fields.Datetime(string='Fecha de revocación')
    expires_at = fields.Datetime(string='Expira en')
    active = fields.Boolean(default=True)

    @api.model
    def generate_token(self):
        """Generate a new unique token string."""
        return str(uuid.uuid4()).replace('-', '')

    def revoke(self):
        self.write({
            'revoked': True,
            'revoked_at': fields.Datetime.now(),
        })


# ─────────────────────────────────────────────────────────────────────────────
# HU-007  Payment Accounts (Cuentas de Pago)
# ─────────────────────────────────────────────────────────────────────────────
class MobilePaymentAccount(models.Model):
    _name = 'mobile.payment.account'
    _description = 'Cuenta de Pago Móvil'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Nombre', required=True, help='Ej: BCP, Yape, Interbank')
    account_number = fields.Char(string='Número / Referencia de Cuenta', required=True)
    icon_url = fields.Char(string='URL del Ícono',
                           default='/web/static/img/placeholder.png')
    sequence = fields.Integer(string='Orden', default=10)
    active = fields.Boolean(default=True)


# ─────────────────────────────────────────────────────────────────────────────
# HU-008  Support Contacts (Contactos de Soporte)
# ─────────────────────────────────────────────────────────────────────────────
class MobileSupportContact(models.Model):
    _name = 'mobile.support.contact'
    _description = 'Contacto de Soporte Móvil'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Nombre', required=True)
    phone = fields.Char(string='Teléfono / WhatsApp')
    role = fields.Selection([
        ('SUPPORT', 'Soporte'),
        ('SALES', 'Ventas'),
        ('ADMIN', 'Administración'),
        ('OTHER', 'Otro'),
    ], string='Rol', default='SUPPORT', required=True)
    sequence = fields.Integer(string='Orden', default=10)
    active = fields.Boolean(default=True)


# ─────────────────────────────────────────────────────────────────────────────
# HU-009  Mobile FCM Device (for push notifications)
# ─────────────────────────────────────────────────────────────────────────────
class MobileFCMDevice(models.Model):
    _name = 'mobile.fcm.device'
    _description = 'Mobile FCM Device Token'
    _order = 'write_date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, index=True)
    mobile_token_id = fields.Many2one('mobile.token', string='Sesion movil', index=True)

    fcm_token = fields.Char(string='FCM Token', required=True, index=True)
    platform = fields.Selection([
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    ], string='Plataforma', required=True)

    device_id = fields.Char(string='Device ID', required=True, index=True)
    device_name = fields.Char(string='Device Name')
    device_os = fields.Char(string='Device OS')
    app_version = fields.Char(string='App Version')

    last_seen_at = fields.Datetime(string='Ultima actividad', default=lambda self: fields.Datetime.now())
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('mobile_fcm_unique_partner_device', 'unique(partner_id, device_id)',
         'Ya existe un registro FCM para este cliente y dispositivo.'),
    ]

