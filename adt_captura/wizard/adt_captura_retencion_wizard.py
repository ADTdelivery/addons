# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from ..models.adt_captura_record import RETENCION_MOTIVOS

import logging

_logger = logging.getLogger(__name__)


class ADTCapturaRetencionWizard(models.TransientModel):
    _name = 'adt.captura.retencion.wizard'
    _description = 'Retener Vehículo'

    captura_id = fields.Many2one('adt.captura.record', string='Captura', required=True)
    retention_reason = fields.Selection(RETENCION_MOTIVOS, string='Motivo', required=True, default='motivo1')
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
        self.captura_id.iniciar_disolucion(self.retention_reason, self.retention_date, self.notes)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
