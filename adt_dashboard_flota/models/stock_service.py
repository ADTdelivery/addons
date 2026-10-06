# -*- coding: utf-8 -*-
from odoo import api, models

from .fleet_dashboard import PLATE_STATUS_LABELS

PLATE_ORDER = ['lista', 'tramite', 'sin_placa']
SIN_ANIO = 'SIN AÑO'
SIN_COLOR = 'SIN COLOR'


class StockApiError(Exception):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


class AdtFleetDashboardStockService(models.AbstractModel):
    """Consulta de stock (motos sin dueño) para la app de ventas.

    Usa las mismas reglas que el dashboard (_vehicle_rows) para que la app y
    gerencia vean siempre los mismos números.
    """
    _inherit = 'adt.fleet.dashboard'

    # ------------------------------------------------------------------ datos base
    @api.model
    def _stock_rows(self):
        return self._vehicle_rows([('driver_id', '=', False)])

    @staticmethod
    def _imagen_modelo_url(model_id):
        return '/web/image/fleet.vehicle.model/%d/image_128' % model_id if model_id else None

    @api.model
    def _api_vehiculo_dict(self, v):
        return {
            'id': v['id'],
            'placa': v['plate'] or None,
            'placa_lista': v['plate_status'] == 'lista',
            'estado_placa': v['plate_status'],
            'estado_placa_texto': PLATE_STATUS_LABELS[v['plate_status']],
            'tramite_placa': v['procedure_state'] or None,
            'marca': v['brand'],
            'modelo': v['model'],
            'modelo_id': v['model_id'] or None,
            'anio': None if v['year'] == SIN_ANIO else v['year'],
            'color': None if v['color'] == SIN_COLOR else v['color'],
            'chasis': v['vin'] or None,
            'motor': v['motor'] or None,
            'tipo': v['vehicle_type_label'],
            'estado_flota': v['state'],
            'imagen_url': self._imagen_modelo_url(v['model_id']),
        }

    @staticmethod
    def _contar(rows):
        conteo = {'stock': len(rows), 'placa_lista': 0, 'en_tramite': 0, 'sin_placa': 0}
        clave = {'lista': 'placa_lista', 'tramite': 'en_tramite', 'sin_placa': 'sin_placa'}
        for v in rows:
            conteo[clave[v['plate_status']]] += 1
        return conteo

    # ------------------------------------------------------------------ filtros
    @staticmethod
    def _texto(valor, campo):
        if valor in (None, False, ''):
            return ''
        if not isinstance(valor, (str, int)) or isinstance(valor, bool):
            raise StockApiError('parametros_invalidos', 'El campo %s debe ser texto.' % campo)
        return str(valor).strip()

    @staticmethod
    def _entero(valor, campo, defecto, minimo=0, maximo=None):
        if valor in (None, ''):
            return defecto
        if isinstance(valor, bool):
            raise StockApiError('parametros_invalidos', 'El campo %s debe ser numérico.' % campo)
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            raise StockApiError('parametros_invalidos', 'El campo %s debe ser numérico.' % campo)
        valor = max(minimo, valor)
        return min(valor, maximo) if maximo else valor

    @api.model
    def _filtrar(self, rows, filtros):
        filtros = filtros or {}
        if not isinstance(filtros, dict):
            raise StockApiError('parametros_invalidos', 'filtros debe ser un objeto.')

        modelo_id = self._entero(filtros.get('modelo_id'), 'modelo_id', None, minimo=1)
        marca = self._texto(filtros.get('marca'), 'marca').upper()
        anio = self._texto(filtros.get('anio'), 'anio').upper()
        color = self._texto(filtros.get('color'), 'color').upper()
        estado_placa = self._texto(filtros.get('estado_placa'), 'estado_placa')
        texto = self._texto(filtros.get('texto'), 'texto').upper()
        solo_placa_lista = filtros.get('solo_placa_lista') is True

        if estado_placa and estado_placa not in PLATE_ORDER:
            raise StockApiError('parametros_invalidos',
                                'estado_placa debe ser uno de: %s.' % ', '.join(PLATE_ORDER))
        if solo_placa_lista:
            estado_placa = 'lista'

        def coincide(v):
            if modelo_id and v['model_id'] != modelo_id:
                return False
            if marca and v['brand'].upper() != marca:
                return False
            if anio and v['year'] != anio:
                return False
            if color and v['color'] != color:
                return False
            if estado_placa and v['plate_status'] != estado_placa:
                return False
            if texto:
                pajar = ' '.join([v['plate'], v['model'], v['brand'], v['color'], v['year'], v['vin'], v['motor']]).upper()
                if texto not in pajar:
                    return False
            return True

        return [v for v in rows if coincide(v)]

    @staticmethod
    def _orden_anio(anio):
        return int(anio) if anio.isdigit() else 0

    # ------------------------------------------------------------------ servicios
    @api.model
    def api_stock_resumen(self):
        """Totales del stock, desglose por modelo (colores y años) y opciones de filtro."""
        rows = self._stock_rows()
        por_modelo = {}
        for v in rows:
            por_modelo.setdefault((v['model_id'], v['model'], v['brand']), []).append(v)

        modelos = []
        for (model_id, modelo, marca), vehiculos in por_modelo.items():
            colores, anios = {}, {}
            for v in vehiculos:
                colores.setdefault(v['color'], []).append(v)
                anios.setdefault(v['year'], []).append(v)
            modelos.append(dict(
                self._contar(vehiculos),
                modelo_id=model_id or None,
                modelo=modelo,
                marca=marca,
                imagen_url=self._imagen_modelo_url(model_id),
                colores=sorted(
                    [dict(self._contar(vs), color=None if c == SIN_COLOR else c) for c, vs in colores.items()],
                    key=lambda x: (-x['stock'], x['color'] or '~')),
                anios=sorted(
                    [dict(self._contar(vs), anio=None if a == SIN_ANIO else a) for a, vs in anios.items()],
                    key=lambda x: -self._orden_anio(x['anio'] or '')),
            ))
        modelos.sort(key=lambda m: (-m['stock'], m['modelo']))

        return {
            'totales': self._contar(rows),
            'modelos': modelos,
            'filtros': {
                'modelos': [{'id': m['modelo_id'], 'nombre': m['modelo'], 'marca': m['marca']}
                            for m in modelos if m['modelo_id']],
                'marcas': sorted({v['brand'] for v in rows}),
                'anios': sorted({v['year'] for v in rows if v['year'] != SIN_ANIO},
                                key=self._orden_anio, reverse=True),
                'colores': sorted({v['color'] for v in rows if v['color'] != SIN_COLOR}),
                'estados_placa': [{'codigo': c, 'nombre': PLATE_STATUS_LABELS[c]} for c in PLATE_ORDER],
            },
        }

    @api.model
    def api_stock_vehiculos(self, filtros=None, limite=20, offset=0):
        """Listado paginado de motos en stock. Primero las de placa lista (entrega inmediata)."""
        limite = self._entero(limite, 'limite', 20, minimo=1, maximo=100)
        offset = self._entero(offset, 'offset', 0)
        rows = self._filtrar(self._stock_rows(), filtros)
        rows.sort(key=lambda v: (PLATE_ORDER.index(v['plate_status']), v['model'],
                                 -self._orden_anio(v['year']), v['color'], v['id']))
        return {
            'total': len(rows),
            'limite': limite,
            'offset': offset,
            'totales': self._contar(rows),
            'vehiculos': [self._api_vehiculo_dict(v) for v in rows[offset:offset + limite]],
        }

    @api.model
    def api_stock_detalle(self, vehiculo_id):
        """Detalle de una moto. Indica si sigue disponible (sin dueño) para venderla."""
        vehiculo_id = self._entero(vehiculo_id, 'vehiculo_id', None, minimo=1)
        if not vehiculo_id:
            raise StockApiError('parametros_invalidos', 'El campo vehiculo_id es obligatorio.')
        rows = self._vehicle_rows([('id', '=', vehiculo_id)])
        if not rows:
            raise StockApiError('no_encontrado', 'El vehículo no existe o está archivado.')
        v = rows[0]
        vehicle = self.env['fleet.vehicle'].browse(vehiculo_id)
        return dict(
            self._api_vehiculo_dict(v),
            disponible=not v['has_owner'],
            fecha_adquisicion=v['acquisition_date'] or None,
            kilometraje=vehicle.odometer,
            unidad_kilometraje=vehicle.odometer_unit,
        )
