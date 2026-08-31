# -*- coding: utf-8 -*-
"""
Envío de notificaciones masivas (módulo Móvil).

Modelo persistente (no wizard transitorio): cada envío queda guardado como
una fila de historial —título, mensaje, destinatarios, redirección y
resultado del envío— en vez de perderse al cerrar la pantalla o al pasar el
vacuum de Odoo. El registro se crea en 'draft' y se puede guardar sin enviar
(borrador); al presionar "Enviar" pasa a 'sent' y queda bloqueado como
constancia de lo que realmente se envió.

Reutiliza el mismo mecanismo de envío que ya usa el cron de cuotas
(`adt.comercial.cuentas._enviar_notificacion`, en models/notificaciones_cron.py):
mismo endpoint HTTP de push (FCM) y mismo modelo `mobile.notification` para
que la notificación quede visible en el historial de la app. No se duplica
lógica de envío, solo se reutiliza para un público elegido a mano en vez de
uno calculado por el cron.
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MobileNotificacionMasivaWizard(models.Model):
    _name = 'mobile.notificacion.masiva.wizard'
    _description = 'Historial de envíos de notificaciones masivas'
    _order = 'create_date desc'

    # No required=True a propósito: si el campo fuera requerido a nivel de
    # vista, el botón "Seleccionar todos los clientes" (que justo sirve para
    # llenarlo) quedaría bloqueado por la validación de Odoo antes de poder
    # ejecutarse ("Campos inválidos: Clientes destino"), porque cualquier
    # botón valida el formulario completo antes de correr. La obligatoriedad
    # real se exige igual, a mano, en action_send().
    partner_ids = fields.Many2many(
        'res.partner', string='Clientes destino',
        help='Cada cliente seleccionado recibe la notificación en el historial de la '
             'app y, si tiene dispositivo(s) registrado(s), un push real vía FCM.',
    )
    # Tampoco required=True: por la misma razón que partner_ids arriba —
    # deben poder quedar vacíos mientras se arma el borrador (p.ej. si se
    # elige primero "Seleccionar todos los clientes" y se redacta el
    # mensaje después). Se exigen igual, a mano, en action_send().
    title = fields.Char(string='Título')
    body = fields.Text(string='Mensaje')
    notification_type = fields.Selection([
        ('PAYMENT_DUE', 'Cuota próxima / vencida'),
        ('PROMOTION', 'Promoción'),
        ('SYSTEM', 'Sistema'),
        ('INFO', 'Información'),
    ], string='Tipo', default='INFO', required=True)
    link_type = fields.Selection([
        ('DEEP_LINK', 'Deep Link (pantalla dentro de la app)'),
        ('EXTERNAL', 'URL Externa'),
        ('NONE', 'Sin acción'),
    ], string='Redirección al tocar', default='NONE', required=True,
        help='Si el cliente toca la notificación en la app, la redirige a este '
             'deep link o URL. "Sin acción" solo la deja visible en su historial.')
    deep_link = fields.Char(
        string='Deep Link',
        help='Ej: adtclient://tienda, adtclient://beneficios',
    )
    external_url = fields.Char(
        string='URL Externa',
        help='Ej: https://...',
    )
    log_only = fields.Boolean(
        string='Modo prueba (no enviar push real)',
        default=True,
        help='Marcado: solo se registra en el log qué se hubiera enviado a cada '
             'dispositivo, sin llamar al servicio de push real. Úsalo para validar '
             'destinatarios y mensaje antes de enviar de verdad.',
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
    ], string='Estado', default='draft', required=True, readonly=True, copy=False,
        help='Draft: guardado pero aún no enviado. Sent: ya se envió y queda como '
             'constancia del historial (no editable).')
    sent_date = fields.Datetime(string='Fecha de envío', readonly=True, copy=False)
    sent_count = fields.Integer(string='Enviados (push real)', readonly=True, copy=False)
    no_device_count = fields.Integer(string='Sin dispositivo', readonly=True, copy=False)
    result_summary = fields.Text(string='Resultado del envío', readonly=True, copy=False)
    active = fields.Boolean(default=True)

    def action_select_all_partners(self):
        """
        Botón "Seleccionar todos los clientes": única regla de selección —
        tener al menos un `mobile.fcm.device` activo (token FCM registrado),
        sin importar si tiene o no cuenta de financiamiento. Sin token FCM
        no hay a dónde mandarle el push, así que no calza como "cliente
        seleccionable" para este envío.
        """
        self.ensure_one()
        FCMModel = self.env['mobile.fcm.device'].sudo()
        partner_ids = FCMModel.search([
            ('partner_id', '!=', False),
            ('active', '=', True),
        ]).mapped('partner_id').ids
        self.partner_ids = [(6, 0, partner_ids)]

    def action_send(self):
        self.ensure_one()
        if self.state == 'sent':
            raise UserError('Esta notificación ya fue enviada; queda como historial.')
        if not self.partner_ids:
            raise UserError('Selecciona al menos un cliente destino.')
        if not self.title or not self.body:
            raise UserError('Título y mensaje son obligatorios.')
        if self.link_type == 'DEEP_LINK' and not self.deep_link:
            raise UserError('Especifica el Deep Link para la redirección elegida.')
        if self.link_type == 'EXTERNAL' and not self.external_url:
            raise UserError('Especifica la URL Externa para la redirección elegida.')

        NotificationModel = self.env['mobile.notification'].sudo()
        FCMModel = self.env['mobile.fcm.device'].sudo()
        # _enviar_notificacion vive en adt.comercial.cuentas (extendida en
        # models/notificaciones_cron.py) — se reutiliza tal cual, mismo
        # endpoint/formato de payload que usa el cron de cuotas.
        CuentasModel = self.env['adt.comercial.cuentas'].sudo()

        sent = 0
        no_device = 0

        for partner in self.partner_ids:
            NotificationModel.create({
                'title': self.title,
                'body': self.body,
                'notification_type': self.notification_type,
                'link_type': self.link_type,
                'deep_link': self.deep_link if self.link_type == 'DEEP_LINK' else False,
                'external_url': self.external_url if self.link_type == 'EXTERNAL' else False,
                'partner_id': partner.id,
                'is_read': False,
                'active': True,
                'created_at': fields.Datetime.now(),
            })

            fcm_devices = FCMModel.search([
                ('partner_id', '=', partner.id),
                ('active', '=', True),
            ])
            if not fcm_devices:
                no_device += 1
                _logger.warning(
                    '[NOTIF_MASIVA] partner_id=%s (%s) sin dispositivos FCM activos, '
                    'no se envía push (queda solo en el historial de la app).',
                    partner.id, partner.name,
                )
                continue

            payload = {
                'title': self.title,
                'body': self.body,
                'data': {
                    'tipo': self.notification_type,
                    'partner_id': partner.id,
                    'partner_name': partner.name,
                    'link_type': self.link_type,
                    'deep_link': self.deep_link if self.link_type == 'DEEP_LINK' else None,
                    'external_url': self.external_url if self.link_type == 'EXTERNAL' else None,
                },
            }
            CuentasModel._enviar_notificacion(payload, log_only=self.log_only)
            sent += 1

        summary = (
            'Notificación registrada en el historial para %s cliente(s). '
            '%s modo %s a %s cliente(s) con dispositivo activo. '
            '%s cliente(s) sin dispositivo FCM registrado (no reciben push, '
            'solo queda en su historial dentro de la app).'
        ) % (
            len(self.partner_ids),
            'Simulación (log_only)' if self.log_only else 'Push real enviado',
            'de prueba' if self.log_only else '',
            sent,
            no_device,
        )
        _logger.info('[NOTIF_MASIVA] %s', summary)

        self.write({
            'state': 'sent',
            'sent_date': fields.Datetime.now(),
            'sent_count': sent,
            'no_device_count': no_device,
            'result_summary': summary,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Envío de notificaciones masivas',
                'message': summary,
                'type': 'success',
                'sticky': True,
            },
        }
