# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from odoo.addons.adt_papeletas.models.papeleta_sat import _fecha_lima

from .captura_sat import CON_ORDEN, SIN_ORDEN


class FleetVehicleCapturaSat(models.Model):
    _inherit = 'fleet.vehicle'

    captura_sat_ids = fields.One2many('adt.captura.sat', 'vehicle_id', string='Órdenes de captura SAT')
    captura_sat_estado = fields.Selection([
        ('sin_consultar', 'Sin consultar'),
        (SIN_ORDEN, 'Sin orden de captura'),
        (CON_ORDEN, 'Con orden de captura'),
    ], string='Captura SAT', default='sin_consultar', readonly=True, index=True, copy=False,
        help='Resultado de la última consulta válida en el SAT Lima.')
    captura_sat_ultima_consulta = fields.Datetime(string='Última consulta de captura SAT', readonly=True, copy=False)
    captura_sat_count = fields.Integer(string='Órdenes SAT vigentes', compute='_compute_captura_sat', store=True)
    captura_sat_monto = fields.Float(string='Monto en captura SAT', compute='_compute_captura_sat', store=True)

    @api.depends('captura_sat_ids.vigente', 'captura_sat_ids.monto')
    def _compute_captura_sat(self):
        for rec in self:
            vigentes = rec.captura_sat_ids.filtered('vigente')
            rec.captura_sat_count = len(vigentes)
            rec.captura_sat_monto = sum(vigentes.mapped('monto'))

    def _captura_sat_registrar(self, tiene, cuando, consulta):
        """Actualiza el estado del vehículo con una consulta válida. False si es un reenvío antiguo."""
        self.ensure_one()
        if self.captura_sat_ultima_consulta and self.captura_sat_ultima_consulta > cuando:
            return False
        nuevo = CON_ORDEN if tiene else SIN_ORDEN
        previo = self.captura_sat_estado
        self.sudo().write({'captura_sat_estado': nuevo, 'captura_sat_ultima_consulta': cuando})
        if previo == CON_ORDEN and nuevo == SIN_ORDEN:
            self.message_post(body=_('El SAT Lima ya no muestra orden de captura para %s (consulta del %s).')
                              % (consulta.placa, _fecha_lima(cuando).strftime('%d/%m/%Y')))
        return True

    def action_ver_capturas_sat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Órdenes de captura SAT'),
            'res_model': 'adt.captura.sat',
            'view_mode': 'tree,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'search_default_vigentes': 1},
        }

    def action_consultar_capturas_sat(self):
        return self.env['adt.captura.sat.ejecucion'].with_context(active_ids=self.ids).action_desde_vehiculos()
