# -*- coding: utf-8 -*-

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone
from odoo import SUPERUSER_ID, http
from odoo.http import content_disposition, request, Response

from . import captura_datos as datos

_logger = logging.getLogger(__name__)

# URL del documento del expediente: firmada y con vencimiento, para que la app la abra
# sin sesión de Odoo (ver _documento_expediente y descargar_documento_expediente).
DOC_URL_HORAS = 24
DOC_FIRMA_SCOPE = 'adt_captura.expediente_documento'
# El contenido manda, no la extensión (mismas firmas que adt.expediente).
DOC_FIRMAS_MIME = (
    (b'%PDF', 'application/pdf', '.pdf'),
    (b'PK\x03\x04', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'application/msword', '.doc'),
)
DOC_EXT_MIME = {ext: mime for _f, mime, ext in DOC_FIRMAS_MIME}
# Orden de GET /api/adt/captura/mora (parámetro order).
MORA_ORDENES = {
    # Lo que debe cada uno: cuotas vencidas + papeletas SAT pendientes; a igual monto, más días de mora.
    'monto': lambda r: (-((r.monto_vencido or 0.0) + (r.deuda_sat or 0.0)), -(r.dias_mora or 0), r.id),
    'dias': lambda r: (-(r.dias_mora or 0), r.fecha_cronograma or datetime.max.date(), r.id),
}
# Estado de la deuda (source_type de adt.captura.mora), en el orden en que la app los muestra.
MORA_ESTADOS_DEUDA = [
    ('mora', 'Cronograma'),
    ('papeleta', 'Papeleta SAT'),
    ('ambos', 'Cronograma y papeleta SAT'),
]
# Alias aceptados en source_type.
MORA_ESTADOS_ALIAS = {'cronograma': 'mora', 'cuotas': 'mora', 'sat': 'papeleta', 'papeleta_sat': 'papeleta'}


class CapturaAPI(http.Controller):

    @staticmethod
    def _mobile_detail_authorized():
        """Allow the existing web session or a validated mobile Bearer token."""
        authorization = request.httprequest.headers.get('Authorization', '').strip()
        if authorization:
            parts = authorization.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return False
            token = request.env['adt.mobile.token'].sudo().validate_token(parts[1], {
                'ip': request.httprequest.remote_addr,
                'endpoint': request.httprequest.path,
                'method': request.httprequest.method,
                'user_agent': request.httprequest.headers.get('User-Agent', ''),
            })
            return bool(token and token.user_id.active)
        return bool(request.session.uid and request.env['res.users'].sudo().browse(request.session.uid).active)


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

    def _get_tipo_financiera(self, cuenta):
        """Return financiera name using the current model schema with legacy fallback."""
        if not cuenta:
            return ''
        try:
            tipo_financiera_rel = getattr(cuenta, 'tipo_financiera_id', False)
            if tipo_financiera_rel and getattr(tipo_financiera_rel, 'name', False):
                return tipo_financiera_rel.name or ''
        except Exception:
            _logger.warning('Could not read tipo_financiera_id on cuenta %s', getattr(cuenta, 'id', None), exc_info=True)

        # Backward compatibility in case some DB still has a legacy plain field.
        try:
            return getattr(cuenta, 'tipo_financiera', '') or ''
        except Exception:
            return ''

    def _papeletas_sat_vehiculo(self, vehicle):
        return request.env['adt.papeleta.sat'].sudo().search(
            [('vehicle_id', '=', vehicle.id)], order='fecha_infraccion desc, id desc')

    # ── Expediente como un solo documento ────────────────────────────────────
    # Desde ahora el expediente se sube en un solo archivo PDF o Word
    # (archivo_consolidado). Los expedientes anteriores, cargados como fotos
    # sueltas, se entregan como un PDF generado con el reporte del expediente.
    # En ambos casos la app recibe lo mismo: una URL al documento.

    @staticmethod
    def _firma_documento(expediente_id, expira):
        secreto = request.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        mensaje = '%s:%s:%s' % (DOC_FIRMA_SCOPE, expediente_id, expira)
        return hmac.new(secreto.encode(), mensaje.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _fotos_expediente(expediente):
        """Campos de foto del expediente que tienen archivo (fotos sueltas, formato anterior)."""
        exp = expediente.with_context(bin_size=True)
        return [name for name, f in exp._fields.items()
                if f.type == 'binary' and name.startswith('foto_') and exp[name]]

    def _documento_expediente(self, expediente):
        """
        Documento único del expediente para la app, o None si no tiene nada cargado:
            {url, nombre, mimetype, origen: 'archivo' | 'generado', estado, observaciones, expira}
        """
        exp = expediente.with_context(bin_size=True)
        tiene_archivo = bool(exp.archivo_consolidado) if 'archivo_consolidado' in exp._fields else False
        if not tiene_archivo and not self._fotos_expediente(expediente):
            return None
        expira = int(time.time()) + DOC_URL_HORAS * 3600
        url = '%s/api/adt/expediente/%s/documento?expira=%s&firma=%s' % (
            request.httprequest.host_url.rstrip('/'), expediente.id, expira,
            self._firma_documento(expediente.id, expira))
        if tiene_archivo:
            nombre = exp.archivo_consolidado_nombre or 'Expediente_%s.pdf' % expediente.id
            ext = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
            documento = {
                'origen': 'archivo',
                'nombre': nombre,
                'mimetype': DOC_EXT_MIME.get(ext, 'application/octet-stream'),
                'estado': exp.estado_archivo_consolidado or None,
                'observaciones': exp.obs_archivo_consolidado or None,
            }
        else:
            documento = {
                'origen': 'generado',
                'nombre': self._nombre_pdf_expediente(expediente),
                'mimetype': 'application/pdf',
                'estado': None,
                'observaciones': None,
            }
        documento.update(url=url, expira=datetime.fromtimestamp(expira, timezone.utc).isoformat())
        return documento

    @staticmethod
    def _nombre_pdf_expediente(expediente):
        cliente = (expediente.cliente_id.name or 'cliente').strip().replace(' ', '_')
        return 'Expediente_%s_%s.pdf' % (expediente.id, cliente)

    def _contenido_documento(self, expediente):
        """(bytes, nombre, mimetype) del documento del expediente, o None."""
        exp = expediente.with_context(bin_size=False)
        datos = exp.archivo_consolidado if 'archivo_consolidado' in exp._fields else False
        if datos:
            contenido = base64.b64decode(datos)
            mime, ext = next(((m, e) for firma, m, e in DOC_FIRMAS_MIME if contenido.startswith(firma)),
                             ('application/octet-stream', ''))
            return contenido, exp.archivo_consolidado_nombre or 'Expediente_%s%s' % (expediente.id, ext), mime
        if not self._fotos_expediente(expediente):
            return None
        reporte = request.env.ref('adt_expedientes.action_report_adt_expediente_pdf', raise_if_not_found=False)
        if not reporte:
            return None
        pdf, _tipo = reporte.with_user(SUPERUSER_ID).sudo()._render_qweb_pdf([expediente.id])
        return pdf, self._nombre_pdf_expediente(expediente), 'application/pdf'

    def _expediente_data(self, expediente):
        """Expediente para la app: datos básicos, el documento (una URL) y las referencias."""
        referencias = []
        for i in range(1, 5):
            nombre = getattr(expediente, 'ref_%s_name' % i, False)
            telefono = getattr(expediente, 'ref_%s_phone' % i, False)
            if nombre or telefono:
                referencias.append({
                    'nombre': nombre or None,
                    'telefono': telefono or None,
                    'vinculo': getattr(expediente, 'ref_%s_vinculo' % i, False) or None,
                })
        return {
            'id': expediente.id,
            'name': expediente.display_name or '',
            'state': expediente.state or '',
            'fecha': expediente.fecha.isoformat() if expediente.fecha else None,
            'cliente': {
                'id': expediente.cliente_id.id,
                'name': expediente.cliente_id.name or '',
                'vat': expediente.cliente_id.vat or '',
            } if expediente.cliente_id else None,
            'asesora': {
                'id': expediente.asesora_id.id,
                'name': expediente.asesora_id.name or '',
            } if expediente.asesora_id else None,
            'documento': self._documento_expediente(expediente),
            'referencias': referencias,
        }

    @http.route(
        '/api/adt/expediente/<int:expediente_id>/documento',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def descargar_documento_expediente(self, expediente_id, expira=None, firma=None, descargar=None, **kwargs):
        """
        Documento del expediente (PDF o Word). La URL la arma la API (campo documento.url):
        va firmada y vence a las DOC_URL_HORAS horas.

        Query params:
            - expira    : timestamp de vencimiento (lo pone la API)
            - firma     : firma de la URL (la pone la API)
            - descargar : 1 para forzar la descarga; sin él, el PDF se abre en el visor
        """
        def _error(msg, status):
            return Response(json.dumps({'error': msg, 'code': status}, ensure_ascii=False),
                            status=status, mimetype='application/json')

        try:
            expira_int = int(expira)
        except (TypeError, ValueError):
            return _error('Enlace inválido.', 403)
        if not firma or not hmac.compare_digest(str(firma), self._firma_documento(expediente_id, expira_int)):
            return _error('Enlace inválido.', 403)
        if expira_int < time.time():
            return _error('El enlace venció. Vuelve a consultar el expediente para obtener uno nuevo.', 410)
        try:
            expediente = request.env['adt.expediente'].sudo().browse(expediente_id)
            if not expediente.exists():
                return _error('Expediente no encontrado.', 404)
            contenido = self._contenido_documento(expediente)
            if not contenido:
                return _error('El expediente no tiene documentos cargados.', 404)
            datos, nombre, mime = contenido
            disposicion = content_disposition(nombre)
            if descargar not in ('1', 'true', 'True'):
                disposicion = disposicion.replace('attachment', 'inline', 1)
            return request.make_response(datos, headers=[
                ('Content-Type', mime),
                ('Content-Length', str(len(datos))),
                ('Content-Disposition', disposicion),
                ('Cache-Control', 'private, max-age=300'),
            ])
        except Exception as e:
            _logger.exception('Error in /api/adt/expediente/%s/documento: %s', expediente_id, e)
            return _error('No se pudo obtener el documento.', 500)

    @http.route(
        '/api/adt/adjunto/<int:attachment_id>',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def descargar_adjunto(self, attachment_id, expira=None, firma=None, descargar=None, **kwargs):
        """
        Archivo de una papeleta SAT o de una captura (copias SAT, evidencias, voucher...).
        La URL la arma la API (campo url de cada archivo): va firmada y vence a las
        ADJUNTO_URL_HORAS horas. descargar=1 fuerza la descarga.
        """
        def _error(msg, status):
            return Response(json.dumps({'error': msg, 'code': status}, ensure_ascii=False),
                            status=status, mimetype='application/json')

        try:
            expira_int = int(expira)
        except (TypeError, ValueError):
            return _error('Enlace inválido.', 403)
        if not firma or not hmac.compare_digest(
                str(firma), datos.firma_adjunto(request.env, attachment_id, expira_int)):
            return _error('Enlace inválido.', 403)
        if expira_int < time.time():
            return _error('El enlace venció. Vuelve a consultar para obtener uno nuevo.', 410)
        try:
            att = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
            if not att or not datos.adjunto_permitido(att):
                return _error('Archivo no encontrado.', 404)
            contenido = att.raw or b''
            disposicion = content_disposition(att.name or 'archivo')
            if descargar not in ('1', 'true', 'True'):
                disposicion = disposicion.replace('attachment', 'inline', 1)
            return request.make_response(contenido, headers=[
                ('Content-Type', att.mimetype or 'application/octet-stream'),
                ('Content-Length', str(len(contenido))),
                ('Content-Disposition', disposicion),
                ('Cache-Control', 'private, max-age=300'),
            ])
        except Exception as e:
            _logger.exception('Error in /api/adt/adjunto/%s: %s', attachment_id, e)
            return _error('No se pudo obtener el archivo.', 500)

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

        Aplica el filtro de Ajustes > Capturas (vista adt.captura.mora): las cuotas vencidas
        del cronograma cuentan solo si superan los días de mora y la cantidad de cuotas
        configurados; las papeletas SAT pendientes cuentan siempre.

        Optional query params:
            - source_type     : estado de la deuda: 'mora' (solo cronograma) | 'papeleta' (solo
                                papeleta SAT) | 'ambos'. Acepta varios separados por coma
                                (p. ej. 'mora,ambos' = todo lo que tiene cuotas vencidas) y los
                                alias 'cronograma' y 'sat'.
            - captura_prioridad: filter by 'normal' | 'urgente'
            - captura_existente: filter by '1' (true) | '0' (false)
            - order           : 'monto' (default) = lo que debe cada uno (monto_vencido + deuda_sat),
                                de mayor a menor | 'dias' = días de mora, de mayor a menor
            - limit           : max records to return (default 100)
            - offset          : pagination offset (default 0)

        Response body:
        {
            "count": <int>,
            "filtro_captura": {"dias_mora_mayor_a": <int>, "cuotas_vencidas_mayor_a": <int>},
            "estados_deuda": [            # cantidad por estado de la deuda, con los demás filtros
                {"key": "todos" | "mora" | "papeleta" | "ambos", "label": <str>, "count": <int>}, ...
            ],
            "records": [
                {
                    "client": {"id", "name", "documento", "tipo_documento", "telefono", "celular",
                               "email", "direccion"},
                    "papeletas": [ ...papeletas SAT pendientes con estado e imagenes (URL firmada)... ],
                    "vehicle_id": {
                        "id": <int>,
                        "display_name": <str>,
                        "license_plate": <str>
                    },
                    "source_type": <str>,
                    "papeleta_id": {"id": <int>, "name": <str>, "monto": <float>} | null,  # papeleta SAT más antigua
                    "papeletas_sat": <int>,
                    "deuda_sat": <float>,
                    "dias_mora": <int>,
                    "numero_cuotas_vencidas": <int>,
                    "monto_vencido": <float>,
                    "deuda_total": <float>,      # monto_vencido + deuda_sat (criterio del orden)
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

            captura_prioridad = kwargs.get('captura_prioridad')
            if captura_prioridad:
                domain.append(('cuenta_id.captura_prioridad', '=', captura_prioridad))

            captura_existente = kwargs.get('captura_existente')
            if captura_existente is not None and captura_existente != '':
                if captura_existente in ('all', 'todos'):
                    pass  # sin filtro: devuelve todos
                else:
                    domain.append(('captura_existente', '=', captura_existente in ('1', 'true', 'True')))
            else:
                # Por defecto excluir cuentas que ya tienen una captura activa
                domain.append(('captura_existente', '=', False))

            # Cantidad por estado de la deuda, con los demás filtros (antes de filtrar por estado).
            MoraModel = request.env['adt.captura.mora'].sudo()
            por_estado = {g['source_type']: g['source_type_count']
                          for g in MoraModel.read_group(domain, ['source_type'], ['source_type'])}
            estados_deuda = [{'key': 'todos', 'label': 'Todos', 'count': sum(por_estado.values())}]
            estados_deuda += [{'key': k, 'label': label, 'count': por_estado.get(k, 0)}
                              for k, label in MORA_ESTADOS_DEUDA]

            source_type = [MORA_ESTADOS_ALIAS.get(x.strip().lower(), x.strip().lower())
                           for x in (kwargs.get('source_type') or '').split(',') if x.strip()]
            if source_type and 'todos' not in source_type:
                domain.append(('source_type', 'in', source_type))

            # ── query ─────────────────────────────────────────────────────────
            # El orden por monto suma dos columnas: se ordena en Python antes de paginar
            # (adt.captura.mora es una vista SQL, una fila por cuenta).
            orden = MORA_ORDENES.get((kwargs.get('order') or 'monto').lower(), MORA_ORDENES['monto'])
            todos = MoraModel.search(domain).sorted(orden)
            total_count = len(todos)
            records = todos[offset:offset + limit]

            # ── batch SQL aggregation for cuota fields ────────────────────────
            # A single query replaces N per-cuenta ORM calls.
            # _compute_qty_cuotas uses bare `self.state` (no for-loop) so it
            # crashes on multi-record sets; raw SQL avoids that entirely.
            cuenta_ids = records.mapped('cuenta_id').ids  # plain list of ints
            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta_computed = {}
            if cuenta_ids:
                try:
                    request.env.cr.execute("""
                        SELECT
                            cuenta_id,
                            COUNT(*) FILTER (WHERE type = 'cuota' AND state = 'pagado')
                                AS qty_pagadas,
                            COUNT(*) FILTER (WHERE type = 'cuota' AND state IN ('pendiente','retrasado','a_cuenta'))
                                AS qty_restantes,
                            COUNT(*) FILTER (WHERE type = 'cuota' AND state = 'retrasado')
                                AS qty_retrasado,
                            COALESCE(SUM(CASE WHEN type = 'cuota' AND state IN ('pendiente','retrasado','a_cuenta')
                                THEN saldo ELSE 0 END), 0) AS cuotas_saldo,
                            COALESCE(SUM(CASE WHEN type = 'cuota'
                                THEN COALESCE(mora_pendiente, 0) ELSE 0 END), 0) AS mora_total
                        FROM adt_comercial_cuotas
                        WHERE cuenta_id = ANY(%s)
                        GROUP BY cuenta_id
                    """, (cuenta_ids,))
                    for row in request.env.cr.dictfetchall():
                        cuenta_computed[row['cuenta_id']] = {
                            'qty_cuotas_pagadas': row['qty_pagadas'] or 0,
                            'qty_cuotas_restantes': row['qty_restantes'] or 0,
                            'qty_cuotas_retrasado': row['qty_retrasado'] or 0,
                            'cuotas_saldo': float(row['cuotas_saldo'] or 0),
                            'mora_total': float(row['mora_total'] or 0),
                        }
                except Exception:
                    _logger.warning('Batch cuota SQL failed, falling back', exc_info=True)

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

                for cap in CapturaRecordModel.search_read(
                    cap_domain, ['vehicle_id', 'cuenta_id', 'create_date']
                ):
                    dt = cap['create_date']
                    if cap.get('vehicle_id'):
                        cap_dates_by_vehicle.setdefault(cap['vehicle_id'][0], []).append(dt)
                    if cap.get('cuenta_id'):
                        cap_dates_by_cuenta.setdefault(cap['cuenta_id'][0], []).append(dt)

            # Papeletas SAT pendientes de cada cuenta, con sus copias: dos consultas para toda la página.
            host = request.httprequest.host_url
            papeletas_por_cuenta = datos.papeletas_sat_pendientes_por_cuenta(request.env, records.mapped('cuenta_id'))
            todas_papeletas = request.env['adt.papeleta.sat'].sudo()
            for pps in papeletas_por_cuenta.values():
                todas_papeletas |= pps
            copias = datos.adjuntos_por_registro(request.env, 'adt.papeleta.sat', todas_papeletas.ids)

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

                # papeleta SAT pendiente más antigua
                papeleta_data = None
                if rec.papeleta_sat_id:
                    papeleta_data = {
                        'id': rec.papeleta_sat_id.id,
                        'name': rec.papeleta_sat_id.name or '',
                        'monto': rec.papeleta_sat_id.deuda or 0.0,
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
                        'tipo_financiera': self._get_tipo_financiera(c),
                        'periodicidad': c.periodicidad or '',
                        'monto_total': c.monto_total or 0.0,
                        'monto_cuota': c.monto_cuota or 0.0,
                        'qty_cuotas': c.qty_cuotas or 0,
                        'qty_cuotas_pagadas': cc.get('qty_cuotas_pagadas', 0),
                        'qty_cuotas_restantes': cc.get('qty_cuotas_restantes', 0),
                        'qty_cuotas_retrasado': cc.get('qty_cuotas_retrasado', 0),
                        'cuotas_saldo': cc.get('cuotas_saldo', 0.0),
                        'mora_total': cc.get('mora_total', 0.0),
                        'fecha_desembolso': c.fecha_desembolso.isoformat() if c.fecha_desembolso else None,
                    }

                cap_summary = self._captura_summary(rec, cap_dates_by_vehicle, cap_dates_by_cuenta)
                papeletas = papeletas_por_cuenta.get(rec.cuenta_id.id) or []
                result.append({
                    'client': datos.contacto_resumen(rec.partner_id),
                    'cuenta_id': cuenta_data,
                    'vehicle_id': vehicle_data,
                    'source_type': rec.source_type or 'none',
                    'estado_deuda': dict(MORA_ESTADOS_DEUDA).get(rec.source_type, ''),
                    'papeleta_id': papeleta_data,
                    'papeletas': [datos.papeleta_sat_data(p, host, copias.get(p.id)) for p in papeletas],
                    'papeletas_sat': rec.papeletas_sat or 0,
                    'deuda_sat': rec.deuda_sat or 0.0,
                    'dias_mora': rec.dias_mora or 0,
                    'numero_cuotas_vencidas': rec.numero_cuotas_vencidas or 0,
                    'monto_vencido': rec.monto_vencido or 0.0,
                    'deuda_total': round((rec.monto_vencido or 0.0) + (rec.deuda_sat or 0.0), 2),
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
                'filtro_captura': MoraModel._filtro_captura(),
                'estados_deuda': estados_deuda,
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
            mora_total_cuenta = 0.0
            monto_total_vencido = 0.0
            for cuota in cuenta.cuota_ids.filtered(lambda c: c.type == 'cuota').sorted('id'):
                cuota_mora_pendiente = self._safe_get(cuota, 'mora_pendiente', 0.0) or 0.0
                cuota_saldo = self._safe_get(cuota, 'saldo', 0.0) or 0.0
                mora_total_cuenta += cuota_mora_pendiente
                if cuota.state == 'retrasado':
                    monto_total_vencido += cuota_saldo
                cuotas_data.append({
                    'id': cuota.id,
                    'name': cuota.name or '',
                    'fecha_vencimiento': cuota.fecha_cronograma.isoformat() if cuota.fecha_cronograma else None,
                    'fecha_pago': cuota.real_date or None,
                    'monto_cuota': cuota.monto or 0.0,
                    'monto_pagado': (cuota.monto or 0.0) - cuota_saldo,
                    'monto_pendiente': cuota_saldo,
                    'payment_state': cuota.state or '',
                    'mora': cuota_mora_pendiente,
                    'dias_mora': self._safe_get(cuota, 'mora_dias', 0) or 0,
                    'monto_mora': self._safe_get(cuota, 'mora_total', 0.0) or 0.0,
                    'numero_operacion': cuota.numero_operacion or None,
                })

            cuenta_data = {
                'id': cuenta.id,
                'reference_no': cuenta.reference_no or '',
                'state': cuenta.state or '',
                'tipo_financiera': self._get_tipo_financiera(cuenta),
                'periodicidad': cuenta.periodicidad or '',
                'monto_total': cuenta.monto_total or 0.0,
                'monto_cuota': cuenta.monto_cuota or 0.0,
                'qty_cuotas': cuenta.qty_cuotas or 0,
                'qty_cuotas_pagadas': self._safe_get(cuenta, 'qty_cuotas_pagadas', 0) or 0,
                'qty_cuotas_restantes': self._safe_get(cuenta, 'qty_cuotas_restantes', 0) or 0,
                'qty_cuotas_retrasado': self._safe_get(cuenta, 'qty_cuotas_retrasado', 0) or 0,
                'cuotas_saldo': self._safe_get(cuenta, 'cuotas_saldo', 0.0) or 0.0,
                'monto_total_vencido': monto_total_vencido,
                'mora_total': mora_total_cuenta,
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
        Returns the expediente of the client linked to the given vehicle, with the whole
        expediente as ONE document URL (PDF or Word) instead of one URL per photo.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record

        record.documento:
            - origen 'archivo'  : the PDF/Word uploaded as the whole expediente
            - origen 'generado' : older expedientes (loose photos) → PDF built from them
            - null              : nothing uploaded yet
        The URL is signed and expires after DOC_URL_HORAS hours; ask again for a new one.
        """
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            # Find partner via cuenta or driver
            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta = CuentaModel.search([('vehiculo_id', '=', vehicle.id)], limit=1, order='id desc')
            partner = cuenta.partner_id if cuenta and cuenta.partner_id else (vehicle.driver_id or None)

            expediente = None
            if partner:
                expediente = request.env['adt.expediente'].sudo().search(
                    [('cliente_id', '=', partner.id)], limit=1, order='id desc')
            if not expediente:
                return Response(
                    json.dumps({'count': 0, 'record': None}),
                    status=200,
                    mimetype='application/json',
                )

            return Response(
                json.dumps({'count': 1, 'record': self._expediente_data(expediente)}, ensure_ascii=False, default=str),
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
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def get_detail_papeletas(self, **kwargs):
        """
        Returns all SAT Lima papeletas (adt.papeleta.sat) of the given vehicle.

        Query param:
            - vehicle_id : ID of the fleet.vehicle record
        """
        if not self._mobile_detail_authorized():
            return Response(json.dumps({'error': 'Tu sesión ha expirado. Inicia sesión nuevamente.'}),
                            status=401, mimetype='application/json')
        try:
            vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
            if err:
                return err

            papeletas_data = datos.papeletas_sat_lista(
                request.env, self._papeletas_sat_vehiculo(vehicle), request.httprequest.host_url)

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
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def get_captura_mora_detail(self, **kwargs):
        """
        Returns full detail for a single cuenta record.

        Query param (one of them):
            - cuenta_id  : ID of the adt.comercial.cuentas record
            - vehicle_id : ID of the fleet.vehicle (its latest cuenta)

        Response body:
        {
            "count": 1,
            "record": {
                "deuda": {"estado", "estado_label", "cronograma": {...}, "papeletas_sat": {...}, "total"},
                "contacto": { ...datos personales, domicilio, referencias, otras cuentas... },
                "gps": { ...estado del GPS (Traccar)... },
                "refinanciamientos": {"total", "registros": [...], "capturas_liberadas_por_refinanciamiento": [...]},
                "capturas": [ ...cada captura con sus pasos, archivos e historial... ],
                "cuenta_id": { ...full cuenta detail + cuotas list... },
                "expediente_id": { ...expediente del cliente... } | null,
                "papeletas": [ ...all SAT papeletas for the vehicle, con imagenes... ],
                "vehicle_id": { ...fleet.vehicle detail... } | null,
                "mantenimientos": [ ...adt.tvs.mantenimiento records for vehicle... ]
            }
        }
        Fechas con hora en ISO con zona (UTC). Las URLs de archivos vencen a las 24 horas.
        """
        if not self._mobile_detail_authorized():
            return Response(json.dumps({'error': 'Tu sesión ha expirado. Inicia sesión nuevamente.'}),
                            status=401, mimetype='application/json')
        try:
            CuentaModel = request.env['adt.comercial.cuentas'].sudo()
            cuenta_id_raw = kwargs.get('cuenta_id')
            if not cuenta_id_raw and kwargs.get('vehicle_id'):
                vehicle, err = self._resolve_vehicle(kwargs.get('vehicle_id'))
                if err:
                    return err
                cuenta_id_raw = CuentaModel.search([('vehiculo_id', '=', vehicle.id)], limit=1, order='id desc').id
                if not cuenta_id_raw:
                    return Response(
                        json.dumps({'error': 'No cuenta found for this vehicle'}),
                        status=404,
                        mimetype='application/json',
                    )
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
                'tipo_financiera': self._get_tipo_financiera(cuenta),
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

            # ── expediente: linked through partner_id (un solo documento, ver _expediente_data) ──
            host = request.httprequest.host_url
            expediente_data = None
            expediente = request.env['adt.expediente'].sudo()
            if cuenta.partner_id:
                expediente = expediente.search(
                    [('cliente_id', '=', cuenta.partner_id.id)], limit=1, order='id desc')
                if expediente:
                    expediente_data = self._expediente_data(expediente)

            # ── papeletas SAT: all for this vehicle ───────────────────────────
            papeletas_data = []
            if cuenta.vehiculo_id:
                papeletas_data = datos.papeletas_sat_lista(
                    request.env, self._papeletas_sat_vehiculo(cuenta.vehiculo_id), host)

            # ── deuda: lo que la pone en la lista de capturas ─────────────────
            mora = request.env['adt.captura.mora'].sudo().search([('cuenta_id', '=', cuenta.id)], limit=1)
            pendientes = datos.papeletas_sat_pendientes_por_cuenta(request.env, cuenta).get(cuenta.id) or []
            monto_vencido = mora.monto_vencido or 0.0
            deuda_sat = sum(p.deuda or 0.0 for p in pendientes)
            deuda_data = {
                'estado': mora.source_type or 'none',
                'estado_label': dict(MORA_ESTADOS_DEUDA).get(mora.source_type, 'Sin deuda vencida'),
                'en_lista_de_capturas': bool(mora),
                'cronograma': {
                    'monto_vencido': monto_vencido,
                    'cuotas_vencidas': mora.numero_cuotas_vencidas or 0,
                    'dias_mora': mora.dias_mora or 0,
                    'cuota_mas_antigua': datos.fecha(mora.fecha_cronograma),
                },
                'papeletas_sat': {
                    'cantidad': len(pendientes),
                    'deuda': deuda_sat,
                    'mas_antigua': datos.fecha(min((p.fecha_infraccion for p in pendientes if p.fecha_infraccion), default=None)),
                    'ids': [p.id for p in pendientes],
                },
                'total': round(monto_vencido + deuda_sat, 2),
                'captura_prioridad': datos.etiqueta(cuenta, 'captura_prioridad'),
            }

            # ── contacto, GPS, capturas y refinanciamientos ───────────────────
            cuentas_cliente = CuentaModel.search(
                [('partner_id', '=', cuenta.partner_id.id)], order='id desc') if cuenta.partner_id else CuentaModel
            cuentas_vehiculo = CuentaModel.search(
                [('vehiculo_id', '=', cuenta.vehiculo_id.id)], order='id') if cuenta.vehiculo_id else cuenta
            Captura = request.env['adt.captura.record'].sudo()
            capturas = Captura.search(
                ['|', ('cuenta_id', '=', cuenta.id), ('vehicle_id', '=', cuenta.vehiculo_id.id)]
                if cuenta.vehiculo_id else [('cuenta_id', '=', cuenta.id)], order='create_date desc, id desc')
            contacto_data = datos.contacto_detalle(cuenta.partner_id, host, expediente, cuentas_cliente)
            gps_data = datos.gps_data(cuenta.vehiculo_id)
            refinanciamientos_data = datos.refinanciamientos_data(cuentas_vehiculo | cuenta, capturas)
            capturas_data = datos.capturas_lista(capturas, host)

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
                    'deuda': deuda_data,
                    'contacto': contacto_data,
                    'gps': gps_data,
                    'refinanciamientos': refinanciamientos_data,
                    'capturas': capturas_data,
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
                "registrado_por": 7,
                "fecha_compromiso": "2026-11-05",      # obligatorio si tipo_captura = "compromiso"
                "comentarios_captura": "..."           # opcional
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

        tipo_captura          = _get('tipo_captura')
        moto_recogida         = _get('moto_recogida')
        motivo_no_recogida    = (_get('motivo_no_recogida') or '').strip()
        vehiculo_id_raw       = _get('vehiculo_id')
        registrado_por        = _get('registrado_por')
        comentarios_captura   = (_get('comentarios_captura') or '').strip() or False
        fecha_compromiso_raw  = (_get('fecha_compromiso') or '').strip()

        # ── Validate tipo_captura ─────────────────────────────────────────────
        if not tipo_captura or tipo_captura not in ('inmediata', 'compromiso'):
            _err('tipo_captura debe ser "inmediata" o "compromiso".')

        # ── Validate fecha_compromiso (el modelo la exige para un compromiso de pago) ──
        fecha_compromiso = False
        if tipo_captura == 'compromiso':
            if not fecha_compromiso_raw:
                _err('fecha_compromiso es requerida cuando tipo_captura es "compromiso" (formato YYYY-MM-DD).', 422)
            try:
                fecha_compromiso = datetime.strptime(fecha_compromiso_raw, '%Y-%m-%d').date()
            except ValueError:
                _err('fecha_compromiso debe tener el formato YYYY-MM-DD.')
            if fecha_compromiso <= datetime.now().date():
                _err('fecha_compromiso debe ser una fecha futura.', 422)

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
        if comentarios_captura:
            vals['comentarios_captura'] = comentarios_captura
        if fecha_compromiso:
            vals['commitment_date'] = fecha_compromiso

        captura = request.env['adt.captura.record'].sudo().create(vals)
        request.env.cr.commit()

        self._notify_captura_fcm(
            db=request.env.cr.dbname,
            uid=request.env.uid or request.env.ref('base.user_admin').id,
            context=dict(request.env.context),
            captura_id=captura.id,
        )

        return {'id': captura.id}

    # ── Helper: push FCM notification al crear una captura ────────────────────
    def _notify_captura_fcm(self, db, uid, context, captura_id):
        """
        Envía la notificación push (FCM) al cliente dueño del vehículo capturado.

        Se ejecuta en un hilo aparte con su propio cursor (mismo patrón que
        _save_attachments más abajo) para no bloquear ni arriesgar la respuesta
        del endpoint si el servicio de notificaciones está caído o es lento.
        Reutiliza el servicio ya existente en adt_comercial
        (adt.comercial.cuentas._enviar_notificacion), el mismo que usa el cron
        de notificaciones de cuotas, y además registra el mensaje en
        mobile.notification para que aparezca en el feed de la app.
        """
        def _run(db, uid, context, captura_id):
            try:
                import odoo
                with odoo.api.Environment.manage():
                    with odoo.registry(db).cursor() as cr:
                        env = odoo.api.Environment(cr, uid, context)
                        captura = env['adt.captura.record'].browse(captura_id)
                        if not captura.exists() or not captura.partner_id:
                            return

                        capture_label = dict(
                            captura._fields['capture_type'].selection
                        ).get(captura.capture_type, captura.capture_type)
                        plate = captura.vehicle_id.license_plate or ''

                        title = 'Captura de vehículo registrada'
                        body = 'Se registró una captura (%s) para el vehículo %s.' % (
                            capture_label, plate or 'sin placa',
                        )
                        payload = {
                            'title': title,
                            'body': body,
                            'data': {
                                'partner_id': captura.partner_id.id,
                                'tipo': 'CAPTURA',
                                'referencia': captura.name,
                                'captura_id': captura.id,
                            },
                        }

                        env['mobile.notification'].sudo().create({
                            'title': title,
                            'body': body,
                            'notification_type': 'SYSTEM',
                            'link_type': 'NONE',
                            'partner_id': captura.partner_id.id,
                            'vehicle_id': captura.vehicle_id.id if captura.vehicle_id else False,
                            'is_read': False,
                            'active': True,
                            'created_at': odoo.fields.Datetime.now(),
                        })

                        env['adt.comercial.cuentas']._enviar_notificacion(payload)
                        cr.commit()
            except Exception:
                _logger.exception('Error enviando notificación FCM para captura id=%s', captura_id)

        t = threading.Thread(
            target=_run,
            args=(db, uid, context, captura_id),
            daemon=True,
        )
        t.start()

    # ─────────────────────────────────────────────────────────────────────────
    # POST /api/adt/captura/record/<int:captura_id>/evidencias
    # Upload evidence files (images / videos) asynchronously.
    # ─────────────────────────────────────────────────────────────────────────


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
            'image/jpeg', 'image/jpg', 'image/png', 'image/webp',
            'video/mp4', 'video/quicktime', 'video/x-msvideo',
        }
        # Extension → canonical MIME mapping used as fallback when the client
        # sends a generic content-type (e.g. application/octet-stream).
        # Android devices frequently do this.
        EXT_MIME_MAP = {
            '.jpg' : 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png' : 'image/png',
            '.webp': 'image/webp',
            '.mp4' : 'video/mp4',
            '.mov' : 'video/quicktime',
            '.avi' : 'video/x-msvideo',
        }

        def _resolve_mimetype(f):
            """Return the effective MIME type for an uploaded file.
            If the reported content_type is not in ALLOWED_MIME, try to
            derive a valid type from the file extension (case-insensitive).
            """
            ct = (f.content_type or '').lower().split(';')[0].strip()
            if ct in ALLOWED_MIME:
                return ct
            # Fallback: use extension
            import os
            _, ext = os.path.splitext((f.filename or '').lower())
            return EXT_MIME_MAP.get(ext)  # None if unknown extension

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

            # Validate file types — accept by MIME or by extension fallback
            invalid = [f.filename for f in files if _resolve_mimetype(f) is None]
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
                    'mimetype'    : _resolve_mimetype(f),   # always a valid canonical type
                    'data'        : f.read(),
                })

            # Mark status as processing
            captura.write({'evidencias_status': 'processing'})

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
                                'evidencias_status': 'completed',
                            })
                            cr.commit()
                    _logger.info('Background upload completed for captura id=%s (%s files)', captura_id, len(files_data))
                except Exception:
                    # A fresh transaction is required after the failed attachment transaction.
                    try:
                        with odoo.registry(db).cursor() as failure_cr:
                            failure_env = odoo.api.Environment(failure_cr, uid, context)
                            record = failure_env['adt.captura.record'].browse(captura_id).exists()
                            if record:
                                record.write({'evidencias_status': 'failed'})
                            failure_cr.commit()
                    except Exception:
                        _logger.exception('Could not persist evidence failure for captura %s', captura_id)
                    _logger.exception('Background upload failed for captura id=%s', captura_id)

            t = threading.Thread(
                target=_save_attachments,
                args=(db, uid, context, captura_id, files_data),
                daemon=True,
            )
            # Start only once the request transaction has committed the processing state.
            request.env.cr.postcommit.add(t.start)

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
        captura = request.env['adt.captura.record'].sudo().browse(captura_id).exists()
        if not captura:
            return Response(json.dumps({'error': 'Captura no encontrada'}), status=404, mimetype='application/json')
        status = captura.evidencias_status
        return Response(
            json.dumps({'captura_id': captura_id, 'evidencias_status': status}),
            status=200,
            mimetype='application/json',
        )
