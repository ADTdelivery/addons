# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.exceptions import UserError

from .tools import CODIGOS_ETAPA


class AdtMotoTrackingEtapa(models.Model):
    """Las 4 etapas logísticas. Son fijas: solo se puede cambiar nombre, descripción y SLA.

    La lógica siempre usa `codigo`, nunca el nombre.
    """
    _name = 'adt.moto.tracking.etapa'
    _description = 'Etapa logística de tracking de moto'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True, translate=True)
    codigo = fields.Selection(CODIGOS_ETAPA, string='Código', required=True, readonly=True)
    sequence = fields.Integer(string='Secuencia', readonly=True)
    sla_horas = fields.Float(
        string='SLA (horas)',
        help='Tiempo objetivo de permanencia en la etapa. Si se supera, la moto se marca como demorada. '
             '0 = sin control.',
    )
    descripcion = fields.Text(string='Descripción')
    fold = fields.Boolean(string='Plegada en kanban')

    _sql_constraints = [
        ('codigo_unique', 'unique(codigo)', 'Ya existe una etapa con ese código.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_('Las etapas del tracking son fijas: solo se puede cambiar su nombre.'))
        return super().create(vals_list)

    def unlink(self):
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            raise UserError(_('Las etapas del tracking son fijas y no se pueden eliminar.'))
        return super().unlink()
