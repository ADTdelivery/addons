# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user
from odoo.tests.common import SavepointCase, tagged


@tagged('post_install', '-at_install')
class TestFlota360Tracking(SavepointCase):
    """Vista 5 de Flota 360: tablero, detalle, acciones y configuración del tracking."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'adt.moto.tracking' not in cls.env:
            cls.skipTest(cls, 'adt_tracking_moto no está instalado')
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS F360'})
        cls.modelo = cls.env['fleet.vehicle.model'].create({'name': 'King F360', 'brand_id': brand.id})
        cls.taller = cls.env.ref('adt_tracking_moto.taller_fibra_ves')
        cls.usuario = new_test_user(cls.env, login='f360_trk_user', groups=(
            'base.group_user,fleet.fleet_group_user,adt_tracking_moto.group_tracking_user'))
        cls.moto = cls.env['fleet.vehicle'].create({'model_id': cls.modelo.id, 'vin_sn': 'CH-F360-TRK'})
        cls.tracking = cls.env['adt.moto.tracking'].search([('vehicle_id', '=', cls.moto.id)])
        cls.F360 = cls.env['adt.flota360'].with_user(cls.usuario)

    def _etapa(self, codigo):
        return self.env['adt.moto.tracking']._etapa(codigo)

    def test_tablero_indicadores(self):
        data = self.F360.tracking_tablero()
        self.assertTrue(data['disponible'])
        self.assertEqual([e['codigo'] for e in data['etapas']], ['recojo', 'almacen', 'fibra', 'listo'])
        recojo = next(e for e in data['etapas'] if e['codigo'] == 'recojo')
        self.assertGreaterEqual(recojo['n'], 1)
        tarjeta = next(i for i in data['items'] if i['id'] == self.tracking.id)
        self.assertEqual(tarjeta['siguiente']['codigo'], 'almacen')
        self.assertEqual(tarjeta['accion_placa']['accion'], 'iniciar')
        buscado = self.F360.tracking_tablero(buscar='ch-f360-trk')
        self.assertEqual([i['id'] for i in buscado['items']], self.tracking.ids)

    def test_logistica_y_fibra_por_taller(self):
        self.F360.tracking_mover(self.tracking.id, self._etapa('almacen').id)
        with self.assertRaises(ValidationError):
            self.F360.tracking_mover(self.tracking.id, self._etapa('fibra').id)
        self.F360.tracking_mover(self.tracking.id, self._etapa('fibra').id, taller_id=self.taller.id)
        self.assertEqual(self.tracking.etapa_codigo, 'fibra')
        data = self.F360.tracking_tablero(taller_id=self.taller.id)
        ves = next(t for t in data['talleres'] if t['id'] == self.taller.id)
        self.assertGreaterEqual(ves['n'], 1)
        self.assertIn(self.tracking.id, [i['id'] for i in data['items']])
        # Un usuario no salta etapas (regla del tracking).
        with self.assertRaises(UserError):
            self.F360.tracking_mover(self.tracking.id, self._etapa('recojo').id)

    def test_placa_desde_la_tarjeta(self):
        self.F360.tracking_placa(self.tracking.id, 'iniciar')
        self.assertEqual(self.tracking.estado_placa, 'en_tramite')
        with self.assertRaises(ValidationError):
            self.F360.tracking_placa(self.tracking.id, 'observar', {'motivo': ' '})
        self.F360.tracking_placa(self.tracking.id, 'observar', {'motivo': 'Falta DUA'})
        self.assertEqual(self.tracking.estado_placa, 'observado')
        self.F360.tracking_placa(self.tracking.id, 'levantar')
        self.F360.tracking_placa(self.tracking.id, 'finalizar', {'num_placa': 'abc-123'})
        self.assertEqual(self.tracking.estado_placa, 'finalizado')
        self.assertEqual(self.moto.license_plate, 'ABC-123')
        caso = self.F360.tracking_caso(self.tracking.id)
        self.assertEqual(caso['placa']['tramite']['num_placa'], 'ABC-123')
        self.assertTrue(caso['historial'])
        with self.assertRaises(AccessError):
            self.F360.tracking_placa(self.tracking.id, 'reabrir')

    def test_configuracion_solo_manager(self):
        etapa = self._etapa('almacen')
        with self.assertRaises(AccessError):
            self.F360.tracking_config_etapa(etapa.id, {'nombre': 'Base X'})
        admin = self.env['adt.flota360']
        admin.tracking_config_etapa(etapa.id, {'nombre': 'Base central', 'sla_horas': 48})
        self.assertEqual((etapa.name, etapa.sla_horas), ('Base central', 48))
        nuevo = admin.tracking_config_taller(None, {'nombre': 'Fibra Ate', 'codigo': 'ate'})
        taller = self.env['adt.moto.tracking.taller'].browse(nuevo['id'])
        self.assertEqual(taller.codigo, 'ATE')
        admin.tracking_config_taller(taller.id, {'nombre': 'Fibra Ate', 'activo': False})
        self.assertFalse(taller.active)
        if 'adt.tramite.placa' in self.env:
            admin.tracking_config_placa(3)
            self.assertEqual(self.env['adt.tramite.placa']._dias_finalizado(), 3)
        with self.assertRaises(ValidationError):
            admin.tracking_config_placa(-1)
        cfg = self.F360.tracking_config()
        self.assertFalse(cfg['manager'])
        self.assertIn(taller.id, [t['id'] for t in cfg['talleres']])
