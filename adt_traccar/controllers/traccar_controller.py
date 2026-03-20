# -*- coding: utf-8 -*-
import json
import logging
import requests
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

TRACCAR_TIMEOUT = 10  # seconds


class TraccarAPI(http.Controller):

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_traccar_config(self):
        """
        Reads Traccar connection parameters from ir.config_parameter (set via
        Settings → Traccar or directly via System Parameters).

        Returns:
            dict with keys: url, email, password
        Raises:
            ValueError if any required parameter is missing.
        """
        ICP = request.env['ir.config_parameter'].sudo()
        url = "http://52.15.86.160:8082"#(ICP.get_param('adt_traccar.url') or '').rstrip('/')
        email = "admin@gmail.com"#ICP.get_param('adt_traccar.email') or ''
        password = "admin123456"#ICP.get_param('adt_traccar.password') or ''

        if not url:
            raise ValueError('Traccar URL no configurada. Ve a Ajustes → Traccar.')
        if not email or not password:
            raise ValueError('Credenciales de Traccar no configuradas. Ve a Ajustes → Traccar.')

        return {'url': url, 'email': email, 'password': password}

    def _traccar_authenticate(self, cfg):
        """
        Step 1 – POST /api/session with email + password.

        Returns:
            str  – JSESSIONID cookie value
        Raises:
            RuntimeError on authentication failure.
        """
        session_url = '{}/api/session'.format(cfg['url'])
        _logger.info('[Traccar] Authenticating at %s', session_url)

        try:
            resp = requests.post(
                session_url,
                data={'email': cfg['email'], 'password': cfg['password']},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=TRACCAR_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError('No se pudo conectar con Traccar: {}'.format(exc))
        except requests.exceptions.Timeout:
            raise RuntimeError('Tiempo de espera agotado al conectar con Traccar.')

        if resp.status_code != 200:
            raise RuntimeError(
                'Traccar devolvió HTTP {} al autenticar. '
                'Verifica las credenciales.'.format(resp.status_code)
            )

        jsessionid = resp.cookies.get('JSESSIONID')
        if not jsessionid:
            raise RuntimeError(
                'Traccar no devolvió JSESSIONID. '
                'Respuesta: {}'.format(resp.text[:200])
            )

        _logger.info('[Traccar] Autenticación exitosa, JSESSIONID obtenido.')
        return jsessionid

    def _traccar_get_devices(self, cfg, jsessionid, user_id=None):
        """
        Step 2 – GET /api/devices using the JSESSIONID cookie.

        Returns:
            list of device dicts from Traccar.
        Raises:
            RuntimeError on failure.
        """
        devices_url = '{}/api/devices'.format(cfg['url'])
        params = {'userId': user_id} if user_id else {}
        _logger.info('[Traccar] Fetching devices from %s params=%s', devices_url, params)

        try:
            resp = requests.get(
                devices_url,
                params=params,
                cookies={'JSESSIONID': jsessionid},
                timeout=TRACCAR_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError('No se pudo conectar con Traccar: {}'.format(exc))
        except requests.exceptions.Timeout:
            raise RuntimeError('Tiempo de espera agotado al obtener dispositivos.')

        if resp.status_code != 200:
            raise RuntimeError(
                'Traccar devolvió HTTP {} al listar dispositivos.'.format(resp.status_code)
            )

        try:
            devices = resp.json()
        except ValueError:
            raise RuntimeError('Respuesta inválida de Traccar: no es JSON.')

        if not isinstance(devices, list):
            raise RuntimeError('Se esperaba una lista de dispositivos.')

        return devices

    def _find_device_by_plate(self, devices, plate):
        """
        Step 3 & 4 – Filter devices where device['name'] matches the plate
        (case-insensitive, stripped).

        Returns:
            dict – the matched device object, or None if not found.
        """
        plate_normalized = plate.strip().upper()
        for device in devices:
            name = (device.get('name') or '').strip().upper()
            if name == plate_normalized:
                return device
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Public endpoint
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/traccar/device/by-plate',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def get_device_by_plate(self, **kwargs):
        """
        GET /api/adt/traccar/device/by-plate?plate=<PLACA>

        Flujo:
          1. Autentica contra Traccar → obtiene JSESSIONID.
          2. GET /api/devices → lista completa de dispositivos.
          3. Filtra por device.name == plate (case-insensitive) → NEW_VEHICLE.
          4. GET /api/devices?userId=8 → extrae el ANTIGUO_VEHICLE (primer elemento).
          5. Devuelve new_device_id, new_device, old_vehicle_id, old_vehicle.

        Query params:
            plate  (str, required) – Placa del nuevo vehículo a buscar.

        Responses:
            200  { success, plate, new_device_id, new_device, old_vehicle_id, old_vehicle }
            400  parámetro faltante
            404  placa no encontrada
            500  error de conexión o Traccar
        """
        plate = (kwargs.get('plate') or '').strip()

        # ── Validate plate ───────────────────────────────────────────────────
        if not plate:
            return self._json_response(
                {'success': False, 'error': 'El parámetro "plate" es obligatorio.'},
                status=400,
            )

        # ── Step 1: config + auth ────────────────────────────────────────────
        try:
            cfg = self._get_traccar_config()
        except ValueError as exc:
            return self._json_response({'success': False, 'error': str(exc)}, status=500)

        try:
            jsessionid = self._traccar_authenticate(cfg)
        except RuntimeError as exc:
            _logger.error('[Traccar] Auth error: %s', exc)
            return self._json_response({'success': False, 'error': str(exc)}, status=500)

        # ── Step 2: get all devices ──────────────────────────────────────────
        try:
            all_devices = self._traccar_get_devices(cfg, jsessionid)
        except RuntimeError as exc:
            _logger.error('[Traccar] Get devices error: %s', exc)
            return self._json_response({'success': False, 'error': str(exc)}, status=500)

        # ── Step 3: filter by plate → NEW_VEHICLE ────────────────────────────
        new_device = self._find_device_by_plate(all_devices, plate)
        if not new_device:
            return self._json_response(
                {
                    'success': False,
                    'error': 'No se encontró ningún dispositivo con la placa "{}".'.format(plate),
                    'plate': plate,
                    'total_devices_searched': len(all_devices),
                },
                status=404,
            )

        new_device_id = new_device['id']
        _logger.info('[Traccar] Placa "%s" → device_id=%s', plate, new_device_id)

        # ── Get ANTIGUO_VEHICLE: GET /api/devices?userId=8 ───────────────────
        try:
            user_devices = self._traccar_get_devices(cfg, jsessionid, user_id=8)
        except RuntimeError as exc:
            _logger.error('[Traccar] Get user devices error: %s', exc)
            return self._json_response({'success': False, 'error': str(exc)}, status=500)

        old_vehicle = user_devices[0] if user_devices else None
        old_vehicle_id = old_vehicle['id'] if old_vehicle else None
        _logger.info('[Traccar] ANTIGUO_VEHICLE id=%s', old_vehicle_id)

        # ── DELETE /api/permissions { userId: 8, deviceId: old_vehicle_id } ──
        delete_result = None
        if old_vehicle_id:
            permissions_url = '{}/api/permissions'.format(cfg['url'])
            _logger.info('[Traccar] DELETE /api/permissions userId=8 deviceId=%s', old_vehicle_id)
            try:
                del_resp = requests.delete(
                    permissions_url,
                    json={'userId': 8, 'deviceId': old_vehicle_id},
                    cookies={'JSESSIONID': jsessionid},
                    headers={'Content-Type': 'application/json'},
                    timeout=TRACCAR_TIMEOUT,
                )
                if del_resp.status_code in (200, 204):
                    delete_result = {
                        'success': True,
                        'status_code': del_resp.status_code,
                        'message': 'Permiso eliminado correctamente (userId=8, deviceId={}).'.format(old_vehicle_id),
                    }
                    _logger.info('[Traccar] Permiso eliminado correctamente para deviceId=%s', old_vehicle_id)
                else:
                    delete_result = {
                        'success': False,
                        'status_code': del_resp.status_code,
                        'message': 'Traccar devolvió HTTP {} al eliminar el permiso.'.format(del_resp.status_code),
                    }
                    _logger.warning('[Traccar] Error al eliminar permiso: HTTP %s', del_resp.status_code)
            except requests.exceptions.ConnectionError as exc:
                delete_result = {'success': False, 'message': 'No se pudo conectar con Traccar: {}'.format(exc)}
            except requests.exceptions.Timeout:
                delete_result = {'success': False, 'message': 'Tiempo de espera agotado al eliminar permiso.'}
        else:
            _logger.info('[Traccar] No hay ANTIGUO_VEHICLE, se omite DELETE /api/permissions.')
            delete_result = {'success': False, 'message': 'No había vehículo previo asignado al usuario 8.'}

        # ── POST /api/permissions { userId: 8, deviceId: new_device_id } ───────
        add_result = None
        permissions_url = '{}/api/permissions'.format(cfg['url'])
        _logger.info('[Traccar] POST /api/permissions userId=8 deviceId=%s', new_device_id)
        try:
            add_resp = requests.post(
                permissions_url,
                json={'userId': 8, 'deviceId': new_device_id},
                cookies={'JSESSIONID': jsessionid},
                headers={'Content-Type': 'application/json'},
                timeout=TRACCAR_TIMEOUT,
            )
            if add_resp.status_code in (200, 204):
                add_result = {
                    'success': True,
                    'status_code': add_resp.status_code,
                    'message': 'Permiso asignado correctamente (userId=8, deviceId={}).'.format(new_device_id),
                }
                _logger.info('[Traccar] Permiso asignado correctamente para deviceId=%s', new_device_id)
            else:
                add_result = {
                    'success': False,
                    'status_code': add_resp.status_code,
                    'message': 'Traccar devolvió HTTP {} al asignar el nuevo permiso.'.format(add_resp.status_code),
                }
                _logger.warning('[Traccar] Error al asignar permiso: HTTP %s', add_resp.status_code)
        except requests.exceptions.ConnectionError as exc:
            add_result = {'success': False, 'message': 'No se pudo conectar con Traccar: {}'.format(exc)}
        except requests.exceptions.Timeout:
            add_result = {'success': False, 'message': 'Tiempo de espera agotado al asignar permiso.'}

        return self._json_response({
            'success': True,
            'plate': plate,
            'new_device_id': new_device_id,
            'status': new_device.get('status'),
            'lastUpdate': new_device.get('lastUpdate'),
        })

    # ─────────────────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _json_response(data, status=200):
        """Returns a JSON HTTP response with the given status code."""
        return Response(
            json.dumps(data, ensure_ascii=False, default=str),
            status=status,
            content_type='application/json; charset=utf-8',
        )
