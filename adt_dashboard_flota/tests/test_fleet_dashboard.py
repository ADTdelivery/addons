# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from ..models.fleet_dashboard import plate_is_ready


@tagged('post_install', '-at_install')
class TestFleetDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS TEST'})
        cls.model = cls.env['fleet.vehicle.model'].create({
            'name': 'APACHE TEST', 'brand_id': brand.id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente Test'})
        Vehicle = cls.env['fleet.vehicle']
        cls.stock_ready = Vehicle.create({
            'model_id': cls.model.id, 'license_plate': '1234-AB',
            'model_year': '2025', 'color': ' negro ',
        })
        cls.stock_no_plate = Vehicle.create({
            'model_id': cls.model.id, 'license_plate': 'EN TRAMITE',
        })
        cls.assigned = Vehicle.create({
            'model_id': cls.model.id, 'license_plate': '9999-ZZ',
            'driver_id': cls.partner.id,
        })

    def _row(self, data, vehicle):
        return next(v for v in data['vehicles'] if v['id'] == vehicle.id)

    def test_plate_is_ready(self):
        self.assertTrue(plate_is_ready('1234-AB'))
        self.assertTrue(plate_is_ready(' ab-1234 '))
        self.assertFalse(plate_is_ready(False))
        self.assertFalse(plate_is_ready('   '))
        self.assertFalse(plate_is_ready('S/P'))
        self.assertFalse(plate_is_ready('en tramite'))
        self.assertFalse(plate_is_ready('PENDIENTE'))

    def test_dashboard_rows(self):
        data = self.env['adt.fleet.dashboard'].get_dashboard_data()
        ready = self._row(data, self.stock_ready)
        self.assertFalse(ready['has_owner'])
        self.assertEqual(ready['plate_status'], 'lista')
        self.assertEqual(ready['color'], 'NEGRO')
        self.assertEqual(ready['year'], '2025')

        no_plate = self._row(data, self.stock_no_plate)
        self.assertFalse(no_plate['has_owner'])
        self.assertEqual(no_plate['year'], 'SIN AÑO')
        self.assertEqual(no_plate['color'], 'SIN COLOR')
        self.assertIn(no_plate['plate_status'], ('sin_placa', 'tramite'))

        self.assertTrue(self._row(data, self.assigned)['has_owner'])

    # ------------------------------------------------------------------ API de stock
    def _ids(self, result):
        return {v['id'] for v in result['vehiculos']}

    def test_api_stock_vehiculos(self):
        service = self.env['adt.fleet.dashboard']
        result = service.api_stock_vehiculos({'modelo_id': self.model.id})
        ids = self._ids(result)
        self.assertIn(self.stock_ready.id, ids)
        self.assertIn(self.stock_no_plate.id, ids)
        self.assertNotIn(self.assigned.id, ids)
        # Las motos con placa lista van primero (entrega inmediata).
        self.assertTrue(result['vehiculos'][0]['placa_lista'])

        ready = service.api_stock_vehiculos({'modelo_id': self.model.id, 'solo_placa_lista': True})
        self.assertEqual(self._ids(ready), {self.stock_ready.id})
        row = ready['vehiculos'][0]
        self.assertEqual((row['placa'], row['anio'], row['color']), ('1234-AB', '2025', 'NEGRO'))

        by_color = service.api_stock_vehiculos({'modelo_id': self.model.id, 'color': 'negro', 'anio': 2025})
        self.assertEqual(self._ids(by_color), {self.stock_ready.id})

        page = service.api_stock_vehiculos({'modelo_id': self.model.id}, limite=1, offset=1)
        self.assertEqual((page['total'], len(page['vehiculos'])), (2, 1))

    def test_api_stock_vehiculos_parametros_invalidos(self):
        from ..models.stock_service import StockApiError
        service = self.env['adt.fleet.dashboard']
        with self.assertRaises(StockApiError):
            service.api_stock_vehiculos({'estado_placa': 'otra'})
        with self.assertRaises(StockApiError):
            service.api_stock_vehiculos({}, limite='abc')

    def test_api_stock_resumen_y_detalle(self):
        service = self.env['adt.fleet.dashboard']
        resumen = service.api_stock_resumen()
        modelo = next(m for m in resumen['modelos'] if m['modelo_id'] == self.model.id)
        self.assertEqual((modelo['stock'], modelo['placa_lista']), (2, 1))
        self.assertIn('NEGRO', resumen['filtros']['colores'])

        self.assertTrue(service.api_stock_detalle(self.stock_ready.id)['disponible'])
        self.assertFalse(service.api_stock_detalle(self.assigned.id)['disponible'])

    # ------------------------------------------------------------------ dashboard operativo
    def _abrir_ids(self, bloque):
        return set(bloque['abrir']['ids'])

    def test_operacion_matriz_y_kpis(self):
        cliente_sin_placa = self.env['fleet.vehicle'].create({'model_id': self.model.id})
        cliente_sin_placa.write({'driver_id': self.partner.id})
        data = self.env['adt.fleet.dashboard'].get_operacion_data()
        m = data['matriz']
        self.assertIn(self.stock_ready.id, self._abrir_ids(m['stock_con_placa']))
        self.assertIn(self.stock_no_plate.id, self._abrir_ids(m['stock_sin_placa']))
        self.assertIn(self.assigned.id, self._abrir_ids(m['duenio_con_placa']))
        self.assertIn(cliente_sin_placa.id, self._abrir_ids(m['duenio_sin_placa']))
        # Las 4 celdas reparten toda la flota.
        flota = next(k for k in data['kpis'] if k['codigo'] == 'flota')
        self.assertEqual(sum(c['valor'] for c in m.values()), flota['valor'])

        alerta = next(a for a in data['alertas'] if a['codigo'] == 'cliente_sin_placa')
        self.assertEqual(alerta['severidad'], 'critico')
        self.assertIn(cliente_sin_placa.id, self._abrir_ids(alerta))
        self.assertEqual([a['severidad'] for a in data['alertas']],
                         sorted((a['severidad'] for a in data['alertas']),
                                key=['critico', 'alto', 'medio'].index))

    def test_operacion_flujo_y_placa(self):
        tracking = self.env['adt.moto.tracking'].search([('vehicle_id', '=', self.stock_no_plate.id)])
        self.assertTrue(tracking)
        tramite = self.env['adt.tramite.placa'].create({'vehicle_id': self.stock_no_plate.id})
        tramite.action_iniciar()
        tramite._observar('Falta DUA')

        data = self.env['adt.fleet.dashboard'].get_operacion_data()
        recojo = next(e for e in data['wip']['logistica'] if e['codigo'] == 'recojo')
        self.assertIn(tracking.id, self._abrir_ids(recojo))
        observado = next(e for e in data['wip']['placa'] if e['codigo'] == 'observado')
        self.assertIn(tramite.id, self._abrir_ids(observado))
        alerta = next(a for a in data['alertas'] if a['codigo'] == 'placa_observada')
        self.assertIn(tramite.id, self._abrir_ids(alerta))
        # La matriz desglosa el "sin placa" por estado del trámite.
        desglose = data['matriz']['stock_sin_placa']['desglose']
        self.assertIn(self.stock_no_plate.id, set(desglose['observado']['abrir']['ids']))

        self.assertEqual(len(data['ritmo']['semanas']), 8)
        self.assertTrue(all(len(s['valores']) == 8 for s in data['ritmo']['series']))
        self.assertEqual(sum(t['valor'] for t in data['antiguedad_stock']),
                         data['matriz']['stock_sin_placa']['valor'] + data['matriz']['stock_con_placa']['valor'])

    def test_api_estado_placa_desde_tramite(self):
        tramite = self.env['adt.tramite.placa'].create({'vehicle_id': self.stock_no_plate.id})
        service = self.env['adt.fleet.dashboard']
        fila = lambda: next(v for v in service.api_stock_vehiculos({'modelo_id': self.model.id})['vehiculos']
                            if v['id'] == self.stock_no_plate.id)
        self.assertEqual(fila()['estado_placa'], 'sin_placa')  # pendiente = aún no se inicia
        tramite.action_iniciar()
        self.assertEqual(fila()['estado_placa'], 'tramite')

    # ------------------------------------------------------------------ acceso delegado
    def test_usuario_solo_operacion_motos(self):
        """Un usuario con solo el grupo de la app "Operación de motos" (sin Flota) puede trabajar."""
        from odoo.tests import new_test_user
        usuario = new_test_user(self.env, login='solo_operacion', groups='adt_tracking_moto.group_tracking_user')
        self.assertFalse(usuario.has_group('fleet.fleet_group_user'))
        env = self.env(user=usuario)

        data = env['adt.fleet.dashboard'].get_operacion_data()
        self.assertTrue(data['kpis'])

        # Los clics del dashboard abren listas y fichas de estos modelos.
        tramite = self.env['adt.tramite.placa'].create({'vehicle_id': self.stock_no_plate.id})
        registros = {
            'fleet.vehicle': self.stock_no_plate,
            'adt.moto.tracking': self.env['adt.moto.tracking'].search([('vehicle_id', '=', self.stock_no_plate.id)]),
            'adt.tramite.placa': tramite,
        }
        vistas_dashboard = data['vistas']
        for model, record in registros.items():
            Model = env[model]
            pedidas = [tuple(v) for v in vistas_dashboard.get(model, [[False, 'list'], [False, 'form']])]
            vistas = Model.load_views(pedidas + [(False, 'search')])['fields_views']
            for tipo in ('list', 'form'):
                campos = [f for f in vistas[tipo]['fields']]
                Model.browse(record.id).read(campos)

        menus = env['ir.ui.menu'].load_menus(debug=False)
        raiz = self.env.ref('adt_tracking_moto.menu_operacion_motos_root').id
        self.assertIn(raiz, menus['root']['children'])
        self.assertNotIn(self.env.ref('fleet.menu_root').id, menus['root']['children'])
