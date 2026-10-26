# -*- coding: utf-8 -*-
"""Flota 360: datos para la vista unificada del vehículo.

Todo se calcula en lote (una consulta por módulo, no por vehículo) para que
el buscador responda rápido aun recorriendo toda la flota. Cada módulo es
opcional: si su modelo no está instalado o el usuario no tiene acceso, su
información simplemente no aparece.
"""
import base64
import logging
import re
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.osv import expression
from odoo.tools import html2plaintext
from odoo.tools.mimetypes import guess_mimetype

_logger = logging.getLogger(__name__)

# Filtros rápidos del buscador (orden de los chips).
FILTROS = [
    ('todos', 'Todos'),
    ('atencion', 'Requieren atención'),
    ('mora', 'Cuotas vencidas'),
    ('papeletas', 'Papeletas pendientes'),
    ('capturas', 'Capturados'),
    ('sin_expediente', 'Sin expediente'),
    ('sin_doc_financiera', 'Falta documento financiera'),
    ('gps_off', 'GPS sin señal'),
    ('sin_placa', 'Sin placa'),
    ('taller', 'En taller'),
]

NIVEL_ORDEN = {'critico': 0, 'atencion': 1, 'ok': 2}
MAX_ANALISIS = 5000          # vehículos evaluados por búsqueda
CUOTAS_CRITICAS = 3          # desde cuántas cuotas vencidas es crítico
GPS_HORAS_SIN_SENAL = 24     # sin reporte del equipo por más de N horas
CUOTAS_ABIERTAS = ('pendiente', 'a_cuenta', 'retrasado')
CUENTA_VIGENTE = ('borrador', 'aprobado', 'en_curso')
SIN_CUENTA = 'sin_cuenta'  # estado de cronograma de un vehículo sin cuenta
# Grupos de la flota. Stock = moto sin dueño (driver_id vacío), el mismo criterio que el
# Dashboard de Flota (adt_dashboard_flota), para que las cifras coincidan.
GRUPOS = ('clientes', 'stock')
CAPTURA_ACTIVA = ('capturado', 'disolucion_contrato')
# Botones del formulario de la captura que la ficha puede ejecutar.
CAPTURA_BOTONES = ('action_registrar_pago', 'action_liberar', 'action_retener', 'action_recolocar',
                   'action_cancelar', 'action_ver_mantenimientos')
TALLER_ABIERTO = ('pending', 'in_progress', 'blocked')
# Estado del expediente → nivel del indicador.
EXPEDIENTE_NIVEL = {
    'completo': 'ok', 'aprobado_sin_desembolso': 'ok', 'por_revisar': 'info',
    'incompleto_expediente': 'atencion', 'incompleto_fase_final': 'atencion', 'rechazado': 'neutral',
}
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


def accion_form(clave, label, icono, res_id=False, params=None, primaria=False):
    """Formulario nativo de la vista (ver flota_360_ops: _form_<clave>)."""
    return {'tipo': 'form', 'form': clave, 'res_id': res_id, 'params': params or {},
            'label': label, 'icon': icono, 'primary': primaria}


def accion_credito(label, icono, cuenta_id=False, primaria=False):
    """Asistente de crédito: nueva cuenta con su cronograma o edición de un borrador."""
    return {'tipo': 'credito', 'cuenta_id': cuenta_id, 'label': label, 'icon': icono, 'primary': primaria}


def frase(nivel, texto, detalle=''):
    """Estado de una sección en una frase: nivel (ok/atencion/critico/info/neutral), texto y detalle."""
    return {'nivel': nivel, 'texto': texto, 'detalle': detalle or ''}


def cifra(etiqueta, valor, icono, sub='', nivel='', principal=False):
    """Una cifra de la cabecera de una sección. `valor` ya formateado."""
    return {'label': etiqueta, 'valor': valor, 'icon': icono, 'sub': sub or '', 'nivel': nivel or '', 'principal': principal}


def accion_tab(tab, label, icono='fa-angle-right'):
    return {'tipo': 'tab', 'tab': tab, 'label': label, 'icon': icono}


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
        # Solo los campos de selección tienen etiqueta; el resto (p. ej. un Char) se muestra tal cual.
        if not valor or campo not in Model._fields or Model._fields[campo].type != 'selection':
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
    def buscar(self, termino='', filtro='todos', offset=0, limit=24, financiera=None, estado=None, grupo=None):
        """grupo: 'clientes' (motos con dueño), 'stock' (sin dueño) o None = todas.
        financiera: id de la financiera de la cuenta del vehículo (en cualquier estado),
        0 = sin financiera, None = todas.
        estado: estado del cronograma de pagos de esa cuenta (borrador, aprobado, en_curso,
        cancelado, pagado o SIN_CUENTA), None = todos.
        Ambos se combinan con la búsqueda y con el filtro rápido."""
        vehiculos = self.env['fleet.vehicle'].search(self._dominio_busqueda(termino), limit=MAX_ANALISIS)
        resumenes = self._resumenes(vehiculos)
        grupos = {g: 0 for g in GRUPOS}
        for r in resumenes:
            grupos['stock' if r['stock'] else 'clientes'] += 1
        if grupo in GRUPOS:
            resumenes = [r for r in resumenes if r['stock'] == (grupo == 'stock')]
        por_financiera = [r for r in resumenes if financiera is None or r['financiera_id'] == financiera]
        por_estado = [r for r in resumenes if estado is None or r['cuenta_estado'] == estado]
        # Cada filtro cuenta con el otro aplicado, para que los números cuadren con la lista.
        financieras = self._contar_financieras(por_estado)
        estados = self._contar_estados(por_financiera)
        resumenes = [r for r in por_financiera if estado is None or r['cuenta_estado'] == estado]

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
            'financieras': financieras,
            'estados': estados,
            'grupos': grupos,
            'truncado': len(vehiculos) >= MAX_ANALISIS,
        }

    def _contar_financieras(self, resumenes):
        """Vehículos de la búsqueda por financiera de su cuenta (en cualquier estado)."""
        conteo = defaultdict(int)
        nombres = {}
        for r in resumenes:
            conteo[r['financiera_id']] += 1
            nombres[r['financiera_id']] = r['financiera'] or _('Sin financiera')
        Financiera = self._modelo('adt.comercial.financiera', 'name')
        if Financiera is not None:
            # También las financieras sin vehículos en la búsqueda, para que el filtro no cambie de forma.
            for f in Financiera.search_read([], ['name'], order='name'):
                nombres.setdefault(f['id'], f['name'])
        lista = sorted(({'id': k, 'name': v, 'n': conteo.get(k, 0)} for k, v in nombres.items() if k),
                       key=lambda f: f['name'].casefold())
        if conteo.get(0):
            lista.append({'id': 0, 'name': nombres[0], 'n': conteo[0]})
        return lista

    def _contar_estados(self, resumenes):
        """Vehículos de la búsqueda por estado del cronograma de pagos de su cuenta."""
        Cuenta = self._modelo('adt.comercial.cuentas', 'state')
        if Cuenta is None:
            return []
        conteo = defaultdict(int)
        for r in resumenes:
            conteo[r['cuenta_estado']] += 1
        lista = [{'id': k, 'name': v, 'n': conteo.get(k, 0)}
                 for k, v in Cuenta._fields['state']._description_selection(self.env)]
        if conteo.get(SIN_CUENTA):
            lista.append({'id': SIN_CUENTA, 'name': _('Sin cronograma'), 'n': conteo[SIN_CUENTA]})
        return lista

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
        con_plan = self._lote_plan_financiera(ids)

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
                self._resumen_expediente(expedientes.get(cliente['id']), modulos, alertas, filtros)
            if con_plan is not None and cuentas:
                self._resumen_financiera(cuentas.get(vid), vid in con_plan, modulos, alertas, filtros)

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
                'stock': not f.get('driver_id'),
                'modulos': modulos,
                'alertas': sorted(alertas, key=lambda a: NIVEL_ORDEN.get(a['nivel'], 3)),
                'filtros': sorted(filtros),
                # Financiera y estado del cronograma de la cuenta del vehículo (la vigente o la más
                # reciente), en cualquier estado; sin cuenta: financiera 0 y estado SIN_CUENTA.
                'financiera_id': (cuentas or {}).get(vid, {}).get('financiera_id') or 0,
                'financiera': (cuentas or {}).get(vid, {}).get('financiera') or '',
                'cuenta_estado': (cuentas or {}).get(vid, {}).get('state') or SIN_CUENTA,
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
        """Cliente = conductor del vehículo; si no tiene, el socio de su cuenta abierta.
        Una cuenta anulada o recuperada no deja cliente: solo queda en el historial."""
        pid_por_vehiculo = {}
        for f in filas:
            pid = self._id(f.get('driver_id'))
            cuenta = cuentas and cuentas.get(f['id'])
            if not pid and cuenta and cuenta['state'] in ('borrador', 'aprobado', 'en_curso'):
                pid = cuenta['partner_id']
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
        campos = [c for c in ('vehiculo_id', 'partner_id', 'state', 'reference_no', 'mora_pendiente',
                              'tipo_financiera_id') if c in Cuenta._fields]
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
            # Solo las cuentas en curso cuentan como cartera (mismo criterio que el Reporte de Cobranzas).
            dominio = [('cuenta_id', 'in', [c['id'] for c in elegida.values() if c['state'] == 'en_curso']),
                       ('state', 'in', list(CUOTAS_ABIERTAS)), ('fecha_cronograma', '<', hoy), ('saldo', '>', 0)]
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
                'mora': (c.get('mora_pendiente') or 0.0) if c['state'] == 'en_curso' else 0.0,
                'financiera': self._m2o(c.get('tipo_financiera_id')),
                'financiera_id': self._id(c.get('tipo_financiera_id')),
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

    def _lote_plan_financiera(self, ids):
        """Vehículos que ya tienen cargado el PDF del plan de pagos de la financiera."""
        if 'cf_pdf' not in self.env['fleet.vehicle']._fields:
            return None
        adjuntos = self.env['ir.attachment'].sudo().search_read([
            ('res_model', '=', 'fleet.vehicle'), ('res_id', 'in', ids), ('res_field', '=', 'cf_pdf')], ['res_id'])
        return {a['res_id'] for a in adjuntos}

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

    def _resumen_expediente(self, e, modulos, alertas, filtros):
        if not e:
            # Todo crédito empieza con el expediente del cliente: si no existe se marca.
            filtros.add('sin_expediente')
            alertas.append(self._alerta('expediente', 'atencion', _('Cliente sin expediente registrado')))
            modulos.append(self._chip('expediente', 'fa-folder-open-o', 'Expediente', 'Sin expediente', 'atencion'))
            return
        Expediente = self.env['adt.expediente']
        nivel = EXPEDIENTE_NIVEL.get(e['state'], 'neutral')
        texto = self._etiqueta(Expediente, 'state', e['state']) or 'Sin estado'
        if nivel == 'atencion':
            alertas.append(self._alerta('expediente', nivel, 'Expediente %s' % texto.lower()))
        modulos.append(self._chip('expediente', 'fa-folder-open-o', 'Expediente', texto, nivel))

    def _resumen_financiera(self, c, tiene_plan, modulos, alertas, filtros):
        # Solo aplica a la cuenta vigente financiada por una financiera.
        if not c or not c.get('financiera') or c['state'] not in CUENTA_VIGENTE or tiene_plan:
            return
        filtros.add('sin_doc_financiera')
        alertas.append(self._alerta('financiera', 'atencion',
                                    _('Falta el plan de pagos de %s') % c['financiera']))
        modulos.append(self._chip('financiera', 'fa-university', 'Financiera', 'Falta documento', 'atencion'))

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

        secciones = [self._seccion_vehiculo(vehiculo), self._seccion_documentos(vehiculo),
                     self._seccion_cliente(vehiculo, resumen['cliente'])]
        for metodo in (self._seccion_cuentas, self._seccion_rentabilidad, self._seccion_financiera,
                       self._seccion_papeletas, self._seccion_gps,
                       self._seccion_placa, self._seccion_capturas, self._seccion_taller,
                       self._seccion_expediente):
            try:
                seccion = metodo(vehiculo, hoy)
            except AccessError:
                seccion = None
            if seccion:
                secciones.append(seccion)

        resumen['secciones'] = secciones
        try:
            resumen['historial_crediticio'] = self._historial_crediticio_vehiculo(vehiculo)
        except AccessError:
            resumen['historial_crediticio'] = {'disponible': False}
        resumen['recorrido'] = self._recorrido(vehiculo, resumen, {s['key']: s for s in secciones})
        return resumen

    def _historial_crediticio_vehiculo(self, vehiculo):
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id', 'partner_id', 'cuota_ids')
        if Cuenta is None:
            return {'disponible': False}
        cuentas = Cuenta.with_context(active_test=False).search([
            ('vehiculo_id', '=', vehiculo.id), ('company_id', 'in', self.env.companies.ids),
            ('state', 'in', ['en_curso', 'pagado', 'cancelado'])], order='id')
        titulares = []
        total = 0
        for cliente in cuentas.mapped('partner_id'):
            anteriores = set()
            coincidencias = explicitos = 0
            propias = cuentas.filtered(lambda c: c.partner_id == cliente)
            for cuenta in propias:
                nombres = {re.sub(r'\s+', ' ', q.name.strip()).casefold()
                           for q in cuenta.cuota_ids if q.name and not q.parent_id}
                if anteriores.intersection(nombres):
                    coincidencias += 1
                if any(re.match(r'^cuota\s+r\.', nombre) for nombre in nombres):
                    explicitos += 1
                anteriores.update(nombres)
            detectados = max(coincidencias, explicitos)
            total += detectados
            titulares.append({'nombre': cliente.display_name, 'cuentas': len(propias),
                              'refinanciamientos': detectados})
        return {'disponible': True, 'titulares': titulares, 'duenos': len(titulares),
                'refinanciamientos': total, 'cuentas': len(cuentas)}

    # --- Recorrido del vehículo -------------------------------------------
    # Las etapas por las que pasa un vehículo financiado, en orden. Cada una
    # indica si está cumplida y, si no, qué falta y cómo resolverlo.

    def _recorrido(self, v, resumen, secciones):
        mods = {m['key']: m for m in resumen['modulos']}
        cliente = resumen['cliente']
        pasos = []

        def paso(key, titulo, nivel, texto, tab=None, accion=None, detalle=''):
            pasos.append({'key': key, 'titulo': titulo, 'nivel': nivel, 'texto': texto, 'tab': tab,
                          'accion': accion, 'detalle': detalle})

        # 1. Cliente
        if cliente:
            paso('cliente', 'Cliente', 'ok', cliente['nombre'], 'cliente', detalle=cliente.get('documento') or '')
        else:
            paso('cliente', 'Cliente', 'pendiente', 'Se asigna al crear el crédito', 'cuentas',
                 accion_credito('Crear crédito', 'fa-credit-card'))

        # 2. Expediente
        if 'expediente' in secciones:
            exp = secciones['expediente'].get('expedientes') or []
            if not cliente:
                paso('expediente', 'Expediente', 'pendiente', 'Requiere cliente', 'expediente')
            elif not exp:
                paso('expediente', 'Expediente', 'atencion', 'Sin expediente', 'expediente',
                     accion_form('expediente', 'Crear expediente', 'fa-plus', params={'cliente_id': cliente['id']}),
                     'Recomendado antes de otorgar el crédito')
            else:
                e = exp[0]
                av = e['avance']
                paso('expediente', 'Expediente', e['nivel'], e['estado'], 'expediente',
                     detalle='Documentos en un solo archivo' if av.get('cubierto') else
                     '%s de %s documentos' % (av['completos'], av['requeridos']) +
                     (' · %s rechazados' % av['rechazados'] if av['rechazados'] else ''))

        # 3. Crédito
        if 'cuentas' in secciones:
            deuda = secciones['cuentas'].get('deuda') or []
            vigente = deuda[0] if deuda else None
            if not vigente:
                paso('credito', 'Crédito', 'pendiente', 'Sin cuenta', 'cuentas',
                     accion_credito('Crear cuenta', 'fa-plus') if cliente else None, 'Crea la cuenta y su cronograma')
            elif vigente['state'] == 'borrador':
                paso('credito', 'Crédito', 'atencion', 'Borrador por aprobar', 'cuentas',
                     accion_credito('Revisar cronograma', 'fa-calendar', vigente['id']), vigente['referencia'])
            else:
                nivel = {'en_curso': 'ok', 'aprobado': 'ok', 'pagado': 'ok'}.get(vigente['state'], 'neutral')
                paso('credito', 'Crédito', nivel, vigente['estado'], 'cuentas',
                     detalle='%s de %s cuotas pagadas' % (vigente['cifras']['pagadas'], vigente['cifras']['total_cuotas']))

        # 4. Entrega y documentos del vehículo
        docs = secciones.get('documentos', {}).get('documentos_vehiculo') or []
        req = [d for d in docs if d['obligatorio']]
        listos = [d for d in req if d['estado'] == 'aceptado']
        entregado = bool(v.fecha_entrega) if 'fecha_entrega' in v._fields else False
        if req:
            faltan = [d['label'] for d in req if d['estado'] != 'aceptado']
            paso('documentos', 'Entrega y documentos', 'ok' if not faltan else ('atencion' if cliente else 'pendiente'),
                 'Completos' if not faltan else '%s de %s cargados' % (len(listos), len(req)), 'documentos',
                 detalle=('Entregado el %s' % v.fecha_entrega.strftime('%d/%m/%Y')) if entregado
                 else ('Falta: %s' % ', '.join(faltan) if faltan else ''))

        # 5. Placa
        if 'placa' in mods:
            m = mods['placa']
            paso('placa', 'Placa', 'ok' if m['nivel'] == 'ok' else (m['nivel'] if m['nivel'] != 'neutral' else 'pendiente'),
                 m['texto'], 'placa' if 'placa' in secciones else 'vehiculo')

        # 6. GPS
        if 'gps' in mods:
            m = mods['gps']
            paso('gps', 'GPS', m['nivel'] if m['nivel'] != 'neutral' else 'pendiente', m['texto'], 'gps',
                 detalle='Último reporte registrado' if m.get('desde') else '')

        # 7. Cobranza
        if 'cuentas' in mods and mods['cuentas']['texto'] != 'Sin cuenta':
            m = mods['cuentas']
            paso('cobranza', 'Cobranza', m['nivel'] if m['nivel'] != 'neutral' else 'pendiente', m['texto'], 'cuentas',
                 detalle=('%s d de atraso' % m['dias']) if m.get('dias') else '')
        return pasos

    def _campo(self, label, valor):
        return [label, valor] if valor not in (False, None, '') else None

    def _campos(self, *pares):
        return [p for p in pares if p]

    def _seccion_vehiculo(self, v):
        g = lambda c: v[c] if c in v._fields else False
        acciones = [accion_form('vehiculo', 'Editar', 'fa-pencil')]
        imprimir = []
        if self._metodo('fleet.vehicle', 'action_print_acta_vehicular'):
            imprimir.append(accion_metodo('fleet.vehicle', v.id, 'action_print_acta_vehicular', 'Acta de entrega vehicular', 'fa-print'))
        if self._metodo('fleet.vehicle', 'action_print_contrato_tvs'):
            imprimir.append(accion_metodo('fleet.vehicle', v.id, 'action_print_contrato_tvs', 'Contrato TVS', 'fa-print'))
        km = g('traccar_km_actual')
        return {
            'key': 'vehiculo', 'titulo': 'Vehículo', 'icon': 'fa-motorcycle',
            'encabezado': {
                'titulo': ' '.join(filter(None, [v.brand_id.name if 'brand_id' in v._fields else '', v.model_id.name])) or 'Vehículo',
                'ref': v.license_plate or 'Sin placa',
                'chips': [x for x in (('fa-calendar', g('model_year') and str(g('model_year'))), ('fa-tint', g('color')),
                                      ('fa-tag', v.state_id.name)) if x[1]],
            },
            'frase': frase('ok', 'Asignado a %s' % v.driver_id.name) if v.driver_id else frase('neutral', 'Sin titular asignado'),
            'cifras': [
                cifra('Kilometraje (GPS)', '%s km' % '{:,.0f}'.format(km) if km else '—', 'fa-tachometer', principal=True),
                cifra('Fecha de entrega', g('fecha_entrega') and g('fecha_entrega').strftime('%d/%m/%Y') or '—', 'fa-handshake-o'),
                cifra('Estado', v.state_id.name or '—', 'fa-tag'),
            ],
            'grupos': [{'titulo': t, 'campos': c} for t, c in (
                ('Identificación', self._campos(self._campo('Placa', v.license_plate), self._campo('Chasis', v.vin_sn),
                                                self._campo('Motor', g('x_motor_sn')))),
                ('Modelo', self._campos(self._campo('Marca', v.brand_id.name if 'brand_id' in v._fields else False),
                                        self._campo('Modelo', v.model_id.name), self._campo('Año', g('model_year')),
                                        self._campo('Color', g('color')))),
            ) if c],
            'acciones': acciones,
            'menu': [{'titulo': 'Imprimir', 'acciones': imprimir}] if imprimir else [],
        }

    def _seccion_documentos(self, v):
        docs = self._documentos_vehiculo(v)
        faltan = [d['label'] for d in docs if d['estado'] != 'aceptado' and d.get('obligatorio')]
        return {
            'key': 'documentos', 'titulo': 'Documentos del vehículo', 'icon': 'fa-file-text-o',
            'frase': frase('atencion', 'Faltan %s' % plural(len(faltan), 'documento', 'documentos'), ', '.join(faltan))
            if faltan else frase('ok', 'Documentos completos'),
            'documentos_vehiculo': docs,
            'modelo': 'fleet.vehicle', 'res_id': v.id,
        }

    def _historial_titulares(self, v):
        """Titulares del vehículo (fleet.vehicle.assignation.log), del más reciente al más antiguo."""
        Log = self._modelo('fleet.vehicle.assignation.log', 'vehicle_id', 'driver_id', 'date_start', 'date_end')
        if Log is None:
            return []
        logs = Log.search([('vehicle_id', '=', v.id)])
        logs = logs.sorted(lambda l: (l.date_start or fields.Date.to_date('1900-01-01'), l.id), reverse=True)
        # Créditos de cada titular con esta moto y cómo están (en curso, anulada, recuperada…).
        creditos = {}
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id', 'partner_id', 'state')
        if Cuenta is not None:
            for c in Cuenta.search([('vehiculo_id', '=', v.id)], order='id desc'):
                texto, nivel, _detalle = self._situacion_cuenta(c)
                creditos.setdefault(c.partner_id.id, []).append(
                    {'referencia': c.reference_no or c.display_name, 'texto': texto, 'nivel': nivel})
        historial = [{
            'id': l.driver_id.id,
            'nombre': l.driver_id.display_name or '',
            'documento': l.driver_id.vat or '',
            'desde': l.date_start and fields.Date.to_string(l.date_start),
            'hasta': l.date_end and fields.Date.to_string(l.date_end),
            'actual': l.driver_id == v.driver_id and not l.date_end,
            'creditos': creditos.get(l.driver_id.id, []),
        } for l in logs]
        # Vehículos cargados antes del historial: el titular actual aparece aunque no tenga registro.
        if v.driver_id and not any(h['actual'] for h in historial):
            historial.insert(0, {'id': v.driver_id.id, 'nombre': v.driver_id.display_name, 'documento': v.driver_id.vat or '',
                                 'desde': False, 'hasta': False, 'actual': True,
                                 'creditos': creditos.get(v.driver_id.id, [])})
        return historial

    def _seccion_cliente(self, v, cliente):
        # Acciones agrupadas por propósito: contactar y datos del cliente. El titular del
        # vehículo no se cambia aquí: se asigna al crear su crédito (Crédito y cuotas).
        historial = self._historial_titulares(v)
        if not cliente:
            # Sin crédito vigente no hay cliente: solo el historial. El cliente se asigna en Crédito y cuotas.
            return {'key': 'cliente', 'titulo': 'Cliente', 'icon': 'fa-user',
                    'vacio': 'Este vehículo no tiene cliente: se asigna al crear un crédito en Crédito y cuotas.',
                    'historial': historial}
        partner = self.env['res.partner'].browse(cliente['id'])
        contacto = []
        digitos = re.sub(r'\D', '', cliente['telefono'] or '')
        if len(digitos) == 9:
            digitos = '51' + digitos
        if len(digitos) >= 11:
            contacto.append(accion_url('https://wa.me/%s' % digitos, 'WhatsApp', 'fa-whatsapp'))
        if cliente['telefono']:
            contacto.append(accion_url('tel:%s' % cliente['telefono'], 'Llamar', 'fa-phone'))
        if cliente.get('email'):
            contacto.append(accion_url('mailto:%s' % cliente['email'], 'Correo', 'fa-envelope-o'))
        actual = next((h for h in historial if h['actual']), None)
        return {
            'key': 'cliente', 'titulo': 'Cliente', 'icon': 'fa-user',
            'perfil': {
                'nombre': partner.display_name,
                'empresa': partner.is_company,
                'documento': cliente['documento'],
                'tipo_documento': partner.l10n_latam_identification_type_id.name
                if 'l10n_latam_identification_type_id' in partner._fields else '',
                'telefono': cliente['telefono'],
                'email': cliente.get('email') or '',
                'titular': bool(v.driver_id == partner),
                'desde': actual and actual['desde'],
            },
            'grupos': [{'titulo': t, 'campos': c} for t, c in self._grupos_cliente(partner) if c],
            'historial': historial,
            'contacto': contacto,
            'editar': accion_form('cliente', 'Editar datos', 'fa-pencil', res_id=partner.id),
        }

    # Campos del contacto (res.partner) por grupo, en el orden del formulario de Contactos.
    # Los que no existen en la base (módulo no instalado) se omiten.
    CLIENTE_GRUPOS = [
        ('Identificación', ['name', 'company_type', 'l10n_latam_identification_type_id', 'vat', 'document_number']),
        ('Datos personales', ['nationality', 'marital_status', 'children_count', 'occupation']),
        ('Contacto', ['mobile', 'phone', 'email']),
        # De lo general a lo particular: cada lista se filtra por la anterior.
        ('Dirección', ['country_id', 'state_id', 'city_id', 'city', 'l10n_pe_district', 'street', 'street2', 'zip']),
    ]
    CLIENTE_ETIQUETAS = {'name': 'Nombre', 'vat': 'N° de documento', 'mobile': 'Celular', 'phone': 'Teléfono',
                         'email': 'Correo', 'street': 'Dirección', 'street2': 'Referencia',
                         'l10n_latam_identification_type_id': 'Tipo de documento', 'country_id': 'País',
                         'state_id': 'Departamento', 'city_id': 'Provincia', 'l10n_pe_district': 'Distrito'}

    def _texto_campo(self, rec, nombre):
        campo = rec._fields[nombre]
        valor = rec[nombre]
        if campo.type == 'many2one':
            return valor.display_name or ''
        if campo.type == 'selection':
            return self._etiqueta(rec, nombre, valor)
        return valor or ''

    def _grupos_cliente(self, partner):
        grupos = []
        for titulo, nombres in self.CLIENTE_GRUPOS:
            # city (texto) solo si no hay ciudad de la localización peruana.
            if 'city_id' in partner._fields and partner.city_id:
                nombres = [n for n in nombres if n != 'city']
            campos = [self._campo(self.CLIENTE_ETIQUETAS.get(n) or partner._fields[n].string, self._texto_campo(partner, n))
                      for n in nombres if n in partner._fields]
            grupos.append((titulo, self._campos(*campos)))
        return grupos

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

    def _orden_cuota(self, q, hoy):
        """Clave de orden del cronograma. Las subcuotas (saldo de un abono parcial) van justo debajo
        de su cuota, aunque venzan el día del abono; por su propia fecha quedaban al final de las vencidas."""
        return (q.parent_id or q).fecha_cronograma or hoy, q.parent_sort_id, q.id

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

    def _aviso_cuota(self, q):
        """Texto informativo de la cuota para su panel (lo amplían otros módulos)."""
        return ''

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
            mas.append(dict(accion_metodo(M, q.id, 'registrar_observacion', 'Agregar observación', 'fa-comment-o'), corto='Observación'))
        if 'voucher_image_urls' in q._fields and q.voucher_image_urls and self._metodo(M, 'action_open_image_gallery'):
            mas.append(dict(accion_metodo(M, q.id, 'action_open_image_gallery', 'Ver comprobantes', 'fa-picture-o'), corto='Comprobantes'))
        if q.state in ('pagado', 'a_cuenta') and self._metodo(M, 'action_delete_payment'):
            mas.append(dict(accion_metodo(M, q.id, 'action_delete_payment', 'Eliminar pagos de la cuota', 'fa-eraser',
                                          peligro=True), corto='Quitar pagos'))
        if self._metodo(M, 'action_eliminar_cuota'):
            mas.append(dict(accion_metodo(M, q.id, 'action_eliminar_cuota', 'Eliminar cuota', 'fa-trash', peligro=True), corto='Eliminar'))
        return principal, mas

    def _acciones_cuenta(self, c):
        """(principal, grupos del menú, documentos). A la vista solo lo diario; el resto en grupos con
        título y lo que no se deshace al final ("Cerrar la cuenta"). Los documentos van en la
        pestaña «Detalle del crédito», no en el menú."""
        M = 'adt.comercial.cuentas'
        user = self.env.user
        principal = []
        cobranza, cronograma, documentos, cierre = [], [], [], []
        if c.state == 'borrador':
            principal.append(accion_credito('Revisar cronograma', 'fa-calendar', c.id))
        if c.state == 'borrador' and self._metodo(M, 'aprobar_cuenta'):
            principal.append(accion_metodo(M, c.id, 'aprobar_cuenta', 'Aprobar cuenta', 'fa-check', primaria=True,
                                           confirmar='¿Aprobar la cuenta? Se generará el cronograma de cuotas.'))
        imprimir = self.env.ref('adt_comercial.reporte_cronograma', raise_if_not_found=False) and \
            accion_metodo('adt.flota360', c.id, 'imprimir_cronograma', 'Cronograma', 'fa-print', args=[c.id])
        if imprimir and c.state != 'borrador':
            principal.append(imprimir)

        if c.state not in ('borrador', 'cancelado') and self._metodo(M, 'agregar_mora'):
            cobranza.append(accion_metodo(M, c.id, 'agregar_mora', 'Agregar cuota o cargo', 'fa-plus'))
        if c.state == 'en_curso' and self._metodo(M, 'refinanciar_cuotas'):
            cronograma.append(accion_metodo(M, c.id, 'refinanciar_cuotas', 'Refinanciar', 'fa-refresh'))
        if c.state != 'cancelado' and self._metodo(M, 'action_cronograma_tramos'):
            cronograma.append(accion_metodo(M, c.id, 'action_cronograma_tramos', 'Cronograma por tramos', 'fa-calendar'))
        if imprimir and c.state == 'borrador':
            cronograma.append(imprimir)
        if self._metodo(M, 'action_ver_contrato'):
            documentos.append(dict(accion_metodo(M, c.id, 'action_ver_contrato', 'Contrato', 'fa-file-pdf-o'),
                                   descripcion='Contrato del crédito firmado con el cliente.'))
        if imprimir:
            documentos.append(dict(imprimir, label='Cronograma de pagos',
                                   descripcion='PDF con las cuotas que paga el cliente a ADT.'))
        documentos.append(dict(accion_abrir(M, c.id, 'Ver en Odoo', 'fa-external-link'),
                               descripcion='Abre la cuenta en el formulario de Odoo.'))
        if c.state == 'en_curso' and user.has_group('adt_comercial.group_access_adt_comercial_recuperar'):
            cierre.append(dict(accion_metodo(M, c.id, 'recuperar_vehiculo', 'Recuperar vehículo', 'fa-undo', peligro=True,
                                             confirmar='¿Recuperar el vehículo? La cuenta pasará a Cancelado y el cliente dejará de ser el titular.'),
                               descripcion='La cuenta pasa a Cancelado y el cliente deja de ser el titular.'))
        if c.state == 'cancelado' and user.has_group('adt_comercial.group_access_adt_comercial_restablecer'):
            cierre.append(accion_metodo(M, c.id, 'restablecer_vehiculo', 'Restablecer cuenta', 'fa-repeat',
                                        confirmar='¿Restablecer la cuenta a En curso? El cliente volverá a ser el titular.'))
        if c.state not in ('borrador', 'cancelado') and self._metodo(M, 'cancelar_cuenta'):
            cierre.append(dict(accion_metodo(M, c.id, 'cancelar_cuenta', 'Anular cuenta', 'fa-ban', peligro=True,
                                             confirmar='¿Anular la cuenta? Se marcará como Cancelada, el vehículo quedará disponible y el cliente dejará de ser el titular.'),
                               descripcion='La cuenta queda Cancelada y el vehículo disponible.'))
        grupos = [{'titulo': t, 'acciones': a} for t, a in (
            ('Cobranza', cobranza), ('Cronograma', cronograma), ('Cerrar la cuenta', cierre)) if a]
        return principal, grupos, documentos

    def _opciones_cobro(self, c, filas):
        """Lo que se puede cobrar en la cuenta, para el botón único "Cobrar"."""
        if c.state != 'en_curso':
            return []
        M = 'adt.comercial.cuotas'
        opciones = []
        abierta = next((f for f in filas if f['grupo'] in ('vencida', 'a_cuenta', 'por_vencer') and f['saldo'] > 0), None)
        if abierta and self._metodo(M, 'action_register_payment'):
            vencida = abierta['grupo'] == 'vencida'
            opciones.append(dict(
                accion_metodo(M, abierta['id'], 'action_register_payment',
                              'Pagar %s' % abierta['nombre'], 'fa-money'),
                descripcion='%s · %s %s' % (
                    self._soles(abierta['saldo']), 'venció el' if vencida else 'vence el',
                    fields.Date.to_date(abierta['fecha']).strftime('%d/%m/%Y') if abierta['fecha'] else '—'),
                sugerida=True))
        if self._metodo('adt.comercial.cuentas', 'action_cancelar_credito'):
            opciones.append(dict(
                accion_metodo('adt.comercial.cuentas', c.id, 'action_cancelar_credito',
                              'Cancelar todo el crédito o pagar varias cuotas', 'fa-sort-amount-asc'),
                descripcion='Pago en cascada desde la cuota más antigua, o todo el saldo de una vez.'))
        mora = next((f for f in filas if f['mora_registrada'] > 0), None)
        if mora and self._metodo(M, 'action_pagar_mora'):
            opciones.append(dict(
                accion_metodo(M, mora['id'], 'action_pagar_mora', 'Pagar mora de %s' % mora['nombre'], 'fa-money'),
                descripcion='%s de mora registrada pendiente.' % self._soles(mora['mora_registrada'])))
        return opciones

    # --- Financiera del vehículo -------------------------------------------
    # El plan de pagos de la financiera es de la moto (se financia una vez): se sube aquí y
    # todas sus cuentas lo muestran. En los reportes lo lleva una sola cuenta (la vigente).

    def _seccion_financiera(self, v, hoy):
        if 'cf_pdf' not in v._fields:
            return None
        d = lambda x: fields.Date.to_string(x) if x else ''
        adjunto = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', v._name), ('res_id', '=', v.id), ('res_field', '=', 'cf_pdf')], limit=1)
        base = '/web/content/%s/%s/cf_pdf' % (v._name, v.id)
        unico = (adjunto.checksum or '')[:8]
        cuentas = v.cuenta_ids if 'cuenta_ids' in v._fields else self.env['adt.comercial.cuentas']
        lleva = cuentas.filtered('fin_desde_vehiculo')[:1] if 'fin_desde_vehiculo' in cuentas._fields else cuentas[:1]
        nombre = (lleva or cuentas.sorted('id', reverse=True))[:1].tipo_financiera_id.display_name \
            if cuentas and 'tipo_financiera_id' in cuentas._fields else ''
        cuotas = v.cf_cuota_ids.sorted(lambda q: (q.nro_cuota, q.id))
        anteriores = max((v.cf_primera_cuota or 1) - 1, 0) if cuotas else 0
        return {
            'key': 'financiera', 'titulo': 'Financiera', 'icon': 'fa-university',
            'vehicle_id': v.id,
            'nombre': nombre or '',
            'cuenta': lleva and (lleva.reference_no or lleva.display_name) or '',
            'pdf': {
                'cargado': bool(adjunto),
                'nombre': v.cf_pdf_nombre or 'Plan de pagos.pdf',
                'url': '%s?unique=%s' % (base, unico),
                'descarga': '%s?download=true&unique=%s' % (base, unico),
                'fecha': fields.Datetime.to_string(adjunto.write_date or adjunto.create_date) if adjunto else '',
            },
            'lectura': {
                'estado': v.cf_estado or '',
                'texto': self._etiqueta(v, 'cf_estado', v.cf_estado) if v.cf_estado else '',
                'confianza': v.cf_confianza or 0.0,
            },
            'total_plan': v.cf_total_plan() if cuotas else 0.0,
            'anteriores': anteriores,
            'datos': self._campos(
                self._campo('N° de solicitud', v.cf_nro_solicitud),
                self._campo('Socio en el PDF', ' · '.join(filter(None, [v.cf_socio, v.cf_dni]))),
                self._campo('Monto del crédito', v.cf_monto_credito and self._soles(v.cf_monto_credito)),
                self._campo('Cuota', v.cf_monto_cuota and self._soles(v.cf_monto_cuota)),
                self._campo('Frecuencia', v.cf_frecuencia_cuota),
                self._campo('Desembolso', v.cf_fecha_desembolso and v.cf_fecha_desembolso.strftime('%d/%m/%Y')),
                self._campo('Próximo vencimiento', v.cf_proximo_vencimiento and v.cf_proximo_vencimiento.strftime('%d/%m/%Y')),
                self._campo('Capital pendiente', v.cf_capital_pendiente and self._soles(v.cf_capital_pendiente)),
                self._campo('Total en el PDF', v.cf_total_pdf and self._soles(v.cf_total_pdf)),
            ),
            'cuotas': [{'nro': q.nro_cuota, 'fecha': d(q.fecha_vencimiento), 'capital': q.capital,
                        'interes': q.interes, 'otros': (q.seguro_desgravamen + q.comision_operativa + q.interes_vencido +
                                                       q.interes_moratorio + q.interes_compensatorio + q.aporte + q.otros),
                        'total': q.total, 'estado': q.estado or ''} for q in cuotas],
            'leer': accion_metodo(v._name, v.id, 'cf_leer_pdf', 'Volver a leer', 'fa-refresh') if adjunto else None,
        }

    def _fecha_cierre(self, c):
        """Fecha en que la cuenta pasó a Cancelado/Pagado, según el seguimiento del estado en el chatter."""
        for m in c.message_ids:  # del más reciente al más antiguo
            try:
                m.check_field_access_rights('read', ['tracking_value_ids'])
                tracking = m.tracking_value_ids
                tracking.check_access_rights('read')
                tracking.check_access_rule('read')
            except AccessError:
                # El historial técnico puede estar restringido; no debe ocultar el crédito completo.
                tracking = self.env['mail.tracking.value']
            for t in tracking:
                if t.field.name == 'state' and t.new_value_char in (
                        self._etiqueta(c, 'state', 'cancelado'), self._etiqueta(c, 'state', 'pagado')):
                    return fields.Date.to_string(m.date.date())
        return False

    def _situacion_cuenta(self, c):
        """(texto, nivel, explicación) de cómo está o cómo terminó la cuenta, para la lista de cuentas."""
        if c.state == 'cancelado' and c.recuperado:
            return 'Recuperada', 'critico', 'Se retiró la moto al cliente'
        if c.state == 'cancelado':
            return 'Anulada', 'neutral', 'Cuenta anulada'
        if c.state == 'pagado':
            return 'Pagada', 'ok', 'Terminó de pagar'
        if c.state == 'en_curso':
            return 'En curso', 'info', ''
        return self._etiqueta(c, 'state', c.state), 'neutral', ''

    def _soles(self, monto):
        return 'S/ {:,.2f}'.format(monto or 0.0)

    def _historial(self, record, limite=25):
        eventos = []
        for m in record.message_ids[:limite]:
            texto = html2plaintext(m.body or '').strip()
            cambios = []
            try:
                m.check_field_access_rights('read', ['tracking_value_ids'])
                tracking = m.tracking_value_ids
                tracking.check_access_rights('read')
                tracking.check_access_rule('read')
            except AccessError:
                # El historial técnico puede estar restringido; no debe ocultar el crédito completo.
                tracking = self.env['mail.tracking.value']
            for t in tracking:
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
            todas = c.cuota_ids.sorted(lambda q: self._orden_cuota(q, hoy))
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
                    'aviso': self._aviso_cuota(q),
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
            principal, grupos_menu, documentos = self._acciones_cuenta(c)
            vigente = c.state in ('borrador', 'aprobado', 'en_curso')
            vencidas = [f for f in filas if f['grupo'] == 'vencida']

            # Una frase con el estado de cobranza (reemplaza leer las cinco cifras).
            if c.state == 'borrador':
                frase = ('info', 'Borrador por aprobar', 'Revisa el cronograma y apruébalo para empezar a cobrar.')
            elif vencidas:
                mas_antigua = fields.Date.to_date(vencidas[0]['fecha'])
                frase = ('critico' if vencidas_n >= CUOTAS_CRITICAS else 'atencion',
                         'Atrasado %s' % plural(dias_atraso, 'día', 'días'),
                         '%s, la más antigua del %s' % (plural(vencidas_n, 'cuota vencida', 'cuotas vencidas'),
                                                        mas_antigua.strftime('%d/%m/%Y') if mas_antigua else '—'))
            elif c.state == 'en_curso':
                frase = ('ok', 'Al día', proxima and 'Próxima cuota el %s' % proxima.fecha_cronograma.strftime('%d/%m/%Y') or '')
            elif c.state == 'pagado':
                frase = ('ok', 'Crédito pagado', '')
            elif c.state == 'cancelado':
                frase = ('neutral', 'Vehículo recuperado' if c.recuperado else 'Cuenta cerrada',
                         'Quedaron %s sin cobrar' % self._soles(capital) if capital > 0 else '')
            else:
                frase = ('neutral', self._etiqueta(c, 'state', c.state), '')

            # Pendientes accionables, de lo más urgente a lo menos.
            pendientes = []
            if vigente:
                for f in filas:
                    if f['grupo'] == 'vencida':
                        detalle = 'Venció el %s · %s' % (fields.Date.to_date(f['fecha']).strftime('%d/%m/%Y'),
                                                          plural((hoy - fields.Date.to_date(f['fecha'])).days, 'día', 'días'))
                        if f['mora']:
                            detalle += ' · mora %s' % self._soles(f['mora'])
                        pendientes.append({'tipo': 'vencida', 'nivel': 'critico', 'icon': 'fa-exclamation-triangle',
                                           'titulo': '%s vencida · %s' % (f['nombre'], self._soles(f['saldo'])),
                                           'detalle': detalle, 'cuota': f['id'],
                                           'accion': f['acciones'][0] if f['acciones'] else None})
                    elif f['grupo'] == 'a_cuenta':
                        pendientes.append({'tipo': 'a_cuenta', 'nivel': 'atencion', 'icon': 'fa-adjust',
                                           'titulo': '%s a cuenta · faltan %s' % (f['nombre'], self._soles(f['saldo'])),
                                           'detalle': 'Pagó %s' % self._soles(f['pagado']), 'cuota': f['id'],
                                           'accion': dict(f['acciones'][0], label='Completar') if f['acciones'] else None})
                    elif f['subcuota'] and f['saldo'] > 0:
                        # Saldo de un abono parcial: adt_comercial lo deja en una subcuota «por vencer».
                        pendientes.append({'tipo': 'a_cuenta', 'nivel': 'atencion', 'icon': 'fa-adjust',
                                           'titulo': '%s · resto de un abono parcial · %s' % (f['nombre'], self._soles(f['saldo'])),
                                           'detalle': 'Vence el %s' % fields.Date.to_date(f['fecha']).strftime('%d/%m/%Y')
                                           if f['fecha'] else 'Saldo pendiente', 'cuota': f['id'],
                                           'accion': dict(f['acciones'][0], label='Pagar el resto') if f['acciones'] else None})

            # Datos clave de la cuenta, cada uno con su etiqueta (cabecera de la cuenta).
            condiciones = [{'icon': i, 'label': l, 'valor': val} for i, l, val in (
                ('fa-university', 'Tipo de Financiera', 'tipo_financiera_id' in c._fields and c.tipo_financiera_id.display_name or ''),
                ('fa-refresh', 'Periodo', self._etiqueta(c, 'periodicidad', c.periodicidad) if c.periodicidad else ''),
                ('fa-calendar-check-o', 'Monto de cuota', c.monto_cuota and self._soles(c.monto_cuota) or ''),
                ('fa-money', 'Fecha de desembolso', c.fecha_desembolso and c.fecha_desembolso.strftime('%d/%m/%Y') or ''),
                ('fa-user-o', 'Vendedor', 'user_id' in c._fields and c.user_id.name or ''),
            ) if val]
            ultimo = pagos_cuenta[0]['fecha'] if pagos_cuenta else False
            ficha = self._ficha_cuenta(c, cuotas_capital, filas, capital)
            ficha['documentos'] = documentos
            ficha['adjuntos'] = self._evidencias(c.attachment_ids) if 'attachment_ids' in c._fields else []
            ficha['contrato'] = self._evidencias(c.contrato_ids) if 'contrato_ids' in c._fields else None

            resultado.append({
                'id': c.id,
                'vigente': vigente,
                'titular': {
                    'nombre': c.partner_id.name or '',
                    'documento': c.partner_id.vat or '',
                    'actual': bool(c.partner_id) and c.partner_id == v.driver_id,
                },
                'periodo': {
                    'desde': fields.Date.to_string(c.fecha_desembolso) if c.fecha_desembolso else '',
                    'hasta': '' if vigente else (self._fecha_cierre(c) or ultimo or ''),
                },
                'situacion': dict(zip(('texto', 'nivel', 'detalle'), self._situacion_cuenta(c))),
                'frase': {'nivel': frase[0], 'texto': frase[1], 'detalle': frase[2]},
                'condiciones': condiciones,
                'ficha': ficha,
                'pendientes': pendientes,
                'cobrar': self._opciones_cobro(c, filas),
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
                'menu': grupos_menu,
                'recuperado': bool(c.recuperado),
                'captura_prioridad': self._etiqueta(c, 'captura_prioridad', c.captura_prioridad)
                if 'captura_prioridad' in c._fields else '',
            })
        vigente = any(c['vigente'] for c in resultado)
        avisos = []
        for c in resultado:
            if c['vigente'] and v.driver_id and not c['titular']['actual']:
                avisos.append('La cuenta %s sigue a nombre de %s, que ya no es el titular del vehículo. '
                              'Revisa si corresponde recuperarla o cancelarla.' % (c['referencia'], c['titular']['nombre']))
        sin_cobrar = sum(c['cifras']['capital'] for c in resultado if c['state'] == 'cancelado')
        return {
            'key': 'cuentas', 'titulo': 'Crédito y cuotas', 'icon': 'fa-credit-card',
            'deuda': resultado,
            'avisos': avisos,
            'sin_cobrar_anteriores': sin_cobrar,
            'vacio': 'El vehículo no tiene cuentas registradas.',
            'acciones': [] if vigente else [accion_credito('Nuevo crédito', 'fa-plus', primaria=True)],
        }

    def _ficha_cuenta(self, c, cuotas_capital, filas, capital):
        """Pestaña «Detalle del crédito»: condiciones pactadas, montos, fechas y responsables."""
        g = lambda n: c[n] if n in c._fields else False
        d = lambda f: f.strftime('%d/%m/%Y') if f else ''
        s = lambda m: self._soles(m) if m else ''
        validas = cuotas_capital.filtered(lambda q: q.state != 'anulada' and q.fecha_cronograma)
        fechas = sorted(validas.mapped('fecha_cronograma'))
        numeradas = validas.filtered(lambda q: q.monto and (q.name or '') != 'Cuota 0')
        pagado = sum(f['pagado'] for f in filas)
        total = sum(validas.mapped('monto'))
        # Mismos nombres y grupos que la pestaña «Crédito» de la cuenta en Comercial.
        cierre = g('fecha_cierre')
        grupos = [
            ('Fechas', 'fa-calendar', [
                self._campo('Fecha de desembolso', d(g('fecha_desembolso'))),
                self._campo('Fecha de cierre', 'Día %s' % cierre if cierre else ''),
                self._campo('Fecha de entrega', d(g('fecha_entrega'))),
            ]),
            ('Montos y cuotas', 'fa-money', [
                self._campo('Valor total del vehículo', s(g('monto_total'))),
                self._campo('Inicial', s(g('monto_inicial'))),
                self._campo('Monto fraccionado', s(g('monto_fraccionado'))),
                self._campo('Cuota de gracia', s(g('cuota_gracia'))),
                self._campo('Fecha de gracia', d(g('fecha_gracia'))),
                self._campo('Periodo', self._etiqueta(c, 'periodicidad', c.periodicidad) if c.periodicidad else ''),
                self._campo('Total de cuotas', str(g('qty_cuotas') or len(numeradas) or '')),
                self._campo('Monto de cuota', s(g('monto_cuota') or (numeradas[:1] and numeradas[0].monto))),
            ]),
            ('Cuenta', 'fa-id-card-o', [
                self._campo('Referencia', c.reference_no or ''),
                self._campo('Estado', self._etiqueta(c, 'state', c.state)),
                self._campo('Socio', c.partner_id.display_name),
                self._campo('Documento', c.partner_id.vat or ''),
                self._campo('Tipo de Financiera', g('tipo_financiera_id') and c.tipo_financiera_id.display_name),
                self._campo('Vendedor', g('user_id') and c.user_id.name),
                self._campo('Asesor', self._etiqueta(c, 'asesor', c.asesor) if g('asesor') else ''),
                self._campo('¿Paga Mora?', 'Sí' if g('is_available_pay_mora') else 'No'),
            ]),
            ('Cronograma generado', 'fa-list-ol', [
                self._campo('Primera cuota', d(fechas and fechas[0])),
                self._campo('Última cuota', d(fechas and fechas[-1])),
                self._campo('Total del cronograma', s(total)),
                self._campo('Pagado', self._soles(pagado)),
                self._campo('Saldo por cobrar', self._soles(capital)),
                self._campo('Registrada el', d(c.create_date)),
            ]),
        ]
        return {
            'grupos': [{'titulo': t, 'icon': i, 'campos': [x for x in campos if x]} for t, i, campos in grupos],
            'avance': {'pagado': pagado, 'total': total,
                       'pct': round(pagado * 100.0 / total) if total else 0},
        }

    # --- Rentabilidad del vehículo -----------------------------------------
    # Una moto puede financiarse varias veces: cada crédito anulado o recuperado deja lo que su
    # cliente pagó (inicial + cuotas + cargos + mora). Se suma todo lo recaudado y lo que falta
    # cobrar al cliente actual (proyección), y se le resta lo que ADT paga a la financiera. El plan
    # de la financiera es del vehículo (un préstamo por moto), aunque el PDF se cargue en una
    # cuenta: cada préstamo (N° de solicitud) se cuenta una sola vez.

    def _seccion_rentabilidad(self, v, hoy):
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id')
        if Cuenta is None:
            return None
        cuentas = Cuenta.search([('vehiculo_id', '=', v.id)])
        if not cuentas:
            return None
        cuentas = cuentas.sorted(lambda c: (c.fecha_desembolso or c.create_date.date(), c.id))
        filas = []
        for orden, c in enumerate(cuentas, 1):
            validas = c.cuota_ids.filtered(lambda q: q.state != 'anulada')
            cuotas = validas.filtered(lambda q: q.type == 'cuota')
            cargos = validas.filtered(lambda q: q.type != 'cuota')
            cobrado = lambda qs: sum(max((q.monto or 0.0) - (q.saldo or 0.0), 0.0) for q in qs)
            mora = sum((p.mora or 0.0) if p.mora_state == 'paid' else (p.mora_pagado or 0.0)
                       for p in validas.mapped('payment_ids'))
            # La inicial se paga al entregar la moto: cuenta como cobrada desde que la cuenta se aprueba.
            iniciada = c.state != 'borrador'
            inicial = c.monto_inicial or 0.0
            cronograma = sum(cuotas.mapped('monto')) if cuotas else (c.monto_fraccionado or 0.0)
            pactado = inicial + cronograma
            recaudado = (inicial if iniciada else 0.0) + cobrado(cuotas) + cobrado(cargos) + mora
            vigente = c.state in ('borrador', 'aprobado', 'en_curso')
            por_cobrar = (pactado if not iniciada else sum(cuotas.mapped('saldo'))) if vigente else 0.0
            texto, nivel, _detalle = self._situacion_cuenta(c)
            filas.append({
                'id': c.id,
                'orden': orden,
                'referencia': c.reference_no or c.display_name,
                'titular': c.partner_id.display_name or '',
                'documento': c.partner_id.vat or '',
                'desde': fields.Date.to_string(c.fecha_desembolso) if c.fecha_desembolso else '',
                'hasta': '' if vigente else (self._fecha_cierre(c) or ''),
                'estado': texto, 'nivel': nivel, 'vigente': vigente,
                'inicial': inicial, 'inicial_cobrada': inicial if iniciada else 0.0, 'cronograma': cronograma, 'pactado': pactado,
                'cuotas_cobradas': cobrado(cuotas), 'cargos': cobrado(cargos) + mora,
                'recaudado': recaudado, 'por_cobrar': por_cobrar, 'proyectado': recaudado + por_cobrar,
                'pct': round(recaudado * 100.0 / pactado) if pactado else 0,
            })
        total = lambda k: sum(f[k] for f in filas)
        planes = self._planes_financiera(v)
        financiera = sum(p['total'] for p in planes)
        return {
            'key': 'rentabilidad', 'titulo': 'Rentabilidad', 'icon': 'fa-line-chart',
            'creditos': filas,
            'planes': planes,
            'totales': {
                'recaudado': total('recaudado'), 'por_cobrar': total('por_cobrar'), 'proyectado': total('proyectado'),
                'pactado': total('pactado'), 'inicial': total('inicial'), 'cargos': total('cargos'),
                'inicial_cobrada': total('inicial_cobrada'), 'cuotas_cobradas': total('cuotas_cobradas'),
                'financiera': financiera, 'margen': total('proyectado') - financiera,
                'clientes': len(set(cuentas.mapped('partner_id').ids)),
            },
        }

    def _planes_financiera(self, v):
        """Préstamo de la financiera por el vehículo (el plan de pagos cargado en la moto), contado
        una vez. Total = plan completo: cuotas del PDF + las anteriores al PDF, estimadas."""
        if 'cf_cuota_ids' not in v._fields or not (v.cf_cuota_ids or v.cf_total_pdf):
            return []
        cuentas = v.cuenta_ids if 'cuenta_ids' in v._fields else self.env['adt.comercial.cuentas']
        lleva = cuentas.filtered('fin_desde_vehiculo')[:1] if 'fin_desde_vehiculo' in cuentas._fields else cuentas[:1]
        return [{
            'solicitud': v.cf_nro_solicitud or '',
            'financiera': lleva.tipo_financiera_id.display_name if lleva and 'tipo_financiera_id' in lleva._fields else '',
            'total': v.cf_total_plan(),
            'anteriores': max((v.cf_primera_cuota or 1) - 1, 0) if v.cf_cuota_ids else 0,
        }]

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

    def _evidencias(self, adjuntos):
        """Adjuntos (ir.attachment) para la vista: miniatura si es imagen, enlace si no."""
        evidencias = []
        for a in adjuntos.sorted('id'):
            unico = (a.checksum or '')[:8]
            es_imagen = (a.mimetype or '').startswith('image/')
            evidencias.append({
                'id': a.id,
                'nombre': a.name or '',
                'imagen': es_imagen,
                'mimetype': a.mimetype or '',
                'fecha': fields.Datetime.to_string(a.create_date),
                'miniatura': '/web/image/%s/320x240?unique=%s' % (a.id, unico) if es_imagen else '',
                'url': '/web/content/%s?unique=%s' % (a.id, unico),
                'descarga': '/web/content/%s?download=true&unique=%s' % (a.id, unico),
            })
        return evidencias

    def _detalle_papeleta(self, p, hoy):
        g = lambda c: p[c] if c in p._fields else False
        pagada = p.state == 'pagado'
        vencida = not pagada and p.fecha_vencimiento_final and p.fecha_vencimiento_final < hoy
        nivel = 'ok' if pagada else ('critico' if vencida else 'atencion')
        fraccionada = g('payment_method') == 'fraccionado'
        cuotas = g('cuotas_ids') or p.browse()
        pendientes = cuotas.filtered(lambda c: c.state == 'pendiente')

        alertas = []
        if not pagada and g('texto_alerta'):
            alertas.append({'nivel': nivel, 'texto': p.texto_alerta})
        if g('capturado') and not g('recolocada'):
            alertas.append({'nivel': 'atencion', 'texto': 'El vehículo fue marcado como capturado: esta papeleta '
                                                           'se deriva al área de captura.'})
        if g('recolocada') and not pagada:
            alertas.append({'nivel': 'critico', 'texto': 'El vehículo ya fue recolocado, pero la papeleta sigue '
                                                         'pendiente de pago.'})

        marcas = []
        if fraccionada:
            marcas.append({'texto': 'Fraccionada', 'nivel': 'info'})
        if g('capturado'):
            marcas.append({'texto': 'Capturado', 'nivel': 'critico'})
        if g('recolocada'):
            marcas.append({'texto': 'Recolocada', 'nivel': 'neutral'})

        a_fecha = lambda d: fields.Date.to_string(d) if d else False
        kpis = [
            {'label': 'Monto', 'monto': p.monto},
            {'label': 'Fecha', 'fecha': a_fecha(p.fecha_papeleta)},
            {'label': 'Fecha de captura', 'fecha': a_fecha(g('fecha_captura'))},
            {'label': 'Vence', 'fecha': a_fecha(p.fecha_vencimiento_final), 'nivel': False if pagada else nivel},
        ]
        if pagada:
            kpis.append({'label': 'Pagada el', 'fecha': a_fecha(g('fecha_pago')), 'nivel': 'ok'})
        elif p.fecha_vencimiento_final:
            dias = (p.fecha_vencimiento_final - hoy).days
            kpis.append({'label': 'Días para captura', 'texto': str(dias), 'nivel': nivel})

        campos = self._campos(
            self._campo('Modalidad de pago', self._etiqueta(p, 'payment_method', g('payment_method'))),
            self._campo('Prórroga', plural(p.dias_prorroga or 0, 'día', 'días') if g('tiene_prorroga') else 'No'),
            self._campo('Motivo de prórroga', g('tiene_prorroga') and g('motivo_prorroga')),
            self._campo('Registrada', '%s · %s' % (p.create_uid.name, fields.Datetime.to_string(p.create_date)[:10])
                        if p.create_uid else False),
        )

        M = 'adt.papeleta'
        acciones, mas = [], []
        if not pagada and not (fraccionada and pendientes) and self._metodo(M, 'action_mark_pagado'):
            acciones.append(accion_metodo(M, p.id, 'action_mark_pagado', 'Marcar pagada', 'fa-check',
                                          confirmar='¿Marcar la papeleta %s como pagada?' % p.name, primaria=True))
        if not pagada:
            # Una papeleta pagada ya no se puede modificar (adt_papeletas lo impide).
            acciones.append(accion_form('papeleta', 'Editar', 'fa-pencil', res_id=p.id))
            if fraccionada and g('cantidad_cuotas'):
                mas.append(accion_metodo('adt.flota360', p.id, 'generar_cuotas_papeleta',
                                         'Regenerar cuotas' if cuotas else 'Generar cuotas', 'fa-list-ol', args=[p.id],
                                         confirmar='Se reemplazarán las %s cuotas actuales.' % len(cuotas) if cuotas else None))
            if fraccionada and cuotas and self._metodo(M, 'action_eliminar_cuotas'):
                mas.append(accion_metodo(M, p.id, 'action_eliminar_cuotas', 'Eliminar cuotas', 'fa-trash-o', peligro=True))
            if not g('capturado') and self._metodo(M, 'action_mark_capturar'):
                mas.append(accion_metodo(M, p.id, 'action_mark_capturar', 'Mandar a capturar', 'fa-lock', peligro=True,
                                         confirmar='¿Mandar a capturar el vehículo por la papeleta %s?' % p.name))
        if g('capturado') and self._metodo(M, 'action_unmark_capturar'):
            mas.append(accion_metodo(M, p.id, 'action_unmark_capturar', 'Remover captura', 'fa-unlock',
                                     confirmar='¿Quitar la marca de captura de la papeleta %s?' % p.name))
        mas.append(accion_abrir(M, p.id, 'Formulario completo'))

        detalle_cuotas = []
        for c in cuotas.sorted(lambda c: (c.due_date or hoy, c.id)):
            pagada_c = c.state == 'pagado'
            vencida_c = not pagada_c and c.due_date and c.due_date < hoy
            detalle_cuotas.append({
                'nombre': c.name,
                'fecha': a_fecha(c.due_date),
                'monto': c.amount,
                'estado': self._etiqueta(c, 'state', c.state),
                'nivel': 'ok' if pagada_c else ('critico' if vencida_c else 'atencion'),
                'accion': accion_metodo('adt.papeleta.cuota', c.id, 'action_mark_cuota_pagado', 'Pagar', 'fa-check',
                                        confirmar='¿Marcar la %s de la papeleta %s como pagada?' % (c.name, p.name))
                if not pagada_c and not pagada else None,
            })

        return {
            'id': p.id,
            'titulo': 'Papeleta %s' % p.name,
            'badge': {'texto': 'Vencida' if vencida else self._etiqueta(p, 'state', p.state), 'nivel': nivel},
            'marcas': marcas,
            'alertas': alertas,
            'kpis': kpis,
            'campos': campos,
            'detalle': (p.detalle or '').strip(),
            'evidencias': self._evidencias(g('attachment_ids') or self.env['ir.attachment']),
            'fraccionada': fraccionada,
            'fraccionamiento': {
                'cantidad': g('cantidad_cuotas') or 0,
                'inicio': a_fecha(g('fecha_inicio_cuotas')),
                'pagadas': len(cuotas) - len(pendientes),
                'total': len(cuotas),
                'saldo': sum(pendientes.mapped('amount')),
                'cuotas': detalle_cuotas,
                'evidencias': self._evidencias(g('attachment_cuotas_ids') or self.env['ir.attachment']),
            } if fraccionada else None,
            'historial': self._historial(p),
            'editable': not pagada,
            'acciones': acciones,
            'mas': mas,
        }

    @api.model
    def generar_cuotas_papeleta(self, papeleta_id):
        """Genera las cuotas de una papeleta fraccionada sin abrir su formulario
        (action_generar_cuotas devuelve una acción que reemplazaría la vista)."""
        papeleta = self.env['adt.papeleta'].browse(papeleta_id).exists()
        papeleta.action_generar_cuotas()
        return True

    def _seccion_papeletas(self, v, hoy):
        Papeleta = self._modelo('adt.papeleta', 'vehicle_id')
        if Papeleta is None:
            return None
        papeletas = Papeleta.search([('vehicle_id', '=', v.id)])
        papeletas = papeletas.sorted(lambda p: (p.state == 'pagado', p.fecha_vencimiento_final or hoy))
        pendientes = papeletas.filtered(lambda p: p.state != 'pagado')
        vencidas = pendientes.filtered(lambda p: p.fecha_vencimiento_final and p.fecha_vencimiento_final < hoy)
        proxima = pendientes.filtered('fecha_vencimiento_final').sorted('fecha_vencimiento_final')[:1]
        if vencidas:
            estado_pap = frase('critico', plural(len(vencidas), 'papeleta vencida', 'papeletas vencidas'), 'Riesgo de captura del vehículo')
        elif pendientes:
            estado_pap = frase('atencion', plural(len(pendientes), 'papeleta pendiente', 'papeletas pendientes'),
                               proxima and 'La próxima vence el %s' % proxima.fecha_vencimiento_final.strftime('%d/%m/%Y') or '')
        else:
            estado_pap = frase('ok', 'Sin papeletas pendientes')
        return {
            'key': 'papeletas', 'titulo': 'Papeletas', 'icon': 'fa-file-text-o',
            'frase': estado_pap,
            'cifras': [
                cifra('Por pagar', self._soles(sum(pendientes.mapped('monto'))), 'fa-money',
                      plural(len(pendientes), 'pendiente', 'pendientes'), 'critico' if vencidas else '', principal=True),
                cifra('Vencidas', str(len(vencidas)), 'fa-exclamation-triangle', nivel='critico' if vencidas else ''),
                cifra('Pagadas', str(len(papeletas) - len(pendientes)), 'fa-check-circle'),
            ] if papeletas else [],
            'papeletas': [self._detalle_papeleta(p, hoy) for p in papeletas],
            'kpis': [
                {'label': 'Pendientes', 'texto': str(len(pendientes)), 'nivel': 'atencion' if pendientes else 'ok'},
                {'label': 'Por pagar', 'monto': sum(pendientes.mapped('monto'))},
                {'label': 'Pagadas', 'texto': str(len(papeletas) - len(pendientes))},
            ] if papeletas else [],
            'vacio': 'Sin papeletas registradas.',
            'acciones': [accion_form('papeleta', 'Registrar papeleta', 'fa-plus', primaria=True)],
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
        ultimo = cred.gps_last_update
        horas = (fields.Datetime.now() - ultimo).total_seconds() / 3600 if ultimo else None
        if status == 'online':
            estado_gps = frase('ok', 'En línea', cred.gps_address or '')
        elif horas is not None and horas > GPS_HORAS_SIN_SENAL:
            estado_gps = frase('critico', 'Sin señal hace %s' % plural(int(horas // 24) or 1, 'día', 'días')
                               if horas >= 24 else 'Sin señal hace %s h' % int(horas), cred.gps_address or '')
        else:
            estado_gps = frase('atencion', self._etiqueta(cred, 'gps_status', status) or 'Sin señal', cred.gps_address or '')
        return {
            'key': 'gps', 'titulo': 'GPS / Traccar', 'icon': 'fa-map-marker',
            'frase': estado_gps,
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
                    'clave': 'tramite',
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
                    'clave': 'entrega',
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
        tramite = next((i for i in items if i['clave'] == 'tramite'), None)
        entrega = next((i for i in items if i['clave'] == 'entrega'), None)
        if placa_valida(v.license_plate):
            estado_placa = frase('ok', 'Placa %s' % v.license_plate, entrega and 'Entrega: %s' % entrega['badge']['texto'] or '')
        elif tramite:
            estado_placa = frase(tramite['badge']['nivel'] if tramite['badge']['nivel'] != 'neutral' else 'info',
                                 'Placa en trámite · %s' % tramite['badge']['texto'], tramite['subtitulo'])
        else:
            estado_placa = frase('atencion', 'Sin placa', 'No hay un trámite de placa registrado.')
        return {'key': 'placa', 'titulo': 'Placa y entrega', 'icon': 'fa-id-card-o', 'items': items,
                'frase': estado_placa,
                'vacio': 'Sin trámite de placa ni seguimiento de entrega.'}

    def _archivo_campo(self, record, campo, nombre):
        """Archivo de un campo binario con el mismo formato que _evidencias."""
        if campo not in record._fields or not record[campo]:
            return None
        adjunto = self.env['ir.attachment'].search([('res_model', '=', record._name), ('res_id', '=', record.id),
                                                    ('res_field', '=', campo)], limit=1)
        if adjunto:
            archivo = self._evidencias(adjunto)[0]
            archivo['nombre'] = nombre or archivo['nombre']
            return archivo
        # Campo guardado en la base (sin ir.attachment): se sirve por modelo/id/campo.
        try:
            mimetype = guess_mimetype(base64.b64decode(record[campo][:1024]))
        except Exception:
            mimetype = 'application/octet-stream'
        es_imagen = mimetype.startswith('image/')
        base = 'model=%s&id=%s&field=%s' % (record._name, record.id, campo)
        return {
            'id': '%s-%s' % (record.id, campo),
            'nombre': nombre,
            'imagen': es_imagen,
            'mimetype': mimetype,
            'fecha': fields.Datetime.to_string(record.write_date),
            'miniatura': '/web/image/%s/%s/%s/320x240' % (record._name, record.id, campo) if es_imagen else '',
            'url': '/web/content?%s' % base,
            'descarga': '/web/content?%s&download=true' % base,
        }

    @api.model
    def accion_captura(self, captura_id, metodo):
        """Ejecuta un botón del formulario de la captura. El asistente de liberación
        toma la captura de active_id (el formulario lo pone; la vista no)."""
        if metodo not in CAPTURA_BOTONES:
            raise AccessError(_('Operación no permitida.'))
        captura = self.env['adt.captura.record'].browse(captura_id).exists()
        if not captura:
            return False
        res = getattr(captura.with_context(active_id=captura.id, active_ids=captura.ids,
                                           active_model=captura._name), metodo)()
        if isinstance(res, dict) and res.get('type') == 'ir.actions.act_window':
            res['context'] = dict(res.get('context') or {}, active_id=captura.id, active_ids=captura.ids,
                                  active_model=captura._name)
        return res

    def _cuotas_captura(self, c, hoy):
        """Pestaña "Cuotas pendientes" del formulario de la captura."""
        if 'cuotas_pendientes_ids' not in c._fields:
            return []
        filas = []
        for q in c.cuotas_pendientes_ids.sorted(lambda q: (q.fecha_cronograma or hoy, q.id)):
            g = lambda f: q[f] if f in q._fields else False
            vencida = q.fecha_cronograma and q.fecha_cronograma < hoy
            filas.append({
                'nombre': q.name or '',
                'monto': g('monto') or 0.0,
                'fecha': fields.Date.to_string(q.fecha_cronograma) if q.fecha_cronograma else False,
                'pago': fields.Date.to_string(g('real_date')) if g('real_date') else False,
                'estado': self._etiqueta(q, 'state', q.state),
                'nivel': 'critico' if vencida else 'atencion',
                'saldo': g('saldo') or 0.0,
                'mora_total': g('mora_total') or 0.0,
                'mora_dias': g('mora_dias') or 0,
                'mora_estado': g('mora_estado_texto') or '',
                'mora_operacion': g('mora_operacion') or '',
                'periodicidad': self._etiqueta(q, 'periodicidad', g('periodicidad')) if g('periodicidad') else '',
                'asesora': self._m2o_texto(g('x_asesora')),
            })
        return filas

    def _m2o_texto(self, valor):
        if isinstance(valor, models.BaseModel):
            return valor.display_name or ''
        return valor or ''

    def _detalle_captura(self, c, hoy, supervisor):
        g = lambda f: c[f] if f in c._fields else False
        si_no = lambda b: 'Sí' if b else 'No'
        a_fecha = lambda d: fields.Date.to_string(d) if d else False
        activa = c.state in CAPTURA_ACTIVA
        pendiente = c.payment_state == 'pendiente'
        nivel = 'critico' if activa else ('ok' if c.state in ('liberado', 'recolocada') else 'neutral')
        compromiso = c.capture_type == 'compromiso'
        retraso = g('commitment_delay_days') or 0

        alertas = []
        if g('maintenance_taller_message'):
            alertas.append({'nivel': 'atencion', 'texto': c.maintenance_taller_message})
        if g('tiene_deuda_anterior'):
            anteriores = c.capturas_anteriores_ids
            alertas.append({'nivel': 'critico', 'texto': 'Deuda anterior: %s sin pagar en esta cuenta (%s) por S/ %.2f.' % (
                plural(len(anteriores), 'captura', 'capturas'), ', '.join(anteriores.mapped('name')),
                c.monto_deuda_anterior)})
        if compromiso and retraso and activa:
            alertas.append({'nivel': 'critico', 'texto': 'El compromiso de pago venció hace %s.' % plural(retraso, 'día', 'días')})
        if activa and pendiente:
            alertas.append({'nivel': 'atencion', 'texto': 'La deuda de intervención está pendiente de pago.'})

        marcas = [{'texto': self._etiqueta(c, 'capture_type', c.capture_type), 'nivel': 'info'}]
        if g('source_type') and c.source_type != 'none':
            marcas.append({'texto': 'Origen: %s' % self._etiqueta(c, 'source_type', c.source_type), 'nivel': 'neutral'})
        if 'moto_recogida' in c._fields:
            marcas.append({'texto': 'Moto recogida' if c.moto_recogida else 'Moto no recogida',
                           'nivel': 'ok' if c.moto_recogida else 'atencion'})

        kpis = [
            {'label': 'Intervención', 'monto': c.intervention_fee,
             'nivel': 'atencion' if activa and pendiente else False},
            {'label': 'Pago', 'texto': self._etiqueta(c, 'payment_state', c.payment_state),
             'nivel': ('atencion' if activa else False) if pendiente else 'ok'},
            {'label': 'Días de mora', 'texto': str(c.dias_mora or 0), 'nivel': 'critico' if c.dias_mora else False},
            {'label': 'Cuotas vencidas', 'texto': str(g('numero_cuotas_vencidas') or 0),
             'nivel': 'critico' if g('numero_cuotas_vencidas') else False},
            {'label': 'Fecha de captura', 'fecha': fields.Datetime.to_string(c.create_date)[:10]},
        ]
        if compromiso:
            kpis.append({'label': 'Compromiso de pago', 'fecha': a_fecha(g('commitment_date')),
                         'nivel': 'critico' if retraso else False,
                         'sub': ('%s de retraso' % plural(retraso, 'día', 'días')) if retraso else ''})
        if g('papeleta_id'):
            kpis.append({'label': 'Monto papeleta', 'monto': g('papeleta_monto') or 0.0})

        cuenta = c.cuenta_id
        grupos = [{
            'titulo': 'Información principal',
            'campos': self._campos(
                self._campo('Cliente', c.partner_id.display_name or False),
                self._campo('Cuenta', cuenta.display_name if cuenta else False),
                self._campo('Vehículo', c.vehicle_id.display_name or False),
                self._campo('Origen', self._etiqueta(c, 'source_type', g('source_type'))),
                self._campo('Papeleta', c.papeleta_id.display_name if g('papeleta_id') else False),
                self._campo('Tipo de cartera', self._etiqueta(c, 'tipo_cartera', g('tipo_cartera'))),
                self._campo('Capturador', c.capturador_id.name if g('capturador_id') else False),
                self._campo('Supervisor', c.supervisor_id.name if g('supervisor_id') else False),
                self._campo('Registrada', '%s · %s' % (c.create_uid.name, fields.Datetime.to_string(c.create_date)[:10])
                            if c.create_uid else False),
            ),
            'textos': [],
        }, {
            'titulo': 'Tipo de captura',
            'campos': self._campos(
                self._campo('Tipo', self._etiqueta(c, 'capture_type', c.capture_type)),
                self._campo('Fecha de compromiso', compromiso and a_fecha(g('commitment_date'))),
                self._campo('Días de retraso (compromiso)', retraso and plural(retraso, 'día', 'días')),
            ),
            'textos': self._campos(self._campo('Comentarios de captura', g('comentarios_captura'))),
        }, {
            'titulo': 'Deuda de intervención',
            'campos': self._campos(
                self._campo('Monto intervención', 'S/ %.2f' % (c.intervention_fee or 0.0)),
                self._campo('Estado de pago', self._etiqueta(c, 'payment_state', c.payment_state)),
                self._campo('Fecha de pago', a_fecha(g('payment_date'))),
                self._campo('N° de voucher', g('voucher_number')),
                self._campo('¿Pagó el monto?', si_no(g('pagar_monto')) if not pendiente else False),
            ),
            'textos': self._campos(self._campo('Motivo de no pago', g('motivo_no_pago'))),
        }, {
            'titulo': 'Recogida del vehículo',
            'campos': self._campos(self._campo('¿Moto recogida?', si_no(g('moto_recogida')))),
            'textos': self._campos(self._campo('Motivo si no se recogió', not g('moto_recogida') and g('motivo_no_recogida'))),
        }]
        if c.state == 'liberado' or g('liberacion_tipo'):
            grupos.append({
                'titulo': 'Liberación del vehículo',
                'campos': self._campos(self._campo('Tipo de liberación', self._etiqueta(c, 'liberacion_tipo', g('liberacion_tipo')))),
                'textos': self._campos(self._campo('Observaciones', g('observaciones'))),
            })
        if c.state in ('disolucion_contrato', 'recolocada') or g('retention_reason'):
            grupos.append({
                'titulo': 'Disolución de contrato',
                'campos': self._campos(
                    self._campo('Motivo', self._etiqueta(c, 'retention_reason', g('retention_reason'))),
                    self._campo('Fecha de inicio', a_fecha(g('retention_date'))),
                ),
                'textos': self._campos(self._campo('Observaciones adicionales', g('notes'))),
            })
        grupos = [gr for gr in grupos if gr['campos'] or gr['textos']]

        documentos = [d for d in (
            self._archivo_campo(c, 'voucher_file', g('voucher_filename') or 'Voucher %s' % (g('voucher_number') or '')),
            self._archivo_campo(c, 'documento_desafiliacion', 'Documento de desafiliación'),
            self._archivo_campo(c, 'evidencia_entrega', 'Evidencia de la entrega'),
        ) if d]
        apelaciones = []
        try:
            for ap in (g('appeal_ids') or []):
                apelaciones.append({'motivo': ap.appeal_reason or '',
                                    'archivo': self._archivo_campo(ap, 'appeal_evidence', 'Evidencia de apelación')})
        except AccessError:
            apelaciones = []

        M = 'adt.captura.record'
        boton = lambda metodo, label, icono, **kw: accion_metodo('adt.flota360', c.id, 'accion_captura', label, icono,
                                                                 args=[c.id, metodo], **kw)
        acciones, mas = [], []
        if activa and pendiente and self._metodo(M, 'action_registrar_pago'):
            acciones.append(boton('action_registrar_pago', 'Registrar pago', 'fa-money', primaria=True))
        if supervisor:
            if c.state in CAPTURA_ACTIVA and self._metodo(M, 'action_liberar'):
                acciones.append(boton('action_liberar', 'Liberar vehículo', 'fa-unlock',
                                      confirmar='¿Está seguro de liberar este vehículo?'))
            if c.state == 'capturado' and self._metodo(M, 'action_retener'):
                mas.append(boton('action_retener', 'Disolución de contrato', 'fa-ban'))
            if c.state == 'disolucion_contrato' and self._metodo(M, 'action_recolocar'):
                mas.append(boton('action_recolocar', 'Recolocar vehículo', 'fa-exchange',
                                 confirmar='¿Está seguro de recolocar este vehículo?'))
            if not g('es_estado_final') and c.state != 'recolocada' and self._metodo(M, 'action_cancelar'):
                mas.append(boton('action_cancelar', 'Cancelar captura', 'fa-times', peligro=True,
                                 confirmar='¿Está seguro de cancelar esta captura?'))
        if c.vehicle_id and 'adt.tvs.mantenimiento' in self.env and self._metodo(M, 'action_ver_mantenimientos'):
            mas.append(boton('action_ver_mantenimientos', 'Ver mantenimientos', 'fa-wrench'))
        if cuenta:
            mas.append(accion_tab('cuentas', 'Ver cuenta', 'fa-book'))
        mas.append(accion_abrir(M, c.id, 'Formulario completo'))

        return {
            'id': c.id,
            'activa': activa,
            'titulo': 'Captura %s' % c.name,
            'badge': {'texto': self._etiqueta(c, 'state', c.state), 'nivel': nivel},
            'marcas': marcas,
            'alertas': alertas,
            'kpis': kpis,
            'grupos': grupos,
            'evidencias': self._evidencias(g('evidencia_archivos') or self.env['ir.attachment']),
            'documentos': documentos,
            'apelaciones': apelaciones,
            'cuotas': self._cuotas_captura(c, hoy),
            'historial': self._historial(c),
            'acciones': acciones,
            'mas': mas,
        }

    def _seccion_capturas(self, v, hoy):
        Captura = self._modelo('adt.captura.record', 'vehicle_id')
        if Captura is None:
            return None
        capturas = Captura.search([('vehicle_id', '=', v.id)], order='id desc')
        capturas = capturas.sorted(lambda c: (c.state not in CAPTURA_ACTIVA, -c.id))
        activas = capturas.filtered(lambda c: c.state in CAPTURA_ACTIVA)
        por_pagar = capturas.filtered(lambda c: c.state in CAPTURA_ACTIVA and c.payment_state == 'pendiente')
        supervisor = self.env.user.has_group('adt_captura.group_captura_supervisor')
        if activas:
            a = activas[0]
            estado_cap = frase('critico', 'Vehículo capturado · %s' % self._etiqueta(a, 'state', a.state),
                               'Intervención por pagar %s' % self._soles(sum(por_pagar.mapped('intervention_fee'))) if por_pagar else '')
        elif capturas:
            estado_cap = frase('ok', 'Sin capturas activas', plural(len(capturas), 'captura anterior', 'capturas anteriores'))
        else:
            estado_cap = frase('ok', 'Nunca fue capturado')
        return {
            'key': 'capturas', 'titulo': 'Capturas', 'icon': 'fa-lock',
            'frase': estado_cap,
            'cifras': [
                cifra('Intervención por pagar', self._soles(sum(por_pagar.mapped('intervention_fee'))), 'fa-money',
                      nivel='atencion' if por_pagar else '', principal=True),
                cifra('Activas', str(len(activas)), 'fa-lock', nivel='critico' if activas else ''),
                cifra('Total de capturas', str(len(capturas)), 'fa-history'),
            ] if capturas else [],
            'capturas': [self._detalle_captura(c, hoy, supervisor) for c in capturas],
            'kpis': [
                {'label': 'Activas', 'texto': str(len(activas)), 'nivel': 'critico' if activas else 'ok'},
                {'label': 'Intervención por pagar', 'monto': sum(por_pagar.mapped('intervention_fee')),
                 'nivel': 'atencion' if por_pagar else False},
                {'label': 'Total de capturas', 'texto': str(len(capturas))},
            ] if capturas else [],
            'vacio': 'Sin capturas registradas.',
            'acciones': [accion_form('captura', 'Registrar captura', 'fa-plus')]
            if self.env['adt.comercial.cuentas'].search_count(
                [('vehiculo_id', '=', v.id), ('state', 'in', ('en_curso', 'aprobado'))]) else [],
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

    def _acciones_expediente(self, e):
        M = 'adt.expediente'
        principal = [accion_form('expediente_datos', 'Editar datos', 'fa-pencil', res_id=e.id)]
        if 'requisitos_cubiertos' in e._fields and e.requisitos_cubiertos:
            # Expediente en un solo archivo: no se genera PDF, se descarga el archivo cargado.
            principal.append(accion_url('/web/content/%s/%s/archivo_consolidado?download=true' % (M, e.id),
                                        'Descargar archivo', 'fa-download'))
        elif self._metodo(M, 'action_print_expediente_pdf'):
            principal.append(accion_metodo(M, e.id, 'action_print_expediente_pdf', 'PDF', 'fa-file-pdf-o'))
        mas = []
        for metodo, estado, label, icono in EXPEDIENTE_ESTADOS:
            if e.state != estado and self._metodo(M, metodo):
                mas.append(accion_metodo(M, e.id, metodo, label, icono,
                                         confirmar='¿%s? Se enviará una notificación push de cambio de estado.' % label))
        if e.state != 'rechazado' and self._metodo(M, 'action_rechazar'):
            mas.append(accion_metodo(M, e.id, 'action_rechazar', 'Rechazar expediente', 'fa-ban', peligro=True,
                                     confirmar='Se abrirá el formulario de rechazo para indicar el motivo.'))
        mas.append(accion_abrir(M, e.id, 'Formulario completo'))
        return principal, mas

    def _datos_expediente(self, e):
        """Datos declarados en el expediente (domicilio, trabajo, referencias)."""
        g = lambda c: e[c] if c in e._fields else False
        et = lambda c: self._etiqueta(e, c, e[c]) if c in e._fields and e[c] else False
        referencias = []
        for i in range(1, 5):
            nombre = g('ref_%s_name' % i)
            if nombre:
                referencias.append(' · '.join(filter(None, [nombre, g('ref_%s_phone' % i), et('ref_%s_vinculo' % i)])))
        mototaxista = g('cliente_occupation_code') == 'mototaxista'
        return {
            'campos': self._campos(
                self._campo('Moto solicitada', et('vehiculo')),
                self._campo('Asesora', e.asesora_id.name),
                self._campo('Dirección', g('direccion_cliente')),
                self._campo('Vivienda', ' · '.join(filter(None, [et('tipo_vivienda'), g('tiempo_viviendo')]))),
                self._campo('Ganancia', g('ganancia_diaria_mensual') if mototaxista else g('ganancia_diaria_mensual_no')),
                self._campo('Tiempo trabajando', g('tiempo_trabajando') if mototaxista else g('tiempo_trabajando_no')),
                self._campo('Beneficiario', ' · '.join(filter(None, [g('beneficiario_celular'), et('beneficiario_parentesco')]))),
                self._campo('Placa / chasis (fase final)', ' · '.join(filter(None, [g('placa'), g('chasis')]))),
            ),
            'referencias': referencias,
            'referencias_estado': g('estado_referencias'),
            'referencias_obs': g('obs_referencias') or '',
            'direccion_estado': g('estado_direccion'),
            'direccion_obs': g('obs_direccion') or '',
        }

    def _seccion_expediente(self, v, hoy):
        Expediente = self._modelo('adt.expediente', 'cliente_id', 'state')
        if Expediente is None:
            return None
        pids = self._clientes_de_turno(v, hoy)
        base = {'key': 'expediente', 'titulo': 'Expediente', 'icon': 'fa-folder-open-o', 'expedientes': []}
        if not pids:
            return dict(base, vacio='El vehículo no tiene cliente: elígelo al crear el crédito y luego registra su expediente.',
                        acciones=[accion_credito('Crear crédito', 'fa-credit-card')])
        expedientes = []
        for i, e in enumerate(Expediente.search([('cliente_id', 'in', pids)], order='fecha desc, id desc')):
            grupos, avance = self._documentos_expediente_grupos(e)
            principal, mas = self._acciones_expediente(e)
            nivel = EXPEDIENTE_NIVEL.get(e.state, 'neutral')
            # Un documento rechazado requiere acción aunque el estado general diga otra cosa.
            if avance['rechazados'] and e.state != 'rechazado':
                nivel = 'atencion'
            faltan = avance['requeridos'] - avance['completos']
            if e.state == 'rechazado':
                estado_exp = frase('critico', 'Expediente rechazado', e.motivo_rechazo or '')
            elif avance.get('cubierto'):
                estado_exp = frase('ok', 'Documentos completos', 'Cargados en un solo archivo')
            elif avance['rechazados']:
                estado_exp = frase('atencion', plural(avance['rechazados'], 'documento rechazado', 'documentos rechazados'),
                                   'El asesor debe corregirlos')
            elif faltan > 0:
                estado_exp = frase('atencion', 'Faltan %s' % plural(faltan, 'documento', 'documentos'),
                                   '%s de %s obligatorios cargados' % (avance['completos'], avance['requeridos']))
            else:
                estado_exp = frase('ok', 'Documentos completos', 'Listo para la revisión')
            expedientes.append({
                'id': e.id,
                'vigente': i == 0,
                'frase': estado_exp,
                'cifras': [
                    cifra('Documentos obligatorios', 'Completos' if avance.get('cubierto') else
                          '%s de %s' % (avance['completos'], avance['requeridos']), 'fa-files-o',
                          nivel='ok' if not faltan or avance.get('cubierto') else 'atencion', principal=True),
                    cifra('Rechazados', str(avance['rechazados']), 'fa-times-circle', nivel='critico' if avance['rechazados'] else ''),
                    cifra('Registrado', e.fecha.strftime('%d/%m/%Y') if e.fecha else '—', 'fa-calendar',
                          e.asesora_id.name and 'por %s' % e.asesora_id.name or ''),
                ],
                'titulo': 'Expediente del %s' % (e.fecha.strftime('%d/%m/%Y') if e.fecha else '—'),
                'cliente': e.cliente_id.name if len(pids) > 1 else '',
                'estado': self._etiqueta(e, 'state', e.state) or 'Por revisar',
                'nivel': 'info' if nivel == 'neutral' and e.state != 'rechazado' else nivel,
                'rechazo': e.motivo_rechazo if e.state == 'rechazado' and e.motivo_rechazo else '',
                'fecha_rechazo': e.fecha_rechazo.strftime('%d/%m/%Y') if e.state == 'rechazado' and e.fecha_rechazo else '',
                'avance': avance,
                'grupos': grupos,
                'consolidado': self._documento_consolidado(e),
                'datos': self._datos_expediente(e),
                'acciones': principal,
                'mas': mas,
            })
        nuevo = accion_form('expediente', 'Nuevo expediente', 'fa-plus', params={'cliente_id': pids[0]},
                            primaria=not expedientes)
        return dict(base, expedientes=expedientes, acciones=[nuevo],
                    vacio='El cliente no tiene expediente. Regístralo para revisar sus documentos antes del crédito.')

    def _seccion_taller(self, v, hoy):
        Orden = self._modelo('maintenance.work.order', 'vehicle_id')
        Regla = self._modelo('adt.mantenimiento.vehicle.rule.state', 'vehicle_id', 'estado')
        if Orden is None and Regla is None:
            return None
        items = []
        gastado = 0.0
        if Orden is not None:
            ordenes = Orden.search([('vehicle_id', '=', v.id)], order='id desc', limit=30)
            gastado = sum(ordenes.filtered(lambda o: o.state == 'done').mapped('total_amount'))
            for o in ordenes.sorted(lambda o: o.state == 'done'):
                items.append({
                    'grupo': 'abiertas' if o.state in TALLER_ABIERTO else 'historial',
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
                    'grupo': 'preventivo',
                    'titulo': 'Mantenimiento preventivo: %s' % r.regla_id.display_name,
                    'badge': {'texto': self._etiqueta(r, 'estado', r.estado), 'nivel': 'atencion'},
                    'acciones': [accion_abrir(r._name, r.id)],
                })
        abiertas = [i for i in items if i['grupo'] == 'abiertas']
        bloqueadas = [i for i in abiertas if i['badge']['nivel'] == 'atencion']
        preventivos = [i for i in items if i['grupo'] == 'preventivo']
        if bloqueadas:
            estado_taller = frase('atencion', '%s en taller' % plural(len(abiertas), 'orden abierta', 'órdenes abiertas'),
                                  plural(len(bloqueadas), 'bloqueada', 'bloqueadas'))
        elif abiertas:
            estado_taller = frase('info', 'En taller', plural(len(abiertas), 'orden abierta', 'órdenes abiertas'))
        elif preventivos:
            estado_taller = frase('atencion', 'Mantenimiento preventivo pendiente',
                                  plural(len(preventivos), 'campaña activa', 'campañas activas'))
        else:
            estado_taller = frase('ok', 'Sin trabajos pendientes')
        return {
            'key': 'taller', 'titulo': 'Taller y mantenimiento', 'icon': 'fa-wrench', 'items': items,
            'frase': estado_taller,
            'cifras': [
                cifra('Órdenes abiertas', str(len(abiertas)), 'fa-wrench', nivel='atencion' if bloqueadas else '', principal=True),
                cifra('Preventivos activos', str(len(preventivos)), 'fa-calendar-check-o'),
                cifra('Gastado en taller', self._soles(gastado), 'fa-money', 'órdenes terminadas'),
            ],
            'vacio': 'Sin órdenes de taller ni mantenimientos pendientes.',
            'acciones': [accion_form('orden_taller', 'Nueva orden', 'fa-plus', primaria=True,
                                     params={'cliente_id': v.driver_id.id})],
        }
