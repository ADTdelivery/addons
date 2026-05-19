# -*- coding: utf-8 -*-
"""
API de Consulta por Placa
GET /api/v1/placa?plate=ABC-123

Busca primero en el Odoo local. Si no encuentra el vehículo,
hace fallback al Odoo legacy (http://12.34.56.78:7040).

Respuesta:
  - usuario      : datos del socio (res.partner)
  - vehiculo     : datos del vehículo (fleet.vehicle)
  - cuentas      : lista de cronogramas de pago (adt.comercial.cuentas)
  - financiera   : nombre de la entidad financiera
"""

import json
import logging
import xmlrpc.client
from datetime import datetime, timezone

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

# ── Legacy Odoo connection params ────────────────────────────────────────────
LEGACY_URL = 'http://52.15.86.160:8070'
LEGACY_DB = 'odoo'
LEGACY_USER = 'rapitash@gmail.com'
LEGACY_PASSWORD = 'Sofka2024'
LEGACY_FINANCIERA = 'Qorilazo'


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type='application/json',
    )


def _success(data):
    return {
        'success': True,
        'statusCode': 200,
        'data': data,
        'meta': {
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        },
    }


def _error(http_code, code, message):
    return {
        'success': False,
        'statusCode': http_code,
        'error': {'code': code, 'message': message},
        'meta': {
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        },
    }


def _fmt_date(d):
    """Format a date/Char field to dd/mm/yyyy string or None."""
    if not d:
        return None
    try:
        if hasattr(d, 'strftime'):
            return d.strftime('%d/%m/%Y')
        # It might be a string already
        return str(d)
    except Exception:
        return None


def _money(v):
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Local Odoo helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_cuota_data(cuota):
    """Serialize one adt.comercial.cuotas record."""
    return {
        'numero_cuota': cuota.name or '',
        'monto_cuota': _money(cuota.monto),
        'saldo': _money(cuota.saldo),
        'fecha_cronograma': _fmt_date(cuota.fecha_cronograma),
        'fecha_pago': cuota.real_date or None,
        'asesora': cuota.x_asesora or None,
        'numero_operacion': cuota.numero_operacion or None,
        'periodo': cuota.periodicidad or None,
        'estado': cuota.state or None,
    }


def _build_cuenta_data(cuenta):
    """Serialize one adt.comercial.cuentas record (full cronograma)."""
    cuotas = cuenta.cuota_ids.filtered(lambda c: c.type == 'cuota').sorted('fecha_cronograma')

    return {
        'id': cuenta.id,
        'referencia': cuenta.reference_no or '',
        'estado': cuenta.state or '',
        # Detalle del préstamo – fechas
        'fecha_desembolso': _fmt_date(cuenta.fecha_desembolso),
        'fecha_cierre': cuenta.fecha_cierre,
        'fecha_entrega': _fmt_date(cuenta.fecha_entrega),
        # Montos y cuotas
        'valor_total_vehiculo': _money(cuenta.monto_total),
        'inicial': _money(cuenta.monto_inicial),
        'monto_fraccionado': _money(cuenta.monto_fraccionado),
        'cuota_gracia': _money(cuenta.cuota_gracia),
        'fecha_gracia': _fmt_date(cuenta.fecha_gracia),
        'periodo': cuenta.periodicidad or '',
        'total_cuotas': cuenta.qty_cuotas,
        'monto_cuota': _money(cuenta.monto_cuota),
        # Detalle del cronograma
        'saldo_restante': _money(cuenta.cuotas_saldo),
        'cuotas_restantes': cuenta.qty_cuotas_restantes,
        'total_retrasado': _money(cuenta.cuotas_retrasado),
        'cuotas_retrasadas': cuenta.qty_cuotas_retrasado,
        'total_pagado': _money(cuenta.cuotas_pagado),
        'cuotas_pagadas': cuenta.qty_cuotas_pagadas,
        # Cuotas detalle
        'cuotas': [_build_cuota_data(c) for c in cuotas],
    }


def _search_local(plate_upper):
    """
    Search for the vehicle in the current Odoo instance.
    Returns (result_dict, financiera_name) or (None, None).
    """
    VehicleModel = request.env['fleet.vehicle'].sudo()
    vehicles = VehicleModel.search([('license_plate', '=ilike', plate_upper)])
    if not vehicles:
        return None, None

    vehicle_ids = vehicles.ids

    # ── Partner ────────────────────────────────────────────────────────────
    partner = vehicles[:1].driver_id

    partner_data = None
    if partner:
        country_name = partner.country_id.name if partner.country_id else None
        partner_data = {
            'nombre': partner.name or '',
            'direccion': partner.street or None,
            'numero_documento': partner.vat or None,
            'pais': country_name,
            'tipo_documento': partner.tipo_documento or None,
        }

    # ── Vehicle ────────────────────────────────────────────────────────────
    vehicle_data = {
        'placa': plate_upper,
        'modelo': vehicles[:1].model_id.name if vehicles[:1].model_id else None,
        'numero_chasis': vehicles[:1].vin_sn or None,
        'total_cuentas': 0,
    }

    # ── Cuentas ────────────────────────────────────────────────────────────
    CuentaModel = request.env['adt.comercial.cuentas'].sudo()
    cuentas = CuentaModel.search([('vehiculo_id', 'in', vehicle_ids)], order='id desc')
    cuentas_data = [_build_cuenta_data(c) for c in cuentas]
    vehicle_data['total_cuentas'] = len(cuentas)

    # ── Financiera ─────────────────────────────────────────────────────────
    # Use the first active account's financiera; fall back to the latest account.
    financiera_name = None
    cuenta_ref = (
        cuentas.filtered(lambda c: c.state == 'en_curso')[:1]
        or cuentas.filtered(lambda c: c.state == 'aprobado')[:1]
        or cuentas.filtered(lambda c: c.state != 'cancelado')[:1]
        or cuentas[:1]
    )
    if not partner and cuenta_ref:
        partner = cuenta_ref.partner_id
        country_name = partner.country_id.name if partner and partner.country_id else None
        partner_data = {
            'nombre': partner.name or '',
            'direccion': partner.street or None,
            'numero_documento': partner.vat or None,
            'pais': country_name,
            'tipo_documento': partner.tipo_documento or None,
        } if partner else None
    if cuenta_ref and cuenta_ref.tipo_financiera_id:
        financiera_name = cuenta_ref.tipo_financiera_id.name

    result = {
        'fuente': 'local',
        'usuario': partner_data,
        'vehiculo': vehicle_data,
        'cuentas': cuentas_data,
        'financiera': financiera_name,
    }
    return result, financiera_name


# ─────────────────────────────────────────────────────────────────────────────
# Legacy Odoo XML-RPC helpers
# ─────────────────────────────────────────────────────────────────────────────

def _xmlrpc_connect():
    """Return (uid, models_proxy) for the legacy Odoo, or (None, None) on error."""
    try:
        common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % LEGACY_URL, allow_none=True)
        uid = common.authenticate(LEGACY_DB, LEGACY_USER, LEGACY_PASSWORD, {})
        if not uid:
            _logger.warning('PlacaAPI: No se pudo autenticar en el Odoo legacy.')
            return None, None
        models = xmlrpc.client.ServerProxy('%s/xmlrpc/2/object' % LEGACY_URL, allow_none=True)
        return uid, models
    except Exception:
        _logger.exception('PlacaAPI: Error conectando al Odoo legacy.')
        return None, None


def _legacy_execute(models, model, method, domain, fields_list, limit=1):
    try:
        return models.execute_kw(
            LEGACY_DB, 1, LEGACY_PASSWORD,
            model, method,
            [domain],
            {'fields': fields_list, 'limit': limit},
        )
    except Exception:
        _logger.exception('PlacaAPI: Error en execute_kw legacy (%s.%s)', model, method)
        return []


def _search_legacy(plate_upper):
    """
    Search for the vehicle in the legacy Odoo using XML-RPC.
    Returns result_dict or None.
    """
    uid, models = _xmlrpc_connect()
    if not uid:
        return None

    def execute(model, method, domain, fields_list, limit=0, order=None):
        try:
            kwargs = {'fields': fields_list}
            if limit:
                kwargs['limit'] = limit
            if order:
                kwargs['order'] = order
            return models.execute_kw(
                LEGACY_DB, uid, LEGACY_PASSWORD,
                model, method,
                [domain],
                kwargs,
            )
        except Exception:
            _logger.exception('PlacaAPI legacy execute %s.%s', model, method)
            return []

    # ── Vehicle ────────────────────────────────────────────────────────────
    vehicles = execute(
        'fleet.vehicle', 'search_read',
        [('license_plate', '=ilike', plate_upper)],
        ['id', 'license_plate', 'model_id', 'vin_sn', 'driver_id'],
    )
    if not vehicles:
        return None

    veh = vehicles[0]
    vehicle_ids = [v.get('id') for v in vehicles if v.get('id')]

    # Model name
    model_name = veh['model_id'][1] if veh.get('model_id') else None

    # ── Partner ────────────────────────────────────────────────────────────
    partner_data = None
    driver = veh.get('driver_id')
    partner_id = driver[0] if driver else None

    if partner_id:
        partners = execute(
            'res.partner', 'search_read',
            [('id', '=', partner_id)],
            ['id', 'name', 'street', 'vat', 'country_id', 'tipo_documento'],
            limit=1,
        )
        if partners:
            p = partners[0]
            country = p.get('country_id')
            partner_data = {
                'nombre': p.get('name') or '',
                'direccion': p.get('street') or None,
                'numero_documento': p.get('vat') or None,
                'pais': country[1] if country else None,
                'tipo_documento': p.get('tipo_documento') or None,
            }

    # ── Cuentas ────────────────────────────────────────────────────────────
    cuentas_raw = execute(
        'adt.comercial.cuentas', 'search_read',
        [('vehiculo_id', 'in', vehicle_ids)],
        [
            'id', 'reference_no', 'state',
            'fecha_desembolso', 'fecha_cierre', 'fecha_entrega',
            'monto_total', 'monto_inicial', 'monto_fraccionado',
            'cuota_gracia', 'fecha_gracia', 'periodicidad',
            'qty_cuotas', 'monto_cuota',
            'partner_id',
        ],
        order='id desc',
    )

    # Cuenta activa: prioriza en_curso/aprobado; fallback a la más reciente.
    active_cuenta_id = None
    for cuenta in (cuentas_raw or []):
        if cuenta.get('state') in ('en_curso', 'aprobado'):
            active_cuenta_id = cuenta.get('id')
            break
    if not active_cuenta_id and cuentas_raw:
        active_cuenta_id = cuentas_raw[0].get('id')

    cuentas_data = []
    for cuenta in (cuentas_raw or []):
        cuenta_id = cuenta['id']

        # Solo devolver cuotas de la cuenta activa.
        cuotas_raw = []
        if cuenta_id == active_cuenta_id:
            cuotas_raw = execute(
                'adt.comercial.cuotas', 'search_read',
                [('cuenta_id', '=', cuenta_id), ('type', '=', 'cuota')],
                ['id', 'name', 'monto', 'saldo', 'fecha_cronograma',
                 'real_date', 'x_asesora', 'numero_operacion', 'periodicidad', 'state'],
                order='fecha_cronograma asc,id asc',
            )

        cuotas_data = []
        for c in sorted(cuotas_raw or [], key=lambda x: x.get('fecha_cronograma') or ''):
            cuotas_data.append({
                'numero_cuota': c.get('name') or '',
                'monto_cuota': _money(c.get('monto')),
                'saldo': _money(c.get('saldo')),
                'fecha_cronograma': c.get('fecha_cronograma') or None,
                'fecha_pago': c.get('real_date') or None,
                'asesora': c.get('x_asesora') or None,
                'numero_operacion': c.get('numero_operacion') or None,
                'periodo': c.get('periodicidad') or None,
                'estado': c.get('state') or None,
            })

        cuotas_restantes = 0
        cuotas_retrasadas = 0
        cuotas_pagadas = 0
        saldo_restante = 0.0
        total_retrasado = 0.0
        total_pagado = 0.0
        for c in cuotas_data:
            estado = c.get('estado')
            monto = _money(c.get('monto_cuota'))
            saldo = _money(c.get('saldo'))
            if estado == 'pagado':
                cuotas_pagadas += 1
                total_pagado += monto
            elif estado in ('retrasado', 'vencido'):
                cuotas_retrasadas += 1
                cuotas_restantes += 1
                total_retrasado += saldo
                saldo_restante += saldo
            elif estado in ('pendiente', 'a_cuenta'):
                cuotas_restantes += 1
                saldo_restante += saldo

        partner_rel = cuenta.get('partner_id') or []
        titular_nombre = partner_rel[1] if len(partner_rel) > 1 else None

        cuentas_data.append({
            'id': cuenta_id,
            'referencia': cuenta.get('reference_no') or '',
            'estado': cuenta.get('state') or '',
            'es_cuenta_activa': cuenta_id == active_cuenta_id,
            'titular_cuenta': titular_nombre,
            'fecha_desembolso': cuenta.get('fecha_desembolso') or None,
            'fecha_cierre': cuenta.get('fecha_cierre'),
            'fecha_entrega': cuenta.get('fecha_entrega') or None,
            'valor_total_vehiculo': _money(cuenta.get('monto_total')),
            'inicial': _money(cuenta.get('monto_inicial')),
            'monto_fraccionado': _money(cuenta.get('monto_fraccionado')),
            'cuota_gracia': _money(cuenta.get('cuota_gracia')),
            'fecha_gracia': cuenta.get('fecha_gracia') or None,
            'periodo': cuenta.get('periodicidad') or '',
            'total_cuotas': cuenta.get('qty_cuotas') or 0,
            'monto_cuota': _money(cuenta.get('monto_cuota')),
            'saldo_restante': _money(saldo_restante),
            'cuotas_restantes': cuotas_restantes,
            'total_retrasado': _money(total_retrasado),
            'cuotas_retrasadas': cuotas_retrasadas,
            'total_pagado': _money(total_pagado),
            'cuotas_pagadas': cuotas_pagadas,
            'cuotas': cuotas_data,
        })

        # If partner not obtained from driver, take from cuenta
        if not partner_data and cuenta.get('partner_id'):
            pid = cuenta['partner_id'][0]
            partners = execute(
                'res.partner', 'search_read',
                [('id', '=', pid)],
                ['id', 'name', 'street', 'vat', 'country_id', 'tipo_documento'],
                limit=1,
            )
            if partners:
                p = partners[0]
                country = p.get('country_id')
                partner_data = {
                    'nombre': p.get('name') or '',
                    'direccion': p.get('street') or None,
                    'numero_documento': p.get('vat') or None,
                    'pais': country[1] if country else None,
                    'tipo_documento': p.get('tipo_documento') or None,
                }

    vehicle_data = {
        'placa': veh.get('license_plate') or '',
        'modelo': model_name,
        'numero_chasis': veh.get('vin_sn') or None,
        'total_cuentas': len(cuentas_data),
    }

    return {
        'fuente': 'legacy',
        'usuario': partner_data,
        'vehiculo': vehicle_data,
        'cuentas': cuentas_data,
        'financiera': LEGACY_FINANCIERA,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Controller
# ─────────────────────────────────────────────────────────────────────────────

class PlacaAPIController(http.Controller):

    @http.route(
        '/api/v1/placa',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        cors='*',
    )
    def consulta_por_placa(self, plate=None, **kwargs):
        """
        GET /api/v1/placa?plate=ABC-123

        Consulta la información completa de un vehículo por su placa.
        Busca primero en el Odoo local. Si no encuentra el vehículo,
        hace fallback al Odoo legacy (Qorilazo).

        No requiere autenticación.
        """
        try:
            # ── Validate plate param ────────────────────────────────────────
            if not plate:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'El parámetro plate es requerido.'),
                    status=422,
                )
            plate_upper = plate.strip().upper()

            # ── 1. Search in local Odoo ─────────────────────────────────────
            result = None
            try:
                result, _ = _search_local(plate_upper)
            except Exception:
                _logger.exception('PlacaAPI: Error buscando en Odoo local, placa=%s', plate_upper)

            # ── 2. Fallback to legacy Odoo ──────────────────────────────────
            if not result:
                _logger.info('PlacaAPI: Placa %s no encontrada en local; buscando en legacy.', plate_upper)
                try:
                    result = _search_legacy(plate_upper)
                except Exception:
                    _logger.exception('PlacaAPI: Error buscando en Odoo legacy, placa=%s', plate_upper)

            if not result:
                return _json_response(
                    _error(404, 'PLATE_NOT_FOUND',
                           'No se encontró ningún registro para la placa %s.' % plate_upper),
                    status=404,
                )

            return _json_response(_success(result))

        except Exception:
            _logger.exception('PlacaAPI: Error inesperado en GET /api/v1/placa')
            return _json_response(
                _error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'),
                status=500,
            )

