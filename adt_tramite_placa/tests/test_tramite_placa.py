# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTramitePlaca(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.modelo = cls.env['fleet.vehicle.model'].create({
            'name': 'King Test', 'brand_id': cls.env['fleet.vehicle.model.brand'].create({'name': 'TVS T'}).id,
        })
        cls.tipo = cls.env['adt.facturacion.tipo'].search([('es_vehiculo', '=', True)], limit=1)
        cls.proveedor = cls.env['res.partner'].create({'name': 'Proveedor Test'})

    def _factura(self):
        return self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.proveedor.id,
            'x_facturacion_tipo_id': self.tipo.id, 'x_facturacion_modelo_id': self.modelo.id,
            'x_facturacion_chasis': 'CH-PLACA',
        })

    def test_se_crea_desde_factura(self):
        moto = self._factura().x_facturacion_vehicle_id
        tramite = moto.adt_tramite_placa_id
        self.assertEqual(tramite.state, 'pendiente')
        self.assertEqual(tramite.proveedor_id, self.proveedor)
        # Un vehículo creado a mano (sin factura) no recibe trámite.
        manual = self.env['fleet.vehicle'].create({'model_id': self.modelo.id})
        self.assertFalse(manual.adt_tramite_placa_id)

    def test_flujo_completo(self):
        moto = self._factura().x_facturacion_vehicle_id
        tramite = moto.adt_tramite_placa_id
        with self.assertRaises(UserError):
            tramite.action_finalizar()  # todavía no se inició

        tramite.action_iniciar()
        self.assertEqual(tramite.state, 'en_tramite')
        self.assertTrue(tramite.fecha_inicio)

        wizard_action = tramite.action_observar()
        self.env[wizard_action['res_model']].with_context(wizard_action['context']).create(
            {'motivo': 'Falta DUA'}).action_confirmar()
        self.assertEqual(tramite.state, 'observado')
        self.assertEqual(tramite.motivo_observacion, 'Falta DUA')
        self.assertEqual(tramite.cant_observaciones, 1)

        tramite.action_levantar_observacion()
        self.assertEqual(tramite.state, 'en_tramite')

        with self.assertRaises(UserError):
            tramite.action_finalizar()  # sin número de placa
        tramite.write({'num_placa': 'abc-123', 'tarjeta_propiedad': b'UERG'})
        tramite.action_finalizar()
        self.assertEqual(tramite.state, 'finalizado')
        self.assertTrue(tramite.fecha_fin)
        self.assertEqual(moto.license_plate, 'ABC-123')
        if 'tarjeta_propiedad_attachment' in moto._fields:
            self.assertEqual(moto.tarjeta_propiedad_attachment, b'UERG')

    def test_finalizado_pasa_a_historial(self):
        from datetime import timedelta
        from odoo import fields
        from odoo.tests import Form
        moto = self._factura().x_facturacion_vehicle_id
        tramite = moto.adt_tramite_placa_id
        tramite.action_iniciar()
        tramite.write({'num_placa': 'HIS-001'})
        tramite.action_finalizar()
        Tramite = self.env['adt.tramite.placa']
        self.assertEqual(Tramite._dias_finalizado(), 7)  # valor por defecto

        tramite.fecha_fin = fields.Datetime.now() - timedelta(days=6)
        Tramite._cron_pasar_a_historial()
        self.assertEqual(tramite.state, 'finalizado')  # aún dentro de los 7 días

        tramite.fecha_fin = fields.Datetime.now() - timedelta(days=8)
        Tramite._cron_pasar_a_historial()
        self.assertEqual(tramite.state, 'historial')
        self.assertTrue(tramite.fecha_historial)
        self.assertEqual(moto.license_plate, 'HIS-001')

        # Configurable: con 10 días, uno de 8 días no se mueve.
        formulario = Form(self.env['adt.tramite.placa.config'])
        self.assertEqual(formulario.dias_finalizado, 7)
        formulario.dias_finalizado = 10
        formulario.save().action_guardar()
        self.assertEqual(Tramite._dias_finalizado(), 10)
        otro = self.env['adt.tramite.placa'].create({'vehicle_id': self.env['fleet.vehicle'].create({'model_id': self.modelo.id}).id})
        otro.action_iniciar()
        otro.write({'num_placa': 'HIS-002'})
        otro.action_finalizar()
        otro.fecha_fin = fields.Datetime.now() - timedelta(days=8)
        Tramite._cron_pasar_a_historial()
        self.assertEqual(otro.state, 'finalizado')

        tramite.action_reabrir()
        self.assertEqual(tramite.state, 'en_tramite')
