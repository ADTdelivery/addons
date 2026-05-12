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

