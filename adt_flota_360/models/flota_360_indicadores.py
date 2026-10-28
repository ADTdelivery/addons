# -*- coding: utf-8 -*-
"""Indicadores SAT Lima para gerencia (acción JS: adt_flota_360_indicadores).

Todo sale de las papeletas del SAT (adt.papeleta.sat): estados, antigüedad, deuda y
las más urgentes. Los filtros de financiera, cronograma y cliente son los de la
consulta de vehículos, así cada cifra coincide con la lista que abre.
"""
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .flota_360 import MAX_ANALISIS, PAPELETA_DIAS_ALERTA, nivel_sat, plural

GRUPO_GERENCIA = 'adt_comercial.group_access_adt_comercial_gerencia'
# Tramos de antigüedad de las pendientes (días desde la infracción): desde, hasta, etiqueta.
TRAMOS = (
    (0, PAPELETA_DIAS_ALERTA, 'Hasta 1 semana'),
    (PAPELETA_DIAS_ALERTA + 1, 30, '8 a 30 días'),
    (31, 90, '1 a 3 meses'),
    (91, 180, '3 a 6 meses'),
    (181, None, 'Más de 6 meses'),
)
MAX_URGENTES = 15
MAX_VEHICULOS = 10
MAX_FALTAS = 6
# Orden de prioridad de una papeleta pendiente (menor = más urgente).
PRIORIDAD = {'coactiva': 0, 'cautelar': 1, 'semana': 2, 'pendiente': 3}


class AdtFlota360Indicadores(models.AbstractModel):
    _inherit = 'adt.flota360'

    @api.model
    def indicadores(self, financiera=None, estado=None, clientes=None, grupo=None):
        if not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(_('Solo gerencia puede ver los indicadores del SAT.'))
        hoy = fields.Date.context_today(self)
        Sat = self._modelo('adt.papeleta.sat', 'vehicle_id', 'estado_pago', 'fecha_infraccion', 'deuda')
        base = {'fecha': fields.Date.to_string(hoy), 'disponible': Sat is not None}
        if Sat is None:
            return base

        vehiculos = self.env['fleet.vehicle'].search([], limit=MAX_ANALISIS)
        f = self._filtrar(self._resumenes(vehiculos), financiera, estado, grupo, clientes=clientes or 'todos')
        filtrado = financiera is not None or estado is not None or clientes not in (None, 'todos') or grupo is not None
        dominio = [('vehicle_id', 'in', [r['id'] for r in f['resumenes']])] if filtrado else []
        filas = Sat.search_read(dominio, [
            'name', 'placa', 'vehicle_id', 'fecha_infraccion', 'primera_vez_visto', 'ultima_vez_visto',
            'resuelta_en', 'importe', 'deuda', 'estado_sat', 'estado_pago', 'vigente', 'revision', 'codigo_falta',
        ])
        base.update(financieras=f['financieras'], estados=f['estados'], clientes=f['clientes'], grupos=f['grupos'],
                    filtrado=filtrado)
        base.update(self._sat_indicadores(filas, hoy, filtrado))
        return base

    # ------------------------------------------------------------------

    def _sat_fecha(self, valor):
        return fields.Datetime.context_timestamp(self, valor).date() if valor else False

    def _sat_tipo(self, fila, dias):
        """coactiva, cautelar, semana o pendiente (ver PRIORIDAD)."""
        texto = (fila['estado_sat'] or '').lower()
        if 'coactiv' in texto:
            return 'coactiva'
        if nivel_sat(fila['estado_sat']) == 'critico':
            return 'cautelar'  # medida cautelar, embargo, orden de captura
        return 'semana' if dias > PAPELETA_DIAS_ALERTA else 'pendiente'

    def _sat_indicadores(self, filas, hoy, filtrado):
        pendientes, pagadas = [], []
        for r in filas:
            r['monto'] = r['deuda'] or r['importe'] or 0.0
            desde = r['fecha_infraccion'] or self._sat_fecha(r['primera_vez_visto'])
            r['dias'] = (hoy - desde).days if desde else 0
            if r['estado_pago'] == 'pendiente':
                r['tipo'] = self._sat_tipo(r, r['dias'])
                pendientes.append(r)
            else:
                r['pagada_el'] = self._sat_fecha(r['resuelta_en'] or r['ultima_vez_visto'])
                pagadas.append(r)

        ids = lambda lista: [r['id'] for r in lista]
        monto = lambda lista: sum(r['monto'] for r in lista)
        de_tipo = lambda *tipos: [r for r in pendientes if r['tipo'] in tipos]
        coactivas, cautelares = de_tipo('coactiva'), de_tipo('cautelar')
        semana = [r for r in pendientes if r['dias'] > PAPELETA_DIAS_ALERTA]
        inicio_mes = hoy.replace(day=1)
        pagadas_mes = [r for r in pagadas if r['pagada_el'] and r['pagada_el'] >= inicio_mes]
        hace_semana = hoy - timedelta(days=7)
        nuevas = [r for r in filas if self._sat_fecha(r['primera_vez_visto']) and self._sat_fecha(r['primera_vez_visto']) > hace_semana]
        revisar = [r for r in filas if r['revision'] == 'pendiente']
        sin_vehiculo = [r for r in pendientes if not r['vehicle_id']]
        vehiculos_pend = {r['vehicle_id'][0] for r in pendientes if r['vehicle_id']}
        promedio = round(sum(r['dias'] for r in pendientes) / len(pendientes)) if pendientes else 0
        antigua = max(pendientes, key=lambda r: r['dias']) if pendientes else None

        def recuadro(key, label, icono, valor, sub, nivel, lista):
            return {'key': key, 'label': label, 'icon': icono, 'valor': valor, 'sub': sub, 'nivel': nivel, 'ids': ids(lista)}

        recuadros = [
            recuadro('deuda', 'Deuda total pendiente', 'fa-money', self._soles(monto(pendientes)),
                     '%s · %s' % (plural(len(pendientes), 'papeleta', 'papeletas'), plural(len(vehiculos_pend), 'vehículo', 'vehículos')),
                     'critico' if coactivas or cautelares or semana else ('atencion' if pendientes else 'ok'), pendientes),
            recuadro('coactiva', 'En coactiva', 'fa-gavel', str(len(coactivas)),
                     '%s · riesgo de captura' % self._soles(monto(coactivas)) if coactivas else 'Ninguna en cobranza coactiva',
                     'critico' if coactivas else 'ok', coactivas),
            recuadro('cautelar', 'Medida cautelar', 'fa-lock', str(len(cautelares)),
                     '%s · embargo u orden de captura' % self._soles(monto(cautelares)) if cautelares else 'Sin medidas cautelares',
                     'critico' if cautelares else 'ok', cautelares),
            recuadro('semana', 'Más de una semana sin pagar', 'fa-exclamation-triangle', str(len(semana)),
                     self._soles(monto(semana)) + ' por pagar' if semana else 'Todas dentro de la semana',
                     'critico' if semana else 'ok', semana),
            recuadro('atraso', 'Días de atraso promedio', 'fa-hourglass-half', plural(promedio, 'día', 'días'),
                     'La más antigua: %s (%s)' % (plural(antigua['dias'], 'día', 'días'), antigua['placa'] or antigua['name'])
                     if antigua else 'Sin papeletas pendientes',
                     'critico' if promedio > 30 else ('atencion' if promedio > PAPELETA_DIAS_ALERTA else 'ok'), pendientes),
            recuadro('nuevas', 'Nuevas en el SAT', 'fa-bell-o', str(len(nuevas)), 'Detectadas en los últimos 7 días',
                     'atencion' if nuevas else 'ok', nuevas),
            recuadro('pagadas', 'Pagadas este mes', 'fa-check-circle', str(len(pagadas_mes)),
                     '%s · %s en total' % (self._soles(sum(r['importe'] or 0.0 for r in pagadas_mes)),
                                           plural(len(pagadas), 'pagada', 'pagadas')), 'ok', pagadas_mes),
            recuadro('revisar', 'Por revisar', 'fa-search', str(len(revisar)),
                     'Dejaron de figurar sin confirmar el pago' if revisar else 'Nada por revisar',
                     'atencion' if revisar else 'ok', revisar),
        ]
        if not filtrado:
            # Con filtros solo cuentan las papeletas de los vehículos filtrados.
            recuadros.append(recuadro('sin_vehiculo', 'Pendientes sin vehículo', 'fa-question-circle', str(len(sin_vehiculo)),
                                      'La placa no coincide con la flota' if sin_vehiculo else 'Todas vinculadas a un vehículo',
                                      'atencion' if sin_vehiculo else 'ok', sin_vehiculo))

        return {
            'total': len(filas),
            'pendientes': len(pendientes),
            'recuadros': recuadros,
            'estados_sat': self._sat_estados(pendientes, pagadas, ids, monto),
            'antiguedad': self._sat_antiguedad(pendientes, ids, monto),
            'fechas': self._sat_fechas(filas, pendientes, pagadas_mes, nuevas, antigua),
            'urgentes': self._sat_urgentes(pendientes),
            'vehiculos': self._sat_vehiculos(pendientes),
            'faltas': self._sat_faltas(pendientes, ids, monto),
        }

    def _sat_estados(self, pendientes, pagadas, ids, monto):
        grupos = defaultdict(list)
        for r in pendientes:
            grupos[r['estado_sat'] or _('Sin estado')].append(r)
        orden = {'critico': 0, 'atencion': 1, 'info': 2, 'neutral': 3, 'ok': 4}
        estados = [{'label': k, 'nivel': nivel_sat(k) if k != _('Sin estado') else 'atencion', 'n': len(v),
                    'monto': monto(v), 'ids': ids(v)} for k, v in grupos.items()]
        estados.sort(key=lambda e: (orden.get(e['nivel'], 5), -e['n']))
        if pagadas:
            estados.append({'label': _('Pagadas'), 'nivel': 'ok', 'n': len(pagadas),
                            'monto': sum(r['importe'] or 0.0 for r in pagadas), 'ids': ids(pagadas)})
        return estados

    def _sat_antiguedad(self, pendientes, ids, monto):
        tramos = []
        for desde, hasta, label in TRAMOS:
            lista = [r for r in pendientes if r['dias'] >= desde and (hasta is None or r['dias'] <= hasta)]
            tramos.append({'label': label, 'n': len(lista), 'monto': monto(lista), 'ids': ids(lista),
                           'nivel': 'atencion' if hasta == PAPELETA_DIAS_ALERTA else 'critico'})
        return tramos

    def _sat_fechas(self, filas, pendientes, pagadas_mes, nuevas, antigua):
        a_texto = fields.Date.to_string
        con_fecha = [r for r in pendientes if r['fecha_infraccion']]
        reciente = max(con_fecha, key=lambda r: r['fecha_infraccion']) if con_fecha else None
        consultas = [r['ultima_vez_visto'] for r in filas if r['ultima_vez_visto']]
        return [
            {'label': 'Infracción pendiente más antigua', 'fecha': antigua and a_texto(antigua['fecha_infraccion'] or False),
             'sub': antigua and '%s · %s' % (antigua['placa'] or '-', plural(antigua['dias'], 'día', 'días')),
             'nivel': 'critico' if antigua and antigua['dias'] > PAPELETA_DIAS_ALERTA else ''},
            {'label': 'Infracción pendiente más reciente', 'fecha': reciente and a_texto(reciente['fecha_infraccion']),
             'sub': reciente and '%s · %s' % (reciente['placa'] or '-', plural(reciente['dias'], 'día', 'días'))},
            {'label': 'Última consulta al SAT', 'fecha_hora': fields.Datetime.to_string(max(consultas)) if consultas else False,
             'sub': 'Sincronización del monitor'},
            {'label': 'Nuevas en los últimos 7 días', 'texto': str(len(nuevas)), 'sub': 'Papeletas detectadas por primera vez'},
            {'label': 'Pagadas este mes', 'texto': str(len(pagadas_mes)), 'sub': 'Según el SAT o al dejar de figurar', 'nivel': 'ok'},
        ]

    def _nombres_clientes(self, vehicle_ids):
        Vehicle = self.env['fleet.vehicle']
        if 'driver_id' not in Vehicle._fields:
            return {}
        return {v['id']: self._m2o(v['driver_id']) for v in Vehicle.browse(list(vehicle_ids)).read(['driver_id'])}

    def _sat_urgentes(self, pendientes):
        lista = sorted(pendientes, key=lambda r: (PRIORIDAD[r['tipo']], -r['dias'], -r['monto']))[:MAX_URGENTES]
        clientes = self._nombres_clientes({r['vehicle_id'][0] for r in lista if r['vehicle_id']})
        motivo = {
            'coactiva': lambda r: 'En coactiva',
            'cautelar': lambda r: r['estado_sat'] or 'Medida cautelar',
            'semana': lambda r: '%s sin pagar' % plural(r['dias'], 'día', 'días'),
            'pendiente': lambda r: 'Pendiente de pago',
        }
        return [{
            'id': r['id'],
            'numero': r['name'],
            'placa': r['placa'] or '',
            'vehicle_id': self._id(r['vehicle_id']),
            'cliente': clientes.get(self._id(r['vehicle_id']), ''),
            'estado': r['estado_sat'] or 'Pendiente',
            'motivo': motivo[r['tipo']](r),
            'nivel': 'atencion' if r['tipo'] == 'pendiente' else 'critico',
            'fecha': fields.Date.to_string(r['fecha_infraccion']) if r['fecha_infraccion'] else False,
            'dias': r['dias'],
            'monto': r['monto'],
        } for r in lista]

    def _sat_vehiculos(self, pendientes):
        por_vehiculo = defaultdict(list)
        for r in pendientes:
            if r['vehicle_id']:
                por_vehiculo[r['vehicle_id'][0]].append(r)
        top = sorted(por_vehiculo.items(), key=lambda kv: -sum(r['monto'] for r in kv[1]))[:MAX_VEHICULOS]
        clientes = self._nombres_clientes([vid for vid, _l in top])
        res = []
        for vid, lista in top:
            criticas = [r for r in lista if r['tipo'] != 'pendiente']
            res.append({
                'vehicle_id': vid,
                'placa': lista[0]['placa'] or lista[0]['vehicle_id'][1],
                'cliente': clientes.get(vid, ''),
                'n': len(lista),
                'monto': sum(r['monto'] for r in lista),
                'dias': max(r['dias'] for r in lista),
                'coactivas': sum(1 for r in lista if r['tipo'] in ('coactiva', 'cautelar')),
                'nivel': 'critico' if criticas else 'atencion',
            })
        return res

    def _sat_faltas(self, pendientes, ids, monto):
        grupos = defaultdict(list)
        for r in pendientes:
            grupos[r['codigo_falta'] or _('Sin código')].append(r)
        top = sorted(grupos.items(), key=lambda kv: -len(kv[1]))[:MAX_FALTAS]
        return [{'label': k, 'n': len(v), 'monto': monto(v), 'ids': ids(v)} for k, v in top]
