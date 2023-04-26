from datetime import timedelta, datetime, date
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, RedirectWarning, UserError
import xmlrpc.client
from odoo.http import request

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

    real_date = fields.Char(string="Fecha de pago")

    numero_operacion = fields.Char(string="# Operación")

    periodicidad = fields.Char(string="Periodo")

    @api.model
    def _change_real_date(self):
        for data in self:
            print(str(data.cuota_ids))
            for cuota in data.cuota_ids:
                account_payment = request.env['account.payment'].search([('cuota_id', '=', cuota.id)]).read([
                    'move_id',
                ])
                print(account_payment)
                if len(account_payment) > 0:
                    account_move = request.env['account.move'].search(
                        [('id', '=', account_payment[0]['move_id'][0])]).read([
                        'date',
                        'ref'
                    ])
                    cuota.real_date = str(account_move[0]['date'])
                    cuota.numero_operacion = str(account_move[0]['ref'])

                else:
                    cuota.real_date = ""
                    cuota.numero_operacion = ""

    @api.depends('observacion_ids')
    def _compute_resumen_observaciones(self):
        for record in self:
            html = "<ul>"
            for obs in record.observacion_ids:
                html += "<li>" + obs.comentario + "</li>"
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
                elif (sum(record.payment_ids.mapped('amount')) > 0) and (
                        sum(record.payment_ids.mapped('amount')) < record.monto):
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

    @api.model
    def prueba_data_2(self):
        print("Row data")

    def action_delete_payment(self):
        return {
            'name': _('Delete Payment'),
            'res_model': 'adt.warning.message',
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


class ADTComercialWarningMessage(models.TransientModel):
    _name = "adt.warning.message"
    _description = "ADT Warning messages"

    message = fields.Text(string="Esta seguro que desea eliminar el pago?", readonly=True, store=True)
    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")

    def action_delete_payment(self):
        data = self.env['account.payment'].search([('cuota_id', '=', self.cuota_id.id)])
        data.unlink()


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
            [('ref', '=', self.communication)]).read(['cuota_id'])

        if len(payment_exist) > 0:
            cuota = self.env['adt.comercial.cuotas'].search(
                [('id', '=', payment_exist[0]['cuota_id'][0] )]).read(['cuenta_id'])
            raise UserError(
                'Ya existe un pago con el mismo número de operación. \n'
                '\n'
                'Usuario : '+ cuota[0]['cuenta_id'][1])

        logging.info("Data Account Payment")
        logging.info(str(self))

        data = {
            'payment_type': self.payment_type,
            'journal_id': self.journal_id.id,
            'cuota_id': self.cuota_id.id,
            'ref': self.communication,
            'amount': self.amount,
            'date': self.payment_date,
            'partner_id': self.cuota_id.cuenta_id.partner_id.id
        }

        logging.info(str(data))

        try:
            logging.info(" data 1 " + str(self._name))
            logging.info("print array data")

            payment = self.env['account.payment'].create(data)
            payment.action_post()

        except Exception as e:
            logging.info(str(e))
            logging.info(
                "failed excep"
            )


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

