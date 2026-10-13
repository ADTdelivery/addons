# -*- coding: utf-8 -*-
"""Flota 360: datos para la vista unificada del vehículo.

Todo se calcula en lote (una consulta por módulo, no por vehículo) para que
el buscador responda rápido aun recorriendo toda la flota. Cada módulo es
opcional: si su modelo no está instalado o el usuario no tiene acceso, su
información simplemente no aparece.
"""
import logging
import re
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.osv import expression
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

# Filtros rápidos del buscador (orden de los chips).
FILTROS = [
    ('todos', 'Todos'),
    ('atencion', 'Requieren atención'),
    ('mora', 'Cuotas vencidas'),
    ('papeletas', 'Papeletas pendientes'),
    ('capturas', 'Capturados'),
    ('gps_off', 'GPS sin señal'),
    ('sin_placa', 'Sin placa'),
    ('taller', 'En taller'),
]

NIVEL_ORDEN = {'critico': 0, 'atencion': 1, 'ok': 2}
MAX_ANALISIS = 5000          # vehículos evaluados por búsqueda
CUOTAS_CRITICAS = 3          # desde cuántas cuotas vencidas es crítico
GPS_HORAS_SIN_SENAL = 24     # sin reporte del equipo por más de N horas
CUOTAS_ABIERTAS = ('pendiente', 'a_cuenta', 'retrasado')
CAPTURA_ACTIVA = ('capturado', 'disolucion_contrato')
TALLER_ABIERTO = ('pending', 'in_progress', 'blocked')
# Estado del expediente → nivel del indicador.
EXPEDIENTE_NIVEL = {
    'completo': 'ok', 'aprobado_sin_desembolso': 'ok', 'por_revisar': 'info',
    'incompleto_expediente': 'atencion', 'incompleto_fase_final': 'atencion', 'rechazado': 'neutral',
}
SIGLAS = {'ce', 'dni', 'soat', 'ruc'}
# Cambios de estado del formulario del expediente (todos envían notificación push).
EXPEDIENTE_ESTADOS = [
    ('action_mark_completo', 'completo', 'Marcar completo', 'fa-check'),
    ('action_mark_aprobado_sin_desembolso', 'aprobado_sin_desembolso', 'Aprobado sin desembolso', 'fa-check-square-o'),
    ('action_mark_incompleto_expediente', 'incompleto_expediente', 'Marcar incompleto - Expediente', 'fa-exclamation'),
    ('action_mark_incompleto_fase_final', 'incompleto_fase_final', 'Marcar incompleto - Fase final', 'fa-exclamation'),
]

# Mismo criterio que adt_tramite_placa / adt_dashboard_flota.
PLACA_FALSA = {
    'S/P', 'SP', 'S/N', 'SN', 'SIN PLACA', 'EN TRAMITE', 'EN TRÁMITE',
    'TRAMITE', 'TRÁMITE', 'PENDIENTE', 'NULL', 'NONE', 'N/A', 'NA', '-', '--',
}


def placa_valida(placa):
    return bool(placa and placa.strip() and placa.strip().upper() not in PLACA_FALSA)


def plural(n, singular, plural_):
    return '%s %s' % (n, singular if n == 1 else plural_)


def compactar(texto):
    return re.sub(r'[^0-9A-Za-z]', '', texto or '').upper()


def accion_abrir(modelo, res_id, label='Abrir', icono='fa-external-link', contexto=None):
    """Abre el formulario del registro en ventana emergente (sin res_id: uno nuevo con `contexto`)."""
    return {'tipo': 'abrir', 'model': modelo, 'res_id': res_id, 'label': label, 'icon': icono, 'context': contexto}


def accion_metodo(modelo, res_id, metodo, label, icono, confirmar=None, primaria=False, peligro=False, args=None):
    """Llama `metodo` sobre el registro (o con `args` si se indican). Si el método
    devuelve una acción (asistente, reporte), la vista la abre en ventana emergente."""
    if peligro and not confirmar:
        confirmar = '¿Confirmas "%s"? Esta operación no se puede deshacer.' % label
    return {'tipo': 'metodo', 'model': modelo, 'res_id': res_id, 'method': metodo, 'args': args,
            'label': label, 'icon': icono, 'confirm': confirmar, 'primary': primaria, 'danger': peligro}


def accion_url(url, label, icono):
    return {'tipo': 'url', 'url': url, 'label': label, 'icon': icono}


class AdtFlota360(models.AbstractModel):
    _name = 'adt.flota360'
    _description = 'Flota 360: vista unificada del vehículo'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _modelo(self, nombre, *campos):
        """Devuelve el modelo si está instalado, tiene los campos pedidos y el
        usuario puede leerlo; si no, None (la sección se omite)."""
        if nombre not in self.env:
            return None
        Model = self.env[nombre]
        if any(c not in Model._fields for c in campos):
            return None
        if not Model.check_access_rights('read', raise_exception=False):
            return None
        return Model

    def _metodo(self, modelo, metodo):
        return modelo in self.env and hasattr(self.env[modelo], metodo)

    def _etiqueta(self, Model, campo, valor):
        if not valor or campo not in Model._fields:
            return valor or ''
        return dict(Model._fields[campo]._description_selection(self.env)).get(valor, valor)

    def _m2o(self, valor):
        return valor[1] if valor else ''

    def _id(self, valor):
        return valor[0] if valor else False

    def _nombre_modelo(self, fila):
        """El display_name del modelo de Odoo es "Marca/Modelo"; la marca ya se muestra aparte."""
        modelo = self._m2o(fila.get('model_id'))
        marca = self._m2o(fila.get('brand_id'))
        if marca and modelo.startswith(marca + '/'):
            modelo = modelo[len(marca) + 1:]
        return modelo

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------

    @api.model
    def get_filtros(self):
        return [{'key': k, 'label': l} for k, l in FILTROS]

    def _dominio_busqueda(self, termino):
        termino = (termino or '').strip()
        if not termino:
            return []
        Vehicle = self.env['fleet.vehicle']
        campos = ['license_plate', 'vin_sn', 'model_id.name', 'driver_id.name',
                  'driver_id.vat', 'driver_id.phone', 'driver_id.mobile']
        if 'x_motor_sn' in Vehicle._fields:
            campos.append('x_motor_sn')
        if 'cuenta_ids' in Vehicle._fields:
            campos += ['cuenta_ids.partner_id.name', 'cuenta_ids.partner_id.vat', 'cuenta_ids.reference_no']
        dominios = [[(c, 'ilike', termino)] for c in campos]
        # "abc123" encuentra "ABC-123" y viceversa.
        compacto = compactar(termino)
        if 4 <= len(compacto) <= 8:
            dominios.append([('license_plate', '=ilike', '%' + '%'.join(compacto) + '%')])
        return expression.OR(dominios)

    @api.model
    def buscar(self, termino='', filtro='todos', offset=0, limit=24):
        vehiculos = self.env['fleet.vehicle'].search(self._dominio_busqueda(termino), limit=MAX_ANALISIS)
        resumenes = self._resumenes(vehiculos)

        contadores = {k: 0 for k, _l in FILTROS}
        cartera = {'vencido': 0.0, 'mora': 0.0, 'papeletas': 0.0}
        for r in resumenes:
            contadores['todos'] += 1
            for k in r['filtros']:
                contadores[k] = contadores.get(k, 0) + 1
            for m in r['modulos']:
                if m['key'] == 'cuentas':
                    cartera['vencido'] += m.get('vencido', 0.0)
                    cartera['mora'] += m.get('mora', 0.0)
                elif m['key'] == 'papeletas':
                    cartera['papeletas'] += m.get('monto', 0.0)

        filtrados = [r for r in resumenes if filtro == 'todos' or filtro in r['filtros']]
        compacto = compactar(termino)
        filtrados.sort(key=lambda r: (
            0 if compacto and compactar(r['placa']) == compacto else 1,
            NIVEL_ORDEN[r['salud']['nivel']],
            -r['salud']['puntaje'],
            r['placa'] or '~',
        ))
        return {
            'total': len(filtrados),
            'items': filtrados[offset:offset + limit],
            'contadores': contadores,
            'cartera': cartera,
            'truncado': len(vehiculos) >= MAX_ANALISIS,
        }

    # ------------------------------------------------------------------
    # Resumen por vehículo (tarjetas)
    # ------------------------------------------------------------------

    def _resumenes(self, vehiculos):
        if not vehiculos:
            return []
        Vehicle = self.env['fleet.vehicle']
        hoy = fields.Date.context_today(self)
        ids = vehiculos.ids

        campos = [c for c in ('license_plate', 'model_id', 'brand_id', 'vin_sn', 'driver_id',
                              'state_id', 'color', 'model_year') if c in Vehicle._fields]
        filas = vehiculos.read(campos)

        cuentas = self._lote_cuentas(ids, hoy)
        clientes = self._lote_clientes(filas, cuentas)
        papeletas = self._lote_papeletas(ids, hoy)
        gps = self._lote_gps(ids)
        placas = self._lote_placa(ids)
        capturas = self._lote_capturas(ids)
        taller = self._lote_taller(ids)
        expedientes = self._lote_expedientes(clientes)

        resultado = []
        for f in filas:
            vid = f['id']
            cliente = clientes.get(vid) or {}
            modulos, alertas, filtros = [], [], set()

            if cuentas is not None:
                self._resumen_cuenta(cuentas.get(vid), modulos, alertas, filtros)
            if papeletas is not None:
                self._resumen_papeletas(papeletas.get(vid), hoy, modulos, alertas, filtros)
            if gps is not None:
                self._resumen_gps(gps.get(vid), cuentas and cuentas.get(vid), modulos, alertas, filtros)
            self._resumen_placa(f.get('license_plate'), placas and placas.get(vid), bool(cliente),
                                modulos, alertas, filtros)
            if capturas is not None:
                self._resumen_captura(capturas.get(vid), modulos, alertas, filtros)
            if taller is not None:
                self._resumen_taller(taller.get(vid), modulos, alertas, filtros)
            if expedientes is not None and cliente:
                self._resumen_expediente(expedientes.get(cliente['id']), modulos, alertas)

            criticos = sum(1 for a in alertas if a['nivel'] == 'critico')
            atencion = sum(1 for a in alertas if a['nivel'] == 'atencion')
            nivel = 'critico' if criticos else ('atencion' if atencion else 'ok')
            if nivel != 'ok':
                filtros.add('atencion')

            resultado.append({
                'id': vid,
                'placa': f.get('license_plate') or '',
                'tiene_placa': placa_valida(f.get('license_plate')),
                'modelo': self._nombre_modelo(f),
                'marca': self._m2o(f.get('brand_id')),
                'anio': f.get('model_year') or '',
                'color': f.get('color') or '',
                'chasis': f.get('vin_sn') or '',
                'estado': self._m2o(f.get('state_id')),
                'cliente': cliente,
                'modulos': modulos,
                'alertas': sorted(alertas, key=lambda a: NIVEL_ORDEN.get(a['nivel'], 3)),
                'filtros': sorted(filtros),
                'salud': {
                    'nivel': nivel,
                    'puntaje': criticos * 10 + atencion * 3,
                    'texto': {'critico': 'Crítico', 'atencion': 'Atención', 'ok': 'Al día'}[nivel],
                },
            })
        return resultado

    # --- Lotes por módulo ------------------------------------------------
    # Cada _lote_* devuelve {vehicle_id: info} o None si el módulo no aplica.

    def _lote_clientes(self, filas, cuentas):
        """Cliente = conductor del vehículo; si no tiene, el socio de su cuenta."""
        pid_por_vehiculo = {}
        for f in filas:
            pid = self._id(f.get('driver_id'))
            if not pid and cuentas and cuentas.get(f['id']):
                pid = cuentas[f['id']]['partner_id']
            if pid:
                pid_por_vehiculo[f['id']] = pid
        if not pid_por_vehiculo:
            return {}
        Partner = self.env['res.partner']
        datos = {p['id']: p for p in Partner.browse(set(pid_por_vehiculo.values())).read(
            ['name', 'vat', 'phone', 'mobile', 'email'])}
        res = {}
        for vid, pid in pid_por_vehiculo.items():
            p = datos.get(pid)
            if p:
                res[vid] = {'id': pid, 'nombre': p['name'] or '', 'documento': p['vat'] or '',
                            'telefono': p['mobile'] or p['phone'] or '', 'email': p['email'] or ''}
        return res

    def _lote_cuentas(self, ids, hoy):
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id', 'state', 'partner_id')
        if Cuenta is None:
            return None
        campos = [c for c in ('vehiculo_id', 'partner_id', 'state', 'reference_no', 'mora_pendiente')
                  if c in Cuenta._fields]
        filas = Cuenta.search_read([('vehiculo_id', 'in', ids)], campos, order='id desc')
        # Prioridad: la cuenta vigente; si no hay, la más reciente.
        elegida = {}
        for c in filas:
            vid = self._id(c['vehiculo_id'])
            actual = elegida.get(vid)
            if not actual or (c['state'] in ('en_curso', 'aprobado') and actual['state'] not in ('en_curso', 'aprobado')):
                elegida[vid] = c
        if not elegida:
            return {}

        vencidas = {}
        Cuota = self._modelo('adt.comercial.cuotas', 'cuenta_id', 'state', 'fecha_cronograma', 'saldo')
        if Cuota is not None:
            dominio = [('cuenta_id', 'in', [c['id'] for c in elegida.values()]),
                       ('state', 'in', list(CUOTAS_ABIERTAS)), ('fecha_cronograma', '<', hoy)]
            if 'type' in Cuota._fields:
                dominio.append(('type', '=', 'cuota'))
            for g in Cuota.read_group(dominio, ['cuenta_id', 'saldo:sum', 'fecha_cronograma:min'], ['cuenta_id']):
                desde = g['fecha_cronograma']
                if isinstance(desde, str):
                    desde = fields.Date.to_date(desde)
                vencidas[g['cuenta_id'][0]] = (g['cuenta_id_count'], g['saldo'] or 0.0,
                                               (hoy - desde).days if desde else 0)

        res = {}
        for vid, c in elegida.items():
            n, monto, dias = vencidas.get(c['id'], (0, 0.0, 0))
            res[vid] = {
                'id': c['id'],
                'partner_id': self._id(c['partner_id']),
                'referencia': c.get('reference_no') or '',
                'state': c['state'],
                'estado': self._etiqueta(Cuenta, 'state', c['state']),
                'vencidas': n,
                'monto_vencido': monto,
                'dias_atraso': dias,
                'mora': c.get('mora_pendiente') or 0.0,
            }
        return res

    def _lote_papeletas(self, ids, hoy):
        Papeleta = self._modelo('adt.papeleta', 'vehicle_id', 'state', 'monto')
        if Papeleta is None:
            return None
        campos = [c for c in ('vehicle_id', 'monto', 'fecha_vencimiento_final', 'proximo_a_vencerse', 'capturado')
                  if c in Papeleta._fields]
        res = defaultdict(lambda: {'pendientes': 0, 'monto': 0.0, 'vencidas': 0, 'por_vencer': 0})
        for p in Papeleta.search_read([('vehicle_id', 'in', ids), ('state', '!=', 'pagado')], campos):
            r = res[self._id(p['vehicle_id'])]
            r['pendientes'] += 1
            r['monto'] += p['monto'] or 0.0
            venc = p.get('fecha_vencimiento_final')
            if venc and venc < hoy:
                r['vencidas'] += 1
            elif p.get('proximo_a_vencerse'):
                r['por_vencer'] += 1
        return dict(res)

    def _lote_gps(self, ids):
        Cred = self._modelo('adt.traccar.device.credential', 'vehicle_id', 'state', 'gps_status')
        if Cred is None:
            return None
        res = {}
        for c in Cred.search_read([('vehicle_id', 'in', ids), ('state', '=', 'activo')],
                                  ['vehicle_id', 'gps_status', 'gps_last_update'], order='id desc'):
            res.setdefault(self._id(c['vehicle_id']), c)
        return res

    def _lote_placa(self, ids):
        Tramite = self._modelo('adt.tramite.placa', 'vehicle_id', 'state')
        if Tramite is None:
            return None
        res = {}
        for t in Tramite.search_read([('vehicle_id', 'in', ids)], ['vehicle_id', 'state', 'num_placa'],
                                     order='id desc'):
            res.setdefault(self._id(t['vehicle_id']), t)
        return res

    def _lote_capturas(self, ids):
        Captura = self._modelo('adt.captura.record', 'vehicle_id', 'state')
        if Captura is None:
            return None
        res = {}
        for c in Captura.search_read([('vehicle_id', 'in', ids), ('state', 'in', list(CAPTURA_ACTIVA))],
                                     ['vehicle_id', 'state', 'name'], order='id desc'):
            res.setdefault(self._id(c['vehicle_id']), c)
        return res

    def _lote_expedientes(self, clientes):
        """Último expediente de cada cliente de turno: {partner_id: expediente}."""
        Expediente = self._modelo('adt.expediente', 'cliente_id', 'state')
        if Expediente is None:
            return None
        pids = list({c['id'] for c in clientes.values()})
        res = {}
        if pids:
            for e in Expediente.search_read([('cliente_id', 'in', pids)], ['cliente_id', 'state'],
                                            order='fecha desc, id desc'):
                res.setdefault(self._id(e['cliente_id']), e)
        return res

    def _lote_taller(self, ids):
        Orden = self._modelo('maintenance.work.order', 'vehicle_id', 'state')
        if Orden is None:
            return None
        res = defaultdict(lambda: {'abiertas': 0, 'bloqueadas': 0})
        for o in Orden.search_read([('vehicle_id', 'in', ids), ('state', 'in', list(TALLER_ABIERTO))],
                                   ['vehicle_id', 'state']):
            r = res[self._id(o['vehicle_id'])]
            r['abiertas'] += 1
            r['bloqueadas'] += o['state'] == 'blocked'
        return dict(res)

    # --- Semáforo por módulo ----------------------------------------------
    # Cada _resumen_* agrega su chip a `modulos`, sus alertas y sus filtros.

    def _chip(self, key, icono, titulo, texto, nivel):
        return {'key': key, 'icon': icono, 'titulo': titulo, 'texto': texto, 'nivel': nivel}

    def _alerta(self, modulo, nivel, texto):
        return {'modulo': modulo, 'nivel': nivel, 'texto': texto}

    def _resumen_cuenta(self, c, modulos, alertas, filtros):
        if not c:
            modulos.append(self._chip('cuentas', 'fa-credit-card', 'Cuenta', 'Sin cuenta', 'neutral'))
            return
        if c['vencidas']:
            nivel = 'critico' if c['vencidas'] >= CUOTAS_CRITICAS else 'atencion'
            texto = plural(c['vencidas'], 'vencida', 'vencidas')
            alertas.append(self._alerta('cuentas', nivel, plural(c['vencidas'], 'cuota vencida', 'cuotas vencidas')))
            filtros.add('mora')
        elif c['mora']:
            nivel, texto = 'atencion', _('Mora pendiente')
            alertas.append(self._alerta('cuentas', 'atencion', _('Mora pendiente por cobrar')))
            filtros.add('mora')
        elif c['state'] in ('en_curso', 'aprobado'):
            nivel, texto = 'ok', _('Al día')
        else:
            nivel, texto = 'neutral', c['estado']
        chip = self._chip('cuentas', 'fa-credit-card', 'Cuenta', texto, nivel)
        chip.update(monto=c['monto_vencido'] + c['mora'], vencido=c['monto_vencido'], mora=c['mora'],
                    dias=c['dias_atraso'], referencia=c['referencia'])
        modulos.append(chip)

    def _resumen_papeletas(self, p, hoy, modulos, alertas, filtros):
        if not p:
            modulos.append(self._chip('papeletas', 'fa-file-text-o', 'Papeletas', 'Sin pendientes', 'ok'))
            return
        filtros.add('papeletas')
        if p['vencidas']:
            nivel = 'critico'
            alertas.append(self._alerta('papeletas', nivel, plural(p['vencidas'], 'papeleta vencida', 'papeletas vencidas') + ': riesgo de captura'))
        elif p['por_vencer']:
            nivel = 'atencion'
            alertas.append(self._alerta('papeletas', nivel, plural(p['por_vencer'], 'papeleta por vencer', 'papeletas por vencer')))
        else:
            nivel = 'atencion'
            alertas.append(self._alerta('papeletas', nivel, plural(p['pendientes'], 'papeleta pendiente', 'papeletas pendientes')))
        chip = self._chip('papeletas', 'fa-file-text-o', 'Papeletas', plural(p['pendientes'], 'pendiente', 'pendientes'), nivel)
        chip['monto'] = p['monto']
        modulos.append(chip)

    def _resumen_gps(self, g, cuenta, modulos, alertas, filtros):
        if not g:
            # Solo es un problema si el vehículo ya está con un cliente.
            activa = cuenta and cuenta['state'] in ('en_curso', 'aprobado')
            if activa:
                alertas.append(self._alerta('gps', 'atencion', _('Cuenta activa sin GPS registrado')))
            modulos.append(self._chip('gps', 'fa-map-marker', 'GPS', 'Sin registrar',
                                      'atencion' if activa else 'neutral'))
            return
        ultimo = g.get('gps_last_update')
        sin_senal = g.get('gps_status') == 'offline' or (
            ultimo and fields.Datetime.now() - ultimo > timedelta(hours=GPS_HORAS_SIN_SENAL))
        if sin_senal:
            filtros.add('gps_off')
            alertas.append(self._alerta('gps', 'atencion', _('GPS sin señal')))
            chip = self._chip('gps', 'fa-map-marker', 'GPS', 'Sin señal', 'atencion')
        elif g.get('gps_status') == 'online':
            chip = self._chip('gps', 'fa-map-marker', 'GPS', 'En línea', 'ok')
        else:
            chip = self._chip('gps', 'fa-map-marker', 'GPS', 'Sin datos', 'neutral')
        chip['desde'] = fields.Datetime.to_string(ultimo) if ultimo else False
        modulos.append(chip)

    def _resumen_placa(self, placa, tramite, tiene_cliente, modulos, alertas, filtros):
        if placa_valida(placa):
            modulos.append(self._chip('placa', 'fa-id-card-o', 'Placa', 'Con placa', 'ok'))
            return
        filtros.add('sin_placa')
        estado = tramite and tramite['state']
        if estado == 'observado':
            nivel, texto = 'atencion', 'Observado'
            alertas.append(self._alerta('placa', nivel, _('Trámite de placa observado')))
        elif tiene_cliente:
            nivel = 'atencion'
            texto = 'En trámite' if estado == 'en_tramite' else 'Sin placa'
            alertas.append(self._alerta('placa', nivel, _('Cliente esperando placa')))
        else:
            nivel = 'neutral'
            texto = {'en_tramite': 'En trámite', 'pendiente': 'Pendiente'}.get(estado, 'Sin placa')
        modulos.append(self._chip('placa', 'fa-id-card-o', 'Placa', texto, nivel))

    def _resumen_captura(self, c, modulos, alertas, filtros):
        if not c:
            return
        filtros.add('capturas')
        texto = 'Capturado' if c['state'] == 'capturado' else 'Disolución'
        alertas.append(self._alerta('capturas', 'critico', _('Vehículo %s (%s)') % (texto.lower(), c['name'])))
        modulos.append(self._chip('capturas', 'fa-lock', 'Captura', texto, 'critico'))

    def _resumen_expediente(self, e, modulos, alertas):
        if not e:
            modulos.append(self._chip('expediente', 'fa-folder-open-o', 'Expediente', 'Sin expediente', 'neutral'))
            return
        Expediente = self.env['adt.expediente']
        nivel = EXPEDIENTE_NIVEL.get(e['state'], 'neutral')
        texto = self._etiqueta(Expediente, 'state', e['state']) or 'Sin estado'
        if nivel == 'atencion':
            alertas.append(self._alerta('expediente', nivel, 'Expediente %s' % texto.lower()))
        modulos.append(self._chip('expediente', 'fa-folder-open-o', 'Expediente', texto, nivel))

    def _resumen_taller(self, t, modulos, alertas, filtros):
        if not t:
            return
        filtros.add('taller')
        if t['bloqueadas']:
            alertas.append(self._alerta('taller', 'atencion', _('Orden de taller bloqueada')))
        modulos.append(self._chip('taller', 'fa-wrench', 'Taller',
                                  plural(t['abiertas'], 'orden abierta', 'órdenes abiertas'),
                                  'atencion' if t['bloqueadas'] else 'info'))

    # ------------------------------------------------------------------
    # Detalle 360 (panel lateral)
    # ------------------------------------------------------------------

    @api.model
    def detalle(self, vehicle_id):
        vehiculo = self.env['fleet.vehicle'].browse(vehicle_id).exists()
        if not vehiculo:
            return False
        vehiculo.check_access_rule('read')
        hoy = fields.Date.context_today(self)
        resumen = self._resumenes(vehiculo)[0]

        secciones = [self._seccion_vehiculo(vehiculo), self._seccion_cliente(vehiculo, resumen['cliente'])]
        for metodo in (self._seccion_cuentas, self._seccion_papeletas, self._seccion_gps,
                       self._seccion_placa, self._seccion_capturas, self._seccion_taller,
                       self._seccion_expediente):
            try:
                seccion = metodo(vehiculo, hoy)
            except AccessError:
                seccion = None
            if seccion:
                secciones.append(seccion)

        resumen['secciones'] = secciones
        resumen['acciones'] = self._acciones_rapidas(vehiculo)
        return resumen

    def _acciones_rapidas(self, v):
        acciones = []
        for metodo, label, icono in (
            ('action_new_cuenta', 'Nueva cuenta', 'fa-credit-card'),
            ('action_new_adt_papeleta', 'Registrar papeleta', 'fa-file-text-o'),
            ('action_new_work_order', 'Orden de taller', 'fa-wrench'),
            ('action_new_adt_captura', 'Registrar captura', 'fa-lock'),
        ):
            if self._metodo('fleet.vehicle', metodo):
                acciones.append(accion_metodo('fleet.vehicle', v.id, metodo, label, icono))
        return acciones

    def _campo(self, label, valor):
        return [label, valor] if valor not in (False, None, '') else None

    def _campos(self, *pares):
        return [p for p in pares if p]

    def _seccion_vehiculo(self, v):
        def doc(campo, label):
            if campo in v._fields:
                return {'label': label, 'ok': bool(v[campo])}
        documentos = [d for d in (
            doc('soat_attachment', 'SOAT'),
            doc('tarjeta_propiedad_attachment', 'Tarjeta de propiedad'),
            doc('contrato_attachment', 'Contrato'),
            doc('chip_gnv_attachment', 'Chip GNV'),
        ) if d]
        g = lambda c: v[c] if c in v._fields else False
        acciones = [accion_abrir('fleet.vehicle', v.id, 'Editar vehículo', 'fa-pencil')]
        if self._metodo('fleet.vehicle', 'action_print_acta_vehicular'):
            acciones.append(accion_metodo('fleet.vehicle', v.id, 'action_print_acta_vehicular', 'Acta vehicular', 'fa-print'))
        if self._metodo('fleet.vehicle', 'action_print_contrato_tvs'):
            acciones.append(accion_metodo('fleet.vehicle', v.id, 'action_print_contrato_tvs', 'Contrato', 'fa-print'))
        return {
            'key': 'vehiculo', 'titulo': 'Vehículo', 'icon': 'fa-motorcycle',
            'campos': self._campos(
                self._campo('Placa', v.license_plate),
                self._campo('Marca', v.brand_id.name if 'brand_id' in v._fields else False),
                self._campo('Modelo', v.model_id.name),
                self._campo('Año', g('model_year')),
                self._campo('Color', g('color')),
                self._campo('Chasis', v.vin_sn),
                self._campo('Motor', g('x_motor_sn')),
                self._campo('Estado', v.state_id.name),
                self._campo('Fecha de entrega', g('fecha_entrega') and fields.Date.to_string(g('fecha_entrega'))),
                self._campo('Kilometraje (GPS)', g('traccar_km_actual') and '%s km' % '{:,.0f}'.format(g('traccar_km_actual'))),
            ),
            'documentos': documentos,
            'acciones': acciones,
        }

    def _seccion_cliente(self, v, cliente):
        if not cliente:
            return {'key': 'cliente', 'titulo': 'Cliente', 'icon': 'fa-user',
                    'vacio': 'Este vehículo no tiene cliente asignado.',
                    'acciones': [accion_abrir('fleet.vehicle', v.id, 'Asignar conductor', 'fa-user-plus')]}
        partner = self.env['res.partner'].browse(cliente['id'])
        acciones = [accion_abrir('res.partner', partner.id, 'Ver contacto', 'fa-user')]
        digitos = re.sub(r'\D', '', cliente['telefono'] or '')
        if len(digitos) == 9:
            digitos = '51' + digitos
        if len(digitos) >= 11:
            acciones.append(accion_url('https://wa.me/%s' % digitos, 'WhatsApp', 'fa-whatsapp'))
        if cliente['telefono']:
            acciones.append(accion_url('tel:%s' % cliente['telefono'], 'Llamar', 'fa-phone'))
        return {
            'key': 'cliente', 'titulo': 'Cliente', 'icon': 'fa-user',
            'campos': self._campos(
                self._campo('Nombre', partner.name),
                self._campo('Documento', partner.vat),
                self._campo('Teléfono', cliente['telefono']),
                self._campo('Correo', partner.email),
                self._campo('Dirección', partner.contact_address and partner.contact_address.replace('\n', ', ').strip(', ')),
            ),
            'acciones': acciones,
        }

    # --- Deuda (adt_comercial) --------------------------------------------
    # Las operaciones replican las condiciones de visibilidad de los botones
    # del formulario de cuenta (view_comercial_cuentas.xml), con dos ajustes
    # validados contra el código:
    #   * "Pagar mora" solo si hay mora REGISTRADA pendiente en los pagos: el
    #     asistente adt.pagar.mora.wizard falla cuando la mora es solo la
    #     calculada en vivo (cuota vencida sin pagos).
    #   * No se ofrece "Pagar moras" de la cuenta (adt.moras.wizard): escribe
    #     sobre campos calculados no almacenados y el pago no persiste.

    def _mora_registrada(self, cuota):
        """Mora pendiente guardada en los pagos (misma regla que la cascada)."""
        return round(sum(max(0.0, (p.mora or 0.0) - (p.mora_pagado or 0.0))
                         for p in cuota.payment_ids
                         if (p.mora or 0.0) > 0 and p.mora_state == 'pending'), 2)

    def _deuda_cancelacion(self, cuenta, hoy):
        """(capital, mora) para cancelar hoy, con la lógica del asistente
        "Cancelar crédito" para que el número coincida con lo que se cobrará."""
        if 'adt.cancelar.credito.wizard' not in self.env:
            return None
        try:
            asistente = self.env['adt.cancelar.credito.wizard'].new({'cuenta_id': cuenta.id, 'payment_date': hoy})
            _cantidad, capital, mora = asistente._deuda()
            return capital, mora
        except Exception:  # la sección no debe caerse por un cálculo auxiliar
            _logger.exception('Flota 360: no se pudo calcular la deuda de cancelación de %s', cuenta.display_name)
            return None

    def _estado_cuota(self, q, hoy):
        if q.state == 'anulada':
            return 'anulada', 'Anulada', 'neutral'
        if q.state == 'pagado':
            return 'pagada', 'Pagada', 'ok'
        if q.fecha_cronograma and q.fecha_cronograma < hoy:
            return 'vencida', 'Vencida', 'critico'
        if q.state == 'a_cuenta':
            return 'a_cuenta', 'A cuenta', 'atencion'
        return 'por_vencer', 'Por vencer', 'neutral'

    def _acciones_cuota(self, q, mora_registrada):
        M = 'adt.comercial.cuotas'
        abierta = q.state not in ('pagado', 'anulada')
        principal, mas = [], []
        if abierta and self._metodo(M, 'action_register_payment'):
            principal.append(accion_metodo(M, q.id, 'action_register_payment', 'Pagar', 'fa-money', primaria=True))
        if mora_registrada > 0 and self._metodo(M, 'action_pagar_mora'):
            principal.append(accion_metodo(M, q.id, 'action_pagar_mora', 'Pagar mora', 'fa-money'))
        if abierta and self._metodo(M, 'action_editar_mora'):
            mas.append(accion_metodo(M, q.id, 'action_editar_mora', 'Editar mora', 'fa-pencil'))
        if q.state != 'anulada' and self._metodo(M, 'registrar_observacion'):
            mas.append(accion_metodo(M, q.id, 'registrar_observacion', 'Agregar observación', 'fa-comment-o'))
        if 'voucher_image_urls' in q._fields and q.voucher_image_urls and self._metodo(M, 'action_open_image_gallery'):
            mas.append(accion_metodo(M, q.id, 'action_open_image_gallery', 'Ver comprobantes', 'fa-picture-o'))
        mas.append(accion_abrir(M, q.id, 'Abrir cuota'))
        if q.state in ('pagado', 'a_cuenta') and self._metodo(M, 'action_delete_payment'):
            mas.append(accion_metodo(M, q.id, 'action_delete_payment', 'Eliminar pagos de la cuota', 'fa-trash',
                                     peligro=True))
        if self._metodo(M, 'action_eliminar_cuota'):
            mas.append(accion_metodo(M, q.id, 'action_eliminar_cuota', 'Eliminar cuota', 'fa-trash', peligro=True))
        return principal, mas

    def _acciones_cuenta(self, c):
        M = 'adt.comercial.cuentas'
        user = self.env.user
        principal, mas = [], []
        if c.state == 'borrador' and self._metodo(M, 'aprobar_cuenta'):
            principal.append(accion_metodo(M, c.id, 'aprobar_cuenta', 'Aprobar cuenta', 'fa-check', primaria=True,
                                           confirmar='¿Aprobar la cuenta? Se generará el cronograma de cuotas.'))
        if c.state == 'en_curso' and self._metodo(M, 'action_cancelar_credito'):
            principal.append(accion_metodo(M, c.id, 'action_cancelar_credito', 'Pago en cascada / cancelar',
                                           'fa-money', primaria=True))
        if c.state == 'en_curso' and self._metodo(M, 'refinanciar_cuotas'):
            principal.append(accion_metodo(M, c.id, 'refinanciar_cuotas', 'Refinanciar', 'fa-refresh'))

        if self.env.ref('adt_comercial.reporte_cronograma', raise_if_not_found=False):
            mas.append(accion_metodo('adt.flota360', c.id, 'imprimir_cronograma', 'Imprimir cronograma', 'fa-print',
                                     args=[c.id]))
        if self._metodo(M, 'action_ver_contrato'):
            mas.append(accion_metodo(M, c.id, 'action_ver_contrato', 'Contrato', 'fa-file-pdf-o'))
        if c.state not in ('borrador', 'cancelado') and self._metodo(M, 'agregar_mora'):
            mas.append(accion_metodo(M, c.id, 'agregar_mora', 'Agregar cuota / cargo', 'fa-plus'))
        if c.state != 'cancelado' and self._metodo(M, 'action_cronograma_tramos'):
            mas.append(accion_metodo(M, c.id, 'action_cronograma_tramos', 'Cronograma por tramos', 'fa-calendar'))
        mas.append(accion_abrir(M, c.id, 'Abrir cuenta'))
        if c.state == 'en_curso' and user.has_group('adt_comercial.group_access_adt_comercial_recuperar'):
            mas.append(accion_metodo(M, c.id, 'recuperar_vehiculo', 'Recuperar vehículo', 'fa-undo', peligro=True,
                                     confirmar='¿Recuperar el vehículo? La cuenta pasará a Cancelado.'))
        if c.state == 'cancelado' and user.has_group('adt_comercial.group_access_adt_comercial_restablecer'):
            mas.append(accion_metodo(M, c.id, 'restablecer_vehiculo', 'Restablecer cuenta', 'fa-repeat',
                                     confirmar='¿Restablecer la cuenta a En curso?'))
        if c.state not in ('borrador', 'cancelado') and self._metodo(M, 'cancelar_cuenta'):
            mas.append(accion_metodo(M, c.id, 'cancelar_cuenta', 'Anular cuenta', 'fa-ban', peligro=True,
                                     confirmar='¿Anular la cuenta? Se marcará como Cancelada y el vehículo quedará disponible.'))
        return principal, mas

    def _historial(self, record, limite=25):
        eventos = []
        for m in record.message_ids[:limite]:
            texto = html2plaintext(m.body or '').strip()
            cambios = []
            for t in m.tracking_value_ids:
                antes = (t.get_old_display_value() or [''])[0]
                despues = (t.get_new_display_value() or [''])[0]
                cambios.append('%s: %s → %s' % (t.field_desc, antes or '—', despues or '—'))
            if not texto and not cambios:
                continue
            eventos.append({
                'fecha': fields.Datetime.to_string(m.date),
                'autor': m.author_id.name or '',
                'texto': texto[:600],
                'cambios': cambios,
            })
        return eventos

    def _seccion_cuentas(self, v, hoy):
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id')
        if Cuenta is None:
            return None
        cuentas = Cuenta.search([('vehiculo_id', '=', v.id)], order='id desc')
        # La cuenta vigente primero.
        cuentas = cuentas.sorted(lambda c: c.state not in ('en_curso', 'aprobado', 'borrador'))
        puede_pagos = self.env['account.payment'].check_access_rights('read', raise_exception=False)
        Pend = self._modelo('adt.comercial.cuotas.pendientes', 'cuota_id', 'estado')

        resultado = []
        for c in cuentas:
            todas = c.cuota_ids.sorted(lambda q: (q.fecha_cronograma or hoy, q.parent_sort_id, q.id))
            cuotas_capital = todas.filtered(lambda q: q.type == 'cuota')

            filas, vencido, mora_total, mora_registrada_total = [], 0.0, 0.0, 0.0
            dias_atraso, proxima = 0, None
            for q in todas:
                grupo, estado, nivel = self._estado_cuota(q, hoy)
                saldo = q.saldo if grupo not in ('pagada', 'anulada') else 0.0
                mora = (q.mora_pendiente or 0.0) if grupo != 'anulada' else 0.0
                mora_reg = self._mora_registrada(q)
                mora_total += mora
                mora_registrada_total += mora_reg
                if grupo == 'vencida':
                    vencido += saldo
                    dias_atraso = max(dias_atraso, (hoy - q.fecha_cronograma).days)
                elif grupo in ('por_vencer', 'a_cuenta') and proxima is None:
                    proxima = q

                pagos = []
                if puede_pagos:
                    for p in q.payment_ids.sorted('date', reverse=True):
                        pagos.append({
                            'id': p.id,
                            'fecha': fields.Date.to_string(p.date) if p.date else '',
                            'monto': p.amount,
                            'ref': p.ref or '',
                            'diario': p.journal_id.name or '',
                            'mora': p.mora or 0.0,
                            'mora_estado': 'Pagada' if p.mora_state == 'paid' else (
                                'Parcial' if (p.mora_pagado or 0) > 0 else 'Pendiente') if p.mora else '',
                        })
                observaciones = [{
                    'fecha': fields.Date.to_string(o.fecha) if o.fecha else '',
                    'texto': o.comentario or '',
                    'adjuntos': len(o.attachment_ids),
                } for o in q.observacion_ids.sorted('id', reverse=True)]
                reportes = []
                if Pend is not None:
                    for r in q.cuota_pendiente_ids.filtered(lambda r: r.estado == 'PENDIENTE_VALIDAR'):
                        reportes.append(self._reporte_app(r, q))

                principal, mas = self._acciones_cuota(q, mora_reg)
                filas.append({
                    'id': q.id,
                    'nombre': q.name or '',
                    'subcuota': bool(q.parent_id),
                    'tipo': 'Cargo' if q.type == 'mora' else '',
                    'fecha': fields.Date.to_string(q.fecha_cronograma) if q.fecha_cronograma else '',
                    'monto': q.monto,
                    'pagado': max(q.monto - (q.saldo or 0.0), 0.0) if grupo != 'anulada' else 0.0,
                    'saldo': saldo,
                    'mora': mora,
                    'mora_dias': q.mora_dias or 0,
                    'mora_registrada': mora_reg,
                    'mora_manual': bool(q.mora_manual),
                    'grupo': grupo, 'estado': estado, 'nivel': nivel,
                    'pago_fecha': q.real_date or (pagos and pagos[0]['fecha']) or '',
                    'pago_ref': q.numero_operacion or (pagos and pagos[0]['ref']) or '',
                    'pagos': pagos,
                    'observaciones': observaciones,
                    'reportes': reportes,
                    'acciones': principal,
                    'mas': mas,
                })

            pagadas = cuotas_capital.filtered(lambda q: q.state == 'pagado')
            capital = sum(f['saldo'] for f in filas)
            cancelacion = self._deuda_cancelacion(c, hoy) if c.state == 'en_curso' else None
            if cancelacion:
                cancelar_hoy, cancelar_nota = sum(cancelacion), 'Según asistente de cancelación'
            else:
                cancelar_hoy, cancelar_nota = capital + mora_total, 'Capital pendiente + mora'

            pagos_cuenta = sorted((dict(p, cuota=f['nombre']) for f in filas for p in f['pagos']),
                                  key=lambda p: (p['fecha'], p['id']), reverse=True)
            vencidas_n = sum(1 for f in filas if f['grupo'] == 'vencida')
            nivel = 'critico' if vencidas_n >= CUOTAS_CRITICAS else ('atencion' if vencidas_n or mora_total else (
                'ok' if c.state in ('en_curso', 'aprobado', 'pagado') else 'neutral'))
            principal, mas = self._acciones_cuenta(c)

            resultado.append({
                'id': c.id,
                'referencia': c.reference_no or c.display_name,
                'estado': self._etiqueta(c, 'state', c.state),
                'state': c.state,
                'nivel': nivel,
                'detalle': ' · '.join(filter(None, [
                    c.partner_id.name,
                    'tipo_financiera_id' in c._fields and c.tipo_financiera_id.display_name or '',
                    self._etiqueta(c, 'periodicidad', c.periodicidad),
                    c.fecha_desembolso and 'Desembolso %s' % c.fecha_desembolso.strftime('%d/%m/%Y') or '',
                    'user_id' in c._fields and c.user_id.name and 'Asesor %s' % c.user_id.name or '',
                ])),
                'cifras': {
                    'al_dia': vencido + mora_total,
                    'vencidas': vencidas_n,
                    'cancelar_hoy': cancelar_hoy,
                    'cancelar_nota': cancelar_nota,
                    'capital': capital,
                    'mora': mora_total,
                    'mora_registrada': mora_registrada_total,
                    'dias_atraso': dias_atraso,
                    'cuota': c.monto_cuota,
                    'financiado': c.monto_fraccionado or sum(cuotas_capital.mapped('monto')),
                    'pagado': sum(f['pagado'] for f in filas),
                    'pagadas': len(pagadas),
                    'total_cuotas': len(cuotas_capital.filtered(lambda q: q.state != 'anulada')),
                },
                'proxima': proxima and {
                    'nombre': proxima.name, 'monto': proxima.saldo,
                    'fecha': fields.Date.to_string(proxima.fecha_cronograma),
                    'dias': (proxima.fecha_cronograma - hoy).days,
                },
                'ultimo_pago': pagos_cuenta[:1] and pagos_cuenta[0],
                'cuotas': filas,
                'pagos': pagos_cuenta,
                'reportes': [r for f in filas for r in f['reportes']],
                'historial': self._historial(c),
                'acciones': principal,
                'mas': mas,
                'recuperado': bool(c.recuperado),
                'captura_prioridad': self._etiqueta(c, 'captura_prioridad', c.captura_prioridad)
                if 'captura_prioridad' in c._fields else '',
            })
        return {
            'key': 'cuentas', 'titulo': 'Deuda', 'icon': 'fa-credit-card',
            'deuda': resultado,
            'vacio': 'El vehículo no tiene cuentas registradas.',
            'acciones': [accion_metodo('fleet.vehicle', v.id, 'action_new_cuenta', 'Nueva cuenta', 'fa-plus')]
            if self._metodo('fleet.vehicle', 'action_new_cuenta') else [],
        }

    def _reporte_app(self, r, cuota):
        """Pago informado desde la app (adt.comercial.cuotas.pendientes) por validar."""
        acciones = []
        if cuota.state not in ('pagado', 'anulada'):
            acciones.append(accion_metodo('adt.flota360', r.id, 'pagar_reporte_app', 'Registrar pago con estos datos',
                                          'fa-money', primaria=True, args=[r.id]))
        acciones.append(accion_abrir(r._name, r.id, 'Ver reporte'))
        return {
            'id': r.id,
            'cuota': cuota.name or '',
            'fecha': fields.Datetime.to_string(r.fecha) if r.fecha else '',
            'monto': r.monto_cuota,
            'operacion': r.numero_operacion_cuota or '',
            'mora': r.monto_mora,
            'operacion_mora': r.numero_operacion_mora or '',
            'comentario': r.comentario or '',
            'comprobantes': r.comprobante_count,
            'acciones': acciones,
        }

    # --- Servicios llamados desde la vista ---------------------------------

    @api.model
    def imprimir_cronograma(self, cuenta_id):
        cuenta = self.env['adt.comercial.cuentas'].browse(cuenta_id).exists()
        cuenta.check_access_rule('read')
        return self.env.ref('adt_comercial.reporte_cronograma').report_action(cuenta)

    @api.model
    def pagar_reporte_app(self, pendiente_id):
        """Abre el asistente de pago de la cuota con el monto y la operación
        informados desde la app. No marca el reporte como validado."""
        reporte = self.env['adt.comercial.cuotas.pendientes'].browse(pendiente_id).exists()
        reporte.check_access_rule('read')
        cuota = reporte.cuota_id
        accion = cuota.action_register_payment()
        accion['context'] = dict(accion.get('context') or {},
                                 default_amount=min(reporte.monto_cuota or cuota.saldo, cuota.saldo),
                                 default_communication=reporte.numero_operacion_cuota or cuota.name)
        return accion

    def _seccion_papeletas(self, v, hoy):
        Papeleta = self._modelo('adt.papeleta', 'vehicle_id')
        if Papeleta is None:
            return None
        papeletas = Papeleta.search([('vehicle_id', '=', v.id)])
        papeletas = papeletas.sorted(lambda p: (p.state == 'pagado', p.fecha_vencimiento_final or hoy))
        items = []
        for p in papeletas:
            vencida = p.state != 'pagado' and p.fecha_vencimiento_final and p.fecha_vencimiento_final < hoy
            if p.state == 'pagado':
                nivel = 'ok'
            elif vencida:
                nivel = 'critico'
            else:
                nivel = 'atencion'
            acciones = []
            if p.state != 'pagado' and self._metodo('adt.papeleta', 'action_mark_pagado'):
                acciones.append(accion_metodo('adt.papeleta', p.id, 'action_mark_pagado', 'Marcar pagada', 'fa-check',
                                              confirmar='¿Marcar la papeleta %s como pagada?' % p.name, primaria=True))
            acciones.append(accion_abrir('adt.papeleta', p.id))
            items.append({
                'titulo': 'Papeleta %s' % p.name,
                'subtitulo': (p.detalle or '').strip()[:120],
                'badge': {'texto': 'Vencida' if vencida else self._etiqueta(p, 'state', p.state), 'nivel': nivel},
                'kpis': [
                    {'label': 'Monto', 'monto': p.monto},
                    {'label': 'Fecha', 'texto': fields.Date.to_string(p.fecha_papeleta) if p.fecha_papeleta else '—'},
                    {'label': 'Vence', 'texto': fields.Date.to_string(p.fecha_vencimiento_final) if p.fecha_vencimiento_final else '—',
                     'nivel': nivel if p.state != 'pagado' else False},
                ],
                'nota': p.texto_alerta if p.state != 'pagado' and 'texto_alerta' in p._fields else False,
                'acciones': acciones,
            })
        return {
            'key': 'papeletas', 'titulo': 'Papeletas', 'icon': 'fa-file-text-o',
            'items': items,
            'vacio': 'Sin papeletas registradas.',
            'acciones': [accion_metodo('fleet.vehicle', v.id, 'action_new_adt_papeleta', 'Registrar papeleta', 'fa-plus')]
            if self._metodo('fleet.vehicle', 'action_new_adt_papeleta') else [],
        }

    def _seccion_gps(self, v, hoy):
        if 'traccar_credential_ids' not in v._fields:
            return None
        cred = v.traccar_credential_active_id
        acciones = []
        if not cred:
            if self._metodo('fleet.vehicle', 'action_open_traccar_register_wizard'):
                acciones.append(accion_metodo('fleet.vehicle', v.id, 'action_open_traccar_register_wizard',
                                              'Registrar en Traccar', 'fa-plus', primaria=True))
            return {'key': 'gps', 'titulo': 'GPS / Traccar', 'icon': 'fa-map-marker',
                    'vacio': 'El vehículo no tiene un equipo GPS registrado en Traccar.', 'acciones': acciones}
        acciones.append(accion_metodo('fleet.vehicle', v.id, 'action_refresh_traccar_status',
                                      'Actualizar ubicación', 'fa-refresh', primaria=True))
        if cred.gps_maps_url:
            acciones.append(accion_url(cred.gps_maps_url, 'Ver en mapa', 'fa-map'))
        acciones.append(accion_abrir('adt.traccar.device.credential', cred.id, 'Credencial', 'fa-key'))
        status = cred.gps_status or 'unknown'
        return {
            'key': 'gps', 'titulo': 'GPS / Traccar', 'icon': 'fa-map-marker',
            'gps': {
                'status': status,
                'estado': self._etiqueta(cred, 'gps_status', status),
                'ultimo': fields.Datetime.to_string(cred.gps_last_update) if cred.gps_last_update else False,
                'refrescado': fields.Datetime.to_string(cred.gps_status_refreshed_at) if cred.gps_status_refreshed_at else False,
                'direccion': cred.gps_address or '',
                'lat': cred.gps_latitude, 'lon': cred.gps_longitude,
            },
            'kpis': [
                {'label': 'Velocidad', 'texto': '%.0f km/h' % (cred.gps_speed_kmh or 0)},
                {'label': 'Batería', 'texto': '%.0f %%' % cred.gps_battery_level if cred.gps_battery_level else '—'},
                {'label': 'Km', 'texto': '{:,.0f}'.format(v.traccar_km_actual) if 'traccar_km_actual' in v._fields and v.traccar_km_actual else '—'},
                {'label': 'IMEI', 'texto': cred.imei or '—'},
            ],
            'acciones': acciones,
        }

    def _seccion_placa(self, v, hoy):
        items = []
        Tramite = self._modelo('adt.tramite.placa', 'vehicle_id')
        if Tramite is not None:
            t = Tramite.search([('vehicle_id', '=', v.id)], order='id desc', limit=1)
            if t:
                acciones = []
                if t.state == 'pendiente' and self._metodo('adt.tramite.placa', 'action_iniciar'):
                    acciones.append(accion_metodo('adt.tramite.placa', t.id, 'action_iniciar', 'Iniciar trámite',
                                                  'fa-play', confirmar='¿Iniciar el trámite de placa?', primaria=True))
                acciones.append(accion_abrir('adt.tramite.placa', t.id, 'Abrir trámite'))
                items.append({
                    'titulo': 'Trámite %s' % t.name,
                    'subtitulo': t.motivo_observacion if t.state == 'observado' and 'motivo_observacion' in t._fields else '',
                    'badge': {'texto': self._etiqueta(t, 'state', t.state),
                              'nivel': {'observado': 'atencion', 'finalizado': 'ok', 'historial': 'ok'}.get(t.state, 'neutral')},
                    'kpis': [
                        {'label': 'N° placa', 'texto': t.num_placa or '—'},
                        {'label': 'Días de trámite', 'texto': '%.1f' % t.dias_tramite if t.dias_tramite else '—'},
                        {'label': 'Observaciones', 'texto': str(t.cant_observaciones or 0)},
                    ],
                    'acciones': acciones,
                })
        Tracking = self._modelo('adt.moto.tracking', 'vehicle_id')
        if Tracking is not None:
            tr = Tracking.search([('vehicle_id', '=', v.id)], limit=1)
            if tr:
                items.append({
                    'titulo': 'Entrega %s' % tr.name,
                    'subtitulo': 'Etapa: %s' % tr.etapa_id.display_name if tr.etapa_id else '',
                    'badge': {'texto': self._etiqueta(tr, 'estado_global', tr.estado_global),
                              'nivel': 'atencion' if tr.demorado else ('ok' if tr.estado_global == 'entregado' else 'neutral')},
                    'kpis': [
                        {'label': 'Días en etapa', 'texto': '%.1f' % (tr.dias_etapa or 0)},
                        {'label': 'Días totales', 'texto': '%.1f' % (tr.dias_totales or 0)},
                        {'label': 'Demorado', 'texto': 'Sí' if tr.demorado else 'No', 'nivel': 'atencion' if tr.demorado else False},
                    ],
                    'acciones': [accion_abrir('adt.moto.tracking', tr.id, 'Abrir tracking')],
                })
        if Tramite is None and Tracking is None:
            return None
        return {'key': 'placa', 'titulo': 'Placa y entrega', 'icon': 'fa-id-card-o', 'items': items,
                'vacio': 'Sin trámite de placa ni seguimiento de entrega.'}

    def _seccion_capturas(self, v, hoy):
        Captura = self._modelo('adt.captura.record', 'vehicle_id')
        if Captura is None:
            return None
        items = []
        for c in Captura.search([('vehicle_id', '=', v.id)], order='id desc', limit=10):
            activa = c.state in CAPTURA_ACTIVA
            acciones = []
            if activa and c.payment_state == 'pendiente' and self._metodo('adt.captura.record', 'action_registrar_pago'):
                acciones.append(accion_metodo('adt.captura.record', c.id, 'action_registrar_pago', 'Registrar pago',
                                              'fa-money', primaria=True))
            acciones.append(accion_abrir('adt.captura.record', c.id))
            items.append({
                'titulo': c.name,
                'subtitulo': self._etiqueta(c, 'capture_type', c.capture_type),
                'badge': {'texto': self._etiqueta(c, 'state', c.state), 'nivel': 'critico' if activa else 'neutral'},
                'kpis': [
                    {'label': 'Intervención', 'monto': c.intervention_fee},
                    {'label': 'Pago', 'texto': self._etiqueta(c, 'payment_state', c.payment_state),
                     'nivel': 'atencion' if activa and c.payment_state == 'pendiente' else False},
                    {'label': 'Días de mora', 'texto': str(c.dias_mora or 0)},
                ],
                'acciones': acciones,
            })
        return {
            'key': 'capturas', 'titulo': 'Capturas', 'icon': 'fa-lock', 'items': items,
            'vacio': 'Sin capturas registradas.',
            'acciones': [accion_metodo('fleet.vehicle', v.id, 'action_new_adt_captura', 'Registrar captura', 'fa-plus')]
            if self._metodo('fleet.vehicle', 'action_new_adt_captura') else [],
        }

    # --- Expediente (adt_expedientes) --------------------------------------
    # El expediente solo se relaciona con el cliente (cliente_id). Aquí se vincula
    # al vehículo a través del cliente de turno: el conductor asignado o, si no
    # hay, el socio de la cuenta vigente. Si el vehículo cambia de manos, la ficha
    # pasa a mostrar los expedientes del nuevo cliente.

    def _clientes_de_turno(self, v, hoy):
        """Socios a considerar: el cliente de turno y, si es distinto, el socio de la cuenta vigente."""
        cuentas = self._lote_cuentas([v.id], hoy) or {}
        clientes = self._lote_clientes(v.read(['driver_id']), cuentas)
        pids = [clientes[v.id]['id']] if v.id in clientes else []
        cuenta = cuentas.get(v.id)
        if cuenta and cuenta['state'] in ('en_curso', 'aprobado', 'borrador') and cuenta['partner_id'] not in pids:
            pids.append(cuenta['partner_id'])
        return pids

    def _documentos_expediente(self, e):
        """Estado de cada documento: aceptado, rechazado (con observación) o sin cargar."""
        cargados = set(self.env['ir.attachment'].sudo().search(
            [('res_model', '=', e._name), ('res_id', '=', e.id), ('res_field', '=like', 'foto_%')]
        ).mapped('res_field'))
        documentos = []
        for nombre, campo in e._fields.items():
            if not nombre.startswith('estado_') or campo.type != 'selection':
                continue
            clave = nombre[len('estado_'):]                     # foto_dni, direccion, referencias…
            fotos = [f for f in e._fields if f.startswith(clave) and e._fields[f].type == 'binary'] \
                if clave.startswith('foto_') else []
            valor = e[nombre]
            obs_campo = 'obs_' + clave
            obs = e[obs_campo] if obs_campo in e._fields else ''
            if fotos:
                etiqueta = (e._fields[fotos[0]].string or clave).split(' - ')[0]
                etiqueta = etiqueta[5:] if etiqueta.lower().startswith('foto ') else etiqueta
                if not any(f in cargados for f in fotos):
                    estado = 'falta'
                else:
                    estado = 'rechazado' if valor == 'rechazado' else 'aceptado'
            elif valor == 'rechazado':
                etiqueta, estado = clave.replace('_', ' ').capitalize(), 'rechazado'
            else:
                continue
            etiqueta = ' '.join(w.upper() if w.lower() in SIGLAS else w for w in etiqueta.split(' '))
            documentos.append({'label': etiqueta[:1].upper() + etiqueta[1:], 'estado': estado, 'obs': obs or ''})
        orden = {'rechazado': 0, 'falta': 1, 'aceptado': 2}
        return sorted(documentos, key=lambda d: (orden[d['estado']], d['label']))

    def _acciones_expediente(self, e):
        M = 'adt.expediente'
        principal = [accion_abrir(M, e.id, 'Abrir expediente')]
        if self._metodo(M, 'action_print_expediente_pdf'):
            principal.append(accion_metodo(M, e.id, 'action_print_expediente_pdf', 'Generar PDF', 'fa-file-pdf-o'))
        mas = []
        for metodo, estado, label, icono in EXPEDIENTE_ESTADOS:
            if e.state != estado and self._metodo(M, metodo):
                mas.append(accion_metodo(M, e.id, metodo, label, icono,
                                         confirmar='¿%s? Se enviará una notificación push de cambio de estado.' % label))
        if e.state != 'rechazado' and self._metodo(M, 'action_rechazar'):
            mas.append(accion_metodo(M, e.id, 'action_rechazar', 'Rechazar expediente', 'fa-ban', peligro=True,
                                     confirmar='Se abrirá el formulario de rechazo para indicar el motivo.'))
        return principal, mas

    def _seccion_expediente(self, v, hoy):
        Expediente = self._modelo('adt.expediente', 'cliente_id', 'state')
        if Expediente is None:
            return None
        pids = self._clientes_de_turno(v, hoy)
        nuevo = []
        if pids:
            nuevo = [accion_abrir('adt.expediente', False, 'Nuevo expediente', 'fa-plus',
                                  contexto={'default_cliente_id': pids[0]})]
        if not pids:
            return {'key': 'expediente', 'titulo': 'Expediente', 'icon': 'fa-folder-open-o', 'items': [],
                    'vacio': 'El vehículo no tiene cliente de turno; asigna un conductor para ver su expediente.'}
        items = []
        expedientes = Expediente.search([('cliente_id', 'in', pids)], order='fecha desc, id desc')
        for i, e in enumerate(expedientes):
            documentos = self._documentos_expediente(e)
            rechazados = [d for d in documentos if d['estado'] == 'rechazado']
            cargados = [d for d in documentos if d['estado'] != 'falta']
            principal, mas = self._acciones_expediente(e)
            vehiculo = self._etiqueta(e, 'vehiculo', e.vehiculo) if 'vehiculo' in e._fields else ''
            items.append({
                'titulo': 'Expediente del %s' % (e.fecha.strftime('%d/%m/%Y') if e.fecha else '—')
                          + ('' if i else ' · vigente'),
                'subtitulo': ' · '.join(filter(None, [
                    e.cliente_id.name if len(pids) > 1 else '',
                    e.asesora_id.name and 'Asesora %s' % e.asesora_id.name,
                    vehiculo and 'Solicita %s' % vehiculo,
                ])),
                'badge': {'texto': self._etiqueta(e, 'state', e.state) or 'Sin estado',
                          'nivel': EXPEDIENTE_NIVEL.get(e.state, 'neutral')},
                'kpis': [
                    {'label': 'Documentos cargados', 'texto': str(len(cargados))},
                    {'label': 'Rechazados', 'texto': str(len(rechazados)),
                     'nivel': 'critico' if rechazados else False},
                ] + ([{'label': 'Fecha de rechazo', 'texto': e.fecha_rechazo.strftime('%d/%m/%Y')}]
                     if e.state == 'rechazado' and e.fecha_rechazo else []),
                'nota': 'Motivo de rechazo: %s' % e.motivo_rechazo if e.state == 'rechazado' and e.motivo_rechazo else False,
                'documentos': documentos,
                'acciones': principal,
                'mas': mas,
            })
        return {
            'key': 'expediente', 'titulo': 'Expediente', 'icon': 'fa-folder-open-o',
            'items': items,
            'vacio': 'El cliente de turno no tiene expedientes registrados.',
            'acciones': nuevo,
        }

    def _seccion_taller(self, v, hoy):
        Orden = self._modelo('maintenance.work.order', 'vehicle_id')
        Regla = self._modelo('adt.mantenimiento.vehicle.rule.state', 'vehicle_id', 'estado')
        if Orden is None and Regla is None:
            return None
        items = []
        if Orden is not None:
            ordenes = Orden.search([('vehicle_id', '=', v.id)], order='id desc', limit=8)
            for o in ordenes.sorted(lambda o: o.state == 'done'):
                items.append({
                    'titulo': o.name,
                    'subtitulo': (o.entry_reason or '').strip()[:120],
                    'badge': {'texto': self._etiqueta(o, 'state', o.state),
                              'nivel': {'blocked': 'atencion', 'done': 'ok'}.get(o.state, 'info')},
                    'kpis': [
                        {'label': 'Inicio', 'texto': fields.Datetime.to_string(o.start_date)[:10] if o.start_date else '—'},
                        {'label': 'Km', 'texto': '{:,.0f}'.format(o.mileage) if o.mileage else '—'},
                        {'label': 'Total', 'monto': o.total_amount},
                    ],
                    'acciones': [accion_abrir('maintenance.work.order', o.id)],
                })
        if Regla is not None:
            for r in Regla.search([('vehicle_id', '=', v.id), ('estado', '=', 'campana_activa')]):
                items.append({
                    'titulo': 'Mantenimiento preventivo: %s' % r.regla_id.display_name,
                    'badge': {'texto': self._etiqueta(r, 'estado', r.estado), 'nivel': 'atencion'},
                    'acciones': [accion_abrir(r._name, r.id)],
                })
        return {
            'key': 'taller', 'titulo': 'Taller y mantenimiento', 'icon': 'fa-wrench', 'items': items,
            'vacio': 'Sin órdenes de taller ni mantenimientos pendientes.',
            'acciones': [accion_metodo('fleet.vehicle', v.id, 'action_new_work_order', 'Nueva orden', 'fa-plus')]
            if self._metodo('fleet.vehicle', 'action_new_work_order') else [],
        }
