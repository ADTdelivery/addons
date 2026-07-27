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
from markupsafe import Markup, escape
from urllib.parse import quote_plus
import uuid
import logging
import re

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
    image = fields.Image(
        string='Imagen',
        max_width=1920,
        max_height=1920,
        help='Al guardar, se genera automáticamente la URL pública que consume la app móvil.')
    image_url = fields.Char(string='URL Imagen', readonly=True, copy=False)
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

    # ── Imagen → URL pública ────────────────────────────────────────────────
    def _build_image_public_url(self):
        """URL /web/content con access_token del adjunto del campo `image`.

        Se usa access_token porque la app móvil consume la imagen sin sesión
        de Odoo. Devuelve False si el registro no tiene imagen.
        """
        self.ensure_one()
        if not self.image:
            return False

        attach = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'image'),
        ], limit=1)
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', default='').rstrip('/')

        if not attach:
            # Fallback: URL directa al campo binario (requiere registro accesible).
            return '%s/web/image/%s/%s/image' % (base_url, self._name, self.id)

        token = attach.access_token
        if not token:
            token = str(uuid.uuid4())
            attach.write({'access_token': token})

        filename = attach.name or 'promocion'
        if '.' not in filename:
            filename = '%s.jpg' % filename

        return '%s/web/content/%d/%s?access_token=%s' % (
            base_url, attach.id, quote_plus(filename), token)

    def _sync_image_url(self):
        for rec in self:
            if rec.image:
                url = rec._build_image_public_url()
                if url and url != rec.image_url:
                    rec.image_url = url
            elif rec.image_url:
                rec.image_url = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_image_url()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'image' in vals:
            self._sync_image_url()
        return res

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


# ─────────────────────────────────────────────────────────────────────────────
# HU-013  Mobile App Image (imagen genérica para mostrar en la app)
# ─────────────────────────────────────────────────────────────────────────────
class MobileAppImage(models.Model):
    _name = 'mobile.app.image'
    _description = 'Imagen de la Aplicación Móvil'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Nombre', required=True, help='Etiqueta interna para identificar la imagen.')
    code = fields.Char(
        string='Código',
        required=True,
        index=True,
        help='Identificador que usa la app para solicitar esta imagen, ej: splash, banner_home, login_bg.',
    )
    description = fields.Text(string='Descripción')
    image = fields.Binary(string='Imagen', required=True, attachment=True)
    image_filename = fields.Char(string='Nombre de archivo')
    sequence = fields.Integer(string='Orden', default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('mobile_app_image_code_uniq', 'unique(code)', 'Ya existe una imagen registrada con ese código.'),
    ]

    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if rec.code and not re.match(r'^[A-Za-z0-9_]+$', rec.code):
                raise ValidationError(
                    'El código solo puede contener letras minúsculas, números y guión bajo (_).'
                )


# ─────────────────────────────────────────────────────────────────────────────
# HU-012  Mobile Catalog Global CTA (WhatsApp buy button)
# ─────────────────────────────────────────────────────────────────────────────
class MobileCatalogCTAConfig(models.Model):
    _name = 'mobile.catalog.cta.config'
    _description = 'Configuración global CTA catálogo móvil'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Nombre', required=True, default='Configuración principal')
    cta_enabled = fields.Boolean(string='Botón comprar activo', default=True)
    whatsapp_phone = fields.Char(
        string='WhatsApp de ventas',
        help='Número en formato internacional sin +, ejemplo: 51999111222',
    )
    whatsapp_url = fields.Char(
        string='URL WhatsApp',
        help='Opcional. Si se define, esta URL se usa directamente al tocar el botón.',
    )
    button_text = fields.Char(string='Texto botón comprar', default='Comprar por WhatsApp')
    button_color = fields.Char(string='Color botón comprar', default='#25D366')
    button_icon_image = fields.Binary(string='Ícono botón (imagen)', attachment=True)
    button_icon_image_filename = fields.Char(string='Nombre archivo ícono')
    preview_html = fields.Html(
        string='Vista previa',
        compute='_compute_preview_html',
        sanitize=False,
    )
    sequence = fields.Integer(string='Orden', default=10)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(MobileCatalogCTAConfig, self).create(vals_list)
        # Keep a single active config to avoid ambiguity in API selection.
        for rec in records.filtered(lambda r: r.active):
            others = self.search([('id', '!=', rec.id), ('active', '=', True)])
            if others:
                others.write({'active': False})
        return records

    def write(self, vals):
        res = super(MobileCatalogCTAConfig, self).write(vals)
        if vals.get('active'):
            for rec in self.filtered(lambda r: r.active):
                others = self.search([('id', '!=', rec.id), ('active', '=', True)])
                if others:
                    others.write({'active': False})
        return res

    @api.model
    def _get_or_create_active_config(self):
        config = self.search([('active', '=', True)], order='write_date desc, id desc', limit=1)
        if config:
            return config
        config = self.search([], order='write_date desc, id desc', limit=1)
        if config and not config.active:
            config.write({'active': True})
            return config
        return self.create({'name': 'Configuración principal', 'active': True})

    @api.model
    def action_open_singleton(self):
        config = self._get_or_create_active_config()
        form_view = self.env.ref('adt_comercial.view_mobile_catalog_cta_config_form', raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Botón comprar catálogo',
            'res_model': 'mobile.catalog.cta.config',
            'view_mode': 'form',
            'views': [(form_view.id, 'form')] if form_view else [(False, 'form')],
            'res_id': config.id,
            'target': 'current',
            'context': dict(self.env.context, form_view_initial_mode='edit'),
        }

    @api.constrains('whatsapp_phone')
    def _check_whatsapp_phone(self):
        for rec in self:
            if not rec.whatsapp_phone:
                continue
            digits = ''.join(ch for ch in rec.whatsapp_phone if ch.isdigit())
            if len(digits) < 8 or len(digits) > 15:
                raise ValidationError(
                    'El número de WhatsApp debe tener entre 8 y 15 dígitos (sin espacios ni símbolos).'
                )

    @api.constrains('button_color')
    def _check_button_color(self):
        hex_pattern = re.compile(r'^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$')
        for rec in self:
            if rec.button_color and not hex_pattern.match(rec.button_color.strip()):
                raise ValidationError('El color del botón debe estar en formato HEX, por ejemplo: #25D366')

    @api.depends('button_text', 'button_color', 'button_icon_image', 'cta_enabled', 'whatsapp_phone', 'whatsapp_url')
    def _compute_preview_html(self):
        hex_pattern = re.compile(r'^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$')
        for rec in self:
            color = (rec.button_color or '').strip()
            if not hex_pattern.match(color):
                color = '#25D366'
            state_label = 'Activo' if rec.cta_enabled else 'Desactivado'
            phone_label = rec.whatsapp_phone or 'Sin número configurado'
            url_label = rec.whatsapp_url or 'No definida (se genera con número + producto)'
            icon_data = rec.button_icon_image
            if isinstance(icon_data, bytes):
                icon_data = icon_data.decode('utf-8')
            icon_html = '<span style="font-size:16px;line-height:1;">&#128241;</span>'
            if icon_data:
                icon_html = '<img src="data:image/*;base64,%s" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;"/>' % escape(icon_data)
            rec.preview_html = Markup(
                '<div style="border:1px solid #d9d9d9;border-radius:10px;padding:16px;background:#f7f8fa;max-width:420px;">'
                '<div style="font-size:12px;color:#666;margin-bottom:8px;">Vista previa en app móvil</div>'
                '<button type="button" style="width:100%%;background:%s;border:none;color:#fff;padding:12px 14px;'
                'border-radius:8px;font-size:14px;font-weight:600;opacity:%s;display:flex;align-items:center;justify-content:center;gap:8px;">'
                '%s<span>%s</span>'
                '</button>'
                '<div style="margin-top:10px;font-size:12px;color:#444;">Estado: <strong>%s</strong></div>'
                '<div style="font-size:12px;color:#444;">WhatsApp: %s</div>'
                '<div style="font-size:12px;color:#444;">URL WhatsApp: %s</div>'
                '</div>'
            ) % (
                escape(color),
                '1' if rec.cta_enabled else '0.55',
                Markup(icon_html),
                escape((rec.button_text or 'Comprar por WhatsApp').strip()),
                escape(state_label),
                escape(phone_label),
                escape(url_label),
            )


