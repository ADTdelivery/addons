# -*- coding: utf-8 -*-
"""
Cliente HTTP hacia la API de administración de Traccar, usado como el
usuario admin configurado en el módulo `adt_traccar` (Settings → Traccar,
ver adt_traccar/models/traccar_config.py) para poder crear dispositivos,
usuarios y permisos.

No es un modelo de Odoo: es una clase plana y sin estado persistente en BD
(vive solo durante un request/acción), pensada para reusarse desde el
modelo `adt.traccar.device.credential` y desde el wizard de registro.

Nota: existe otro cliente Traccar en el repo,
`adt_mantenimiento_preventivo/models/traccar_client.py`
(`adt.mantenimiento.traccar.client`), pero ese solo lee posiciones/km de
dispositivos ya existentes — no crea devices/users/permissions. No se
reutiliza directamente para no acoplar dos módulos con responsabilidades
distintas; ver plan-adt-traccar-device.md sección 2.
"""
import logging
from datetime import datetime, timezone

import requests

_logger = logging.getLogger(__name__)

TRACCAR_TIMEOUT = 15  # segundos
LOG_PREFIX = '[adt_traccar_device][Traccar]'


def parse_traccar_datetime(value):
    """Convierte un datetime ISO 8601 de Traccar (ej. '2026-08-15T14:32:10.000+00:00')
    a un datetime naive en UTC, listo para guardar en un campo fields.Datetime
    de Odoo. Devuelve None si no se puede parsear (mismo criterio que
    adt_mantenimiento_preventivo/models/traccar_client.py::_parse_traccar_datetime)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        _logger.warning('%s No se pudo parsear la fecha "%s" devuelta por Traccar.', LOG_PREFIX, value)
        return None


class TraccarAPIError(Exception):
    """Cualquier error de negocio/conexión al hablar con la API de Traccar.

    Se captura en la capa de modelo/controller y se convierte en un
    UserError (para el wizard) o en una respuesta JSON de error (para el
    endpoint REST) — nunca debe llegar cruda hasta la UI de Odoo.
    """
    pass


class TraccarClient(object):

    def __init__(self, url, email, password):
        self.url = (url or '').rstrip('/')
        self.email = email
        self.password = password
        self._session_cookie = None

    @classmethod
    def from_env(cls, env):
        """Construye el cliente leyendo la config de adt_traccar
        (ir.config_parameter: adt_traccar.url / .email / .password)."""
        ICP = env['ir.config_parameter'].sudo()
        url = (ICP.get_param('adt_traccar.url') or '').rstrip('/')
        email = ICP.get_param('adt_traccar.email') or ''
        password = ICP.get_param('adt_traccar.password') or ''
        if not url or not email or not password:
            raise TraccarAPIError(
                'Traccar no está configurado. Ve a Ajustes → Traccar y '
                'completa URL, email y password del administrador.'
            )
        return cls(url, email, password)

    # ── Autenticación ────────────────────────────────────────────────────
    def authenticate(self):
        session_url = '%s/api/session' % self.url
        _logger.info('%s Autenticando en %s (email=%s)', LOG_PREFIX, session_url, self.email)
        try:
            resp = requests.post(
                session_url,
                data={'email': self.email, 'password': self.password},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=TRACCAR_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            raise TraccarAPIError('No se pudo conectar con Traccar: %s' % exc)

        if resp.status_code != 200:
            raise TraccarAPIError('Traccar devolvió HTTP %s al autenticar.' % resp.status_code)

        jsessionid = resp.cookies.get('JSESSIONID')
        if not jsessionid:
            raise TraccarAPIError('Traccar no devolvió JSESSIONID al autenticar.')

        self._session_cookie = jsessionid
        _logger.info('%s Autenticación exitosa.', LOG_PREFIX)
        return jsessionid

    def _cookies(self):
        if not self._session_cookie:
            self.authenticate()
        return {'JSESSIONID': self._session_cookie}

    def _request(self, method, path, **kwargs):
        url = '%s%s' % (self.url, path)
        try:
            resp = requests.request(
                method, url, cookies=self._cookies(), timeout=TRACCAR_TIMEOUT, **kwargs
            )
        except requests.exceptions.RequestException as exc:
            raise TraccarAPIError('No se pudo conectar con Traccar (%s %s): %s' % (method, path, exc))
        return resp

    # ── Dispositivos ─────────────────────────────────────────────────────
    def get_devices(self):
        resp = self._request('GET', '/api/devices')
        if resp.status_code != 200:
            raise TraccarAPIError('Traccar devolvió HTTP %s al listar dispositivos.' % resp.status_code)
        try:
            devices = resp.json()
        except ValueError:
            raise TraccarAPIError('Respuesta inválida de Traccar al listar dispositivos.')
        return devices if isinstance(devices, list) else []

    def find_device_by_unique_id(self, unique_id):
        unique_id_normalized = (unique_id or '').strip()
        if not unique_id_normalized:
            return None
        for device in self.get_devices():
            if (device.get('uniqueId') or '').strip() == unique_id_normalized:
                return device
        return None

    def create_device(self, name, unique_id):
        _logger.info('%s Creando dispositivo name=%s uniqueId=%s', LOG_PREFIX, name, unique_id)
        resp = self._request('POST', '/api/devices', json={'name': name, 'uniqueId': unique_id})
        if resp.status_code not in (200, 201):
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al crear el dispositivo "%s" (uniqueId=%s). Respuesta: %.300s'
                % (resp.status_code, name, unique_id, resp.text)
            )
        return resp.json()

    def get_or_create_device(self, name, unique_id):
        """Busca un device por IMEI (uniqueId); si no existe lo crea.

        Si existe pero tiene un nombre distinto (ej. cambió la placa), se
        actualiza el nombre para que quede reflejando la placa vigente.
        """
        device = self.find_device_by_unique_id(unique_id)
        if device:
            if (device.get('name') or '') != name:
                device = self.update_device_name(device['id'], name, unique_id)
            return device, False
        return self.create_device(name, unique_id), True

    def get_device_by_id(self, device_id):
        """GET /api/devices?id=<id> — estado puntual de un dispositivo
        (status: online/offline/unknown, lastUpdate, positionId, etc.)."""
        resp = self._request('GET', '/api/devices', params={'id': device_id})
        if resp.status_code != 200:
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al consultar el dispositivo %s.' % (resp.status_code, device_id)
            )
        try:
            devices = resp.json()
        except ValueError:
            raise TraccarAPIError('Respuesta inválida de Traccar al consultar el dispositivo %s.' % device_id)
        if not devices:
            raise TraccarAPIError('Traccar no encontró el dispositivo id=%s.' % device_id)
        return devices[0] if isinstance(devices, list) else devices

    def get_position(self, position_id):
        """GET /api/positions?id=<id> — última posición/telemetría conocida
        (latitude, longitude, speed en NUDOS, address, attributes con datos
        específicos del protocolo como batteryLevel, ignition, motion...).
        Devuelve None si Traccar no tiene ninguna posición para ese id."""
        if not position_id:
            return None
        resp = self._request('GET', '/api/positions', params={'id': position_id})
        if resp.status_code != 200:
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al consultar la posición %s.' % (resp.status_code, position_id)
            )
        try:
            positions = resp.json()
        except ValueError:
            raise TraccarAPIError('Respuesta inválida de Traccar al consultar la posición %s.' % position_id)
        if isinstance(positions, list) and positions:
            return positions[0]
        return None

    def update_device_name(self, device_id, name, unique_id):
        _logger.info('%s Actualizando nombre de device_id=%s → %s', LOG_PREFIX, device_id, name)
        resp = self._request(
            'PUT', '/api/devices/%s' % device_id,
            json={'id': device_id, 'name': name, 'uniqueId': unique_id},
        )
        if resp.status_code not in (200, 201, 204):
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al renombrar el dispositivo %s.' % (resp.status_code, device_id)
            )
        return resp.json() if resp.text else {'id': device_id, 'name': name, 'uniqueId': unique_id}

    # ── Usuarios ─────────────────────────────────────────────────────────
    def get_users(self):
        resp = self._request('GET', '/api/users')
        if resp.status_code != 200:
            raise TraccarAPIError('Traccar devolvió HTTP %s al listar usuarios.' % resp.status_code)
        try:
            users = resp.json()
        except ValueError:
            raise TraccarAPIError('Respuesta inválida de Traccar al listar usuarios.')
        return users if isinstance(users, list) else []

    def find_user_by_email(self, email):
        email_normalized = (email or '').strip().lower()
        if not email_normalized:
            return None
        for user in self.get_users():
            if (user.get('email') or '').strip().lower() == email_normalized:
                return user
        return None

    def create_user(self, name, email, password):
        _logger.info('%s Creando usuario Traccar email=%s', LOG_PREFIX, email)
        payload = {
            'name': name or email,
            'email': email,
            'password': password,
            'administrator': False,
        }
        resp = self._request('POST', '/api/users', json=payload)
        if resp.status_code not in (200, 201):
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al crear el usuario "%s". Respuesta: %.300s'
                % (resp.status_code, email, resp.text)
            )
        return resp.json()

    def update_user_password(self, traccar_user_id, name, email, new_password):
        _logger.info('%s Actualizando password de user_id=%s (email=%s)', LOG_PREFIX, traccar_user_id, email)
        payload = {
            'id': traccar_user_id,
            'name': name or email,
            'email': email,
            'password': new_password,
            'administrator': False,
        }
        resp = self._request('PUT', '/api/users/%s' % traccar_user_id, json=payload)
        if resp.status_code not in (200, 201, 204):
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al actualizar el password del usuario %s.'
                % (resp.status_code, traccar_user_id)
            )
        return True

    # ── Permisos ─────────────────────────────────────────────────────────
    def add_permission(self, user_id, device_id):
        _logger.info('%s Asignando permiso userId=%s deviceId=%s', LOG_PREFIX, user_id, device_id)
        resp = self._request('POST', '/api/permissions', json={'userId': user_id, 'deviceId': device_id})
        if resp.status_code not in (200, 201, 204):
            raise TraccarAPIError(
                'Traccar devolvió HTTP %s al asignar el permiso userId=%s deviceId=%s.'
                % (resp.status_code, user_id, device_id)
            )
        return True
