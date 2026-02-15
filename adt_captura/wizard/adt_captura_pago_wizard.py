# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ADTCapturaPagoWizard(models.TransientModel):
    _name = 'adt.captura.pago.wizard'
    _description = 'Registrar Pago de Intervención'

    captura_id = fields.Many2one('adt.captura.record', string='Captura', required=True)
    monto = fields.Float(string='Monto (S/)', required=True)
    voucher_file = fields.Binary(string='Voucher', required=True, attachment=True)
    voucher_filename = fields.Char(string='Nombre Archivo')
    voucher_number = fields.Char(string='Número de Voucher', required=True)
    payment_date = fields.Date(string='Fecha de Pago', required=True, default=fields.Date.today)
    notes = fields.Text(string='Observaciones')

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

    def action_registrar(self):
        """Registra el pago en la captura"""
        self.ensure_one()

        if not self.voucher_file:
            raise ValidationError('Debe adjuntar el voucher de pago.')

        # Actualizar la captura
        self.captura_id.write({
            'payment_state': 'pagado',
            'voucher_file': self.voucher_file,
            'voucher_filename': self.voucher_filename,
            'voucher_number': self.voucher_number,
            'payment_date': self.payment_date,
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
        if self.notes:
            mensaje += f"<p><strong>Observaciones:</strong> {self.notes}</p>"

        self.captura_id.message_post(body=mensaje, subject='Pago Registrado')

        _logger.info(f"Pago registrado para captura {self.captura_id.name} - Monto: S/ {self.monto}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Pago Registrado',
                'message': 'El pago ha sido registrado correctamente. Ahora puede liberar el vehículo.',
                'type': 'success',
                'sticky': False,
            }
        }
