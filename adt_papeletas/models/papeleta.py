# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ADTPapeleta(models.Model):
    _name = 'adt.papeleta'
    _description = 'Papeleta Vehicular'
    _order = 'fecha_papeleta desc'

    name = fields.Char(string='Número de Papeleta', required=True)
    fecha_papeleta = fields.Date(string='Fecha de Papeleta', required=True)
    monto = fields.Monetary(string='Monto', required=True, currency_field='company_currency_id')
    detalle = fields.Text(string='Detalle')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True)

    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado'),
        ('fraccionado', 'Fraccionado')
    ], string='Estado', default='pendiente', tracking=True)

    fecha_captura = fields.Date(string='Fecha de Captura', compute='_compute_fecha_captura', store=True)

    tiene_prorroga = fields.Boolean(string='Tiene Prórroga')
    dias_prorroga = fields.Integer(string='Días de Prórroga')
    motivo_prorroga = fields.Text(string='Motivo de Prórroga')
    fecha_vencimiento_final = fields.Date(string='Fecha de Vencimiento Final', compute='_compute_fecha_vencimiento_final', store=True)

    company_currency_id = fields.Many2one('res.currency', string='Moneda', related='company_id.currency_id', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Indicador de proximidad
    proximo_a_vencerse = fields.Boolean(string='Próximo a vencerse', compute='_compute_proximo_a_vencerse', store=True)
    dias_para_captura = fields.Integer(string='Días para captura', compute='_compute_proximo_a_vencerse', store=True)
    texto_alerta = fields.Char(string='Texto Alerta', compute='_compute_proximo_a_vencerse', store=True)
    alert_badge = fields.Char(string='Badge Alerta', compute='_compute_proximo_a_vencerse', store=True)

    # Fraccionamiento
    cantidad_cuotas = fields.Integer(string='Cantidad de Cuotas')
    cuotas_ids = fields.One2many('adt.papeleta.cuota', 'papeleta_id', string='Cuotas', copy=True)
    fecha_pago = fields.Date(string='Fecha de Pago')
    show_fraccionamiento = fields.Boolean(string='Mostrar Fraccionamiento', compute='_compute_show_fraccionamiento', store=True)

    @api.depends('fecha_papeleta')
    def _compute_fecha_captura(self):
        for rec in self:
            rec.fecha_captura = False
            if rec.fecha_papeleta:
                rec.fecha_captura = fields.Date.add(rec.fecha_papeleta, days=30)

    @api.depends('fecha_captura', 'fecha_vencimiento_final', 'state')
    def _compute_proximo_a_vencerse(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.proximo_a_vencerse = False
            rec.dias_para_captura = 0
            rec.texto_alerta = False
            if rec.state != 'pendiente':
                continue
            if not rec.fecha_vencimiento_final:
                continue
            # compute difference in days: fecha_captura - today
            try:
                delta = (rec.fecha_vencimiento_final - today).days
            except Exception:
                delta = 0
            rec.dias_para_captura = delta
            # show alert starting 5 days before (delta <= 5). includes negative deltas for overdue
            if delta <= 5:
                rec.proximo_a_vencerse = True
                # build texto_alerta
                if delta > 1:
                    rec.texto_alerta = 'Vence en %s días' % delta
                elif delta == 1:
                    rec.texto_alerta = 'Vence en 1 día'
                elif delta == 0:
                    rec.texto_alerta = 'Vence hoy'
                else:
                    # overdue: delta < 0
                    dias_pasados = abs(delta)
                    if dias_pasados == 1:
                        rec.texto_alerta = 'Se pasó 1 día'
                    else:
                        rec.texto_alerta = 'Se pasó %s días' % dias_pasados
                # badge text is same as texto_alerta
                rec.alert_badge = rec.texto_alerta
            else:
                rec.proximo_a_vencerse = False
                rec.texto_alerta = False
                rec.alert_badge = False

    @api.depends('fecha_captura', 'tiene_prorroga', 'dias_prorroga')
    def _compute_fecha_vencimiento_final(self):
        for rec in self:
            if rec.tiene_prorroga and rec.dias_prorroga and rec.fecha_captura:
                rec.fecha_vencimiento_final = fields.Date.add(rec.fecha_captura, days=rec.dias_prorroga)
            else:
                rec.fecha_vencimiento_final = rec.fecha_captura

    @api.constrains('name')
    def _check_unique_name(self):
        for rec in self:
            if self.search_count([('name', '=', rec.name)]) > 1:
                raise ValidationError('El número de papeleta debe ser único.')

    @api.constrains('vehicle_id')
    def _check_vehicle_active(self):
        for rec in self:
            if rec.vehicle_id and rec.vehicle_id.state_id and hasattr(rec.vehicle_id, 'active') and not rec.vehicle_id.active:
                # fleet.vehicle may not have 'active' field in some setups; check safely
                raise ValidationError('El vehículo debe estar activo en la flota.')

    def unlink(self):
        for rec in self:
            if rec.state == 'pagado':
                raise ValidationError('No se puede eliminar una papeleta en estado Pagado.')
        return super(ADTPapeleta, self).unlink()

    @api.onchange('cantidad_cuotas', 'state', 'monto')
    def _onchange_cantidad_o_estado(self):
        """Genera automáticamente las cuotas cuando el estado es 'fraccionado' y no existen cuotas creadas."""
        for rec in self:
            if rec.state != 'fraccionado' or not rec.cantidad_cuotas:
                # if state not fraccionado, don't show/generate cuotas
                continue
            # Only generate if there are no existing cuotas
            if rec.cuotas_ids:
                continue
            total = float(rec.monto or 0.0)
            n = int(rec.cantidad_cuotas or 0)
            if n <= 0:
                continue
            base = total / n if n else 0.0
            cuotas = []
            for i in range(n):
                cuotas.append((0, 0, {
                    'name': 'Cuota %s' % (i + 1),
                    'amount': base,
                }))
            rec.cuotas_ids = cuotas

    @api.depends('state')
    def _compute_show_fraccionamiento(self):
        for rec in self:
            rec.show_fraccionamiento = rec.state in ('fraccionado', 'pagado')

    def action_mark_pagado(self):
        """Marca la papeleta como pagada. Validaciones:
        - Si ya está en 'pagado' se ignora.
        - Si está en 'fraccionado' y existen cuotas pendientes, lanza error.
        - Si todo OK, setea state='pagado' y fecha_pago hoy.
        """
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state == 'pagado':
                continue
            if rec.state == 'fraccionado':
                pendientes = rec.cuotas_ids.filtered(lambda c: c.state == 'pendiente')
                if pendientes:
                    raise ValidationError('Existen cuotas pendientes. Marque las cuotas como pagadas antes de marcar la papeleta como pagada.')
            rec.write({
                'state': 'pagado',
                'fecha_pago': today,
            })
        return True


class ADTPapeletaCuota(models.Model):
    _name = 'adt.papeleta.cuota'
    _description = 'Cuota de Papeleta'
    _order = 'id'

    name = fields.Char(string='Cuota', required=True)
    papeleta_id = fields.Many2one('adt.papeleta', string='Papeleta', ondelete='cascade', required=True)
    due_date = fields.Date(string='Fecha de Cuota')
    amount = fields.Monetary(string='Monto', currency_field='company_currency_id')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado')
    ], string='Estado', default='pendiente')

    company_currency_id = fields.Many2one('res.currency', related='papeleta_id.company_currency_id', string='Moneda', readonly=True)

    @api.model
    def create(self, vals):
        # ensure default name if missing
        if not vals.get('name') and vals.get('papeleta_id'):
            papeleta = self.env['adt.papeleta'].browse(vals.get('papeleta_id'))
            count = self.search_count([('papeleta_id', '=', papeleta.id)]) + 1
            vals['name'] = 'Cuota %s' % count
        return super(ADTPapeletaCuota, self).create(vals)
