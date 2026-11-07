# -*- coding: utf-8 -*-
"""Pestaña «Captura SAT» de la vista SAT (acción JS: adt_flota_360_indicadores).

Cruza las órdenes de captura del SAT Lima (adt.captura.sat, de adt_captura_sat) con:

* la flota: vehículo vinculado, o encontrado por placa / placa original si la orden no
  quedó vinculada; cliente, razón social, financiera y captura interna en curso;
* las papeletas: el documento de la orden suele ser el número de la papeleta, así que se
  busca en las papeletas del SAT (adt.papeleta.sat) y, si no está, en las internas
  (adt.papeleta).

Con eso cada orden lleva sus «hallazgos» (riesgo de captura en la calle, papeleta pagada
con la orden aún vigente, placa fuera de la flota…) y se prioriza la lista.
Los filtros de financiera, cronograma y cliente son los de la pestaña de papeletas.
"""
import re
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .flota_360 import MAX_ANALISIS, plural
from .flota_360_indicadores import GRUPO_GERENCIA

MAX_FILAS = 200
DIAS_NUEVAS = 7
DIAS_LEVANTADAS = 30
NIVEL_ORDEN = {'critico': 0, 'atencion': 1, 'info': 2, 'ok': 3}


def _clave(texto):
    """Placa / número sin espacios ni símbolos, en mayúsculas."""
    return re.sub(r'[^A-Z0-9]', '', (texto or '').upper())


def _clave_documento(texto):
    """Número de documento comparable: solo dígitos y sin ceros a la izquierda."""
    clave = _clave(texto)
    digitos = re.sub(r'[^0-9]', '', clave).lstrip('0')
    return digitos or clave


def _es_papeleta(concepto):
    """«Inf. RNT», «Papeleta»…: órdenes por infracciones de tránsito (no deuda tributaria)."""
    texto = (concepto or '').lower()
    return any(p in texto for p in ('inf', 'papeleta', 'rnt', 'tránsito', 'transito'))


class AdtFlota360CapturaSat(models.AbstractModel):
    _inherit = 'adt.flota360'

    @api.model
    def capturas_sat(self, financiera=None, estado=None, clientes=None, grupo=None):
        if not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(_('Solo gerencia puede ver las capturas del SAT.'))
        hoy = fields.Date.context_today(self)
        Orden = self._modelo('adt.captura.sat', 'vehicle_id', 'vigente', 'monto', 'placa_original', 'gestion')
        base = {'fecha': fields.Date.to_string(hoy), 'disponible': Orden is not None}
        if Orden is None:
            return base

        vehiculos = self.env['fleet.vehicle'].search([], limit=MAX_ANALISIS)
        resumenes = self._resumenes(vehiculos)
        f = self._filtrar(resumenes, financiera, estado, grupo, clientes=clientes or 'todos')
        filtrado = financiera is not None or estado is not None or clientes not in (None, 'todos') or grupo is not None
        resumen_de = {r['id']: r for r in (f['resumenes'] if filtrado else resumenes)}

        campos = ['name', 'placa', 'placa_original', 'vehicle_id', 'concepto', 'anio', 'referencia', 'monto',
                  'primera_vez_visto', 'ultima_vez_visto', 'levantada_en', 'vigente', 'gestion', 'responsable_id']
        vigentes = Orden.search_read([('vigente', '=', True)], campos)
        desde = fields.Datetime.to_string(fields.Datetime.now() - timedelta(days=DIAS_LEVANTADAS))
        levantadas = Orden.search_read([('vigente', '=', False), ('levantada_en', '>=', desde)], campos)

        self._cap_vehiculos(vigentes + levantadas)
        if filtrado:
            # Entra la orden si cualquiera de sus dos vehículos (placa actual u original) está en el filtro.
            en_filtro = lambda o: o['_vid'] in resumen_de or o['_vid_original'] in resumen_de
            vigentes = [o for o in vigentes if en_filtro(o)]
            levantadas = [o for o in levantadas if en_filtro(o)]
        self._cap_contexto(vigentes, resumen_de)
        self._cap_papeletas(vigentes)
        for o in vigentes:
            o['hallazgos'] = self._cap_hallazgos(o)
            o['nivel'] = min((h['nivel'] for h in o['hallazgos']), key=lambda n: NIVEL_ORDEN[n], default='info')

        base.update(financieras=f['financieras'], estados=f['estados'], clientes=f['clientes'], grupos=f['grupos'],
                    filtrado=filtrado)
        base.update(self._cap_indicadores(vigentes, levantadas, hoy, filtrado, resumen_de))
        return base

    # ------------------------------------------------------------------ cruce

    def _cap_vehiculos(self, ordenes):
        """Los dos vehículos posibles de cada orden.

        * _vid_actual: el vinculado a la orden o, si no hay, el de la placa actual;
        * _vid_original: el de la placa original, cuando el SAT la publica distinta;
        * _vid: el principal (actual o, si no está en la flota, el original).
        """
        Sat = self.env['adt.papeleta.sat'] if 'adt.papeleta.sat' in self.env else None
        cache = {}

        def buscar(placa):
            placa = _clave(placa)
            if not placa or Sat is None:
                return False
            if placa not in cache:
                cache[placa] = Sat._buscar_vehiculo(placa).id
            return cache[placa]

        for o in ordenes:
            o['_cambio_placa'] = bool(o['placa_original']) and _clave(o['placa_original']) != _clave(o['placa'])
            o['_vid_original'] = buscar(o['placa_original']) if o['_cambio_placa'] else False
            if o['vehicle_id']:
                o['_vid_actual'], o['_match'] = o['vehicle_id'][0], 'vinculado'
            elif buscar(o['placa']):
                o['_vid_actual'], o['_match'] = buscar(o['placa']), 'placa'
            else:
                o['_vid_actual'] = False
                o['_match'] = 'placa_original' if o['_vid_original'] else 'sin_flota'
            if o['_vid_original'] == o['_vid_actual']:
                o['_vid_original'] = False  # la placa original es del mismo vehículo
            o['_vid'] = o['_vid_actual'] or o['_vid_original']

    def _cap_contexto(self, ordenes, resumen_de):
        """Resumen de los vehículos de cada orden: cliente, razón social, financiera, captura interna…"""
        vids = {v for o in ordenes for v in (o['_vid_actual'], o['_vid_original']) if v}
        faltan = vids - set(resumen_de)
        resumen_de = dict(resumen_de)  # copia: los vehículos extra no cuentan en la cobertura del filtro
        Vehicle = self.env['fleet.vehicle'].with_context(active_test=False)
        if faltan:
            # Vehículos archivados, fuera del análisis o fuera del filtro (la placa original de otro vehículo).
            for r in self._resumenes(Vehicle.browse(list(faltan))):
                resumen_de[r['id']] = r
        extra = {}
        campos = [c for c in ('active', 'captura_sat_estado', 'captura_sat_count') if c in Vehicle._fields]
        if vids:
            extra = {v['id']: v for v in Vehicle.browse(list(vids)).read(campos)}

        def tarjeta(vid):
            r = resumen_de.get(vid)
            if not r:
                return None
            cliente = r.get('cliente') or {}
            interna = next((m for m in r.get('modulos', []) if m['key'] == 'capturas'), None)
            x = extra.get(vid, {})
            return {
                'id': r['id'],
                'placa': r['placa'],
                'nombre': ' '.join(filter(None, [r.get('marca'), r.get('modelo')])),
                'anio': r.get('anio') or '',
                'color': r.get('color') or '',
                'chasis': r.get('chasis') or '',
                'estado': r.get('estado') or '',
                'cliente': cliente.get('nombre') or '',
                'documento': cliente.get('documento') or '',
                'telefono': cliente.get('telefono') or '',
                'con_cliente': not r.get('stock'),
                'razon_social': r.get('razon_social') or '',
                'financiera': r.get('financiera') or '',
                'captura_interna': interna['texto'] if interna else '',
                'captura_sat': self._etiqueta(Vehicle, 'captura_sat_estado', x.get('captura_sat_estado')),
                'ordenes_sat': x.get('captura_sat_count') or 0,
                'archivado': not x.get('active', True),
                'alertas': [a['texto'] for a in (r.get('alertas') or [])[:3]],
            }

        for o in ordenes:
            o['_vehiculo_actual'] = tarjeta(o['_vid_actual'])
            o['_vehiculo_original'] = tarjeta(o['_vid_original'])
            o['_vehiculo'] = o['_vehiculo_actual'] or o['_vehiculo_original'] or {}

    def _cap_papeletas(self, ordenes):
        """Papeleta SAT o interna del documento de cada orden (el documento es el número de la papeleta)."""
        claves = {_clave_documento(o['name']) for o in ordenes if o['name']}
        for o in ordenes:
            o['_papeleta'] = None
        if not claves:
            return
        Sat = self._modelo('adt.papeleta.sat', 'estado_pago', 'deuda', 'papeleta_id')
        por_clave = defaultdict(list)
        if Sat is not None:
            self.env.cr.execute("""
                SELECT id FROM adt_papeleta_sat
                 WHERE ltrim(regexp_replace(coalesce(name, ''), '[^0-9]', '', 'g'), '0') IN %s
                    OR regexp_replace(upper(coalesce(name, '')), '[^A-Z0-9]', '', 'g') IN %s
            """, (tuple(claves), tuple(claves)))
            # El SQL solo ubica candidatas; la búsqueda aplica las reglas de acceso (compañía).
            ids = [r[0] for r in self.env.cr.fetchall()]
            for p in Sat.search([('id', 'in', ids)]).read(['name', 'placa', 'estado_pago', 'estado_sat', 'deuda', 'importe',
                                           'fecha_infraccion', 'codigo_falta', 'papeleta_id', 'vehicle_id']):
                por_clave[_clave_documento(p['name'])].append(p)

        Interna = self._modelo('adt.papeleta', 'name', 'state', 'monto')
        for o in ordenes:
            candidatas = por_clave.get(_clave_documento(o['name'])) or []
            # Prioridad: misma placa que la orden; luego, la del mismo vehículo; luego, cualquiera.
            exacta = [p for p in candidatas if _clave(p['placa']) in (_clave(o['placa']), _clave(o['placa_original']))]
            suyos = {v for v in (o['_vid_actual'], o['_vid_original']) if v}
            mismo_vehiculo = [p for p in candidatas if self._id(p['vehicle_id']) in suyos]
            p = (exacta or mismo_vehiculo or candidatas or [None])[0]
            if p:
                o['_papeleta'] = {
                    'tipo': 'sat', 'id': p['id'], 'numero': p['name'],
                    'coincide': 'exacta' if exacta else ('vehiculo' if mismo_vehiculo else 'documento'),
                    'placa': p['placa'] or '',
                    'pagada': p['estado_pago'] != 'pendiente',
                    'estado': p['estado_sat'] or ('Pagada' if p['estado_pago'] != 'pendiente' else 'Pendiente'),
                    'deuda': p['deuda'] or p['importe'] or 0.0,
                    'falta': p['codigo_falta'] or '',
                    'fecha': fields.Date.to_string(p['fecha_infraccion']) if p['fecha_infraccion'] else False,
                    'interna': self._m2o(p['papeleta_id']),
                    'interna_id': self._id(p['papeleta_id']),
                }
                continue
            if Interna is None or 'adt.papeleta.sat' not in self.env:
                continue
            internas = Interna.search([('id', 'in', self.env['adt.papeleta.sat']._candidatas_internas(o['name']).ids)])
            if len(internas) == 1:
                i = internas.read(['name', 'state', 'monto', 'vehicle_id'])[0]
                o['_papeleta'] = {
                    'tipo': 'interna', 'id': i['id'], 'numero': i['name'], 'coincide': 'documento',
                    'placa': '', 'pagada': i['state'] == 'pagado', 'estado': self._etiqueta(Interna, 'state', i['state']),
                    'deuda': i['monto'] or 0.0, 'falta': '', 'fecha': False, 'interna': i['name'], 'interna_id': i['id'],
                }

    def _cap_hallazgos(self, o):
        """Lo que hay que saber de la orden, del más al menos grave."""
        h = []
        add = lambda nivel, texto: h.append({'nivel': nivel, 'texto': texto})
        v, p = o['_vehiculo'], o['_papeleta']
        if v and v['captura_interna']:
            add('info', _('Vehículo ya retenido por ADT (%s)') % v['captura_interna'])
        elif v and v['con_cliente']:
            add('critico', _('Moto con cliente: puede ser capturada en la calle'))
        elif v:
            add('atencion', _('Moto en stock con orden de captura'))
        if o['_match'] == 'sin_flota':
            add('atencion', _('La placa no está en la flota'))
        elif o['_match'] == 'placa':
            add('atencion', _('Encontrado por placa: la orden no está vinculada al vehículo'))
        elif o['_match'] == 'placa_original':
            add('atencion', _('Encontrado por placa original %s') % o['placa_original'])
        elif o['_cambio_placa']:
            add('info', _('Placa original distinta: %s') % o['placa_original'])
        if o['_vehiculo_actual'] and o['_vehiculo_original']:
            orig = o['_vehiculo_original']
            add('critico' if orig['con_cliente'] and not orig['captura_interna'] else 'atencion',
                _('La placa original %s es de otro vehículo de la flota%s: dos vehículos afectados')
                % (o['placa_original'], ' (con cliente: %s)' % orig['cliente'] if orig['con_cliente'] else ''))
        if v and v.get('archivado'):
            add('atencion', _('El vehículo está archivado'))
        if p and p['pagada']:
            add('atencion', _('Papeleta %s pagada, pero la orden sigue vigente') % p['numero'])
        elif p and p['coincide'] == 'documento' and p['placa']:
            add('atencion', _('La papeleta %s figura con otra placa (%s)') % (p['numero'], p['placa']))
        elif p and p['tipo'] == 'sat' and abs((p['deuda'] or 0.0) - (o['monto'] or 0.0)) >= 1:
            add('info', _('Monto en captura %s y deuda de la papeleta %s') % (self._soles(o['monto']), self._soles(p['deuda'])))
        elif not p and _es_papeleta(o['concepto']):
            add('atencion', _('Papeleta sin registrar: no figura en las papeletas SAT ni internas'))
        elif not p:
            add('info', _('Concepto «%s»: no es una papeleta de tránsito') % (o['concepto'] or _('sin concepto')))
        if o['gestion'] == 'nueva':
            add('info', _('Sin gestionar'))
        return sorted(h, key=lambda x: NIVEL_ORDEN[x['nivel']])

    # -------------------------------------------------------------- indicadores

    def _cap_indicadores(self, vigentes, levantadas, hoy, filtrado, resumen_de):
        fecha = lambda valor: self._sat_fecha(valor)
        for o in vigentes:
            o['dias'] = (hoy - fecha(o['primera_vez_visto'])).days if o['primera_vez_visto'] else 0
        ids = lambda lista: [o['id'] for o in lista]
        monto = lambda lista: sum(o['monto'] or 0.0 for o in lista)
        con = lambda cond: [o for o in vigentes if cond(o)]

        con_cliente = con(lambda o: o['_vehiculo'] and o['_vehiculo']['con_cliente'] and not o['_vehiculo']['captura_interna'])
        en_stock = con(lambda o: o['_vehiculo'] and not o['_vehiculo']['con_cliente'])
        retenidas = con(lambda o: o['_vehiculo'] and o['_vehiculo']['captura_interna'])
        sin_flota = con(lambda o: o['_match'] == 'sin_flota')
        sin_vincular = con(lambda o: o['_match'] in ('placa', 'placa_original'))
        con_papeleta = con(lambda o: o['_papeleta'])
        pagadas = con(lambda o: o['_papeleta'] and o['_papeleta']['pagada'])
        sin_registrar = con(lambda o: not o['_papeleta'] and _es_papeleta(o['concepto']))
        sin_gestion = con(lambda o: o['gestion'] == 'nueva')
        hace = hoy - timedelta(days=DIAS_NUEVAS)
        nuevas = con(lambda o: o['primera_vez_visto'] and fecha(o['primera_vez_visto']) > hace)
        placas = {o['_vid'] or _clave(o['placa']) for o in vigentes}

        def recuadro(key, label, icono, valor, sub, nivel, lista, modelo='adt.captura.sat'):
            return {'key': key, 'label': label, 'icon': icono, 'valor': valor, 'sub': sub, 'nivel': nivel,
                    'ids': ids(lista) if modelo == 'adt.captura.sat' else lista, 'modelo': modelo}

        recuadros = [
            recuadro('vigentes', 'Órdenes de captura vigentes', 'fa-lock', str(len(vigentes)),
                     '%s · %s' % (self._soles(monto(vigentes)), plural(len(placas), 'vehículo', 'vehículos')),
                     'critico' if vigentes else 'ok', vigentes),
            recuadro('con_cliente', 'Motos con cliente', 'fa-exclamation-circle', str(len(con_cliente)),
                     'Pueden ser capturadas en la calle' if con_cliente else 'Ninguna moto con cliente en captura',
                     'critico' if con_cliente else 'ok', con_cliente),
            recuadro('stock', 'Motos en stock', 'fa-cubes', str(len(en_stock)),
                     'Regularizar antes de entregarlas' if en_stock else 'Ninguna en stock con orden',
                     'atencion' if en_stock else 'ok', en_stock),
            recuadro('retenidas', 'Ya retenidas por ADT', 'fa-shield', str(len(retenidas)),
                     'Con captura interna en curso', 'ok', retenidas),
            recuadro('pagadas', 'Papeleta pagada, orden vigente', 'fa-check-square-o', str(len(pagadas)),
                     'Pedir el levantamiento al SAT' if pagadas else 'Sin pagos por levantar',
                     'atencion' if pagadas else 'ok', pagadas),
            recuadro('con_papeleta', 'Con papeleta identificada', 'fa-link', str(len(con_papeleta)),
                     '%s sin registrar' % plural(len(sin_registrar), 'papeleta', 'papeletas') if sin_registrar
                     else 'Todas las papeletas cruzadas', 'atencion' if sin_registrar else 'ok', con_papeleta),
            recuadro('nuevas', 'Nuevas en el SAT', 'fa-bell-o', str(len(nuevas)),
                     'Detectadas en los últimos %s días' % DIAS_NUEVAS, 'atencion' if nuevas else 'ok', nuevas),
            recuadro('sin_gestion', 'Sin gestionar', 'fa-inbox', str(len(sin_gestion)),
                     'Órdenes sin responsable ni gestión' if sin_gestion else 'Todas en gestión',
                     'atencion' if sin_gestion else 'ok', sin_gestion),
            recuadro('levantadas', 'Levantadas', 'fa-unlock', str(len(levantadas)),
                     'Dejaron de figurar en los últimos %s días' % DIAS_LEVANTADAS, 'ok', levantadas),
        ]
        if not filtrado:
            recuadros.insert(5, recuadro('sin_flota', 'Fuera de la flota', 'fa-question-circle',
                                         str(len(sin_flota) + len(sin_vincular)),
                                         '%s sin vehículo · %s sin vincular' % (len(sin_flota), len(sin_vincular)),
                                         'atencion' if sin_flota or sin_vincular else 'ok', sin_flota + sin_vincular))

        # Cobertura: vehículos (del filtro) que nunca se consultaron en el SAT.
        Vehicle = self.env['fleet.vehicle']
        cobertura = None
        if 'captura_sat_estado' in Vehicle._fields and resumen_de:
            filas = Vehicle.browse(list(resumen_de)).read(['captura_sat_estado', 'captura_sat_ultima_consulta'])
            sin_consultar = [v['id'] for v in filas if v['captura_sat_estado'] == 'sin_consultar']
            ultima = max((v['captura_sat_ultima_consulta'] for v in filas if v['captura_sat_ultima_consulta']), default=False)
            cobertura = {'total': len(filas), 'sin_consultar': len(sin_consultar),
                         'ultima': fields.Datetime.to_string(ultima) if ultima else False}
            recuadros.append(recuadro('cobertura', 'Sin consultar en el SAT', 'fa-search', str(len(sin_consultar)),
                                      'de %s · nunca se buscó su placa' % plural(len(filas), 'vehículo', 'vehículos'),
                                      'atencion' if sin_consultar else 'ok', sin_consultar, modelo='fleet.vehicle'))

        def barras(clave, vacio):
            grupos = defaultdict(list)
            for o in vigentes:
                grupos[clave(o) or vacio].append(o)
            filas = [{'label': k, 'n': len(v), 'monto': monto(v), 'ids': ids(v)} for k, v in grupos.items()]
            return sorted(filas, key=lambda x: (-x['n'], -x['monto']))

        veh = lambda o: o['_vehiculo'] or {}
        return {
            'total': len(vigentes),
            'monto': monto(vigentes),
            'vehiculos_n': len(placas),
            'recuadros': recuadros,
            'por_concepto': barras(lambda o: o['concepto'], _('Sin concepto')),
            'por_razon_social': barras(lambda o: veh(o).get('razon_social') or (
                _('Sin razón social') if o['_vehiculo'] else _('Fuera de la flota')), ''),
            'por_financiera': barras(lambda o: veh(o).get('financiera'), _('Sin financiera')),
            'filas': self._cap_filas(vigentes),
            'cobertura': cobertura,
        }

    def _cap_filas(self, vigentes):
        """Una fila por vehículo (o placa fuera de la flota), con sus órdenes y papeletas."""
        grupos = defaultdict(list)
        for o in vigentes:
            clave = ('v', o['_vid']) if o['_vid'] else ('p', _clave(o['placa']))
            grupos[clave + (o['_vid_original'] or _clave(o['placa_original']) if o['_cambio_placa'] else '',)].append(o)
        filas = []
        for lista in grupos.values():
            hallazgos, vistos = [], set()
            for o in lista:
                for h in o['hallazgos']:
                    if h['texto'] not in vistos:
                        vistos.add(h['texto'])
                        hallazgos.append(h)
            hallazgos.sort(key=lambda x: NIVEL_ORDEN[x['nivel']])
            primera = lista[0]
            filas.append({
                'placa': primera['placa'],
                'vehicle_id': primera['_vid'] or False,
                'match': primera['_match'],
                'vehiculo': primera['_vehiculo'] or None,
                'placa_original': primera['placa_original'] if primera['_cambio_placa'] else '',
                'vehiculo_actual': primera['_vehiculo_actual'],
                'vehiculo_original': primera['_vehiculo_original'],
                'nivel': hallazgos[0]['nivel'] if hallazgos else 'info',
                'hallazgos': hallazgos,
                'monto': sum(o['monto'] or 0.0 for o in lista),
                'dias': max(o['dias'] for o in lista),
                'ordenes': [{
                    'id': o['id'], 'documento': o['name'], 'concepto': o['concepto'] or '', 'anio': o['anio'] or '',
                    'referencia': o['referencia'] or '', 'placa_original': o['placa_original'] or '',
                    'monto': o['monto'] or 0.0, 'dias': o['dias'],
                    'detectada': fields.Datetime.to_string(o['primera_vez_visto']) if o['primera_vez_visto'] else False,
                    'ultima_consulta': fields.Datetime.to_string(o['ultima_vez_visto']) if o['ultima_vez_visto'] else False,
                    'hallazgos': o['hallazgos'],
                    'gestion': self._etiqueta(self.env['adt.captura.sat'], 'gestion', o['gestion']),
                    'responsable': self._m2o(o['responsable_id']),
                    'papeleta': o['_papeleta'],
                } for o in sorted(lista, key=lambda o: -(o['monto'] or 0.0))],
            })
        filas.sort(key=lambda r: (NIVEL_ORDEN[r['nivel']], -r['monto'], -r['dias']))
        return filas[:MAX_FILAS]
