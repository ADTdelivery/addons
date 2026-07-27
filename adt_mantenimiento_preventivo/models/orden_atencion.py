# -*- coding: utf-8 -*-
"""
Confirmación de que un mantenimiento pendiente ya fue realizado.

Ver propuesta-mantenimiento-preventivo-traccar.md, sección 9 ("Diseño futuro:
confirmación de mantenimiento atendido") — esta es esa integración, ahora
implementada.

Al registrar una Orden de Atención para (vehículo, regla):
    - si hay una campaña ACTIVA para ese (vehículo, regla), se cancela
      (adt.mantenimiento.campana.action_cancelar ya deja el
      vehicle_rule_state en 'completada_por_usuario' con atendida_en).
    - si no hay campaña activa (ej. la campaña ya terminó sus días de envío
      pero el mantenimiento seguía sin confirmarse), se actualiza el
      vehicle_rule_state directamente, sin necesitar una campaña de por
      medio.

El "origen" (dónde se hizo el mantenimiento: ADT Taller, Taller TVS, Otro
Taller, etc.) es configurable desde adt.mantenimiento.origen.atencion, no
un Selection fijo — se puede ampliar sin tocar código.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AdtMantenimientoOrigenAtencion(models.Model):
    _name = 'adt.mantenimiento.origen.atencion'
    _description = 'Origen de Atención de Mantenimiento (configurable)'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre', required=True,
        help='Ej: ADT Taller, Taller TVS, Otro Taller.',
    )
    code = fields.Char(
        string='Código interno',
        help='Identificador técnico opcional para integraciones (ej. ADT_TALLER). '
             'No se usa en la lógica de negocio.',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        ('origen_atencion_name_uniq', 'unique(name)',
         'Ya existe un origen de atención con ese nombre.'),
    ]


class AdtMantenimientoOrdenAtencion(models.Model):
    _name = 'adt.mantenimiento.orden.atencion'
    _description = 'Orden de Atención de Mantenimiento (confirmación de mantenimiento realizado)'
    _order = 'fecha_atencion desc, id desc'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo', required=True, ondelete='cascade', index=True,
    )
    regla_id = fields.Many2one(
        'adt.mantenimiento.regla', string='Regla', required=True, ondelete='cascade', index=True,
    )
    umbral_id = fields.Many2one('adt.mantenimiento.umbral', string='Umbral atendido')
    campana_id = fields.Many2one(
        'adt.mantenimiento.campana', string='Campaña relacionada',
        help='Se completa automáticamente si había una campaña activa para este '
             'vehículo y regla al momento de registrar la atención.',
    )
    origen_id = fields.Many2one(
        'adt.mantenimiento.origen.atencion', string='Origen de atención', required=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Cliente', compute='_compute_partner_id', store=True,
    )
    fecha_atencion = fields.Datetime(string='Fecha de atención', required=True, default=fields.Datetime.now)
    km_atencion = fields.Float(string='Km al atender', digits=(10, 1))
    observaciones = fields.Text(string='Observaciones')
    active = fields.Boolean(default=True)

    @api.depends('vehicle_id')
    def _compute_partner_id(self):
        for rec in self:
            rec.partner_id = rec.vehicle_id._adt_mant_get_partner() if rec.vehicle_id else False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._aplicar_atencion()
        return records

    def _aplicar_atencion(self):
        """Cancela la campaña activa (si existe) o actualiza el estado directamente."""
        self.ensure_one()
        Campana = self.env['adt.mantenimiento.campana'].sudo()
        campanas_activas = Campana.search([
            ('vehicle_id', '=', self.vehicle_id.id),
            ('regla_id', '=', self.regla_id.id),
            ('estado', '=', 'activa'),
        ])
        if campanas_activas:
            if not self.campana_id:
                self.campana_id = campanas_activas[0].id
            campanas_activas.action_cancelar()
        else:
            state = self.env['adt.mantenimiento.vehicle.rule.state'].sudo().search([
                ('vehicle_id', '=', self.vehicle_id.id), ('regla_id', '=', self.regla_id.id),
            ], limit=1)
            if state:
                state.write({'estado': 'completada_por_usuario', 'atendida_en': self.fecha_atencion})

        _logger.info(
            '[ADT Mantenimiento] Orden de atención registrada: vehículo=%s regla=%s origen=%s '
            '(campaña cancelada=%s)',
            self.vehicle_id.license_plate, self.regla_id.name, self.origen_id.name,
            bool(campanas_activas),
        )

    @api.model
    def registrar_atencion(self, vehicle_id, regla_id, origen_id, observaciones=None,
                            fecha_atencion=None, km_atencion=None):
        """
        Punto de entrada único para registrar que un mantenimiento pendiente
        ya se realizó (usado tanto por el controlador REST de la app como
        desde el propio backend).
        """
        vals = {
            'vehicle_id': vehicle_id,
            'regla_id': regla_id,
            'origen_id': origen_id,
            'observaciones': observaciones or '',
        }
        if fecha_atencion:
            vals['fecha_atencion'] = fecha_atencion
        if km_atencion is not None:
            vals['km_atencion'] = km_atencion
        return self.create(vals)
