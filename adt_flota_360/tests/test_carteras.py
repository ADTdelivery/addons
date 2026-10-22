from unittest.mock import patch
from datetime import timedelta
from odoo import fields
from odoo.tests.common import SavepointCase, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestCarteras(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.worker = cls.env['res.users'].create({
            'name': 'Gestor cartera QA', 'login': 'cartera_qa_worker',
            'company_id': cls.company.id, 'company_ids': [(6, 0, [cls.company.id])],
            'groups_id': [(6, 0, [cls.env.ref('fleet.fleet_group_user').id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente cartera QA'})
        cls.account = cls.env['adt.comercial.cuentas'].create({
            'partner_id': cls.partner.id, 'company_id': cls.company.id,
            'reference_no': 'QA-CARTERA', 'state': 'en_curso'})
        cls.quota = cls.env['adt.comercial.cuotas'].create({
            'cuenta_id': cls.account.id, 'monto': 100, 'company_id': cls.company.id,
            'fecha_cronograma': fields.Date.today() - timedelta(days=3)})

    def assign(self):
        return self.env['adt.flota360.cartera'].browse(self.env['adt.flota360.cartera'].asignar(
            'QA', self.worker.id, fields.Date.today(), account_ids=self.account.ids))

    def test_assignment_target_and_duplicate(self):
        portfolio = self.assign()
        self.assertEqual(sum(portfolio.linea_ids.cuota_ids.mapped('objetivo')), 100)
        with self.assertRaises(ValidationError):
            self.assign()
        portfolio.linea_ids.cerrar()
        self.assertTrue(self.assign())

    def test_worker_permissions_and_promise(self):
        portfolio = self.assign()
        worker_service = self.env['adt.flota360.cartera'].with_user(self.worker)
        with self.assertRaises(AccessError):
            worker_service.asignar('No', self.worker.id, fields.Date.today())
        line = portfolio.linea_ids.with_user(self.worker)
        line.registrar_gestion('contactado', nota='Se llamó al cliente')
        self.assertEqual(line.gestion, 'contactado')
        with self.assertRaises(ValidationError):
            line.registrar_gestion('promesa')
        with self.assertRaises(AccessError):
            line.write({'cuenta_id': self.account.id})

    def test_collection_counts_split_payments_and_freezes_on_close(self):
        portfolio = self.assign()
        line = portfolio.linea_ids
        self.assertEqual(line._cobrado(), 0)
        # Use real payment records with mocked posted state to avoid creating journal entries.
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id), ('type', 'in', ['bank', 'cash'])], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({'name': 'QA bank', 'code': 'QABK', 'type': 'bank'})
        payment = self.env['account.payment'].create({
            'partner_id': self.partner.id, 'payment_type': 'inbound', 'partner_type': 'customer',
            'amount': 40, 'journal_id': journal.id, 'cuota_id': self.quota.id})
        self.assertEqual(line._cobrado(), 0)  # draft payment does not count
        with patch.object(type(payment), 'state', new=property(lambda p: 'posted')):
            self.assertEqual(line._cobrado(), 40)
            child = self.env['adt.comercial.cuotas'].create({
                'cuenta_id': self.account.id, 'parent_id': self.quota.id, 'monto': 60,
                'company_id': self.company.id, 'fecha_cronograma': fields.Date.today()})
            payment.copy({'amount': 60, 'cuota_id': child.id})
            self.assertEqual(line._cobrado(), 100)
            result = self.env['adt.flota360.cartera'].with_user(self.worker).tablero()
            self.assertEqual(result['rows'][0]['cobrado'], 100)
            line.cerrar()
            self.assertEqual(line.cobrado_cierre, 100)

    def test_other_worker_cannot_read_or_edit(self):
        portfolio = self.assign()
        other = self.worker.copy({'name': 'Otro gestor QA', 'login': 'cartera_qa_other'})
        self.assertFalse(self.env['adt.flota360.cartera'].with_user(other).tablero()['rows'])
        with self.assertRaises(AccessError):
            portfolio.linea_ids.with_user(other).registrar_gestion('contactado')

    def test_manager_without_accounting_can_assign(self):
        manager = self.worker.copy({'name': 'Gerencia sin contabilidad QA', 'login': 'cartera_qa_manager',
            'groups_id': [(6, 0, [self.env.ref('fleet.fleet_group_user').id,
                self.env.ref('adt_comercial.group_access_adt_comercial_gerencia').id])]})
        pid = self.env['adt.flota360.cartera'].with_user(manager).asignar(
            'QA gerencia', self.worker.id, fields.Date.today(), account_ids=self.account.ids)
        self.assertTrue(pid)

    def test_collector_profile_scopes_accounts_quotas_and_metrics(self):
        collector = self.env['res.users'].create({
            'name': 'Cobrador exclusivo QA', 'login': 'cartera_qa_collector',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('adt_flota_360.group_cobrador').id])]})
        pid = self.env['adt.flota360.cartera'].asignar(
            'Mi cartera QA', collector.id, fields.Date.today(), account_ids=self.account.ids)
        other = self.env['adt.comercial.cuentas'].create({
            'partner_id': self.partner.id, 'reference_no': 'OTRA-CUENTA-QA',
            'company_id': self.company.id, 'state': 'en_curso'})
        other_quota = self.quota.copy({'cuenta_id': other.id})
        data = self.env['adt.flota360.cartera'].with_user(collector).tablero()
        self.assertFalse(data['manager'])
        self.assertEqual([r['cuenta_id'] for r in data['rows']], self.account.ids)
        self.assertEqual([u['id'] for u in data['users']], collector.ids)
        self.assertEqual(data['rows'][0]['objetivo'], 100)
        self.assertFalse(other.with_user(collector).search([('id', '=', other.id)]))
        self.assertFalse(other_quota.with_user(collector).search([('id', '=', other_quota.id)]))
        with self.assertRaises(AccessError):
            other.with_user(collector).read(['reference_no'])
        with self.assertRaises(AccessError):
            other_quota.with_user(collector).read(['monto'])
        line = self.env['adt.flota360.cartera'].browse(pid).linea_ids.with_user(collector)
        line.registrar_gestion('contactado', nota='Gestión de mi cliente')
        self.assertEqual(line.gestion, 'contactado')

    def test_assignment_preview_filters_eligible_accounts_and_sums_goal(self):
        service = self.env['adt.flota360.cartera']
        future_account = self.env['adt.comercial.cuentas'].create({
            'partner_id': self.partner.id, 'company_id': self.company.id,
            'reference_no': 'QA-FUTURE', 'state': 'en_curso'})
        self.env['adt.comercial.cuotas'].create({'cuenta_id': future_account.id,
            'company_id': self.company.id, 'fecha_cronograma': fields.Date.today() + timedelta(days=5), 'monto': 250})
        domain = [('id', 'in', self.account.ids + future_account.ids)]
        due = service.candidatos(domain=domain, vencidas=True)
        self.assertEqual([r['id'] for r in due['rows']], self.account.ids)
        self.assertEqual(due['rows'][0]['objetivo'], 100)
        review = service.revisar_asignacion(domain=domain, vencidas=False)
        self.assertEqual(review['cuentas'], 2)
        self.assertEqual(review['clientes'], 1)
        self.assertEqual(review['importes'][self.company.currency_id.name], 350)
        self.assign()
        self.assertFalse(service.candidatos(domain=[('id', '=', self.account.id)])['rows'])
        with self.assertRaises(ValidationError):
            service.revisar_asignacion(account_ids=self.account.ids)

    def test_worker_cannot_preview_assignment(self):
        with self.assertRaises(AccessError):
            self.env['adt.flota360.cartera'].with_user(self.worker).revisar_asignacion()
