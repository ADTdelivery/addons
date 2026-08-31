# -*- coding: utf-8 -*-
import json
import logging
from datetime import date, timedelta, datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TOP_PRODUCTOS = 5
DIAS_SERIE = 14

COLOR_VERDE = '#22c55e'
COLOR_AMARILLO = '#f59e0b'
COLOR_ROJO = '#ef4444'
CATEGORICAL_PALETTE = ['#3987e5', '#008300', '#d55181', '#c98500', '#199e70']


class DashboardCreditoController(http.Controller):

    @http.route('/web/dashboard/credito', type='http', auth='user', website=False)
    def dashboard_credito(self, periodo='mes', fecha_inicio=None, fecha_fin=None, **kwargs):
        """Reporte de indicadores clave de la cartera de crédito: deuda, mora y
        recaudo, con el mismo patrón de dashboard embebido (controller + template QWeb
        con JS/CSS propios) que ya usa adt_comercial."""
        today = date.today()

        if periodo == 'dia':
            f_inicio = today
            f_fin = today
        elif periodo == 'semana':
            f_inicio = today - timedelta(days=today.weekday())
            f_fin = f_inicio + timedelta(days=6)
        elif periodo == 'rango':
            try:
                f_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date() if fecha_inicio else date(today.year, today.month, 1)
                f_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date() if fecha_fin else today
            except ValueError:
                f_inicio = date(today.year, today.month, 1)
                f_fin = today
        else:
            periodo = 'mes'
            f_inicio = date(today.year, today.month, 1)
            if today.month == 12:
                f_fin = date(today.year, 12, 31)
            else:
                f_fin = date(today.year, today.month + 1, 1) - timedelta(days=1)

        Contrato = request.env['credito.contrato'].sudo()
        Pago = request.env['credito.pago'].sudo()
        currency_symbol = request.env.company.currency_id.symbol or ''

        contratos_vivos = Contrato.search([('estado', 'in', ('activo', 'en_mora'))])
        n_contratos = len(contratos_vivos)
        cartera_financiada = sum(contratos_vivos.mapped('monto_financiado'))
        saldo_pendiente = sum(contratos_vivos.mapped('saldo_pendiente'))
        mora_total = sum(contratos_vivos.mapped('mora_total'))
        cuotas_vencidas = sum(contratos_vivos.mapped('cuotas_vencidas'))

        n_verde = len(contratos_vivos.filtered(lambda c: c.semaforo == 'verde'))
        n_amarillo = len(contratos_vivos.filtered(lambda c: c.semaforo == 'amarillo'))
        n_rojo = len(contratos_vivos.filtered(lambda c: c.semaforo == 'rojo'))
        pct_en_mora = (n_rojo / n_contratos * 100.0) if n_contratos else 0.0

        pagos_periodo = Pago.search([('fecha_pago', '>=', f_inicio), ('fecha_pago', '<=', f_fin)])
        recaudado_cuota = sum(pagos_periodo.filtered(lambda p: p.tipo == 'cuota').mapped('monto'))
        recaudado_mora = sum(pagos_periodo.filtered(lambda p: p.tipo == 'mora').mapped('monto'))
        recaudado_total = recaudado_cuota + recaudado_mora
        n_pagos = len(pagos_periodo)
        ticket_promedio = (recaudado_total / n_pagos) if n_pagos else 0.0

        # ── Serie de recaudo por día (últimos DIAS_SERIE días, no depende del período) ──
        desde_serie = today - timedelta(days=DIAS_SERIE - 1)
        pagos_serie = Pago.search([('fecha_pago', '>=', desde_serie), ('fecha_pago', '<=', today)])
        recaudo_por_dia = {}
        for p in pagos_serie:
            recaudo_por_dia[p.fecha_pago] = recaudo_por_dia.get(p.fecha_pago, 0.0) + p.monto
        serie_diaria = []
        for i in range(DIAS_SERIE):
            d = desde_serie + timedelta(days=i)
            serie_diaria.append({'fecha': d.strftime('%d/%m'), 'monto': round(recaudo_por_dia.get(d, 0.0), 2)})

        # ── Top productos por cartera financiada (contratos vivos) ──────────────────
        cartera_por_producto = {}
        for c in contratos_vivos:
            key = c.product_id.display_name or 'Sin producto'
            cartera_por_producto[key] = cartera_por_producto.get(key, 0.0) + c.monto_financiado
        top_productos = sorted(cartera_por_producto.items(), key=lambda kv: kv[1], reverse=True)[:TOP_PRODUCTOS]

        # ── Ganancia por producto vs. costo de todos los préstamos ──────────────────
        # "Todos los préstamos" = todo contrato que alguna vez se confirmó (no cuenta
        # un borrador que nunca se activó, ni uno cancelado antes de desembolsar) —
        # incluye pagados y refinanciados, porque la venta y su costo ya ocurrieron
        # aunque el crédito en sí haya cambiado de forma después.
        # Costo = costo estándar del producto (product.standard_price) × cantidad.
        # Ganancia = venta (monto_total) − costo. No es ganancia "cobrada" todavía
        # (eso ya lo cubre "Recaudado del período" arriba): es margen sobre lo vendido.
        contratos_prestamos = Contrato.search([('estado', 'not in', ('borrador', 'cancelado'))])
        n_prestamos = len(contratos_prestamos)
        venta_total = sum(contratos_prestamos.mapped('monto_total'))
        costo_por_producto = {}
        ganancia_por_producto = {}
        costo_total = 0.0
        for c in contratos_prestamos:
            costo_linea = c.cantidad * c.product_id.standard_price
            ganancia_linea = c.monto_total - costo_linea
            costo_total += costo_linea
            key = c.product_id.display_name or 'Sin producto'
            costo_por_producto[key] = costo_por_producto.get(key, 0.0) + costo_linea
            ganancia_por_producto[key] = ganancia_por_producto.get(key, 0.0) + ganancia_linea
        ganancia_total = venta_total - costo_total
        margen_pct = (ganancia_total / venta_total * 100.0) if venta_total else 0.0
        top_ganancia = sorted(ganancia_por_producto.items(), key=lambda kv: kv[1], reverse=True)[:TOP_PRODUCTOS]

        values = {
            'periodo_activo': periodo,
            'fecha_inicio_input': f_inicio.strftime('%Y-%m-%d'),
            'fecha_fin_input': f_fin.strftime('%Y-%m-%d'),
            'moneda': currency_symbol,
            'n_contratos': n_contratos,
            'cartera_financiada': round(cartera_financiada, 2),
            'saldo_pendiente': round(saldo_pendiente, 2),
            'mora_total': round(mora_total, 2),
            'cuotas_vencidas': cuotas_vencidas,
            'pct_en_mora': round(pct_en_mora, 1),
            'recaudado_total': round(recaudado_total, 2),
            'recaudado_cuota': round(recaudado_cuota, 2),
            'recaudado_mora': round(recaudado_mora, 2),
            'ticket_promedio': round(ticket_promedio, 2),
            'n_verde': n_verde,
            'n_amarillo': n_amarillo,
            'n_rojo': n_rojo,
            'serie_diaria_json': json.dumps(serie_diaria),
            'top_productos_json': json.dumps([
                {'nombre': nombre, 'monto': round(monto, 2)} for nombre, monto in top_productos
            ]),
            'palette_json': json.dumps(CATEGORICAL_PALETTE),
            'n_prestamos': n_prestamos,
            'venta_total': round(venta_total, 2),
            'costo_total': round(costo_total, 2),
            'ganancia_total': round(ganancia_total, 2),
            'margen_pct': round(margen_pct, 1),
            'top_ganancia_json': json.dumps([
                {'nombre': nombre, 'monto': round(monto, 2)} for nombre, monto in top_ganancia
            ]),
        }
        return request.render('adt_credito.dashboard_credito', values)
