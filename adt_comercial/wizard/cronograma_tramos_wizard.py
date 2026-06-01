# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import UserError


class AdtCronogramaTramoLine(models.TransientModel):
    _name = 'adt.cronograma.tramo.line'
    _description = 'Tramo del cronograma por tramos'
    _order = 'cuota_desde asc'

    wizard_id = fields.Many2one(
        'adt.cronograma.tramos.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', related='wizard_id.currency_id')

    cuota_desde = fields.Integer(string='Cuota desde', required=True, default=1)
    cuota_hasta = fields.Integer(string='Cuota hasta', required=True, default=1)
    monto_cuota = fields.Monetary(
        string='Monto por cuota', required=True, currency_field='currency_id')

    cantidad = fields.Integer(
        string='Cant. cuotas', compute='_compute_totales', store=False)
    total_tramo = fields.Monetary(
        string='Subtotal tramo', compute='_compute_totales', store=False,
        currency_field='currency_id')

    @api.depends('cuota_desde', 'cuota_hasta', 'monto_cuota')
    def _compute_totales(self):
        for r in self:
            count = max(0, r.cuota_hasta - r.cuota_desde + 1)
            r.cantidad = count
            r.total_tramo = count * r.monto_cuota


class AdtCronogramaPreviewLine(models.TransientModel):
    _name = 'adt.cronograma.preview.line'
    _description = 'Línea de previsualización del cronograma'
    _order = 'numero asc'

    wizard_id = fields.Many2one(
        'adt.cronograma.tramos.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', related='wizard_id.currency_id')

    numero = fields.Integer(string='# Cuota')
    fecha = fields.Date(string='Fecha')
    monto = fields.Monetary(string='Monto', currency_field='currency_id')
    tramo_label = fields.Char(string='Tramo')


class AdtCronogramaTramos(models.TransientModel):
    _name = 'adt.cronograma.tramos.wizard'
    _description = 'Cronograma por tramos con montos variables'

    # ── Cuenta origen ────────────────────────────────────────────────────────
    cuenta_id = fields.Many2one(
        'adt.comercial.cuentas', string='Cuenta', required=True)

    # ── Parámetros del cronograma ────────────────────────────────────────────
    periodicidad = fields.Selection(
        [('semanal', 'Semanal'), ('quincena', 'Quincenal'), ('mensual', 'Mensual')],
        string='Periodicidad', required=True, default='quincena')
    fecha_inicio = fields.Date(
        string='Fecha de Cuota 0', required=True,
        help='Fecha de la cuota de gracia. Las cuotas del cronograma se generan a partir de esta fecha.')

    # Campo proxy para mostrar fecha_inicio con un label diferente cuando no hay cuota_gracia
    fecha_inicio_cuota1 = fields.Date(
        string='Fecha inicio Cuota 1',
        compute='_compute_fecha_inicio_cuota1',
        inverse='_set_fecha_inicio_cuota1',
        help='Fecha a partir de la cual arranca la Cuota 1 (sin cuota de gracia).')

    @api.depends('fecha_inicio')
    def _compute_fecha_inicio_cuota1(self):
        for r in self:
            r.fecha_inicio_cuota1 = r.fecha_inicio

    def _set_fecha_inicio_cuota1(self):
        for r in self:
            r.fecha_inicio = r.fecha_inicio_cuota1
    cuota_gracia = fields.Monetary(
        string='Cuota de gracia (Cuota 0)', currency_field='currency_id',
        default=0.0,
        help='Si es 0 no se genera Cuota 0 y la fecha ingresada corresponde a la Cuota 1.')

    tiene_cuota_gracia = fields.Boolean(
        compute='_compute_tiene_cuota_gracia', store=False)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)

    # ── Tramos y preview ─────────────────────────────────────────────────────
    tramo_ids = fields.One2many(
        'adt.cronograma.tramo.line', 'wizard_id', string='Tramos')
    preview_ids = fields.One2many(
        'adt.cronograma.preview.line', 'wizard_id', string='Vista previa')

    # ── Control de pasos ─────────────────────────────────────────────────────
    wizard_state = fields.Selection(
        [('configurar', 'Configurar'), ('previsualizar', 'Previsualizar')],
        default='configurar', string='Paso')

    # ── Totales calculados automáticamente desde los tramos ──────────────────
    total_cuotas = fields.Integer(
        string='Total cuotas', compute='_compute_totales')
    monto_fraccionado = fields.Monetary(
        string='Monto fraccionado total', compute='_compute_totales',
        currency_field='currency_id',
        help='Suma automática de todos los subtotales de tramos.')

    @api.depends('cuota_gracia')
    def _compute_tiene_cuota_gracia(self):
        for r in self:
            r.tiene_cuota_gracia = (r.cuota_gracia or 0.0) > 0.0

    @api.depends('tramo_ids.cantidad', 'tramo_ids.total_tramo')
    def _compute_totales(self):
        for r in self:
            r.total_cuotas = sum(r.tramo_ids.mapped('cantidad'))
            r.monto_fraccionado = sum(r.tramo_ids.mapped('total_tramo'))

    # ── Validación interna ───────────────────────────────────────────────────
    def _validar_tramos(self):
        if not self.tramo_ids:
            raise UserError('Debe definir al menos un tramo.')

        tramos = self.tramo_ids.sorted('cuota_desde')
        prev_hasta = 0
        for tramo in tramos:
            if tramo.cuota_desde <= 0:
                raise UserError(
                    'El número de cuota inicial debe ser mayor a 0 (tramo %d-%d).' % (
                        tramo.cuota_desde, tramo.cuota_hasta))
            if tramo.cuota_hasta < tramo.cuota_desde:
                raise UserError(
                    'La cuota hasta (%d) debe ser ≥ cuota desde (%d).' % (
                        tramo.cuota_hasta, tramo.cuota_desde))
            if tramo.cuota_desde != prev_hasta + 1:
                if prev_hasta == 0:
                    raise UserError(
                        'El primer tramo debe comenzar en la cuota 1 (actualmente comienza en %d).' % tramo.cuota_desde)
                raise UserError(
                    'Los tramos deben ser consecutivos sin huecos ni solapamientos.\n'
                    'El tramo %d-%d debe comenzar en %d (sigue al tramo anterior que termina en %d).' % (
                        tramo.cuota_desde, tramo.cuota_hasta,
                        prev_hasta + 1, prev_hasta))
            if tramo.monto_cuota <= 0:
                raise UserError(
                    'El monto de cuota debe ser mayor a 0 (tramo %d-%d).' % (
                        tramo.cuota_desde, tramo.cuota_hasta))
            prev_hasta = tramo.cuota_hasta

    def _days_for_periodicidad(self):
        return {'semanal': 7, 'quincena': 15, 'mensual': 30}.get(self.periodicidad, 15)

    def _build_preview_data(self):
        days = self._days_for_periodicidad()
        tramos = self.tramo_ids.sorted('cuota_desde')
        lines = []
        # Con cuota_gracia: fecha_inicio es la fecha de Cuota 0;
        #   la primera cuota del tramo cae en fecha_inicio + days.
        # Sin cuota_gracia: fecha_inicio ES la fecha de Cuota 1;
        #   retrocedemos un período para que el primer += days dé fecha_inicio.
        if (self.cuota_gracia or 0.0) > 0:
            fecha = self.fecha_inicio
        else:
            fecha = self.fecha_inicio - timedelta(days=days)
        for idx, tramo in enumerate(tramos, start=1):
            label = 'Tramo %d  (cuotas %d – %d)' % (idx, tramo.cuota_desde, tramo.cuota_hasta)
            for num in range(tramo.cuota_desde, tramo.cuota_hasta + 1):
                fecha = fecha + timedelta(days=days)
                lines.append({
                    'numero': num,
                    'fecha': fecha,
                    'monto': tramo.monto_cuota,
                    'tramo_label': label,
                })
        return lines

    # ── Acciones de los botones ──────────────────────────────────────────────
    def action_previsualizar(self):
        self.ensure_one()
        self._validar_tramos()

        preview_data = self._build_preview_data()
        self.preview_ids.unlink()
        self.write({
            'wizard_state': 'previsualizar',
            'preview_ids': [(0, 0, line) for line in preview_data],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_volver(self):
        self.ensure_one()
        self.wizard_state = 'configurar'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirmar(self):
        self.ensure_one()
        self._validar_tramos()
        cuenta = self.cuenta_id

        if cuenta.state == 'cancelado':
            raise UserError('No se puede modificar el cronograma de una cuenta cancelada.')

        days = self._days_for_periodicidad()
        Cuota = self.env['adt.comercial.cuotas']

        new_ids = []

        # Cuota 0 solo si hay monto de gracia > 0
        if (self.cuota_gracia or 0.0) > 0:
            new_ids.append(Cuota.create({
                'name': 'Cuota 0',
                'monto': self.cuota_gracia,
                'fecha_cronograma': self.fecha_inicio,
                'periodicidad': self.periodicidad,
                'cuenta_id': cuenta.id,
            }).id)
            fecha = self.fecha_inicio
        else:
            # Sin cuota gracia: fecha_inicio ES la fecha de Cuota 1
            fecha = self.fecha_inicio - timedelta(days=days)

        for tramo in self.tramo_ids.sorted('cuota_desde'):
            for num in range(tramo.cuota_desde, tramo.cuota_hasta + 1):
                fecha = fecha + timedelta(days=days)
                new_ids.append(Cuota.create({
                    'name': 'Cuota %d' % num,
                    'monto': tramo.monto_cuota,
                    'fecha_cronograma': fecha,
                    'periodicidad': self.periodicidad,
                    'cuenta_id': cuenta.id,
                }).id)

        # Reemplaza cuotas existentes
        cuenta.cuota_ids = [(6, 0, new_ids)]

        # Sincroniza campos de la cuenta para que el reporte y cálculos cuadren
        cuenta.write({
            'periodicidad': self.periodicidad,
            'fecha_gracia': self.fecha_inicio,
            'cuota_gracia': self.cuota_gracia,
            'monto_fraccionado': self.monto_fraccionado,
            'qty_cuotas': self.total_cuotas,
        })

        return {'type': 'ir.actions.act_window_close'}
