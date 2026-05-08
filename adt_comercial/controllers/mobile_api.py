# -*- coding: utf-8 -*-
"""
Mobile App REST API Controller
Implements the following endpoints:

  HU-001  GET  /v1/app/version              (no auth)
  HU-002  GET  /v1/loans?plate=ABC-123      (bearer token)
  HU-003  GET  /v1/documents?plate=ABC-123  (bearer token)
  HU-004  GET  /v1/promotions               (bearer token, pagination)
  HU-005  GET  /v1/notifications            (bearer token, pagination)
  HU-006  POST /v1/auth/logout              (bearer token)

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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone

from odoo import http, fields as odoo_fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

# ── Plate regex ────────────────────────────────────────────────────────────
# Standard format: 3 uppercase letters, dash, 3 digits  e.g.  ABC-123
# Some plates in Peru use 4+2 variants; we accept both permissively.
PLATE_RE = re.compile(r'^[A-Z0-9]{2,4}-?[A-Z0-9]{2,4}$', re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _request_id():
    return str(uuid.uuid4())


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
                        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
                        voucher_url = f"{base_url}/web/content/{attach.id}"

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

            data = {
                'customer': customer_data,
                'loan': loan_data,
                'paymentAccounts': payment_accounts,
                'contacts': contacts,
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
                image_value = comp.get('image') if comp.get('image') is not None else comp.get('imagen')
                if not numero_operacion:
                    return _contract_error(400, 'COMPROBANTE_DUPLICADO', 'numero_operacion es requerido.', 'comprobante[%s].numero_operacion' % idx)

                # Soporta image string o images arreglo.
                if isinstance(image_value, list):
                    images = [img for img in image_value if img]
                elif image_value:
                    images = [image_value]
                else:
                    images = [False]

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

                for comp in comprobantes_normalizados:
                    request.env['adt.comercial.cuotas.pendientes.comprobante'].sudo().create({
                        'pendiente_id': pendiente.id,
                        'numero_operacion': comp['numero_operacion'],
                        'image': comp['image'],
                    })

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
                })

            response = {
                'pagoId': pago_id,
                'comprobante': [{'numero_operacion': n} for n in list(dict.fromkeys(numeros_operacion))],
                'montoTotal': float(monto_total),
                'fechaPago': fecha_pago.replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'cuotas': cuota_results,
            }
            return _json_response(response, status=200)

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
                base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
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
                            url = '%s/web/content/%d' % (base_url, attach.id)
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
            except Exception:
                _logger.exception('Error while building vehicle documents for GET /v1/documents')

            data = {'documents': documents_data}
            return _json_response(_success(data))

        except Exception:
            _logger.exception('Error in GET /v1/documents')
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
            domain = [('active', '=', True)]
            if token_rec.partner_id:
                domain.append(('partner_id', '=', token_rec.partner_id.id))
            elif token_rec.vehicle_id:
                domain.append(('vehicle_id', '=', token_rec.vehicle_id.id))
            else:
                # No association → return empty
                data = {'unreadCount': 0, 'notifications': []}
                pagination = {
                    'page': 1, 'pageSize': page_size,
                    'totalItems': 0, 'totalPages': 1,
                    'hasNext': False, 'hasPrev': False,
                }
                return _json_response(_success(data, pagination=pagination))

            NotifModel = request.env['mobile.notification'].sudo()
            unread_count = NotifModel.search_count(domain + [('read', '=', False)])

            if unread_filter:
                domain.append(('read', '=', False))

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
                    'read': n.read,
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

            notif.mark_as_read()
            return _json_response(_success(
                {'id': 'notif-%d' % notification_id, 'read': True},
                message='Notificación marcada como leída.',
            ))
        except Exception:
            _logger.exception('Error in POST /v1/notifications/%s/read', notification_id)
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
                    'vehicle_id': vehicle_id,
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


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

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

    base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')

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
            url = '%s/web/content/%d' % (base_url, attach.id)
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
