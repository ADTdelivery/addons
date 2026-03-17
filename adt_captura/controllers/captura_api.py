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
        auth='none',
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
    # DETAIL endpoint (legacy – kept for backwards compatibility)
    # GET /api/adt/captura/mora/detail?cuenta_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _resolve_vehicle(self, vehicle_id_raw):
        """
        Resolve a vehicle_id query param to a fleet.vehicle singleton.
        Returns (vehicle, error_response) – exactly one of them is None.
        """
        if not vehicle_id_raw:
            return None, Response(
                json.dumps({'error': 'vehicle_id is required'}),
                status=400,
                mimetype='application/json',
            )
        try:
            vehicle_id_int = int(vehicle_id_raw)
        except (ValueError, TypeError):
            return None, Response(
                json.dumps({'error': 'vehicle_id must be an integer'}),
                status=400,
                mimetype='application/json',
            )
        vehicle = request.env['fleet.vehicle'].sudo().browse(vehicle_id_int)
        if not vehicle.exists():
            return None, Response(
                json.dumps({'error': 'vehicle not found'}),
                status=404,
                mimetype='application/json',
            )
        return vehicle, None

    @staticmethod
    def _safe_get(record, field_name, default=None):
        try:
            return getattr(record, field_name)
        except Exception:
            _logger.warning('Could not read %s on %s(%s)', field_name, record._name, record.id, exc_info=True)
            return default

    # ─────────────────────────────────────────────────────────────────────────
    # /api/adt/captura/mora/detail/cuenta?vehicle_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/mora/detail/cuenta',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_cuenta(self, **kwargs):
        """
        Returns full cuenta detail (including cuotas) for the given vehicle.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record
        """
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta = CuentaModel.search([('vehiculo_id', '=', vehicle.id)], limit=1, order='id desc')
            if not cuenta.exists():
                return Response(
                    json.dumps({'error': 'No cuenta found for this vehicle'}),
                    status=404,
                    mimetype='application/json',
                )

            # cuotas
            cuotas_data = []
            for cuota in cuenta.cuota_ids.filtered(lambda c: c.type == 'cuota').sorted('id'):
                cuotas_data.append({
                    'id': cuota.id,
                    'name': cuota.name or '',
                    'fecha_vencimiento': cuota.fecha_cronograma.isoformat() if cuota.fecha_cronograma else None,
                    'fecha_pago': cuota.real_date or None,
                    'monto_cuota': cuota.monto or 0.0,
                    'monto_pagado': (cuota.monto or 0.0) - (self._safe_get(cuota, 'saldo', 0.0) or 0.0),
                    'monto_pendiente': self._safe_get(cuota, 'saldo', 0.0) or 0.0,
                    'state': cuota.state or '',
                    'dias_mora': self._safe_get(cuota, 'mora_dias', 0) or 0,
                    'monto_mora': self._safe_get(cuota, 'mora_total', 0.0) or 0.0,
                    'mora_pendiente': self._safe_get(cuota, 'mora_pendiente', 0.0) or 0.0,
                    'numero_operacion': cuota.numero_operacion or None,
                })

            cuenta_data = {
                'id': cuenta.id,
                'reference_no': cuenta.reference_no or '',
                'state': cuenta.state or '',
                'tipo_financiera': cuenta.tipo_financiera or '',
                'periodicidad': cuenta.periodicidad or '',
                'monto_total': cuenta.monto_total or 0.0,
                'monto_cuota': cuenta.monto_cuota or 0.0,
                'qty_cuotas': cuenta.qty_cuotas or 0,
                'qty_cuotas_pagadas': self._safe_get(cuenta, 'qty_cuotas_pagadas', 0) or 0,
                'qty_cuotas_restantes': self._safe_get(cuenta, 'qty_cuotas_restantes', 0) or 0,
                'qty_cuotas_retrasado': self._safe_get(cuenta, 'qty_cuotas_retrasado', 0) or 0,
                'cuotas_saldo': self._safe_get(cuenta, 'cuotas_saldo', 0.0) or 0.0,
                'fecha_desembolso': cuenta.fecha_desembolso.isoformat() if cuenta.fecha_desembolso else None,
                'mora_pendiente': self._safe_get(cuenta, 'mora_pendiente', 0.0) or 0.0,
                'moras_dias_total': self._safe_get(cuenta, 'mora_dias_total', 0) or 0,
                'cuotas': cuotas_data,
            }

            return Response(
                json.dumps({'count': 1, 'record': cuenta_data}, ensure_ascii=False, default=str),
                status=200,
                mimetype='application/json',
            )
        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora/detail/cuenta: %s', e)
            return Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')

    # ─────────────────────────────────────────────────────────────────────────
    # /api/adt/captura/mora/detail/expediente?vehicle_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/mora/detail/expediente',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_expediente(self, **kwargs):
        """
        Returns expediente data for the partner linked to the given vehicle.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record
        """
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            # Find partner via cuenta or driver
            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta = CuentaModel.search([('vehiculo_id', '=', vehicle.id)], limit=1, order='id desc')
            partner = cuenta.partner_id if cuenta and cuenta.partner_id else (vehicle.driver_id or None)

            if not partner:
                return Response(
                    json.dumps({'count': 0, 'record': None}),
                    status=200,
                    mimetype='application/json',
                )

            Expediente = request.env['adt.expediente'].sudo()
            expediente = Expediente.search([('cliente_id', '=', partner.id)], limit=1, order='id desc')
            if not expediente:
                return Response(
                    json.dumps({'count': 0, 'record': None}),
                    status=200,
                    mimetype='application/json',
                )

            def _img_url(rec_id, field_name, has_data):
                if not has_data:
                    return None
                return '/web/image/adt.expediente/%s/%s' % (rec_id, field_name)

            eid = expediente.id

            expediente_data = {
                'id': eid,
                'name': expediente.display_name or '',
                'state': expediente.state or '',
                'cliente_id': {
                    'id': expediente.cliente_id.id,
                    'name': expediente.cliente_id.name or '',
                } if expediente.cliente_id else None,
                'asesora_id': {
                    'id': expediente.asesora_id.id,
                    'name': expediente.asesora_id.name or '',
                } if expediente.asesora_id else None,
                'fecha': expediente.fecha.isoformat() if expediente.fecha else None,
                'vehiculo': expediente.vehiculo or '',
                'placa': expediente.placa or '',
                'chasis': expediente.chasis or '',
                'documento_identidad': {
                    'foto_dni_frente': _img_url(eid, 'foto_dni_frente', expediente.foto_dni_frente),
                    'foto_dni_reverso': _img_url(eid, 'foto_dni_reverso', expediente.foto_dni_reverso),
                    'estado_foto_dni': expediente.estado_foto_dni or None,
                    'obs_foto_dni': expediente.obs_foto_dni or None,
                    'foto_ce_frente': _img_url(eid, 'foto_ce_frente', expediente.foto_ce_frente),
                    'foto_ce_reverso': _img_url(eid, 'foto_ce_reverso', expediente.foto_ce_reverso),
                    'estado_foto_ce': expediente.estado_foto_ce or None,
                    'obs_foto_ce': expediente.obs_foto_ce or None,
                    'foto_pasaporte_frente': _img_url(eid, 'foto_pasaporte_frente', expediente.foto_pasaporte_frente),
                    'foto_pasaporte_reverso': _img_url(eid, 'foto_pasaporte_reverso', expediente.foto_pasaporte_reverso),
                    'estado_foto_pasaporte': expediente.estado_foto_pasaporte or None,
                    'obs_foto_pasaporte': expediente.obs_foto_pasaporte or None,
                },
                'domicilio': {
                    'direccion_cliente': expediente.direccion_cliente or None,
                    'estado_direccion': expediente.estado_direccion or None,
                    'obs_direccion': expediente.obs_direccion or None,
                    'tipo_vivienda': expediente.tipo_vivienda or None,
                    'tiempo_viviendo': expediente.tiempo_viviendo or None,
                    'propietario_contacto': expediente.propietario_contacto or None,
                    'foto_vivienda': _img_url(eid, 'foto_vivienda', expediente.foto_vivienda),
                    'estado_foto_vivienda': expediente.estado_foto_vivienda or None,
                    'obs_foto_vivienda': expediente.obs_foto_vivienda or None,
                    'foto_ubicacion_actual': _img_url(eid, 'foto_ubicacion_actual', expediente.foto_ubicacion_actual),
                    'estado_foto_ubicacion': expediente.estado_foto_ubicacion or None,
                    'obs_foto_ubicacion': expediente.obs_foto_ubicacion or None,
                    'foto_fachada_domicilio': _img_url(eid, 'foto_fachada_domicilio', expediente.foto_fachada_domicilio),
                    'estado_foto_fachada': expediente.estado_foto_fachada or None,
                    'obs_foto_fachada': expediente.obs_foto_fachada or None,
                    'foto_contrato_alquiler': _img_url(eid, 'foto_contrato_alquiler', expediente.foto_contrato_alquiler),
                    'estado_foto_contrato': expediente.estado_foto_contrato or None,
                    'obs_foto_contrato': expediente.obs_foto_contrato or None,
                },
                'ingresos': {
                    'foto_ingresos': _img_url(eid, 'foto_ingresos', expediente.foto_ingresos),
                    'estado_foto_ingresos': expediente.estado_foto_ingresos or None,
                    'obs_foto_ingresos': expediente.obs_foto_ingresos or None,
                    'foto_recibo': _img_url(eid, 'foto_recibo', expediente.foto_recibo),
                    'estado_foto_recibo': expediente.estado_foto_recibo or None,
                    'obs_foto_recibo': expediente.obs_foto_recibo or None,
                },
                'licencia': {
                    'foto_licencia': _img_url(eid, 'foto_licencia', expediente.foto_licencia),
                    'estado_foto_licencia': expediente.estado_foto_licencia or None,
                    'obs_foto_licencia': expediente.obs_foto_licencia or None,
                },
                'mototaxista': {
                    'foto_moto': _img_url(eid, 'foto_moto', expediente.foto_moto),
                    'estado_foto_moto': expediente.estado_foto_moto or None,
                    'obs_foto_moto': expediente.obs_foto_moto or None,
                    'foto_soat': _img_url(eid, 'foto_soat', expediente.foto_soat),
                    'estado_foto_soat': expediente.estado_foto_soat or None,
                    'obs_foto_soat': expediente.obs_foto_soat or None,
                    'foto_tarjeta_propiedad_frente': _img_url(eid, 'foto_tarjeta_propiedad_frente', expediente.foto_tarjeta_propiedad_frente),
                    'foto_tarjeta_propiedad_reverso': _img_url(eid, 'foto_tarjeta_propiedad_reverso', expediente.foto_tarjeta_propiedad_reverso),
                    'estado_foto_tarjeta': expediente.estado_foto_tarjeta or None,
                    'obs_foto_tarjeta': expediente.obs_foto_tarjeta or None,
                    'ganancia_diaria_mensual': expediente.ganancia_diaria_mensual or None,
                    'tiempo_trabajando': expediente.tiempo_trabajando or None,
                    'moto_empresa': expediente.moto_empresa or None,
                    'moto_propiedad': expediente.moto_propiedad or None,
                },
                'no_mototaxista': {
                    'foto_lugar_trabajo': _img_url(eid, 'foto_lugar_trabajo', expediente.foto_lugar_trabajo),
                    'estado_foto_lugar_trabajo': expediente.estado_foto_lugar_trabajo or None,
                    'obs_foto_lugar_trabajo': expediente.obs_foto_lugar_trabajo or None,
                    'foto_lugar_negocio': _img_url(eid, 'foto_lugar_negocio', expediente.foto_lugar_negocio),
                    'estado_foto_lugar_negocio': expediente.estado_foto_lugar_negocio or None,
                    'obs_foto_lugar_negocio': expediente.obs_foto_lugar_negocio or None,
                    'foto_boletas': _img_url(eid, 'foto_boletas', expediente.foto_boletas),
                    'estado_foto_boletas': expediente.estado_foto_boletas or None,
                    'obs_foto_boletas': expediente.obs_foto_boletas or None,
                    'foto_estado_cuenta': _img_url(eid, 'foto_estado_cuenta', expediente.foto_estado_cuenta),
                    'estado_foto_estado_cuenta': expediente.estado_foto_estado_cuenta or None,
                    'obs_foto_estado_cuenta': expediente.obs_foto_estado_cuenta or None,
                    'ganancia_diaria_mensual': expediente.ganancia_diaria_mensual_no or None,
                    'tiempo_trabajando': expediente.tiempo_trabajando_no or None,
                },
                'sentinel': {
                    'foto_sentinel_1': _img_url(eid, 'foto_sentinel_1', expediente.foto_sentinel_1),
                    'foto_sentinel_2': _img_url(eid, 'foto_sentinel_2', expediente.foto_sentinel_2),
                    'estado_foto_sentinel': expediente.estado_foto_sentinel or None,
                    'obs_foto_sentinel': expediente.obs_foto_sentinel or None,
                },
                'fase_final': {
                    'foto_entrega': _img_url(eid, 'foto_entrega', expediente.foto_entrega),
                    'placa': expediente.placa or None,
                    'chasis': expediente.chasis or None,
                },
                'referencias': {
                    'estado_referencias': expediente.estado_referencias or None,
                    'obs_referencias': expediente.obs_referencias or None,
                    'lista': [
                        {'nombre': expediente.ref_1_name or None, 'telefono': expediente.ref_1_phone or None, 'vinculo': expediente.ref_1_vinculo or None},
                        {'nombre': expediente.ref_2_name or None, 'telefono': expediente.ref_2_phone or None, 'vinculo': expediente.ref_2_vinculo or None},
                        {'nombre': expediente.ref_3_name or None, 'telefono': expediente.ref_3_phone or None, 'vinculo': expediente.ref_3_vinculo or None},
                        {'nombre': expediente.ref_4_name or None, 'telefono': expediente.ref_4_phone or None, 'vinculo': expediente.ref_4_vinculo or None},
                    ],
                },
            }

            return Response(
                json.dumps({'count': 1, 'record': expediente_data}, ensure_ascii=False, default=str),
                status=200,
                mimetype='application/json',
            )
        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora/detail/expediente: %s', e)
            return Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')

    # ─────────────────────────────────────────────────────────────────────────
    # /api/adt/captura/mora/detail/papeletas?vehicle_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/mora/detail/papeletas',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_papeletas(self, **kwargs):
        """
        Returns all papeletas linked to the given vehicle.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record
        """
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            Papeleta = request.env['adt.papeleta'].sudo()
            papeletas = Papeleta.search([('vehicle_id', '=', vehicle.id)], order='fecha_papeleta desc')

            papeletas_data = []
            for p in papeletas:
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

            return Response(
                json.dumps({'count': len(papeletas_data), 'records': papeletas_data}, ensure_ascii=False, default=str),
                status=200,
                mimetype='application/json',
            )
        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora/detail/papeletas: %s', e)
            return Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')

    # ─────────────────────────────────────────────────────────────────────────
    # /api/adt/captura/mora/detail/vehicle?vehicle_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/mora/detail/vehicle',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_vehicle(self, **kwargs):
        """
        Returns fleet.vehicle detail for the given vehicle_id.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record
        """
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            v = vehicle
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
                'odometer': self._safe_get(v, 'odometer', 0.0) or 0.0,
                'odometer_unit': getattr(v, 'odometer_unit', '') or '',
                'acquisition_date': v.acquisition_date.isoformat() if getattr(v, 'acquisition_date', None) else None,
                'driver_id': {
                    'id': v.driver_id.id,
                    'name': v.driver_id.name or '',
                } if getattr(v, 'driver_id', None) else None,
            }

            return Response(
                json.dumps({'count': 1, 'record': vehicle_data}, ensure_ascii=False, default=str),
                status=200,
                mimetype='application/json',
            )
        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora/detail/vehicle: %s', e)
            return Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')

    # ─────────────────────────────────────────────────────────────────────────
    # /api/adt/captura/mora/detail/mantenimientos?vehicle_id=<int>
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/mora/detail/mantenimientos',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_mantenimientos(self, **kwargs):
        """
        Returns all adt.tvs.mantenimiento records for the given vehicle.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record
        """
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            Mantenimiento = request.env['adt.tvs.mantenimiento'].sudo()
            mantenimientos = Mantenimiento.search(
                [('vehicle_id', '=', vehicle.id)],
                order='date_inicio_revision desc',
            )

            mantenimientos_data = []
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

            return Response(
                json.dumps({'count': len(mantenimientos_data), 'records': mantenimientos_data}, ensure_ascii=False, default=str),
                status=200,
                mimetype='application/json',
            )
        except Exception as e:
            _logger.exception('Error in /api/adt/captura/mora/detail/mantenimientos: %s', e)
            return Response(json.dumps({'error': str(e)}), status=500, mimetype='application/json')

    # ─────────────────────────────────────────────────────────────────────────
    # FULL DETAIL endpoint (legacy – full combined response)
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
            def _img_url(model_name, rec_id, field_name, has_data):
                """Return Odoo image URL if the binary field has data, else None."""
                if not has_data:
                    return None
                return '/web/image/%s/%s/%s' % (model_name, rec_id, field_name)

            expediente_data = None
            if cuenta.partner_id:
                Expediente = request.env['adt.expediente'].sudo()
                expediente = Expediente.search(
                    [('cliente_id', '=', cuenta.partner_id.id)],
                    limit=1,
                    order='id desc',
                )
                if expediente:
                    eid = expediente.id
                    emod = 'adt.expediente'

                    expediente_data = {
                        'id': eid,
                        'name': expediente.display_name or '',
                        'state': expediente.state or '',
                        'cliente_id': {
                            'id': expediente.cliente_id.id,
                            'name': expediente.cliente_id.name or '',
                        } if expediente.cliente_id else None,
                        'asesora_id': {
                            'id': expediente.asesora_id.id,
                            'name': expediente.asesora_id.name or '',
                        } if expediente.asesora_id else None,
                        'fecha': expediente.fecha.isoformat() if expediente.fecha else None,
                        'vehiculo': expediente.vehiculo or '',
                        'placa': expediente.placa or '',
                        'chasis': expediente.chasis or '',

                        # ── Documento de identidad ────────────────────────────
                        'documento_identidad': {
                            'foto_dni_frente': _img_url(emod, eid, 'foto_dni_frente', expediente.foto_dni_frente),
                            'foto_dni_reverso': _img_url(emod, eid, 'foto_dni_reverso', expediente.foto_dni_reverso),
                            'estado_foto_dni': expediente.estado_foto_dni or None,
                            'obs_foto_dni': expediente.obs_foto_dni or None,
                            'foto_ce_frente': _img_url(emod, eid, 'foto_ce_frente', expediente.foto_ce_frente),
                            'foto_ce_reverso': _img_url(emod, eid, 'foto_ce_reverso', expediente.foto_ce_reverso),
                            'estado_foto_ce': expediente.estado_foto_ce or None,
                            'obs_foto_ce': expediente.obs_foto_ce or None,
                            'foto_pasaporte_frente': _img_url(emod, eid, 'foto_pasaporte_frente', expediente.foto_pasaporte_frente),
                            'foto_pasaporte_reverso': _img_url(emod, eid, 'foto_pasaporte_reverso', expediente.foto_pasaporte_reverso),
                            'estado_foto_pasaporte': expediente.estado_foto_pasaporte or None,
                            'obs_foto_pasaporte': expediente.obs_foto_pasaporte or None,
                        },

                        # ── Domicilio ─────────────────────────────────────────
                        'domicilio': {
                            'direccion_cliente': expediente.direccion_cliente or None,
                            'estado_direccion': expediente.estado_direccion or None,
                            'obs_direccion': expediente.obs_direccion or None,
                            'tipo_vivienda': expediente.tipo_vivienda or None,
                            'tiempo_viviendo': expediente.tiempo_viviendo or None,
                            'propietario_contacto': expediente.propietario_contacto or None,
                            'foto_vivienda': _img_url(emod, eid, 'foto_vivienda', expediente.foto_vivienda),
                            'estado_foto_vivienda': expediente.estado_foto_vivienda or None,
                            'obs_foto_vivienda': expediente.obs_foto_vivienda or None,
                            'foto_ubicacion_actual': _img_url(emod, eid, 'foto_ubicacion_actual', expediente.foto_ubicacion_actual),
                            'estado_foto_ubicacion': expediente.estado_foto_ubicacion or None,
                            'obs_foto_ubicacion': expediente.obs_foto_ubicacion or None,
                            'foto_fachada_domicilio': _img_url(emod, eid, 'foto_fachada_domicilio', expediente.foto_fachada_domicilio),
                            'estado_foto_fachada': expediente.estado_foto_fachada or None,
                            'obs_foto_fachada': expediente.obs_foto_fachada or None,
                            'foto_contrato_alquiler': _img_url(emod, eid, 'foto_contrato_alquiler', expediente.foto_contrato_alquiler),
                            'estado_foto_contrato': expediente.estado_foto_contrato or None,
                            'obs_foto_contrato': expediente.obs_foto_contrato or None,
                        },

                        # ── Ingresos ──────────────────────────────────────────
                        'ingresos': {
                            'foto_ingresos': _img_url(emod, eid, 'foto_ingresos', expediente.foto_ingresos),
                            'estado_foto_ingresos': expediente.estado_foto_ingresos or None,
                            'obs_foto_ingresos': expediente.obs_foto_ingresos or None,
                            'foto_recibo': _img_url(emod, eid, 'foto_recibo', expediente.foto_recibo),
                            'estado_foto_recibo': expediente.estado_foto_recibo or None,
                            'obs_foto_recibo': expediente.obs_foto_recibo or None,
                        },

                        # ── Licencia ──────────────────────────────────────────
                        'licencia': {
                            'foto_licencia': _img_url(emod, eid, 'foto_licencia', expediente.foto_licencia),
                            'estado_foto_licencia': expediente.estado_foto_licencia or None,
                            'obs_foto_licencia': expediente.obs_foto_licencia or None,
                        },

                        # ── Mototaxista ───────────────────────────────────────
                        'mototaxista': {
                            'foto_moto': _img_url(emod, eid, 'foto_moto', expediente.foto_moto),
                            'estado_foto_moto': expediente.estado_foto_moto or None,
                            'obs_foto_moto': expediente.obs_foto_moto or None,
                            'foto_soat': _img_url(emod, eid, 'foto_soat', expediente.foto_soat),
                            'estado_foto_soat': expediente.estado_foto_soat or None,
                            'obs_foto_soat': expediente.obs_foto_soat or None,
                            'foto_tarjeta_propiedad_frente': _img_url(emod, eid, 'foto_tarjeta_propiedad_frente', expediente.foto_tarjeta_propiedad_frente),
                            'foto_tarjeta_propiedad_reverso': _img_url(emod, eid, 'foto_tarjeta_propiedad_reverso', expediente.foto_tarjeta_propiedad_reverso),
                            'estado_foto_tarjeta': expediente.estado_foto_tarjeta or None,
                            'obs_foto_tarjeta': expediente.obs_foto_tarjeta or None,
                            'ganancia_diaria_mensual': expediente.ganancia_diaria_mensual or None,
                            'tiempo_trabajando': expediente.tiempo_trabajando or None,
                            'moto_empresa': expediente.moto_empresa or None,
                            'moto_propiedad': expediente.moto_propiedad or None,
                        },

                        # ── No mototaxista ────────────────────────────────────
                        'no_mototaxista': {
                            'foto_lugar_trabajo': _img_url(emod, eid, 'foto_lugar_trabajo', expediente.foto_lugar_trabajo),
                            'estado_foto_lugar_trabajo': expediente.estado_foto_lugar_trabajo or None,
                            'obs_foto_lugar_trabajo': expediente.obs_foto_lugar_trabajo or None,
                            'foto_lugar_negocio': _img_url(emod, eid, 'foto_lugar_negocio', expediente.foto_lugar_negocio),
                            'estado_foto_lugar_negocio': expediente.estado_foto_lugar_negocio or None,
                            'obs_foto_lugar_negocio': expediente.obs_foto_lugar_negocio or None,
                            'foto_boletas': _img_url(emod, eid, 'foto_boletas', expediente.foto_boletas),
                            'estado_foto_boletas': expediente.estado_foto_boletas or None,
                            'obs_foto_boletas': expediente.obs_foto_boletas or None,
                            'foto_estado_cuenta': _img_url(emod, eid, 'foto_estado_cuenta', expediente.foto_estado_cuenta),
                            'estado_foto_estado_cuenta': expediente.estado_foto_estado_cuenta or None,
                            'obs_foto_estado_cuenta': expediente.obs_foto_estado_cuenta or None,
                            'ganancia_diaria_mensual': expediente.ganancia_diaria_mensual_no or None,
                            'tiempo_trabajando': expediente.tiempo_trabajando_no or None,
                        },

                        # ── Sentinel ──────────────────────────────────────────
                        'sentinel': {
                            'foto_sentinel_1': _img_url(emod, eid, 'foto_sentinel_1', expediente.foto_sentinel_1),
                            'foto_sentinel_2': _img_url(emod, eid, 'foto_sentinel_2', expediente.foto_sentinel_2),
                            'estado_foto_sentinel': expediente.estado_foto_sentinel or None,
                            'obs_foto_sentinel': expediente.obs_foto_sentinel or None,
                        },

                        # ── Fase final ────────────────────────────────────────
                        'fase_final': {
                            'foto_entrega': _img_url(emod, eid, 'foto_entrega', expediente.foto_entrega),
                            'placa': expediente.placa or None,
                            'chasis': expediente.chasis or None,
                        },

                        # ── Referencias ───────────────────────────────────────
                        'referencias': {
                            'estado_referencias': expediente.estado_referencias or None,
                            'obs_referencias': expediente.obs_referencias or None,
                            'lista': [
                                {
                                    'nombre': expediente.ref_1_name or None,
                                    'telefono': expediente.ref_1_phone or None,
                                    'vinculo': expediente.ref_1_vinculo or None,
                                },
                                {
                                    'nombre': expediente.ref_2_name or None,
                                    'telefono': expediente.ref_2_phone or None,
                                    'vinculo': expediente.ref_2_vinculo or None,
                                },
                                {
                                    'nombre': expediente.ref_3_name or None,
                                    'telefono': expediente.ref_3_phone or None,
                                    'vinculo': expediente.ref_3_vinculo or None,
                                },
                                {
                                    'nombre': expediente.ref_4_name or None,
                                    'telefono': expediente.ref_4_phone or None,
                                    'vinculo': expediente.ref_4_vinculo or None,
                                },
                            ],
                        },
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

