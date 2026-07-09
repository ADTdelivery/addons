# -*- coding: utf-8 -*-
"""
Mobile App REST API Controller
Implements the following endpoints:

  HU-001  GET  /v1/app/version              (no auth)
  HU-002  GET  /v1/loans?plate=ABC-123      (bearer token)
  HU-003  GET  /v1/documents?plate=ABC-123  (bearer token)
          GET  /v1/vehicles/captura-status?plate=ABC-123  (bearer token)
  HU-004  GET  /v1/promotions               (bearer token, pagination)
  HU-005  GET  /v1/notifications            (bearer token, pagination)
  HU-006  POST /v1/auth/logout              (bearer token)
  HU-012  GET  /v1/catalog/products         (bearer token)
  HU-013  GET  /v1/catalog/products/<id>    (bearer token)

Authentication
  - All endpoints except HU-001 require the header:
      Authorization: Bearer <token>
  - Tokens are stored in the `mobile.token` model.
  - Logout revokes the token.

Device headers are recorded in the token model.
"""

import json
import re
import uuid
import logging
import base64
import mimetypes
from urllib.parse import quote_plus
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone

from odoo import http, fields as odoo_fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

# ── Plate regex ────────────────────────────────────────────────────────────
# Standard format: 3 uppercase letters, dash, 3 digits  e.g.  ABC-123
# Some plates in Peru use 4+2 variants; we accept both permissively.
PLATE_RE = re.compile(r'^[A-Z0-9]{2,4}-?[A-Z0-9]{2,4}$', re.IGNORECASE)

WORKSHOP_STATE_LABELS = {
    'pending': 'Pendiente',
    'in_progress': 'En progreso',
    'blocked': 'Bloqueado',
    'done': 'Finalizado',
}

WORKSHOP_PAYER_LABELS = {
    'adt': 'ADT Corporación',
    'cliente': 'Cliente',
    'ambos': 'Ambos',
}

WORKSHOP_FINAL_STATE_LABELS = {
    'optimal': 'Óptimo',
    'with_observations': 'Con Observaciones',
    'follow_up': 'Seguimiento',
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _request_id():
    return str(uuid.uuid4())


def _mask_token(token_value):
    token_str = str(token_value or '').strip()
    if len(token_str) <= 10:
        return token_str
    return '%s...%s' % (token_str[:6], token_str[-4:])


def _json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type='application/json',
    )


def _success(data, message='OK', pagination=None):
    meta = {'timestamp': _now_iso(), 'requestId': _request_id()}
    if pagination:
        meta['pagination'] = pagination
    return {
        'success': True,
        'statusCode': 200,
        'message': message,
        'data': data,
        'meta': meta,
    }


def _error(http_code, code, message, details=None):
    body = {
        'success': False,
        'statusCode': http_code,
        'error': {
            'code': code,
            'message': message,
        },
        'meta': {'timestamp': _now_iso(), 'requestId': _request_id()},
    }
    if details:
        body['error']['details'] = details
    return body


def _validate_plate(plate):
    """
    Returns (normalized_plate, error_response | None)
    """
    if not plate:
        return None, _error(422, 'VALIDATION_ERROR', 'El parámetro plate es requerido.',
                            [{'field': 'plate', 'issue': 'Parámetro requerido', 'rejectedValue': plate}])
    plate_upper = plate.strip().upper()
    if not PLATE_RE.match(plate_upper):
        return None, _error(422, 'PLATE_INVALID_FORMAT',
                            'La placa ingresada no tiene un formato válido.',
                            [{'field': 'plate',
                              'issue': 'Formato inválido. Ejemplo esperado: ABC-123',
                              'rejectedValue': plate}])
    return plate_upper, None


def _get_token_record(auth_header):
    """
    Validates the Authorization: Bearer <token> header.
    Returns (token_record, error_response | None)
    """
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, _error(401, 'TOKEN_MISSING', 'Token ausente en el header Authorization.')

    raw_token = auth_header[7:].strip()
    TokenModel = request.env['mobile.token'].sudo()
    token_rec = TokenModel.search([('token', '=', raw_token), ('revoked', '=', False)], limit=1)

    if not token_rec:
        return None, _error(401, 'TOKEN_INVALID', 'Token inválido o no encontrado.')

    # Check expiry
    if token_rec.expires_at:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        exp = token_rec.expires_at
        if hasattr(exp, 'replace'):
            exp = exp.replace(tzinfo=None)
        if now > exp:
            return None, _error(401, 'TOKEN_EXPIRED', 'El token ha expirado.')

    return token_rec, None


def _vehicle_by_plate(plate_upper):
    """
    Returns (vehicle_record | None, error_response | None)
    """
    VehicleModel = request.env['fleet.vehicle'].sudo()
    vehicle = VehicleModel.search([('license_plate', '=ilike', plate_upper)], limit=1)
    if not vehicle:
        return None, _error(404, 'PLATE_NOT_FOUND',
                            'No existe préstamo activo para la placa indicada.')
    return vehicle, None


def _installment_status(cuota):
    """
    Map adt.comercial.cuotas state → mobile installment status enum.
    """
    state_map = {
        'pagado': 'PAID',
        'pendiente': 'PENDING',
        'vencido': 'OVERDUE',
        'retrasado': 'OVERDUE',
    }
    return state_map.get(cuota.state or '', 'PENDING')


def _late_fee_status(cuota):
    mora_state = getattr(cuota, 'mora_estado_texto', None) or ''
    if not mora_state:
        return 'NONE'
    if 'pagad' in mora_state.lower():
        return 'PAID'
    if 'condo' in mora_state.lower() or 'waiv' in mora_state.lower():
        return 'WAIVED'
    if cuota.mora_pendiente and cuota.mora_pendiente > 0:
        return 'PENDING'
    return 'NONE'


def _format_date(d):
    if not d:
        return None
    try:
        if hasattr(d, 'strftime'):
            return d.strftime('%Y-%m-%d')
        return str(d)
    except Exception:
        return None


def _format_datetime(dt):
    if not dt:
        return None
    try:
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        return str(dt)
    except Exception:
        return None


def _contract_error(status, code, message, field=None):
    body = {
        'code': code,
        'message': message,
    }
    if field:
        body['field'] = field
    return _json_response(body, status=status)


def _to_decimal(value):
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _money(value):
    if value is None:
        value = Decimal('0')
    if not isinstance(value, Decimal):
        value = _to_decimal(value) or Decimal('0')
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        raw = str(value).strip()
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _normalize_base64_image(value):
    """Return a clean base64 payload string (supports data URLs)."""
    if not value:
        return None
    if not isinstance(value, str):
        return None
    payload = value.strip()
    if not payload:
        return None
    if payload.startswith('data:') and ',' in payload:
        payload = payload.split(',', 1)[1].strip()
    try:
        base64.b64decode(payload, validate=True)
    except Exception:
        return None
    return payload


def _resolve_credit_record(credito_id):
    CuentaModel = request.env['adt.comercial.cuentas'].sudo()
    credito_str = str(credito_id or '').strip()
    if not credito_str:
        return None

    if credito_str.isdigit():
        rec = CuentaModel.search([('id', '=', int(credito_str))], limit=1)
        if rec:
            return rec

    rec = CuentaModel.search([('reference_no', '=', credito_str)], limit=1)
    if rec:
        return rec

    return CuentaModel.search([('id', '=', credito_str)], limit=1)


def _resolve_cuota_record(cuenta, cuota_ref):
    cuota_str = str(cuota_ref or '').strip()
    if not cuota_str:
        return None

    cuotas = cuenta.cuota_ids.filtered(lambda c: c.type == 'cuota')

    if cuota_str.isdigit():
        rec = cuotas.filtered(lambda c: c.id == int(cuota_str))[:1]
        if rec:
            return rec

    rec = cuotas.filtered(lambda c: (c.name or '').strip() == cuota_str)[:1]
    if rec:
        return rec

    return None


def _compute_server_mora(cuota, fecha_pago_dt):
    if not cuota or not cuota.fecha_cronograma or not fecha_pago_dt:
        return Decimal('0.00')

    fecha_cronograma = cuota.fecha_cronograma
    diff_days = (fecha_pago_dt.date() - fecha_cronograma).days
    if diff_days <= 0:
        return Decimal('0.00')

    default_factor = float(
        request.env['ir.config_parameter'].sudo().get_param('adt_comercial.mora_factor', 2)
    )

    factors = request.env['adt.cobranza.config.factor'].sudo().search(
        [('company_id', '=', cuota.company_id.id)],
        order='id asc',
        limit=2
    )

    previous_mora_payments = cuota.cuenta_id.cuota_ids.filtered(lambda p: (p.mora_total or 0.0) > 0.0)
    previous_mora_count = len(previous_mora_payments)

    if not factors:
        factor = default_factor
    else:
        index = min(previous_mora_count, len(factors) - 1)
        factor = float(factors[index].factor_mora)

    return _money(Decimal(str(diff_days)) * Decimal(str(factor)))


def _get_base_url():
    """
    URL base a usar para construir links absolutos (imágenes, etc.).

    Se usa el host real con el que el cliente llamó al servidor
    (request.httprequest.host_url), en vez del parámetro fijo 'web.base.url',
    porque en redes locales el servidor puede ser accesible por varias IPs
    (ej. 192.168.100.62 y 192.168.100.68) y 'web.base.url' solo guarda una.
    Si el link se genera con la IP equivocada, el dispositivo que hizo la
    petición no puede alcanzar esa otra IP y la imagen nunca carga.
    """
    host_url = request.httprequest.host_url
    if host_url:
        return host_url.rstrip('/')
    return request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')


def _public_attachment_url(attach, base_url):
    """Genera una URL pública con access_token para que sea accesible sin sesión de Odoo.

    El access_token va como query param (?access_token=...), que es donde Odoo
    realmente valida el acceso público en /web/content. Se agrega además un
    filename con extensión real en el path (derivada del mimetype si el nombre
    del adjunto no la trae) para que los clientes (apps móviles) reconozcan que
    es una imagen a partir de la URL.
    """
    token = attach.access_token
    if not token:
        token = str(uuid.uuid4())
        attach.sudo().write({'access_token': token})

    filename = attach.name or 'image'
    if '.' not in filename:
        ext = mimetypes.guess_extension(attach.mimetype or '') or '.jpg'
        filename = '%s%s' % (filename, ext)

    return '%s/web/content/%d/%s?access_token=%s' % (
        base_url, attach.id, quote_plus(filename), token)


def _build_attachment_url(res_model, res_id, res_field):
    """Devuelve URL /web/content del attachment asociado a un campo binario."""
    try:
        attach = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', res_model),
            ('res_id', '=', res_id),
            ('res_field', '=', res_field),
        ], limit=1)
        base_url = _get_base_url()
        if not attach:
            # Fallback robusto: URL directa al campo binario.
            return '%s/web/image/%s/%s/%s' % (base_url, res_model, res_id, res_field)
        return _public_attachment_url(attach, base_url)
    except Exception:
        _logger.exception('Error generating attachment URL for %s(%s).%s', res_model, res_id, res_field)
        return None


def _notification_domain_from_token(token_rec):
    """
    Build the notification domain for the authenticated mobile token.
    Returns an empty list when the token is not linked to a partner/vehicle.
    """
    if not token_rec:
        return []

    domain = [('active', '=', True)]
    if token_rec.partner_id:
        domain.append(('partner_id', '=', token_rec.partner_id.id))
        return domain
    if token_rec.vehicle_id:
        domain.append(('vehicle_id', '=', token_rec.vehicle_id.id))
        return domain
    return []


def _notify_papeleta_channel(papeleta, vehicle, token_rec, foto_urls):
    """Post papeleta registration details to Discuss channel 'papeleta'."""
    try:
        ChannelModel = request.env['mail.channel'].sudo()
        channel = ChannelModel.search([('name', '=ilike', 'papeleta')], limit=1)
        if not channel:
            _logger.warning("No se encontro canal 'papeleta' para notificar registro %s", papeleta.id)
            return

        partner_name = (token_rec.partner_id.name if token_rec and token_rec.partner_id else 'N/A')
        user_name = (token_rec.create_uid.name if token_rec and token_rec.create_uid else 'API Mobile')
        body = (
            "<p><b>Nueva papeleta registrada desde API móvil</b></p>"
            "<ul>"
            "<li><b>ID:</b> %s</li>"
            "<li><b>Número:</b> %s</li>"
            "<li><b>Fecha:</b> %s</li>"
            "<li><b>Monto:</b> S/ %s</li>"
            "<li><b>Vehículo ID:</b> %s</li>"
            "<li><b>Placa:</b> %s</li>"
            "<li><b>Cliente:</b> %s</li>"
            "<li><b>Usuario:</b> %s</li>"
            "<li><b>Fotos:</b> %s</li>"
            "</ul>"
        ) % (
            papeleta.id,
            papeleta.name or '',
            _format_date(papeleta.fecha_papeleta) or '',
            ('%.2f' % float(_money(papeleta.monto))),
            vehicle.id if vehicle else '',
            (vehicle.license_plate or '') if vehicle else '',
            partner_name,
            user_name,
            len(foto_urls or []),
        )

        if foto_urls:
            links = ''.join(["<li><a href='%s' target='_blank'>Foto %s</a></li>" % (u, i + 1) for i, u in enumerate(foto_urls)])
            body += "<p><b>Adjuntos:</b></p><ul>%s</ul>" % links

        channel.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
    except Exception:
        # Do not break the API flow if Discuss notification fails.
        _logger.exception('Error notificando papeleta %s al canal de conversaciones', getattr(papeleta, 'id', None))


def _captura_record_reasons(rec):
    """
    Junta en una lista los distintos campos de motivo/observaciones de una
    adt.captura.record, para mostrarlos como texto en el full screen de la app.
    """
    reasons = []
    if not rec.moto_recogida and rec.motivo_no_recogida:
        reasons.append(rec.motivo_no_recogida.strip())
    if rec.comentarios_captura:
        reasons.append(rec.comentarios_captura.strip())
    if rec.retention_reason:
        label = dict(rec._fields['retention_reason'].selection).get(rec.retention_reason)
        if label:
            reasons.append(label)
    if rec.observaciones:
        reasons.append(rec.observaciones.strip())

    seen = set()
    unique_reasons = []
    for reason in reasons:
        if reason and reason not in seen:
            seen.add(reason)
            unique_reasons.append(reason)
    return unique_reasons


def _serialize_captura_record(rec):
    """Serializa un adt.captura.record para la respuesta de /v1/vehicles/captura-status."""
    state_label = dict(rec._fields['state'].selection).get(rec.state, rec.state)
    type_label = dict(rec._fields['capture_type'].selection).get(rec.capture_type, rec.capture_type)
    return {
        'id': rec.id,
        'reference': rec.name or None,
        'captureType': (rec.capture_type or '').upper(),
        'captureTypeLabel': type_label,
        'state': (rec.state or '').upper(),
        'stateLabel': state_label,
        'capturedAt': _format_datetime(rec.create_date),
        'motoRecogida': bool(rec.moto_recogida),
        'commitmentDate': _format_date(rec.commitment_date) if rec.capture_type == 'compromiso' else None,
        'intervencionMonto': rec.intervention_fee or 0.0,
        'paymentState': (rec.payment_state or '').upper(),
        'reasons': _captura_record_reasons(rec),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Controller
# ─────────────────────────────────────────────────────────────────────────────

class MobileAPIController(http.Controller):

    # ══════════════════════════════════════════════════════════════════════════
    # HU-001 — GET /v1/app/version
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/app/version',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def app_version(self, **kwargs):
        """
        Returns the current app version, maintenance mode status,
        and whether an update is required/available.
        No authentication required.
        """
        try:
            platform = request.httprequest.headers.get('X-Platform', 'all').lower()

            # Try to find a platform-specific record first, then fall back to 'all'
            VersionModel = request.env['mobile.app.version'].sudo()
            version_rec = VersionModel.search(
                [('active', '=', True), ('platform', 'in', [platform, 'all'])],
                order='platform asc',  # 'all' comes before 'android'/'ios' alphabetically → override below
                limit=1,
            )

            # Prefer exact platform match
            exact = VersionModel.search(
                [('active', '=', True), ('platform', '=', platform)], limit=1)
            if exact:
                version_rec = exact

            if not version_rec:
                # Return safe defaults if no record configured yet
                data = {
                    'latestVersion': '1.0.0',
                    'minimumVersion': '1.0.0',
                    'updateRequired': False,
                    'updateAvailable': False,
                    'updateMessage': None,
                    'storeUrl': {
                        'android': None,
                        'ios': None,
                    },
                    'maintenanceMode': False,
                    'maintenanceMessage': None,
                }
                return _json_response(_success(data))

            data = {
                'latestVersion': version_rec.latest_version,
                'minimumVersion': version_rec.minimum_version,
                'updateRequired': version_rec.update_required,
                'updateAvailable': version_rec.update_available,
                'updateMessage': version_rec.update_message or None,
                'storeUrl': {
                    'android': version_rec.store_url_android or None,
                    'ios': version_rec.store_url_ios or None,
                },
                'maintenanceMode': version_rec.maintenance_mode,
                'maintenanceMessage': version_rec.maintenance_message or None,
            }

            if version_rec.maintenance_mode:
                return _json_response(
                    _error(503, 'SERVICE_UNAVAILABLE',
                           version_rec.maintenance_message or 'Servidor en mantenimiento.'),
                    status=503,
                )

            return _json_response(_success(data))

        except Exception:
            _logger.exception('Error in GET /v1/app/version')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-002 — GET /v1/loans?plate=ABC-123
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/loans',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_loan(self, plate=None, **kwargs):
        """
        Returns the full loan detail for a given plate.
        Requires Authorization: Bearer <token>
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            plate_upper, plate_err = _validate_plate(plate)
            if plate_err:
                return _json_response(plate_err, status=plate_err['statusCode'])

            vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
            if vehicle_err:
                return _json_response(vehicle_err, status=vehicle_err['statusCode'])

            # ── Customer ───────────────────────────────────────────────────
            partner = vehicle.driver_id
            if not partner:
                return _json_response(
                    _error(404, 'PLATE_NOT_FOUND', 'No se encontró cliente asociado a la placa.'),
                    status=404,
                )

            # Map civil status from res.partner
            marital_map = {
                'single': 'SINGLE',
                'married': 'MARRIED',
                'divorced': 'DIVORCED',
                'widower': 'WIDOWED',
                'other': 'SINGLE',
            }
            marital = getattr(partner, 'marital', None) or 'single'

            customer_data = {
                'id': str(partner.id),
                'fullName': partner.name or '',
                'phone': partner.phone or partner.mobile or None,
                'address': partner.street or None,
                'nationality': getattr(partner, 'nationality', None) or None,
                'maritalStatus': marital_map.get(marital, 'SINGLE'),
            }

            # ── Loan / Account ─────────────────────────────────────────────
            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta = CuentaModel.search(
                [('vehiculo_id', '=', vehicle.id), ('state', 'in', ('en_curso', 'aprobado'))],
                limit=1,
            )
            if not cuenta:
                # Try any non-cancelled account
                cuenta = CuentaModel.search(
                    [('vehiculo_id', '=', vehicle.id), ('state', '!=', 'cancelado')],
                    limit=1,
                )

            if not cuenta:
                return _json_response(
                    _error(404, 'PLATE_NOT_FOUND', 'No existe préstamo activo para la placa indicada.'),
                    status=404,
                )

            # Cuotas
            cuotas = cuenta.cuota_ids.filtered(lambda c: c.type == 'cuota').sorted('fecha_cronograma')

            # Sort cuotas by name (e.g., "Cuota 1", "Cuota 2", ...) in ascending order
            cuotas = sorted(cuotas, key=lambda c: c.fecha_cronograma)

            total_debt = cuenta.monto_total or 0.0
            paid_amount = 0.0
            installments_data = []

            # ── New aggregate counters ─────────────────────────────────────
            cuota_total = len(cuotas)
            cuotas_pagadas_count = 0
            cuotas_retrasadas_list = []

            for cuota in cuotas:
                # Compute paid amount
                saldo = getattr(cuota, 'saldo', None) or 0.0
                status = _installment_status(cuota)

                if status == 'PAID':
                    paid_amount += (cuota.monto or 0.0)
                    cuotas_pagadas_count += 1

                if cuota.state == 'retrasado':
                    cuotas_retrasadas_list.append(cuota)

                late_fee = cuota.mora_total if hasattr(cuota, 'mora_total') else 0.0
                paid_at_raw = getattr(cuota, 'real_date', None)
                paid_at = _format_date(paid_at_raw) if paid_at_raw else None

                # Voucher URL
                voucher_url = None
                if cuota.voucher_image:
                    AttachModel = request.env['ir.attachment'].sudo()
                    attach = AttachModel.search([
                        ('res_model', '=', 'adt.comercial.cuotas'),
                        ('res_id', '=', cuota.id),
                        ('res_field', '=', 'voucher_image'),
                    ], limit=1)
                    if attach:
                        base_url = _get_base_url()
                        voucher_url = _public_attachment_url(attach, base_url)

                installments_data.append({
                    'number': cuota.id,
                    'name': cuota.name or '',
                    'dueDate': _format_date(cuota.fecha_cronograma),
                    'amount': cuota.monto or 0.0,
                    'status': status,
                    'paidAt': paid_at,
                    'lateFee': late_fee or 0.0,
                    'lateFeeStatus': _late_fee_status(cuota),
                    'voucherUrl': voucher_url,
                    # Campo 9: suma cuota + mora
                    'totalConMora': round((cuota.monto or 0.0) + (late_fee or 0.0), 2),
                })

            pending_amount = max(0.0, total_debt - paid_amount)
            paid_pct = round((paid_amount / total_debt * 100), 2) if total_debt > 0 else 0.0

            # ── Aggregate values for new fields ───────────────────────────
            qty_cuotas_retrasadas = len(cuotas_retrasadas_list)
            monto_cuotas_retrasadas = round(
                sum((c.saldo or 0.0) for c in cuotas_retrasadas_list), 2
            )

            # Cuota pendiente del período actual: primera que no está retrasada ni pagada
            cuota_pendiente_actual = next(
                (c for c in cuotas if c.state in ('pendiente', 'a_cuenta')), None
            )
            monto_cuota_pendiente = round(
                (cuota_pendiente_actual.saldo or 0.0) if cuota_pendiente_actual else 0.0, 2
            )

            total_pendiente_cobrar = round(monto_cuotas_retrasadas + monto_cuota_pendiente, 2)

            loan_data = {
                'id': str(cuenta.id),
                'referenceNo': cuenta.reference_no or '',
                'state': cuenta.state or '',
                'totalDebt': total_debt,
                'paidAmount': paid_amount,
                'pendingAmount': pending_amount,
                'paidPercentage': paid_pct,
                'currency': 'S/',
                # ── Nuevos campos ──────────────────────────────────────────
                'plate': plate_upper,                               # Campo 3
                'paymentType': cuenta.periodicidad or '',           # Campo 4
                'cuotaTotal': cuota_total,                          # Campo 1
                'cuotasPagadas': cuotas_pagadas_count,              # Campo 2
                'cuotasRetrasadas': qty_cuotas_retrasadas,          # Campo 5
                'montoCuotasRetrasadas': monto_cuotas_retrasadas,   # Campo 6
                'montoCuotaPendiente': monto_cuota_pendiente,       # Campo 7
                'totalPendienteCobrar': total_pendiente_cobrar,     # Campo 8
                # ───────────────────────────────────────────────────────────
                'installments': installments_data,
            }

            # ── Payment accounts (static / config) ───────────────────────
            payment_accounts = _get_payment_accounts()

            # ── Contacts ──────────────────────────────────────────────────
            contacts = _get_support_contacts(cuenta)

            # ── Notifications summary ─────────────────────────────────────
            notifications_domain = _notification_domain_from_token(token_rec)
            unread_count = 0
            if notifications_domain:
                unread_count = request.env['mobile.notification'].sudo().search_count(
                    notifications_domain + [('is_read', '=', False)]
                )

            data = {
                'customer': customer_data,
                'loan': loan_data,
                'paymentAccounts': payment_accounts,
                'contacts': contacts,
                'unreadCount': unread_count,
            }

            return _json_response(_success(data))

        except Exception:
            _logger.exception('Error in GET /v1/loans')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/api/v1/pagos/registrar',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def register_payment(self, **kwargs):
        try:
            raw_body = request.httprequest.data
            body = json.loads(raw_body) if raw_body else {}

            credito_id = body.get('creditoId')
            comprobantes_payload = body.get('comprobante')
            if comprobantes_payload is None:
                comprobantes_payload = body.get('comprobantes')
            monto_total_raw = body.get('montoTotal')
            comentario = (body.get('comentario') or '').strip()
            cuotas_payload = body.get('cuotas') or []

            if not credito_id:
                return _contract_error(400, 'CUOTA_NOT_FOUND', 'creditoId es requerido.', 'creditoId')
            if not isinstance(cuotas_payload, list) or len(cuotas_payload) == 0:
                return _contract_error(400, 'CUOTA_NOT_FOUND', 'Debe enviar al menos una cuota.', 'cuotas')

            # Nuevo formato: comprobante/comprobantes como arreglo de objetos.
            if isinstance(comprobantes_payload, str):
                comprobantes_payload = [{'numero_operacion': comprobantes_payload.strip()}]
            if not isinstance(comprobantes_payload, list) or len(comprobantes_payload) == 0:
                return _contract_error(400, 'COMPROBANTE_DUPLICADO', 'Debe enviar al menos un comprobante.', 'comprobante')

            comprobantes_normalizados = []
            numeros_operacion = []
            for idx, comp in enumerate(comprobantes_payload):
                if not isinstance(comp, dict):
                    return _contract_error(400, 'ESTADO_INCONSISTENTE', 'Formato inválido en comprobante.', 'comprobante[%s]' % idx)

                numero_operacion = (comp.get('numero_operacion') or comp.get('numeroOperacion') or '').strip()
                image_value = None
                if comp.get('image') is not None:
                    image_value = comp.get('image')
                elif comp.get('imagen') is not None:
                    image_value = comp.get('imagen')
                elif comp.get('images') is not None:
                    image_value = comp.get('images')
                elif comp.get('imagenes') is not None:
                    image_value = comp.get('imagenes')
                if not numero_operacion:
                    return _contract_error(400, 'COMPROBANTE_DUPLICADO', 'numero_operacion es requerido.', 'comprobante[%s].numero_operacion' % idx)

                # Soporta image string o images arreglo.
                if isinstance(image_value, list):
                    images = [img for img in image_value if isinstance(img, str) and img.strip()]
                elif image_value:
                    images = [image_value] if isinstance(image_value, str) and image_value.strip() else []
                else:
                    images = []

                if not images:
                    return _contract_error(
                        400,
                        'COMPROBANTE_SIN_IMAGEN',
                        'Cada comprobante debe incluir al menos una imagen válida.',
                        'comprobante[%s].image' % idx,
                    )

                for img in images:
                    comprobantes_normalizados.append({
                        'numero_operacion': numero_operacion,
                        'image': img,
                    })
                numeros_operacion.append(numero_operacion)

            monto_total = _to_decimal(monto_total_raw)
            if monto_total is None:
                return _contract_error(400, 'MONTO_NO_COINCIDE', 'montoTotal no es válido.', 'montoTotal')
            monto_total = _money(monto_total)

            fecha_pago = _parse_iso_datetime(body.get('fechaPago'))
            if body.get('fechaPago') and not fecha_pago:
                return _contract_error(400, 'ESTADO_INCONSISTENTE', 'fechaPago no tiene formato ISO 8601.', 'fechaPago')
            if not fecha_pago:
                fecha_pago = datetime.now()

            cuenta = _resolve_credit_record(credito_id)
            if not cuenta:
                return _contract_error(404, 'CUOTA_NOT_FOUND', 'El crédito no existe.', 'creditoId')

            # a) Verificar cuotas existen y pertenecen al crédito
            cuotas_data = []
            any_partial = False
            sum_pagado = Decimal('0.00')

            for idx, item in enumerate(cuotas_payload):
                cuota_ref = item.get('cuotaId')
                cuota_rec = _resolve_cuota_record(cuenta, cuota_ref)
                if not cuota_rec:
                    return _contract_error(
                        404,
                        'CUOTA_NOT_FOUND',
                        'La cuota no existe o no pertenece al crédito.',
                        'cuotas[%s].cuotaId' % idx,
                    )

                monto_cuota = _to_decimal(item.get('montoCuota'))
                monto_mora = _to_decimal(item.get('montoMora'))
                monto_pagado = _to_decimal(item.get('montoPagado'))
                estado_pago = (item.get('estadoPago') or '').strip().upper()

                if None in (monto_cuota, monto_mora, monto_pagado):
                    return _contract_error(
                        400,
                        'ESTADO_INCONSISTENTE',
                        'Montos inválidos en la cuota enviada.',
                        'cuotas[%s]' % idx,
                    )

                monto_cuota = _money(monto_cuota)
                monto_mora = _money(monto_mora)
                monto_pagado = _money(monto_pagado)
                sum_pagado += monto_pagado

                if estado_pago not in ('PAGADO', 'PARCIAL'):
                    return _contract_error(
                        400,
                        'ESTADO_INCONSISTENTE',
                        'estadoPago debe ser PAGADO o PARCIAL.',
                        'cuotas[%s].estadoPago' % idx,
                    )

                if estado_pago == 'PARCIAL':
                    any_partial = True

                cuotas_data.append({
                    'idx': idx,
                    'cuota': cuota_rec,
                    'monto_cuota': monto_cuota,
                    'monto_mora': monto_mora,
                    'monto_pagado': monto_pagado,
                    'estado_pago': estado_pago,
                    'numero_operacion_cuota': (item.get('numeroOperacionCuota') or item.get('numero_operacion_cuota') or '').strip(),
                    'numero_operacion_mora': (item.get('numeroOperacionMora') or item.get('numero_operacion_mora') or '').strip(),
                })

            # b) Verificar que ninguna cuota esté PAGADO en BD
            for c in cuotas_data:
                if (c['cuota'].state or '').strip().lower() == 'pagado':
                    return _contract_error(
                        409,
                        'CUOTA_YA_PAGADA',
                        'Se intenta pagar una cuota ya pagada.',
                        'cuotas[%s].cuotaId' % c['idx'],
                    )

            # c) Verificar orden de cuotas
            cuotas_credito_ordenadas = sorted(
                cuenta.cuota_ids.filtered(lambda x: x.type == 'cuota'),
                key=lambda x: (x.fecha_cronograma or datetime.max.date(), x.id)
            )
            selected_ids = {c['cuota'].id for c in cuotas_data}

            for c in cuotas_data:
                cuota_actual = c['cuota']
                for cuota_prev in cuotas_credito_ordenadas:
                    if cuota_prev.id == cuota_actual.id:
                        break
                    if (cuota_prev.state or '').strip().lower() != 'pagado' and cuota_prev.id not in selected_ids:
                        return _contract_error(
                            422,
                            'CUOTAS_FUERA_DE_ORDEN',
                            'No puede pagar una cuota dejando cuotas anteriores pendientes.',
                            'cuotas[%s].cuotaId' % c['idx'],
                        )

            # d) Verificar suma montoPagado == montoTotal
            if _money(sum_pagado) != monto_total:
                return _contract_error(400, 'MONTO_NO_COINCIDE', 'La suma de montoPagado no coincide con montoTotal.', 'montoTotal')

            # e) Recalcular mora y comparar
            for c in cuotas_data:
                server_mora = _compute_server_mora(c['cuota'], fecha_pago)
                if _money(server_mora) != _money(c['monto_mora']):
                    return _contract_error(
                        400,
                        'MORA_INCORRECTA',
                        'montoMora no coincide con el cálculo del servidor.',
                        'cuotas[%s].montoMora' % c['idx'],
                    )

            # f) Verificar coherencia estadoPago vs montos
            for c in cuotas_data:
                total_cuota = _money(c['monto_cuota'] + c['monto_mora'])
                if c['estado_pago'] == 'PAGADO' and _money(c['monto_pagado']) != total_cuota:
                    return _contract_error(
                        400,
                        'ESTADO_INCONSISTENTE',
                        'Para estado PAGADO, montoPagado debe ser igual a montoCuota + montoMora.',
                        'cuotas[%s].montoPagado' % c['idx'],
                    )
                if c['estado_pago'] == 'PARCIAL' and _money(c['monto_pagado']) >= total_cuota:
                    return _contract_error(
                        400,
                        'ESTADO_INCONSISTENTE',
                        'Para estado PARCIAL, montoPagado debe ser menor a montoCuota + montoMora.',
                        'cuotas[%s].montoPagado' % c['idx'],
                    )

            # g) Verificar comentario si hay PARCIAL
            if any_partial and not comentario:
                return _contract_error(400, 'COMENTARIO_REQUERIDO', 'El comentario es obligatorio cuando hay cuotas parciales.', 'comentario')

            # h) Verificar comprobante duplicado
            payment_exist = request.env['account.payment'].sudo().search([
                ('ref', 'in', list(set(numeros_operacion)))
            ], limit=1)
            pending_exist = request.env['adt.comercial.cuotas.pendientes.comprobante'].sudo().search([
                ('numero_operacion', 'in', list(set(numeros_operacion)))
            ], limit=1)
            if payment_exist or pending_exist:
                return _contract_error(409, 'COMPROBANTE_DUPLICADO', 'El número de comprobante ya fue registrado.', 'comprobante')

            # i) Persistir y retornar response (registro pendiente para validacion)
            cuota_results = []
            pago_id = str(uuid.uuid4())

            for c in cuotas_data:
                cuota = c['cuota']
                monto_mora = _money(c['monto_mora'])
                pendiente = request.env['adt.comercial.cuotas.pendientes'].sudo().create({
                    'cuota_id': cuota.id,
                    'monto_cuota': float(_money(c['monto_cuota'])),
                    'numero_operacion_cuota': c['numero_operacion_cuota'] or comprobantes_normalizados[0]['numero_operacion'],
                    'monto_mora': float(monto_mora),
                    'numero_operacion_mora': c['numero_operacion_mora'] or False,
                    'fecha': fecha_pago,
                    'comentario': comentario or False,
                    'estado': 'PENDIENTE_VALIDAR',
                })

                comprobante_urls = []
                for comp in comprobantes_normalizados:
                    comprobante_line = request.env['adt.comercial.cuotas.pendientes.comprobante'].sudo().create({
                        'pendiente_id': pendiente.id,
                        'numero_operacion': comp['numero_operacion'],
                        'image': comp['image'],
                    })
                    image_url = _build_attachment_url(
                        'adt.comercial.cuotas.pendientes.comprobante',
                        comprobante_line.id,
                        'image',
                    )
                    if image_url:
                        comprobante_urls.append(image_url)

                # Guardar en la cuota una lista JSON con las URLs de comprobantes.
                # Si ya existen URLs previas, se agregan sin duplicar.
                existing_urls = []
                try:
                    if cuota.voucher_image_urls:
                        parsed = json.loads(cuota.voucher_image_urls)
                        if isinstance(parsed, list):
                            existing_urls = [u for u in parsed if u]
                        elif isinstance(parsed, str) and parsed.strip():
                            existing_urls = [parsed.strip()]
                except Exception:
                    # Compatibilidad: si el valor anterior no es JSON, conservarlo como string simple.
                    raw_prev = (cuota.voucher_image_urls or '').strip()
                    if raw_prev:
                        existing_urls = [raw_prev]
                    _logger.warning('No se pudo parsear voucher_image_urls previo de cuota %s; se conservará valor previo como texto.', cuota.id)

                merged_urls = list(dict.fromkeys(existing_urls + comprobante_urls))
                cuota.sudo().write({'voucher_image_urls': json.dumps(merged_urls, ensure_ascii=False)})
                _logger.info(
                    'Cuota %s actualizada con %d URL(s) de comprobante (total guardado: %d).',
                    cuota.id, len(comprobante_urls), len(merged_urls)
                )

                request.env['adt.comercial.cuotas.pendientes'].sudo()._sync_cuota_pendiente_validar(cuota)

                saldo_pendiente = _money(c['monto_cuota'] + c['monto_mora'] - c['monto_pagado'])
                if saldo_pendiente < Decimal('0.00'):
                    saldo_pendiente = Decimal('0.00')

                if saldo_pendiente == Decimal('0.00'):
                    estado_result = 'PAGADO'
                elif _money(c['monto_pagado']) > Decimal('0.00'):
                    estado_result = 'PARCIAL'
                else:
                    estado_result = 'PENDIENTE'

                cuota_results.append({
                    'cuotaId': str(cuota.id),
                    'estado': estado_result,
                    'montoPagado': float(_money(c['monto_pagado'])),
                    'saldoPendiente': float(saldo_pendiente),
                    'voucherUrls': merged_urls,
                })

            response = {
                'pagoId': pago_id,
                'comprobante': [{'numero_operacion': n} for n in list(dict.fromkeys(numeros_operacion))],
                'montoTotal': float(monto_total),
                'fechaPago': fecha_pago.replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'cuotas': cuota_results,
            }
            return _json_response(_success(response), status=200)

        except Exception:
            _logger.exception('Error in POST /api/v1/pagos/registrar')
            return _contract_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.')

    # ══════════════════════════════════════════════════════════════════════════
    # HU-003 — GET /v1/documents?plate=ABC-123
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/documents',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_documents(self, plate=None, **kwargs):
        """
        Returns the list of documents linked to the expediente of the vehicle's driver.
        Requires Authorization: Bearer <token>
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            plate_upper, plate_err = _validate_plate(plate)
            if plate_err:
                return _json_response(plate_err, status=plate_err['statusCode'])

            vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
            if vehicle_err:
                return _json_response(vehicle_err, status=vehicle_err['statusCode'])

            partner = vehicle.driver_id
            documents_data = []

            if partner:
                # Try to find an expediente linked to this partner
                try:
                    ExpModel = request.env['adt.expediente'].sudo()
                    expediente = ExpModel.search([('cliente_id', '=', partner.id)], limit=1)
                    if expediente:
                        documents_data = _build_expediente_documents(expediente)
                except Exception:
                    _logger.warning('Could not query adt.expediente for partner %s', partner.id)

            # Also include specific vehicle attachments (Tarjeta de Propiedad, Chip GNV, SOAT)
            try:
                base_url = _get_base_url()
                # fields on fleet.vehicle that can contain pdf/image
                VEHICLE_DOC_FIELDS = [
                    ('tarjeta_propiedad_attachment', 'Tarjeta de Propiedad', 'GUARANTEE'),
                    ('chip_gnv_attachment', 'Chip GNV', 'OTHER'),
                    ('soat_attachment', 'SOAT', 'GUARANTEE'),
                ]

                # Only proceed if we have a vehicle record
                if vehicle:
                    AttachModel = request.env['ir.attachment'].sudo()
                    for field_name, display_name, doc_type in VEHICLE_DOC_FIELDS:
                        try:
                            field_val = getattr(vehicle, field_name, None)
                        except Exception:
                            field_val = None

                        if not field_val:
                            continue

                        # try to find a matching attachment record
                        attach = AttachModel.search([
                            ('res_model', '=', 'fleet.vehicle'),
                            ('res_id', '=', vehicle.id),
                            ('res_field', '=', field_name),
                        ], limit=1)

                        if attach:
                            url = _public_attachment_url(attach, base_url)
                            size_kb = int((attach.file_size or 0) / 1024)
                            mime = attach.mimetype or 'application/octet-stream'
                            uploaded_at = _format_datetime(attach.create_date)
                        else:
                            # fallback to the web image/url route for binary fields
                            url = '%s/web/image/fleet.vehicle/%d/%s' % (base_url, vehicle.id, field_name)
                            size_kb = 0
                            mime = 'application/octet-stream'
                            uploaded_at = _format_datetime(vehicle.create_date if hasattr(vehicle, 'create_date') else None)

                        owner_id = expediente.id if 'expediente' in locals() and expediente else vehicle.id
                        doc_idx = len(documents_data)
                        documents_data.append({
                            'id': 'doc-%d-%d' % (owner_id, doc_idx),
                            'name': display_name,
                            'type': doc_type,
                            'mimeType': mime,
                            'sizeKb': size_kb,
                            'url': url,
                            'urlExpiresAt': None,  # Odoo URLs don't expire
                            'uploadedAt': uploaded_at,
                        })

                    # Documentos del contrato (adt.comercial.cuentas.contrato_ids) de la cuenta activa del vehículo
                    CuentaModel = request.env['adt.comercial.cuentas'].sudo()
                    cuenta = CuentaModel.search(
                        [('vehiculo_id', '=', vehicle.id), ('state', 'in', ('en_curso', 'aprobado'))],
                        limit=1,
                    )
                    if not cuenta:
                        cuenta = CuentaModel.search(
                            [('vehiculo_id', '=', vehicle.id), ('state', '!=', 'cancelado')],
                            limit=1,
                        )

                    if cuenta and cuenta.contrato_ids:
                        for attach in cuenta.contrato_ids:
                            url = _public_attachment_url(attach, base_url)
                            size_kb = int((attach.file_size or 0) / 1024)
                            mime = attach.mimetype or 'application/octet-stream'
                            uploaded_at = _format_datetime(attach.create_date)

                            doc_idx = len(documents_data)
                            documents_data.append({
                                'id': 'doc-%d-%d' % (cuenta.id, doc_idx),
                                'name': attach.name,
                                'type': 'CONTRACT',
                                'mimeType': mime,
                                'sizeKb': size_kb,
                                'url': url,
                                'urlExpiresAt': None,  # Odoo URLs don't expire
                                'uploadedAt': uploaded_at,
                            })
            except Exception:
                _logger.exception('Error while building vehicle documents for GET /v1/documents')

            data = {'documents': documents_data}
            return _json_response(_success(data))

        except Exception:
            _logger.exception('Error in GET /v1/documents')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # GET /v1/vehicles/captura-status?plate=ABC-123
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/vehicles/captura-status',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_vehicle_captura_status(self, plate=None, **kwargs):
        """
        Indica si el vehículo está actualmente en captura (con los motivos) y
        cuántas capturas anteriores tuvo, para mostrar en un full screen de
        alerta antes de operar sobre el vehículo/cuenta.

        Requiere el módulo adt_captura instalado (adt.captura.record).
        Requires Authorization: Bearer <token>
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            plate_upper, plate_err = _validate_plate(plate)
            if plate_err:
                return _json_response(plate_err, status=plate_err['statusCode'])

            vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
            if vehicle_err:
                return _json_response(vehicle_err, status=vehicle_err['statusCode'])

            if 'adt.captura.record' not in request.env:
                return _json_response(
                    _error(503, 'CAPTURA_MODULE_NOT_AVAILABLE',
                           'El módulo de capturas no está instalado.'),
                    status=503,
                )

            CapturaModel = request.env['adt.captura.record'].sudo()
            capturas = CapturaModel.search(
                [('vehicle_id', '=', vehicle.id)], order='create_date desc'
            )

            current = capturas.filtered(lambda c: c.state == 'capturado')[:1]
            previous = capturas - current

            data = {
                'plate': plate_upper,
                'vehicleId': vehicle.id,
                'isInCaptura': bool(current),
                'currentCapture': _serialize_captura_record(current[0]) if current else None,
                'previousCapturesCount': len(previous),
                'previousCaptures': [_serialize_captura_record(c) for c in previous],
            }
            return _json_response(_success(data))

        except Exception:
            _logger.exception('Error in GET /v1/vehicles/captura-status')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-004 — GET /v1/promotions
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/promotions',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_promotions(self, page=1, pageSize=20, **kwargs):
        """
        Returns the list of currently active promotions, ordered by priority.
        Requires Authorization: Bearer <token>
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            try:
                page = max(1, int(page))
                page_size = max(1, min(50, int(pageSize)))
            except (ValueError, TypeError):
                return _json_response(
                    _error(400, 'BAD_REQUEST', 'Parámetros de paginación inválidos.'), status=400)

            now = odoo_fields.Datetime.now()
            PromoModel = request.env['mobile.promotion'].sudo()
            domain = [
                ('active', '=', True),
                ('active_from', '<=', now),
                ('active_to', '>=', now),
            ]

            total_items = PromoModel.search_count(domain)
            total_pages = max(1, -(-total_items // page_size))  # ceiling division
            offset = (page - 1) * page_size

            promos = PromoModel.search(domain, limit=page_size, offset=offset, order='priority asc')

            promotions_data = []
            for promo in promos:
                promotions_data.append({
                    'id': promo.name,
                    'title': promo.title,
                    'body': promo.body,
                    'imageUrl': promo.image_url or None,
                    'deepLink': promo.deep_link or None,
                    'externalUrl': promo.external_url or None,
                    'linkType': promo.link_type,
                    'activeFrom': _format_datetime(promo.active_from),
                    'activeTo': _format_datetime(promo.active_to),
                    'priority': promo.priority,
                })

            pagination = {
                'page': page,
                'pageSize': page_size,
                'totalItems': total_items,
                'totalPages': total_pages,
                'hasNext': page < total_pages,
                'hasPrev': page > 1,
            }

            data = {'promotions': promotions_data}
            return _json_response(_success(data, pagination=pagination))

        except Exception:
            _logger.exception('Error in GET /v1/promotions')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-013 — GET /v1/app-images
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/app-images',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_app_images(self, code=None, **kwargs):
        """
        Devuelve las imágenes configuradas en mobile.app.image (subidas desde Odoo).

        - GET /v1/app-images          -> lista todas las imágenes activas, ordenadas por secuencia.
        - GET /v1/app-images?code=xxx -> devuelve una sola imagen por su código.

        Endpoint público: no requiere Authorization, ya que se consume antes del login
        (ej. splash screen, banners previos a iniciar sesión).
        """
        try:
            ImageModel = request.env['mobile.app.image'].sudo()
            domain = [('active', '=', True)]
            if code:
                # '=ilike' evita fallos por diferencia de mayúsculas/minúsculas
                # entre el código enviado por la app y el guardado en Odoo.
                domain.append(('code', '=ilike', code))

            images = ImageModel.search(domain, order='sequence asc, id asc')

            if code and not images:
                return _json_response(
                    _error(404, 'APP_IMAGE_NOT_FOUND', 'No existe una imagen activa con ese código.'),
                    status=404,
                )

            base_url = _get_base_url()
            images_data = []
            for img in images:
                images_data.append({
                    'code': img.code,
                    'name': img.name,
                    'description': img.description or None,
                    'imageUrl': '%s/v1/app-images/%s/file' % (base_url, quote_plus(img.code)),
                    'updatedAt': _format_datetime(img.write_date),
                })

            if code:
                return _json_response(_success(images_data[0]))

            return _json_response(_success({'images': images_data}))

        except Exception:
            _logger.exception('Error in GET /v1/app-images')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/app-images/<string:code>/file',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_app_image_file(self, code, **kwargs):
        """
        Sirve el binario de la imagen directamente (sin access_token ni /web/content),
        para que la app pueda usar esta URL tal cual en un <img>/Image.network/Coil.

        Nosotros controlamos el Content-Type y el Content-Disposition, evitando
        depender del comportamiento del controlador binario nativo de Odoo.
        """
        try:
            img = request.env['mobile.app.image'].sudo().search([
                ('active', '=', True),
                ('code', '=ilike', code),
            ], limit=1)
            if not img or not img.image:
                return request.not_found()

            attach = request.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'mobile.app.image'),
                ('res_id', '=', img.id),
                ('res_field', '=', 'image'),
            ], limit=1)
            mimetype = (attach.mimetype if attach else None) or 'image/png'
            filename = img.image_filename or (attach.name if attach else None) or ('%s.png' % img.code)

            data = base64.b64decode(img.image)
            return request.make_response(
                data,
                headers=[
                    ('Content-Type', mimetype),
                    ('Content-Disposition', 'inline; filename="%s"' % filename),
                    ('Cache-Control', 'public, max-age=3600'),
                ],
            )
        except Exception:
            _logger.exception('Error in GET /v1/app-images/%s/file', code)
            return request.not_found()

    # ══════════════════════════════════════════════════════════════════════════
    # HU-005 — GET /v1/notifications
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/notifications',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_notifications(self, page=1, pageSize=20, unreadOnly='false', **kwargs):
        """
        Returns the notifications for the authenticated user's partner/vehicle.
        Requires Authorization: Bearer <token>
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            try:
                page = max(1, int(page))
                page_size = max(1, min(100, int(pageSize)))
            except (ValueError, TypeError):
                return _json_response(
                    _error(400, 'BAD_REQUEST', 'Parámetros de paginación inválidos.'), status=400)

            unread_filter = str(unreadOnly).lower() in ('true', '1')

            # Build domain using the token's linked partner or vehicle
            domain = _notification_domain_from_token(token_rec)
            if not domain:
                # No association → return empty
                data = {'unreadCount': 0, 'notifications': []}
                pagination = {
                    'page': 1, 'pageSize': page_size,
                    'totalItems': 0, 'totalPages': 1,
                    'hasNext': False, 'hasPrev': False,
                }
                return _json_response(_success(data, pagination=pagination))

            NotifModel = request.env['mobile.notification'].sudo()
            unread_count = NotifModel.search_count(domain + [('is_read', '=', False)])

            if unread_filter:
                domain.append(('is_read', '=', False))

            total_items = NotifModel.search_count(domain)
            total_pages = max(1, -(-total_items // page_size))
            offset = (page - 1) * page_size

            notifs = NotifModel.search(domain, limit=page_size, offset=offset, order='created_at desc')

            notifications_data = []
            for n in notifs:
                notifications_data.append({
                    'id': 'notif-%d' % n.id,
                    'title': n.title,
                    'body': n.body,
                    'type': n.notification_type,
                    'deepLink': n.deep_link or None,
                    'externalUrl': n.external_url or None,
                    'linkType': n.link_type,
                    'read': n.is_read,
                    'createdAt': _format_datetime(n.created_at),
                })

            pagination = {
                'page': page,
                'pageSize': page_size,
                'totalItems': total_items,
                'totalPages': total_pages,
                'hasNext': page < total_pages,
                'hasPrev': page > 1,
            }

            data = {'unreadCount': unread_count, 'notifications': notifications_data}
            return _json_response(_success(data, pagination=pagination))

        except Exception:
            _logger.exception('Error in GET /v1/notifications')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-006 — POST /v1/auth/logout
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/auth/logout',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def logout(self, **kwargs):
        """
        Revokes the mobile token and optionally targets a specific device.
        Body JSON (flat): { "plate": "ABC-123", "deviceId": "<optional>" }
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')

            # request.jsonrequest holds the full parsed JSON body dict
            body = request.jsonrequest if hasattr(request, 'jsonrequest') and request.jsonrequest else {}

            plate = body.get('plate')
            device_id = body.get('deviceId')

            # Validate plate if provided
            if plate:
                plate_upper, plate_err = _validate_plate(plate)
                if plate_err:
                    return plate_err
            else:
                plate_upper = None

            # Get token
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return token_err

            # Check if already revoked
            if token_rec.revoked:
                return _error(409, 'SESSION_ALREADY_CLOSED', 'La sesión ya fue cerrada previamente.')

            # Revoke
            if device_id:
                matched = token_rec.filtered(lambda t: t.device_id == device_id)
                if matched:
                    matched.revoke()
                else:
                    token_rec.revoke()
            else:
                TokenModel = request.env['mobile.token'].sudo()
                additional_domain = [('revoked', '=', False)]
                if token_rec.vehicle_id:
                    additional_domain.append(('vehicle_id', '=', token_rec.vehicle_id.id))
                elif token_rec.partner_id:
                    additional_domain.append(('partner_id', '=', token_rec.partner_id.id))
                all_tokens = TokenModel.search(additional_domain)
                all_tokens.revoke()

            data = {'loggedOutAt': _now_iso()}
            return _success(data, message='Sesión cerrada correctamente.')

        except Exception:
            _logger.exception('Error in POST /v1/auth/logout')
            return _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.')

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: POST /v1/auth/login  (utility endpoint to get a token)
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/auth/login',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def login(self, **kwargs):
        """
        Utility endpoint to generate a mobile token by plate.
        Body JSON (flat, no jsonrpc wrapper needed): { "plate": "ABC-123" }
        No real authentication – designed for internal/partner use.
        Returns: { "token": "<token>", "vehicle_id": <int>, "partner_id": <int> }
        """
        try:
            # request.jsonrequest holds the full parsed JSON body dict
            body = request.jsonrequest if hasattr(request, 'jsonrequest') and request.jsonrequest else {}

            plate = body.get('plate')
            plate_upper, plate_err = _validate_plate(plate)
            if plate_err:
                return plate_err

            vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
            if vehicle_err:
                return vehicle_err

            # Device info from headers
            device_model = request.httprequest.headers.get('X-Device-Model', '')
            device_id_header = request.httprequest.headers.get('X-Device-ID', '')
            platform = request.httprequest.headers.get('X-Platform', '')
            app_version = request.httprequest.headers.get('X-App-Version', '')

            # Create token (valid for 90 days)
            from datetime import timedelta
            TokenModel = request.env['mobile.token'].sudo()
            new_token = TokenModel.generate_token()
            expires = odoo_fields.Datetime.now() + timedelta(days=90)

            token_rec = TokenModel.create({
                'token': new_token,
                'vehicle_id': vehicle.id,
                'partner_id': vehicle.driver_id.id if vehicle.driver_id else False,
                'device_id': device_id_header or False,
                'device_model': device_model or False,
                'platform': platform or False,
                'app_version': app_version or False,
                'expires_at': expires,
            })

            data = {
                'token': new_token,
                'vehicleId': vehicle.id,
                'licensePlate': vehicle.license_plate,
                'partnerId': vehicle.driver_id.id if vehicle.driver_id else None,
                'partnerName': vehicle.driver_id.name if vehicle.driver_id else None,
                'expiresAt': _format_datetime(expires),
            }
            return _success(data, message='Token generado correctamente.')

        except Exception:
            _logger.exception('Error in POST /v1/auth/login')
            return _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.')

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: POST /v1/notifications/{id}/read
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/notifications/<int:notification_id>/read',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def mark_notification_read(self, notification_id, **kwargs):
        """
        Marks a notification as read.
        Requires Authorization: Bearer <token>
        Returns plain JSON (no jsonrpc wrapper).
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            NotifModel = request.env['mobile.notification'].sudo()
            notif = NotifModel.browse(notification_id)
            if not notif.exists():
                return _json_response(_error(404, 'NOT_FOUND', 'Notificación no encontrada.'), status=404)

            domain = _notification_domain_from_token(token_rec)
            if not domain:
                return _json_response(
                    _error(403, 'FORBIDDEN', 'El token autenticado no está asociado a notificaciones.'),
                    status=403,
                )

            owned_notif = NotifModel.search(domain + [('id', '=', notification_id)], limit=1)
            if not owned_notif:
                return _json_response(
                    _error(403, 'FORBIDDEN', 'No tiene permisos para marcar esta notificación.'),
                    status=403,
                )

            owned_notif.mark_as_read()
            unread_count = NotifModel.search_count(domain + [('is_read', '=', False)])
            return _json_response(_success(
                {
                    'id': 'notif-%d' % notification_id,
                    'read': True,
                    'unreadCount': unread_count,
                },
                message='Notificación marcada como leída.',
            ))
        except Exception:
            _logger.exception('Error in POST /v1/notifications/%s/read', notification_id)
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-011 — POST /v1/notifications/read-all
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/notifications/read-all',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def mark_all_notifications_read(self, **kwargs):
        """
        Marks all notifications as read for the authenticated token scope.
        Requires Authorization: Bearer <token>
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            domain = _notification_domain_from_token(token_rec)
            if not domain:
                return _json_response(
                    _error(403, 'FORBIDDEN', 'El token autenticado no está asociado a notificaciones.'),
                    status=403,
                )

            NotifModel = request.env['mobile.notification'].sudo()
            unread_recs = NotifModel.search(domain + [('is_read', '=', False)])
            marked_count = len(unread_recs)

            if unread_recs:
                unread_recs.write({'is_read': True})

            unread_count = NotifModel.search_count(domain + [('is_read', '=', False)])

            return _json_response(_success(
                {
                    'read': True,
                    'markedCount': marked_count,
                    'unreadCount': unread_count,
                },
                message='Todas las notificaciones fueron marcadas como leídas.',
            ))
        except Exception:
            _logger.exception('Error in POST /v1/notifications/read-all')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-004 — POST /v1/promotions
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/promotions',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def create_promotion(self, **kwargs):
        """
        Creates a new promotion. If the promotion is for WhatsApp, it will include a green button styled like WhatsApp.
        Otherwise, the button color will be configurable from the Odoo module.
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            body = request.jsonrequest if hasattr(request, 'jsonrequest') and request.jsonrequest else {}

            title = body.get('title')
            body_text = body.get('body')
            link_type = body.get('linkType')
            deep_link = body.get('deepLink')
            external_url = body.get('externalUrl')

            if not title or not body_text or not link_type:
                return _json_response(
                    _error(400, 'BAD_REQUEST', 'Faltan campos obligatorios: title, body, linkType.'),
                    status=400
                )

            PromoModel = request.env['mobile.promotion'].sudo()
            new_promo = PromoModel.create({
                'title': title,
                'body': body_text,
                'link_type': link_type,
                'deep_link': deep_link,
                'external_url': external_url,
                'button_color': 'green' if link_type == 'whatsapp' else 'configurable',
            })

            data = {
                'id': new_promo.id,
                'title': new_promo.title,
                'body': new_promo.body,
                'linkType': new_promo.link_type,
                'buttonColor': new_promo.button_color,
            }

            return _json_response(_success(data, message='Promoción creada exitosamente.'))

        except Exception:
            _logger.exception('Error in POST /v1/promotions')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    # ══════════════════════════════════════════════════════════════════════════
    # HU-007 — POST /v1/installments/upload_voucher
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/installments/upload_voucher',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def upload_voucher(self, **kwargs):
        try:
            # Parsear body JSON manualmente
            body = request.httprequest.data
            data = json.loads(body) if body else {}

            cuota_id = data.get('cuota_id')
            cuenta_id = data.get('cuenta_id')
            voucher_image = data.get('voucher_image')

            _logger.info(f"Received cuota_id: {cuota_id}")
            _logger.info(f"Received cuenta_id: {cuenta_id}")
            _logger.info(f"Received voucher_image: {voucher_image}")

            if not voucher_image:
                _logger.warning('Validation failed:  voucher_image missing.')
                return _json_response(
                    _error(400, 'VALIDATION_ERROR', 'cuota_id y voucher_image son obligatorios.'),
                    status=400
                )

            if not cuota_id:
                _logger.warning('Validation failed: cuota_id missing.')
                return _json_response(
                    _error(400, 'VALIDATION_ERROR', 'cuota_id y voucher_image son obligatorios.'),
                    status=400
                )

            _logger.info('Fetching cuota with ID: %s', cuota_id)
            CuotaModel = request.env['adt.comercial.cuotas'].sudo()
            cuota = CuotaModel.browse(int(cuota_id))

            if not cuota.exists():
                _logger.warning('Cuota with ID %s does not exist.', cuota_id)
                return _json_response(
                    _error(404, 'NOT_FOUND', 'La cuota especificada no existe.'),
                    status=404
                )

            _logger.info('Updating voucher_image for cuota ID: %s', cuota_id)
            cuota.write({'voucher_image': voucher_image})

            _logger.info('Voucher uploaded successfully for cuota ID: %s', cuota_id)
            return _json_response(
                _success({}, 'Voucher subido exitosamente.')
            )

        except Exception as e:
            _logger.exception('Error en POST /v1/installments/upload_voucher: %s', str(e))
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'),
                status=500
            )

    # ══════════════════════════════════════════════════════════════════════════
    # HU-008 — POST /v1/maintenance/record
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/maintenance/record',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def maintenance_record(self, **kwargs):
        """
        Handles the creation or update of vehicle maintenance records and lines.
        """
        try:
            body = request.jsonrequest if hasattr(request, 'jsonrequest') and request.jsonrequest else {}

            vehicle_id = body.get('vehicle_id')
            km_objetivo = body.get('km_objetivo')
            realizado = body.get('realizado', False)
            attachment_ids = body.get('attachment_ids', [])
            fecha_inicio = body.get('fecha_inicio')
            fecha_fin = body.get('fecha_fin')

            if not vehicle_id or not km_objetivo or not fecha_inicio or not fecha_fin:
                return _json_response(
                    _error(400, 'VALIDATION_ERROR', 'vehicle_id, km_objetivo, fecha_inicio y fecha_fin son obligatorios.'),
                    status=400
                )

            MaintenanceRecordModel = request.env['adt.tvs.vehicle_maintenance_record'].sudo()
            existing_record = MaintenanceRecordModel.search([('vehicle_id', '=', vehicle_id)], limit=1)

            if existing_record:
                # Add a new line to the existing record
                existing_record.line_ids.create({
                    'record_id': existing_record.id,
                    'km_objetivo': km_objetivo,
                    'realizado': realizado,
                    'attachment_ids': [(6, 0, attachment_ids)],
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': fecha_fin,
                })
            else:
                # Fetch vehicle details from fleet.model
                FleetModel = request.env['fleet.vehicle'].sudo()
                vehicle = FleetModel.search([('id', '=', vehicle_id)], limit=1)

                if not vehicle:
                    return _json_response(
                        _error(404, 'VEHICLE_NOT_FOUND', 'El vehículo especificado no existe.'),
                        status=404
                    )

                # Create a new record with the fetched vehicle data
                new_record = MaintenanceRecordModel.create({
                    'vehicle_id': vehicle.id,
                    'conductor_id': vehicle.driver_id.id if vehicle.driver_id else None,
                    'chassis': vehicle.vin_sn or '',
                    'motor':  '',  # Replace missing engine_no with an empty string
                    'placa': vehicle.license_plate or '',
                    'estado_mantenimiento': 'tvs',
                    'line_ids': [(0, 0, {
                        'km_objetivo': km_objetivo,
                        'realizado': realizado,
                        'attachment_ids': [(6, 0, attachment_ids)],
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin': fecha_fin,
                    })],
                })

            return _json_response(_success({}, 'Registro de mantenimiento procesado exitosamente.'))

        except Exception as e:
            _logger.exception('Error en POST /v1/maintenance/record: %s', str(e))
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'),
                status=500
            )

    # ══════════════════════════════════════════════════════════════════════════
    # HU-009 — GET /v1/maintenance/lines
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/maintenance/lines',
        type='http',  # Changed from 'json' to 'http'
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def get_maintenance_lines(self, **kwargs):
        """
        Fetches all maintenance lines for a given vehicle_id from headers.
        """
        try:
            vehicle_id = kwargs.get('vehicle_id')
            vehicle_id = int(vehicle_id)
            if not vehicle_id:
                return _json_response(
                    _error(400, 'VALIDATION_ERROR', 'El parámetro vehicle_id es obligatorio.'),
                    status=400
                )

            _logger.info(f"vehicle_id {vehicle_id}")
            MaintenanceRecordModel = request.env['adt.tvs.vehicle_maintenance_record'].sudo()
            record = MaintenanceRecordModel.search([('vehicle_id', '=', vehicle_id)], limit=1)
            _logger.info(f"Found {len(record)} maintenance lines for vehicle_id {vehicle_id}")

            lines_data = []
            for line in record.line_ids:
                lines_data.append({
                    'id': line.id,
                    'km_objetivo': line.km_objetivo,
                    'realizado': line.realizado,
                    'attachment_ids': [attachment.id for attachment in line.attachment_ids],
                    'fecha_inicio': _format_date(line.fecha_inicio),
                    'fecha_fin': _format_date(line.fecha_fin),
                })

            return  _json_response(_success(lines_data, 'Líneas de mantenimiento obtenidas exitosamente.'))

        except Exception as e:
            _logger.exception('Error en GET /v1/maintenance/lines: %s', str(e))
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'),
                status=500
            )

    # ══════════════════════════════════════════════════════════════════════════
    # HU-010 — POST /v1/fcm/register
    # ══════════════════════════════════════════════════════════════════════════
    @http.route(
        '/v1/papeletas/register',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def register_papeleta(self, **kwargs):
        """
        Registra una papeleta con una o varias fotos.

        Request JSON:
        {
          "numeroPapeleta": "PAP-001",
          "fechaPapeleta": "2026-05-18",
          "monto": 150.00,
          "idVehiculo": 10,
          "fotos": ["<base64>", "<base64>"]
        }
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            raw_body = request.httprequest.data
            body = json.loads(raw_body) if raw_body else {}
            if not isinstance(body, dict):
                return _json_response(
                    _error(400, 'BAD_REQUEST', 'El cuerpo del request debe ser un objeto JSON.'),
                    status=400,
                )

            numero = str(
                body.get('numeroPapeleta') or body.get('numero_papeleta') or body.get('name') or ''
            ).strip()
            fecha = body.get('fechaPapeleta') or body.get('fecha_papeleta')
            monto = _to_decimal(body.get('monto'))
            vehicle_id_raw = body.get('idVehiculo') if body.get('idVehiculo') is not None else body.get('vehicle_id')
            fotos_payload = body.get('fotos') if body.get('fotos') is not None else body.get('foto')

            if not numero:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'numeroPapeleta es requerido.'),
                    status=422,
                )

            if not fecha:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'fechaPapeleta es requerida.'),
                    status=422,
                )

            fecha_dt = _parse_iso_datetime(fecha)
            if fecha_dt:
                fecha_val = fecha_dt.date()
            else:
                try:
                    fecha_val = datetime.strptime(str(fecha), '%Y-%m-%d').date()
                except Exception:
                    return _json_response(
                        _error(422, 'VALIDATION_ERROR', 'fechaPapeleta debe tener formato YYYY-MM-DD o ISO 8601.'),
                        status=422,
                    )

            if monto is None or _money(monto) <= Decimal('0.00'):
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'monto debe ser mayor a 0.'),
                    status=422,
                )

            try:
                vehicle_id = int(vehicle_id_raw)
            except Exception:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'idVehiculo es requerido y debe ser numérico.'),
                    status=422,
                )

            vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id)
            if not vehicle.exists():
                return _json_response(
                    _error(404, 'VEHICLE_NOT_FOUND', 'El vehículo indicado no existe.'),
                    status=404,
                )

            if token_rec.vehicle_id and token_rec.vehicle_id.id != vehicle.id:
                return _json_response(
                    _error(403, 'FORBIDDEN', 'El token no tiene permiso para registrar papeletas en este vehículo.'),
                    status=403,
                )

            if isinstance(fotos_payload, str):
                fotos_payload = [fotos_payload]
            if not isinstance(fotos_payload, list) or not fotos_payload:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'fotos debe contener al menos una imagen en base64.'),
                    status=422,
                )

            fotos = []
            for idx, foto in enumerate(fotos_payload):
                normalized = _normalize_base64_image(foto)
                if not normalized:
                    return _json_response(
                        _error(422, 'VALIDATION_ERROR', 'Imagen base64 inválida.', details=[{'field': 'fotos[%s]' % idx}]),
                        status=422,
                    )
                fotos.append(normalized)

            PapeletaModel = request.env['adt.papeleta'].sudo()
            if PapeletaModel.search_count([('name', '=', numero)]) > 0:
                return _json_response(
                    _error(409, 'PAPELETA_DUPLICADA', 'El número de papeleta ya existe.'),
                    status=409,
                )

            papeleta = PapeletaModel.create({
                'name': numero,
                'fecha_papeleta': fecha_val,
                'monto': float(_money(monto)),
                'vehicle_id': vehicle.id,
            })

            AttachModel = request.env['ir.attachment'].sudo()
            attachment_ids = []
            for idx, foto in enumerate(fotos, 1):
                attach = AttachModel.create({
                    'name': 'papeleta_%s_%s.jpg' % (papeleta.id, idx),
                    'type': 'binary',
                    'datas': foto,
                    'res_model': 'adt.papeleta',
                    'res_id': papeleta.id,
                    'mimetype': 'image/jpeg',
                })
                attachment_ids.append(attach.id)

            if attachment_ids:
                papeleta.write({'attachment_ids': [(6, 0, attachment_ids)]})

            base_url = _get_base_url()
            attach_records = AttachModel.browse(attachment_ids)
            urls = [_public_attachment_url(att, base_url) for att in attach_records]

            _notify_papeleta_channel(
                papeleta=papeleta,
                vehicle=vehicle,
                token_rec=token_rec,
                foto_urls=urls,
            )

            return _json_response(_success({
                'id': papeleta.id,
                'numeroPapeleta': papeleta.name,
                'fechaPapeleta': _format_date(papeleta.fecha_papeleta),
                'monto': float(_money(papeleta.monto)),
                'idVehiculo': papeleta.vehicle_id.id,
                'fotosCount': len(attachment_ids),
                'fotoUrls': urls,
            }, message='Papeleta registrada correctamente.'))

        except Exception:
            _logger.exception('Error in POST /v1/papeletas/register')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/papeletas',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def list_papeletas(self, **kwargs):
        """
        Lista las papeletas de un vehículo.
        Query params opcionales: idVehiculo o vehicle_id.
        Si no se envía, usa el vehicle_id del token (cuando exista).
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            vehicle_id_raw = kwargs.get('idVehiculo') or kwargs.get('vehicle_id')
            if vehicle_id_raw is None and token_rec.vehicle_id:
                vehicle_id_raw = token_rec.vehicle_id.id

            try:
                vehicle_id = int(vehicle_id_raw)
            except Exception:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'idVehiculo (o vehicle_id) es requerido y debe ser numérico.'),
                    status=422,
                )

            vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id)
            if not vehicle.exists():
                return _json_response(
                    _error(404, 'VEHICLE_NOT_FOUND', 'El vehículo indicado no existe.'),
                    status=404,
                )

            if token_rec.vehicle_id and token_rec.vehicle_id.id != vehicle.id:
                return _json_response(
                    _error(403, 'FORBIDDEN', 'El token no tiene permiso para consultar papeletas de este vehículo.'),
                    status=403,
                )

            base_url = _get_base_url()
            papeletas = request.env['adt.papeleta'].sudo().search(
                [('vehicle_id', '=', vehicle.id)],
                order='fecha_papeleta desc, id desc',
            )

            papeletas_data = []
            for papeleta in papeletas:
                foto_urls = [_public_attachment_url(att, base_url) for att in papeleta.attachment_ids.sudo()]
                papeletas_data.append({
                    'id': papeleta.id,
                    'numeroPapeleta': papeleta.name,
                    'fechaPapeleta': _format_date(papeleta.fecha_papeleta),
                    'monto': float(_money(papeleta.monto)),
                    'idVehiculo': papeleta.vehicle_id.id,
                    'fotosCount': len(foto_urls),
                    'fotoUrls': foto_urls,
                })

            return _json_response(_success({
                'idVehiculo': vehicle.id,
                'placa': vehicle.license_plate or None,
                'totalPapeletas': len(papeletas_data),
                'papeletas': papeletas_data,
            }))

        except Exception:
            _logger.exception('Error in GET /v1/papeletas')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/fcm/register',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def register_fcm(self, **kwargs):
        """
        Registers or updates an FCM token for the authenticated mobile session.
        The owner is resolved from bearer token -> mobile.token.partner_id.
        """
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            if not token_rec.partner_id:
                return _json_response(
                    _error(
                        422,
                        'TOKEN_WITHOUT_PARTNER',
                        'El token autenticado no tiene un cliente asociado.',
                    ),
                    status=422,
                )

            raw_body = request.httprequest.data
            body = json.loads(raw_body) if raw_body else {}
            if not isinstance(body, dict):
                return _json_response(
                    _error(400, 'BAD_REQUEST', 'El cuerpo del request debe ser un objeto JSON.'),
                    status=400,
                )

            fcm_token = (body.get('fcm_token') or body.get('token') or '').strip()
            platform = str(body.get('platform') or '').strip().lower()
            device_info = body.get('device_info') or {}

            if not isinstance(device_info, dict):
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'device_info debe ser un objeto JSON.'),
                    status=422,
                )

            if not fcm_token:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'fcm_token (o token) es requerido.'),
                    status=422,
                )

            allowed_platforms = ('android', 'ios', 'web')
            if platform not in allowed_platforms:
                return _json_response(
                    _error(
                        422,
                        'VALIDATION_ERROR',
                        'platform debe ser uno de: android, ios, web.',
                    ),
                    status=422,
                )

            device_id = str(device_info.get('device_id') or token_rec.device_id or '').strip()
            if not device_id:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'device_info.device_id es requerido.'),
                    status=422,
                )

            device_name = str(device_info.get('device_name') or '').strip() or False
            device_os = str(device_info.get('device_os') or '').strip() or False
            app_version = str(device_info.get('app_version') or token_rec.app_version or '').strip() or False

            FCMModel = request.env['mobile.fcm.device'].sudo()

            # Upsert by owner + device; if FCM token already exists elsewhere, reassign it.
            rec = FCMModel.search([
                ('partner_id', '=', token_rec.partner_id.id),
                ('device_id', '=', device_id),
            ], limit=1)

            vals = {
                'partner_id': token_rec.partner_id.id,
                'mobile_token_id': token_rec.id,
                'fcm_token': fcm_token,
                'platform': platform,
                'device_id': device_id,
                'device_name': device_name,
                'device_os': device_os,
                'app_version': app_version,
                'last_seen_at': odoo_fields.Datetime.now(),
                'active': True,
            }

            operation = 'created'
            if rec:
                rec.write(vals)
                operation = 'updated'
            else:
                existing_by_fcm = FCMModel.search([('fcm_token', '=', fcm_token)], limit=1)
                if existing_by_fcm:
                    existing_by_fcm.write(vals)
                    rec = existing_by_fcm
                    operation = 'reassigned'
                else:
                    rec = FCMModel.create(vals)

            # Keep session metadata aligned with latest device info.
            token_rec.sudo().write({
                'device_id': device_id,
                'platform': platform,
                'app_version': app_version,
            })

            response_data = {
                'id': rec.id,
                'operation': operation,
                'partnerId': token_rec.partner_id.id,
                'partnerName': token_rec.partner_id.name or None,
                'platform': rec.platform,
                'fcmTokenMasked': _mask_token(rec.fcm_token),
                'device': {
                    'device_id': rec.device_id,
                    'device_name': rec.device_name,
                    'device_os': rec.device_os,
                    'app_version': rec.app_version,
                },
                'lastSeenAt': _format_datetime(rec.last_seen_at),
            }

            _logger.info(
                '[FCM Register] operation=%s partner_id=%s device_id=%s platform=%s fcm=%s',
                operation,
                token_rec.partner_id.id,
                device_id,
                platform,
                _mask_token(fcm_token),
            )

            return _json_response(_success(response_data, message='FCM token registrado correctamente.'))

        except Exception:
            _logger.exception('Error in POST /v1/fcm/register')
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'),
                status=500,
            )

    @http.route(
        '/v1/comercial/workshop/search-by-plate',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def workshop_search_by_plate(self, plate=None, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            model_err = _ensure_workshop_model('maintenance.work.order')
            if model_err:
                return _json_response(model_err, status=model_err['statusCode'])

            plate_upper, plate_err = _validate_plate(plate)
            if plate_err:
                return _json_response(plate_err, status=plate_err['statusCode'])

            vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
            if vehicle_err:
                return _json_response(vehicle_err, status=vehicle_err['statusCode'])

            if token_rec.vehicle_id and token_rec.vehicle_id.id != vehicle.id:
                return _json_response(_error(403, 'FORBIDDEN', 'El token no tiene permiso para este vehículo.'), status=403)

            partner = vehicle.driver_id or getattr(vehicle, 'partner_id', False) or getattr(vehicle, 'owner_id', False)
            data = {
                'cliente': {
                    'id': partner.id if partner else None,
                    'name': partner.name if partner else None,
                    'document': getattr(partner, 'vat', None) if partner else None,
                    'phone': (partner.phone or partner.mobile) if partner else None,
                },
                'vehiculo': {
                    'id': vehicle.id,
                    'plate': vehicle.license_plate or '',
                    'model': vehicle.model_id.name if vehicle.model_id else None,
                    'brand': vehicle.model_id.brand_id.name if vehicle.model_id and vehicle.model_id.brand_id else None,
                    'vin': vehicle.vin_sn or None,
                    'displayName': vehicle.display_name or None,
                },
            }
            return _json_response(_success(data))
        except Exception:
            _logger.exception('Error in GET /v1/workshop/search-by-plate')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/comercial/workshop/products',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def workshop_products(self, q=None, page=1, pageSize=20, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            _, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            try:
                page = max(1, int(page))
                page_size = max(1, min(100, int(pageSize)))
            except (TypeError, ValueError):
                return _json_response(_error(400, 'BAD_REQUEST', 'Parámetros de paginación inválidos.'), status=400)

            ProductModel = request.env['product.product'].sudo()
            domain = [('active', '=', True)]
            query = (q or '').strip()
            if query:
                domain.append(('display_name', 'ilike', query))

            total_items = ProductModel.search_count(domain)
            total_pages = max(1, -(-total_items // page_size))
            offset = (page - 1) * page_size
            products = ProductModel.search(domain, limit=page_size, offset=offset, order='name asc')

            data = {
                'items': [{
                    'id': p.id,
                    'name': p.display_name,
                    'defaultPrice': float(_money(p.list_price)),
                } for p in products]
            }
            pagination = {
                'page': page,
                'pageSize': page_size,
                'totalItems': total_items,
                'totalPages': total_pages,
                'hasNext': page < total_pages,
                'hasPrev': page > 1,
            }
            return _json_response(_success(data, pagination=pagination))
        except Exception:
            _logger.exception('Error in GET /v1/workshop/products')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/comercial/workshop/labor-templates',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def workshop_labor_templates(self, q=None, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            _, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            model_err = _ensure_workshop_model('maintenance.work.order.service.template')
            if model_err:
                return _json_response(model_err, status=model_err['statusCode'])

            domain = []
            query = (q or '').strip()
            if query:
                domain = ['|', ('name', 'ilike', query), ('description', 'ilike', query)]

            templates = request.env['maintenance.work.order.service.template'].sudo().search(domain, order='name asc')
            data = {
                'items': [{
                    'id': t.id,
                    'name': t.name,
                    'description': t.description or None,
                    'defaultPrice': float(_money(t.default_unit_price)),
                } for t in templates]
            }
            return _json_response(_success(data))
        except Exception:
            _logger.exception('Error in GET /v1/workshop/labor-templates')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/comercial/workshop/catalogs',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def workshop_catalogs(self, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            _, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            data = {
                'payerTypes': [{'value': k, 'label': v} for k, v in WORKSHOP_PAYER_LABELS.items()],
                'finalResultTypes': [{'value': k, 'label': v} for k, v in WORKSHOP_FINAL_STATE_LABELS.items()],
                'workOrderStates': [{'value': k, 'label': v} for k, v in WORKSHOP_STATE_LABELS.items()],
            }
            return _json_response(_success(data))
        except Exception:
            _logger.exception('Error in GET /v1/workshop/catalogs')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/comercial/workshop/work-orders',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def workshop_work_orders(self, page=1, pageSize=20, state=None, plate=None, vehicleId=None, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            model_err = _ensure_workshop_model('maintenance.work.order')
            if model_err:
                return _json_response(model_err, status=model_err['statusCode'])

            try:
                page = max(1, int(page))
                page_size = max(1, min(100, int(pageSize)))
            except (TypeError, ValueError):
                return _json_response(_error(400, 'BAD_REQUEST', 'Parámetros de paginación inválidos.'), status=400)

            domain = []
            if token_rec.vehicle_id:
                domain.append(('vehicle_id', '=', token_rec.vehicle_id.id))

            if state:
                state_db = _map_workshop_state(str(state).strip())
                if not state_db:
                    return _json_response(_error(422, 'VALIDATION_ERROR', 'state inválido.'), status=422)
                domain.append(('state', '=', state_db))

            if vehicleId:
                try:
                    domain.append(('vehicle_id', '=', int(vehicleId)))
                except Exception:
                    return _json_response(_error(422, 'VALIDATION_ERROR', 'vehicleId debe ser numérico.'), status=422)

            if plate:
                plate_upper, plate_err = _validate_plate(plate)
                if plate_err:
                    return _json_response(plate_err, status=plate_err['statusCode'])
                vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
                if vehicle_err:
                    return _json_response(vehicle_err, status=vehicle_err['statusCode'])
                domain.append(('vehicle_id', '=', vehicle.id))

            WoModel = request.env['maintenance.work.order'].sudo()
            total_items = WoModel.search_count(domain)
            total_pages = max(1, -(-total_items // page_size))
            offset = (page - 1) * page_size
            recs = WoModel.search(domain, limit=page_size, offset=offset, order='create_date desc,id desc')

            data = {
                'items': [_serialize_work_order_card(rec) for rec in recs]
            }
            pagination = {
                'page': page,
                'pageSize': page_size,
                'totalItems': total_items,
                'totalPages': total_pages,
                'hasNext': page < total_pages,
                'hasPrev': page > 1,
            }
            return _json_response(_success(data, pagination=pagination))
        except Exception:
            _logger.exception('Error in GET /v1/workshop/work-orders')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/comercial/workshop/work-orders',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def workshop_work_order_save(self, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            token_rec, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            model_err = _ensure_workshop_model('maintenance.work.order')
            if model_err:
                return _json_response(model_err, status=model_err['statusCode'])

            raw_body = request.httprequest.data
            body = json.loads(raw_body) if raw_body else {}
            if not isinstance(body, dict):
                return _json_response(_error(400, 'BAD_REQUEST', 'El cuerpo debe ser un objeto JSON.'), status=400)

            work_order_id = body.get('workOrderId') or body.get('id')
            WoModel = request.env['maintenance.work.order'].sudo()
            is_create = not work_order_id
            work_order = None
            if not is_create:
                try:
                    work_order = WoModel.browse(int(work_order_id))
                except Exception:
                    return _json_response(_error(422, 'VALIDATION_ERROR', 'workOrderId debe ser numérico.'), status=422)
                if not work_order.exists():
                    return _json_response(_error(404, 'NOT_FOUND', 'Orden de trabajo no encontrada.'), status=404)

            vehicle = None
            vehicle_id_raw = body.get('vehicleId')
            plate = body.get('plate')
            if vehicle_id_raw is not None:
                try:
                    vehicle = request.env['fleet.vehicle'].sudo().browse(int(vehicle_id_raw))
                except Exception:
                    vehicle = None
                if not vehicle or not vehicle.exists():
                    return _json_response(_error(404, 'VEHICLE_NOT_FOUND', 'El vehículo indicado no existe.'), status=404)
            elif plate:
                plate_upper, plate_err = _validate_plate(plate)
                if plate_err:
                    return _json_response(plate_err, status=plate_err['statusCode'])
                vehicle, vehicle_err = _vehicle_by_plate(plate_upper)
                if vehicle_err:
                    return _json_response(vehicle_err, status=vehicle_err['statusCode'])
            elif is_create:
                return _json_response(_error(422, 'VALIDATION_ERROR', 'vehicleId o plate es requerido para crear.'), status=422)

            if token_rec.vehicle_id and vehicle and token_rec.vehicle_id.id != vehicle.id:
                return _json_response(_error(403, 'FORBIDDEN', 'El token no tiene permiso para este vehículo.'), status=403)

            vals = {}
            if vehicle:
                vals['vehicle_id'] = vehicle.id

            client_id = body.get('clientId')
            if client_id:
                try:
                    client = request.env['res.partner'].sudo().browse(int(client_id))
                except Exception:
                    client = None
                if not client or not client.exists():
                    return _json_response(_error(404, 'NOT_FOUND', 'Cliente no encontrado.'), status=404)
                vals['client_id'] = client.id
            elif is_create and vehicle:
                partner = vehicle.driver_id or getattr(vehicle, 'partner_id', False) or getattr(vehicle, 'owner_id', False)
                if partner:
                    vals['client_id'] = partner.id

            mechanic_id = body.get('mechanicId')
            if mechanic_id is not None:
                if mechanic_id:
                    mechanic = request.env['res.users'].sudo().browse(int(mechanic_id))
                    if not mechanic.exists():
                        return _json_response(_error(404, 'NOT_FOUND', 'Mecánico no encontrado.'), status=404)
                    vals['mechanic_id'] = mechanic.id
                else:
                    vals['mechanic_id'] = False

            mapping = {
                'entryReason': 'entry_reason',
                'diagnostic': 'diagnostic',
                'finalState': 'final_state',
                'finalNotes': 'final_notes',
                'adtNote': 'adt_note',
            }
            for src, dst in mapping.items():
                if src in body:
                    vals[dst] = body.get(src) or False

            if 'mileage' in body:
                vals['mileage'] = float(body.get('mileage') or 0.0)
            if 'payerType' in body:
                vals['payer_type'] = body.get('payerType') or 'cliente'
            if 'adtContribution' in body:
                vals['adt_contribution'] = float(body.get('adtContribution') or 0.0)

            if 'nextRevisionDate' in body:
                vals['next_revision_date'] = _parse_date(body.get('nextRevisionDate'))
            if 'startDate' in body:
                vals['start_date'] = _parse_iso_datetime(body.get('startDate'))
            if 'endDate' in body:
                vals['end_date'] = _parse_iso_datetime(body.get('endDate'))

            if is_create and not vals.get('client_id'):
                return _json_response(_error(422, 'VALIDATION_ERROR', 'No se pudo determinar el cliente para la orden.'), status=422)

            if is_create:
                work_order = WoModel.create(vals)
            elif vals:
                work_order.write(vals)

            _sync_work_order_lines(work_order, body)

            action = str(body.get('action') or '').strip().lower()
            state_input = body.get('state')
            state_to_set = _map_workshop_action_to_state(action)
            if not state_to_set and state_input:
                state_to_set = _map_workshop_state(str(state_input).strip())

            if state_to_set:
                state_vals = {'state': state_to_set}
                if state_to_set == 'in_progress' and not work_order.start_date:
                    state_vals['start_date'] = odoo_fields.Datetime.now()
                if state_to_set == 'done' and not work_order.end_date:
                    state_vals['end_date'] = odoo_fields.Datetime.now()
                work_order.write(state_vals)

            message = 'Orden de trabajo creada correctamente.' if is_create else 'Orden de trabajo actualizada correctamente.'
            if action == 'pause':
                message = 'Orden de trabajo pausada correctamente.'
            elif action == 'resume':
                message = 'Orden de trabajo reanudada correctamente.'
            elif action == 'finalize':
                message = 'Orden de trabajo finalizada correctamente.'

            return _json_response(_success({'workOrder': _serialize_work_order_detail(work_order)}, message=message))
        except Exception:
            _logger.exception('Error in POST /v1/workshop/work-orders')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/catalog/products',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def catalog_products(self, q=None, page=1, pageSize=20, categoryId=None, vehicleModelId=None, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            _, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            try:
                page = max(1, int(page))
                page_size = max(1, min(100, int(pageSize)))
            except (TypeError, ValueError):
                return _json_response(_error(400, 'BAD_REQUEST', 'Parámetros de paginación inválidos.'), status=400)

            ProductTemplate = request.env['product.template'].sudo()
            domain = [('active', '=', True), ('sale_ok', '=', True), ('mobile_published', '=', True)]

            query = (q or '').strip()
            if query:
                domain.extend([
                    '|', '|', '|',
                    ('name', 'ilike', query),
                    ('default_code', 'ilike', query),
                    ('barcode', 'ilike', query),
                    ('mobile_short_description', 'ilike', query),
                ])

            if categoryId not in (None, ''):
                try:
                    domain.append(('categ_id', '=', int(categoryId)))
                except (TypeError, ValueError):
                    return _json_response(_error(400, 'BAD_REQUEST', 'categoryId debe ser numérico.'), status=400)

            if vehicleModelId not in (None, '') and 'product_model_id' in ProductTemplate._fields:
                try:
                    domain.append(('product_model_id', '=', int(vehicleModelId)))
                except (TypeError, ValueError):
                    return _json_response(_error(400, 'BAD_REQUEST', 'vehicleModelId debe ser numérico.'), status=400)

            total_items = ProductTemplate.search_count(domain)
            total_pages = max(1, -(-total_items // page_size))
            offset = (page - 1) * page_size
            products = ProductTemplate.search(domain, limit=page_size, offset=offset, order='mobile_sequence asc, name asc, id asc')

            data = {
                'items': [_serialize_catalog_product_summary(product) for product in products]
            }
            pagination = {
                'page': page,
                'pageSize': page_size,
                'totalItems': total_items,
                'totalPages': total_pages,
                'hasNext': page < total_pages,
                'hasPrev': page > 1,
            }
            return _json_response(_success(data, pagination=pagination))
        except Exception:
            _logger.exception('Error in GET /v1/catalog/products')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route(
        '/v1/catalog/products/<int:product_id>',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def catalog_product_detail(self, product_id, **kwargs):
        try:
            auth = request.httprequest.headers.get('Authorization', '')
            _, token_err = _get_token_record(auth)
            if token_err:
                return _json_response(token_err, status=token_err['statusCode'])

            ProductTemplate = request.env['product.template'].sudo()
            product = ProductTemplate.search([
                ('id', '=', product_id),
                ('active', '=', True),
                ('sale_ok', '=', True),
                ('mobile_published', '=', True),
            ], limit=1)
            if not product:
                return _json_response(_error(404, 'PRODUCT_NOT_FOUND', 'Producto no encontrado.'), status=404)

            return _json_response(_success({'product': _serialize_catalog_product_detail(product)}))
        except Exception:
            _logger.exception('Error in GET /v1/catalog/products/%s', product_id)
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_workshop_model(model_name):
    try:
        if request.env.registry.get(model_name):
            return None
    except Exception:
        pass
    return _error(503, 'MODULE_NOT_AVAILABLE', 'El módulo de taller no está disponible (%s).' % model_name)


def _map_workshop_state(state_input):
    if not state_input:
        return None
    raw = str(state_input or '').strip().lower().replace(' ', '_')
    aliases = {
        'pendiente': 'pending',
        'pending': 'pending',
        'en_progreso': 'in_progress',
        'in_progress': 'in_progress',
        'bloqueado': 'blocked',
        'blocked': 'blocked',
        'finalizado': 'done',
        'done': 'done',
    }
    return aliases.get(raw)


def _map_workshop_action_to_state(action):
    action = (action or '').strip().lower()
    if action == 'pause':
        return 'blocked'
    if action == 'resume':
        return 'in_progress'
    if action == 'finalize':
        return 'done'
    return None


def _parse_date(value):
    if not value:
        return False
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except Exception:
        return False


def _work_order_relative_time(dt):
    if not dt:
        return None
    try:
        base_date = dt.date() if hasattr(dt, 'date') else dt
        days = (datetime.now().date() - base_date).days
        if days <= 0:
            return 'hoy'
        if days == 1:
            return 'hace 1 día'
        return 'hace %s días' % days
    except Exception:
        return None


def _initials(name):
    parts = [p for p in str(name or '').strip().split(' ') if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _money_label(value):
    try:
        return 'S/ %s' % format(float(_money(value)), ',.2f')
    except Exception:
        return 'S/ 0.00'


def _serialize_work_order_card(wo):
    plate = wo.vehicle_id.license_plate if wo.vehicle_id else ''
    model_name = wo.vehicle_id.model_id.name if wo.vehicle_id and wo.vehicle_id.model_id else ''
    vehicle_label = ('%s · %s' % (plate, model_name)).strip(' ·')
    days = wo.days_in_taller or 0
    return {
        'id': wo.id,
        'code': wo.name or '',
        'daysInWorkshop': days,
        'daysLabel': '%s día%s' % (days, '' if days == 1 else 's'),
        'state': wo.state or 'pending',
        'stateLabel': WORKSHOP_STATE_LABELS.get(wo.state, wo.state or ''),
        'clientName': wo.client_id.name if wo.client_id else None,
        'vehicleLabel': vehicle_label,
        'relativeTime': _work_order_relative_time(wo.create_date),
        'mechanicInitials': _initials(wo.mechanic_id.name) if wo.mechanic_id else None,
        'mechanicName': wo.mechanic_id.name if wo.mechanic_id else None,
        'totalAmount': float(_money(wo.total_amount)),
        'totalAmountLabel': _money_label(wo.total_amount),
    }


def _serialize_work_order_detail(wo):
    data = _serialize_work_order_card(wo)
    data.update({
        'vehicle': {
            'id': wo.vehicle_id.id if wo.vehicle_id else None,
            'plate': wo.vehicle_id.license_plate if wo.vehicle_id else None,
            'model': wo.vehicle_id.model_id.name if wo.vehicle_id and wo.vehicle_id.model_id else None,
            'vin': wo.vehicle_id.vin_sn if wo.vehicle_id else None,
        },
        'client': {
            'id': wo.client_id.id if wo.client_id else None,
            'name': wo.client_id.name if wo.client_id else None,
        },
        'mechanic': {
            'id': wo.mechanic_id.id if wo.mechanic_id else None,
            'name': wo.mechanic_id.name if wo.mechanic_id else None,
        },
        'entryReason': wo.entry_reason or None,
        'diagnostic': wo.diagnostic or None,
        'mileage': wo.mileage or 0.0,
        'payerType': wo.payer_type or None,
        'payerTypeLabel': WORKSHOP_PAYER_LABELS.get(wo.payer_type, wo.payer_type or None),
        'adtContribution': float(_money(wo.adt_contribution)),
        'adtAmount': float(_money(wo.adt_amount)),
        'clientAmount': float(_money(wo.client_amount)),
        'adtNote': wo.adt_note or None,
        'finalState': wo.final_state or None,
        'finalStateLabel': WORKSHOP_FINAL_STATE_LABELS.get(wo.final_state, wo.final_state or None),
        'finalNotes': wo.final_notes or None,
        'startDate': _format_datetime(wo.start_date),
        'endDate': _format_datetime(wo.end_date),
        'nextRevisionDate': _format_date(wo.next_revision_date),
        'parts': [],
        'services': [],
        'paymentSchedule': [],
    })
    for part in wo.part_ids:
        data['parts'].append({
            'id': part.id,
            'productId': part.product_id.id if part.product_id else None,
            'productName': part.product_id.display_name if part.product_id else None,
            'quantity': part.quantity or 0.0,
            'unitPrice': float(_money(part.unit_price)),
            'subtotal': float(_money(part.subtotal)),
            'notes': part.notes or None,
        })
    for service in wo.service_ids:
        data['services'].append({
            'id': service.id,
            'serviceTemplateId': service.service_template_id.id if service.service_template_id else None,
            'name': service.name or None,
            'description': service.description or None,
            'unitPrice': float(_money(service.unit_price)),
            'subtotal': float(_money(service.subtotal)),
        })
    for pay in wo.payment_schedule_ids.sorted('due_date'):
        data['paymentSchedule'].append({
            'id': pay.id,
            'name': pay.name or None,
            'dueDate': _format_date(pay.due_date),
            'amount': float(_money(pay.amount)),
            'payer': pay.payer or None,
            'state': pay.state or None,
        })
    return data


def _sync_work_order_lines(work_order, body):
    if 'parts' in body:
        commands = [(5, 0, 0)]
        for row in body.get('parts') or []:
            if not isinstance(row, dict):
                continue
            product_id = row.get('productId')
            if not product_id:
                continue
            commands.append((0, 0, {
                'product_id': int(product_id),
                'quantity': float(row.get('quantity') or 1.0),
                'unit_price': float(row.get('unitPrice') or 0.0),
                'notes': row.get('notes') or False,
            }))
        work_order.sudo().write({'part_ids': commands})

    if 'services' in body:
        commands = [(5, 0, 0)]
        for row in body.get('services') or []:
            if not isinstance(row, dict):
                continue
            commands.append((0, 0, {
                'service_template_id': int(row.get('serviceTemplateId')) if row.get('serviceTemplateId') else False,
                'name': row.get('name') or False,
                'description': row.get('description') or False,
                'unit_price': float(row.get('unitPrice') or 0.0),
            }))
        work_order.sudo().write({'service_ids': commands})

    if 'paymentSchedule' in body:
        commands = [(5, 0, 0)]
        for row in body.get('paymentSchedule') or []:
            if not isinstance(row, dict):
                continue
            commands.append((0, 0, {
                'name': row.get('name') or False,
                'due_date': _parse_date(row.get('dueDate')),
                'amount': float(row.get('amount') or 0.0),
                'payer': row.get('payer') or 'cliente',
                'state': row.get('state') or 'pending',
            }))
        work_order.sudo().write({'payment_schedule_ids': commands})


def _catalog_currency_symbol(product_tmpl):
    currency = getattr(product_tmpl, 'currency_id', False) or request.env.company.currency_id
    return currency.symbol or 'S/'


def _catalog_product_main_image_url(product_tmpl):
    if not product_tmpl or not getattr(product_tmpl, 'image_1920', False):
        return None
    return _build_attachment_url('product.template', product_tmpl.id, 'image_1920')


def _catalog_product_gallery(product_tmpl):
    images = []
    main_image_url = _catalog_product_main_image_url(product_tmpl)
    if main_image_url:
        images.append({
            'id': 'main-%s' % product_tmpl.id,
            'name': product_tmpl.name or 'Imagen principal',
            'url': main_image_url,
            'isMain': True,
        })

    for image in product_tmpl.mobile_product_image_ids.filtered(lambda img: img.active).sorted('sequence'):
        image_url = _build_attachment_url('mobile.catalog.product.image', image.id, 'image_1920')
        if not image_url:
            continue
        images.append({
            'id': image.id,
            'name': image.name or 'Imagen',
            'url': image_url,
            'isMain': False,
        })

    return images


def _catalog_vehicle_model_data(product_tmpl):
    if 'product_model_id' not in product_tmpl._fields:
        return None
    vehicle_model = product_tmpl.product_model_id
    if not vehicle_model:
        return None
    brand_name = vehicle_model.brand_id.name if getattr(vehicle_model, 'brand_id', False) else None
    return {
        'id': vehicle_model.id,
        'name': vehicle_model.name,
        'brand': brand_name,
    }


def _normalize_whatsapp_phone(phone_raw):
    if not phone_raw:
        return None
    digits = ''.join(ch for ch in str(phone_raw).strip() if ch.isdigit())
    return digits or None


def _get_catalog_cta_config():
    try:
        ConfigModel = request.env['mobile.catalog.cta.config'].sudo()
        candidates = ConfigModel.search([('active', '=', True)], order='write_date desc, id desc', limit=20)
        for rec in candidates:
            has_phone = bool(_normalize_whatsapp_phone(rec.whatsapp_phone))
            has_url = bool((rec.whatsapp_url or '').strip())
            if rec.cta_enabled and (has_phone or has_url):
                return rec
        return candidates[:1]
    except Exception:
        return None


def _catalog_buy_cta(product_tmpl):
    config = _get_catalog_cta_config()
    phone = _normalize_whatsapp_phone(config.whatsapp_phone if config else None)
    configured_url = (config.whatsapp_url or '').strip() if config else ''
    configured_enabled = bool(config and config.cta_enabled)
    enabled = configured_enabled and bool(configured_url or phone)

    message = 'Hola, deseo consultar por el producto %s' % (product_tmpl.name or '')
    if product_tmpl.default_code:
        message += ' (SKU: %s)' % product_tmpl.default_code

    whatsapp_url = None
    if enabled:
        whatsapp_url = configured_url or 'https://wa.me/%s?text=%s' % (phone, quote_plus(message))

    button_icon_url = None
    if config and config.id and config.button_icon_image:
        button_icon_url = _build_attachment_url('mobile.catalog.cta.config', config.id, 'button_icon_image')

    return {
        'enabled': enabled,
        'phone': phone,
        'buttonText': (config.button_text if config and config.button_text else 'Comprar por WhatsApp'),
        'buttonColor': (config.button_color if config and config.button_color else '#25D366'),
        'buttonIcon': 'uploaded_image' if button_icon_url else 'whatsapp',
        'buttonIconUrl': button_icon_url,
        'whatsappUrl': whatsapp_url,
    }


def _serialize_catalog_product_summary(product_tmpl):
    category = product_tmpl.categ_id
    vehicle_model = _catalog_vehicle_model_data(product_tmpl)
    image_url = _catalog_product_main_image_url(product_tmpl)
    return {
        'id': product_tmpl.id,
        'name': product_tmpl.name,
        'sku': product_tmpl.default_code or None,
        'barcode': product_tmpl.barcode or None,
        'price': float(_money(product_tmpl.list_price)),
        'currency': _catalog_currency_symbol(product_tmpl),
        'shortDescription': product_tmpl.mobile_short_description or product_tmpl.description_sale or None,
        'badge': product_tmpl.mobile_badge or None,
        'imageUrl': image_url,
        'hasImage': bool(image_url),
        'category': {
            'id': category.id if category else None,
            'name': category.name if category else None,
        },
        'vehicleModel': vehicle_model,
        'buyCta': _catalog_buy_cta(product_tmpl),
    }


def _serialize_catalog_product_detail(product_tmpl):
    summary = _serialize_catalog_product_summary(product_tmpl)
    summary.update({
        'saleDescription': product_tmpl.description_sale or None,
        'description': product_tmpl.description or None,
        'mobilePublished': bool(product_tmpl.mobile_published),
        'sequence': product_tmpl.mobile_sequence or 0,
        'canSell': bool(product_tmpl.sale_ok),
        'qtyAvailable': float(product_tmpl.mobile_qty_available or 0.0),
        'uom': product_tmpl.uom_id.name if getattr(product_tmpl, 'uom_id', False) else None,
        'images': _catalog_product_gallery(product_tmpl),
    })
    return summary

def _get_payment_accounts():
    """
    Returns the list of payment accounts from the database model mobile.payment.account.
    Falls back to an empty list if the model is not yet installed.
    """
    try:
        accounts = request.env['mobile.payment.account'].sudo().search(
            [('active', '=', True)], order='sequence asc'
        )
        return [
            {
                'id': str(acc.id),
                'name': acc.name,
                'iconUrl': acc.icon_url or '/web/static/img/placeholder.png',
                'accountNumber': acc.account_number,
            }
            for acc in accounts
        ]
    except Exception:
        return []


def _get_support_contacts(cuenta):
    """
    Returns support contacts from mobile.support.contact model.
    Falls back to the assigned seller (user_id) from the account if no contacts are configured.
    """
    try:
        contacts_model = request.env['mobile.support.contact'].sudo()
        records = contacts_model.search([('active', '=', True)], order='sequence asc')
        if records:
            return [
                {
                    'id': 'sc%d' % rec.id,
                    'name': rec.name,
                    'phone': rec.phone or None,
                    'role': rec.role,
                }
                for rec in records
            ]
    except Exception:
        pass

    # Fallback: use the seller assigned to the account
    contacts = []
    if cuenta and cuenta.user_id:
        user = cuenta.user_id
        partner = user.partner_id
        contacts.append({
            'id': 'u%d' % user.id,
            'name': partner.name or user.name or '',
            'phone': partner.phone or partner.mobile or None,
            'role': 'SUPPORT',
        })
    return contacts


def _build_expediente_documents(expediente):
    """
    Builds the list of documents from an adt.expediente record.
    Returns a list of document dicts.
    """
    docs = []

    # Image fields that are stored as base64 attachments on the expediente
    IMAGE_FIELDS = [
        ('foto_dni_frente', 'DNI – Frente', 'ID'),
        ('foto_dni_reverso', 'DNI – Reverso', 'ID'),
        ('foto_ce_frente', 'Carnet de Extranjería – Frente', 'ID'),
        ('foto_ce_reverso', 'Carnet de Extranjería – Reverso', 'ID'),
        ('foto_pasaporte_frente', 'Pasaporte – Frente', 'ID'),
        ('foto_pasaporte_reverso', 'Pasaporte – Reverso', 'ID'),
        ('foto_licencia', 'Licencia de Conducir', 'OTHER'),
        ('foto_recibo', 'Recibo de Servicios', 'OTHER'),
        ('foto_sentinel_1', 'Sentinel 1', 'OTHER'),
        ('foto_sentinel_2', 'Sentinel 2', 'OTHER'),
        ('foto_moto', 'Foto Moto', 'OTHER'),
        ('foto_soat', 'SOAT', 'GUARANTEE'),
        ('foto_tarjeta_propiedad_frente', 'Tarjeta Propiedad – Frente', 'GUARANTEE'),
        ('foto_tarjeta_propiedad_reverso', 'Tarjeta Propiedad – Reverso', 'GUARANTEE'),
        ('foto_lugar_trabajo', 'Lugar de Trabajo', 'OTHER'),
        ('foto_lugar_negocio', 'Lugar de Negocio', 'OTHER'),
        ('foto_boletas', 'Boletas', 'OTHER'),
        ('foto_estado_cuenta', 'Estado de Cuenta', 'OTHER'),
        ('foto_ubicacion_actual', 'Ubicación Actual', 'OTHER'),
        ('foto_fachada_domicilio', 'Fachada Domicilio', 'OTHER'),
        ('foto_contrato_alquiler', 'Contrato de Alquiler', 'CONTRACT'),
    ]

    base_url = _get_base_url()

    for idx, (field_name, display_name, doc_type) in enumerate(IMAGE_FIELDS):
        try:
            field_val = getattr(expediente, field_name, None)
        except Exception:
            field_val = None

        if not field_val:
            continue

        # Try to build a public URL via the attachment mechanism
        # field_val is binary (base64); we need to find the attachment record
        AttachModel = request.env['ir.attachment'].sudo()
        attach = AttachModel.search([
            ('res_model', '=', 'adt.expediente'),
            ('res_id', '=', expediente.id),
            ('res_field', '=', field_name),
        ], limit=1)

        if attach:
            url = _public_attachment_url(attach, base_url)
            size_kb = int((attach.file_size or 0) / 1024)
            mime = attach.mimetype or 'image/jpeg'
            uploaded_at = _format_datetime(attach.create_date)
        else:
            url = '%s/web/image/adt.expediente/%d/%s' % (base_url, expediente.id, field_name)
            size_kb = 0
            mime = 'image/jpeg'
            uploaded_at = _format_datetime(expediente.create_date if hasattr(expediente, 'create_date') else None)

        docs.append({
            'id': 'doc-%d-%d' % (expediente.id, idx),
            'name': display_name,
            'type': doc_type,
            'mimeType': mime,
            'sizeKb': size_kb,
            'url': url,
            'urlExpiresAt': None,  # Odoo URLs don't expire
            'uploadedAt': uploaded_at,
        })

    return docs
