# -*- coding: utf-8 -*-

import json
import logging
import threading
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class CapturaAPI(http.Controller):

    # ── Helper: captura summary (count + time since last) ────────────────────
    def _captura_summary(self, mora_rec, cap_dates_by_vehicle, cap_dates_by_cuenta):
        """
        Returns a dict with:
          - total_capturas      : int  – how many times the vehicle/account was captured
          - ultima_captura_hace : str  – human-readable time since the latest capture
                                        e.g. "5 días", "3 meses", "2 años"
                                        null if never captured
        """
        from datetime import date as date_cls

        seen = set()
        all_dates = []

        for dt in cap_dates_by_vehicle.get(mora_rec.vehicle_id.id if mora_rec.vehicle_id else 0, []):
            key = id(dt)
            if key not in seen:
                seen.add(key)
                all_dates.append(dt)

        for dt in cap_dates_by_cuenta.get(mora_rec.cuenta_id.id if mora_rec.cuenta_id else 0, []):
            key = id(dt)
            if key not in seen:
                seen.add(key)
                all_dates.append(dt)

        total = len(all_dates)

        if not all_dates:
            return {'total_capturas': 0, 'ultima_captura_hace': None}

        latest_dt = max(all_dates)
        latest_date = latest_dt.date() if hasattr(latest_dt, 'date') else latest_dt
        today = date_cls.today()
        delta_days = (today - latest_date).days

        if delta_days < 30:
            label = '%d %s' % (delta_days, 'día' if delta_days == 1 else 'días')
        elif delta_days < 365:
            months = delta_days // 30
            label = '%d %s' % (months, 'mes' if months == 1 else 'meses')
        else:
            years = delta_days // 365
            label = '%d %s' % (years, 'año' if years == 1 else 'años')

        return {'total_capturas': total, 'ultima_captura_hace': label}

    # ── Helper: días de mora desde la primera cuota retrasada ────────────────
    def _dias_desde_ultimo_pago(self, cuenta):
        """
        Returns the number of days in mora, calculated as:
            today  -  fecha_cronograma of the OLDEST overdue cuota

        Overdue cuotas are those with state in ('vencido', 'retrasado').
        Returns None if no overdue cuota exists.
        """
        from datetime import date as date_cls

        overdue = cuenta.cuota_ids.filtered(
            lambda c: c.type == 'cuota'
            and c.state in ('vencido', 'retrasado')
            and c.fecha_cronograma
        )
        if not overdue:
            return None

        # Oldest overdue cuota = the one with the earliest fecha_cronograma
        primera_fecha = min(overdue.mapped('fecha_cronograma'))

        return (date_cls.today() - primera_fecha).days

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

            # ── pre-fetch adt.captura.record counts & latest date ─────────────
            vehicle_ids = [r for r in records.mapped('vehicle_id').ids if r]
            all_cuenta_ids = [r for r in records.mapped('cuenta_id').ids if r]
            CapturaRecordModel = request.env['adt.captura.record'].sudo()

            # Build lookup dicts: key → list of create_date values
            cap_dates_by_vehicle = {}   # vehicle_id.id → [datetime, ...]
            cap_dates_by_cuenta  = {}   # cuenta_id.id  → [datetime, ...]

            if vehicle_ids or all_cuenta_ids:
                cap_domain = []
                if vehicle_ids and all_cuenta_ids:
                    cap_domain = ['|',
                                  ('vehicle_id', 'in', vehicle_ids),
                                  ('cuenta_id',  'in', all_cuenta_ids)]
                elif vehicle_ids:
                    cap_domain = [('vehicle_id', 'in', vehicle_ids)]
                else:
                    cap_domain = [('cuenta_id', 'in', all_cuenta_ids)]

                for cap in CapturaRecordModel.search(cap_domain):
                    dt = cap.create_date
                    if cap.vehicle_id:
                        cap_dates_by_vehicle.setdefault(cap.vehicle_id.id, []).append(dt)
                    if cap.cuenta_id:
                        cap_dates_by_cuenta.setdefault(cap.cuenta_id.id, []).append(dt)

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

                cap_summary = self._captura_summary(rec, cap_dates_by_vehicle, cap_dates_by_cuenta)
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
                    'total_capturas': cap_summary['total_capturas'],
                    'ultima_captura_hace': cap_summary['ultima_captura_hace'],
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
        auth='none',
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
                'dias_mora': self._dias_desde_ultimo_pago(cuenta),
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
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_expediente(self, **kwargs):
        """
        Returns expediente data for the partner linked to the given vehicle.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record

        Images are returned as absolute URLs:
            https://<host>/web/image/adt.expediente/<id>/<field>
        The app can load them directly (no base64 bloat).
        To display in React Native:  <Image source={{ uri: url }} />
        To display in Flutter:       Image.network(url)
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

            # Build absolute base URL once (e.g. "https://odoo.miempresa.com")
            base_url = request.httprequest.host_url.rstrip('/')

            def _img_url(rec_id, field_name, has_data):
                """Return an absolute public URL the app can fetch directly.
                Returns None when the field is empty so the app knows not to show it."""
                if not has_data:
                    return None
                return '%s/web/image/adt.expediente/%s/%s' % (base_url, rec_id, field_name)

            eid = expediente.id
            nat = getattr(expediente.cliente_id, 'nationality', False) or ''
            occ = getattr(expediente.cliente_id, 'occupation', False) or ''
            es_peruano = (nat.lower() in ('peruana', 'peru', 'pe'))
            es_mototaxista = (occ.lower() == 'mototaxista')

            expediente_data = {
                'es_peruano': es_peruano,
                'es_mototaxista': es_mototaxista,
                'documento_identidad': {
                    'foto_dni_frente': _img_url(eid, 'foto_dni_frente', expediente.foto_dni_frente),
                    'foto_dni_reverso': _img_url(eid, 'foto_dni_reverso', expediente.foto_dni_reverso),
                    'foto_ce_frente': _img_url(eid, 'foto_ce_frente', expediente.foto_ce_frente),
                    'foto_ce_reverso': _img_url(eid, 'foto_ce_reverso', expediente.foto_ce_reverso),
                    'foto_pasaporte_frente': _img_url(eid, 'foto_pasaporte_frente', expediente.foto_pasaporte_frente),
                    'foto_pasaporte_reverso': _img_url(eid, 'foto_pasaporte_reverso', expediente.foto_pasaporte_reverso),
                },
                'licencia': {
                    'foto_licencia': _img_url(eid, 'foto_licencia', expediente.foto_licencia),
                },
                'recibo_servicios': {
                    'foto_recibo': _img_url(eid, 'foto_recibo', expediente.foto_recibo),
                },
                'sentinel': {
                    'foto_sentinel_1': _img_url(eid, 'foto_sentinel_1', expediente.foto_sentinel_1),
                    'foto_sentinel_2': _img_url(eid, 'foto_sentinel_2', expediente.foto_sentinel_2),
                },
                'mototaxista': {
                    'foto_moto': _img_url(eid, 'foto_moto', expediente.foto_moto),
                    'foto_soat': _img_url(eid, 'foto_soat', expediente.foto_soat),
                    'foto_tarjeta_propiedad_frente': _img_url(eid, 'foto_tarjeta_propiedad_frente', expediente.foto_tarjeta_propiedad_frente),
                    'foto_tarjeta_propiedad_reverso': _img_url(eid, 'foto_tarjeta_propiedad_reverso', expediente.foto_tarjeta_propiedad_reverso),
                    'ganancia_diaria_mensual': expediente.ganancia_diaria_mensual or None,
                    'tiempo_trabajando': expediente.tiempo_trabajando or None,
                    'moto_empresa': expediente.moto_empresa or None,
                    'moto_propiedad': expediente.moto_propiedad or None,
                },
                'no_mototaxista': {
                    'foto_lugar_trabajo': _img_url(eid, 'foto_lugar_trabajo', expediente.foto_lugar_trabajo),
                    'foto_lugar_negocio': _img_url(eid, 'foto_lugar_negocio', expediente.foto_lugar_negocio),
                    'foto_boletas': _img_url(eid, 'foto_boletas', expediente.foto_boletas),
                    'foto_estado_cuenta': _img_url(eid, 'foto_estado_cuenta', expediente.foto_estado_cuenta),
                    'ganancia_diaria_mensual': expediente.ganancia_diaria_mensual_no or None,
                    'tiempo_trabajando': expediente.tiempo_trabajando_no or None,
                },
                'domicilio': {
                    'foto_ubicacion_actual': _img_url(eid, 'foto_ubicacion_actual', expediente.foto_ubicacion_actual),
                    'foto_fachada_domicilio': _img_url(eid, 'foto_fachada_domicilio', expediente.foto_fachada_domicilio),
                    'tipo_vivienda': expediente.tipo_vivienda or None,
                    'propietario_contacto': expediente.propietario_contacto or None,
                    'tiempo_viviendo': expediente.tiempo_viviendo or None,
                    'foto_contrato_alquiler': _img_url(eid, 'foto_contrato_alquiler', expediente.foto_contrato_alquiler),
                },
                'referencias': [
                    {'nombre': expediente.ref_1_name or None, 'telefono': expediente.ref_1_phone or None, 'vinculo': expediente.ref_1_vinculo or None},
                    {'nombre': expediente.ref_2_name or None, 'telefono': expediente.ref_2_phone or None, 'vinculo': expediente.ref_2_vinculo or None},
                    {'nombre': expediente.ref_3_name or None, 'telefono': expediente.ref_3_phone or None, 'vinculo': expediente.ref_3_vinculo or None},
                    {'nombre': expediente.ref_4_name or None, 'telefono': expediente.ref_4_phone or None, 'vinculo': expediente.ref_4_vinculo or None},
                ],
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

    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/adt/captura/record
    # Create a new adt.captura.record from a mobile/frontend form.
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/record',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def create_captura_record(self, **kwargs):
        """
        Plain REST endpoint. Send a flat JSON body – no jsonrpc wrapper needed:

            POST /api/adt/captura/record
            Content-Type: application/json

            {
                "tipo_captura": "inmediata",
                "moto_recogida": false,
                "motivo_no_recogida": "Cliente ausente",
                "vehiculo_id": 120,
                "registrado_por": 7
            }

        Odoo's JSON dispatcher always stores the parsed body in
        request.jsonrequest, regardless of whether the jsonrpc envelope is
        present. Reading from there makes both flat JSON and jsonrpc+params
        formats work transparently.
        """
        from odoo.exceptions import UserError

        def _err(msg, code=400):
            raise UserError('[%s] %s' % (code, msg))

        # request.jsonrequest is the full parsed body dict.
        # For a flat body  { "tipo_captura": ... }  it IS the payload.
        # For a jsonrpc body { "jsonrpc":..., "params": {...} }  Odoo already
        # unwraps params into kwargs, but we prefer the unified approach below.
        body = request.jsonrequest or {}

        # If the client sent a proper jsonrpc envelope, params are in body['params']
        # AND already in kwargs. Prefer kwargs when available (jsonrpc path),
        # otherwise fall back to reading directly from the flat body.
        def _get(key):
            if key in kwargs:
                return kwargs[key]
            return body.get(key)

        tipo_captura       = _get('tipo_captura')
        moto_recogida      = _get('moto_recogida')
        motivo_no_recogida = (_get('motivo_no_recogida') or '').strip()
        vehiculo_id_raw    = _get('vehiculo_id')
        registrado_por     = _get('registrado_por')

        # ── Validate tipo_captura ─────────────────────────────────────────────
        if not tipo_captura or tipo_captura not in ('inmediata', 'compromiso'):
            _err('tipo_captura debe ser "inmediata" o "compromiso".')

        # ── Validate vehiculo_id ──────────────────────────────────────────────
        if vehiculo_id_raw is None:
            _err('vehiculo_id es requerido.')
        try:
            vehiculo_id_int = int(vehiculo_id_raw)
        except (ValueError, TypeError):
            _err('vehiculo_id debe ser un entero.')

        vehicle = request.env['fleet.vehicle'].sudo().browse(vehiculo_id_int)
        if not vehicle.exists():
            _err('El vehículo con id %s no existe en el sistema.' % vehiculo_id_int, 404)

        # ── Validate registrado_por ───────────────────────────────────────────
        if registrado_por is None:
            _err('registrado_por es requerido.')
        try:
            registrado_por_int = int(registrado_por)
        except (ValueError, TypeError):
            _err('registrado_por debe ser un entero (ID de usuario).')

        user = request.env['res.users'].sudo().browse(registrado_por_int)
        if not user.exists():
            _err('El usuario con id %s no existe en el sistema.' % registrado_por_int, 404)

        # ── Validate moto_recogida / motivo_no_recogida ───────────────────────
        if moto_recogida is True or moto_recogida == 1:
            moto_recogida      = True
            motivo_no_recogida = False
        else:
            moto_recogida = False
            if not motivo_no_recogida:
                _err('motivo_no_recogida es requerido cuando moto_recogida es false.', 422)

        # ── Resolve partner / cuenta from vehicle ─────────────────────────────
        CuentaModel = request.env['adt.comercial.cuentas'].sudo()
        cuenta = CuentaModel.search([('vehiculo_id', '=', vehicle.id)], limit=1, order='id desc')

        if cuenta and cuenta.partner_id:
            partner_id = cuenta.partner_id.id
            cuenta_id  = cuenta.id
            cliente_id = partner_id
        elif vehicle.driver_id:
            partner_id = vehicle.driver_id.id
            cuenta_id  = None
            cliente_id = partner_id
        else:
            _err('No se pudo determinar el cliente para el vehículo id=%s.' % vehiculo_id_int, 422)

        if not cuenta_id:
            _err('No existe una cuenta comercial asociada al vehículo id=%s.' % vehiculo_id_int, 422)

        # ── Build vals & create ───────────────────────────────────────────────
        vals = {
            'capture_type'  : tipo_captura,
            'moto_recogida' : moto_recogida,
            'partner_id'    : partner_id,
            'cuenta_id'     : cuenta_id,
            'capturador_id' : registrado_por_int,
        }
        if motivo_no_recogida:
            vals['motivo_no_recogida'] = motivo_no_recogida

        captura = request.env['adt.captura.record'].sudo().create(vals)

        fecha_registro_str = None
        if captura.create_date:
            try:
                fecha_registro_str = captura.create_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            except Exception:
                fecha_registro_str = str(captura.create_date)

        return {
            'id'                : captura.id,
            'tipo_captura'      : captura.capture_type,
            'moto_recogida'     : captura.moto_recogida,
            'motivo_no_recogida': captura.motivo_no_recogida or None,
            'vehiculo_id'       : vehicle.id,
            'cliente_id'        : cliente_id,
            'registrado_por'    : registrado_por_int,
            'fecha_registro'    : fecha_registro_str,
            'evidencias_status' : 'pending',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/adt/captura/record/<int:captura_id>/evidencias
    # Upload evidence files (images / videos) asynchronously.
    # ─────────────────────────────────────────────────────────────────────────

    # Simple in-memory status registry (process-local).
    # For multi-worker setups, replace with a DB-backed status field.
    _evidencia_status = {}

    @http.route(
        '/api/adt/captura/record/<int:captura_id>/evidencias',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def upload_evidencias(self, captura_id, **kwargs):
        """
        Uploads evidence files (photos / videos) to an existing adt.captura.record.

        The endpoint returns immediately with status="processing" and processes
        the files in a background thread so the client is never blocked.

        Accepted MIME types:
            images : image/jpeg, image/png, image/webp
            videos : video/mp4, video/quicktime, video/x-msvideo

        Multipart fields:
            files[]  – one or more file upload parts

        Success – 202 Accepted:
        {
            "captura_id": <int>,
            "evidencias_status": "processing",
            "files_received": <int>
        }
        """
        ALLOWED_MIME = {
            'image/jpeg', 'image/png', 'image/webp',
            'video/mp4', 'video/quicktime', 'video/x-msvideo',
        }

        try:
            # Verify the capture record exists
            captura = request.env['adt.captura.record'].sudo().browse(captura_id)
            if not captura.exists():
                return Response(
                    json.dumps({'error': 'Registro de captura id=%s no encontrado' % captura_id, 'code': 404}),
                    status=404,
                    mimetype='application/json',
                )

            # Collect uploaded files
            files = request.httprequest.files.getlist('files[]') or request.httprequest.files.getlist('files')
            if not files:
                return Response(
                    json.dumps({'error': 'No se recibieron archivos. Use el campo multipart "files[]".', 'code': 400}),
                    status=400,
                    mimetype='application/json',
                )

            # Validate MIME types up front (fast check before spawning thread)
            invalid = [f.filename for f in files if f.content_type not in ALLOWED_MIME]
            if invalid:
                return Response(
                    json.dumps({
                        'error'            : 'Tipo de archivo no permitido: %s' % ', '.join(invalid),
                        'tipos_permitidos' : list(ALLOWED_MIME),
                        'code'             : 415,
                    }),
                    status=415,
                    mimetype='application/json',
                )

            # Read file bytes while in the request context (must happen before thread)
            files_data = []
            for f in files:
                files_data.append({
                    'filename'    : f.filename,
                    'mimetype'    : f.content_type,
                    'data'        : f.read(),
                })

            # Mark status as processing
            CapturaAPI._evidencia_status[captura_id] = 'processing'

            # ── Background thread: save attachments ───────────────────────────
            db      = request.env.cr.dbname
            uid     = request.env.uid or request.env.ref('base.user_admin').id
            context = dict(request.env.context)

            def _save_attachments(db, uid, context, captura_id, files_data):
                try:
                    import odoo
                    with odoo.api.Environment.manage():
                        with odoo.registry(db).cursor() as cr:
                            env = odoo.api.Environment(cr, uid, context)
                            captura = env['adt.captura.record'].browse(captura_id)
                            if not captura.exists():
                                _logger.warning('Background upload: captura id=%s not found', captura_id)
                                CapturaAPI._evidencia_status[captura_id] = 'failed'
                                return
                            import base64
                            attachment_ids = []
                            for f in files_data:
                                att = env['ir.attachment'].create({
                                    'name'      : f['filename'],
                                    'datas'     : base64.b64encode(f['data']).decode(),
                                    'mimetype'  : f['mimetype'],
                                    'res_model' : 'adt.captura.record',
                                    'res_id'    : captura_id,
                                })
                                attachment_ids.append(att.id)
                            # Link to evidencia_archivos (Many2many)
                            captura.write({
                                'evidencia_archivos': [(4, att_id) for att_id in attachment_ids],
                            })
                            cr.commit()
                    CapturaAPI._evidencia_status[captura_id] = 'completed'
                    _logger.info('Background upload completed for captura id=%s (%s files)', captura_id, len(files_data))
                except Exception:
                    CapturaAPI._evidencia_status[captura_id] = 'failed'
                    _logger.exception('Background upload failed for captura id=%s', captura_id)

            t = threading.Thread(
                target=_save_attachments,
                args=(db, uid, context, captura_id, files_data),
                daemon=True,
            )
            t.start()

            return Response(
                json.dumps({
                    'captura_id'       : captura_id,
                    'evidencias_status': 'processing',
                    'files_received'   : len(files_data),
                }, ensure_ascii=False),
                status=202,
                mimetype='application/json',
            )

        except Exception as e:
            _logger.exception('Error in POST /api/adt/captura/record/%s/evidencias: %s', captura_id, e)
            CapturaAPI._evidencia_status[captura_id] = 'failed'
            return Response(
                json.dumps({'error': str(e), 'code': 500}),
                status=500,
                mimetype='application/json',
            )

    # ─────────────────────────────────────────────────────────────────────────
    # GET /api/adt/captura/record/<int:captura_id>/evidencias/status
    # Poll the background upload status for a given captura.
    # ─────────────────────────────────────────────────────────────────────────

    @http.route(
        '/api/adt/captura/record/<int:captura_id>/evidencias/status',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def evidencias_status(self, captura_id, **kwargs):
        """
        Returns the current upload status for the given capture record.

        States:
            pending     – no upload started yet
            processing  – background thread is running
            completed   – all files saved successfully
            failed      – background thread raised an exception
        """
        status = CapturaAPI._evidencia_status.get(captura_id, 'pending')
        return Response(
            json.dumps({'captura_id': captura_id, 'evidencias_status': status}),
            status=200,
            mimetype='application/json',
        )
