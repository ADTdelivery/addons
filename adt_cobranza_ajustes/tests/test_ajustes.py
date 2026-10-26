# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import SavepointCase, tagged


@tagged('post_install', '-at_install')
class TestAjustes(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'QA ajustes', 'currency_id': cls.env.company.currency_id.id})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        receivable = cls.env['account.account'].create({'name': 'QA aj receivable', 'code': 'QAAJR',
            'user_type_id': cls.env.ref('account.data_account_type_receivable').id,
            'company_id': cls.company.id, 'reconcile': True})
        bank = cls.env['account.account'].create({'name': 'QA aj bank', 'code': 'QAAJB',
            'user_type_id': cls.env.ref('account.data_account_type_liquidity').id, 'company_id': cls.company.id})
        cls.journal = cls.env['account.journal'].create({'name': 'QA aj bank', 'code': 'QAAJ', 'type': 'bank',
            'company_id': cls.company.id, 'default_account_id': bank.id,
            'inbound_payment_method_line_ids': [(0, 0, {'payment_method_id': cls.env.ref('account.account_payment_method_manual_in').id,
                'payment_account_id': bank.id})]})
        cls.partner = cls.env['res.partner'].create({'name': 'QA cliente ajuste', 'property_account_receivable_id': receivable.id})
        model = cls.env['fleet.vehicle.model'].create({'name': 'QAAJ model',
            'brand_id': cls.env['fleet.vehicle.model.brand'].create({'name': 'QAAJ brand'}).id})
        cls.vehicle = cls.env['fleet.vehicle'].create({'model_id': model.id, 'company_id': cls.company.id, 'license_plate': 'QAAJ001'})
        cls.cuenta = cls.env['adt.comercial.cuentas'].create({'partner_id': cls.partner.id, 'vehiculo_id': cls.vehicle.id,
            'company_id': cls.company.id, 'state': 'en_curso', 'reference_no': 'QAAJ001', 'periodicidad': 'semanal'})
        hoy = fields.Date.today()
        cls.hoy = hoy
        Cuota = cls.env['adt.comercial.cuotas']
        cls.c1, cls.c2, cls.c3, cls.c4 = [Cuota.create({'cuenta_id': cls.cuenta.id, 'company_id': cls.company.id,
            'name': 'Cuota %s' % (i + 1), 'monto': 100, 'fecha_cronograma': hoy + timedelta(days=d)})
            for i, d in enumerate((-10, 4, 11, 18))]
        cls.Ajuste = cls.env['adt.cobranza.ajuste']

    def pagar(self, cuota, monto):
        pago = self.env['account.payment'].create({'payment_type': 'inbound', 'journal_id': self.journal.id,
            'cuota_id': cuota.id, 'amount': monto, 'date': self.hoy, 'partner_id': self.partner.id,
            'ref': 'QAAJ-%s-%s' % (cuota.id, monto)})
        pago.action_post()
        cuota.invalidate_cache()
        return pago

    def aplicar(self, **vals):
        vals = dict({'cuenta_id': self.cuenta.id, 'motivo': 'Acuerdo QA'}, **vals)
        filas = vals.pop('filas', None)
        return self.Ajuste.aplicar(vals, filas)

    def deuda(self):
        self.cuenta.cuota_ids.invalidate_cache()
        return round(sum(q.saldo for q in self.cuenta.cuota_ids if q.state not in ('pagado', 'anulada')), 2)

    def test_reprogramar_al_final_perdonando_mora(self):
        self.assertGreater(self.c1.mora_pendiente, 0)
        ajuste = self.aplicar(tipo='reprogramar', cuota_id=self.c1.id, destino='final', mora_accion='perdonar')
        self.assertEqual(self.c1.fecha_cronograma, self.c4.fecha_cronograma + timedelta(days=7))
        self.assertEqual(self.c1.ajuste_estado, 'reprogramada')
        self.assertEqual(self.c1.mora_pendiente, 0)
        self.assertEqual(ajuste.mora_perdonada, ajuste.mora_calculada)
        self.assertEqual(self.deuda(), 400)

    def test_reprogramar_con_abono_deja_la_mora_acordada_en_la_cuota_nueva(self):
        self.pagar(self.c1, 40)
        self.assertEqual(self.c1.state, 'a_cuenta')
        ajuste = self.aplicar(tipo='reprogramar', cuota_id=self.c1.id, destino='despues', cuota_ref_id=self.c2.id,
                              mora_accion='cuota', mora_acordada=5)
        self.assertEqual(self.c1.state, 'pagado')
        self.assertEqual(self.c1.monto, 40)
        self.assertEqual(self.c1.monto_pactado, 100)
        nueva = ajuste.linea_ids.filtered(lambda l: l.accion == 'creada').cuota_id
        self.assertEqual(nueva.saldo, 60)
        self.assertEqual(nueva.fecha_cronograma, self.hoy + timedelta(days=11))
        self.assertEqual(self.c3.fecha_cronograma, self.hoy + timedelta(days=18), 'las siguientes se corren un periodo')
        self.assertEqual(nueva.mora_pendiente, 5)
        self.assertEqual(self.deuda(), 360)

    def test_trasladar_saldo_cierra_la_cuota_y_suma_al_destino(self):
        self.pagar(self.c1, 30)
        self.aplicar(tipo='trasladar', cuota_id=self.c1.id, cuota_ref_id=self.c2.id, mora_accion='perdonar')
        self.assertEqual(self.c1.state, 'pagado')
        self.assertEqual(self.c1.ajuste_estado, 'cerrada')
        self.assertEqual(self.c2.monto, 170)
        self.assertEqual(self.c2.monto_pactado, 100)
        self.assertEqual(self.deuda(), 370)

    def test_trasladar_sin_pagos_deja_la_cuota_trasladada(self):
        self.aplicar(tipo='trasladar', cuota_id=self.c2.id, cuota_ref_id=self.c3.id)
        self.assertEqual(self.c2.state, 'anulada')
        self.assertEqual(self.c2.ajuste_estado, 'trasladada')
        self.assertEqual(self.c3.saldo, 200)
        self.assertEqual(self.deuda(), 400)

    def test_mora_como_cargo_con_descuento(self):
        calculada = self.c1.mora_pendiente
        ajuste = self.aplicar(tipo='mora', cuota_id=self.c1.id, mora_accion='cargo', mora_acordada=5, mora_fecha=self.hoy)
        cargo = ajuste.linea_ids.filtered(lambda l: l.accion == 'creada').cuota_id
        self.assertEqual((cargo.type, cargo.monto), ('mora', 5))
        self.assertEqual(self.c1.mora_pendiente, 0)
        self.assertAlmostEqual(ajuste.mora_perdonada, calculada - 5)
        with self.assertRaises(ValidationError):
            self.aplicar(tipo='mora', cuota_id=self.c1.id, mora_accion='cargo', mora_acordada=0)

    def test_agregar_cuota_redistribuyendo_no_cambia_el_total(self):
        ajuste = self.aplicar(tipo='insertar', nombre='Extra', monto=150, cuota_tipo='cuota', destino='despues',
                              cuota_ref_id=self.c2.id, origen='redistribuir')
        nueva = ajuste.linea_ids.filtered(lambda l: l.accion == 'creada').cuota_id
        self.assertEqual(nueva.fecha_cronograma, self.hoy + timedelta(days=11))
        self.assertEqual((self.c4.ajuste_estado, self.c4.state), ('eliminada', 'anulada'), 'la última cuota se descuenta completa')
        self.assertEqual(self.c3.monto, 50)
        self.assertEqual(self.deuda(), 400)

    def test_editor_exige_que_el_total_cuadre(self):
        filas = [{'id': q.id, 'nombre': q.name, 'fecha': str(q.fecha_cronograma), 'saldo': s}
                 for q, s in ((self.c1, 100), (self.c2, 150), (self.c3, 50), (self.c4, 100))]
        ajuste = self.aplicar(tipo='editar', mora_accion='perdonar', filas=filas)
        self.assertEqual((self.c2.monto, self.c3.monto), (150, 50))
        self.assertEqual(ajuste.deuda_despues, 400)
        filas[0]['saldo'] = 90
        with self.assertRaises(ValidationError):
            self.aplicar(tipo='editar', mora_accion='perdonar', filas=filas)
        # Con motivo se acepta un total distinto y queda registrada la diferencia.
        filas[0]['saldo'] = 120
        ajuste = self.aplicar(tipo='editar', mora_accion='perdonar', filas=filas, diferencia_motivo='Descuento por pronto pago')
        self.assertEqual(ajuste.diferencia, 20)
        self.assertIn('Descuento por pronto pago', ajuste.resumen)
        self.assertEqual(ajuste._resumen_dict()['diferencia_motivo'], 'Descuento por pronto pago')

    def test_editor_incluye_la_mora_y_agrega_filas(self):
        mora = round(sum(self.cuenta.cuota_ids.mapped('mora_pendiente')), 2)
        filas = [{'id': self.c1.id, 'nombre': 'Cuota 1', 'fecha': str(self.hoy), 'saldo': 100 + mora},
                 {'id': self.c2.id, 'nombre': 'Cuota 2', 'fecha': str(self.c2.fecha_cronograma), 'saldo': 100},
                 {'id': False, 'nombre': 'Nueva', 'fecha': str(self.hoy + timedelta(days=30)), 'saldo': 200}]
        self.aplicar(tipo='editar', mora_accion='incluir', filas=filas)
        self.assertEqual(set((self.c3 | self.c4).mapped('state')), {'anulada'})
        self.assertEqual(self.deuda(), 400 + mora)
        self.assertEqual(sum(self.cuenta.cuota_ids.mapped('mora_pendiente')), 0)

    def test_deshacer_restaura_las_cuotas(self):
        fecha_c1 = self.c1.fecha_cronograma
        ajuste = self.aplicar(tipo='insertar', nombre='Extra', monto=150, cuota_tipo='cuota', destino='despues',
                              cuota_ref_id=self.c2.id, origen='redistribuir')
        self.aplicar(tipo='reprogramar', cuota_id=self.c1.id, destino='final', mora_accion='perdonar')
        with self.assertRaises(UserError):
            ajuste._revertir()
        ultimo = self.Ajuste.search([('cuenta_id', '=', self.cuenta.id)], limit=1)
        ultimo._revertir()
        self.assertEqual(self.c1.fecha_cronograma, fecha_c1)
        self.assertGreater(self.c1.mora_pendiente, 0)
        ajuste._revertir()
        cuotas = self.cuenta.cuota_ids
        self.assertEqual(sorted(cuotas.mapped('monto')), [100, 100, 100, 100])
        self.assertFalse(cuotas.filtered('ajuste_estado'))
        self.assertEqual(self.c3.fecha_cronograma, self.hoy + timedelta(days=11))
        self.assertEqual(ajuste.estado, 'revertido')

    def test_deshacer_bloqueado_si_hubo_pagos_despues(self):
        ajuste = self.aplicar(tipo='trasladar', cuota_id=self.c2.id, cuota_ref_id=self.c3.id)
        self.pagar(self.c3, 50)
        with self.assertRaises(UserError):
            ajuste._revertir()

    def test_vista_previa_no_guarda_cambios(self):
        res = self.Ajuste.simular({'cuenta_id': self.cuenta.id, 'motivo': 'x', 'tipo': 'trasladar',
                                   'cuota_id': self.c2.id, 'cuota_ref_id': self.c3.id})
        self.assertTrue(res['lineas'])
        self.assertEqual(self.c3.monto, 100)
        self.assertFalse(self.Ajuste.search([('cuenta_id', '=', self.cuenta.id)]))

    def test_flota360_formulario_y_ficha(self):
        svc = self.env['adt.flota360']
        spec = svc.formulario('ajuste', self.vehicle.id, params={'tipo': 'reprogramar', 'cuota_id': self.c1.id})
        nombres = [c['name'] for s in spec['secciones'] for c in s['campos']]
        self.assertIn('mora_accion', nombres)
        prev = svc.simular_ajuste(self.vehicle.id, {'tipo': 'reprogramar', 'cuota_id': self.c1.id}, spec['valores'])
        self.assertNotIn('error', prev)
        valores = dict(spec['valores'], motivo='Se pasa al final')
        svc.guardar('ajuste', self.vehicle.id, valores, params={'tipo': 'reprogramar', 'cuota_id': self.c1.id})
        seccion = svc._seccion_cuentas(self.vehicle, self.hoy)
        cuenta = seccion['deuda'][0]
        self.assertEqual(len(cuenta['ajustes']), 1)
        self.assertTrue(cuenta['ajustes'][0]['deshacer'])
        self.assertEqual(cuenta['cuotas'][-1]['id'], self.c1.id, 'la cuota reprogramada va al final')

    def test_eliminar_cuota_queda_en_historial_y_se_deshace(self):
        mensajes = len(self.cuenta.message_ids)
        ajuste = self.aplicar(tipo='eliminar', cuota_id=self.c4.id, motivo='Cuota duplicada')
        self.assertEqual((self.c4.ajuste_estado, self.c4.state, self.c4.monto), ('eliminada', 'anulada', 0))
        self.assertEqual(self.deuda(), 300)
        self.assertGreater(len(self.cuenta.message_ids), mensajes, 'deja una nota en la cuenta')
        ajuste._revertir()
        self.assertEqual((self.c4.ajuste_estado, self.c4.monto), (False, 100))
        self.assertEqual(self.deuda(), 400)
        self.pagar(self.c3, 10)
        with self.assertRaises(ValidationError):
            self.aplicar(tipo='eliminar', cuota_id=self.c3.id)

    def test_refinanciamiento_guarda_el_cronograma_antes_y_despues(self):
        filas = [{'id': self.c1.id, 'nombre': 'Cuota 1', 'fecha': str(self.c1.fecha_cronograma), 'saldo': 200},
                 {'id': self.c2.id, 'nombre': 'Cuota 2', 'fecha': str(self.c2.fecha_cronograma), 'saldo': 200}]
        ajuste = self.aplicar(tipo='editar', mora_accion='perdonar', filas=filas)
        cron = ajuste._resumen_dict()['cronograma']
        self.assertEqual(len(cron['antes']), 4)
        self.assertEqual([f['saldo'] for f in cron['despues']], [200, 200])
        res = self.Ajuste.simular({'cuenta_id': self.cuenta.id, 'motivo': 'x', 'tipo': 'eliminar', 'cuota_id': self.c2.id})
        self.assertTrue(res['lineas'])
        self.assertEqual((self.c2.monto, self.c2.ajuste_estado), (200, False), 'la vista previa no guarda la eliminación')
