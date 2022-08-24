from datetime import timedelta, datetime, date
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, RedirectWarning, UserError

import logging
_logger = logging.getLogger(__name__)


class ADTComercialCuotas(models.Model):
    _name = "adt.comercial.cuotas"
    _description = "ADT Módulo comercial - Cuotas"

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency",
                                  string="Company Currency", readonly=True, related="company_id.currency_id")

    cuenta_id = fields.Many2one("adt.comercial.cuentas", string="Cuenta id")
    name = fields.Char(string="# Cuota")

    # fecha_cierre = fields.Date(
    #     string="Fecha de cierre", default=fields.Date.today)
    monto = fields.Monetary(string="Monto de cuota")

    fecha_cronograma = fields.Date(
        string="Fecha de cronograma", default=fields.Date.today)
    fecha_compromiso = fields.Date(string="Fecha compromiso")

    resumen_pagos = fields.Html("Resumen de pagos")
    resumen_observaciones = fields.Html(
        "Resumen observaciones", compute="_compute_resumen_observaciones", store=True)

    @api.depends('observacion_ids')
    def _compute_resumen_observaciones(self):
        for record in self:
            html = "<ul>"
            for obs in record.observacion_ids:
                html += "<li>"+obs.comentario+"</li>"
            html += "</ul>"
            record.resumen_observaciones = html

    payment_ids = fields.One2many(
        "account.payment", "cuota_id", string="Pagos")
    type = fields.Selection(
        [('cuota', 'Cuota'), ('mora', 'Mora')], default='cuota')

    @api.depends('payment_ids')
    def _compute_saldo(self):
        for record in self:
            record.saldo = record.monto - \
                sum(record.payment_ids.mapped('amount'))

    @api.depends('payment_ids', 'cuenta_id.state')
    def _compute_state(self):
        for record in self:
            if len(record.payment_ids) > 0:
                if record.monto == sum(record.payment_ids.mapped('amount')):
                    record.state = 'pagado'
                elif (sum(record.payment_ids.mapped('amount')) > 0) and (sum(record.payment_ids.mapped('amount')) < record.monto):
                    record.state = 'a_cuenta'
            else:
                if record.fecha_cronograma < date.today():
                    record.state = 'retrasado'
                elif record.cuenta_id.state == 'cancelado':
                    record.state = 'anulada'
                else:
                    record.state = 'pendiente'

    state = fields.Selection([("pendiente", "Pendiente"), ("a_cuenta", "A cuenta"), ("retrasado", "Retrasado"), (
        "pagado", "Pagado"), ("anulada", "Anulada")], string="Estado", compute="_compute_state", store=True)
    saldo = fields.Monetary(
        string="Saldo", compute="_compute_saldo", store=True)

    observacion_ids = fields.One2many(
        "adt.comercial.observaciones", "cuota_id", string="Observaciones")

    def action_register_payment(self):
        return {
            'name': _('Register Payment'),
            'res_model': 'adt.register.payment',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuotas',
                'active_ids': self.ids,
                'default_amount': self.saldo,
                'default_communication': self.name,
                'default_cuota_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def registrar_observacion(self):
        return {
            'name': 'Registrar observaciones',
            'res_model': 'adt.registrar.observacion',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuotas',
                'default_cuota_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }


class ADTComercialRegisterPayment(models.TransientModel):
    _name = "adt.register.payment"
    _description = "ADT Registro de pagos"

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency",
                                  string="Company Currency", readonly=True, related="company_id.currency_id")
    payment_date = fields.Date(
        string="Payment Date", required=True, default=fields.Date.context_today)
    amount = fields.Monetary(currency_field='currency_id', readonly=False)
    communication = fields.Char(string="Memo", readonly=False)
    journal_id = fields.Many2one('account.journal', store=True, readonly=False,
                                 compute='_compute_journal_id',
                                 domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]")
    payment_type = fields.Selection(
        [('outbound', 'Send Money'), ('inbound', 'Receive Money'), ], string='Payment Type', default='inbound')

    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")

    @api.depends('company_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', wizard.company_id.id),
            ], limit=1)

    def action_create_payments(self):
        payment_exist = self.env['account.payment'].search(
            [('ref', '=', self.communication)])

        if len(payment_exist) > 0:
            raise UserError(
                'Ya existe un pago con el mismo número de operación.')

        payment = self.env['account.payment'].create({
            'payment_type': self.payment_type,
            'journal_id': self.journal_id.id,
            'cuota_id': self.cuota_id.id,
            'ref': self.communication,
            'amount': self.amount,
            'date': self.payment_date,
            'partner_id': self.cuota_id.cuenta_id.partner_id.id
        })

        payment.action_post()


class ADTRegistrarObservacion(models.TransientModel):
    _name = "adt.registrar.observacion"
    _description = "ADT Registro de observaciones"

    fecha = fields.Date(string="Fecha", default=fields.Date.today)
    comentario = fields.Text(string='Comentario')
    attachment_ids = fields.Many2many("ir.attachment", string="Adjuntos")

    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")

    def action_create_observacion(self):
        observacion = self.env['adt.comercial.observaciones'].create({
            'cuota_id': self.cuota_id.id,
            'comentario': self.comentario,
            'fecha': self.fecha,
            'attachment_ids': self.attachment_ids,
        })