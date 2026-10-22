from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import SavepointCase, tagged


@tagged('post_install', '-at_install')
class TestCandidatoDetalle(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.partner = cls.env['res.partner'].create({'name': 'QA candidato detalle'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'QA candidato modelo',
            'brand_id': cls.env['fleet.vehicle.model.brand'].create({'name': 'QA candidato marca'}).id})
        cls.vehicle = cls.env['fleet.vehicle'].create({'model_id': model.id, 'company_id': cls.env.company.id})
        cls.account = cls.env['adt.comercial.cuentas'].create({'reference_no': 'QA-CANDIDATO',
            'partner_id': cls.partner.id, 'vehiculo_id': cls.vehicle.id, 'company_id': cls.env.company.id,
            'state': 'en_curso', 'fecha_desembolso': cls.today - timedelta(days=60)})
        cls.quota = cls.env['adt.comercial.cuotas'].create({'cuenta_id': cls.account.id, 'name': '1',
            'monto': 100, 'fecha_cronograma': cls.today - timedelta(days=10), 'company_id': cls.env.company.id})
        cls.future = cls.env['adt.comercial.cuotas'].create({'cuenta_id': cls.account.id, 'name': '2',
            'monto': 200, 'fecha_cronograma': cls.today + timedelta(days=30), 'company_id': cls.env.company.id})
        cls.service = cls.env['adt.comercial.clientes.dashboard']

    def test_full_installment_detail_and_future_debt_separated(self):
        data = self.service.detalle_candidato(self.partner.id)
        account = next(a for a in data['creditos']['items'] if a['id'] == self.account.id)
        self.assertEqual(account['saldo'], 300)
        self.assertEqual(account['vencido'], 100)
        self.assertEqual(len(account['cuotas']), 2)
        self.assertEqual(account['cuotas'][0]['atraso_dias'], 10)
        self.assertEqual(account['cuotas'][1]['atraso_dias'], 0)

    def test_paper_installments_use_remaining_balance(self):
        p = self.env['adt.papeleta'].create({'name': 'QA-CANDIDATO-PAP', 'vehicle_id': self.vehicle.id,
            'company_id': self.env.company.id, 'fecha_papeleta': self.today - timedelta(days=5),
            'monto': 120, 'payment_method': 'fraccionado',
            'cuotas_ids': [(0, 0, {'name': '1', 'amount': 60, 'state': 'pagado', 'due_date': self.today}),
                          (0, 0, {'name': '2', 'amount': 60, 'state': 'pendiente', 'due_date': self.today + timedelta(days=20)})]})
        data = self.service.detalle_candidato(self.partner.id)
        row = next(paper for paper in data['papeletas']['items'] if paper['id'] == p.id)
        self.assertEqual(row['saldo'], 60)
        self.assertEqual(row['importe'], 120)
        self.assertEqual(len(row['cuotas']), 2)
        self.assertEqual(data['totales'][self.env.company.currency_id.name]['papeletas'], 60)

    def test_capture_history_contains_reasons_and_evidence(self):
        if 'adt.captura.record' not in self.env:
            self.skipTest('Módulo de capturas opcional')
        capture = self.env['adt.captura.record'].create({'partner_id': self.partner.id, 'cuenta_id': self.account.id,
            'company_id': self.env.company.id, 'comentarios_captura': 'Incumplió el compromiso registrado', 'source_type': 'mora'})
        attachment = self.env['ir.attachment'].create({'name': 'Acta QA.txt', 'datas': 'UVAgZXZpZGVuY2lh',
            'res_model': capture._name, 'res_id': capture.id, 'mimetype': 'text/plain'})
        capture.evidencia_archivos = [(4, attachment.id)]
        second = self.env['adt.captura.record'].create({'partner_id': self.partner.id, 'cuenta_id': self.account.id,
            'company_id': self.env.company.id, 'state': 'cancelado'})
        data = self.service.detalle_candidato(self.partner.id)
        self.assertEqual(len(data['capturas']['items']), 2)
        self.assertEqual(data['capturas']['activas'], 1)
        self.assertEqual(data['capturas']['canceladas'], 1)
        row = next(c for c in data['capturas']['items'] if c['id'] == capture.id)
        self.assertEqual(row['motivo'], 'Incumplió el compromiso registrado')
        self.assertTrue(row['fecha'])
        self.assertEqual(row['evidencias'][0]['nombre'], 'Acta QA.txt')
        self.assertIn('/web/content/', row['evidencias'][0]['url'])
        empty_reason = next(c for c in data['capturas']['items'] if c['id'] == second.id)
        self.assertEqual(empty_reason['motivo'], '')

    def test_papers_from_next_owner_are_not_attributed_to_previous_customer(self):
        other = self.env['res.partner'].create({'name': 'QA otro titular'})
        self.env['adt.comercial.cuentas'].create({'reference_no': 'QA-OTRO-TITULAR',
            'partner_id': other.id, 'vehiculo_id': self.vehicle.id, 'company_id': self.env.company.id,
            'state': 'en_curso', 'fecha_desembolso': self.today - timedelta(days=3)})
        paper = self.env['adt.papeleta'].create({'name': 'QA-PAP-OTRO-TITULAR', 'vehicle_id': self.vehicle.id,
            'company_id': self.env.company.id, 'fecha_papeleta': self.today - timedelta(days=1), 'monto': 80})
        data = self.service.detalle_candidato(self.partner.id)
        self.assertNotIn(paper.id, [p['id'] for p in data['papeletas']['items']])

    def test_company_and_dashboard_access_are_enforced(self):
        other_company = self.env['res.company'].create({'name': 'QA candidato otra empresa'})
        other_partner = self.env['res.partner'].create({'name': 'QA cliente otra empresa'})
        self.env['adt.comercial.cuentas'].create({'partner_id': other_partner.id,
            'reference_no': 'QA-OTRA-EMPRESA', 'company_id': other_company.id, 'state': 'en_curso'})
        with self.assertRaises(AccessError):
            self.service.with_context(allowed_company_ids=self.env.company.ids).detalle_candidato(other_partner.id)
        user = self.env['res.users'].create({'name': 'QA sin dashboard', 'login': 'qa_candidato_no_dashboard',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            self.service.with_user(user).detalle_candidato(self.partner.id)
