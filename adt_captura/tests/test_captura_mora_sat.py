# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests.common import SavepointCase, tagged


@tagged('post_install', '-at_install')
class TestCapturaMoraOrdenSat(SavepointCase):
    """Una orden de captura vigente del SAT pone la cuenta en la lista de posibles capturas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        modelo = cls.env['fleet.vehicle.model'].create({
            'name': 'QA ordsat modelo',
            'brand_id': cls.env['fleet.vehicle.model.brand'].create({'name': 'QA ordsat marca'}).id})
        cls.partner = cls.env['res.partner'].create({'name': 'QA orden SAT'})
        cls.vehicle = cls.env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': 'QS-1001',
                                                       'company_id': cls.env.company.id})
        cls.cuenta = cls.env['adt.comercial.cuentas'].create({
            'reference_no': 'QA-ORDSAT', 'partner_id': cls.partner.id, 'vehiculo_id': cls.vehicle.id,
            'company_id': cls.env.company.id, 'state': 'en_curso',
            'fecha_desembolso': cls.today - timedelta(days=60)})
        cls.Mora = cls.env['adt.captura.mora']

    def _fila(self):
        self.env['adt.captura.mora'].flush()
        self.env['adt.captura.mora'].invalidate_cache()
        return self.Mora.search([('cuenta_id', '=', self.cuenta.id)])

    def _orden(self, **vals):
        return self.env['adt.captura.sat'].create(dict({
            'name': '0077001', 'placa': 'QS1001', 'vehicle_id': self.vehicle.id, 'concepto': 'Inf. RNT',
            'monto': 450.0, 'primera_vez_visto': fields.Datetime.now()}, **vals))

    def test_sin_deuda_no_es_candidata(self):
        self.assertFalse(self._fila())

    def test_orden_vigente_es_candidata(self):
        self._orden()
        fila = self._fila()
        self.assertEqual(len(fila), 1)
        self.assertEqual(fila.source_type, 'captura_sat')
        self.assertTrue(fila.orden_captura_sat)
        self.assertEqual(fila.ordenes_captura_sat, 1)
        self.assertEqual(fila.monto_captura_sat, 450.0)

    def test_orden_con_cuotas_vencidas_mantiene_origen_y_marca(self):
        self.env['adt.comercial.cuotas'].create({
            'cuenta_id': self.cuenta.id, 'name': '1', 'monto': 100, 'company_id': self.env.company.id,
            'fecha_cronograma': self.today - timedelta(days=10)})
        self._orden()
        fila = self._fila()
        self.assertEqual(fila.source_type, 'mora')
        self.assertTrue(fila.orden_captura_sat)

    def test_orden_levantada_o_resuelta_no_cuenta(self):
        orden = self._orden(vigente=False)
        self.assertFalse(self._fila())
        orden.write({'vigente': True, 'gestion': 'resuelta'})
        self.assertFalse(self._fila())

    def test_cuenta_no_vigente_no_cuenta(self):
        self.cuenta.state = 'cancelado'
        self._orden()
        self.assertFalse(self._fila())
