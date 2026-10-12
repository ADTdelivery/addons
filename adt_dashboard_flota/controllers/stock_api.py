# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from ..models.stock_service import StockApiError


def _error(codigo, mensaje):
    return {'ok': False, 'codigo': codigo, 'error': mensaje}


class StockFlotaController(http.Controller):
    """Stock de motos para la app de ventas. JSON-RPC (POST) con sesión de usuario,
    mismo contrato que /api/simulador/*.

    Stock = vehículo activo de flota sin conductor/dueño. Errores: {ok: false, codigo, error}.
    """

    def _servicio(self):
        # Solo usuarios internos (vendedoras); la lectura de flota se hace con sudo
        # porque el perfil de ventas no necesariamente tiene permisos de Flota.
        if not request.env.user.has_group('base.group_user'):
            raise StockApiError('sin_permiso', 'Tu usuario no tiene acceso al stock.')
        return request.env['adt.fleet.dashboard'].sudo()

    def _responder(self, funcion):
        try:
            return dict({'ok': True}, **funcion(self._servicio()))
        except StockApiError as e:
            return _error(e.codigo, e.mensaje)

    @http.route('/api/stock/resumen', type='json', auth='user', methods=['POST'])
    def resumen(self, **kw):
        """Totales del stock, desglose por modelo (colores/años) y opciones para los filtros."""
        return self._responder(lambda s: s.api_stock_resumen())

    @http.route('/api/stock/vehiculos', type='json', auth='user', methods=['POST'])
    def vehiculos(self, filtros=None, limite=20, offset=0, **kw):
        """Motos en stock, paginadas. filtros: modelo_id, marca, anio, color,
        estado_placa (lista|tramite|sin_placa), solo_placa_lista, texto."""
        return self._responder(lambda s: s.api_stock_vehiculos(filtros, limite, offset))

    @http.route('/api/stock/vehiculos/detalle', type='json', auth='user', methods=['POST'])
    def detalle(self, vehiculo_id=None, **kw):
        """Ficha de una moto e indicador de si sigue disponible."""
        return self._responder(lambda s: {'vehiculo': s.api_stock_detalle(vehiculo_id)})

    # ------------------------------------------------------------------ operación (solo lectura)
    @http.route('/api/operacion/resumen', type='json', auth='user', methods=['POST'])
    def operacion_resumen(self, **kw):
        """Totales, combinaciones dueño × placa, carga por etapa (logística y placa) y alertas."""
        return self._responder(lambda s: s.api_operacion_resumen())

    @http.route('/api/operacion/motos', type='json', auth='user', methods=['POST'])
    def operacion_motos(self, alcance='stock', filtros=None, limite=20, offset=0, **kw):
        """Motos con su proceso completo (fibra y placa). alcance: stock | flota.
        filtros: etapa, estado_placa, demorado, con_duenio, lista_para_entregar, modelo_id, texto."""
        return self._responder(lambda s: s.api_operacion_motos(alcance, filtros, limite, offset))

    @http.route('/api/operacion/motos/detalle', type='json', auth='user', methods=['POST'])
    def operacion_moto_detalle(self, vehiculo_id=None, **kw):
        """Una moto con su proceso y su línea de tiempo."""
        return self._responder(lambda s: {'moto': s.api_operacion_moto_detalle(vehiculo_id)})
