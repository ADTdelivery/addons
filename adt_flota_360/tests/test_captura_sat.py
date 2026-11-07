# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests.common import SavepointCase, tagged

from ..models.flota_360_captura_sat import _clave_documento, _es_papeleta


@tagged('post_install', '-at_install')
class TestCapturaSatCruce(SavepointCase):
    """Pestaña Captura SAT: cruce de órdenes con la flota y las papeletas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'adt.captura.sat' not in cls.env:
            return
        cls.env.user.groups_id |= cls.env.ref('adt_comercial.group_access_adt_comercial_gerencia')
        cls.service = cls.env['adt.flota360']
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS CAPSAT'})
        modelo = cls.env['fleet.vehicle.model'].create({'name': 'King CAPSAT', 'brand_id': brand.id})
        cliente = cls.env['res.partner'].create({'name': 'Cliente CAPSAT'})
        cls.con_cliente = cls.env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': 'CS-1001',
                                                           'driver_id': cliente.id})
        cls.stock = cls.env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': 'CS-1002'})
        ahora = fields.Datetime.now()
        Orden = cls.env['adt.captura.sat']
        # Vinculada, con papeleta SAT pagada (mismo número y placa).
        cls.orden_pagada = Orden.create({'name': '0099001', 'placa': 'CS1001', 'vehicle_id': cls.con_cliente.id,
                                         'concepto': 'Inf. RNT', 'monto': 400.0, 'primera_vez_visto': ahora})
        cls.env['adt.papeleta.sat'].create({'name': '99001', 'placa': 'CS1001', 'vehicle_id': cls.con_cliente.id,
                                            'vigente': False, 'deuda': 0.0})  # dejó de figurar: pagada
        # Sin vincular: se encuentra por placa; papeleta de tránsito sin registrar.
        cls.orden_suelta = Orden.create({'name': '0099002', 'placa': 'CS1002', 'concepto': 'Inf. RNT',
                                         'monto': 300.0, 'primera_vez_visto': ahora})
        # Placa fuera de la flota.
        cls.orden_fuera = Orden.create({'name': '0099003', 'placa': 'ZZ9999', 'concepto': 'Impuesto vehicular',
                                        'monto': 100.0, 'primera_vez_visto': ahora})

    def setUp(self):
        super().setUp()
        if 'adt.captura.sat' not in self.env:
            self.skipTest('adt_captura_sat no está instalado')

    def _fila(self, data, placa):
        return next(f for f in data['filas'] if f['placa'] == placa)

    def test_claves(self):
        self.assertEqual(_clave_documento('N° 0015529425'), '15529425')
        self.assertTrue(_es_papeleta('Inf. RNT'))
        self.assertFalse(_es_papeleta('Impuesto vehicular'))

    def test_cruce_con_flota_y_papeletas(self):
        data = self.service.capturas_sat()
        self.assertTrue(data['disponible'])

        pagada = self._fila(data, 'CS1001')
        self.assertEqual(pagada['vehicle_id'], self.con_cliente.id)
        self.assertEqual(pagada['match'], 'vinculado')
        self.assertTrue(pagada['vehiculo']['con_cliente'])
        papeleta = pagada['ordenes'][0]['papeleta']
        self.assertEqual((papeleta['tipo'], papeleta['coincide'], papeleta['pagada']), ('sat', 'exacta', True))
        textos = [h['texto'] for h in pagada['hallazgos']]
        self.assertTrue(any('pagada' in t for t in textos))
        self.assertEqual(pagada['nivel'], 'critico')  # moto con cliente

        suelta = self._fila(data, 'CS1002')
        self.assertEqual((suelta['vehicle_id'], suelta['match']), (self.stock.id, 'placa'))
        self.assertIsNone(suelta['ordenes'][0]['papeleta'])
        self.assertTrue(any('sin registrar' in h['texto'] for h in suelta['hallazgos']))

        fuera = self._fila(data, 'ZZ9999')
        self.assertFalse(fuera['vehicle_id'])
        self.assertEqual(fuera['match'], 'sin_flota')

        recuadros = {r['key']: r for r in data['recuadros']}
        self.assertIn(self.orden_pagada.id, recuadros['con_cliente']['ids'])
        self.assertIn(self.orden_pagada.id, recuadros['pagadas']['ids'])
        self.assertIn(self.orden_fuera.id, recuadros['sin_flota']['ids'])

    def test_placa_original_de_otro_vehiculo(self):
        # La placa original es de otra moto de la flota: la fila muestra los dos vehículos.
        self.env['adt.captura.sat'].create({'name': '0099004', 'placa': 'CS1002', 'placa_original': 'CS-1001',
                                            'concepto': 'Inf. RNT', 'monto': 50.0,
                                            'primera_vez_visto': fields.Datetime.now()})
        data = self.service.capturas_sat()
        fila = next(f for f in data['filas'] if f['placa_original'] == 'CS-1001')
        self.assertEqual(fila['vehiculo_actual']['id'], self.stock.id)
        self.assertEqual(fila['vehiculo_original']['id'], self.con_cliente.id)
        self.assertTrue(fila['vehiculo_original']['con_cliente'])
        self.assertTrue(any('dos vehículos afectados' in h['texto'] for h in fila['hallazgos']))

    def test_filtro_stock_excluye_fuera_de_flota(self):
        data = self.service.capturas_sat(grupo='stock')
        placas = {f['placa'] for f in data['filas']}
        self.assertIn('CS1002', placas)
        self.assertNotIn('CS1001', placas)
        self.assertNotIn('ZZ9999', placas)
        self.assertNotIn('sin_flota', {r['key'] for r in data['recuadros']})
