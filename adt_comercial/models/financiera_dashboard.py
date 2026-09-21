from odoo import _, api, fields, models
from odoo.tools import html_escape
from odoo.tools.misc import format_amount

from .comercial_cuentas_financiera import (
    AZUL, AZUL_CLARO, GRIS, NARANJA, ROJO, VERDE, VERDE_CLARO, ADTComercialCuentasFinanciera as Vista)

CAMPOS = [
    'tipo_financiera_id', 'fin_estado', 'fin_monto_total', 'fin_pagado', 'fin_pendiente',
    'fin_cobrado_cliente', 'fin_total_cliente', 'fin_faltante_equilibrio', 'fin_ganancia_actual',
    'fin_ganancia_esperada', 'fin_caja_neta', 'fin_en_ganancia', 'fin_semaforo',
]


class AdtFinancieraDashboard(models.TransientModel):
    _name = 'adt.comercial.financiera.dashboard'
    _description = 'Resumen gerencial de financieras'

    html = fields.Html(string="Resumen", compute='_compute_html', sanitize=False)

    @api.model
    def action_abrir(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Resumen gerencial - Financieras'),
            'res_model': self._name,
            'res_id': self.create({}).id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _compute_html(self):
        for rec in self:
            rec.html = rec._render()

    # ------------------------------------------------------------------
    def _render(self):
        moneda = self.env.company.currency_id

        def money(valor):
            return html_escape(format_amount(self.env, valor, moneda))

        def pct(parte, todo):
            return max(0.0, min(100.0, parte / todo * 100.0)) if todo else 0.0

        cuentas = self.env['adt.comercial.cuentas'].search_read(
            [('fin_monto_total', '>', 0)], CAMPOS)
        if not cuentas:
            return Vista._fin_caja(
                GRIS, '#374151', 'ℹ️ Aún no hay cuentas con datos de la financiera',
                'Ingresa el cronograma de la financiera en la pestaña <b>Financiera</b> de cada cuenta.')

        def nueva():
            return dict(n=0, canceladas=0, ganando=0, total_fin=0.0, pagado=0.0, cobrado=0.0,
                        total_cliente=0.0, falta=0.0, gan_ya=0.0, gan_pot=0.0, gan_esp=0.0, caja=0.0,
                        desfase=0, monto_desfase=0.0)

        total, por_financiera = nueva(), {}
        for c in cuentas:
            nombre = c['tipo_financiera_id'][1] if c['tipo_financiera_id'] else _('Sin financiera')
            gan_pot = max(c['fin_ganancia_esperada'], 0.0)
            gan_ya = min(c['fin_ganancia_actual'], gan_pot)
            for acumulado in (total, por_financiera.setdefault(nombre, nueva())):
                acumulado['n'] += 1
                acumulado['canceladas'] += c['fin_estado'] == 'cancelada'
                acumulado['ganando'] += bool(c['fin_en_ganancia'])
                acumulado['total_fin'] += c['fin_monto_total']
                acumulado['pagado'] += c['fin_pagado']
                acumulado['cobrado'] += c['fin_cobrado_cliente']
                acumulado['total_cliente'] += c['fin_total_cliente']
                acumulado['falta'] += c['fin_faltante_equilibrio']
                acumulado['gan_ya'] += gan_ya
                acumulado['gan_pot'] += gan_pot
                acumulado['gan_esp'] += c['fin_ganancia_esperada']
                acumulado['caja'] += c['fin_caja_neta']
                if c['fin_semaforo'] == 'desfase':
                    acumulado['desfase'] += 1
                    acumulado['monto_desfase'] += -c['fin_caja_neta']

        t = total
        pagando = t['n'] - t['canceladas']
        recuperando = t['n'] - t['ganando']
        cubierto = t['total_fin'] - t['falta']
        escala = t['total_fin'] + t['gan_pot']
        gan_falta = t['gan_pot'] - t['gan_ya']

        banner = Vista._fin_caja(
            VERDE if t['ganando'] == t['n'] else AZUL, '#ffffff',
            '📊 %s vehículos con financiera' % t['n'],
            '<b>%s</b> ya canceló la financiera · <b>%s</b> sigue pagando · '
            '<b>%s</b> ya cubrió a la financiera y genera ganancia · <b>%s</b> aún recupera.'
            % (t['canceladas'], pagando, t['ganando'], recuperando))
        if t['desfase']:
            banner = Vista._fin_caja(
                ROJO, '#ffffff', '🔴 %s vehículos en desfase' % t['desfase'],
                'En estas cuentas ya se pagó a la financiera más de lo que se cobró al cliente: '
                'ADT está adelantando <b>%s</b>.' % money(t['monto_desfase'])) + banner
        else:
            banner = Vista._fin_caja(
                VERDE, '#ffffff', '🟢 Sin desfases',
                'En todas las cuentas lo cobrado cubre lo ya pagado a las financieras.') + banner

        kpis = ''.join([
            Vista._fin_kpi('🏦 Pagado a las financieras', money(t['pagado']),
                           'de %s (%.1f%%)' % (money(t['total_fin']), pct(t['pagado'], t['total_fin'])),
                           AZUL),
            Vista._fin_kpi('🧾 Cobrado a los clientes', money(t['cobrado']),
                           'de %s programados' % money(t['total_cliente']), AZUL),
            Vista._fin_kpi('💰 Ganancia de ADT a la fecha', money(t['gan_ya']),
                           'esperada al final: %s' % money(t['gan_pot']), VERDE),
            Vista._fin_kpi('⚖️ Caja neta hoy', money(t['caja']), 'cobrado − pagado a las financieras',
                           VERDE if t['caja'] >= 0 else ROJO),
        ])

        barra1 = Vista._fin_barra_simple(pct(t['pagado'], t['total_fin']))
        barra2 = Vista._fin_barra_equilibrio(
            pct(cubierto, escala), pct(t['falta'], escala), pct(t['gan_ya'], escala),
            pct(gan_falta, escala), pct(t['total_fin'], escala), '📍 Punto de equilibrio global',
            texto_ganancia='💰 Ganancia de ADT: %s' % money(t['gan_ya']))
        leyenda = ''.join(Vista._fin_leyenda(color, texto) for color, texto in (
            (AZUL, 'Cobrado que cubre a las financieras: <b>%s</b>' % money(cubierto)),
            (AZUL_CLARO, 'Falta cubrir: <b>%s</b>' % money(t['falta'])),
            (VERDE, 'Ganancia ya lograda: <b>%s</b>' % money(t['gan_ya'])),
            (VERDE_CLARO, 'Ganancia por lograr: <b>%s</b>' % money(gan_falta)),
        ))

        def mini(porcentaje, color):
            return (
                '<div style="display:flex;align-items:center;gap:6px;min-width:120px">'
                '<div style="flex:1;background:%s;border-radius:6px;height:10px;overflow:hidden">'
                '<div style="width:%.1f%%;background:%s;height:100%%"></div></div>'
                '<span style="font-size:11px;color:#374151;width:38px;text-align:right">%.0f%%</span></div>'
                % (GRIS, porcentaje, color, porcentaje))

        celda = 'padding:8px 10px;border-bottom:1px solid #e5e7eb;'
        def fila(nombre, a, total=False):
            fondo = 'background:#f0fdf4;border-top:2px solid %s;' % VERDE if total else ''
            peso = 'font-weight:700;' if total else 'font-weight:600;'
            tam = 'font-size:15px;' if total else ''
            return (
                '<tr style="%(fondo)s"><td style="%(c)s%(peso)s">%(nombre)s</td>'
                '<td style="%(c)stext-align:center">%(n)s</td>'
                '<td style="%(c)stext-align:center">%(canc)s</td>'
                '<td style="%(c)stext-align:center">%(gan)s</td>'
                '<td style="%(c)s">%(b1)s</td><td style="%(c)s">%(b2)s</td>'
                '<td style="%(c)stext-align:center">%(desf)s</td>'
                '<td style="%(c)stext-align:right;white-space:nowrap;color:%(verde)s;%(peso)s%(tam)s">%(gya)s</td>'
                '<td style="%(c)stext-align:right;%(peso)s">%(gesp)s</td></tr>' % {
                    'fondo': fondo, 'peso': peso, 'tam': tam,
                    'c': celda, 'nombre': nombre, 'n': a['n'], 'canc': a['canceladas'],
                    'gan': a['ganando'], 'verde': VERDE,
                    'b1': mini(pct(a['pagado'], a['total_fin']), AZUL),
                    'b2': mini(pct(a['total_fin'] - a['falta'], a['total_fin']),
                               VERDE if a['total_fin'] - a['falta'] >= a['pagado'] else ROJO),
                    'desf': (
                        '<span style="color:%s;font-weight:600">🔴 %s · %s</span>'
                        % (ROJO, a['desfase'], money(a['monto_desfase'])) if a['desfase']
                        else '<span style="color:%s">🟢 —</span>' % VERDE),
                    'gya': ('💰 ' if total else '') + money(a['gan_ya']), 'gesp': money(a['gan_pot'])})

        filas = ''.join(fila(html_escape(nombre), por_financiera[nombre])
                        for nombre in sorted(por_financiera))
        filas += fila('TOTAL GLOBAL — Ganancia de ADT', total, total=True)
        encabezados = ''.join(
            '<th style="padding:8px 10px;text-align:%s">%s</th>' % (alineacion, texto)
            for texto, alineacion in (
                ('Financiera', 'left'), ('Vehículos', 'center'), ('Canceladas', 'center'),
                ('Ya ganando', 'center'), ('Pagado a la financiera', 'left'),
                ('Recuperado (cobrado vs. financiera)', 'left'), ('En desfase', 'center'),
                ('Ganancia a la fecha', 'right'), ('Ganancia esperada', 'right')))
        tabla = (
            '<table style="width:100%%;border-collapse:collapse;font-size:13px">'
            '<thead><tr style="background:#f3f4f6">%s</tr></thead><tbody>%s</tbody></table>'
            % (encabezados, filas))

        return (
            '<div style="max-width:1100px">%(banner)s'
            '<div style="display:flex;flex-wrap:wrap;gap:12px;margin:14px 0">%(kpis)s</div>'
            '%(t1)s%(barra1)s'
            '<div style="font-size:12px;color:#6b7280;margin-top:4px">%(p1).1f%% pagado a las '
            'financieras · faltan %(pend)s</div>'
            '%(t2)s%(barra2)s'
            '<div style="display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:10px">%(leyenda)s</div>'
            '%(t3)s%(tabla)s'
            '<div style="margin-top:18px;padding:12px 16px;background:#f9fafb;border:1px solid #e5e7eb;'
            'border-radius:8px;font-size:13px;color:#374151"><b>📖 ¿Cómo se lee?</b> '
            'ADT paga a cada financiera su cuota todos los meses. Mientras lo cobrado a los clientes no '
            'alcance lo que se debe a la financiera, ADT está <b>recuperando</b>; al pasar el '
            '<b>punto de equilibrio</b>, lo que entra es <b>ganancia</b>. <span style="color:#dc2626">'
            '<b>Rojo</b></span> = se pagó a la financiera más de lo que se cobró (desfase); '
            '<span style="color:#16a34a"><b>verde</b></span> = lo cobrado cubre lo pagado. '
            'El detalle por vehículo está en las opciones de <i>Reporte Financiera</i>.</div></div>'
        ) % {
            'banner': banner, 'kpis': kpis, 'barra1': barra1, 'barra2': barra2, 'leyenda': leyenda,
            't1': Vista._fin_titulo('1) Lo que ADT ha pagado a las financieras (global)'),
            't2': Vista._fin_titulo('2) Lo que cobramos a los clientes vs. lo que debemos a las financieras'),
            't3': Vista._fin_titulo('3) Detalle por financiera'),
            'p1': pct(t['pagado'], t['total_fin']), 'pend': money(t['total_fin'] - t['pagado']),
            'tabla': tabla,
        }
