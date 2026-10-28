# -*- coding: utf-8 -*-
"""Datos de una deuda en captura para la app: contacto, papeletas SAT con sus copias,
GPS, refinanciamientos y capturas. Los usa captura_api; todas las funciones reciben
registros ya en sudo y no hacen consultas por fila cuando arman listas."""

import hashlib
import hmac
import re
import time
from datetime import datetime, timezone

# Archivos (copias SAT, evidencias, vouchers...) por URL firmada con vencimiento, para que
# la app los abra sin sesión de Odoo. Ver /api/adt/adjunto/<id> en captura_api.
ADJUNTO_URL_HORAS = 24
ADJUNTO_FIRMA_SCOPE = 'adt_captura.adjunto'
# Solo estos archivos se sirven por la URL firmada: (modelo, campo binario o None).
ADJUNTOS_PERMITIDOS = {
    ('adt.papeleta.sat', None),
    ('adt.captura.record', None),
    ('adt.captura.record', 'voucher_file'),
    ('adt.captura.record', 'documento_desafiliacion'),
    ('adt.captura.record', 'evidencia_entrega'),
    ('adt.captura.appeal', 'appeal_evidence'),
    ('res.partner', 'image_dni'),
}
GPS_HORAS_SIN_SENAL = 24
# Las cuotas que crea el refinanciamiento se llaman "Cuota R. - N" (adt.registrar.refinanciamiento).
CUOTA_REFINANCIADA = re.compile(r'^\s*cuota\s+r\.', re.IGNORECASE)
CAPTURAS_ACTIVAS = ('capturado', 'disolucion_contrato')


def fecha(valor):
    return valor.isoformat() if valor else None


def fecha_hora(valor):
    """Datetime de Odoo (UTC sin zona) en ISO con zona, para que la app no lo confunda con hora local."""
    return valor.replace(microsecond=0, tzinfo=timezone.utc).isoformat() if valor else None


def etiqueta(rec, campo, valor=None):
    """Texto de una opción de un campo selection; '' si el campo no existe o está vacío."""
    if campo not in rec._fields:
        return ''
    valor = rec[campo] if valor is None else valor
    if not valor:
        return ''
    campo = rec._fields[campo]
    if campo.type != 'selection':
        return str(valor)
    return dict(campo._description_selection(rec.env)).get(valor, valor)


def leer(rec, campo, defecto=None):
    """Valor de un campo que puede no existir (depende de los módulos instalados)."""
    return rec[campo] if rec and campo in rec._fields else defecto


def ref(rec, nombre='display_name'):
    return {'id': rec.id, 'name': rec[nombre] or ''} if rec else None


# ── Archivos ────────────────────────────────────────────────────────────────

def firma_adjunto(env, attachment_id, expira):
    secreto = env['ir.config_parameter'].sudo().get_param('database.secret') or ''
    mensaje = '%s:%s:%s' % (ADJUNTO_FIRMA_SCOPE, attachment_id, expira)
    return hmac.new(secreto.encode(), mensaje.encode(), hashlib.sha256).hexdigest()


def adjunto_permitido(att):
    return (att.res_model, att.res_field or None) in ADJUNTOS_PERMITIDOS


def adjunto_data(att, host, nombre=None):
    """{id, nombre, mimetype, es_imagen, tamano, fecha, url, expira} de un ir.attachment."""
    expira = int(time.time()) + ADJUNTO_URL_HORAS * 3600
    mimetype = att.mimetype or 'application/octet-stream'
    return {
        'id': att.id,
        'nombre': nombre or att.name or '',
        'mimetype': mimetype,
        'es_imagen': mimetype.startswith('image/'),
        'es_video': mimetype.startswith('video/'),
        'tamano': att.file_size or 0,
        'fecha': fecha_hora(att.create_date),
        'url': '%s/api/adt/adjunto/%s?expira=%s&firma=%s' % (
            host.rstrip('/'), att.id, expira, firma_adjunto(att.env, att.id, expira)),
        'expira': datetime.fromtimestamp(expira, timezone.utc).isoformat(),
    }


def adjuntos_por_registro(env, modelo, ids, campo=None):
    """{res_id: ir.attachment} de varios registros en una sola consulta."""
    if not ids:
        return {}
    domain = [('res_model', '=', modelo), ('res_id', 'in', list(ids))]
    domain.append(('res_field', '=', campo) if campo else ('res_field', '=', False))
    grupos = {}
    for att in env['ir.attachment'].sudo().search(domain, order='id desc'):
        grupos.setdefault(att.res_id, env['ir.attachment'].sudo())
        grupos[att.res_id] |= att
    return grupos


def archivo_campo(rec, campo, host, nombre):
    """Archivo guardado en un campo binario (attachment=True) del registro, o None."""
    if campo not in rec._fields:
        return None
    att = rec.env['ir.attachment'].sudo().search([
        ('res_model', '=', rec._name), ('res_id', '=', rec.id), ('res_field', '=', campo)], limit=1)
    return adjunto_data(att, host, nombre) if att else None


# ── Contacto ────────────────────────────────────────────────────────────────

def contacto_resumen(partner):
    """Lo necesario para ubicar al cliente desde la lista."""
    if not partner:
        return None
    return {
        'id': partner.id,
        'name': partner.name or '',
        'documento': leer(partner, 'document_number') or partner.vat or '',
        'tipo_documento': etiqueta(partner, 'tipo_documento'),
        'telefono': partner.phone or '',
        'celular': partner.mobile or '',
        'email': partner.email or '',
        'direccion': ', '.join(x for x in (partner.street, partner.street2, partner.city, partner.state_id.name,
                                           partner.zip, partner.country_id.name) if x),
    }


def contacto_detalle(partner, host, expediente=None, cuentas=None):
    """Todo lo que se sabe del cliente: datos personales, domicilio, referencias del
    expediente y sus otras cuentas y vehículos."""
    if not partner:
        return None
    data = contacto_resumen(partner)
    dni = archivo_campo(partner, 'image_dni', host, 'DNI de %s' % (partner.name or ''))
    data.update({
        'nombres': leer(partner, 'nombre_completo') or '',
        'apellido_paterno': leer(partner, 'apellido_paterno') or '',
        'apellido_materno': leer(partner, 'apellido_materno') or '',
        'ruc_dni': partner.vat or '',
        'codigo_socio': leer(partner, 'codigo_socio') or '',
        'nacionalidad': etiqueta(partner, 'nationality'),
        'estado_civil': etiqueta(partner, 'marital_status'),
        'hijos': etiqueta(partner, 'children_count'),
        'ocupacion': etiqueta(partner, 'occupation'),
        'calle': partner.street or '',
        'calle2': partner.street2 or '',
        'ciudad': partner.city or '',
        'departamento': partner.state_id.name or '',
        'pais': partner.country_id.name or '',
        'ubigeo': leer(partner, 'ubigeo') or '',
        'imagen_dni': dni,
        'domicilio_expediente': None,
        'referencias': [],
        'cuentas': [],
    })
    if expediente:
        if 'direccion_cliente' in expediente._fields:
            data['domicilio_expediente'] = {
                'direccion': expediente.direccion_cliente or '',
                'estado': etiqueta(expediente, 'estado_direccion'),
                'observaciones': leer(expediente, 'obs_direccion') or '',
            }
        for i in range(1, 5):
            nombre = leer(expediente, 'ref_%s_name' % i)
            telefono = leer(expediente, 'ref_%s_phone' % i)
            if nombre or telefono:
                data['referencias'].append({
                    'nombre': nombre or '',
                    'telefono': telefono or '',
                    'vinculo': etiqueta(expediente, 'ref_%s_vinculo' % i),
                })
    for c in (cuentas or []):
        data['cuentas'].append({
            'id': c.id,
            'reference_no': c.reference_no or '',
            'state': c.state or '',
            'estado': etiqueta(c, 'state'),
            'vehiculo': {
                'id': c.vehiculo_id.id,
                'display_name': c.vehiculo_id.display_name or '',
                'license_plate': c.vehiculo_id.license_plate or '',
            } if c.vehiculo_id else None,
            'fecha_desembolso': fecha(c.fecha_desembolso),
            'monto_cuota': c.monto_cuota or 0.0,
            'periodicidad': etiqueta(c, 'periodicidad'),
        })
    return data


# ── Papeletas SAT ───────────────────────────────────────────────────────────

def papeleta_sat_data(p, host, copias=None):
    """Papeleta del SAT Lima con su estado y sus copias (imágenes). Conserva las claves que
    usaba la app con la papeleta interna (state, monto, fecha_emision...)."""
    return {
        'id': p.id,
        'name': p.name or '',
        'state': p.estado_pago or '',
        'estado_pago': etiqueta(p, 'estado_pago'),
        'estado_sat': p.estado_sat or '',
        'vigente': p.vigente,
        'revision': etiqueta(p, 'revision'),
        'monto': p.deuda or 0.0,
        'importe': p.importe or 0.0,
        'gastos_costas': p.gastos_costas or 0.0,
        'descuento': p.descuento or 0.0,
        'deuda': p.deuda or 0.0,
        'fecha_emision': fecha(p.fecha_infraccion),
        'dias': p.dias or 0,
        'alerta_dias': p.alerta_dias,
        'reglamento': p.reglamento or '',
        'codigo_falta': p.codigo_falta or '',
        'detalle': p.codigo_falta or '',
        'placa': p.placa or '',
        'licencia_conducir': p.licencia_conducir or '',
        'documento_infractor': ' '.join(x for x in (p.tipo_documento, p.numero_documento) if x),
        'numero_compromiso_pago': p.numero_compromiso_pago or '',
        'primera_vez_visto': fecha_hora(p.primera_vez_visto),
        'ultima_consulta': fecha_hora(p.ultima_vez_visto),
        'resuelta_en': fecha_hora(p.resuelta_en),
        'url_copia_sat': p.url_copia or '',
        'estado_copia': p.estado_copia or '',
        'imagenes': [adjunto_data(a, host) for a in (copias or [])],
        'vehicle_id': {
            'id': p.vehicle_id.id,
            'display_name': p.vehicle_id.display_name or '',
        } if p.vehicle_id else None,
    }


def papeletas_sat_lista(env, papeletas, host):
    copias = adjuntos_por_registro(env, 'adt.papeleta.sat', papeletas.ids)
    return [papeleta_sat_data(p, host, copias.get(p.id)) for p in papeletas]


def papeletas_sat_pendientes_por_cuenta(env, cuentas):
    """{cuenta_id: papeletas SAT pendientes}, con el criterio de adt.captura.mora: pendientes
    de pago y cometidas desde el desembolso (o sin fecha)."""
    Sat = env['adt.papeleta.sat'].sudo()
    vehiculos = cuentas.mapped('vehiculo_id')
    if not vehiculos:
        return {}
    todas = Sat.search([('vehicle_id', 'in', vehiculos.ids), ('estado_pago', '=', 'pendiente')],
                       order='fecha_infraccion asc, id asc')
    resultado = {}
    for c in cuentas:
        resultado[c.id] = todas.filtered(
            lambda p, c=c: p.vehicle_id == c.vehiculo_id and (
                not c.fecha_desembolso or not p.fecha_infraccion or p.fecha_infraccion >= c.fecha_desembolso))
    return resultado


# ── GPS ─────────────────────────────────────────────────────────────────────

def gps_data(vehicle):
    """Estado del GPS (Traccar) del vehículo. registrado=False si no tiene equipo."""
    if not vehicle or 'traccar_credential_active_id' not in vehicle._fields:
        return {'registrado': False, 'disponible': False}
    cred = vehicle.traccar_credential_active_id
    if not cred:
        return {'registrado': False, 'disponible': True}
    ultimo = cred.gps_last_update
    horas = round((datetime.utcnow() - ultimo).total_seconds() / 3600, 1) if ultimo else None
    status = cred.gps_status or 'unknown'
    return {
        'registrado': True,
        'disponible': True,
        'status': status,
        'estado': etiqueta(cred, 'gps_status', status) or 'Desconocido',
        'sin_senal': status == 'offline' or horas is None or horas > GPS_HORAS_SIN_SENAL,
        'ultimo_reporte': fecha_hora(ultimo),
        'horas_sin_reporte': horas,
        'actualizado_en_odoo': fecha_hora(cred.gps_status_refreshed_at),
        'latitud': cred.gps_latitude or None,
        'longitud': cred.gps_longitude or None,
        'direccion': cred.gps_address or '',
        'velocidad_kmh': cred.gps_speed_kmh or 0.0,
        'bateria': cred.gps_battery_level or None,
        'mapa_url': cred.gps_maps_url or '',
        'imei': cred.imei or '',
        'registro': etiqueta(cred, 'state'),
        'km_actual': leer(vehicle, 'traccar_km_actual') or None,
    }


# ── Refinanciamientos ───────────────────────────────────────────────────────

def refinanciamientos_data(cuentas, capturas):
    """Refinanciamientos de las cuentas. El asistente no guarda un registro propio: borra las
    cuotas sin pagar y crea las nuevas como "Cuota R. - N", todas en la misma operación, así
    que cada grupo de esas cuotas creadas juntas es un refinanciamiento."""
    resultado = []
    for c in cuentas:
        grupos = {}
        for q in c.cuota_ids:
            if q.type == 'cuota' and not q.parent_id and q.name and CUOTA_REFINANCIADA.match(q.name):
                grupos.setdefault(q.create_date.replace(microsecond=0) if q.create_date else None, []).append(q)
        for creado, cuotas in sorted(grupos.items(), key=lambda g: g[0] or datetime.min):
            fechas = [q.fecha_cronograma for q in cuotas if q.fecha_cronograma]
            resultado.append({
                'cuenta': {'id': c.id, 'reference_no': c.reference_no or ''},
                'fecha': fecha_hora(creado),
                'registrado_por': cuotas[0].create_uid.name or '',
                'periodicidad': etiqueta(cuotas[0], 'periodicidad'),
                'cuotas': len(cuotas),
                'monto_total': round(sum(q.monto or 0.0 for q in cuotas), 2),
                'monto_cuota': cuotas[0].monto or 0.0,
                'cuotas_pagadas': sum(1 for q in cuotas if q.state == 'pagado'),
                'cuotas_retrasadas': sum(1 for q in cuotas if q.state == 'retrasado'),
                'cuotas_pendientes': sum(1 for q in cuotas if q.state in ('pendiente', 'a_cuenta', 'retrasado')),
                'saldo': round(sum(q.saldo or 0.0 for q in cuotas if q.state != 'pagado'), 2),
                'primera_cuota': fecha(min(fechas)) if fechas else None,
                'ultima_cuota': fecha(max(fechas)) if fechas else None,
            })
    liberadas = capturas.filtered(lambda k: k.liberacion_tipo == 'refinanciamiento')
    return {
        'total': len(resultado),
        'registros': resultado,
        'capturas_liberadas_por_refinanciamiento': [
            {'id': k.id, 'name': k.name or '', 'estado': etiqueta(k, 'state'),
             'ultima_modificacion': fecha_hora(k.write_date)} for k in liberadas],
    }


# ── Capturas ────────────────────────────────────────────────────────────────

def captura_data(k, host):
    """Una captura con lo que pasó en cada paso y los archivos que se subieron en él."""
    otros = k.env['ir.attachment'].sudo().search([
        ('res_model', '=', k._name), ('res_id', '=', k.id), ('res_field', '=', False),
        ('id', 'not in', k.evidencia_archivos.ids)])
    apelaciones = []
    for a in k.appeal_ids:
        apelaciones.append({
            'id': a.id,
            'motivo': a.appeal_reason or '',
            'evidencia': archivo_campo(a, 'appeal_evidence', host, a.appeal_reason or 'Apelación'),
        })
    documentos = [d for d in (
        archivo_campo(k, 'documento_desafiliacion', host, 'Documento de desafiliación'),
        archivo_campo(k, 'evidencia_entrega', host, 'Evidencia de la entrega'),
    ) if d]
    historial = []
    for m in k.message_ids[:50]:
        cambios = ['%s: %s → %s' % (t.field_desc or '', t.get_old_display_value()[0] or '',
                                    t.get_new_display_value()[0] or '')
                   for t in m.tracking_value_ids]
        historial.append({
            'fecha': fecha_hora(m.date),
            'autor': m.author_id.name or '',
            'mensaje': re.sub(r'<[^>]+>', ' ', m.body or '').strip(),
            'cambios': cambios,
        })
    return {
        'id': k.id,
        'name': k.name or '',
        'state': k.state or '',
        'estado': etiqueta(k, 'state'),
        'activa': k.state in CAPTURAS_ACTIVAS,
        'origen': k.source_type or 'none',
        'origen_label': etiqueta(k, 'source_type'),
        'fecha': fecha_hora(k.create_date),
        'cuenta': {'id': k.cuenta_id.id, 'reference_no': k.cuenta_id.reference_no or ''} if k.cuenta_id else None,
        'captura': {
            'tipo': k.capture_type or '',
            'tipo_label': etiqueta(k, 'capture_type'),
            'fecha_compromiso': fecha(k.commitment_date),
            'capturador': ref(k.capturador_id, 'name'),
            'supervisor': ref(k.supervisor_id, 'name'),
            'moto_recogida': k.moto_recogida,
            'motivo_no_recogida': k.motivo_no_recogida or '',
            'comentarios': k.comentarios_captura or '',
            'dias_mora': k.dias_mora or 0,
            'cuotas_vencidas': k.numero_cuotas_vencidas or 0,
            'papeletas_sat': [{'id': p.id, 'name': p.name or '', 'deuda': p.deuda or 0.0,
                               'estado_pago': etiqueta(p, 'estado_pago')} for p in k.papeleta_sat_ids],
            'deuda_sat_pendiente': k.deuda_sat or 0.0,
            'evidencias': [adjunto_data(a, host) for a in (k.evidencia_archivos | otros).sudo()],
            'evidencias_estado': etiqueta(k, 'evidencias_status'),
        },
        'cobro': {
            'monto_intervencion': k.intervention_fee or 0.0,
            'pagar_monto': k.pagar_monto,
            'estado': k.payment_state or '',
            'estado_label': etiqueta(k, 'payment_state'),
            'fecha_pago': fecha(k.payment_date),
            'numero_voucher': k.voucher_number or '',
            'motivo_no_pago': k.motivo_no_pago or '',
            'voucher': archivo_campo(k, 'voucher_file', host, k.voucher_filename or 'Voucher de pago'),
        },
        'decision': {
            'liberacion_tipo': k.liberacion_tipo or '',
            'liberacion': etiqueta(k, 'liberacion_tipo'),
            'observaciones': k.observaciones or '',
            'retencion_motivo': etiqueta(k, 'retention_reason'),
            'retencion_fecha': fecha(k.retention_date),
            'retencion_notas': k.notes or '',
            'apelaciones': apelaciones,
        },
        'recolocacion': {'documentos': documentos},
        'historial': historial,
    }


def capturas_lista(capturas, host):
    return [captura_data(k, host) for k in capturas]
