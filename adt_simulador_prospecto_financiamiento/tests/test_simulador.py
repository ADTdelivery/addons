from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from ..models.calculo import calcular_cuotas, generar_cronograma


@tagged('post_install', '-at_install')
class TestSimuladorCuotas(TransactionCase):

    def test_paridad_con_excel(self):
        r = calcular_cuotas(25000, 2000, 0.2682, 26)
        self.assertAlmostEqual(r['capital'], 23000.0, places=6)
        self.assertAlmostEqual(r['interes_mensual'], 0.0199971988, places=10)
        self.assertAlmostEqual(r['cuota_mensual'], 1143.0434106969, places=8)
        self.assertAlmostEqual(r['cuota_diaria'], 38.1014470232, places=8)
        self.assertAlmostEqual(r['cuota_semanal'], 266.7101291626, places=8)
        self.assertAlmostEqual(r['total_credito'], r['cuota_mensual'] * 26, places=8)
        self.assertAlmostEqual(r['total_intereses'], r['total_credito'] - 23000, places=8)

    def test_simulacion_persistida(self):
        vehiculo = self.env['financing.vehicle'].create(
            {'name': 'TEST', 'importe_financiar': 25000, 'tea': 0.2682})
        sim = self.env['financing.simulation'].create(
            {'vehicle_id': vehiculo.id, 'cuota_inicial': 2000, 'plazo_meses': 26})
        self.assertEqual(sim.cuota_mensual, 1143.04)
        self.assertEqual(sim.cuota_semanal, 266.71)
        self.assertEqual(sim.cuota_diaria, 38.10)
        # Cambiar la TEA no altera simulaciones ya registradas.
        vehiculo.tea = 0.30
        sim.invalidate_cache()
        self.assertEqual(sim.cuota_mensual, 1143.04)

    def test_validaciones(self):
        with self.assertRaises(ValidationError):
            calcular_cuotas(25000, 25000, 0.2682, 26)
        with self.assertRaises(ValidationError):
            calcular_cuotas(25000, 2000, 0.2682, 0)
        with self.assertRaises(ValidationError):
            calcular_cuotas(25000, 2000, 0.2682, 12.5)

    def test_cronograma_suma_total_del_credito(self):
        r = calcular_cuotas(25000, 2000, 0.2682, 26)
        esperado = {'mensual': 26, 'semanal': 112, 'diaria': 780}
        for frecuencia, cantidad in esperado.items():
            filas = generar_cronograma(
                date(2026, 1, 31), frecuencia, 26, r['cuota_mensual'], r['total_credito'])
            self.assertEqual(len(filas), cantidad, frecuencia)
            self.assertAlmostEqual(sum(f['cuota'] for f in filas), r['total_credito'], places=2)
            self.assertEqual(filas[-1]['saldo'], 0.0)
        mensual = generar_cronograma(
            date(2026, 1, 31), 'mensual', 26, r['cuota_mensual'], r['total_credito'])
        self.assertEqual(mensual[0]['fecha'], date(2026, 2, 28))
        self.assertEqual(mensual[0]['cuota'], 1143.04)

    def test_simulacion_con_cliente_y_cronograma(self):
        vehiculo = self.env['financing.vehicle'].create(
            {'name': 'TEST2', 'importe_financiar': 25000, 'tea': 0.2682})
        cliente = self.env['res.partner'].create({'name': 'Cliente Prueba'})
        sim = self.env['financing.simulation'].create({
            'vehicle_id': vehiculo.id, 'cuota_inicial': 2000, 'plazo_meses': 26,
            'partner_id': cliente.id, 'frecuencia': 'semanal',
            'fecha_inicio': '2026-01-05'})
        self.assertEqual(sim.partner_id, cliente)
        self.assertEqual(sim.cantidad_cuotas, 112)
        self.assertAlmostEqual(sum(sim.linea_ids.mapped('cuota')), 29719.13, places=2)
        # Sin fecha de inicio no hay cronograma.
        sin_fecha = self.env['financing.simulation'].create(
            {'vehicle_id': vehiculo.id, 'cuota_inicial': 2000, 'plazo_meses': 26})
        self.assertEqual(sin_fecha.cantidad_cuotas, 0)

    def test_reporte_pdf_se_renderiza(self):
        vehiculo = self.env['financing.vehicle'].create(
            {'name': 'TEST3', 'importe_financiar': 25000, 'tea': 0.2682})
        sim = self.env['financing.simulation'].create({
            'vehicle_id': vehiculo.id, 'cuota_inicial': 2000, 'plazo_meses': 26,
            'fecha_inicio': '2026-01-05'})
        reporte = self.env.ref('adt_simulador_prospecto_financiamiento.action_report_simulacion')
        html, _tipo = reporte._render_qweb_html(sim.ids)
        self.assertIn(b'Simulaci', html)
        self.assertIn(sim.name.encode(), html)
