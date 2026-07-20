# -*- coding: utf-8 -*-
import json
import logging
from collections import defaultdict
from datetime import date, timedelta, datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

TOP_COBRADORES = 8

# Paleta categórica validada (contraste + CVD) sobre superficie oscura #0f172a.
CATEGORICAL_PALETTE = [
    '#3987e5', '#008300', '#d55181', '#c98500',
    '#199e70', '#d95926', '#9085e9', '#e66767',
]
COLOR_OTROS = '#64748b'
COLOR_PUNTUAL = '#0ca30c'
COLOR_MORA = '#fab219'


class DashboardCobranzasController(http.Controller):

    @http.route('/web/dashboard/cobranzas', type='http', auth='user', website=False)
    def dashboard_cobranzas(self, periodo='mes', fecha_inicio=None, fecha_fin=None, cobradores=None, **kwargs):
        """Reporte estadístico de pagos de cronogramas: recaudo por día/semana/mes/rango,
        con desempeño por cobrador."""
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
            if today.month == 12:
                f_fin = date(today.year, 12, 31)
            else:
                f_fin = date(today.year, today.month + 1, 1) - timedelta(days=1)

        # ── Cobradores seleccionados en el filtro ────────────────────────────
        cobrador_ids_sel = []
        if cobradores:
            for token in cobradores.split(','):
                token = token.strip()
                if token.isdigit():
                    cobrador_ids_sel.append(int(token))

        # ── Dominio y consulta al modelo de reporte ──────────────────────────
        Reporte = request.env['adt.reporte.cobranza.pagos.realizados'].sudo()
        domain = [
            ('fecha', '>=', f_inicio.strftime('%Y-%m-%d')),
            ('fecha', '<=', f_fin.strftime('%Y-%m-%d')),
            ('move_state', '=', 'posted'),
        ]
        if cobrador_ids_sel:
            domain.append(('cobrador_id', 'in', cobrador_ids_sel))

        records_orm = Reporte.search(domain, order='fecha asc, id asc')

        registros = []
        for r in records_orm:
            mora = r.mora or 0.0
            mora_cobrada = mora if r.mora_state == 'paid' else 0.0
            total = (r.monto or 0.0) + mora_cobrada
            registros.append({
                'id': r.id,
                'fecha_raw': r.fecha,
                'fecha': r.fecha.strftime('%d/%m/%Y') if r.fecha else '',
                'hora': r.fecha_registro.strftime('%H:%M') if r.fecha_registro else '',
                'monto': r.monto or 0.0,
                'mora': mora,
                'mora_cobrada': mora_cobrada,
                'total': total,
                'cobrador_id': r.cobrador_id.id or 0,
                'cobrador': r.cobrador_id.name or 'Sin asignar',
                'partner_id': r.partner_id.id,
                'cliente': r.partner_id.name or 'N/D',
                'cuenta': r.cuenta_id.reference_no or '',
                'cuota': r.cuota_id.name or '',
                'vehiculo': r.vehicle_id.display_name or '',
                'forma_pago': r.journal_id.name or 'N/D',
                'numero_operacion': r.numero_operacion or '',
                'puntual': mora <= 0,
            })

        # ── KPIs principales ─────────────────────────────────────────────────
        total_recaudado = sum(r['total'] for r in registros)
        total_cuotas = sum(r['monto'] for r in registros)
        mora_recuperada = sum(r['mora_cobrada'] for r in registros)
        total_pagos = len(registros)
        ticket_promedio = total_recaudado / total_pagos if total_pagos else 0.0

        cobradores_activos = len({r['cobrador_id'] for r in registros if r['cobrador_id']})
        clientes_atendidos = len({r['partner_id'] for r in registros if r['partner_id']})

        dias_periodo = max((f_fin - f_inicio).days + 1, 1)
        promedio_pagos_dia = total_pagos / dias_periodo
        promedio_recaudo_dia = total_recaudado / dias_periodo

        pagos_puntuales = sum(1 for r in registros if r['puntual'])
        pagos_con_mora = total_pagos - pagos_puntuales
        pct_puntualidad = (pagos_puntuales / total_pagos * 100) if total_pagos else 0.0

        pago_maximo = max((r['total'] for r in registros), default=0.0)

        # ── Ranking de cobradores ─────────────────────────────────────────────
        cobrador_totales = defaultdict(lambda: {'monto': 0.0, 'pagos': 0, 'nombre': '', 'clientes': set()})
        for r in registros:
            key = r['cobrador_id']
            entry = cobrador_totales[key]
            entry['monto'] += r['total']
            entry['pagos'] += 1
            entry['nombre'] = r['cobrador']
            if r['partner_id']:
                entry['clientes'].add(r['partner_id'])

        ranking_cobradores = sorted(
            (
                {
                    'nombre': v['nombre'],
                    'monto': v['monto'],
                    'pagos': v['pagos'],
                    'clientes': len(v['clientes']),
                    'promedio': v['monto'] / v['pagos'] if v['pagos'] else 0.0,
                    'pct': (v['monto'] / total_recaudado * 100) if total_recaudado else 0.0,
                }
                for v in cobrador_totales.values()
            ),
            key=lambda x: x['monto'],
            reverse=True,
        )

        mejor_cobrador = ranking_cobradores[0] if ranking_cobradores else None

        ranking_chart = ranking_cobradores[:TOP_COBRADORES]
        resto = ranking_cobradores[TOP_COBRADORES:]
        if resto:
            ranking_chart.append({
                'nombre': 'Otros (%d)' % len(resto),
                'monto': sum(x['monto'] for x in resto),
                'pagos': sum(x['pagos'] for x in resto),
                'clientes': sum(x['clientes'] for x in resto),
                'promedio': 0.0,
                'pct': sum(x['pct'] for x in resto),
            })
        for idx, entry in enumerate(ranking_chart):
            entry['color'] = CATEGORICAL_PALETTE[idx] if idx < len(CATEGORICAL_PALETTE) else COLOR_OTROS
        monto_max_cobrador = max((x['monto'] for x in ranking_chart), default=0.0)
        for entry in ranking_chart:
            entry['barra_pct'] = (entry['monto'] / monto_max_cobrador * 100) if monto_max_cobrador else 0.0

        # ── Recaudo diario (para el gráfico principal) ──────────────────────
        grafico_dict = defaultdict(lambda: {'monto': 0.0, 'pagos': 0})
        for r in registros:
            if not r['fecha_raw']:
                continue
            grafico_dict[r['fecha']]['monto'] += r['total']
            grafico_dict[r['fecha']]['pagos'] += 1

        datos_grafico = [
            {'fecha': k, 'monto': v['monto'], 'pagos': v['pagos']}
            for k, v in sorted(grafico_dict.items(), key=lambda x: datetime.strptime(x[0], '%d/%m/%Y'))
        ]

        dia_mayor_recaudo = ''
        if datos_grafico:
            best_day = max(datos_grafico, key=lambda x: x['monto'])
            dia_mayor_recaudo = '%s (S/ %s)' % (best_day['fecha'], '{:,.2f}'.format(best_day['monto']))

        # ── Recaudo por día de la semana ─────────────────────────────────────
        semana_dict = defaultdict(lambda: {'monto': 0.0, 'pagos': 0})
        for r in registros:
            if not r['fecha_raw']:
                continue
            semana_dict[r['fecha_raw'].weekday()]['monto'] += r['total']
            semana_dict[r['fecha_raw'].weekday()]['pagos'] += 1

        datos_semana = [
            {'dia': DIAS_SEMANA[i], 'monto': semana_dict[i]['monto'], 'pagos': semana_dict[i]['pagos']}
            for i in range(7)
        ]

        # ── Distribución por forma de pago ───────────────────────────────────
        forma_pago_dict = defaultdict(lambda: {'monto': 0.0, 'pagos': 0})
        for r in registros:
            forma_pago_dict[r['forma_pago']]['monto'] += r['total']
            forma_pago_dict[r['forma_pago']]['pagos'] += 1

        datos_forma_pago = sorted(
            [{'forma': k, 'monto': v['monto'], 'pagos': v['pagos']} for k, v in forma_pago_dict.items()],
            key=lambda x: x['monto'],
            reverse=True,
        )
        for idx, entry in enumerate(datos_forma_pago):
            entry['color'] = CATEGORICAL_PALETTE[idx] if idx < len(CATEGORICAL_PALETTE) else COLOR_OTROS

        # ── Lista histórica de cobradores para el filtro ─────────────────────
        historicos = Reporte.search_read(
            [('move_state', '=', 'posted'), ('cobrador_id', '!=', False)], ['cobrador_id']
        )
        cobradores_map = {}
        for rec in historicos:
            cid, cname = rec['cobrador_id']
            cobradores_map[cid] = cname
        lista_cobradores = sorted(
            [{'id': k, 'name': v, 'selected': k in cobrador_ids_sel} for k, v in cobradores_map.items()],
            key=lambda x: x['name'],
        )

        # ── Renderizar template ──────────────────────────────────────────────
        values = {
            'registros': registros,
            'total_recaudado': total_recaudado,
            'total_cuotas': total_cuotas,
            'mora_recuperada': mora_recuperada,
            'total_pagos': total_pagos,
            'ticket_promedio': ticket_promedio,
            'cobradores_activos': cobradores_activos,
            'clientes_atendidos': clientes_atendidos,
            'promedio_pagos_dia': promedio_pagos_dia,
            'promedio_recaudo_dia': promedio_recaudo_dia,
            'pagos_puntuales': pagos_puntuales,
            'pagos_con_mora': pagos_con_mora,
            'pct_puntualidad': pct_puntualidad,
            'pago_maximo': pago_maximo,
            'mejor_cobrador': mejor_cobrador,
            'ranking_cobradores': ranking_cobradores,
            'ranking_chart': ranking_chart,
            'datos_forma_pago': datos_forma_pago,
            'datos_grafico_json': json.dumps(datos_grafico),
            'datos_semana_json': json.dumps(datos_semana),
            'datos_forma_pago_json': json.dumps(datos_forma_pago),
            'dia_mayor_recaudo': dia_mayor_recaudo,
            'color_puntual': COLOR_PUNTUAL,
            'color_mora': COLOR_MORA,
            'lista_cobradores': lista_cobradores,
            'cobrador_ids_sel': cobrador_ids_sel,
            'cobradores_sel_count': len(cobrador_ids_sel),
            'periodo_activo': periodo,
            'fecha_inicio_val': f_inicio.strftime('%d/%m/%Y'),
            'fecha_fin_val': f_fin.strftime('%d/%m/%Y'),
            'fecha_inicio_input': f_inicio.strftime('%Y-%m-%d'),
            'fecha_fin_input': f_fin.strftime('%Y-%m-%d'),
            'cobradores_qs': cobradores or '',
        }

        return request.render('adt_comercial.dashboard_cobranzas', values)
