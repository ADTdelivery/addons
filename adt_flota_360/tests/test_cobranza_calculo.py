from datetime import date

from odoo.tests import BaseCase, tagged

from odoo.addons.adt_flota_360.models.cobranza_calculo import (
    agrupar_cuotas, cuotas_financiera_pdf, devengado, lunes, refinanciamientos, rentabilidad_cuenta,
    semanal_credito, semanal_recuperada, semanas,
)

HOY = date(2026, 10, 24)  # sábado: la semana en curso empezó el lunes 19


def cuota(id_, fecha, monto, saldo, parent=False, state='pendiente'):
    return {'id': id_, 'parent_id': parent, 'monto': monto, 'saldo': saldo, 'fecha': fecha, 'state': state}


@tagged('post_install', '-at_install')
class TestCobranzaCalculo(BaseCase):

    def test_semanas_lunes_a_domingo(self):
        lista = semanas(HOY, 4)
        self.assertEqual(len(lista), 5)
        self.assertEqual(lista[-1], date(2026, 10, 19))
        self.assertEqual(lista[0], date(2026, 9, 21))
        self.assertEqual(lunes(date(2026, 10, 25)), date(2026, 10, 19))

    def test_pago_parcial_se_agrupa_en_la_cuota_original(self):
        # Cuota de 100 del 13/10: pagó 40 el 15/10 (subcuota de 60 fechada ese día, sigue pendiente).
        grupos = agrupar_cuotas([
            cuota(1, date(2026, 10, 13), 40, 0, state='pagado'),
            cuota(2, date(2026, 10, 15), 60, 60, parent=1),
            cuota(3, date(2026, 10, 20), 100, 100, state='anulada'),
        ])
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]['fecha'], date(2026, 10, 13))
        self.assertEqual(grupos[0]['esperado'], 10000)
        self.assertEqual(grupos[0]['pendiente'], 6000)

    def test_devengado_reparte_la_cuota_mensual_por_dias(self):
        fin = [(date(2026, 10, 1), 3000), (date(2026, 11, 1), 3100)]
        # Octubre completo = cuota de noviembre; una semana de octubre = 7/31 de ella.
        self.assertEqual(devengado(fin, date(2026, 10, 1), date(2026, 11, 1)), 3100)
        self.assertEqual(devengado(fin, date(2026, 10, 1), date(2026, 10, 8)), round(3100 * 7 / 31))
        self.assertEqual(devengado([], date(2026, 10, 1), date(2026, 10, 8)), 0)

    def test_semanal_morosidad_y_lo_que_cubre_adt(self):
        lunes_semanas = semanas(HOY, 2)  # 05/10, 12/10 y la semana en curso 19/10
        grupos = agrupar_cuotas([
            cuota(1, date(2026, 10, 6), 100, 0, state='pagado'),     # pagó a tiempo
            cuota(2, date(2026, 10, 13), 100, 0, state='pagado'),    # pagó tarde (el 20/10)
            cuota(3, date(2026, 10, 20), 100, 100),                  # no paga: semana en curso
            cuota(4, date(2026, 10, 27), 100, 100),                  # aún no vence
        ])
        pagos = {1: [(date(2026, 10, 6), 10000)], 2: [(date(2026, 10, 20), 10000)]}
        # Financiera: 70 por semana (cuota mensual repartida por días, 10/día).
        fin = [(date(2026, 10, 31), 31000), (date(2026, 11, 30), 30000)]
        r = semanal_credito(HOY, lunes_semanas, grupos, pagos, fin, 'semanal')
        self.assertEqual(r['semanas'][0], [10000, 0, 0, 0])
        # Semana del 12/10: no pagó al cierre; ADT cubrió la parte de la financiera (7 días = 70) y ya la recuperó.
        self.assertEqual(r['semanas'][1], [10000, 10000, 7000, 0])
        # Semana en curso: la cuota del 20/10 venció y sigue impaga; ADT la sigue cubriendo.
        self.assertEqual(r['semanas'][2], [10000, 10000, 7000, 7000])
        self.assertEqual((r['vencido'], r['cubriendo'], r['cuotas_vencidas']), (10000, 7000, 1))

    def test_credito_recuperado_solo_cuenta_hasta_el_cierre(self):
        grupos = agrupar_cuotas([cuota(1, date(2026, 10, 6), 100, 100), cuota(2, date(2026, 10, 13), 100, 100)])
        r = semanal_credito(HOY, semanas(HOY, 3), grupos, {}, [], 'semanal', hasta=date(2026, 10, 10))
        self.assertEqual(sum(f[0] for f in r['semanas'].values()), 10000)
        # Sin financiera ADT no adelanta nada.
        self.assertEqual(r['cubriendo'], 0)

    def test_recuperada_cuotas_a_la_financiera_desde_la_recuperacion(self):
        fin = [(date(2026, 9, 15), 5000), (date(2026, 10, 15), 5000), (date(2026, 11, 15), 5000)]
        r = semanal_recuperada(semanas(HOY, 8), fin, date(2026, 10, 1), HOY)
        self.assertEqual(r['pagado_desde'], 5000)
        self.assertEqual(sum(r['semanas'].values()), 5000)

    def test_pdf_estima_cuotas_anteriores(self):
        filas = [{'nro': 3, 'fecha': date(2026, 12, 5), 'total': 450.5}]
        self.assertEqual(cuotas_financiera_pdf(filas, 450), [
            (date(2026, 10, 5), 45000), (date(2026, 11, 5), 45000), (date(2026, 12, 5), 45050)])

    def test_rentabilidad_incluye_inicial_cargos_y_mora(self):
        r = rentabilidad_cuenta({'state': 'en_curso', 'monto_inicial': 500, 'monto_fraccionado': 0}, [
            {'type': 'cuota', 'monto': 100, 'saldo': 0, 'state': 'pagado'},
            {'type': 'cuota', 'monto': 100, 'saldo': 100, 'state': 'pendiente'},
            {'type': 'cuota', 'monto': 100, 'saldo': 100, 'state': 'anulada'},
            {'type': 'cargo', 'monto': 30, 'saldo': 10, 'state': 'a_cuenta'},
        ], 1500)
        self.assertEqual(r['recaudado'], 50000 + 10000 + 2000 + 1500)
        self.assertEqual(r['por_cobrar'], 10000)

    def test_refinanciamientos_por_nombres_repetidos(self):
        self.assertEqual(refinanciamientos([['Cuota 1', 'Cuota 2'], ['Cuota 2', 'Cuota 3']]), 1)
        self.assertEqual(refinanciamientos([['Cuota 1'], ['Cuota R. 1']]), 1)
        self.assertEqual(refinanciamientos([['Cuota 1']]), 0)
