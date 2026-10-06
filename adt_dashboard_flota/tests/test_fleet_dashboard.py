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
