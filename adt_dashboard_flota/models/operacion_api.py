# -*- coding: utf-8 -*-
"""API de solo lectura del proceso de cada moto: stock, logística (fibra) y trámite de placa.

Mismas reglas que el dashboard "Operación de motos" (get_operacion_data): la app y gerencia
ven los mismos números. Ningún método escribe en la base.
"""
from odoo import api, fields, models

from .fleet_dashboard import plate_is_ready
from .stock_service import SIN_ANIO, SIN_COLOR, StockApiError

ALCANCES = ('stock', 'flota')
ESTADOS_PLACA_API = ('sin_tramite', 'pendiente', 'en_tramite', 'observado', 'finalizado')
ETAPAS_API = ('recojo', 'almacen', 'fibra', 'listo')


def _fecha(valor):
    return fields.Datetime.to_string(valor) if valor else None


def _dias(valor):
    return round(valor, 1) if valor else 0.0


class AdtFleetDashboardOperacionApi(models.AbstractModel):
    _inherit = 'adt.fleet.dashboard'

    # ------------------------------------------------------------------ armado
    @api.model
    def _api_contexto_proceso(self, vehicle_ids):
        trackings = self.env['adt.moto.tracking'].search([('vehicle_id', 'in', vehicle_ids)])
        tramites = self.env['adt.tramite.placa'].search([('vehicle_id', 'in', vehicle_ids)])
        etiquetas = {
            'global': dict(trackings._fields['estado_global']._description_selection(self.env)),
            'tramite': dict(tramites._fields['state']._description_selection(self.env)),
        }
        return {
            'tracking': {t.vehicle_id.id: t for t in trackings},
            'tramite': {t.vehicle_id.id: t for t in tramites},
            'etiquetas': etiquetas,
        }

    @api.model
    def _api_logistica_dict(self, tracking):
        if not tracking:
            return None
        return {
            'etapa': tracking.etapa_codigo,
            'etapa_texto': tracking.etapa_id.name,
            'paso': ETAPAS_API.index(tracking.etapa_codigo) + 1 if tracking.etapa_codigo in ETAPAS_API else None,
            'total_pasos': len(ETAPAS_API),
            'desde': _fecha(tracking.fecha_etapa),
            'dias_en_etapa': _dias(tracking.dias_etapa),
            'demorado': bool(tracking.demorado),
            'taller_fibra': tracking.taller_fibra_id.name or None,
            'fechas': {
                'recojo': _fecha(tracking.fecha_recojo),
                'ingreso_almacen': _fecha(tracking.fecha_ingreso_almacen),
                'envio_fibra': _fecha(tracking.fecha_envio_fibra),
                'listo': _fecha(tracking.fecha_listo),
                'asignacion': _fecha(tracking.fecha_asignacion),
                'entrega': fields.Date.to_string(tracking.fecha_entrega) if tracking.fecha_entrega else None,
            },
        }

    @api.model
    def _api_placa_proceso_dict(self, tramite, etiquetas):
        if not tramite:
            return {'estado': 'sin_tramite', 'estado_texto': 'Sin trámite', 'numero': None, 'inicio': None,
                    'fin': None, 'dias_tramite': 0.0, 'dias_sin_iniciar': 0.0, 'veces_observado': 0,
                    'observacion': None}
        # Historial = finalizado archivado de la vista diaria: para la app es "finalizado".
        estado = 'finalizado' if tramite.state == 'historial' else tramite.state
        return {
            'estado': estado,
            'estado_texto': etiquetas['tramite'].get(estado, estado),
            'numero': tramite.num_placa or None,
            'inicio': _fecha(tramite.fecha_inicio),
            'fin': _fecha(tramite.fecha_fin),
            'dias_tramite': _dias(tramite.dias_tramite),
            'dias_sin_iniciar': _dias(tramite.dias_sin_iniciar),
            'veces_observado': tramite.cant_observaciones,
            'observacion': tramite.motivo_observacion if estado == 'observado' else None,
        }

    @api.model
    def _api_moto_dict(self, row, ctx):
        tracking = ctx['tracking'].get(row['id'])
        tramite = ctx['tramite'].get(row['id'])
        placa_proceso = self._api_placa_proceso_dict(tramite, ctx['etiquetas'])
        con_placa = plate_is_ready(row['plate']) or placa_proceso['estado'] == 'finalizado'
        logistica_lista = not tracking or tracking.etapa_codigo == 'listo'
        if tracking:
            estado_general = tracking.estado_global
            estado_general_texto = ctx['etiquetas']['global'].get(estado_general, estado_general)
        else:
            estado_general, estado_general_texto = 'fuera_del_flujo', 'Fuera del flujo'
        return {
            'id': row['id'],
            'placa': row['plate'] if plate_is_ready(row['plate']) else None,
            'chasis': row['vin'] or None,
            'motor': row['motor'] or None,
            'marca': row['brand'],
            'modelo': row['model'],
            'modelo_id': row['model_id'] or None,
            'anio': None if row['year'] == SIN_ANIO else row['year'],
            'color': None if row['color'] == SIN_COLOR else row['color'],
            'imagen_url': self._imagen_modelo_url(row['model_id']),
            'disponible': not row['has_owner'],
            'con_placa': con_placa,
            'lista_para_entregar': not row['has_owner'] and con_placa and logistica_lista,
            'estado_general': estado_general,
            'estado_general_texto': estado_general_texto,
            'tracking_ref': tracking.name if tracking else None,
            'logistica': self._api_logistica_dict(tracking),
            'placa_proceso': placa_proceso,
        }

    # ------------------------------------------------------------------ filtros
    @api.model
    def _api_filtrar_motos(self, motos, filtros):
        filtros = filtros or {}
        if not isinstance(filtros, dict):
            raise StockApiError('parametros_invalidos', 'filtros debe ser un objeto.')
        etapa = self._texto(filtros.get('etapa'), 'etapa')
        estado_placa = self._texto(filtros.get('estado_placa'), 'estado_placa')
        modelo_id = self._entero(filtros.get('modelo_id'), 'modelo_id', None, minimo=1)
        texto = self._texto(filtros.get('texto'), 'texto').upper()
        if etapa and etapa not in ETAPAS_API:
            raise StockApiError('parametros_invalidos', 'etapa debe ser uno de: %s.' % ', '.join(ETAPAS_API))
        if estado_placa and estado_placa not in ESTADOS_PLACA_API:
            raise StockApiError('parametros_invalidos',
                                'estado_placa debe ser uno de: %s.' % ', '.join(ESTADOS_PLACA_API))
        booleanos = {}
        for clave in ('demorado', 'con_duenio', 'lista_para_entregar'):
            valor = filtros.get(clave)
            if valor is not None and not isinstance(valor, bool):
                raise StockApiError('parametros_invalidos', 'El campo %s debe ser true o false.' % clave)
            booleanos[clave] = valor

        def coincide(m):
            if etapa and (m['logistica'] or {}).get('etapa') != etapa:
                return False
            if estado_placa and m['placa_proceso']['estado'] != estado_placa:
                return False
            if modelo_id and m['modelo_id'] != modelo_id:
                return False
            if booleanos['demorado'] is not None and bool((m['logistica'] or {}).get('demorado')) != booleanos['demorado']:
                return False
            if booleanos['con_duenio'] is not None and (not m['disponible']) != booleanos['con_duenio']:
                return False
            if booleanos['lista_para_entregar'] is not None and m['lista_para_entregar'] != booleanos['lista_para_entregar']:
                return False
            if texto:
                pajar = ' '.join(filter(None, [m['placa'], m['chasis'], m['motor'], m['modelo'], m['marca'],
                                               m['color'], m['tracking_ref'], m['placa_proceso']['numero']])).upper()
                if texto not in pajar:
                    return False
            return True

        return [m for m in motos if coincide(m)]

    # ------------------------------------------------------------------ servicios
    @api.model
    def api_operacion_resumen(self):
        """Totales, combinaciones dueño × placa, carga por etapa y alertas (sin listas de ids)."""
        data = self.get_operacion_data()
        return {
            'generado': data['generado'],
            'totales': {k['codigo']: k['valor'] for k in data['kpis']},
            'combinaciones': {
                clave: {
                    'cantidad': celda['valor'],
                    'por_estado_placa': {estado: d['valor'] for estado, d in celda['desglose'].items()},
                }
                for clave, celda in data['matriz'].items()
            },
            'logistica': [
                {'etapa': e['codigo'], 'etapa_texto': e['nombre'], 'cantidad': e['valor'],
                 'en_riesgo': e['en_riesgo'], 'mediana_dias': e['edad_mediana']}
                for e in data['wip']['logistica']
            ],
            'placa': [
                {'estado': e['codigo'], 'estado_texto': e['nombre'], 'cantidad': e['valor'],
                 'en_riesgo': e.get('en_riesgo', 0), 'mediana_dias': e.get('edad_mediana')}
                for e in data['wip']['placa']
            ],
            'talleres_fibra': [
                {'taller': t['nombre'], 'en_fibra': t['valor'], 'en_riesgo': t['en_riesgo'],
                 'mediana_historica_dias': t['historia']['mediana']}
                for t in data['talleres']
            ],
            'alertas': [
                {'codigo': a['codigo'], 'severidad': a['severidad'], 'titulo': a['titulo'],
                 'descripcion': a['descripcion'], 'detalle': a['detalle'], 'cantidad': a['valor']}
                for a in data['alertas'] if a['valor']
            ],
        }

    @api.model
    def api_operacion_motos(self, alcance='stock', filtros=None, limite=20, offset=0):
        """Motos con su proceso completo. alcance: 'stock' (sin dueño) o 'flota' (todas las activas)."""
        alcance = self._texto(alcance, 'alcance') or 'stock'
        if alcance not in ALCANCES:
            raise StockApiError('parametros_invalidos', 'alcance debe ser uno de: %s.' % ', '.join(ALCANCES))
        limite = self._entero(limite, 'limite', 20, minimo=1, maximo=100)
        offset = self._entero(offset, 'offset', 0)
        rows = self._vehicle_rows([('driver_id', '=', False)] if alcance == 'stock' else [])
        ctx = self._api_contexto_proceso([r['id'] for r in rows])
        motos = self._api_filtrar_motos([self._api_moto_dict(r, ctx) for r in rows], filtros)
        # Primero lo que se puede entregar ya; luego lo más avanzado en el proceso.
        motos.sort(key=lambda m: (not m['lista_para_entregar'], -((m['logistica'] or {}).get('paso') or 0),
                                  m['modelo'], m['id']))
        return {
            'alcance': alcance,
            'total': len(motos),
            'limite': limite,
            'offset': offset,
            'motos': motos[offset:offset + limite],
        }

    @api.model
    def api_operacion_moto_detalle(self, vehiculo_id):
        """Una moto con su proceso y la línea de tiempo de cada cambio (logística, placa e hitos)."""
        vehiculo_id = self._entero(vehiculo_id, 'vehiculo_id', None, minimo=1)
        if not vehiculo_id:
            raise StockApiError('parametros_invalidos', 'El campo vehiculo_id es obligatorio.')
        rows = self._vehicle_rows([('id', '=', vehiculo_id)])
        if not rows:
            raise StockApiError('no_encontrado', 'El vehículo no existe o está archivado.')
        ctx = self._api_contexto_proceso([vehiculo_id])
        moto = self._api_moto_dict(rows[0], ctx)
        tracking = ctx['tracking'].get(vehiculo_id)
        flujos = dict(self.env['adt.moto.tracking.log']._fields['flujo']._description_selection(self.env))
        linea = []
        if tracking:
            for log in tracking.log_ids.sorted(lambda l: (l.fecha_inicio, l.id)):
                linea.append({
                    'flujo': log.flujo,
                    'flujo_texto': flujos.get(log.flujo, log.flujo),
                    'desde': log.etapa_desde or None,
                    'hacia': log.etapa_hasta or None,
                    'codigo': log.codigo_hasta or None,
                    'taller_fibra': log.taller_fibra_id.name or None,
                    'inicio': _fecha(log.fecha_inicio),
                    'fin': _fecha(log.fecha_fin),
                    'duracion_dias': round(log.duracion_dias, 2) if log.fecha_fin else None,
                    'nota': log.nota or None,
                })
        return dict(moto, linea_de_tiempo=linea)
