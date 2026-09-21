from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import html_escape
from odoo.tools.misc import format_amount

from .financiera_resumen import calcular_resumen

AZUL, AZUL_CLARO = '#2563eb', '#bfdbfe'
VERDE, VERDE_CLARO = '#16a34a', '#bbf7d0'
NARANJA, ROJO, GRIS = '#d97706', '#dc2626', '#e5e7eb'


class ADTComercialCuentasFinanciera(models.Model):
    _inherit = 'adt.comercial.cuentas'

    # --- Cronograma de la financiera (lo que ADT paga) ---
    fin_fecha_desembolso = fields.Date(string="Fecha de desembolso")
    fin_fecha_inicio = fields.Date(string="Fecha de inicio")
    fin_es_mensual = fields.Boolean(string="Es mensual", default=True)
    fin_fecha_fin = fields.Date(string="Fecha fin")
    fin_plazo_dias = fields.Integer(string="Plazo (días)")
    fin_monto_credito = fields.Monetary(string="Monto de crédito")
    fin_monto_cuota = fields.Monetary(string="Monto mensual de cuota")
    fin_monto_total = fields.Monetary(string="Monto total a pagar")
    fin_tasa_interes = fields.Float(string="Tasa de interés (%)", digits=(16, 4))

    fin_cancelada_manual = fields.Boolean(
        string="Cancelada manualmente",
        help="Márcalo si la financiera se pagó antes de lo previsto (pago anticipado). "
             "Con esto la cuenta pasa a 'Cancelada a la financiera' sin esperar las fechas del cronograma.",
        tracking=True)

    # --- Resultado (calculado y almacenado para poder filtrar, agrupar y reportar) ---
    fin_estado = fields.Selection(
        [('sin_datos', 'Sin datos de la financiera'),
         ('pagando', 'Pagando a la financiera'),
         ('cancelada', 'Cancelada a la financiera')],
        string="Estado con la financiera", compute='_compute_fin_resumen', store=True, index=True)
    fin_cantidad_cuotas = fields.Integer(
        string="Cuotas a la financiera", compute='_compute_fin_resumen', store=True)
    fin_cuotas_pagadas = fields.Integer(
        string="Cuotas pagadas a la financiera", compute='_compute_fin_resumen', store=True)
    fin_pagado = fields.Monetary(
        string="Pagado a la financiera", compute='_compute_fin_resumen', store=True)
    fin_pendiente = fields.Monetary(
        string="Pendiente con la financiera", compute='_compute_fin_resumen', store=True)
    fin_total_cliente = fields.Monetary(
        string="Total del cronograma del cliente", compute='_compute_fin_resumen', store=True)
    fin_cobrado_cliente = fields.Monetary(
        string="Cobrado al cliente", compute='_compute_fin_resumen', store=True)
    fin_faltante_equilibrio = fields.Monetary(
        string="Falta para el punto de equilibrio", compute='_compute_fin_resumen', store=True)
    fin_ganancia_esperada = fields.Monetary(
        string="Ganancia esperada de ADT", compute='_compute_fin_resumen', store=True)
    fin_ganancia_actual = fields.Monetary(
        string="Ganancia de ADT a la fecha", compute='_compute_fin_resumen', store=True)
    fin_caja_neta = fields.Monetary(
        string="Caja neta (cobrado - pagado a la financiera)",
        compute='_compute_fin_resumen', store=True)
    fin_en_ganancia = fields.Boolean(
        string="ADT ya está ganando", compute='_compute_fin_resumen', store=True)
    fin_pct_pagado = fields.Float(
        string="% pagado a la financiera", compute='_compute_fin_resumen', store=True, digits=(16, 2))
    fin_pct_recuperado = fields.Float(
        string="% recuperado (cobrado vs. financiera)", compute='_compute_fin_resumen',
        store=True, digits=(16, 2))
    fin_pct_cliente = fields.Float(
        string="% pagado por el cliente a ADT", compute='_compute_fin_resumen', store=True,
        digits=(16, 2), help="Cobrado al cliente sobre el total de su cronograma.")
    fin_desfase_pct = fields.Float(
        string="Desfase (% recuperado - % pagado)", compute='_compute_fin_resumen',
        store=True, digits=(16, 2),
        help="Negativo: se ha pagado a la financiera más de lo que se ha cobrado al cliente.")
    fin_semaforo = fields.Selection(
        [('sin_datos', 'Sin datos'),
         ('desfase', 'Desfase (cobrado < pagado)'),
         ('al_dia', 'Al día (cobrado >= pagado)'),
         ('ganando', 'Ganando (cobrado >= financiera)')],
        string="Semáforo", compute='_compute_fin_resumen', store=True, index=True)
    fin_html = fields.Html(
        string="Resumen visual", compute='_compute_fin_html', sanitize=False)

    @api.constrains('fin_fecha_inicio', 'fin_fecha_fin', 'fin_monto_credito',
                    'fin_monto_cuota', 'fin_monto_total', 'fin_plazo_dias')
    def _check_fin_datos(self):
        for rec in self:
            if rec.fin_fecha_inicio and rec.fin_fecha_fin and rec.fin_fecha_fin < rec.fin_fecha_inicio:
                raise ValidationError(_("La fecha fin de la financiera no puede ser anterior a la fecha de inicio."))
            if min(rec.fin_monto_credito, rec.fin_monto_cuota, rec.fin_monto_total) < 0 \
                    or rec.fin_plazo_dias < 0:
                raise ValidationError(_("Los datos de la financiera no pueden ser negativos."))

    _FIN_DEPENDENCIAS = (
        'fin_fecha_inicio', 'fin_es_mensual', 'fin_fecha_fin', 'fin_monto_cuota', 'fin_monto_total',
        'fin_cancelada_manual', 'cuota_ids.monto', 'cuota_ids.state', 'cuota_ids.type',
        'cuota_ids.payment_ids.amount', 'cuota_ids.payment_ids.state')

    def _fin_calcular(self, hoy):
        """Resumen de la financiera + lo que el cliente debe/ha pagado a ADT."""
        self.ensure_one()
        cuotas = self.cuota_ids.filtered(lambda c: c.type == 'cuota' and c.state != 'anulada')
        total_cliente = sum(cuotas.mapped('monto'))
        cobrado = sum(cuotas.mapped('payment_ids').filtered(
            lambda p: p.state == 'posted').mapped('amount'))
        r = calcular_resumen(
            hoy, self.fin_fecha_inicio, self.fin_es_mensual, self.fin_fecha_fin,
            self.fin_monto_cuota, self.fin_monto_total, total_cliente, cobrado,
            cancelada_manual=self.fin_cancelada_manual)
        return r, total_cliente, cobrado

    @api.depends(*_FIN_DEPENDENCIAS)
    def _compute_fin_resumen(self):
        hoy = fields.Date.context_today(self)
        for rec in self:
            r, total_cliente, cobrado = rec._fin_calcular(hoy)
            total_fin = rec.fin_monto_total
            if total_fin <= 0 or rec.fin_monto_cuota <= 0:
                estado = 'sin_datos'
            elif r['cantidad_cuotas'] and r['cuotas_pagadas'] >= r['cantidad_cuotas']:
                estado = 'cancelada'
            else:
                estado = 'pagando'
            rec.fin_estado = estado
            rec.fin_cantidad_cuotas = r['cantidad_cuotas']
            rec.fin_cuotas_pagadas = r['cuotas_pagadas']
            rec.fin_pagado = r['pagado']
            rec.fin_pendiente = r['pendiente']
            rec.fin_total_cliente = total_cliente
            rec.fin_cobrado_cliente = cobrado
            rec.fin_faltante_equilibrio = r['faltante_equilibrio']
            rec.fin_ganancia_esperada = r['ganancia_esperada']
            rec.fin_ganancia_actual = r['ganancia_actual']
            rec.fin_caja_neta = r['caja_neta']
            rec.fin_en_ganancia = total_fin > 0 and cobrado >= total_fin
            rec.fin_pct_pagado = min(r['pagado'] / total_fin * 100, 100.0) if total_fin > 0 else 0.0
            rec.fin_pct_recuperado = (
                min(cobrado / total_fin * 100, 100.0) if total_fin > 0 else 0.0)
            rec.fin_pct_cliente = (
                min(cobrado / total_cliente * 100, 100.0) if total_cliente > 0 else 0.0)
            rec.fin_desfase_pct = rec.fin_pct_recuperado - rec.fin_pct_pagado
            if estado == 'sin_datos':
                rec.fin_semaforo = 'sin_datos'
            elif cobrado >= total_fin:
                rec.fin_semaforo = 'ganando'
            elif r['caja_neta'] < -0.005:
                rec.fin_semaforo = 'desfase'
            else:
                rec.fin_semaforo = 'al_dia'

    @api.depends(*_FIN_DEPENDENCIAS)
    def _compute_fin_html(self):
        hoy = fields.Date.context_today(self)
        for rec in self:
            r, total_cliente, cobrado = rec._fin_calcular(hoy)
            rec.fin_html = rec._fin_render_html(r, total_cliente, cobrado)

    @api.model
    def _cron_actualizar_financiera(self):
        """Los estados dependen de la fecha de hoy: se refrescan cada día."""
        cuentas = self.search([('fin_monto_total', '>', 0), ('fin_estado', '!=', 'cancelada')])
        cuentas.modified(['fin_fecha_inicio'])
        cuentas.flush()
        return True

    # ------------------------------------------------------------------ visual
    def _fin_render_html(self, r, total_cliente, cobrado):
        self.ensure_one()
        total_fin = self.fin_monto_total
        if total_fin <= 0 or self.fin_monto_cuota <= 0:
            return self._fin_caja(
                GRIS, '#374151', 'ℹ️ Aún no hay datos de la financiera',
                'Completa más abajo el <b>monto total</b> y el <b>monto mensual de cuota</b> '
                'del cronograma de la financiera para ver la comparación.')

        def money(valor):
            return html_escape(format_amount(self.env, valor, self.currency_id))

        def pct(parte, todo):
            return max(0.0, min(100.0, parte / todo * 100.0)) if todo else 0.0

        en_ganancia = cobrado >= total_fin
        pct_financiera = pct(r['pagado'], total_fin)

        # Barra 2: escala = lo que sea mayor entre lo que cobra ADT y lo que debe a la financiera
        escala = max(total_cliente, total_fin)
        ganancia_total = max(escala - total_fin, 0.0)
        cubierto = min(cobrado, total_fin)
        falta_cubrir = total_fin - cubierto
        ganancia_ya = min(max(cobrado - total_fin, 0.0), ganancia_total)
        ganancia_falta = ganancia_total - ganancia_ya
        w = {k: pct(v, escala) for k, v in (
            ('a', cubierto), ('b', falta_cubrir), ('c', ganancia_ya), ('d', ganancia_falta))}
        marca = pct(total_fin, escala)

        if en_ganancia:
            banner = self._fin_caja(
                VERDE, '#ffffff', '🎉 ¡Ya cubrimos a la financiera! Desde aquí estamos ganando',
                'Lo cobrado al cliente ya supera los <b>%s</b> que se pagan a la financiera. '
                'Cada sol que entra ahora es ganancia de ADT. <b>Ganancia acumulada: %s</b>.'
                % (money(total_fin), money(r['ganancia_actual'])))
        else:
            banner = self._fin_caja(
                NARANJA, '#ffffff', '⏳ Todavía recuperando lo que se paga a la financiera',
                'Faltan <b>%s</b> por cobrar al cliente para llegar al punto de equilibrio. '
                'Después de ese punto, todo lo que cobremos es ganancia.'
                % money(r['faltante_equilibrio']))
        if r['cantidad_cuotas'] and r['cuotas_pagadas'] >= r['cantidad_cuotas']:
            banner += self._fin_caja(
                AZUL, '#ffffff', '✅ La financiera ya fue pagada en su totalidad',
                'Se completaron las %s cuotas del cronograma de la financiera.%s'
                % (r['cantidad_cuotas'],
                   ' (Marcada como cancelada manualmente.)' if self.fin_cancelada_manual else ''))

        pct_cobrado = pct(cobrado, total_fin)
        desfase = pct_cobrado - pct_financiera
        if self.fin_semaforo == 'desfase':
            banner = self._fin_caja(
                ROJO, '#ffffff', '🔴 Desfase: hemos pagado a la financiera más de lo que hemos cobrado',
                'Pagado a la financiera: <b>%s</b> (%.1f%%) · Cobrado al cliente: <b>%s</b> (%.1f%%). '
                'ADT está adelantando <b>%s</b> de su propio dinero.'
                % (money(r['pagado']), pct_financiera, money(cobrado), pct_cobrado,
                   money(-r['caja_neta']))) + banner
        color_cmp = ROJO if desfase < -0.005 else VERDE
        comparacion = (
            '<div style="margin-top:12px;padding:8px 14px;border-radius:8px;background:%s;'
            'border-left:5px solid %s;font-size:13px;color:#111827">⚖️ <b>Pagado a la financiera %.1f%%</b> '
            'vs. <b>cobrado al cliente %.1f%%</b> → %s <b style="color:%s">%+.1f puntos</b></div>' % (
                '#fef2f2' if desfase < -0.005 else '#f0fdf4', color_cmp, pct_financiera, pct_cobrado,
                'desfase de' if desfase < -0.005 else 'a favor de ADT:', color_cmp, desfase))

        caja_color = VERDE if r['caja_neta'] >= 0 else ROJO
        kpis = ''.join([
            self._fin_kpi('🏦 Pagado a la financiera', money(r['pagado']),
                          'de %s · %s de %s cuotas' % (money(total_fin), r['cuotas_pagadas'],
                                                        r['cantidad_cuotas']), AZUL),
            self._fin_kpi('🧾 Cobrado al cliente', money(cobrado),
                          'de %s programados' % money(total_cliente), AZUL),
            self._fin_kpi('💰 Ganancia de ADT a la fecha', money(r['ganancia_actual']),
                          'esperada al final: %s' % money(r['ganancia_esperada']), VERDE),
            self._fin_kpi('⚖️ Caja neta hoy', money(r['caja_neta']),
                          'cobrado − pagado a la financiera', caja_color),
        ])

        barra1 = self._fin_barra_simple(pct_financiera)
        barra2 = self._fin_barra_equilibrio(
            w['a'], w['b'], w['c'], w['d'], marca,
            texto_ganancia='💰 Ganancia de ADT: %s' % money(ganancia_ya))
        leyenda = ''.join(self._fin_leyenda(color, texto) for color, texto in (
            (AZUL, 'Cobrado que cubre a la financiera: <b>%s</b>' % money(cubierto)),
            (AZUL_CLARO, 'Falta cubrir a la financiera: <b>%s</b>' % money(falta_cubrir)),
            (VERDE, 'Ganancia ya lograda: <b>%s</b>' % money(ganancia_ya)),
            (VERDE_CLARO, 'Ganancia por lograr: <b>%s</b>' % money(ganancia_falta)),
        ))
        aviso = ''
        if total_cliente < total_fin:
            aviso = self._fin_caja(
                ROJO, '#ffffff', '⚠️ El cronograma del cliente es menor que lo que se paga a la financiera',
                'Total del cliente %s vs. financiera %s: con este cronograma ADT no llegaría a ganar.'
                % (money(total_cliente), money(total_fin)))

        explicacion = (
            '<ol style="margin:0;padding-left:18px;color:#374151;font-size:13px;line-height:1.7">'
            '<li>ADT paga a la financiera su cuota <b>todos los meses</b>, sin atrasos.</li>'
            '<li>El cliente le paga a ADT su <b>propio cronograma</b>.</li>'
            '<li>Mientras lo cobrado al cliente sea menor al monto total de la financiera, '
            'ADT está <b>recuperando</b>.</li>'
            '<li>Al pasar el <b>punto de equilibrio</b>, lo que se cobra es <b>ganancia de ADT</b>.</li>'
            '</ol>')

        return (
            '<div style="max-width:1000px">%(banner)s%(aviso)s'
            '<div style="display:flex;flex-wrap:wrap;gap:12px;margin:14px 0">%(kpis)s</div>'
            '%(t1)s%(barra1)s'
            '<div style="font-size:12px;color:#6b7280;margin-top:4px">%(p1).1f%% pagado a la financiera'
            ' · faltan %(pend)s</div>'
            '%(t2)s%(barra2)s'
            '<div style="display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:10px">%(leyenda)s</div>'
            '%(comparacion)s'
            '<div style="margin-top:18px;padding:12px 16px;background:#f9fafb;border:1px solid #e5e7eb;'
            'border-radius:8px"><div style="font-weight:600;margin-bottom:6px">📖 ¿Cómo se lee?</div>'
            '%(explicacion)s</div></div>'
        ) % {
            'banner': banner, 'aviso': aviso, 'kpis': kpis,
            't1': self._fin_titulo('1) Lo que ADT paga a la financiera'), 'barra1': barra1,
            'p1': pct_financiera, 'pend': money(r['pendiente']),
            't2': self._fin_titulo('2) Lo que el cliente paga a ADT vs. lo que ADT debe a la financiera'),
            'barra2': barra2, 'leyenda': leyenda, 'explicacion': explicacion,
            'comparacion': comparacion,
        }

    @staticmethod
    def _fin_barra_simple(porcentaje, color=AZUL):
        return (
            '<div style="background:%s;border-radius:8px;height:26px;overflow:hidden">'
            '<div style="width:%.2f%%;background:%s;height:100%%"></div></div>'
            % (GRIS, porcentaje, color))

    @staticmethod
    def _fin_barra_equilibrio(a, b, c, d, marca, etiqueta='📍 Punto de equilibrio',
                              texto_ganancia=''):
        """a: cubre financiera, b: falta cubrir, c: ganancia lograda, d: ganancia por lograr (en %)."""
        rayas = ('repeating-linear-gradient(45deg,%s,%s 6px,#ffffff 6px,#ffffff 12px)'
                 % (AZUL_CLARO, AZUL_CLARO))
        segmentos = ''.join(
            '<div style="width:%.2f%%;height:100%%;float:left;background:%s"></div>' % (ancho, fondo)
            for ancho, fondo in ((a, AZUL), (b, rayas), (c, VERDE), (d, VERDE_CLARO)))
        # La ganancia arranca donde termina el punto de equilibrio; su etiqueta va justo debajo.
        lado = 'right:0;' if marca > 70 else 'left:%.2f%%;' % marca
        pastilla = (
            '<div style="position:absolute;top:62px;%s"><span style="display:inline-block;'
            'background:#dcfce7;color:#166534;border:1px solid #86efac;border-radius:999px;'
            'padding:3px 12px;font-size:12px;font-weight:700;white-space:nowrap">%s</span></div>'
            % (lado, texto_ganancia)) if texto_ganancia else ''
        return (
            '<div style="position:relative;padding-top:22px;padding-bottom:%(pb)spx">'
            '<div style="position:absolute;top:0;left:%(m).2f%%;transform:translateX(-50%%);'
            'font-size:11px;font-weight:600;color:#374151;white-space:nowrap">%(et)s</div>'
            '<div style="position:absolute;top:16px;bottom:0;left:%(m).2f%%;width:0;'
            'border-left:3px dashed #111827;z-index:2"></div>'
            '<div style="background:%(gris)s;border-radius:8px;height:34px;overflow:hidden">%(seg)s</div>'
            '%(pastilla)s</div>' % {'m': marca, 'gris': GRIS, 'seg': segmentos, 'et': etiqueta,
                                   'pastilla': pastilla, 'pb': 34 if texto_ganancia else 0})

    @staticmethod
    def _fin_caja(fondo, texto, titulo, detalle):
        return (
            '<div style="background:%s;color:%s;border-radius:10px;padding:14px 18px;margin-bottom:10px">'
            '<div style="font-size:16px;font-weight:700">%s</div>'
            '<div style="font-size:13px;margin-top:4px">%s</div></div>' % (fondo, texto, titulo, detalle))

    @staticmethod
    def _fin_kpi(titulo, valor, detalle, color):
        return (
            '<div style="flex:1 1 200px;border:1px solid #e5e7eb;border-top:4px solid %s;'
            'border-radius:8px;padding:10px 14px;background:#ffffff">'
            '<div style="font-size:12px;color:#6b7280">%s</div>'
            '<div style="font-size:22px;font-weight:700;color:%s">%s</div>'
            '<div style="font-size:11px;color:#6b7280">%s</div></div>' % (color, titulo, color, valor, detalle))

    @staticmethod
    def _fin_titulo(texto):
        return '<div style="font-weight:600;margin:16px 0 6px">%s</div>' % texto

    @staticmethod
    def _fin_leyenda(color, texto):
        return (
            '<div style="font-size:12px;color:#374151"><span style="display:inline-block;width:12px;'
            'height:12px;border-radius:3px;background:%s;margin-right:6px;vertical-align:middle;'
            'border:1px solid #d1d5db"></span>%s</div>' % (color, texto))
