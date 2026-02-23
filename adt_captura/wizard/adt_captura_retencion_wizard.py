# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ADTCapturaRetencionWizard(models.TransientModel):
    _name = 'adt.captura.retencion.wizard'
    _description = 'Retener Vehículo'

    captura_id = fields.Many2one('adt.captura.record', string='Captura', required=True)
    retention_reason = fields.Selection([
        ('motivo1', 'El cliente no se comunicó por más de 3 días'),
        ('motivo2', 'El cliente decidio no continuar pagando el credito'),
        ('otro', 'Otro')
    ], string='Motivo', required=True, default='motivo1')
    retention_date = fields.Date(string='Fecha', required=True,
                                 default=fields.Date.today)
    notes = fields.Text(string='Observaciones Adicionales', readonly=True)

    @api.constrains('retention_reason')
    def _check_retention_reason(self):
        for wizard in self:
            if wizard.retention_reason == 'otro' and (not wizard.notes or len(wizard.notes.strip()) < 10):
                raise ValidationError('Las observaciones deben tener al menos 10 caracteres cuando el motivo es "Otro".')

    @api.constrains('retention_date')
    def _check_retention_date(self):
        for wizard in self:
            if wizard.retention_date > fields.Date.today():
                raise ValidationError('La fecha de retención no puede ser futura.')

    @api.onchange('retention_reason')
    def _onchange_retention_reason(self):
        if self.retention_reason == 'otro':
            self.notes = False  # Clear notes when switching to 'otro'
            self.update({'notes': False})
            self.env.context = dict(self.env.context, force_edit=True)
        else:
            self.notes = False  # Clear notes for other options
            self.env.context = dict(self.env.context, force_edit=False)

    def action_retener(self):
        """Retiene el vehículo"""
        self.ensure_one()

        # Actualizar la captura
        self.captura_id.write({
            'state': 'disolucion_contrato',
            'retention_reason': self.retention_reason,
            'retention_date': self.retention_date,
            'notes': self.notes,
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
