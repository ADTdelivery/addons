# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from ..models.tools import plate_is_ready


class AdtMotoTrackingSincronizarWizard(models.TransientModel):
    """Carga de existentes: incorpora al flujo los vehículos de flota que aún no pasaron por él,
    salvo los que ya tienen placa y dueño."""
    _name = 'adt.moto.tracking.sincronizar.wizard'
    _description = 'Sincronizar vehículos con el tracking'

    etapa_id = fields.Many2one(
        'adt.moto.tracking.etapa', string='Etapa para motos sin dueño', required=True,
        default=lambda self: self.env['adt.moto.tracking']._etapa('almacen'),
        help='Etapa en la que entran las motos sin dueño (no se conoce su historia real). '
             'Las que ya tienen dueño entran en la última etapa.',
    )
    etapa_codigo = fields.Selection(related='etapa_id.codigo')
    taller_id = fields.Many2one('adt.moto.tracking.taller', string='Taller de fibra')
    # Se calculan al abrir (default_get): un compute sin dependencias no se evalúa en el formulario.
    cantidad = fields.Integer(string='Vehículos a incorporar', readonly=True)
    cantidad_con_duenio = fields.Integer(string='Con dueño (entran a la última etapa)', readonly=True)
    cantidad_sin_placa = fields.Integer(string='Sin placa (se les crea trámite)', readonly=True)

    def _candidatos(self):
        vehiculos = self.env['fleet.vehicle'].search([])
        con_tracking = vehiculos._adt_trackings().vehicle_id
        return vehiculos.filtered(lambda v: v not in con_tracking and v._adt_es_existente_pendiente())

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        candidatos = self._candidatos()
        res.update(
            cantidad=len(candidatos),
            cantidad_con_duenio=len(candidatos.filtered('driver_id')),
            cantidad_sin_placa=len(candidatos.filtered(lambda v: not plate_is_ready(v.license_plate))),
        )
        return res

    def action_confirmar(self):
        self.ensure_one()
        trackings = self._candidatos()._adt_incorporar_existentes(
            self.etapa_id, taller=self.taller_id if self.etapa_codigo == 'fibra' else None)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vehículos incorporados al tracking'),
            'res_model': 'adt.moto.tracking',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', trackings.ids)],
            'target': 'current',
        }
