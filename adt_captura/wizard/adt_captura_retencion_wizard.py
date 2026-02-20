# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ADTCapturaRetencionWizard(models.TransientModel):
    _name = 'adt.captura.retencion.wizard'
    _description = 'Retener Vehículo'

    captura_id = fields.Many2one('adt.captura.record', string='Captura', required=True)
    retention_reason = fields.Text(string='Motivo de Retención', required=True,
                                   placeholder='Especifique el motivo de la retención del vehículo...')
    retention_date = fields.Date(string='Fecha de Retención', required=True,
                                 default=fields.Date.today)
    notes = fields.Text(string='Observaciones Adicionales')

    @api.constrains('retention_reason')
    def _check_retention_reason(self):
        for wizard in self:
            if not wizard.retention_reason or len(wizard.retention_reason.strip()) < 10:
                raise ValidationError('El motivo de retención debe tener al menos 10 caracteres.')

    @api.constrains('retention_date')
    def _check_retention_date(self):
        for wizard in self:
            if wizard.retention_date > fields.Date.today():
                raise ValidationError('La fecha de retención no puede ser futura.')

    def action_retener(self):
        """Retiene el vehículo"""
        self.ensure_one()

        # Actualizar la captura
        self.captura_id.write({
            'state': 'disolucion_contrato',
            'retention_reason': self.retention_reason,
            'retention_date': self.retention_date,
            'supervisor_id': self.env.user.id,
        })

        # Agregar nota en el chatter
        mensaje = f"""
        <p><strong>Vehículo Retenido</strong></p>
        <p><strong>Motivo:</strong> {self.retention_reason}</p>
        <p><strong>Fecha:</strong> {self.retention_date}</p>
        <p><strong>Supervisor:</strong> {self.env.user.name}</p>
        """
        if self.notes:
            mensaje += f"<p><strong>Observaciones:</strong> {self.notes}</p>"

        self.captura_id.message_post(body=mensaje, subject='Vehículo Retenido')

        _logger.info(f"Vehículo disolución contrato - Captura: {self.captura_id.name} - Supervisor: {self.env.user.name}")

        # Cerrar el wizard y recargar la vista
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
