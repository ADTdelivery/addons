import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

FRECUENCIAS = [
    ('diario', 'Diario'),
    ('semanal', 'Semanal'),
    ('quincenal', 'Quincenal'),
    ('mensual', 'Mensual'),
]

FRECUENCIA_DELTA = {
    'diario': relativedelta(days=1),
    'semanal': relativedelta(weeks=1),
    'quincenal': relativedelta(days=15),
    'mensual': relativedelta(months=1),
}


class CreditoContrato(models.Model):
    _name = 'credito.contrato'
    _description = 'Contrato de crédito'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inicio desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string="Referencia", default="Nuevo", copy=False, readonly=True)
    company_id = fields.Many2one('res.company', string="Compañía", required=True,
                                  default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string="Moneda", related='company_id.currency_id')
    partner_id = fields.Many2one('res.partner', string="Cliente", required=True, tracking=True)

    # Un contrato = un solo producto (sin líneas múltiples).
    product_id = fields.Many2one('product.product', string="Producto", required=True,
                                  domain=[('es_financiable', '=', True)])
    cantidad = fields.Float(string="Cantidad", default=1.0)
    precio_unitario = fields.Monetary(string="Precio unitario")

    cuota_ids = fields.One2many('credito.cuota', 'contrato_id', string="Cronograma")
    pago_ids = fields.One2many('credito.pago', 'contrato_id', string="Pagos")

    monto_total = fields.Monetary(string="Monto total", compute='_compute_montos', store=True)
    enganche = fields.Monetary(string="Enganche / Inicial", default=0.0)
    monto_financiado = fields.Monetary(string="Monto financiado", compute='_compute_montos', store=True)

    frecuencia = fields.Selection(FRECUENCIAS, string="Frecuencia de pago", required=True, default='mensual')
    numero_cuotas = fields.Integer(string="Número de cuotas", required=True, default=1)
    monto_cuota = fields.Monetary(
        string="Monto por cuota", compute='_compute_montos', store=True,
        help="Cuota fija sin interés: monto financiado / número de cuotas.",
    )
    fecha_inicio = fields.Date(string="Fecha de primera cuota", required=True, default=fields.Date.context_today)

    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('activo', 'Activo'),
        ('en_mora', 'En mora'),
        ('pagado', 'Pagado'),
        ('refinanciado', 'Refinanciado'),
        ('cancelado', 'Cancelado'),
    ], string="Estado", default='borrador', copy=False, tracking=True)

    semaforo = fields.Selection([
        ('verde', 'Al día'),
        ('amarillo', 'Retrasado'),
        ('rojo', 'En mora'),
    ], string="Semáforo", compute='_compute_semaforo', store=True)

    saldo_pendiente = fields.Monetary(string="Saldo pendiente", compute='_compute_saldo', store=True)
    mora_total = fields.Monetary(string="Mora acumulada", compute='_compute_saldo', store=True)
    cuotas_vencidas = fields.Integer(string="Cuotas vencidas", compute='_compute_saldo', store=True)
    cuotas_pagadas = fields.Integer(string="Cuotas pagadas", compute='_compute_saldo', store=True)

    pct_pagado = fields.Float(
        string="% Pagado", compute='_compute_progreso', store=True,
        help="Porcentaje del monto financiado ya pagado.",
    )
    pct_atraso = fields.Float(
        string="% Cuotas atrasadas", compute='_compute_progreso', store=True,
        help="Porcentaje de cuotas del cronograma que están vencidas.",
    )

    contrato_origen_id = fields.Many2one('credito.contrato', string="Refinanciado desde", readonly=True, copy=False)
    contrato_refinanciado_id = fields.Many2one('credito.contrato', string="Refinanciado en", readonly=True,
                                                copy=False)

    cliente_riesgo_html = fields.Html(
        string="Historial del cliente", compute='_compute_cliente_riesgo',
        help="Créditos activos y comportamiento de pago del cliente, en este sistema y "
             "(si está instalado) en adt_comercial.",
    )

    @api.depends('partner_id')
    def _compute_cliente_riesgo(self):
        for rec in self:
            rec.cliente_riesgo_html = rec._build_cliente_riesgo_html() if rec.partner_id else False

    # Paleta de severidad reutilizada por todas las filas del resumen — mismos 3
    # niveles que el semáforo del contrato (verde/amarillo/rojo) más un neutro "gris"
    # para cuando no hay nada que evaluar todavía.
    _RIESGO_COLORES = {
        'verde': {'bg': '#ecfdf5', 'border': '#a7f3d0', 'text': '#065f46', 'dot': '#22c55e'},
        'amarillo': {'bg': '#fffbeb', 'border': '#fde68a', 'text': '#92400e', 'dot': '#f59e0b'},
        'rojo': {'bg': '#fef2f2', 'border': '#fecaca', 'text': '#991b1b', 'dot': '#ef4444'},
        'gris': {'bg': '#f8fafc', 'border': '#e2e8f0', 'text': '#475569', 'dot': '#94a3b8'},
    }
    _RIESGO_ETIQUETA = {'verde': 'Riesgo bajo', 'amarillo': 'Riesgo medio', 'rojo': 'Riesgo alto', 'gris': 'Sin datos'}

    def _riesgo_fila(self, icono, titulo, cuerpo_html, nivel):
        """Una fila-tarjeta del resumen: ícono + título + contenido + punto de color."""
        c = self._RIESGO_COLORES[nivel]
        return (
            '<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 12px;'
            'border-radius:8px;background:%(bg)s;border:1px solid %(border)s;margin-bottom:8px;">'
            '<span style="font-size:18px;line-height:1.2;">%(icono)s</span>'
            '<div style="flex:1;min-width:0;">'
            '<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.4px;color:%(text)s;margin-bottom:3px;">%(titulo)s</div>'
            '%(cuerpo)s'
            '</div>'
            '<span style="width:10px;height:10px;border-radius:50%%;background:%(dot)s;'
            'flex-shrink:0;margin-top:4px;" title="%(etiqueta)s"></span>'
            '</div>'
        ) % {
            'bg': c['bg'], 'border': c['border'], 'text': c['text'], 'dot': c['dot'],
            'icono': icono, 'titulo': titulo, 'cuerpo': cuerpo_html,
            'etiqueta': self._RIESGO_ETIQUETA[nivel],
        }

    @staticmethod
    def _riesgo_chip(valor, etiqueta, color='#374151'):
        return (
            '<span style="display:inline-block;margin:2px 12px 0 0;font-size:12px;color:#374151;">'
            '<b style="color:%s;">%s</b> %s</span>'
        ) % (color, valor, etiqueta)

    @staticmethod
    def _riesgo_barra(pct, color):
        pct = max(min(pct, 100.0), 0.0)
        return (
            '<div style="background:#e5e7eb;border-radius:6px;height:6px;width:100%%;'
            'max-width:220px;margin-top:6px;overflow:hidden;">'
            '<div style="background:%s;height:100%%;width:%.1f%%;"></div>'
            '</div>'
        ) % (color, pct)

    def _build_cliente_riesgo_html(self):
        """Arma el resumen visual de riesgo del cliente que se muestra al elegirlo en
        un contrato: créditos activos, puntualidad de pago (en este sistema) y una
        validación cruzada contra adt.comercial.cuentas (financiamiento de vehículos),
        si ese módulo está instalado. adt_credito no depende de adt_comercial — por eso
        la validación es defensiva (chequea que el modelo exista en el registro antes de
        consultarlo) en vez de una dependencia dura en el manifest.

        Cada sección es una fila-tarjeta con ícono + color de severidad (ver
        _RIESGO_COLORES); al final se agrega un encabezado con el peor nivel de riesgo
        encontrado, para que se entienda de un vistazo sin tener que leer todo el
        detalle."""
        self.ensure_one()
        partner = self.partner_id
        moneda = self.currency_id.symbol or ''
        filas = []
        niveles_encontrados = []

        # ── 1. Créditos activos del cliente en este sistema (otros contratos) ──────
        domain = [('partner_id', '=', partner.id)]
        if self.id:
            domain.append(('id', '!=', self.id))
        otros = self.env['credito.contrato'].sudo().search(domain)
        activos = otros.filtered(lambda c: c.estado in ('activo', 'en_mora'))
        if activos:
            saldo = sum(activos.mapped('saldo_pendiente'))
            mora = sum(activos.mapped('mora_total'))
            nivel1 = 'rojo' if any(c.semaforo == 'rojo' for c in activos) else (
                'amarillo' if any(c.semaforo == 'amarillo' for c in activos) else 'verde')
            cuerpo = '<div style="font-size:13px;color:#111827;">'
            cuerpo += self._riesgo_chip('%d' % len(activos), 'crédito(s) activo(s)')
            cuerpo += self._riesgo_chip('%s %.2f' % (moneda, saldo), 'saldo pendiente')
            if mora:
                cuerpo += self._riesgo_chip('%s %.2f' % (moneda, mora), 'mora', color='#dc2626')
            cuerpo += '</div>'
            filas.append(self._riesgo_fila('💳', 'Este sistema (Crédito)', cuerpo, nivel1))
        else:
            nivel1 = 'verde'
            filas.append(self._riesgo_fila(
                '💳', 'Este sistema (Crédito)',
                '<div style="font-size:13px;color:#111827;">✓ Sin créditos activos.</div>', nivel1))
        niveles_encontrados.append(nivel1)

        # ── 2. Comportamiento de pago histórico (todas sus cuotas ya pagadas) ──────
        cuotas = self.env['credito.cuota'].sudo().search([('partner_id', '=', partner.id)])
        pagadas = cuotas.filtered(lambda c: c.estado == 'pagada')
        if pagadas:
            a_tiempo = 0
            for cuota in pagadas:
                pagos_cuota = cuota.pago_ids.filtered(lambda p: p.tipo == 'cuota' and p.fecha_pago)
                ultima_fecha = max(pagos_cuota.mapped('fecha_pago')) if pagos_cuota else False
                if ultima_fecha and cuota.fecha_vencimiento and ultima_fecha <= cuota.fecha_vencimiento:
                    a_tiempo += 1
            total = len(pagadas)
            pct = (a_tiempo / total * 100.0) if total else 0.0
            if pct >= 90:
                icono2, etiqueta2, nivel2 = '✅', 'Puntual', 'verde'
            elif pct >= 60:
                icono2, etiqueta2, nivel2 = '⚠️', 'Irregular', 'amarillo'
            else:
                icono2, etiqueta2, nivel2 = '❌', 'Mal pagador', 'rojo'
            color_barra = self._RIESGO_COLORES[nivel2]['dot']
            cuerpo = (
                '<div style="font-size:13px;color:#111827;">'
                '<b style="color:%s;">%s</b> — %d/%d cuotas pagadas a tiempo (%.0f%%)'
                '</div>%s'
            ) % (self._RIESGO_COLORES[nivel2]['text'], etiqueta2, a_tiempo, total, pct,
                 self._riesgo_barra(pct, color_barra))
            filas.append(self._riesgo_fila(icono2, 'Comportamiento de pago', cuerpo, nivel2))
        elif cuotas:
            nivel2 = 'gris'
            filas.append(self._riesgo_fila(
                '⏳', 'Comportamiento de pago',
                '<div style="font-size:13px;color:#111827;">Aún pagando su primer cronograma — '
                'todavía sin cuotas completadas.</div>', nivel2))
        else:
            nivel2 = 'gris'
            filas.append(self._riesgo_fila(
                '⏳', 'Comportamiento de pago',
                '<div style="font-size:13px;color:#111827;">Sin historial de pagos en este '
                'sistema.</div>', nivel2))
        niveles_encontrados.append(nivel2)

        # ── 3. Validación contra adt_comercial (financiamiento de vehículos) ───────
        # Todo este bloque es defensivo por partida doble: adt_credito no depende de
        # adt_comercial (puede no estar instalado), y aunque lo esté, es código de otro
        # módulo que esta función solo consulta — un error ahí (por ejemplo, un compute
        # de adt_comercial que no es seguro en batch al leer varios registros a la vez)
        # nunca debe romper el formulario del contrato de crédito. Por eso cada campo se
        # lee registro por registro (browse de un solo id, sin ids hermanos en el
        # prefetch) y todo el bloque va en try/except.
        if 'adt.comercial.cuentas' not in self.env.registry:
            filas.append(self._riesgo_fila(
                '🚗', 'adt_comercial (vehículos)',
                '<div style="font-size:13px;color:#111827;">adt_comercial no está instalado en '
                'este servidor — no se pudo validar.</div>', 'gris'))
        else:
            try:
                Cuentas = self.env['adt.comercial.cuentas'].sudo()
                cuentas = Cuentas.search([('partner_id', '=', partner.id)])
                activas = cuentas.filtered(lambda c: c.state in ('aprobado', 'en_curso'))
                if activas:
                    saldo_c = 0.0
                    mora_c = 0.0
                    retrasadas_c = 0
                    for cuenta_id in activas.ids:
                        cuenta = Cuentas.browse(cuenta_id)
                        saldo_c += cuenta.cuotas_saldo
                        mora_c += cuenta.mora_pendiente
                        retrasadas_c += cuenta.qty_cuotas_retrasado
                    nivel3 = 'rojo' if (mora_c or retrasadas_c) else 'amarillo'
                    cuerpo = '<div style="font-size:13px;color:#111827;">'
                    cuerpo += self._riesgo_chip('%d' % len(activas), 'préstamo(s) activo(s)')
                    cuerpo += self._riesgo_chip('%s %.2f' % (moneda, saldo_c), 'saldo')
                    if mora_c:
                        cuerpo += self._riesgo_chip('%s %.2f' % (moneda, mora_c), 'mora', color='#dc2626')
                    if retrasadas_c:
                        cuerpo += self._riesgo_chip('%d' % retrasadas_c, 'cuota(s) retrasada(s)', color='#dc2626')
                    cuerpo += '</div>'
                    filas.append(self._riesgo_fila('🚗', '⚠ adt_comercial (vehículos)', cuerpo, nivel3))
                elif cuentas:
                    nivel3 = 'verde'
                    filas.append(self._riesgo_fila(
                        '🚗', 'adt_comercial (vehículos)',
                        '<div style="font-size:13px;color:#111827;">✓ Sin préstamos activos '
                        '(tiene historial, pero está cerrado/pagado/cancelado).</div>', nivel3))
                else:
                    nivel3 = 'verde'
                    filas.append(self._riesgo_fila(
                        '🚗', 'adt_comercial (vehículos)',
                        '<div style="font-size:13px;color:#111827;">✓ Sin préstamos.</div>', nivel3))
            except Exception:
                _logger.exception(
                    'No se pudo validar préstamos de adt_comercial para el partner %s', partner.id)
                nivel3 = 'gris'
                filas.append(self._riesgo_fila(
                    '🚗', 'adt_comercial (vehículos)',
                    '<div style="font-size:13px;color:#111827;">No se pudo validar (error interno, '
                    'revisado en el log del servidor).</div>', nivel3))
        niveles_encontrados.append(nivel3)

        # ── Encabezado: peor nivel de riesgo encontrado, para leer todo de un vistazo ──
        orden_severidad = {'rojo': 3, 'amarillo': 2, 'gris': 1, 'verde': 0}
        nivel_general = max(niveles_encontrados, key=lambda n: orden_severidad[n])
        cg = self._RIESGO_COLORES[nivel_general]
        icono_general = {'rojo': '🔴', 'amarillo': '🟡', 'verde': '🟢', 'gris': '⚪'}[nivel_general]
        encabezado = (
            '<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;'
            'border-radius:8px 8px 0 0;background:%s;border:1px solid %s;border-bottom:none;">'
            '<span style="font-size:16px;">%s</span>'
            '<span style="font-size:12px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.5px;color:%s;">%s — %s</span>'
            '</div>'
        ) % (cg['bg'], cg['border'], icono_general, cg['text'],
             self._RIESGO_ETIQUETA[nivel_general], partner.name or '')

        return encabezado + ''.join(filas)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.precio_unitario = self.product_id.list_price

    @api.depends('cantidad', 'precio_unitario', 'enganche', 'numero_cuotas')
    def _compute_montos(self):
        for rec in self:
            rec.monto_total = rec.cantidad * rec.precio_unitario
            rec.monto_financiado = rec.monto_total - rec.enganche
            rec.monto_cuota = rec.numero_cuotas and (rec.monto_financiado / rec.numero_cuotas) or 0.0

    @api.depends('cuota_ids.saldo', 'cuota_ids.mora_monto', 'cuota_ids.estado')
    def _compute_saldo(self):
        for rec in self:
            rec.saldo_pendiente = sum(rec.cuota_ids.mapped('saldo'))
            rec.mora_total = sum(rec.cuota_ids.mapped('mora_monto'))
            rec.cuotas_vencidas = len(rec.cuota_ids.filtered(lambda c: c.estado == 'vencida'))
            rec.cuotas_pagadas = len(rec.cuota_ids.filtered(lambda c: c.estado == 'pagada'))

    @api.depends('estado', 'mora_total', 'cuotas_vencidas')
    def _compute_semaforo(self):
        for rec in self:
            if rec.estado == 'pagado':
                rec.semaforo = 'verde'
            elif rec.estado == 'en_mora' or rec.mora_total > 0:
                rec.semaforo = 'rojo'
            elif rec.cuotas_vencidas > 0:
                rec.semaforo = 'amarillo'
            else:
                rec.semaforo = 'verde'

    @api.depends('monto_financiado', 'saldo_pendiente', 'numero_cuotas', 'cuotas_vencidas')
    def _compute_progreso(self):
        for rec in self:
            if rec.monto_financiado:
                pagado = rec.monto_financiado - rec.saldo_pendiente
                rec.pct_pagado = max(min((pagado / rec.monto_financiado) * 100.0, 100.0), 0.0)
            else:
                rec.pct_pagado = 0.0
            rec.pct_atraso = (rec.cuotas_vencidas / rec.numero_cuotas * 100.0) if rec.numero_cuotas else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('credito.contrato') or 'Nuevo'
        return super().create(vals_list)

    def action_confirmar(self):
        for rec in self:
            if rec.estado != 'borrador':
                raise UserError(_("Solo se puede confirmar un contrato en borrador."))
            if not rec.product_id:
                raise UserError(_("Selecciona el producto a financiar."))
            if rec.numero_cuotas <= 0:
                raise UserError(_("El número de cuotas debe ser mayor a cero."))
            if rec.monto_financiado <= 0:
                raise UserError(_("El monto financiado debe ser mayor a cero."))
            rec._generar_cronograma()
            rec.estado = 'activo'

    @api.model
    def _calcular_cronograma(self, monto_financiado, numero_cuotas, frecuencia, fecha_inicio):
        """Calcula las cuotas fijas (sin interés) para un monto/plazo/frecuencia dados.

        Reutilizado tanto al confirmar un contrato real (`_generar_cronograma`) como por
        el simulador de la app móvil (`POST /v1/credit/simulate`), para que ambos caminos
        calculen exactamente lo mismo.
        """
        delta = FRECUENCIA_DELTA[frecuencia]
        fecha = fecha_inicio
        monto_cuota = round(monto_financiado / numero_cuotas, 2)
        acumulado = 0.0
        cuotas = []
        for i in range(1, numero_cuotas + 1):
            monto = monto_cuota
            if i == numero_cuotas:
                # ajusta la última cuota para que la suma cuadre exacto con el monto financiado
                monto = round(monto_financiado - acumulado, 2)
            acumulado += monto
            cuotas.append({'numero_cuota': i, 'fecha_vencimiento': fecha, 'monto': monto})
            fecha = fecha + delta
        return cuotas

    def _generar_cronograma(self):
        self.ensure_one()
        self.cuota_ids.unlink()
        cuotas = self._calcular_cronograma(self.monto_financiado, self.numero_cuotas,
                                            self.frecuencia, self.fecha_inicio)
        for vals in cuotas:
            vals['contrato_id'] = self.id
        self.env['credito.cuota'].create(cuotas)

    def action_cancelar(self):
        self.write({'estado': 'cancelado'})

    def action_ver_cronograma(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cronograma'),
            'res_model': 'credito.cuota',
            'view_mode': 'list,form',
            'domain': [('contrato_id', '=', self.id)],
        }

    def action_registrar_pago(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registrar pago'),
            'res_model': 'credito.registrar.pago',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contrato_id': self.id},
        }
