import base64
from datetime import date
from unittest.mock import patch

from odoo.tests.common import SavepointCase, tagged

PARSER = 'odoo.addons.adt_comercial.models.financiera_carga_pdf.parse_pdf'


def _plan(dni):
    cuota = {'nro_cuota': 1, 'fecha_vencimiento': '2026-11-10', 'capital': 900.0, 'interes': 80.0,
             'seguro_desgravamen': 2.0, 'comision_operativa': 0.0, 'interes_vencido': 0.0,
             'interes_moratorio': 0.0, 'interes_compensatorio': 0.0, 'aporte': 0.0, 'otros': 0.0,
             'total': 982.0, 'estado': 'Pendiente'}
    return '', {
        'cabecera': {'nro_solicitud': '1', 'nro_expediente': 'E-1', 'agencia': 'LIMA', 'socio': 'QA SOCIO',
                     'codigo_socio': '99', 'monto_credito': 900.0, 'fecha_desembolso': '2026-10-10',
                     'plazo_dias': 31, 'frecuencia_cuota': 'MENSUAL', 'tasa_interes_anual': 30.0,
                     'producto': 'MOTO', 'tipo_credito': 'CONSUMO', 'tipo_cobro': 'CAJA', 'analista': 'QA'},
        'pie': {'dni': dni},
        'cuotas': [cuota],
        'totales': {'total': 982.0},
        'resumen': {'cuotas_pendientes': 1, 'primera_cuota': 1, 'ultima_cuota': 1, 'capital_pendiente': 900.0,
                    'capital_amortizado': 0.0, 'monto_cuota_referencial': 982.0,
                    'tasa_desgravamen_mensual': 0.22, 'proximo_vencimiento': '2026-11-10'},
        'validacion': {'estado': 'valido', 'confianza': 100.0, 'reglas': [{'regla': 'x', 'ok': True, 'detalle': ''}]},
    }


@tagged('post_install', '-at_install')
class TestFinancieraCargaPdf(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'QA carga marca'})
        cls.modelo = cls.env['fleet.vehicle.model'].create({'name': 'QA carga modelo', 'brand_id': brand.id})
        cls.Cuenta = cls.env['adt.comercial.cuentas']

    def _cliente(self, dni, state, otro_activo=False):
        partner = self.env['res.partner'].create({'name': 'QA %s' % dni, 'vat': dni})
        moto = self.env['fleet.vehicle'].create({'model_id': self.modelo.id, 'company_id': self.env.company.id})
        self.Cuenta.create({'reference_no': 'QA-%s' % dni, 'partner_id': partner.id, 'vehiculo_id': moto.id,
                            'company_id': self.env.company.id, 'state': state,
                            'fecha_desembolso': date(2026, 1, 1)})
        if otro_activo:
            otro = self.env['res.partner'].create({'name': 'QA otro %s' % dni})
            self.Cuenta.create({'reference_no': 'QA-OTRO-%s' % dni, 'partner_id': otro.id, 'vehiculo_id': moto.id,
                                'company_id': self.env.company.id, 'state': 'en_curso',
                                'fecha_desembolso': date(2026, 6, 1)})
        return partner, moto

    def _lote(self, *nombres):
        atts = self.env['ir.attachment'].create([
            {'name': n, 'datas': base64.b64encode(n.encode()), 'mimetype': 'application/pdf'} for n in nombres])
        return self.env['adt.financiera.carga.pdf'].create({'attachment_ids': [(6, 0, atts.ids)]})

    def _procesar(self, lote, dni_por_archivo):
        def fake(pdf):
            return _plan(dni_por_archivo[pdf.decode()])
        with patch(PARSER, side_effect=fake):
            lote.action_procesar()
            lote._procesar_lineas(lote.linea_ids.filtered(lambda l: l.state == 'pendiente'), commit=False)
            lote._cerrar_terminados()
        return {l.nombre_archivo: l for l in lote.linea_ids}

    def test_identifica_deuda_y_carga_plan_en_la_moto(self):
        _p1, moto1 = self._cliente('40000001', 'en_curso')
        _p2, moto2 = self._cliente('40000002', 'pagado')
        _p3, moto3 = self._cliente('40000003', 'cancelado')
        lote = self._lote('a.pdf', 'b.pdf', 'c.pdf', 'd.pdf')
        res = self._procesar(lote, {'a.pdf': '40000001', 'b.pdf': '40000002',
                                    'c.pdf': '40000003', 'd.pdf': '49999999'})
        self.assertEqual(res['a.pdf'].situacion_deuda, 'activa')
        self.assertEqual(res['b.pdf'].situacion_deuda, 'cancelada')
        self.assertEqual(res['c.pdf'].situacion_deuda, 'anulada')
        self.assertEqual(res['d.pdf'].state, 'sin_cliente')
        for nombre, moto in (('a.pdf', moto1), ('b.pdf', moto2), ('c.pdf', moto3)):
            self.assertEqual(res[nombre].state, 'cargado')
            self.assertEqual(moto.cf_pdf_nombre, nombre)
            self.assertEqual(moto.cf_monto_credito, 900.0)
            self.assertEqual(len(moto.cf_cuota_ids), 1)
        self.assertEqual(lote.state, 'terminado')
        self.assertEqual(lote.total_cargado, 3)

    def test_moto_anulada_ahora_de_otro_cliente_no_se_carga(self):
        _p, moto = self._cliente('40000010', 'cancelado', otro_activo=True)
        res = self._procesar(self._lote('x.pdf'), {'x.pdf': '40000010'})
        self.assertEqual(res['x.pdf'].state, 'revisar')
        self.assertFalse(moto.cf_cuota_ids)

    def test_error_de_un_pdf_no_detiene_el_lote(self):
        self._cliente('40000020', 'en_curso')
        lote = self._lote('malo.pdf', 'bueno.pdf')

        def fake(pdf):
            if pdf == b'malo.pdf':
                raise ValueError('PDF corrupto')
            return _plan('40000020')
        with patch(PARSER, side_effect=fake):
            lote.action_procesar()
            lote._procesar_lineas(lote.linea_ids, commit=False)
        res = {l.nombre_archivo: l for l in lote.linea_ids}
        self.assertEqual(res['malo.pdf'].state, 'error')
        self.assertEqual(res['bueno.pdf'].state, 'cargado')

    def test_200_pdfs(self):
        dnis = {}
        for i in range(200):
            dni = '41%06d' % i
            self._cliente(dni, 'en_curso')
            dnis['p%03d.pdf' % i] = dni
        lote = self._lote(*dnis)
        res = self._procesar(lote, dnis)
        self.assertEqual(len(res), 200)
        self.assertEqual(lote.total_cargado, 200)

    def test_cargar_en_otro_cliente_reemplaza(self):
        _p1, moto1 = self._cliente('40000030', 'en_curso')
        p2, moto2 = self._cliente('40000031', 'en_curso')
        lote = self._lote('z.pdf')
        linea = self._procesar(lote, {'z.pdf': '40000030'})['z.pdf']
        self.assertEqual(linea.vehiculo_id, moto1)

        linea.partner_manual_id = p2
        linea._onchange_partner_manual_id()
        self.assertEqual(linea.cuenta_manual_id.vehiculo_id, moto2)
        with patch(PARSER, return_value=_plan('40000030')):
            linea.action_cargar_otro_cliente()
        self.assertEqual(linea.state, 'cargado')
        self.assertEqual(linea.vehiculo_id, moto2)
        self.assertEqual(linea.partner_id, p2)
        self.assertEqual(moto2.cf_pdf_nombre, 'z.pdf')
        self.assertEqual(len(moto2.cf_cuota_ids), 1)
        # La moto del cliente equivocado se queda sin el plan.
        self.assertFalse(moto1.cf_cuota_ids)
        self.assertFalse(moto1.cf_pdf_nombre)
        self.assertFalse(linea.partner_manual_id)

    def test_revisar_se_resuelve_a_mano(self):
        _p, moto = self._cliente('40000040', 'cancelado', otro_activo=True)
        linea = self._procesar(self._lote('r.pdf'), {'r.pdf': '40000040'})['r.pdf']
        self.assertEqual(linea.state, 'revisar')
        linea.write({'partner_manual_id': linea.partner_id.id, 'cuenta_manual_id': linea.cuenta_id.id})
        with patch(PARSER, return_value=_plan('40000040')):
            linea.action_cargar_otro_cliente()
        self.assertEqual(linea.state, 'cargado')
        self.assertEqual(moto.cf_pdf_nombre, 'r.pdf')
