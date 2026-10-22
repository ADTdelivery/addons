from odoo import fields
from odoo.tests.common import SavepointCase, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestPagosFlota360(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'QA pagos Flota360', 'currency_id': cls.env.company.currency_id.id})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        receivable = cls.env['account.account'].create({'name': 'QA receivable', 'code': 'QA360R',
            'user_type_id': cls.env.ref('account.data_account_type_receivable').id,
            'company_id': cls.company.id, 'reconcile': True})
        bank = cls.env['account.account'].create({'name': 'QA bank', 'code': 'QA360B',
            'user_type_id': cls.env.ref('account.data_account_type_liquidity').id, 'company_id': cls.company.id})
        cls.journal = cls.env['account.journal'].create({'name': 'QA bank', 'code': 'QA360', 'type': 'bank',
            'company_id': cls.company.id, 'default_account_id': bank.id,
            'inbound_payment_method_line_ids': [(0, 0, {'payment_method_id': cls.env.ref('account.account_payment_method_manual_in').id,
                'payment_account_id': bank.id})]})
        cls.partner = cls.env['res.partner'].create({'name': 'QA cliente pago', 'property_account_receivable_id': receivable.id})
        model = cls.env['fleet.vehicle.model'].create({'name': 'QA360 model',
            'brand_id': cls.env['fleet.vehicle.model.brand'].create({'name': 'QA360 brand'}).id})
        cls.vehicle = cls.env['fleet.vehicle'].create({'model_id': model.id, 'company_id': cls.company.id, 'license_plate': 'QA360PAY'})
        cls.account = cls.env['adt.comercial.cuentas'].create({'partner_id': cls.partner.id,
            'vehiculo_id': cls.vehicle.id, 'company_id': cls.company.id, 'state': 'en_curso', 'reference_no': 'QA360PAY'})
        cls.quota = cls.env['adt.comercial.cuotas'].create({'cuenta_id': cls.account.id, 'company_id': cls.company.id,
            'name': '1', 'monto': 100, 'fecha_cronograma': fields.Date.today()})
        cls.service = cls.env['adt.flota360']

    def pay(self, tipo='cuota', **values):
        data = {'payment_date': str(fields.Date.today()), 'journal_id': self.journal.id,
            'amount': 100, 'communication': 'QA360-OP', 'mora_manual': False, 'mora_state': 'pending'}
        data.update(values)
        return self.service.guardar('pago', self.vehicle.id, data,
            params={'tipo': tipo, 'id': self.account.id if tipo == 'cascada' else self.quota.id})

    def test_native_form_uses_same_company_journal(self):
        spec = self.service.formulario('pago', self.vehicle.id, params={'tipo': 'cuota', 'id': self.quota.id})
        self.assertEqual(spec['clave'], 'pago')
        self.assertEqual(spec['pago_resumen']['capital'], 100)
        self.assertEqual(spec['valores']['journal_id'], self.journal.id)
        self.assertFalse(self.env['adt.register.payment'].search([('cuota_id', '=', self.quota.id)]))

    def test_partial_payment_posts_and_generates_remaining_installment(self):
        self.pay(amount=40)
        payment = self.quota.payment_ids
        self.assertEqual(payment.state, 'posted')
        self.assertEqual(payment.amount, 40)
        self.assertEqual(sum(self.quota.child_ids.mapped('saldo')), 60)
        with self.assertRaises(ValidationError):
            self.service.guardar('pago', self.vehicle.id,
                {'payment_date': str(fields.Date.today()), 'journal_id': self.journal.id,
                 'amount': 10, 'communication': 'QA360-OP'},
                params={'tipo': 'cuota', 'id': self.quota.child_ids.id})

    def test_invalid_amounts_do_not_create_payments(self):
        for amount in [0, -1, 101, float('nan'), float('inf')]:
            with self.assertRaises(ValidationError):
                self.pay(amount=amount)
        self.assertFalse(self.quota.payment_ids)
        with self.assertRaises(ValidationError):
            self.pay(journal_id=0)

    def test_wrong_vehicle_is_rejected(self):
        vehicle = self.vehicle.copy({'license_plate': 'OTHERQA'})
        with self.assertRaises(AccessError):
            self.service.formulario('pago', vehicle.id, params={'tipo': 'cuota', 'id': self.quota.id})

    def test_partial_mora_uses_existing_payment_logic(self):
        self.pay(mora_manual=True, mora=20)
        self.pay(tipo='mora', amount=5, mora_operacion='QA360-MORA')
        self.assertEqual(self.quota.payment_ids.mora_pagado, 5)
        result = self.service.simular_pago(self.vehicle.id, {'tipo': 'mora', 'id': self.quota.id})
        self.assertEqual(result['total'], 15)
        with self.assertRaises(ValidationError):
            self.pay(tipo='mora', amount=5, mora_operacion='QA360-MORA')
        self.assertEqual(self.quota.payment_ids.mora_pagado, 5)

    def test_cascade_payment_uses_existing_distribution(self):
        self.pay(tipo='cascada', cancelar_todo=False, monto=40, numero_operacion='QA360-CASCADE')
        payments = self.env['account.payment'].search([('cuota_id.cuenta_id', '=', self.account.id)])
        self.assertEqual(sum(payments.mapped('amount')), 40)
        self.assertTrue(all(p.state == 'posted' for p in payments))
        self.assertEqual(sum(self.account.cuota_ids.mapped('saldo')), 60)

    def test_vehicle_reports_have_explicit_labels_and_target_current_vehicle(self):
        # adt_fleet is optional; when present both existing report actions must target this vehicle.
        if not hasattr(self.vehicle, 'action_print_acta_vehicular'):
            self.skipTest('adt_fleet no está instalado')
        section = self.service._seccion_vehiculo(self.vehicle)
        actions = section['menu'][0]['acciones']
        labels = {a['method']: a['label'] for a in actions}
        self.assertEqual(labels['action_print_acta_vehicular'], 'Acta de entrega vehicular')
        self.assertEqual(labels['action_print_contrato_tvs'], 'Contrato TVS')
        for method, report in [('action_print_acta_vehicular', 'adt_fleet.report_acta_vehicular'),
                               ('action_print_contrato_tvs', 'adt_fleet.report_contrato_tvs')]:
            action = getattr(self.vehicle.with_context(discard_logo_check=True), method)()
            self.assertEqual(action['report_name'], report)
            self.assertEqual(action['context']['active_ids'], self.vehicle.ids)

    def test_credit_section_visible_without_technical_tracking_permission(self):
        user = self.env['res.users'].create({'name': 'QA operador pagos', 'login': 'qa360_pay_operator',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('fleet.fleet_group_user').id,
                self.env.ref('account.group_account_invoice').id])]})
        self.vehicle.driver_id = user.partner_id
        self.account.message_post(body='Creación de cuenta para prueba')
        self.account.message_ids.mapped('tracking_value_ids').mapped('field_desc')
        section = self.service.with_user(user)._seccion_cuentas(self.vehicle.with_user(user), fields.Date.today())
        self.assertEqual(section['key'], 'cuentas')

    def test_vehicle_owners_and_refinancing_history(self):
        history = self.service._historial_crediticio_vehiculo(self.vehicle)
        self.assertEqual((history['duenos'], history['refinanciamientos']), (1, 0))
        second = self.env['adt.comercial.cuentas'].create({'partner_id': self.partner.id,
            'vehiculo_id': self.vehicle.id, 'company_id': self.company.id, 'state': 'en_curso'})
        for name in ['1', '2']:
            self.env['adt.comercial.cuotas'].create({'cuenta_id': second.id,
                'company_id': self.company.id, 'name': name, 'monto': 100,
                'fecha_cronograma': fields.Date.today()})
        history = self.service._historial_crediticio_vehiculo(self.vehicle)
        self.assertEqual((history['duenos'], history['refinanciamientos']), (1, 1))
        other = self.env['res.partner'].create({'name': 'QA segundo titular'})
        third = self.env['adt.comercial.cuentas'].create({'partner_id': other.id,
            'vehiculo_id': self.vehicle.id, 'company_id': self.company.id, 'state': 'pagado'})
        self.env['adt.comercial.cuotas'].create({'cuenta_id': third.id,
            'company_id': self.company.id, 'name': '1', 'monto': 100,
            'fecha_cronograma': fields.Date.today()})
        history = self.service._historial_crediticio_vehiculo(self.vehicle)
        self.assertEqual((history['duenos'], history['refinanciamientos']), (2, 1))
        self.quota.name = 'Cuota R. - 1'
        history = self.service._historial_crediticio_vehiculo(self.vehicle)
        self.assertEqual(history['refinanciamientos'], 1)
