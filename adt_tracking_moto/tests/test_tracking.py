# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTrackingMoto(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS Test'})
        cls.modelo = cls.env['fleet.vehicle.model'].create({'name': 'King Test', 'brand_id': brand.id})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Test'})
        cls.Tracking = cls.env['adt.moto.tracking']
        cls.taller = cls.env.ref('adt_tracking_moto.taller_fibra_ves')
        cls.usuario = new_test_user(
            cls.env, login='tracking_user', groups='base.group_user,fleet.fleet_group_user,'
                                                   'adt_tracking_moto.group_tracking_user')

    def _moto(self, **vals):
        return self.env['fleet.vehicle'].create(dict({'model_id': self.modelo.id, 'vin_sn': 'CH-TEST'}, **vals))

    def _tracking(self, moto):
        return self.Tracking.search([('vehicle_id', '=', moto.id)])

    def _etapa(self, codigo):
        return self.Tracking._etapa(codigo)

    def test_ingreso_automatico(self):
        tracking = self._tracking(self._moto())
        self.assertEqual(len(tracking), 1)
        self.assertEqual(tracking.etapa_codigo, 'recojo')
        self.assertEqual(tracking.estado_placa, 'pendiente')
        self.assertEqual(tracking.estado_global, 'en_proceso')
        self.assertTrue(tracking.name.startswith('TRK/'))
        # Placeholder de placa cuenta como sin placa.
        self.assertTrue(self._tracking(self._moto(license_plate='S/P')))

    def test_no_ingresa_con_placa_o_duenio(self):
        self.assertFalse(self._tracking(self._moto(license_plate='ABC-123')))
        self.assertFalse(self._tracking(self._moto(driver_id=self.cliente.id)))

    def test_moto_desde_factura_amarra_tramite(self):
        tipo = self.env['adt.facturacion.tipo'].search([('es_vehiculo', '=', True)], limit=1)
        factura = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.cliente.id,
            'x_facturacion_tipo_id': tipo.id, 'x_facturacion_modelo_id': self.modelo.id,
        })
        tracking = self._tracking(factura.x_facturacion_vehicle_id)
        self.assertEqual(tracking.factura_id, factura)
        self.assertEqual(tracking.tramite_placa_id.state, 'pendiente')
        self.assertEqual(tracking.estado_placa, 'pendiente')

    def test_flujo_logistico_con_tiempos(self):
        tracking = self._tracking(self._moto()).with_user(self.usuario)
        tracking.action_llevar_almacen()
        self.assertEqual(tracking.etapa_codigo, 'almacen')

        with self.assertRaises(UserError):
            tracking.write({'etapa_id': self._etapa('fibra').id})  # sin taller

        wizard = self.env['adt.moto.tracking.fibra.wizard'].with_user(self.usuario).with_context(
            active_model='adt.moto.tracking', active_ids=tracking.ids).create({'taller_id': self.taller.id})
        wizard.action_confirmar()
        self.assertEqual(tracking.etapa_codigo, 'fibra')
        self.assertEqual(tracking.taller_fibra_id, self.taller)

        tracking.action_regreso_fibra()
        self.assertEqual(tracking.estado_global, 'listo_asignar')
        self.assertTrue(all([tracking.fecha_recojo, tracking.fecha_ingreso_almacen,
                             tracking.fecha_envio_fibra, tracking.fecha_listo]))

        logs = tracking.log_ids.filtered(lambda l: l.flujo == 'logistica').sorted('id')
        self.assertEqual(logs.mapped('codigo_hasta'), ['recojo', 'almacen', 'fibra', 'listo'])
        self.assertEqual(logs[2].taller_fibra_id, self.taller)
        self.assertTrue(all(logs[:3].mapped('fecha_fin')))
        self.assertFalse(logs[3].fecha_fin)

    def test_usuario_no_salta_etapas(self):
        tracking = self._tracking(self._moto())
        with self.assertRaises(UserError):
            tracking.with_user(self.usuario).write({'etapa_id': self._etapa('listo').id})
        # El administrador sí puede (p. ej. corregir datos).
        tracking.write({'etapa_id': self._etapa('listo').id})
        self.assertEqual(tracking.etapa_codigo, 'listo')

    def test_nombre_etapa_editable(self):
        etapa = self._etapa('recojo')
        etapa.name = 'Distribuidor'
        tracking = self._tracking(self._moto())
        self.assertEqual(tracking.etapa_id.name, 'Distribuidor')
        with self.assertRaises(UserError):
            etapa.unlink()
        with self.assertRaises(UserError):
            self.env['adt.moto.tracking.etapa'].with_user(self.usuario).create({'name': 'X', 'codigo': 'recojo'})

    def test_flujo_placa_con_tramite(self):
        moto = self._moto()
        tracking = self._tracking(moto)
        self.assertFalse(tracking.tramite_placa_id)  # creada a mano, sin factura

        tracking.action_iniciar_tramite()  # crea el trámite y lo inicia
        tramite = tracking.tramite_placa_id
        self.assertEqual(tramite.state, 'en_tramite')
        self.assertEqual(tracking.estado_placa, 'en_tramite')
        self.assertTrue(tracking.fecha_inicio_tramite)

        tramite._observar('Falta DUA')
        self.assertEqual(tracking.estado_placa, 'observado')
        self.assertEqual(tracking.cant_observaciones, 1)
        log_obs = tracking.log_ids.filtered(lambda l: l.codigo_hasta == 'observado')
        self.assertEqual(log_obs.nota, 'Falta DUA')

        tramite.action_levantar_observacion()
        self.assertEqual(tracking.estado_placa, 'en_tramite')

        tramite.write({'num_placa': 'XYZ-987'})
        tramite.action_finalizar()
        self.assertEqual(tracking.estado_placa, 'finalizado')
        self.assertEqual(moto.license_plate, 'XYZ-987')
        self.assertTrue(tracking.fecha_placa_ok)
        placa = tracking.log_ids.filtered(lambda l: l.flujo == 'placa').sorted('id')
        self.assertEqual(placa.mapped('codigo_hasta'),
                         ['pendiente', 'en_tramite', 'observado', 'en_tramite', 'finalizado'])

    def test_asignacion_antes_de_listo_solo_advierte(self):
        moto = self._moto()
        tracking = self._tracking(moto)
        moto.write({'driver_id': self.cliente.id})
        self.assertEqual(tracking.partner_id, self.cliente)
        self.assertTrue(tracking.asignado_antes_listo)
        self.assertTrue(tracking.fecha_asignacion)
        self.assertEqual(tracking.estado_global, 'asignado_sin_placa')
        self.assertTrue(tracking.log_ids.filtered(lambda l: l.flujo == 'hito'))

    def test_entrega_cierra_tracking(self):
        moto = self._moto()
        tracking = self._tracking(moto)
        tracking.write({'etapa_id': self._etapa('listo').id})
        moto.write({'driver_id': self.cliente.id})
        self.assertFalse(tracking.asignado_antes_listo)

        moto.write({'fecha_entrega': '2026-10-10'})
        self.assertEqual(tracking.estado_global, 'asignado_sin_placa')  # entregada pero sin placa

        moto.write({'license_plate': 'ABC-123'})  # sin trámite: la placa real basta
        self.assertEqual(tracking.estado_placa, 'finalizado')
        self.assertEqual(tracking.estado_global, 'entregado')
        self.assertTrue(tracking.fecha_cierre)
        self.assertFalse(tracking.log_ids.filtered(lambda l: not l.fecha_fin))

    def test_sincronizar_existentes(self):
        Tramite = self.env['adt.tramite.placa']
        sin_nada = self._moto()
        sin_placa_con_duenio = self._moto(driver_id=self.cliente.id)
        con_placa_sin_duenio = self._moto(license_plate='ABC-111')
        completo = self._moto(license_plate='ABC-222', driver_id=self.cliente.id)
        self._tracking(sin_nada).unlink()  # simula que ya existía antes del módulo

        wizard = self.env['adt.moto.tracking.sincronizar.wizard'].create({})
        self.assertGreaterEqual(wizard.cantidad, 3)
        wizard.action_confirmar()

        t = self._tracking(sin_nada)
        self.assertEqual(t.etapa_codigo, 'almacen')
        self.assertFalse(t.fecha_recojo)
        self.assertEqual(t.tramite_placa_id.state, 'pendiente')

        t = self._tracking(sin_placa_con_duenio)
        self.assertEqual(t.etapa_codigo, 'listo')
        self.assertEqual(t.estado_global, 'asignado_sin_placa')
        self.assertFalse(t.asignado_antes_listo)
        self.assertTrue(t.tramite_placa_id)

        t = self._tracking(con_placa_sin_duenio)
        self.assertEqual(t.etapa_codigo, 'almacen')
        self.assertEqual(t.estado_placa, 'finalizado')
        self.assertFalse(Tramite.search([('vehicle_id', '=', con_placa_sin_duenio.id)]))

        self.assertFalse(self._tracking(completo))
        self.assertFalse(Tramite.search([('vehicle_id', '=', completo.id)]))

    def test_usuario_no_salta_etapas(self):
        tracking = self._tracking(self._moto())
        with self.assertRaises(UserError):
            tracking.with_user(self.usuario).write({'etapa_id': self._etapa('listo').id})
        # El administrador sí puede (p. ej. corregir datos).
        tracking.write({'etapa_id': self._etapa('listo').id})
        self.assertEqual(tracking.etapa_codigo, 'listo')

    def test_nombre_etapa_editable(self):
        etapa = self._etapa('recojo')
        etapa.name = 'Distribuidor'
        tracking = self._tracking(self._moto())
        self.assertEqual(tracking.etapa_id.name, 'Distribuidor')
        with self.assertRaises(UserError):
            etapa.unlink()
        with self.assertRaises(UserError):
            self.env['adt.moto.tracking.etapa'].with_user(self.usuario).create({'name': 'X', 'codigo': 'recojo'})

    def test_flujo_placa_con_tramite(self):
        moto = self._moto()
        tracking = self._tracking(moto)
        self.assertFalse(tracking.tramite_placa_id)  # creada a mano, sin factura

        tracking.action_iniciar_tramite()  # crea el trámite y lo inicia
        tramite = tracking.tramite_placa_id
        self.assertEqual(tramite.state, 'en_tramite')
        self.assertEqual(tracking.estado_placa, 'en_tramite')
        self.assertTrue(tracking.fecha_inicio_tramite)

        tramite._observar('Falta DUA')
        self.assertEqual(tracking.estado_placa, 'observado')
        self.assertEqual(tracking.cant_observaciones, 1)
        log_obs = tracking.log_ids.filtered(lambda l: l.codigo_hasta == 'observado')
        self.assertEqual(log_obs.nota, 'Falta DUA')

        tramite.action_levantar_observacion()
        self.assertEqual(tracking.estado_placa, 'en_tramite')

        tramite.write({'num_placa': 'XYZ-987'})
        tramite.action_finalizar()
        self.assertEqual(tracking.estado_placa, 'finalizado')
        self.assertEqual(moto.license_plate, 'XYZ-987')
        self.assertTrue(tracking.fecha_placa_ok)
        placa = tracking.log_ids.filtered(lambda l: l.flujo == 'placa').sorted('id')
        self.assertEqual(placa.mapped('codigo_hasta'),
                         ['pendiente', 'en_tramite', 'observado', 'en_tramite', 'finalizado'])

    def test_asignacion_antes_de_listo_solo_advierte(self):
        moto = self._moto()
        tracking = self._tracking(moto)
        moto.write({'driver_id': self.cliente.id})
        self.assertEqual(tracking.partner_id, self.cliente)
        self.assertTrue(tracking.asignado_antes_listo)
        self.assertTrue(tracking.fecha_asignacion)
        self.assertEqual(tracking.estado_global, 'asignado_sin_placa')
        self.assertTrue(tracking.log_ids.filtered(lambda l: l.flujo == 'hito'))

    def test_entrega_cierra_tracking(self):
        moto = self._moto()
        tracking = self._tracking(moto)
        tracking.write({'etapa_id': self._etapa('listo').id})
        moto.write({'driver_id': self.cliente.id})
        self.assertFalse(tracking.asignado_antes_listo)

        moto.write({'fecha_entrega': '2026-10-10'})
        self.assertEqual(tracking.estado_global, 'asignado_sin_placa')  # entregada pero sin placa

        moto.write({'license_plate': 'ABC-123'})  # sin trámite: la placa real basta
        self.assertEqual(tracking.estado_placa, 'finalizado')
        self.assertEqual(tracking.estado_global, 'entregado')
        self.assertTrue(tracking.fecha_cierre)
        self.assertFalse(tracking.log_ids.filtered(lambda l: not l.fecha_fin))

    def test_sincronizar_existentes(self):
        moto = self._moto()
        self._tracking(moto).unlink()
        wizard = self.env['adt.moto.tracking.sincronizar.wizard'].create({})
        self.assertGreaterEqual(wizard.cantidad, 1)
        wizard.action_confirmar()
        tracking = self._tracking(moto)
        self.assertEqual(tracking.etapa_codigo, 'almacen')
        self.assertFalse(tracking.fecha_recojo)

    def test_sincronizar_muestra_cantidad_al_abrir(self):
        """El contador (y con él el botón Sincronizar) debe venir lleno al abrir el asistente."""
        from odoo.tests import Form
        moto = self._moto()
        self._tracking(moto).unlink()
        formulario = Form(self.env['adt.moto.tracking.sincronizar.wizard'])
        self.assertGreaterEqual(formulario.cantidad, 1)
        self.assertGreaterEqual(formulario.cantidad_sin_placa, 1)
        formulario.save().action_confirmar()
        self.assertTrue(self._tracking(moto))
        self.assertEqual(Form(self.env['adt.moto.tracking.sincronizar.wizard']).cantidad, 0)

    def test_demorado_usa_historico_sin_sla(self):
        from datetime import timedelta
        from odoo import fields
        Log = self.env['adt.moto.tracking.log']
        ahora = fields.Datetime.now()
        base = self._tracking(self._moto())
        for i in range(6):  # 6 casos cerrados de ~2 días en "Gambeta"
            Log.create({'tracking_id': base.id, 'flujo': 'logistica', 'codigo_hasta': 'recojo',
                        'fecha_inicio': ahora - timedelta(days=10), 'fecha_fin': ahora - timedelta(days=8)})
        lenta = self._tracking(self._moto())
        lenta.fecha_etapa = ahora - timedelta(days=5)
        rapida = self._tracking(self._moto())
        self.assertFalse(self._etapa('recojo').sla_horas)
        self.assertTrue(lenta.demorado)
        self.assertFalse(rapida.demorado)
        self.assertIn(lenta, self.Tracking.search([('demorado', '=', True)]))

    def test_historial_cuenta_como_finalizado(self):
        tracking = self._tracking(self._moto())
        tracking.action_iniciar_tramite()
        tramite = tracking.tramite_placa_id
        tramite.write({'num_placa': 'HIS-777'})
        tramite.action_finalizar()
        tramite.write({'state': 'historial'})
        self.assertEqual(tracking.estado_placa, 'finalizado')
