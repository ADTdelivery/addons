# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class CapturaAPI(http.Controller):

    @http.route(
        '/api/adt/captura/mora',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_captura_mora(self, **kwargs):
        """
        Returns the list of vehicles/accounts that require capture action.

        Optional query params:
            - source_type     : filter by 'mora' | 'papeleta' | 'ambos' | 'none'
            - captura_prioridad: filter by 'normal' | 'urgente'
            - captura_existente: filter by '1' (true) | '0' (false)
            - limit           : max records to return (default 100)
            - offset          : pagination offset (default 0)

        Response body:
        {
            "count": <int>,
            "records": [
                {
                    "partner_id": {"id": <int>, "name": <str>},
                    "vehicle_id": {
                        "id": <int>,
                        "display_name": <str>,
                        "license_plate": <str>
                    },
                    "source_type": <str>,
                    "papeleta_id": {"id": <int>, "name": <str>} | null,
                    "dias_mora": <int>,
                    "numero_cuotas_vencidas": <int>,
                    "monto_vencido": <float>,
                    "fecha_cronograma": <str|null>,
                    "user_id": {"id": <int>, "name": <str>} | null,
                    "captura_existente": <bool>,
                    "captura_prioridad": <str>,
                    "en_mantenimiento_tvs": <bool>,
                    "dias_en_mantenimiento_tvs": <int>
                },
                ...
            ]
        }
        """
        try:
            # ── pagination & filters ──────────────────────────────────────────
            limit = int(kwargs.get('limit', 100))
            offset = int(kwargs.get('offset', 0))

            domain = []

            source_type = kwargs.get('source_type')
            if source_type:
                domain.append(('source_type', '=', source_type))

            captura_prioridad = kwargs.get('captura_prioridad')
            if captura_prioridad:
                domain.append(('cuenta_id.captura_prioridad', '=', captura_prioridad))

            captura_existente = kwargs.get('captura_existente')
            if captura_existente is not None and captura_existente != '':
                domain.append(('captura_existente', '=', captura_existente in ('1', 'true', 'True')))

            # ── query ─────────────────────────────────────────────────────────
            MoraModel = request.env['adt.captura.mora'].sudo()
            total_count = MoraModel.search_count(domain)
            records = MoraModel.search(domain, limit=limit, offset=offset)

            # ── pre-fetch cuenta computed fields safely ────────────────────────
            # _compute_qty_cuotas in comercial_cuentas uses bare `self.state`
            # (no for-loop), so Odoo crashes when it tries to batch-compute on
            # more than one record.
            # Browsing each cuenta ID individually in a separate env call
            # guarantees the prefetch set contains exactly one record, making
            # `self` a true singleton inside the compute method.
            cuenta_ids = records.mapped('cuenta_id').ids  # plain list of ints
            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta_computed = {}
            for cid in cuenta_ids:
                c_single = CuentaModel.browse(cid)
                try:
                    cuenta_computed[cid] = {
                        'qty_cuotas_pagadas': c_single.qty_cuotas_pagadas or 0,
                        'qty_cuotas_restantes': c_single.qty_cuotas_restantes or 0,
                        'qty_cuotas_retrasado': c_single.qty_cuotas_retrasado or 0,
                        'cuotas_saldo': c_single.cuotas_saldo or 0.0,
                    }
                except Exception:
                    _logger.warning(
                        'Could not compute cuota fields for cuenta id=%s', cid, exc_info=True
                    )
                    cuenta_computed[cid] = {
                        'qty_cuotas_pagadas': 0,
                        'qty_cuotas_restantes': 0,
                        'qty_cuotas_retrasado': 0,
                        'cuotas_saldo': 0.0,
                    }

            # ── serialise ─────────────────────────────────────────────────────
            result = []
            for rec in records:
                # vehicle
                vehicle_data = None
                if rec.vehicle_id:
                    vehicle_data = {
                        'id': rec.vehicle_id.id,
                        'display_name': rec.vehicle_id.display_name or '',
                        'license_plate': rec.vehicle_id.license_plate or '',
                    }

                # papeleta
                papeleta_data = None
                if rec.papeleta_id:
                    papeleta_data = {
                        'id': rec.papeleta_id.id,
                        'name': rec.papeleta_id.display_name or '',
                        'monto': rec.papeleta_id.monto or 0.0,
                    }

                # user / asesor
                user_data = None
                if rec.user_id:
                    user_data = {
                        'id': rec.user_id.id,
                        'name': rec.user_id.name or '',
                    }

                # cuenta — use pre-fetched computed values
                cuenta_data = None
                if rec.cuenta_id:
                    c = rec.cuenta_id
                    cc = cuenta_computed.get(c.id, {})
                    cuenta_data = {
                        'id': c.id,
                        'reference_no': c.reference_no or '',
                        'state': c.state or '',
                        'tipo_financiera': c.tipo_financiera or '',
                        'periodicidad': c.periodicidad or '',
                        'monto_total': c.monto_total or 0.0,
                        'monto_cuota': c.monto_cuota or 0.0,
                        'qty_cuotas': c.qty_cuotas or 0,
                        'qty_cuotas_pagadas': cc.get('qty_cuotas_pagadas', 0),
                        'qty_cuotas_restantes': cc.get('qty_cuotas_restantes', 0),
                        'qty_cuotas_retrasado': cc.get('qty_cuotas_retrasado', 0),
                        'cuotas_saldo': cc.get('cuotas_saldo', 0.0),
                        'fecha_desembolso': c.fecha_desembolso.isoformat() if c.fecha_desembolso else None,
                    }

                result.append({
                    'client': {
                        'id': rec.partner_id.id,
                        'name': rec.partner_id.name or '',
                    },
                    'cuenta_id': cuenta_data,
                    'vehicle_id': vehicle_data,
                    'source_type': rec.source_type or 'none',
                    'papeleta_id': papeleta_data,
                    'dias_mora': rec.dias_mora or 0,
                    'numero_cuotas_vencidas': rec.numero_cuotas_vencidas or 0,
                    'monto_vencido': rec.monto_vencido or 0.0,
                    'fecha_cronograma': rec.fecha_cronograma.isoformat() if rec.fecha_cronograma else None,
                    'adviser': user_data,
                    'captura_existente': rec.captura_existente or False,
                    'captura_prioridad': rec.captura_prioridad or '',
                    'en_mantenimiento_tvs': rec.en_mantenimiento_tvs or False,
                    'dias_en_mantenimiento_tvs': rec.dias_en_mantenimiento_tvs or 0,
                })

            payload = {
                'count': total_count,
                'records': result,
            }

            return Response(
                json.dumps(payload, ensure_ascii=False),
                status=200,
                mimetype='application/json',
            )

        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora: %s', e)
            error_payload = {'error': str(e)}
            return Response(
                json.dumps(error_payload),
                status=500,
                mimetype='application/json',
            )

    # ─────────────────────────────────────────────────────────────────────────
    # DETAIL endpoint
    # GET /api/adt/captura/mora/detail?cuenta_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/mora/detail',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_captura_mora_detail(self, **kwargs):
        """
        Returns full detail for a single cuenta record.

        Required query param:
            - cuenta_id : ID of the adt.comercial.cuentas record

        Response body:
        {
            "count": 1,
            "record": {
                "cuenta_id": { ...full cuenta detail + cuotas list... },
                "expediente_id": { ...expediente del cliente... } | null,
                "papeletas": [ ...all papeletas for the vehicle... ],
                "vehicle_id": { ...fleet.vehicle detail... } | null,
                "mantenimientos": [ ...adt.tvs.mantenimiento records for vehicle... ]
            }
        }
        """
        try:
            cuenta_id_raw = kwargs.get('cuenta_id')
            if not cuenta_id_raw:
                return Response(
                    json.dumps({'error': 'cuenta_id is required'}),
                    status=400,
                    mimetype='application/json',
                )
            try:
                cuenta_id_int = int(cuenta_id_raw)
            except (ValueError, TypeError):
                return Response(
                    json.dumps({'error': 'cuenta_id must be an integer'}),
                    status=400,
                    mimetype='application/json',
                )

            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta = CuentaModel.browse(cuenta_id_int)
            if not cuenta.exists():
                return Response(
                    json.dumps({'error': 'cuenta not found'}),
                    status=404,
                    mimetype='application/json',
                )

            # ── Compute calculated fields safely on a singleton ───────────────
            def _safe_compute(record, field_name, default=None):
                try:
                    return getattr(record, field_name)
                except Exception:
                    _logger.warning('Could not read %s on record %s', field_name, record.id, exc_info=True)
                    return default

            # ── Cuotas ────────────────────────────────────────────────────────
            cuotas_data = []
            for cuota in cuenta.cuota_ids.filtered(lambda c: c.type == 'cuota').sorted('id'):
                cuotas_data.append({
                    'id': cuota.id,
                    'name': cuota.name or '',
                    'numero_cuota': cuota.id,
                    'fecha_vencimiento': cuota.fecha_cronograma.isoformat() if cuota.fecha_cronograma else None,
                    'fecha_pago': cuota.real_date or None,
                    'monto_cuota': cuota.monto or 0.0,
                    'monto_pagado': _safe_compute(cuota, 'cuotas_pagado', 0.0) if False else (
                        (cuota.monto or 0.0) - (_safe_compute(cuota, 'saldo', 0.0) or 0.0)
                    ),
                    'monto_pendiente': _safe_compute(cuota, 'saldo', 0.0) or 0.0,
                    'state': cuota.state or '',
                    'dias_mora': _safe_compute(cuota, 'mora_dias', 0) or 0,
                    'monto_mora': _safe_compute(cuota, 'mora_total', 0.0) or 0.0,
                    'mora_pendiente': _safe_compute(cuota, 'mora_pendiente', 0.0) or 0.0,
                    'numero_operacion': cuota.numero_operacion or None,
                })

            # ── cuenta_id block ───────────────────────────────────────────────
            cuenta_data = {
                'id': cuenta.id,
                'reference_no': cuenta.reference_no or '',
                'state': cuenta.state or '',
                'tipo_financiera': cuenta.tipo_financiera or '',
                'periodicidad': cuenta.periodicidad or '',
                'monto_total': cuenta.monto_total or 0.0,
                'monto_cuota': cuenta.monto_cuota or 0.0,
                'qty_cuotas': cuenta.qty_cuotas or 0,
                'qty_cuotas_pagadas': _safe_compute(cuenta, 'qty_cuotas_pagadas', 0) or 0,
                'qty_cuotas_restantes': _safe_compute(cuenta, 'qty_cuotas_restantes', 0) or 0,
                'qty_cuotas_retrasado': _safe_compute(cuenta, 'qty_cuotas_retrasado', 0) or 0,
                'cuotas_saldo': _safe_compute(cuenta, 'cuotas_saldo', 0.0) or 0.0,
                'fecha_desembolso': cuenta.fecha_desembolso.isoformat() if cuenta.fecha_desembolso else None,
                'mora_pendiente': _safe_compute(cuenta, 'mora_pendiente', 0.0) or 0.0,
                'moras_dias_total': _safe_compute(cuenta, 'mora_dias_total', 0) or 0,
                'cuotas': cuotas_data,
            }

            # ── expediente: linked through partner_id ─────────────────────────
            expediente_data = None
            if cuenta.partner_id:
                Expediente = request.env['adt.expediente'].sudo()
                expediente = Expediente.search(
                    [('cliente_id', '=', cuenta.partner_id.id)],
                    limit=1,
                    order='id desc',
                )
                if expediente:
                    expediente_data = {
                        'id': expediente.id,
                        'name': expediente.display_name or '',
                        'state': expediente.state or '',
                        'partner_id': {
                            'id': expediente.cliente_id.id,
                            'name': expediente.cliente_id.name or '',
                        } if expediente.cliente_id else None,
                        'fecha': expediente.fecha.isoformat() if expediente.fecha else None,
                        'vehiculo': expediente.vehiculo or '',
                        'placa': expediente.placa or '',
                        'chasis': expediente.chasis or '',
                    }

            # ── papeletas: all for this vehicle ───────────────────────────────
            papeletas_data = []
            if cuenta.vehiculo_id:
                Papeleta = request.env['adt.papeleta'].sudo()
                papeletas = Papeleta.search(
                    [('vehicle_id', '=', cuenta.vehiculo_id.id)],
                    order='fecha_papeleta desc',
                )
                for p in papeletas:
                    # Build cuotas list for fraccionado papeletas
                    p_cuotas = []
                    for pc in p.cuotas_ids.sorted('id'):
                        p_cuotas.append({
                            'id': pc.id,
                            'name': pc.name or '',
                            'due_date': pc.due_date.isoformat() if pc.due_date else None,
                            'amount': pc.amount or 0.0,
                            'state': pc.state or '',
                        })
                    papeletas_data.append({
                        'id': p.id,
                        'name': p.name or '',
                        'state': p.state or '',
                        'monto': p.monto or 0.0,
                        'fecha_emision': p.fecha_papeleta.isoformat() if p.fecha_papeleta else None,
                        'fecha_vencimiento': p.fecha_vencimiento_final.isoformat() if p.fecha_vencimiento_final else None,
                        'payment_method': p.payment_method or '',
                        'capturado': p.capturado or False,
                        'recolocada': p.recolocada or False,
                        'detalle': p.detalle or '',
                        'vehicle_id': {
                            'id': p.vehicle_id.id,
                            'display_name': p.vehicle_id.display_name or '',
                        } if p.vehicle_id else None,
                        'cuotas': p_cuotas,
                    })

            # ── vehicle detail ────────────────────────────────────────────────
            vehicle_data = None
            if cuenta.vehiculo_id:
                v = cuenta.vehiculo_id
                vehicle_data = {
                    'id': v.id,
                    'display_name': v.display_name or '',
                    'license_plate': v.license_plate or '',
                    'model_id': {
                        'id': v.model_id.id,
                        'name': v.model_id.name or '',
                    } if v.model_id else None,
                    'brand_id': {
                        'id': v.model_id.brand_id.id,
                        'name': v.model_id.brand_id.name or '',
                    } if v.model_id and v.model_id.brand_id else None,
                    'vin_sn': v.vin_sn or '',
                    'state_id': {
                        'id': v.state_id.id,
                        'name': v.state_id.name or '',
                    } if v.state_id else None,
                    'odometer': _safe_compute(v, 'odometer', 0.0) or 0.0,
                    'odometer_unit': getattr(v, 'odometer_unit', '') or '',
                    'acquisition_date': v.acquisition_date.isoformat() if getattr(v, 'acquisition_date', None) else None,
                    'driver_id': {
                        'id': v.driver_id.id,
                        'name': v.driver_id.name or '',
                    } if getattr(v, 'driver_id', None) else None,
                }

            # ── mantenimientos: adt.tvs.mantenimiento for this vehicle ─────────
            mantenimientos_data = []
            if cuenta.vehiculo_id:
                Mantenimiento = request.env['adt.tvs.mantenimiento'].sudo()
                mantenimientos = Mantenimiento.search(
                    [('vehicle_id', '=', cuenta.vehiculo_id.id)],
                    order='date_inicio_revision desc',
                )
                for m in mantenimientos:
                    mantenimientos_data.append({
                        'id': m.id,
                        'name': m.name or '',
                        'state': m.state or '',
                        'vehicle_id': {
                            'id': m.vehicle_id.id,
                            'display_name': m.vehicle_id.display_name or '',
                        } if m.vehicle_id else None,
                        'fecha_inicio': m.date_inicio_revision.isoformat() if m.date_inicio_revision else None,
                        'fecha_fin': m.date_fin_revision.isoformat() if m.date_fin_revision else None,
                        'dias_en_mantenimiento': m.days_in_taller or 0,
                        'motivo_ingreso': m.motivo_ingreso or '',
                        'tiene_garantia': m.tiene_garantia or False,
                        'gasto_mantenimiento': m.gasto_mantenimiento or 0.0,
                        'punto_autorizado': {
                            'id': m.punto_autorizado_id.id,
                            'name': m.punto_autorizado_id.name or '',
                        } if m.punto_autorizado_id else None,
                    })

            payload = {
                'count': 1,
                'record': {
                    'cuenta_id': cuenta_data,
                    'expediente_id': expediente_data,
                    'papeletas': papeletas_data,
                    'vehicle_id': vehicle_data,
                    'mantenimientos': mantenimientos_data,
                },
            }

            return Response(
                json.dumps(payload, ensure_ascii=False, default=str),
                status=200,
                mimetype='application/json',
            )

        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora/detail: %s', e)
            error_payload = {'error': str(e)}
            return Response(
                json.dumps(error_payload),
                status=500,
                mimetype='application/json',
            )

