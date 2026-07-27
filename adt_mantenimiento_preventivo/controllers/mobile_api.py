# -*- coding: utf-8 -*-
"""
API móvil de Mantenimiento Preventivo.

Sigue exactamente el mismo contrato ya usado por
adt_comercial/controllers/mobile_api.py (mismo esquema de respuesta
_success/_error/_json_response, mismo mecanismo de autenticación por
Authorization: Bearer <token> contra mobile.token) para que la app pueda
usar la misma sesión/token que ya usa para el resto de endpoints (/v1/...).

No se importan los helpers de adt_comercial (son funciones privadas de ese
archivo); se replican aquí de forma idéntica para no depender de imports
frágiles entre módulos.

Endpoints:
    GET  /v1/mantenimiento-preventivo/origenes    → catálogo configurable de
         orígenes de atención (ADT Taller, Taller TVS, Otro Taller, ...).
    GET  /v1/mantenimiento-preventivo/pendientes  → mantenimientos pendientes
         de confirmar para un vehículo (?plate=).
    POST /v1/mantenimiento-preventivo/atencion    → registra que un
         mantenimiento pendiente ya se realizó (cancela la campaña activa y
         marca el estado como atendido).
    GET  /v1/mantenimiento-preventivo/imagen/<id> → sirve el binario de una
         imagen de oferta (público, sin token — mismo criterio que
         adt_comercial: mobile.app.image, /v1/app-images/<code>/file).
"""
import base64
import json
import logging
import mimetypes
import uuid
from datetime import datetime, timezone

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Helpers de respuesta (mismo formato que adt_comercial/controllers/mobile_api.py)
# ─────────────────────────────────────────────────────────────────────────
def _now_iso():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def _request_id():
    return str(uuid.uuid4())


def _json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type='application/json',
    )


def _success(data, message='OK'):
    return {
        'success': True,
        'statusCode': 200,
        'message': message,
        'data': data,
        'meta': {'timestamp': _now_iso(), 'requestId': _request_id()},
    }


def _error(http_code, code, message, details=None):
    body = {
        'success': False,
        'statusCode': http_code,
        'error': {'code': code, 'message': message},
        'meta': {'timestamp': _now_iso(), 'requestId': _request_id()},
    }
    if details:
        body['error']['details'] = details
    return body


# ─────────────────────────────────────────────────────────────────────────
# Helpers de autenticación / resolución (mismo mecanismo que adt_comercial)
# ─────────────────────────────────────────────────────────────────────────
def _get_token_record(auth_header):
    """Valida Authorization: Bearer <token> contra mobile.token."""
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, _error(401, 'TOKEN_MISSING', 'Token ausente en el header Authorization.')

    raw_token = auth_header[7:].strip()
    TokenModel = request.env['mobile.token'].sudo()
    token_rec = TokenModel.search([('token', '=', raw_token), ('revoked', '=', False)], limit=1)

    if not token_rec:
        return None, _error(401, 'TOKEN_INVALID', 'Token inválido o no encontrado.')

    if token_rec.expires_at:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        exp = token_rec.expires_at
        if hasattr(exp, 'replace'):
            exp = exp.replace(tzinfo=None)
        if now > exp:
            return None, _error(401, 'TOKEN_EXPIRED', 'El token ha expirado.')

    return token_rec, None


def _vehicle_by_plate(plate_upper):
    VehicleModel = request.env['fleet.vehicle'].sudo()
    vehicle = VehicleModel.search([('license_plate', '=ilike', plate_upper)], limit=1)
    if not vehicle:
        return None, _error(404, 'PLATE_NOT_FOUND', 'No se encontró ningún vehículo con esa placa.')
    return vehicle, None


def _parse_fecha(value):
    """Acepta ISO 8601 ('...T...Z' / '...+00:00') o el formato nativo de Odoo."""
    if not value:
        return None
    try:
        texto = value.replace('Z', '+00:00') if 'T' in value else value
        dt = datetime.fromisoformat(texto)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None


class AdtMantenimientoPreventivoAPI(http.Controller):

    # ─────────────────────────────────────────────────────────────
    # GET /v1/mantenimiento-preventivo/origenes
    # ─────────────────────────────────────────────────────────────
    @http.route(
        '/v1/mantenimiento-preventivo/origenes',
        type='http', auth='none', methods=['GET'], csrf=False, cors='*',
    )
    def get_origenes(self, **kwargs):
        """
        Catálogo configurable de orígenes de atención (ej. "ADT Taller",
        "Taller TVS", "Otro Taller"), para que la app arme el selector al
        registrar que un mantenimiento ya se realizó.
        """
        auth = request.httprequest.headers.get('Authorization', '')
        token_rec, token_err = _get_token_record(auth)
        if token_err:
            return _json_response(token_err, status=token_err['statusCode'])

        origenes = request.env['adt.mantenimiento.origen.atencion'].sudo().search([
            ('active', '=', True),
        ])
        data = [{'id': o.id, 'nombre': o.name, 'codigo': o.code or None} for o in origenes]
        return _json_response(_success(data))

    # ─────────────────────────────────────────────────────────────
    # GET /v1/mantenimiento-preventivo/pendientes
    # ─────────────────────────────────────────────────────────────
    @http.route(
        '/v1/mantenimiento-preventivo/pendientes',
        type='http', auth='none', methods=['GET'], csrf=False, cors='*',
    )
    def get_pendientes(self, plate=None, **kwargs):
        """
        GET /v1/mantenimiento-preventivo/pendientes?plate=<placa>

        Lista todos los mantenimientos pendientes de confirmar para el
        vehículo: cualquier regla ya disparada (umbral alcanzado) que
        todavía no se marcó como atendida, sin importar si la campaña de
        notificaciones sigue activa o ya terminó sus días de envío.
        """
        auth = request.httprequest.headers.get('Authorization', '')
        token_rec, token_err = _get_token_record(auth)
        if token_err:
            return _json_response(token_err, status=token_err['statusCode'])

        plate = (plate or '').strip()
        if not plate:
            return _json_response(
                _error(400, 'PLATE_REQUIRED', 'El parámetro "plate" es obligatorio.'), status=400,
            )

        vehicle, vehicle_err = _vehicle_by_plate(plate)
        if vehicle_err:
            return _json_response(vehicle_err, status=vehicle_err['statusCode'])

        RuleState = request.env['adt.mantenimiento.vehicle.rule.state'].sudo()
        pendientes = RuleState.get_pendientes_vehiculo(vehicle.id)
        return _json_response(_success(pendientes))

    # ─────────────────────────────────────────────────────────────
    # POST /v1/mantenimiento-preventivo/atencion
    # ─────────────────────────────────────────────────────────────
    @http.route(
        '/v1/mantenimiento-preventivo/atencion',
        type='http', auth='none', methods=['POST'], csrf=False, cors='*',
    )
    def post_atencion(self, **kwargs):
        """
        Registra que el mantenimiento de una regla ya se realizó (en ADT
        Taller, en un Taller TVS, en otro taller, etc. — ver
        /v1/mantenimiento-preventivo/origenes). Cancela la campaña activa
        de esa regla (si existe) y detiene el envío de notificaciones
        restantes.

        Body JSON plano esperado (Content-Type: application/json):
            {
                "plate": "ABC-123",
                "regla_id": 3,
                "origen_id": 1,
                "observaciones": "...",                    (opcional)
                "km_atencion": 1050.0,                      (opcional)
                "fecha_atencion": "2026-07-26T10:00:00"     (opcional; default: ahora)
            }

        Nota técnica: esta ruta es `type='http'` (no `type='json'`) a
        propósito. Las rutas `type='json'` de Odoo esperan el body envuelto
        en el sobre JSON-RPC (`{"jsonrpc":"2.0","method":"call","params":{...}}`)
        y devuelven la respuesta envuelta igual — si un cliente externo
        manda el JSON plano de arriba sin ese envoltorio, Odoo no encuentra
        "params" y todos los argumentos llegan como None. Por eso acá se
        parsea el body a mano, aceptando tanto el JSON plano (lo normal para
        un cliente REST) como el envuelto en "params" (por si acaso).
        """
        auth = request.httprequest.headers.get('Authorization', '')
        token_rec, token_err = _get_token_record(auth)
        if token_err:
            return _json_response(token_err, status=token_err['statusCode'])

        try:
            body = json.loads(request.httprequest.data or b'{}')
        except (ValueError, TypeError):
            return _json_response(
                _error(400, 'INVALID_JSON', 'El body debe ser JSON válido.'), status=400,
            )
        params = body.get('params') if isinstance(body.get('params'), dict) else body

        plate = (params.get('plate') or '').strip()
        regla_id = params.get('regla_id')
        origen_id = params.get('origen_id')
        observaciones = params.get('observaciones')
        km_atencion = params.get('km_atencion')
        fecha_atencion = params.get('fecha_atencion')

        if not plate:
            return _json_response(
                _error(400, 'PLATE_REQUIRED', 'El parámetro "plate" es obligatorio.'), status=400,
            )
        if not regla_id:
            return _json_response(
                _error(400, 'REGLA_ID_REQUIRED', 'El parámetro "regla_id" es obligatorio.'), status=400,
            )
        if not origen_id:
            return _json_response(
                _error(400, 'ORIGEN_ID_REQUIRED', 'El parámetro "origen_id" es obligatorio.'), status=400,
            )

        vehicle, vehicle_err = _vehicle_by_plate(plate)
        if vehicle_err:
            return _json_response(vehicle_err, status=vehicle_err['statusCode'])

        Regla = request.env['adt.mantenimiento.regla'].sudo().browse(int(regla_id))
        if not Regla.exists():
            return _json_response(
                _error(404, 'REGLA_NOT_FOUND', 'No se encontró la regla indicada.'), status=404,
            )

        Origen = request.env['adt.mantenimiento.origen.atencion'].sudo().browse(int(origen_id))
        if not Origen.exists():
            return _json_response(
                _error(404, 'ORIGEN_NOT_FOUND', 'No se encontró el origen de atención indicado.'), status=404,
            )

        try:
            km_val = float(km_atencion) if km_atencion is not None else None
        except (TypeError, ValueError):
            return _json_response(
                _error(400, 'KM_ATENCION_INVALID', 'El parámetro "km_atencion" debe ser numérico.'), status=400,
            )

        try:
            orden = request.env['adt.mantenimiento.orden.atencion'].sudo().registrar_atencion(
                vehicle_id=vehicle.id,
                regla_id=Regla.id,
                origen_id=Origen.id,
                observaciones=observaciones,
                fecha_atencion=_parse_fecha(fecha_atencion),
                km_atencion=km_val,
            )
        except Exception as exc:
            _logger.exception('[ADT Mantenimiento] Error registrando atención: %s', exc)
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'No se pudo registrar la atención del mantenimiento.'), status=500,
            )

        return _json_response(_success({
            'orden_atencion_id': orden.id,
            'vehicle_id': vehicle.id,
            'placa': vehicle.license_plate,
            'regla_id': Regla.id,
            'regla_nombre': Regla.name,
            'origen': Origen.name,
            'fecha_atencion': orden.fecha_atencion.isoformat(),
        }, message='Mantenimiento registrado como atendido.'))

    # ─────────────────────────────────────────────────────────────
    # GET /v1/mantenimiento-preventivo/imagen/<imagen_id>
    # ─────────────────────────────────────────────────────────────
    @http.route(
        '/v1/mantenimiento-preventivo/imagen/<int:imagen_id>',
        type='http', auth='none', methods=['GET'], csrf=False, cors='*',
    )
    def get_oferta_imagen(self, imagen_id, **kwargs):
        """
        Sirve el binario de una imagen de oferta (adt.mantenimiento.oferta.imagen)
        para poder usar la URL directo en un <img src=...>/Image.network, sin
        headers especiales — son imágenes de marketing, no datos privados del
        cliente (mismo criterio que /v1/app-images/<code>/file en adt_comercial).
        """
        imagen = request.env['adt.mantenimiento.oferta.imagen'].sudo().browse(imagen_id)
        if not imagen.exists() or not imagen.image:
            return request.not_found()

        data = base64.b64decode(imagen.image)
        content_type = None
        if imagen.image_filename:
            content_type, _ = mimetypes.guess_type(imagen.image_filename)
        content_type = content_type or 'image/jpeg'

        return request.make_response(data, headers=[
            ('Content-Type', content_type),
            ('Content-Length', len(data)),
            ('Cache-Control', 'public, max-age=86400'),
        ])
