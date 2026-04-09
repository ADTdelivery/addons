# -*- coding: utf-8 -*-
import json
import logging
from collections import defaultdict
from datetime import date, timedelta, datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DashboardCajaController(http.Controller):

    @http.route('/web/dashboard/caja', type='http', auth='user', website=False)
    def dashboard_caja(self, periodo='mes', fecha_inicio=None, fecha_fin=None, **kwargs):
        """Dashboard de ingresos y egresos de caja."""
        today = date.today()

        # ── Calcular rango de fechas según periodo ──────────────────────────
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
        else:  # mes (default)
            periodo = 'mes'
            f_inicio = date(today.year, today.month, 1)
            # último día del mes
            if today.month == 12:
                f_fin = date(today.year, 12, 31)
            else:
                f_fin = date(today.year, today.month + 1, 1) - timedelta(days=1)

        # ── Consulta al modelo ───────────────────────────────────────────────
        domain = [
            ('fecha', '>=', f_inicio.strftime('%Y-%m-%d')),
            ('fecha', '<=', f_fin.strftime('%Y-%m-%d')),
        ]
        records_orm = request.env['adt.comercial.egreso.caja'].search(domain, order='fecha asc')

        registros = []
        for r in records_orm:
            registros.append({
                'fecha': r.fecha.strftime('%d/%m/%Y') if r.fecha else '',
                'fecha_raw': r.fecha,
                'descripcion': r.descripcion or '',
                'monto': r.monto,
                'numero_operacion': r.numero_operacion or '',
            })

        # ── Métricas principales ─────────────────────────────────────────────
        total_ingresos = sum(r['monto'] for r in registros if r['monto'] > 0)
        total_egresos = abs(sum(r['monto'] for r in registros if r['monto'] < 0))
        saldo_neto = total_ingresos - total_egresos
        total_operaciones = len(registros)

        # Promedio diario de ingresos
        dias_con_ingresos_dict = defaultdict(float)
        for r in registros:
            if r['monto'] > 0 and r['fecha_raw']:
                dias_con_ingresos_dict[r['fecha_raw']] += r['monto']

        promedio_diario_ingresos = (
            sum(dias_con_ingresos_dict.values()) / len(dias_con_ingresos_dict)
            if dias_con_ingresos_dict else 0.0
        )

        # Día con mayor ingreso
        dia_mayor_ingreso = ''
        if dias_con_ingresos_dict:
            best_day = max(dias_con_ingresos_dict, key=dias_con_ingresos_dict.get)
            dia_mayor_ingreso = best_day.strftime('%d/%m/%Y')

        # ── Datos para el gráfico (agrupados por día) ───────────────────────
        grafico_dict = defaultdict(lambda: {'ingresos': 0.0, 'egresos': 0.0})
        for r in registros:
            if not r['fecha_raw']:
                continue
            key = r['fecha_raw'].strftime('%d/%m/%Y')
            if r['monto'] > 0:
                grafico_dict[key]['ingresos'] += r['monto']
            else:
                grafico_dict[key]['egresos'] += abs(r['monto'])

        datos_grafico = [
            {'fecha': k, 'ingresos': v['ingresos'], 'egresos': v['egresos']}
            for k, v in sorted(
                grafico_dict.items(),
                key=lambda x: datetime.strptime(x[0], '%d/%m/%Y')
            )
        ]

        # ── Renderizar template ──────────────────────────────────────────────
        values = {
            'registros': registros,
            'total_ingresos': total_ingresos,
            'total_egresos': total_egresos,
            'saldo_neto': saldo_neto,
            'total_operaciones': total_operaciones,
            'promedio_diario_ingresos': promedio_diario_ingresos,
            'dia_mayor_ingreso': dia_mayor_ingreso,
            'datos_grafico': datos_grafico,
            'datos_grafico_json': json.dumps(datos_grafico),
            'periodo_activo': periodo,
            'fecha_inicio_val': f_inicio.strftime('%d/%m/%Y'),
            'fecha_fin_val': f_fin.strftime('%d/%m/%Y'),
            'fecha_inicio_input': f_inicio.strftime('%Y-%m-%d'),
            'fecha_fin_input': f_fin.strftime('%Y-%m-%d'),
        }

        return request.render('adt_comercial.dashboard_caja', values)
