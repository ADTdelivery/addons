# -*- coding: utf-8 -*-
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user
from odoo.tests.common import SavepointCase, tagged

from ..models.flota_360_gps import (BUS_TIPO, AdtFlota360GpsDispositivo, IndicePlacas, PALABRAS_RUIDO, claves_placa,
                                    diagnosticar, evaluar_geocercas, palabras_ruido)
from ..models.flota_360_gps_geocerca import (AdtFlota360GpsGeocerca, distancia_m, punto_en_poligono,
                                             wkt_a_geometria)

RUIDO = palabras_ruido(PALABRAS_RUIDO)
# Plaza de Armas de Lima y un punto a ~1,1 km.
CENTRO = (-12.0464, -77.0300)
LEJOS = (-12.0464, -77.0200)


def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000+00:00')


@tagged('post_install', '-at_install')
class TestFlota360GpsPuras(SavepointCase):
    """Limpieza de la placa, diagnóstico y geometría (funciones puras)."""

    def test_claves_quitan_texto_extra(self):
        self.assertIn(('limpieza', 'XYAZ12'), claves_placa('XYAZ12 - nuevo', RUIDO))
        self.assertIn(('limpieza', 'XYAZ12'), claves_placa('xyaz12NUEVO', RUIDO))
        self.assertIn(('limpieza', 'ABC123'), claves_placa('Prueba ABC-123 (repuesto)', RUIDO))
        self.assertIn(('patron', '1234AB'), claves_placa('Moto 1234-AB juan', RUIDO))

    def test_indice(self):
        indice = IndicePlacas([(1, 'XYAZ12', False), (2, 'ABC-123', False), (3, 'D4E567', False),
                               (4, 'D4E-567', False), (5, 'S/P', False), (6, 'B7K-456', '86001')], RUIDO)
        self.assertEqual(indice.buscar('XYAZ12 - nuevo')[:2], (1, 'limpieza'))
        self.assertEqual(indice.buscar('ABC123XQ7')[:2], (2, 'contenida'))
        self.assertEqual(indice.buscar('otro nombre', '86001')[:2], (6, 'imei'))
        self.assertEqual(indice.buscar('D4E567')[:2], (False, 'ambiguo'))
        self.assertEqual(indice.buscar('ZZZ999')[:2], (False, 'sin_vinculo'))

    def test_diagnostico(self):
        ahora = fields.Datetime.now()
        self.assertEqual(diagnosticar({'lastUpdate': iso(ahora - timedelta(minutes=2))}, {'valid': True}, ahora)['estado'],
                         'reportando')
        self.assertEqual(diagnosticar({'lastUpdate': iso(ahora - timedelta(minutes=30))}, {}, ahora)['estado'], 'demorado')
        caido = diagnosticar({'lastUpdate': iso(ahora - timedelta(hours=5))},
                             {'attributes': {'alarm': 'powerCut', 'power': 0}}, ahora)
        self.assertEqual(caido['estado'], 'sin_reporte')
        self.assertIn('Corte de energía', caido['motivo'])
        self.assertEqual(diagnosticar({}, None, ahora)['estado'], 'nunca')
        self.assertEqual(diagnosticar({'disabled': True}, None, ahora)['estado'], 'deshabilitado')

    def test_geometria(self):
        self.assertAlmostEqual(distancia_m(*CENTRO, *LEJOS), 1088, delta=15)
        cuadrado = [[-12.05, -77.04], [-12.05, -77.02], [-12.04, -77.02], [-12.04, -77.04]]
        self.assertTrue(punto_en_poligono(-12.045, -77.03, cuadrado))
        self.assertFalse(punto_en_poligono(-12.06, -77.03, cuadrado))
        # Formatos reales de Traccar (latitud primero).
        circulo = wkt_a_geometria('CIRCLE (-11.866768333333333 -77.11207666666667, 50)')
        self.assertEqual((circulo['tipo'], circulo['radio']), ('circulo', 50.0))
        poligono = wkt_a_geometria('POLYGON ((-12.16 -76.97, -12.161 -76.962, -12.17 -76.965, -12.16 -76.97))')
        self.assertEqual((poligono['tipo'], len(poligono['puntos'])), ('poligono', 3))

    def test_entrada_salida_geocerca(self):
        geo = {'id': 7, 'name': 'Base', 'tipo': 'circulo', 'latitud': CENTRO[0], 'longitud': CENTRO[1], 'radio': 300,
               'puntos': [], 'entrada': True, 'salida': True, 'todos': True, 'dispositivos': set()}
        # Primera evaluación: solo inicializa (no alerta aunque esté dentro).
        estado, trans = evaluar_geocercas(False, 1, CENTRO[0], CENTRO[1], True, [geo])
        self.assertEqual(trans, [])
        estado, trans = evaluar_geocercas(estado, 1, LEJOS[0], LEJOS[1], True, [geo])
        self.assertEqual([t[1] for t in trans], ['salida'])
        # Posición sin señal GPS: no cambia nada.
        mismo, trans = evaluar_geocercas(estado, 1, CENTRO[0], CENTRO[1], False, [geo])
        self.assertEqual((mismo, trans), (estado, []))
        estado, trans = evaluar_geocercas(estado, 1, CENTRO[0], CENTRO[1], True, [geo])
        self.assertEqual([t[1] for t in trans], ['entrada'])
        self.assertTrue(AdtFlota360GpsGeocerca.contiene(geo, *CENTRO))


@tagged('post_install', '-at_install')
class TestFlota360GpsSync(SavepointCase):
    """Sincronización y webhook de Traccar (simulados), alertas por el bus, relación
    manual, creación de vehículos, geocercas y API de la vista."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS GPS'})
        cls.modelo = cls.env['fleet.vehicle.model'].create({'name': 'King GPS', 'brand_id': brand.id})
        cls.v1 = cls.env['fleet.vehicle'].create({'model_id': cls.modelo.id, 'license_plate': 'QWZ-981'})
        cls.v2 = cls.env['fleet.vehicle'].create({'model_id': cls.modelo.id, 'license_plate': 'QWZ-982'})
        cls.usuario = new_test_user(cls.env, login='f360_gps_user', groups='base.group_user,fleet.fleet_group_user')
        cls.F360 = cls.env['adt.flota360'].with_user(cls.usuario)
        cls.Disp = cls.env['adt.flota360.gps.dispositivo']
        cls.ahora = fields.Datetime.now()
        # Solo el usuario de prueba recibe alertas (aísla las aserciones del bus).
        cls.env['ir.config_parameter'].sudo().set_param('adt_flota_360.gps_destinatarios', str(cls.usuario.id))

    def _sync(self, devices, positions=(), geofences=()):
        datos = (devices, list(positions), [], list(geofences))
        with patch.object(AdtFlota360GpsDispositivo, '_traccar_datos', return_value=datos):
            return self.Disp.sincronizar()

    def _device(self, tid, nombre, minutos, **extra):
        d = {'id': tid, 'name': nombre, 'uniqueId': 'IMEI%s' % tid, 'status': 'online', 'disabled': False,
             'lastUpdate': iso(self.ahora - timedelta(minutes=minutos)) if minutos is not None else None}
        d.update(extra)
        return d

    def _pos(self, tid, lat, lon, **attrs):
        return {'deviceId': tid, 'valid': True, 'latitude': lat, 'longitude': lon, 'speed': 0,
                'serverTime': iso(self.ahora), 'fixTime': iso(self.ahora), 'attributes': attrs}

    def _bus(self):
        """Mensajes del monitoreo enviados por el bus al usuario de prueba."""
        canal = json.dumps([self.env.cr.dbname, 'res.partner', self.usuario.partner_id.id], separators=(',', ':'))
        mensajes = self.env['bus.bus'].sudo().search([('channel', '=', canal)])
        return [json.loads(m.message) for m in mensajes if json.loads(m.message).get('type') == BUS_TIPO]

    def _tipos_bus(self):
        return [e['tipo'] for m in self._bus() for e in m['payload']['eventos']]

    def test_sincroniza_relaciona_y_alerta(self):
        res = self._sync([self._device(9001, 'QWZ981 - nuevo', 1), self._device(9002, 'Equipo suelto 77', None)],
                         [self._pos(9001, -12.05, -77.04, ignition=True)])
        self.assertTrue(res['ok'])
        d1 = self.Disp.search([('traccar_id', '=', 9001)])
        d2 = self.Disp.search([('traccar_id', '=', 9002)])
        self.assertEqual((d1.vehicle_id, d1.vinculo_metodo, d1.estado), (self.v1, 'limpieza', 'reportando'))
        self.assertFalse(d2.vehicle_id)
        self.assertEqual(d2.estado, 'nunca')  # sin vehículo en Odoo, pero se monitorea igual
        self.assertEqual(self._tipos_bus(), [])  # dispositivos nuevos: sin alertas

        inicio = self.F360.gps_alertas()
        self.assertTrue(inicio['activo'])
        # Deja de reportar: alerta al instante por el bus y en el respaldo.
        self._sync([self._device(9001, 'QWZ981 - nuevo', 300, status='offline'),
                    self._device(9002, 'Equipo suelto 77', None)])
        self.assertEqual(d1.estado, 'sin_reporte')
        self.assertEqual(self._tipos_bus(), ['sin_reporte'])
        alertas = self.F360.gps_alertas(inicio['ultimo_id'])
        self.assertEqual([(e['tipo'], e['placa']) for e in alertas['eventos']], [('sin_reporte', 'QWZ-981')])
        # Vuelve a reportar.
        self._sync([self._device(9001, 'QWZ981 - nuevo', 0), self._device(9002, 'Equipo suelto 77', None)])
        self.assertEqual([e['tipo'] for e in self.F360.gps_alertas(alertas['ultimo_id'])['eventos']], ['volvio'])
        # Ya no existe en Traccar: se archiva.
        self._sync([self._device(9001, 'QWZ981 - nuevo', 0)])
        self.assertFalse(d2.active)

    def test_webhook_tiempo_real(self):
        self._sync([self._device(9401, 'QWZ981', 1)], [self._pos(9401, *CENTRO)])
        d = self.Disp.search([('traccar_id', '=', 9401)])
        # Traccar avisa la desconexión: alerta inmediata, sin esperar el umbral de minutos.
        res = self.Disp.procesar_webhook({'event': {'type': 'deviceOffline', 'deviceId': 9401},
                                          'device': self._device(9401, 'QWZ981', 1, status='offline')})
        self.assertTrue(res['ok'])
        self.assertEqual(d.traccar_status, 'offline')
        self.assertEqual(self._tipos_bus(), ['desconectado'])
        # Alarma SOS.
        self.Disp.procesar_webhook({'event': {'type': 'alarm', 'deviceId': 9401, 'attributes': {'alarm': 'sos'}},
                                    'device': self._device(9401, 'QWZ981', 0, status='online'),
                                    'position': self._pos(9401, *CENTRO, alarm='sos')})
        self.assertIn('alarma', self._tipos_bus())
        self.assertTrue(self.env['ir.config_parameter'].sudo().get_param('adt_flota_360.gps_webhook_ultimo'))

    def test_geocerca_alerta_entrada_y_salida(self):
        self._sync([self._device(9501, 'QWZ982', 1)], [self._pos(9501, *LEJOS)])
        with patch.object(AdtFlota360GpsGeocerca, '_publicar_traccar') as publicar:
            r = self.env['adt.flota360'].gps_geocerca_guardar(False, {
                'name': 'Base central', 'tipo': 'circulo', 'lat': CENTRO[0], 'lon': CENTRO[1], 'radio': 300,
                'entrada': True, 'salida': True, 'alcance': 'todos'})
            publicar.assert_called_once()
        # Primera posición con la geocerca: se inicializa sin alerta.
        self._sync([self._device(9501, 'QWZ982', 0)], [self._pos(9501, *LEJOS)])
        # Llega una posición dentro (por el webhook de posiciones).
        self.Disp.procesar_webhook({'position': self._pos(9501, *CENTRO), 'device': self._device(9501, 'QWZ982', 0)})
        self.Disp.procesar_webhook({'position': self._pos(9501, *LEJOS), 'device': self._device(9501, 'QWZ982', 0)})
        self.assertEqual(self._tipos_bus(), ['geocerca_entrada', 'geocerca_salida'])
        geo = self.F360.gps_tablero()['geocercas']
        self.assertEqual([g['name'] for g in geo if g['id'] == r['id']], ['Base central'])
        with self.assertRaises(AccessError):
            self.F360.gps_geocerca_guardar(False, {'name': 'X'})

    def test_importa_geocercas_de_traccar_sin_alertas(self):
        self._sync([], geofences=[{'id': 77001, 'name': 'Geo-Zona', 'area': 'CIRCLE (-11.86 -77.11, 50)'}])
        geo = self.env['adt.flota360.gps.geocerca'].search([('traccar_id', '=', 77001)])
        self.assertEqual((geo.tipo, geo.radio, geo.alertar_entrada), ('circulo', 50.0, False))

    def test_crear_vehiculos_faltantes(self):
        self._sync([self._device(9601, 'MKT555 - nuevo', 1), self._device(9602, 'MKT555 viejo', 1),
                    self._device(9603, 'Equipo suelto', 1)])
        d1, d2, d3 = (self.Disp.search([('traccar_id', '=', t)]) for t in (9601, 9602, 9603))
        with self.assertRaises(ValidationError):
            self.env['adt.flota360'].gps_crear_vehiculos((d1 | d2).ids)  # falta el modelo por defecto
        self.env['adt.flota360'].gps_config_guardar({'minutos_demora': 20, 'minutos_sin_reporte': 60,
                                                     'modelo_id': self.modelo.id})
        res = self.env['adt.flota360'].gps_crear_vehiculos((d1 | d2 | d3).ids)
        self.assertEqual((res['creados'], res['relacionados'], res['omitidos']), (1, 2, 1))
        self.assertEqual(d1.vehicle_id, d2.vehicle_id)
        self.assertEqual((d1.vehicle_id.license_plate, d1.vinculo_metodo), ('MKT555', 'creado'))
        # La sincronización conserva el vehículo creado.
        self._sync([self._device(9601, 'MKT555 - nuevo', 1)])
        # Con x_imei (adt_traccar_device) el vehículo creado guarda el IMEI y se relaciona por él.
        self.assertIn(d1.vinculo_metodo, ('imei', 'limpieza'))
        self.assertEqual(d1.vehicle_id.license_plate, 'MKT555')

    def test_relacion_manual_se_conserva(self):
        self._sync([self._device(9101, 'QWZ981', 1)])
        d = self.Disp.search([('traccar_id', '=', 9101)])
        self.assertEqual(d.vehicle_id, self.v1)
        self.F360.gps_vincular(d.id, self.v2.id)
        self._sync([self._device(9101, 'QWZ981', 1)])
        self.assertEqual((d.vehicle_id, d.vinculo_metodo), (self.v2, 'manual'))
        self.F360.gps_vinculo_automatico(d.id)
        self.assertEqual((d.vehicle_id, d.vinculo_manual), (self.v1, False))

    def test_tablero_y_ficha(self):
        self._sync([self._device(9201, 'QWZ982 viejo', 500)])
        data = self.F360.gps_tablero()
        item = next(i for i in data['items'] if i['nombre'] == 'QWZ982 viejo')
        self.assertEqual((item['estado'], item['placa']), ('sin_reporte', 'QWZ-982'))
        detalle = self.F360.gps_dispositivo(item['id'])
        self.assertEqual(detalle['vehicle_id'], self.v2.id)
        self.assertTrue(self.F360.gps_buscar_vehiculos('qwz982'))
        self.assertEqual(self.F360._lote_gps(self.v2.ids)[self.v2.id]['gps_status'], 'offline')

    def test_recorrido(self):
        self._sync([self._device(9701, 'QWZ981', 1)])
        d = self.Disp.search([('traccar_id', '=', 9701)])
        ruta = [self._pos(9701, *CENTRO), self._pos(9701, *LEJOS)]
        with patch('odoo.addons.adt_flota_360.models.flota_360_gps.Traccar') as T:
            t = T.return_value.__enter__.return_value
            t.leer_lista.side_effect = lambda ruta_api, *a, **k: ruta if ruta_api.endswith('route') else []
            r = self.F360.gps_recorrido(d.id, '2026-11-03 00:00:00', '2026-11-03 12:00:00')
        self.assertEqual(len(r['puntos']), 2)
        self.assertAlmostEqual(r['resumen']['distancia_km'], 1.1, delta=0.05)
        with self.assertRaises(ValidationError):
            self.F360.gps_recorrido(d.id, '2026-11-01 00:00:00', '2026-11-10 00:00:00')

    def test_traccar_caido_no_cambia_estados(self):
        self._sync([self._device(9301, 'QWZ981', 1)])
        d = self.Disp.search([('traccar_id', '=', 9301)])
        with patch.object(AdtFlota360GpsDispositivo, '_traccar_datos', side_effect=UserError('sin conexión')):
            res = self.Disp.sincronizar()
        self.assertFalse(res['ok'])
        self.assertEqual(d.estado, 'reportando')
        self.assertEqual(self.F360.gps_tablero()['meta']['error'], 'sin conexión')

    def test_prueba_de_notificacion_por_bus(self):
        self.F360.gps_probar_notificacion()
        self.assertTrue(any(m['payload'].get('prueba') for m in self._bus()))

    def test_configuracion_solo_manager(self):
        with self.assertRaises(AccessError):
            self.F360.gps_config_guardar({'minutos_demora': 10, 'minutos_sin_reporte': 30})
        admin = self.env['adt.flota360']
        with self.assertRaises(ValidationError):
            admin.gps_config_guardar({'minutos_demora': 30, 'minutos_sin_reporte': 30})
        meta = admin.gps_config_guardar({'minutos_demora': 10, 'minutos_sin_reporte': 45, 'frecuencia': 1,
                                         'palabras_ruido': 'nuevo, viejo', 'alertas': ['sin_reporte', 'alarma'],
                                         'alarmas': ['sos']})
        self.assertEqual((meta['minutos_demora'], meta['minutos_sin_reporte'], meta['frecuencia']), (10, 45, 1))
        self.assertEqual((meta['palabras_ruido'], meta['alertas'], meta['alarmas']), ('NUEVO VIEJO', ['sin_reporte', 'alarma'], ['sos']))
        self.assertIn('/adt_flota_360/gps/traccar/', meta['webhook_url'])
