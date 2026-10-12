# -*- coding: utf-8 -*-
"""Indicadores operativos del dashboard de flota.

Criterios (ver README del módulo):
* Excepciones primero: las alertas resumen lo que requiere acción.
* Métricas de flujo: trabajo en curso por etapa, antigüedad de cada moto en su etapa,
  tiempos de ciclo (mediana y P85, no promedio) y ritmo semanal de entradas/salidas.
* Antigüedad del stock en tramos de 30 días.
"""
import math
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models

from .fleet_dashboard import plate_is_ready

VENTANA_DIAS = 90               # historia usada para tiempos de ciclo y umbrales P85
SEMANAS = 8                     # ritmo semanal
MIN_MUESTRAS = 5                # mínimo de casos cerrados para usar el P85 como umbral
TRAMITE_SIN_INICIAR_DIAS = 7
STOCK_ENVEJECIDO_DIAS = 60
TRAMOS_STOCK = [(0, 30, '0–30 días'), (31, 60, '31–60 días'), (61, 90, '61–90 días'), (91, None, 'Más de 90 días')]
ESTADOS_PLACA_WIP = ['pendiente', 'en_tramite', 'observado']


def percentil(valores, p):
    """Percentil por rango más cercano (sin interpolar)."""
    if not valores:
        return None
    orden = sorted(valores)
    return orden[max(0, math.ceil(p / 100 * len(orden)) - 1)]


def dias(delta):
    # Nunca negativo: create_date viene del reloj de la base y puede ir unos segundos adelante.
    return max(0.0, delta.total_seconds() / 86400)


def redondear(valor):
    return None if valor is None else round(valor, 1)


def resumen_tiempos(valores):
    return {'n': len(valores), 'mediana': redondear(percentil(valores, 50)), 'p85': redondear(percentil(valores, 85))}


def abrir(model, ids):
    return {'model': model, 'ids': sorted(set(ids))}


class AdtFleetDashboardOperacion(models.AbstractModel):
    _inherit = 'adt.fleet.dashboard'

    # ------------------------------------------------------------------ carga
    @api.model
    def _operacion_contexto(self):
        ahora = fields.Datetime.now()
        vehiculos = self.env['fleet.vehicle'].search([])
        trackings = self.env['adt.moto.tracking'].search([('vehicle_id', 'in', vehiculos.ids)])
        tramites = self.env['adt.tramite.placa'].search([('vehicle_id', 'in', vehiculos.ids)])
        Log = self.env['adt.moto.tracking.log']

        abiertos = {}
        for log in Log.search([('tracking_id', 'in', trackings.ids), ('fecha_fin', '=', False),
                               ('flujo', 'in', ('logistica', 'placa'))]):
            abiertos[(log.tracking_id.id, log.flujo)] = log

        # Duraciones cerradas en la ventana: base de tiempos de ciclo y de umbrales P85.
        duraciones = defaultdict(list)
        por_taller = defaultdict(list)
        for log in Log.search([('fecha_fin', '>=', ahora - timedelta(days=VENTANA_DIAS)),
                               ('flujo', 'in', ('logistica', 'placa'))]):
            valor = dias(log.fecha_fin - log.fecha_inicio)
            duraciones[(log.flujo, log.codigo_hasta)].append(valor)
            if log.flujo == 'logistica' and log.codigo_hasta == 'fibra' and log.taller_fibra_id:
                por_taller[log.taller_fibra_id.id].append(valor)
        # La etapa "listo" no se cierra al asignar: su historia es lo que tardó en asignarse.
        desde = ahora - timedelta(days=VENTANA_DIAS)
        for t in trackings:
            if t.fecha_listo and t.fecha_asignacion and not t.asignado_antes_listo \
                    and t.fecha_asignacion >= max(desde, t.fecha_listo):
                duraciones[('logistica', 'listo')].append(dias(t.fecha_asignacion - t.fecha_listo))

        return {
            'ahora': ahora,
            'vehiculos': vehiculos,
            'trackings': trackings,
            'tramites': tramites,
            'tracking_por_vehiculo': {t.vehicle_id.id: t for t in trackings},
            'tramite_por_vehiculo': {t.vehicle_id.id: t for t in tramites},
            'abiertos': abiertos,
            'duraciones': duraciones,
            'por_taller': por_taller,
            'etapas': self.env['adt.moto.tracking.etapa'].search([]),
        }

    @staticmethod
    def _tiene_placa(vehiculo, tramite):
        return plate_is_ready(vehiculo.license_plate) or bool(tramite and tramite.state in ('finalizado', 'historial'))

    @staticmethod
    def _umbral(ctx, flujo, codigo, sla_horas=0.0):
        """Días a partir de los cuales una moto está en riesgo: SLA configurado o, si no hay, P85 histórico."""
        if sla_horas:
            return sla_horas / 24, 'SLA'
        historia = ctx['duraciones'].get((flujo, codigo), [])
        if len(historia) >= MIN_MUESTRAS:
            return percentil(historia, 85), 'P85'
        return None, None

    # ------------------------------------------------------------------ bloques
    @api.model
    def _operacion_kpis_y_matriz(self, ctx):
        celdas = {k: [] for k in ('stock_sin_placa', 'stock_con_placa', 'duenio_sin_placa', 'duenio_con_placa')}
        desglose = {k: defaultdict(list) for k in ('stock_sin_placa', 'duenio_sin_placa')}
        listas_entregar, con_placa = [], []
        for v in ctx['vehiculos']:
            tramite = ctx['tramite_por_vehiculo'].get(v.id)
            tracking = ctx['tracking_por_vehiculo'].get(v.id)
            placa = self._tiene_placa(v, tramite)
            clave = ('duenio_' if v.driver_id else 'stock_') + ('con_placa' if placa else 'sin_placa')
            celdas[clave].append(v.id)
            if placa:
                con_placa.append(v.id)
            else:
                desglose[clave][tramite.state if tramite else 'sin_tramite'].append(v.id)
            if clave == 'stock_con_placa' and (not tracking or tracking.etapa_codigo == 'listo'):
                listas_entregar.append(v.id)

        total = len(ctx['vehiculos'])
        stock = celdas['stock_sin_placa'] + celdas['stock_con_placa']
        kpis = [
            {'codigo': 'flota', 'label': 'Flota activa', 'valor': total, 'sub': 'vehículos',
             'ayuda': 'Todos los vehículos activos registrados en flota.',
             'abrir': abrir('fleet.vehicle', ctx['vehiculos'].ids)},
            {'codigo': 'con_placa', 'label': 'Con placa', 'valor': len(con_placa), 'base': total,
             'sub_base': 'de la flota', 'ayuda': 'Vehículos con placa real o trámite finalizado.',
             'abrir': abrir('fleet.vehicle', con_placa)},
            {'codigo': 'stock', 'label': 'Stock disponible', 'valor': len(stock), 'base': total,
             'sub_base': 'de la flota', 'ayuda': 'Vehículos sin dueño asignado.',
             'abrir': abrir('fleet.vehicle', stock), 'hero': True},
            {'codigo': 'listas', 'label': 'Listas para entregar', 'valor': len(listas_entregar), 'base': len(stock),
             'sub_base': 'del stock', 'ayuda': 'Sin dueño, con placa y con la logística terminada (fibra lista).',
             'abrir': abrir('fleet.vehicle', listas_entregar)},
            {'codigo': 'completo', 'label': 'Proceso completo', 'valor': len(celdas['duenio_con_placa']),
             'base': total, 'sub_base': 'de la flota', 'ayuda': 'Con dueño y con placa.',
             'abrir': abrir('fleet.vehicle', celdas['duenio_con_placa'])},
        ]
        matriz = {
            clave: {
                'valor': len(ids),
                'abrir': abrir('fleet.vehicle', ids),
                'desglose': {estado: {'valor': len(vids), 'abrir': abrir('fleet.vehicle', vids)}
                             for estado, vids in desglose.get(clave, {}).items()},
            }
            for clave, ids in celdas.items()
        }
        return kpis, matriz, total

    @api.model
    def _operacion_wip(self, ctx):
        """Trabajo en curso por etapa con su antigüedad y las motos que superan el umbral."""
        ahora = ctx['ahora']
        logistica = []
        en_riesgo_logistica = []
        for etapa in ctx['etapas']:
            activos = ctx['trackings'].filtered(
                lambda t: t.etapa_id == etapa and t.estado_global != 'entregado'
                and not (t.etapa_codigo == 'listo' and t.partner_id))
            umbral, fuente = self._umbral(ctx, 'logistica', etapa.codigo, etapa.sla_horas)
            edades, riesgo = [], []
            for t in activos:
                edad = dias(ahora - (t.fecha_etapa or t.create_date))
                limite = umbral
                if etapa.codigo == 'fibra' and t.taller_fibra_id.sla_horas:
                    limite = t.taller_fibra_id.sla_horas / 24
                edades.append(edad)
                if limite is not None and edad > limite:
                    riesgo.append(t.id)
            en_riesgo_logistica += riesgo
            logistica.append({
                'codigo': etapa.codigo, 'nombre': etapa.name, 'valor': len(activos),
                'abrir': abrir('adt.moto.tracking', activos.ids),
                'edad_mediana': redondear(percentil(edades, 50)), 'edad_max': redondear(max(edades) if edades else None),
                'umbral': redondear(umbral), 'umbral_fuente': fuente,
                'en_riesgo': len(riesgo), 'abrir_riesgo': abrir('adt.moto.tracking', riesgo),
            })

        etiquetas = dict(ctx['tramites']._fields['state']._description_selection(self.env))
        placa = []
        en_riesgo_placa = []
        for estado in ESTADOS_PLACA_WIP:
            activos = ctx['tramites'].filtered(lambda tp: tp.state == estado)
            umbral, fuente = self._umbral(ctx, 'placa', estado)
            edades, riesgo = [], []
            for tp in activos:
                tracking = ctx['tracking_por_vehiculo'].get(tp.vehicle_id.id)
                log = tracking and ctx['abiertos'].get((tracking.id, 'placa'))
                desde = (log and log.fecha_inicio) or {
                    'pendiente': tp.create_date,
                    'en_tramite': tp.fecha_inicio,
                    'observado': tp.fecha_ultima_observacion,
                }[estado] or tp.create_date
                edad = dias(ahora - desde)
                edades.append(edad)
                if umbral is not None and edad > umbral:
                    riesgo.append(tp.id)
            if estado != 'pendiente':  # "pendiente" tiene su propia alerta (sin iniciar)
                en_riesgo_placa += riesgo
            placa.append({
                'codigo': estado, 'nombre': etiquetas.get(estado, estado), 'valor': len(activos),
                'abrir': abrir('adt.tramite.placa', activos.ids),
                'edad_mediana': redondear(percentil(edades, 50)), 'edad_max': redondear(max(edades) if edades else None),
                'umbral': redondear(umbral), 'umbral_fuente': fuente,
                'en_riesgo': len(riesgo), 'abrir_riesgo': abrir('adt.tramite.placa', riesgo),
            })
        finalizados = ctx['tramites'].filtered(lambda tp: tp.state in ('finalizado', 'historial'))
        placa.append({'codigo': 'finalizado', 'nombre': etiquetas.get('finalizado', 'Finalizado'),
                      'valor': len(finalizados), 'abrir': abrir('adt.tramite.placa', finalizados.ids), 'cerrado': True})
        return {'logistica': logistica, 'placa': placa}, en_riesgo_logistica, en_riesgo_placa

    @api.model
    def _operacion_alertas(self, ctx, matriz, riesgo_logistica, riesgo_placa):
        ahora = ctx['ahora']
        trk = ctx['tracking_por_vehiculo']
        alertas = []

        def agregar(codigo, severidad, titulo, descripcion, model, ids, vehiculos, detalle=None):
            alertas.append({
                'codigo': codigo, 'severidad': severidad, 'titulo': titulo, 'descripcion': descripcion,
                'valor': len(set(ids)), 'abrir': abrir(model, ids), 'detalle': detalle,
                'vehiculos': sorted(set(vehiculos)),
            })

        # Crítico: el cliente ya tiene la moto y no tiene placa.
        sin_placa = matriz['duenio_sin_placa']['abrir']['ids']
        esperas = [dias(ahora - trk[v].fecha_asignacion) for v in sin_placa
                   if v in trk and trk[v].fecha_asignacion]
        sin_iniciar = [v for v in sin_placa if ctx['tramite_por_vehiculo'].get(v) is None
                       or ctx['tramite_por_vehiculo'][v].state == 'pendiente']
        agregar('cliente_sin_placa', 'critico', 'Clientes sin placa',
                'Motos asignadas cuyo trámite de placa no ha terminado.',
                'fleet.vehicle', sin_placa, sin_placa,
                detalle=' · '.join(filter(None, [
                    '%d sin iniciar' % len(sin_iniciar) if sin_iniciar else '',
                    'máx. %d d' % max(esperas) if esperas and max(esperas) >= 1 else '',
                ])))

        observados = ctx['tramites'].filtered(lambda tp: tp.state == 'observado')
        espera_obs = [dias(ahora - tp.fecha_ultima_observacion) for tp in observados if tp.fecha_ultima_observacion]
        agregar('placa_observada', 'critico', 'Trámites observados',
                'El trámite está detenido hasta levantar la observación.',
                'adt.tramite.placa', observados.ids, observados.vehicle_id.ids,
                detalle='máx. %d d' % max(espera_obs) if espera_obs and max(espera_obs) >= 1 else None)

        # Alto: trabajo detenido.
        limite = ahora - timedelta(days=TRAMITE_SIN_INICIAR_DIAS)
        sin_iniciar_tp = ctx['tramites'].filtered(lambda tp: tp.state == 'pendiente' and tp.create_date < limite)
        agregar('tramite_sin_iniciar', 'alto', 'Trámites sin iniciar',
                'Motos facturadas cuyo trámite de placa sigue en Pendiente hace más de %d días.' % TRAMITE_SIN_INICIAR_DIAS,
                'adt.tramite.placa', sin_iniciar_tp.ids, sin_iniciar_tp.vehicle_id.ids)

        trk_riesgo = self.env['adt.moto.tracking'].browse(riesgo_logistica)
        agregar('etapa_demorada', 'alto', 'Demoradas en su etapa',
                'Llevan más tiempo que el SLA de la etapa o que el 85%% de los casos de los últimos %d días.' % VENTANA_DIAS,
                'adt.moto.tracking', trk_riesgo.ids, trk_riesgo.vehicle_id.ids,
                detalle=', '.join('%s: %d' % (e.name, len(trk_riesgo.filtered(lambda t: t.etapa_id == e)))
                                  for e in ctx['etapas'] if trk_riesgo.filtered(lambda t: t.etapa_id == e)))

        tp_riesgo = self.env['adt.tramite.placa'].browse(riesgo_placa)
        agregar('placa_demorada', 'alto', 'Trámites lentos',
                'En trámite u observados por más tiempo que el 85%% de los trámites de los últimos %d días.' % VENTANA_DIAS,
                'adt.tramite.placa', tp_riesgo.ids, tp_riesgo.vehicle_id.ids)

        # Medio: riesgo comercial y calidad del proceso.
        stock_ids = matriz['stock_sin_placa']['abrir']['ids'] + matriz['stock_con_placa']['abrir']['ids']
        viejos = [v for v in stock_ids if self._dias_en_stock(ctx, v) > STOCK_ENVEJECIDO_DIAS]
        agregar('stock_envejecido', 'medio', 'Stock envejecido',
                'Motos sin dueño con más de %d días en la empresa.' % STOCK_ENVEJECIDO_DIAS, 'fleet.vehicle', viejos, viejos)

        antes = ctx['trackings'].filtered(lambda t: t.asignado_antes_listo and t.estado_global != 'entregado')
        agregar('asignada_antes', 'medio', 'Asignadas sin terminar',
                'Se entregaron a un cliente sin terminar la logística (fibra).',
                'adt.moto.tracking', antes.ids, antes.vehicle_id.ids)

        fuera = [v.id for v in ctx['vehiculos'] if v.id not in trk and not (
            self._tiene_placa(v, ctx['tramite_por_vehiculo'].get(v.id)) and v.driver_id)]
        agregar('fuera_flujo', 'medio', 'Fuera del flujo',
                'Les falta placa o dueño y no tienen tracking. Use «Sincronizar vehículos».',
                'fleet.vehicle', fuera, fuera)

        orden = {'critico': 0, 'alto': 1, 'medio': 2}
        alertas.sort(key=lambda a: (orden[a['severidad']], -a['valor']))
        return alertas

    @api.model
    def _dias_en_stock(self, ctx, vehicle_id):
        tracking = ctx['tracking_por_vehiculo'].get(vehicle_id)
        vehiculo = self.env['fleet.vehicle'].browse(vehicle_id)
        inicio = (tracking and tracking.fecha_recojo) or vehiculo.create_date
        return dias(ctx['ahora'] - inicio)

    @api.model
    def _operacion_antiguedad_stock(self, ctx, matriz):
        stock_ids = matriz['stock_sin_placa']['abrir']['ids'] + matriz['stock_con_placa']['abrir']['ids']
        tramos = [{'label': label, 'ids': []} for _desde, _hasta, label in TRAMOS_STOCK]
        for v in stock_ids:
            edad = self._dias_en_stock(ctx, v)
            for i, (desde, hasta, _label) in enumerate(TRAMOS_STOCK):
                if edad >= desde and (hasta is None or edad < hasta + 1):
                    tramos[i]['ids'].append(v)
                    break
        return [{'label': t['label'], 'valor': len(t['ids']), 'abrir': abrir('fleet.vehicle', t['ids'])}
                for t in tramos]

    @api.model
    def _operacion_tiempos(self, ctx):
        desde = ctx['ahora'] - timedelta(days=VENTANA_DIAS)
        dur = ctx['duraciones']
        etapas = {e.codigo: e.name for e in ctx['etapas']}
        etiquetas = dict(ctx['tramites']._fields['state']._description_selection(self.env))
        trackings = ctx['trackings']

        def entre(registros, inicio, fin, condicion=None):
            valores = []
            for r in registros:
                a, b = r[inicio], r[fin]
                if a and b and b >= a and b >= desde and (condicion is None or condicion(r)):
                    valores.append(dias(b - a))
            return valores

        filas = [
            dict(resumen_tiempos(dur.get(('logistica', c), [])), grupo='Logística', nombre=etapas.get(c, c))
            for c in ('recojo', 'almacen', 'fibra')
        ]
        filas.append(dict(resumen_tiempos(dur.get(('logistica', 'listo'), [])),
                          grupo='Logística', nombre='En stock hasta venderse'))
        filas += [
            dict(resumen_tiempos(dur.get(('placa', c), [])), grupo='Placa', nombre=etiquetas.get(c, c))
            for c in ESTADOS_PLACA_WIP
        ]
        filas += [
            dict(resumen_tiempos(entre(trackings, 'fecha_recojo', 'fecha_listo')),
                 grupo='De punta a punta', nombre='Recojo hasta quedar lista'),
            dict(resumen_tiempos(entre(ctx['tramites'], 'fecha_inicio', 'fecha_fin')),
                 grupo='De punta a punta', nombre='Trámite completo'),
            dict(resumen_tiempos(entre(trackings, 'fecha_asignacion', 'fecha_placa_ok')),
                 grupo='De punta a punta', nombre='Cliente esperando placa'),
        ]
        return filas

    @api.model
    def _operacion_ritmo(self, ctx):
        """Unidades por semana (lunes a domingo, hora local) en las últimas SEMANAS."""
        local = self.with_context(tz=self.env.user.tz or 'America/Lima')
        hoy = fields.Datetime.context_timestamp(local, ctx['ahora']).date()
        lunes = hoy - timedelta(days=hoy.weekday())
        semanas = [lunes - timedelta(weeks=i) for i in range(SEMANAS - 1, -1, -1)]

        def por_semana(fechas):
            conteo = [0] * SEMANAS
            for f in fechas:
                if not f:
                    continue
                dia = fields.Datetime.context_timestamp(local, f).date()
                indice = (dia - semanas[0]).days // 7
                if 0 <= indice < SEMANAS:
                    conteo[indice] += 1
            return conteo

        trackings = ctx['trackings']
        series = [
            {'codigo': 'entradas', 'label': 'Motos que entran al flujo', 'valores': por_semana(trackings.mapped('create_date'))},
            {'codigo': 'listas', 'label': 'Quedan listas para asignar', 'valores': por_semana(trackings.mapped('fecha_listo'))},
            {'codigo': 'asignadas', 'label': 'Se asignan a un cliente', 'valores': por_semana(trackings.mapped('fecha_asignacion'))},
            {'codigo': 'placas', 'label': 'Placas finalizadas', 'valores': por_semana(ctx['tramites'].mapped('fecha_fin'))},
        ]
        ultimas = 4
        entradas = sum(series[0]['valores'][-ultimas:])
        asignadas = sum(series[2]['valores'][-ultimas:])
        return {
            'semanas': [s.strftime('%d/%m') for s in semanas],
            'series': series,
            'balance': {'semanas': ultimas, 'entradas': entradas, 'asignadas': asignadas},
        }

    @api.model
    def _operacion_talleres(self, ctx, wip):
        ahora = ctx['ahora']
        fibra = next((e for e in wip['logistica'] if e['codigo'] == 'fibra'), None)
        en_riesgo = set(fibra['abrir_riesgo']['ids']) if fibra else set()
        en_fibra = ctx['trackings'].filtered(lambda t: t.etapa_codigo == 'fibra' and t.estado_global != 'entregado')
        filas = []
        for taller in self.env['adt.moto.tracking.taller'].search([]) | en_fibra.taller_fibra_id:
            actuales = en_fibra.filtered(lambda t: t.taller_fibra_id == taller)
            historia = ctx['por_taller'].get(taller.id, [])
            edades = [dias(ahora - (t.fecha_etapa or t.create_date)) for t in actuales]
            riesgo = [t.id for t in actuales if t.id in en_riesgo]
            filas.append({
                'nombre': taller.name, 'valor': len(actuales), 'abrir': abrir('adt.moto.tracking', actuales.ids),
                'edad_max': redondear(max(edades) if edades else None),
                'en_riesgo': len(riesgo), 'abrir_riesgo': abrir('adt.moto.tracking', riesgo),
                'historia': resumen_tiempos(historia),
            })
        filas.sort(key=lambda f: (-f['en_riesgo'], -f['valor'], f['nombre']))
        return filas

    # ------------------------------------------------------------------ entrada
    @api.model
    def get_operacion_data(self):
        ctx = self._operacion_contexto()
        kpis, matriz, total = self._operacion_kpis_y_matriz(ctx)
        wip, riesgo_logistica, riesgo_placa = self._operacion_wip(ctx)
        alertas = self._operacion_alertas(ctx, matriz, riesgo_logistica, riesgo_placa)
        con_alerta = sorted({v for a in alertas for v in a['vehiculos']})
        kpis.append({'codigo': 'alertas', 'label': 'Motos con alertas', 'valor': len(con_alerta), 'base': total,
                     'sub_base': 'de la flota', 'ayuda': 'Motos que aparecen en al menos una alerta operativa.',
                     'abrir': abrir('fleet.vehicle', con_alerta), 'alerta': True})
        return {
            'generado': fields.Datetime.to_string(ctx['ahora']),
            'ventana_dias': VENTANA_DIAS,
            'kpis': kpis,
            'alertas': alertas,
            'matriz': matriz,
            'wip': wip,
            'tiempos': self._operacion_tiempos(ctx),
            'ritmo': self._operacion_ritmo(ctx),
            'antiguedad_stock': self._operacion_antiguedad_stock(ctx, matriz),
            'talleres': self._operacion_talleres(ctx, wip),
            'vistas': self._operacion_vistas(),
        }

    @api.model
    def _operacion_vistas(self):
        """Los vehículos se abren con vistas simples: no exigen permisos de Flota."""
        lista = self.env.ref('adt_tracking_moto.fleet_vehicle_view_tree_operacion', raise_if_not_found=False)
        ficha = self.env.ref('adt_tracking_moto.fleet_vehicle_view_form_operacion', raise_if_not_found=False)
        if not (lista and ficha):  # módulo aún sin actualizar: vistas estándar
            return {}
        return {'fleet.vehicle': [[lista.id, 'list'], [ficha.id, 'form']]}
