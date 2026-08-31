# -*- coding: utf-8 -*-
"""
API REST de Crédito para la app móvil.

  GET  /v1/credit/contracts                 Lista los contratos del cliente autenticado
  GET  /v1/credit/contracts/<id>             Detalle de un contrato + cronograma
  POST /v1/credit/simulate                   Simula un cronograma sin crear el contrato

Autenticación
  - Igual esquema que el resto de la app: header `Authorization: Bearer <token>`.
  - El token se valida contra el modelo `mobile.token`, que vive en `adt_comercial`.
  - adt_credito NO depende de adt_comercial (decisión de diseño: el motor de crédito es
    genérico). Por eso el token se busca de forma defensiva: si `mobile.token` no existe
    en el registro (adt_comercial no está instalado), se responde 501 en vez de un
    traceback. En este despliegue de ADT, adt_comercial sí está instalado, así que estos
    endpoints funcionan igual que el resto de `/v1/...` de la app.

Ver `context/adt-credito-guia-integracion-app.md` para el detalle de payloads.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from odoo import http
from odoo import fields as odoo_fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


# ── Helpers de respuesta (mismo formato que adt_comercial/controllers/mobile_api.py) ──

def _now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


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
        'meta': {'timestamp': _now_iso(), 'requestId': str(uuid.uuid4())},
    }


def _error(http_code, code, message):
    return {
        'success': False,
        'statusCode': http_code,
        'error': {'code': code, 'message': message},
        'meta': {'timestamp': _now_iso(), 'requestId': str(uuid.uuid4())},
    }


def _error_response(http_code, code, message):
    return _json_response(_error(http_code, code, message), status=http_code)


def _get_partner_from_token(auth_header):
    """Returns (partner_record, error_response|None)."""
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, _error_response(401, 'TOKEN_MISSING', 'Token ausente en el header Authorization.')

    if 'mobile.token' not in request.env.registry:
        return None, _error_response(
            501, 'MOBILE_AUTH_NOT_AVAILABLE',
            'El módulo de autenticación móvil (adt_comercial) no está instalado.',
        )

    raw_token = auth_header[7:].strip()
    token_rec = request.env['mobile.token'].sudo().search(
        [('token', '=', raw_token), ('revoked', '=', False)], limit=1)
    if not token_rec:
        return None, _error_response(401, 'TOKEN_INVALID', 'Token inválido o no encontrado.')
    if not token_rec.partner_id:
        return None, _error_response(403, 'TOKEN_WITHOUT_PARTNER', 'El token no tiene un cliente asociado.')
    return token_rec.partner_id, None


def _contrato_summary(contrato):
    return {
        'id': contrato.id,
        'referencia': contrato.name,
        'estado': contrato.estado,
        'semaforo': contrato.semaforo,
        'productId': contrato.product_id.id,
        'productName': contrato.product_id.display_name,
        'frecuencia': contrato.frecuencia,
        'numeroCuotas': contrato.numero_cuotas,
        'montoTotal': contrato.monto_total,
        'enganche': contrato.enganche,
        'montoFinanciado': contrato.monto_financiado,
        'montoCuota': contrato.monto_cuota,
        'fechaInicio': contrato.fecha_inicio.isoformat() if contrato.fecha_inicio else None,
        'saldoPendiente': contrato.saldo_pendiente,
        'moraTotal': contrato.mora_total,
        'cuotasVencidas': contrato.cuotas_vencidas,
        'cuotasPagadas': contrato.cuotas_pagadas,
        'pctPagado': round(contrato.pct_pagado, 2),
        'pctAtraso': round(contrato.pct_atraso, 2),
        'moneda': contrato.currency_id.name,
    }


def _cuota_detail(cuota):
    return {
        'id': cuota.id,
        'numeroCuota': cuota.numero_cuota,
        'fechaVencimiento': cuota.fecha_vencimiento.isoformat() if cuota.fecha_vencimiento else None,
        'monto': cuota.monto,
        'montoPagado': cuota.monto_pagado,
        'saldo': cuota.saldo,
        'estado': cuota.estado,
        'diasMora': cuota.dias_mora,
        'moraMonto': cuota.mora_monto,
        'moraPagada': cuota.mora_pagada,
        'moraPendiente': cuota.mora_pendiente,
    }


class CreditoMobileController(http.Controller):

    @http.route('/v1/credit/contracts', type='http', auth='none', methods=['GET'], csrf=False, cors='*')
    def list_contracts(self, **kwargs):
        try:
            auth_header = request.httprequest.headers.get('Authorization', '')
            partner, err = _get_partner_from_token(auth_header)
            if err:
                return err

            contratos = request.env['credito.contrato'].sudo().search(
                [('partner_id', '=', partner.id)], order='fecha_inicio desc')
            data = [_contrato_summary(c) for c in contratos]
            return _json_response(_success(data))
        except Exception:
            _logger.exception('Error in GET /v1/credit/contracts')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route('/v1/credit/contracts/<int:contrato_id>', type='http', auth='none', methods=['GET'],
                csrf=False, cors='*')
    def contract_detail(self, contrato_id, **kwargs):
        try:
            auth_header = request.httprequest.headers.get('Authorization', '')
            partner, err = _get_partner_from_token(auth_header)
            if err:
                return err

            contrato = request.env['credito.contrato'].sudo().search(
                [('id', '=', contrato_id), ('partner_id', '=', partner.id)], limit=1)
            if not contrato:
                return _json_response(
                    _error(404, 'CONTRACT_NOT_FOUND', 'No existe el contrato indicado.'), status=404)

            data = _contrato_summary(contrato)
            data['cronograma'] = [_cuota_detail(c) for c in contrato.cuota_ids]
            return _json_response(_success(data))
        except Exception:
            _logger.exception('Error in GET /v1/credit/contracts/<id>')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)

    @http.route('/v1/credit/simulate', type='http', auth='none', methods=['POST'], csrf=False, cors='*')
    def simulate(self, **kwargs):
        try:
            auth_header = request.httprequest.headers.get('Authorization', '')
            partner, err = _get_partner_from_token(auth_header)
            if err:
                return err

            raw_body = request.httprequest.data
            body = json.loads(raw_body) if raw_body else {}

            product_id = body.get('productId')
            cantidad = float(body.get('cantidad') or 1)
            enganche = float(body.get('enganche') or 0)
            frecuencia = body.get('frecuencia') or 'mensual'
            numero_cuotas = int(body.get('numeroCuotas') or 0)

            if not product_id:
                return _json_response(_error(422, 'VALIDATION_ERROR', 'productId es requerido.'), status=422)
            if frecuencia not in ('diario', 'semanal', 'quincenal', 'mensual'):
                return _json_response(_error(422, 'VALIDATION_ERROR', 'frecuencia inválida.'), status=422)
            if numero_cuotas <= 0:
                return _json_response(
                    _error(422, 'VALIDATION_ERROR', 'numeroCuotas debe ser mayor a cero.'), status=422)

            product = request.env['product.product'].sudo().browse(int(product_id))
            if not product.exists() or not product.es_financiable:
                return _json_response(_error(
                    404, 'PRODUCT_NOT_FINANCIABLE',
                    'El producto no existe o no está disponible a crédito.'), status=404)

            monto_total = product.list_price * cantidad
            monto_financiado = monto_total - enganche
            if monto_financiado <= 0:
                return _json_response(_error(
                    422, 'VALIDATION_ERROR', 'El enganche debe ser menor al monto total.'), status=422)

            fecha_inicio = odoo_fields.Date.context_today(request.env['credito.contrato'])
            cuotas = request.env['credito.contrato'].sudo()._calcular_cronograma(
                monto_financiado, numero_cuotas, frecuencia, fecha_inicio)

            data = {
                'productId': product.id,
                'productName': product.display_name,
                'montoTotal': monto_total,
                'enganche': enganche,
                'montoFinanciado': monto_financiado,
                'frecuencia': frecuencia,
                'numeroCuotas': numero_cuotas,
                'montoCuota': cuotas[0]['monto'] if cuotas else 0,
                'cronograma': [
                    {
                        'numeroCuota': c['numero_cuota'],
                        'fechaVencimiento': c['fecha_vencimiento'].isoformat(),
                        'monto': c['monto'],
                    }
                    for c in cuotas
                ],
            }
            return _json_response(_success(data))
        except Exception:
            _logger.exception('Error in POST /v1/credit/simulate')
            return _json_response(_error(500, 'INTERNAL_ERROR', 'Error inesperado en el servidor.'), status=500)
