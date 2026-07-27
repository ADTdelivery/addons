# -*- coding: utf-8 -*-
"""
Cliente HTTP hacia el servidor Traccar.

Reutiliza la configuración ya existente del módulo adt_traccar
(ir.config_parameter: adt_traccar.url / adt_traccar.email / adt_traccar.password
— ver adt_traccar/models/traccar_config.py).

Expone únicamente lo que necesita el motor de mantenimiento preventivo:
    - autenticación (JSESSIONID)
    - listado de dispositivos (para hacer match por placa, sección 3)
    - kilometraje acumulado (totalDistance) de la última posición conocida
      (sección 3.a: "Traccar expone esto vía... el atributo totalDistance
      del dispositivo/posición")

No persiste nada: es un servicio sin estado, pensado para usarse dentro de
una misma ejecución de cron (se autentica una sola vez y se reutiliza el
jsessionid para todas las llamadas de esa corrida).

Todos los pasos quedan registrados con el prefijo "[ADT Mantenimiento][Traccar]"
en el log de Odoo, para poder diagnosticar en qué punto exacto falla una
conexión (config incompleta, credenciales rechazadas, placa sin match,
dispositivo sin posiciones, posición sin totalDistance, etc.).
"""
import logging
from datetime import datetime

import requests

from odoo import models

_logger = logging.getLogger(__name__)

TRACCAR_TIMEOUT = 15  # segundos
LOG_PREFIX = '[ADT Mantenimiento][Traccar]'


class AdtMantenimientoTraccarClient(models.AbstractModel):
    _name = 'adt.mantenimiento.traccar.client'
    _description = 'Cliente Traccar para el motor de mantenimiento preventivo'

    # ── Configuración ────────────────────────────────────────────────────
    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        url = (ICP.get_param('adt_traccar.url') or '').rstrip('/')
        email = ICP.get_param('adt_traccar.email') or ''
        password = ICP.get_param('adt_traccar.password') or ''

        _logger.info(
            '%s Configuración leída: url=%s | email=%s | password=%s',
            LOG_PREFIX, url or '(vacío)', email or '(vacío)', '(definido)' if password else '(vacío)',
        )

        if not url or not email or not password:
            _logger.error(
                '%s Configuración incompleta (falta url/email/password). '
                'Ve a Ajustes → Traccar y completa los 3 campos.', LOG_PREFIX,
            )
            raise ValueError(
                'Traccar no está configurado. Ve a Ajustes → Traccar y define '
                'URL, email y password.'
            )
        return {'url': url, 'email': email, 'password': password}

    # ── Autenticación ────────────────────────────────────────────────────
    def _authenticate(self, cfg):
        session_url = '%s/api/session' % cfg['url']
        _logger.info('%s Autenticando en %s con email=%s', LOG_PREFIX, session_url, cfg['email'])
        try:
            resp = requests.post(
                session_url,
                data={'email': cfg['email'], 'password': cfg['password']},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=TRACCAR_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            _logger.error('%s Error de conexión al autenticar en %s: %s', LOG_PREFIX, session_url, exc)
            raise RuntimeError('No se pudo conectar con Traccar: %s' % exc)

        if resp.status_code != 200:
            _logger.error(
                '%s HTTP %s al autenticar. ¿Credenciales incorrectas? Respuesta: %.300s',
                LOG_PREFIX, resp.status_code, resp.text,
            )
            raise RuntimeError('Traccar devolvió HTTP %s al autenticar.' % resp.status_code)

        jsessionid = resp.cookies.get('JSESSIONID')
        if not jsessionid:
            _logger.error('%s Traccar no devolvió JSESSIONID. Respuesta: %.300s', LOG_PREFIX, resp.text)
            raise RuntimeError('Traccar no devolvió JSESSIONID al autenticar.')

        _logger.info('%s Autenticación exitosa (JSESSIONID obtenido).', LOG_PREFIX)
        return jsessionid

    # ── Dispositivos ─────────────────────────────────────────────────────
    def _get_devices(self, cfg, jsessionid):
        devices_url = '%s/api/devices' % cfg['url']
        _logger.info('%s Consultando dispositivos: GET %s', LOG_PREFIX, devices_url)
        try:
            resp = requests.get(
                devices_url,
                cookies={'JSESSIONID': jsessionid},
                timeout=TRACCAR_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            _logger.error('%s Error de conexión al listar dispositivos: %s', LOG_PREFIX, exc)
            raise RuntimeError('No se pudo conectar con Traccar: %s' % exc)
        if resp.status_code != 200:
            _logger.error(
                '%s HTTP %s al listar dispositivos. Respuesta: %.300s',
                LOG_PREFIX, resp.status_code, resp.text,
            )
            raise RuntimeError('Traccar devolvió HTTP %s al listar dispositivos.' % resp.status_code)
        try:
            devices = resp.json()
        except ValueError:
            _logger.error('%s Respuesta de /api/devices no es JSON: %.300s', LOG_PREFIX, resp.text)
            raise RuntimeError('Respuesta inválida de Traccar (no es JSON).')

        devices = devices if isinstance(devices, list) else []
        _logger.info('%s %d dispositivo(s) recibido(s) de Traccar.', LOG_PREFIX, len(devices))
        return devices

    def _get_devices_by_plate(self, cfg, jsessionid):
        """Devuelve un dict {PLACA_NORMALIZADA: device_dict} (match case-insensitive)."""
        devices = self._get_devices(cfg, jsessionid)
        result = {}
        for device in devices:
            name = (device.get('name') or '').strip().upper()
            if name:
                result[name] = device
        _logger.info(
            '%s Placas (nombres de dispositivo) detectadas en Traccar: %s',
            LOG_PREFIX, ', '.join(sorted(result.keys())) or '(ninguna)',
        )
        return result

    # ── Posición / kilometraje ───────────────────────────────────────────
    def _get_position(self, cfg, jsessionid, position_id):
        """GET /api/positions?id=<position_id> → última posición puntual conocida."""
        if not position_id:
            _logger.warning(
                '%s El dispositivo no tiene positionId; no tiene ninguna posición '
                'registrada todavía en Traccar.', LOG_PREFIX,
            )
            return None

        positions_url = '%s/api/positions' % cfg['url']
        _logger.info('%s Consultando posición id=%s: GET %s', LOG_PREFIX, position_id, positions_url)
        try:
            resp = requests.get(
                positions_url,
                params={'id': position_id},
                cookies={'JSESSIONID': jsessionid},
                timeout=TRACCAR_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            _logger.warning('%s Error obteniendo posición %s: %s', LOG_PREFIX, position_id, exc)
            return None
        if resp.status_code != 200:
            _logger.warning(
                '%s HTTP %s obteniendo posición %s. Respuesta: %.300s',
                LOG_PREFIX, resp.status_code, position_id, resp.text,
            )
            return None
        try:
            positions = resp.json()
        except ValueError:
            _logger.warning('%s Respuesta de /api/positions no es JSON: %.300s', LOG_PREFIX, resp.text)
            return None

        if isinstance(positions, list) and positions:
            _logger.info(
                '%s Posición id=%s recibida. attributes=%s',
                LOG_PREFIX, position_id, positions[0].get('attributes'),
            )
            return positions[0]

        _logger.warning('%s Traccar no devolvió ninguna posición para id=%s.', LOG_PREFIX, position_id)
        return None

    def get_km_and_last_report(self, cfg, jsessionid, device):
        """
        A partir de un dict de dispositivo (ver _get_devices), obtiene:
            - km_actual (float en km, o None si no está disponible) leído de
              attributes.totalDistance de la última posición conocida
              (Traccar lo reporta en metros).
            - ultima_fecha_reporte (datetime tz-aware, o None).

        Devuelve la tupla (km_actual, ultima_fecha_reporte).
        """
        device_id = device.get('id')
        device_name = device.get('name')
        _logger.info(
            '%s Leyendo kilometraje de device_id=%s name=%s status=%s positionId=%s lastUpdate=%s',
            LOG_PREFIX, device_id, device_name, device.get('status'),
            device.get('positionId'), device.get('lastUpdate'),
        )

        km_actual = None
        position = self._get_position(cfg, jsessionid, device.get('positionId'))
        if position:
            attrs = position.get('attributes') or {}
            total_distance_m = attrs.get('totalDistance')
            if total_distance_m is not None:
                try:
                    km_actual = float(total_distance_m) / 1000.0
                except (TypeError, ValueError):
                    _logger.warning(
                        '%s device_id=%s: attributes.totalDistance=%r no es numérico.',
                        LOG_PREFIX, device_id, total_distance_m,
                    )
            else:
                _logger.warning(
                    '%s device_id=%s: la posición no trae "totalDistance" en attributes '
                    '(attributes=%s). Puede que el GPS no reporte odómetro.',
                    LOG_PREFIX, device_id, attrs,
                )

        ultima_fecha_reporte = self._parse_traccar_datetime(
            device.get('lastUpdate') or (position or {}).get('fixTime')
        )

        _logger.info(
            '%s Resultado device_id=%s name=%s: km_actual=%s km | última_fecha_reporte=%s',
            LOG_PREFIX, device_id, device_name,
            ('%.1f' % km_actual) if km_actual is not None else 'None (no disponible)',
            ultima_fecha_reporte,
        )
        return km_actual, ultima_fecha_reporte

    @staticmethod
    def _parse_traccar_datetime(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            _logger.warning('%s No se pudo parsear la fecha "%s" devuelta por Traccar.', LOG_PREFIX, value)
            return None
