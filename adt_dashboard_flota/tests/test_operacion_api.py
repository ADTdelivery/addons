# -*- coding: utf-8 -*-
import json

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..models.stock_service import StockApiError


@tagged('post_install', '-at_install')
class TestOperacionApi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS API'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'APACHE API', 'brand_id': brand.id})
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente API'})
        Vehicle = cls.env['fleet.vehicle']
        cls.en_proceso = Vehicle.create({'model_id': cls.model.id, 'vin_sn': 'API-001'})
        cls.vendida = Vehicle.create({'model_id': cls.model.id, 'vin_sn': 'API-002', 'license_plate': 'API-123',
                                      'driver_id': cls.partner.id})
        cls.tracking = cls.env['adt.moto.tracking'].search([('vehicle_id', '=', cls.en_proceso.id)])
        cls.tracking.action_llevar_almacen()
        cls.tramite = cls.env['adt.tramite.placa'].create({'vehicle_id': cls.en_proceso.id})
        cls.tramite.action_iniciar()
        cls.servicio = cls.env['adt.fleet.dashboard']

    def _moto(self, resultado, vehiculo):
        return next(m for m in resultado['motos'] if m['id'] == vehiculo.id)

    def test_motos_stock_con_proceso(self):
        res = self.servicio.api_operacion_motos(filtros={'modelo_id': self.model.id})
        ids = {m['id'] for m in res['motos']}
        self.assertIn(self.en_proceso.id, ids)
        self.assertNotIn(self.vendida.id, ids)  # alcance stock = sin dueño
        moto = self._moto(res, self.en_proceso)
        self.assertEqual(moto['chasis'], 'API-001')
        self.assertTrue(moto['disponible'])
        self.assertFalse(moto['lista_para_entregar'])
        self.assertEqual(moto['logistica']['etapa'], 'almacen')
        self.assertEqual(moto['logistica']['paso'], 2)
        self.assertEqual(moto['placa_proceso']['estado'], 'en_tramite')
        self.assertTrue(moto['placa_proceso']['inicio'])

    def test_motos_flota_y_filtros(self):
        res = self.servicio.api_operacion_motos('flota', {'modelo_id': self.model.id})
        vendida = self._moto(res, self.vendida)
        self.assertFalse(vendida['disponible'])
        self.assertEqual(vendida['placa'], 'API-123')
        self.assertEqual(vendida['estado_general'], 'fuera_del_flujo')  # nunca pasó por el tracking

        def ids(**filtros):
            filtros['modelo_id'] = self.model.id
            return {m['id'] for m in self.servicio.api_operacion_motos('flota', filtros)['motos']}
        self.assertEqual(ids(etapa='almacen'), {self.en_proceso.id})
        self.assertEqual(ids(estado_placa='en_tramite'), {self.en_proceso.id})
        self.assertEqual(ids(con_duenio=True), {self.vendida.id})
        self.assertEqual(ids(texto='api-002'), {self.vendida.id})

        pagina = self.servicio.api_operacion_motos('flota', {'modelo_id': self.model.id}, limite=1, offset=1)
        self.assertEqual((pagina['total'], len(pagina['motos'])), (2, 1))

    def test_parametros_invalidos(self):
        for args in (('otro',), ('stock', {'etapa': 'x'}), ('stock', {'estado_placa': 'x'}),
                     ('stock', {'demorado': 'si'}), ('stock', 'no-es-objeto'), ('stock', None, 'abc')):
            with self.assertRaises(StockApiError):
                self.servicio.api_operacion_motos(*args)
        with self.assertRaises(StockApiError):
            self.servicio.api_operacion_moto_detalle(None)
        with self.assertRaises(StockApiError):
            self.servicio.api_operacion_moto_detalle(999999999)

    def test_detalle_con_linea_de_tiempo(self):
        self.tramite._observar('Falta DUA')
        detalle = self.servicio.api_operacion_moto_detalle(self.en_proceso.id)
        self.assertEqual(detalle['placa_proceso']['estado'], 'observado')
        self.assertEqual(detalle['placa_proceso']['observacion'], 'Falta DUA')
        hacia = [(l['flujo'], l['codigo']) for l in detalle['linea_de_tiempo']]
        self.assertIn(('logistica', 'recojo'), hacia)
        self.assertIn(('logistica', 'almacen'), hacia)
        self.assertIn(('placa', 'observado'), hacia)
        cerrado = next(l for l in detalle['linea_de_tiempo'] if l['codigo'] == 'recojo')
        self.assertTrue(cerrado['fin'])

    def test_resumen_coincide_con_dashboard(self):
        resumen = self.servicio.api_operacion_resumen()
        tablero = self.servicio.get_operacion_data()
        self.assertEqual(resumen['totales']['flota'], tablero['kpis'][0]['valor'])
        self.assertEqual(sum(c['cantidad'] for c in resumen['combinaciones'].values()), resumen['totales']['flota'])
        self.assertEqual([e['etapa'] for e in resumen['logistica']], ['recojo', 'almacen', 'fibra', 'listo'])
        self.assertNotIn('abrir', json.dumps(resumen))  # sin listas de ids internas
        self.assertTrue(all('cantidad' in a and 'vehiculos' not in a for a in resumen['alertas']))


@tagged('post_install', '-at_install')
class TestOperacionApiHttp(HttpCase):

    def _post(self, ruta, params=None):
        respuesta = self.url_open(ruta, data=json.dumps({'jsonrpc': '2.0', 'params': params or {}}),
                                  headers={'Content-Type': 'application/json'})
        return respuesta.json()

    def test_rutas_con_sesion(self):
        # Usuario interno sin permisos de Flota (como la vendedora).
        new_test_user(self.env, login='vendedora_api', password='vendedora_api', groups='base.group_user')
        self.authenticate('vendedora_api', 'vendedora_api')
        resumen = self._post('/api/operacion/resumen')['result']
        self.assertTrue(resumen['ok'])
        self.assertIn('totales', resumen)
        motos = self._post('/api/operacion/motos', {'alcance': 'flota', 'limite': 5})['result']
        self.assertTrue(motos['ok'])
        self.assertLessEqual(len(motos['motos']), 5)
        error = self._post('/api/operacion/motos', {'alcance': 'otro'})['result']
        self.assertEqual((error['ok'], error['codigo']), (False, 'parametros_invalidos'))
