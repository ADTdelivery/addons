# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

import logging

_logger = logging.getLogger(__name__)


class ADTCapturaPagoWizard(models.TransientModel):
    _name = 'adt.captura.pago.wizard'
    _description = 'Registrar Pago de Intervención'

    captura_id = fields.Many2one('adt.captura.record', string='Captura', required=True)
    pagar_monto = fields.Boolean(string='¿Pagar monto?', default=True)
    monto = fields.Float(string='Monto a Pagar', required=True)
    motivo_no_pago = fields.Text(string='Motivo de no pago', help='Especifique el motivo por el cual no se realiza el pago', readonly=False)
    estado_pago = fields.Selection([
        ('pagado', 'Pagado'),
        ('no_pagado', 'No Pagado')
    ], string='Estado de Pago', default='no_pagado', readonly=True)

    voucher_file = fields.Binary(string='Voucher', required=True, attachment=True)
    voucher_filename = fields.Char(string='Nombre Archivo')
    voucher_number = fields.Char(string='Número de Voucher', required=True)
    payment_date = fields.Date(string='Fecha de Pago', required=True, default=fields.Date.today)

    @api.constrains('monto')
    def _check_monto(self):
        for wizard in self:
            if wizard.monto <= 0:
                raise ValidationError('El monto debe ser mayor a cero.')

    @api.constrains('payment_date')
    def _check_payment_date(self):
        for wizard in self:
            if wizard.payment_date > fields.Date.today():
                raise ValidationError('La fecha de pago no puede ser futura.')

    @api.onchange('pagar_monto')
    def _onchange_pagar_monto(self):
        if not self.pagar_monto:
            self.monto = 0.0
            self.voucher_file = 'default_file_path'
            self.voucher_filename = 'default_filename'
            self.voucher_number = 'default_number'
        self.motivo_no_pago = False if self.pagar_monto else self.motivo_no_pago

    def action_registrar(self):
        """Registra el pago en la captura"""
        self.ensure_one()

        if not self.voucher_file:
            raise ValidationError('Debe adjuntar el voucher de pago.')

        if not self.pagar_monto and not self.motivo_no_pago:
            raise UserError(_('Debe especificar un motivo para no realizar el pago.'))

        # Actualizar la captura
        self.captura_id.write({
            'payment_state': 'pagado',
            'voucher_file': self.voucher_file,
            'voucher_filename': self.voucher_filename,
            'voucher_number': self.voucher_number,
            'payment_date': self.payment_date,
            'intervention_fee': self.monto,
            'motivo_no_pago': self.motivo_no_pago,
            'pagar_monto': self.pagar_monto,
        })

        # Agregar nota en el chatter
        mensaje = f"""
        <p><strong>Pago Registrado</strong></p>
        <ul>
            <li>Monto: S/ {self.monto}</li>
            <li>N° Voucher: {self.voucher_number}</li>
            <li>Fecha: {self.payment_date}</li>
        </ul>
        """

        self.captura_id.message_post(body=mensaje, subject='Pago Registrado')

        _logger.info(f"Pago registrado para captura {self.captura_id.name} - Monto: S/ {self.monto}")

        # Cerrar el wizard y recargar la vista
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
