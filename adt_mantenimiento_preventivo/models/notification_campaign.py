# -*- coding: utf-8 -*-
"""
Campaña de Notificación y su bitácora de envíos.

Ver propuesta-mantenimiento-preventivo-traccar.md, secciones 2.4, 2.5 y 5.

Decisión de negocio (sección 6.6): dias_totales y notificaciones_por_dia se
copian ("snapshot") de la regla al momento de crear la campaña. Un cambio
posterior en la configuración de la regla solo afecta a campañas nuevas, no
a las que ya están en curso.

El envío reutiliza el mismo servicio HTTP externo y el modelo
mobile.fcm.device que usa adt_comercial (ver
adt_comercial/models/notificaciones_cron.py: _enviar_notificacion), para no
duplicar infraestructura de push.
"""
import logging
from datetime import time, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AdtMantenimientoCampana(models.Model):
    _name = 'adt.mantenimiento.campana'
    _description = 'Campaña de Notificación de Mantenimiento Preventivo'
    _order = 'fecha_inicio desc, id desc'

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True, ondelete='cascade', index=True)
    regla_id = fields.Many2one('adt.mantenimiento.regla', string='Regla', required=True, ondelete='cascade', index=True)
    umbral_id = fields.Many2one('adt.mantenimiento.umbral', string='Umbral que la disparó', ondelete='set null')
    partner_id = fields.Many2one(
        'res.partner', string='Cliente', compute='_compute_partner_id', store=True,
    )

    fecha_inicio = fields.Date(
        string='Fecha de inicio', required=True, default=lambda self: self._today_lima(),
    )
    km_al_disparo = fields.Float(string='Km al disparo', digits=(10, 1))

    # Snapshot de configuración de la regla al momento de crearse (sección 6.6)
    dias_totales = fields.Integer(string='Días totales', required=True)
    notificaciones_por_dia = fields.Integer(string='Notificaciones por día', required=True)

    dia_actual = fields.Integer(string='Día actual', default=1)
    notificaciones_enviadas_hoy = fields.Integer(string='Notificaciones enviadas hoy', default=0)

    estado = fields.Selection([
        ('activa', 'Activa'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ], string='Estado', default='activa', required=True, index=True)

    log_ids = fields.One2many('adt.mantenimiento.notificacion.log', 'campana_id', string='Bitácora de envíos')
    log_count = fields.Integer(compute='_compute_log_count', string='N° Envíos')

    @api.depends('vehicle_id')
    def _compute_partner_id(self):
        for rec in self:
            rec.partner_id = rec.vehicle_id._adt_mant_get_partner() if rec.vehicle_id else False

    @api.depends('log_ids')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    def action_cancelar(self):
        """
        Cancelación anticipada (sección 5 y diseño futuro sección 9): cuando
        el mantenimiento se confirma como realizado, la campaña deja de
        enviar notificaciones restantes, independientemente de los días que
        falten.
        """
        for rec in self:
            rec.estado = 'cancelada'
            state = self.env['adt.mantenimiento.vehicle.rule.state'].search([
                ('vehicle_id', '=', rec.vehicle_id.id), ('regla_id', '=', rec.regla_id.id),
            ], limit=1)
            if state:
                state.write({'estado': 'completada_por_usuario', 'atendida_en': fields.Datetime.now()})

    def action_ver_bitacora(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bitácora de envíos',
            'res_model': 'adt.mantenimiento.notificacion.log',
            'view_mode': 'tree,form',
            'domain': [('campana_id', '=', self.id)],
        }

    # ─────────────────────────────────────────────────────────────
    # Horarios (ver sección 2.2 / 5): hora Lima fija UTC-5, igual que
    # adt_traccar (_to_peru_time) y los cron nightly del resto del proyecto.
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _now_lima():
        return fields.Datetime.now() - timedelta(hours=5)

    @classmethod
    def _today_lima(cls):
        return cls._now_lima().date()

    @staticmethod
    def _parse_hora(hhmm):
        hh, mm = hhmm.strip().split(':')
        return time(int(hh), int(mm))

    def _get_ventana_default(self):
        """Ventana horaria por defecto (config Ajustes) usada cuando faltan horarios."""
        ICP = self.env['ir.config_parameter'].sudo()
        inicio_str = ICP.get_param('adt_mantenimiento.horario_ventana_inicio') or '09:00'
        fin_str = ICP.get_param('adt_mantenimiento.horario_ventana_fin') or '19:00'
        return self._parse_hora(inicio_str), self._parse_hora(fin_str)

    @staticmethod
    def _distribuir_uniforme(inicio, fin, count):
        """`count` horas distribuidas uniformemente (sin tocar los bordes) entre inicio y fin."""
        if count <= 0:
            return []
        inicio_min = inicio.hour * 60 + inicio.minute
        fin_min = fin.hour * 60 + fin.minute
        if fin_min <= inicio_min:
            fin_min = inicio_min + 60
        step = (fin_min - inicio_min) / (count + 1)
        puntos = []
        for i in range(1, count + 1):
            minuto = int(round(inicio_min + step * i))
            puntos.append(time((minuto // 60) % 24, minuto % 60))
        return puntos

    def _get_horarios_hoy(self):
        """
        Lista ordenada de `time` en los que corresponde enviar hoy, de largo
        == notificaciones_por_dia.

        Usa los `horario_ids` (tags seleccionables) configurados en la regla; si faltan
        horarios (o no se configuró ninguno), completa repartiendo
        uniformemente el resto dentro de la ventana horaria por defecto
        (Ajustes → Mantenimiento Preventivo).
        """
        self.ensure_one()
        n = max(1, self.notificaciones_por_dia)
        configurados = []
        for h in self.regla_id._get_horarios_list()[:n]:
            try:
                configurados.append(self._parse_hora(h))
            except ValueError:
                continue

        if len(configurados) >= n:
            return sorted(configurados[:n])

        faltantes = n - len(configurados)
        inicio_ventana, fin_ventana = self._get_ventana_default()
        inicio_extra = max(configurados) if configurados else inicio_ventana
        extra = self._distribuir_uniforme(inicio_extra, fin_ventana, faltantes)
        return sorted(configurados + extra)

    # ─────────────────────────────────────────────────────────────
    # Job B — Emisor de notificaciones (ver secciones 5 y 10)
    # ─────────────────────────────────────────────────────────────
    @api.model
    def cron_enviar_notificaciones_campanas(self, log_only=False):
        """
        Recorre TODAS las campañas en estado ACTIVA (no solo las recién
        creadas). Pensado para correr varias veces al día (ver
        data/ir_cron_data.xml, cada 30 minutos): en cada corrida solo envía
        las notificaciones cuyo horario ya se cumplió y que todavía no se
        enviaron hoy, respetando `horario_ids` de la regla (o la
        ventana horaria por defecto si no hay horarios configurados).
        """
        campanas = self.search([('estado', '=', 'activa')])
        hoy = self._today_lima()
        ahora = self._now_lima().time()
        enviados_total = 0

        for campana in campanas:
            try:
                # savepoint por campaña: si una falla (ej. error de red no
                # controlado, registro corrupto), no debe tumbar el resto del
                # cron ni dejar la transacción abortada para las siguientes.
                with self.env.cr.savepoint():
                    enviados_total += campana._procesar_envio_del_dia(hoy, ahora, log_only=log_only)
            except Exception as exc:
                _logger.exception(
                    '[ADT Mantenimiento] Error procesando campaña %s: %s', campana.id, exc,
                )

        _logger.info(
            '[ADT Mantenimiento] Job B (envío) ejecutado. Campañas activas=%d | Notificaciones enviadas=%d',
            len(campanas), enviados_total,
        )
        return enviados_total

    def _procesar_envio_del_dia(self, hoy, ahora, log_only=False):
        """
        Evalúa y envía (si corresponde) las notificaciones pendientes de HOY
        para esta campaña, según sus horarios. Se puede llamar varias veces
        al día: es idempotente porque `notificaciones_enviadas_hoy` recuerda
        cuántos horarios de hoy ya se cumplieron.
        """
        self.ensure_one()
        dia_calculado = (hoy - self.fecha_inicio).days + 1

        if dia_calculado > self.dias_totales:
            self.estado = 'finalizada'
            state = self.env['adt.mantenimiento.vehicle.rule.state'].search([
                ('vehicle_id', '=', self.vehicle_id.id), ('regla_id', '=', self.regla_id.id),
            ], limit=1)
            if state:
                state.estado = 'campana_finalizada'
            return 0

        if dia_calculado > self.dia_actual:
            # Nuevo día de campaña: arranca el conteo de notificaciones desde 0.
            self.write({'dia_actual': dia_calculado, 'notificaciones_enviadas_hoy': 0})
        elif dia_calculado < self.dia_actual:
            # El reloj no debería retroceder; no reprocesar por las dudas.
            return 0

        horarios = self._get_horarios_hoy()
        enviados = 0
        while self.notificaciones_enviadas_hoy < len(horarios) and ahora >= horarios[self.notificaciones_enviadas_hoy]:
            if self._enviar_una_notificacion(log_only=log_only):
                enviados += 1
            self.notificaciones_enviadas_hoy += 1

        return enviados

    def _build_deep_link(self):
        """
        Deep link que la app debe reconocer para redirigir a la pantalla de
        detalle de esta campaña de mantenimiento.

        Formato: adt://mantenimiento/campana/<campana_id>?vehicle_id=<id>&regla_id=<id>&es_oferta=<0|1>

        Sigue el mismo esquema "adt://<recurso>" ya usado como referencia en
        la colección Postman del equipo (ej. adt://loan/installments,
        adt://refinancing, adt://promotions) — no existía un contrato
        formal, así que este módulo lo adopta para mantenerse consistente.
        """
        self.ensure_one()
        return 'adt://mantenimiento/campana/%d?vehicle_id=%d&regla_id=%d&es_oferta=%d' % (
            self.id, self.vehicle_id.id, self.regla_id.id, 1 if self.regla_id.es_oferta else 0,
        )

    def _enviar_una_notificacion(self, log_only=False):
        """Envía UNA notificación push de esta campaña y la registra en la bitácora."""
        self.ensure_one()
        partner = self.partner_id or self.vehicle_id._adt_mant_get_partner()
        if not partner:
            _logger.warning(
                '[ADT Mantenimiento] Campaña %s (vehículo %s): no se pudo resolver cliente.',
                self.id, self.vehicle_id.license_plate,
            )
            self._registrar_log(partner=False, resultado='error', detalle='Sin cliente asociado al vehículo')
            return False

        titulo = '🔧 Mantenimiento preventivo'
        km_referencia = self.vehicle_id.traccar_km_actual or self.km_al_disparo
        cuerpo = self.regla_id.build_mensaje(self.vehicle_id.license_plate, km_referencia)

        self._guardar_notificacion_mobile(partner, titulo, cuerpo)
        resultado, detalle = self._enviar_push(partner, titulo, cuerpo, log_only=log_only)
        self._registrar_log(partner=partner, resultado=resultado, detalle=detalle, titulo=titulo, cuerpo=cuerpo)
        return resultado == 'exito'

    def _guardar_notificacion_mobile(self, partner, titulo, cuerpo):
        """
        Registra la notificación en mobile.notification (el feed de
        notificaciones in-app), con deep_link/link_type poblados de verdad
        para que la app pueda redirigir a la pantalla de la campaña al
        tocarla. Si falla el guardado, no interrumpe el envío del push (
        mismo criterio que adt_comercial: notificaciones_cron.py:
        _guardar_notificacion_mobile).
        """
        self.ensure_one()
        try:
            self.env['mobile.notification'].sudo().create({
                'title': titulo,
                'body': cuerpo,
                'notification_type': 'MAINTENANCE',
                'link_type': 'DEEP_LINK',
                'deep_link': self._build_deep_link(),
                'partner_id': partner.id,
                'vehicle_id': self.vehicle_id.id,
                'is_read': False,
                'active': True,
            })
        except Exception as exc:
            _logger.exception(
                '[ADT Mantenimiento] Error guardando mobile.notification para campaña=%s: %s',
                self.id, exc,
            )

    def _registrar_log(self, partner, resultado, detalle='', titulo='', cuerpo=''):
        self.env['adt.mantenimiento.notificacion.log'].sudo().create({
            'campana_id': self.id,
            'partner_id': partner.id if partner else False,
            'resultado': resultado,
            'detalle': detalle or '',
            'titulo': titulo,
            'cuerpo': cuerpo,
        })

    def _enviar_push(self, partner, titulo, cuerpo, log_only=False):
        """
        Envía el push al mismo servicio HTTP externo usado por adt_comercial
        (ver notificaciones_cron.py: _enviar_notificacion), buscando los
        dispositivos FCM activos del cliente en mobile.fcm.device.

        Devuelve (resultado, detalle) con resultado en ('exito', 'error').
        """
        IrConfig = self.env['ir.config_parameter'].sudo()
        endpoint = (
            IrConfig.get_param('adt_comercial.notificaciones_endpoint')
            or IrConfig.get_param('notification.service.url')
            or 'http://192.168.100.51:8030/send'
        )

        fcm_devices = self.env['mobile.fcm.device'].sudo().search([
            ('partner_id', '=', partner.id), ('active', '=', True),
        ])
        if not fcm_devices:
            _logger.warning(
                '[ADT Mantenimiento] partner_id=%s sin dispositivos FCM activos.', partner.id,
            )
            return 'error', 'Cliente %s sin dispositivos FCM activos' % partner.display_name

        if log_only:
            for device in fcm_devices:
                _logger.info(
                    '[ADT Mantenimiento][TEST] partner_id=%s device_id=%s platform=%s titulo=%s cuerpo=%s',
                    partner.id, device.device_id, device.platform, titulo, cuerpo,
                )
            return 'exito', 'log_only, dispositivos=%s' % len(fcm_devices)

        import requests

        deep_link = self._build_deep_link()
        data_payload = {
            'tipo': 'MANTENIMIENTO_PREVENTIVO',
            'vehicle_id': self.vehicle_id.id,
            'placa': self.vehicle_id.license_plate,
            'regla_id': self.regla_id.id,
            'regla': self.regla_id.name,
            'campana_id': self.id,
            'link_type': 'DEEP_LINK',
            'deep_link': deep_link,
            'es_oferta': 0,  # mismo formato "1/0" que el query param es_oferta del deep_link
        }
        if self.regla_id.es_oferta:
            # OJO: el relay de push (firebase_events/firebase_service.py)
            # convierte cada valor de "data" con str(v) antes de mandarlo a
            # FCM (FCM real solo acepta pares string→string, no objetos
            # anidados). Por eso estos campos van aplanados a nivel raíz en
            # vez de en un sub-diccionario "oferta": un dict anidado se
            # habría convertido en un string tipo repr de Python, no JSON.
            data_payload['es_oferta'] = 1
            data_payload['oferta_titulo'] = self.regla_id.oferta_titulo
            data_payload['oferta_descripcion'] = self.regla_id.oferta_descripcion
            data_payload['oferta_precio'] = self.regla_id.oferta_precio
            data_payload['oferta_moneda'] = self.regla_id.oferta_moneda_id.name
            data_payload['oferta_dias_duracion'] = self.regla_id.oferta_dias_duracion
            data_payload['oferta_wsp_link'] = self.regla_id.oferta_wsp_link
            imagenes_urls = self.regla_id._get_oferta_imagen_urls()
            # Una sola URL (la primera/portada): el "data" del push va todo
            # aplanado a string (ver nota de arriba), así que no se puede
            # mandar la lista completa acá sin romper el parseo del lado de
            # la app. La lista completa sí viaja en
            # GET /v1/mantenimiento-preventivo/pendientes (oferta_imagenes_urls).
            data_payload['oferta_imagen_url'] = imagenes_urls[0] if imagenes_urls else ''
            data_payload['oferta_imagenes_count'] = len(imagenes_urls)

        sent, failed = 0, 0
        for device in fcm_devices:
            token = (device.fcm_token or '').strip()
            if not token:
                failed += 1
                continue
            body = {
                'token': token,
                'title': titulo,
                'body': cuerpo,
                'data': data_payload,
            }
            try:
                response = requests.post(endpoint, json=body, timeout=10)
                if response.status_code == 200:
                    sent += 1
                else:
                    failed += 1
                    _logger.error(
                        '[ADT Mantenimiento] Error %s enviando a device_id=%s partner_id=%s: %.300s',
                        response.status_code, device.device_id, partner.id, response.text,
                    )
                    if 'UNREGISTERED' in response.text or 'NotRegistered' in response.text:
                        # Firebase confirma que este token ya no existe (app
                        # desinstalada, datos limpiados, token rotado sin
                        # volver a registrarse): desactivamos el dispositivo
                        # para no seguir reintentando contra un token muerto
                        # en cada corrida del Job B.
                        device.write({'active': False})
                        _logger.warning(
                            '[ADT Mantenimiento] Token FCM inválido (UNREGISTERED). Se '
                            'desactivó el dispositivo device_id=%s de partner_id=%s.',
                            device.device_id, partner.id,
                        )
            except Exception as exc:
                failed += 1
                _logger.exception(
                    '[ADT Mantenimiento] Fallo de red enviando a device_id=%s partner_id=%s: %s',
                    device.device_id, partner.id, exc,
                )

        detalle = 'sent=%s failed=%s total=%s' % (sent, failed, len(fcm_devices))
        return ('exito', detalle) if sent else ('error', detalle)

    def action_test_envio(self):
        """Botón de prueba manual: envía una notificación inmediata, ignorando el horario programado."""
        total = 0
        for rec in self:
            if rec._enviar_una_notificacion(log_only=False):
                total += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test envío de campaña',
                'message': 'Se enviaron %d notificación(es) de prueba. Revisa la bitácora de cada campaña.' % total,
                'type': 'success' if total else 'warning',
                'sticky': True,
            },
        }


class AdtMantenimientoNotificacionLog(models.Model):
    _name = 'adt.mantenimiento.notificacion.log'
    _description = 'Bitácora de envío de Notificación de Mantenimiento'
    _order = 'fecha_hora desc'

    campana_id = fields.Many2one(
        'adt.mantenimiento.campana', string='Campaña', required=True, ondelete='cascade', index=True,
    )
    vehicle_id = fields.Many2one(related='campana_id.vehicle_id', string='Vehículo', store=True)
    regla_id = fields.Many2one(related='campana_id.regla_id', string='Regla', store=True)
    partner_id = fields.Many2one('res.partner', string='Cliente')

    fecha_hora = fields.Datetime(string='Fecha y hora', default=fields.Datetime.now, required=True)
    resultado = fields.Selection([
        ('exito', 'Éxito'),
        ('error', 'Error'),
    ], string='Resultado', required=True)
    detalle = fields.Char(string='Detalle')
    titulo = fields.Char(string='Título enviado')
    cuerpo = fields.Text(string='Cuerpo enviado')
