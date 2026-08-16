# -*- coding: utf-8 -*-
"""
Servicio REST consumido por la app: entrega las credenciales Traccar de un
vehículo, para que la app se conecte directamente al websocket de Traccar
y reciba solo la ubicación de ese dispositivo (ver plan-adt-traccar-device.md,
sección 4.3/4.4).

Dos formas de pedirlo (ver GET /v1/app/traccar-credentials más abajo):

  a) Por Bearer token (Authorization: Bearer <mobile.token>) — el vehículo
     sale del token, igual que el resto de la API móvil de ADT Comercial
     (adt_comercial/controllers/mobile_api.py). Si además se manda `plate`,
     debe coincidir con el vehículo del token (si no, 403).

  b) Por placa directa (?plate=ABC-123, sin token) — mismo criterio de
     seguridad que ya usa POST /v1/auth/login en adt_comercial/controllers/
     mobile_api.py ("No real authentication – designed for internal/partner
     use"): la placa alcanza para identificar el vehículo, sin credenciales
     adicionales. Se agrega acá por pedido explícito ("devolver las
     credenciales... por placa"), replicando el mismo nivel de exposición
     que ya tiene ese endpoint de login para el resto de datos del cliente
     (préstamos, documentos, etc.) — no es una superficie nueva de riesgo
     en este backend, es consistente con lo que ya existe.
"""
import json
import logging
import re
from datetime import datetime, timezone

from odoo import fields as odoo_fields, http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

# Mismo patrón que adt_comercial/controllers/mobile_api.py (PLATE_RE): 2-4
# letras/números, guion opcional, 2-4 letras/números.
PLATE_RE = re.compile(r'^[A-Z0-9]{2,4}-?[A-Z0-9]{2,4}$', re.IGNORECASE)


def _now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type='application/json; charset=utf-8',
    )


def _success(data):
    return {'success': True, 'statusCode': 200, 'data': data, 'meta': {'timestamp': _now_iso()}}


def _error(http_code, code, message):
    return {
        'success': False,
        'statusCode': http_code,
        'error': {'code': code, 'message': message},
        'meta': {'timestamp': _now_iso()},
    }


def _ws_url(traccar_url):
    """Deriva la URL del websocket (/api/socket) a partir de la URL base
    configurada en adt_traccar (http(s)://... → ws(s)://.../api/socket)."""
    if not traccar_url:
        return ''
    if traccar_url.startswith('https://'):
        base = 'wss://' + traccar_url[len('https://'):]
    elif traccar_url.startswith('http://'):
        base = 'ws://' + traccar_url[len('http://'):]
    else:
        base = traccar_url
    return base.rstrip('/') + '/api/socket'


class TraccarCredentialsAPI(http.Controller):

    # ── Helpers ──────────────────────────────────────────────────────────
    def _resolve_token(self):
        """Valida el header Bearer contra mobile.token (mismo modelo que
        usa adt_comercial para el resto de la API móvil). Devuelve el
        registro o None (sin token, inválido, revocado o expirado)."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        token_value = auth_header[len('Bearer '):].strip()
        if not token_value:
            return None

        MobileToken = request.env['mobile.token'].sudo()
        token = MobileToken.search([('token', '=', token_value), ('revoked', '=', False)], limit=1)
        if not token:
            return None
        if token.expires_at and token.expires_at < odoo_fields.Datetime.now():
            return None
        return token

    def _validate_plate(self, plate):
        """Devuelve (placa_normalizada, None) o (None, error_dict)."""
        if not plate:
            return None, _error(422, 'VALIDATION_ERROR', 'El parámetro plate es requerido.')
        plate_upper = plate.strip().upper()
        if not PLATE_RE.match(plate_upper):
            return None, _error(
                422, 'PLATE_INVALID_FORMAT',
                'La placa ingresada no tiene un formato válido (ej. ABC-123).')
        return plate_upper, None

    def _vehicle_by_plate(self, plate_upper):
        """Devuelve (fleet.vehicle, None) o (None, error_dict)."""
        vehicle = request.env['fleet.vehicle'].sudo().search(
            [('license_plate', '=ilike', plate_upper)], limit=1)
        if not vehicle:
            return None, _error(404, 'PLATE_NOT_FOUND', 'No existe ningún vehículo con esa placa.')
        return vehicle, None

    def _not_found_response(self):
        return _json_response(
            _error(404, 'NOT_FOUND', 'Este vehículo no tiene un dispositivo Traccar registrado.'),
            status=404)

    # ── Endpoint ─────────────────────────────────────────────────────────
    @http.route(
        '/v1/app/traccar-credentials',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_traccar_credentials(self, plate=None, **kwargs):
        """
        GET /v1/app/traccar-credentials
        GET /v1/app/traccar-credentials?plate=ABC-123
        Headers (opcional si se manda plate): Authorization: Bearer <mobile.token>

        Devuelve las credenciales Traccar (email, password, url) del
        vehículo, para que la app abra el websocket de Traccar directamente
        y reciba solo la posición de ese dispositivo (el aislamiento lo
        garantiza el permiso Traccar acotado, no un filtro de este
        endpoint).

        Resolución del vehículo (ver docstring del módulo):
          - Con Bearer token: el vehículo sale del token. Si además viene
            `plate`, debe coincidir con el vehículo del token.
          - Sin Bearer token, con `plate`: se busca el vehículo directamente
            por placa (mismo criterio que POST /v1/auth/login).
          - Ninguno de los dos: 401.
        """
        try:
            token = self._resolve_token()
            owner_partner_id = False  # para el chequeo de defensa en profundidad
            vehicle = None

            if token:
                vehicle = token.vehicle_id
                owner_partner_id = token.partner_id.id if token.partner_id else False

                if plate:
                    plate_upper, err = self._validate_plate(plate)
                    if err:
                        return _json_response(err, status=err['statusCode'])
                    vehicle_by_plate, err = self._vehicle_by_plate(plate_upper)
                    if err:
                        return _json_response(err, status=err['statusCode'])
                    if not vehicle or vehicle.id != vehicle_by_plate.id:
                        _logger.warning(
                            'TraccarCredentialsAPI: plate=%s no coincide con el vehículo del '
                            'token (token.vehicle_id=%s).', plate_upper, vehicle and vehicle.id)
                        return _json_response(
                            _error(403, 'PLATE_TOKEN_MISMATCH',
                                   'La placa indicada no corresponde al token enviado.'),
                            status=403)

                if not vehicle:
                    return _json_response(
                        _error(422, 'NO_VEHICLE', 'El token no está asociado a ningún vehículo.'),
                        status=422)

            elif plate:
                # Sin token: se resuelve directo por placa (ver docstring).
                plate_upper, err = self._validate_plate(plate)
                if err:
                    return _json_response(err, status=err['statusCode'])
                vehicle, err = self._vehicle_by_plate(plate_upper)
                if err:
                    return _json_response(err, status=err['statusCode'])

            else:
                return _json_response(
                    _error(401, 'UNAUTHORIZED',
                           'Falta el header Authorization Bearer o el parámetro plate.'),
                    status=401)

            Credential = request.env['adt.traccar.device.credential'].sudo()
            credential = Credential.search([
                ('vehicle_id', '=', vehicle.id),
                ('state', '=', 'activo'),
            ], limit=1)
            if not credential:
                return self._not_found_response()

            # Defensa en profundidad (solo aplica al flujo con token): si el
            # token trae partner_id, debe coincidir con el dueño de la
            # credencial — un token no puede pedir las credenciales de un
            # vehículo de otro cliente aunque adivine la placa correcta.
            if owner_partner_id and credential.partner_id.id != owner_partner_id:
                _logger.warning(
                    'TraccarCredentialsAPI: token partner_id=%s no coincide con '
                    'credential.partner_id=%s (vehicle_id=%s) — se responde 404.',
                    owner_partner_id, credential.partner_id.id, vehicle.id,
                )
                return self._not_found_response()

            password_plain = credential.get_plain_password()

            traccar_url = (request.env['ir.config_parameter'].sudo().get_param('adt_traccar.url') or '').rstrip('/')

            return _json_response(_success({
                'traccar_url': traccar_url,
                'traccar_ws_url': _ws_url(traccar_url),
                'email': credential.traccar_email,
                'password': password_plain,
                'device_id': credential.traccar_device_id,
                'unique_id': credential.imei,
                'plate': credential.plate,
            }))

        except Exception:
            _logger.exception('TraccarCredentialsAPI: error inesperado en GET /v1/app/traccar-credentials')
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)
