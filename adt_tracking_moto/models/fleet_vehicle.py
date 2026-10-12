# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .tools import plate_is_ready


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    adt_tracking_id = fields.Many2one(
        'adt.moto.tracking', string='Tracking', compute='_compute_adt_tracking_id',
        groups='adt_tracking_moto.group_tracking_user',
    )

    def _adt_trackings(self):
        return self.env['adt.moto.tracking'].sudo().search([('vehicle_id', 'in', self.ids)])

    def _compute_adt_tracking_id(self):
        por_vehiculo = {t.vehicle_id.id: t.id for t in self._adt_trackings()}
        for vehicle in self:
            vehicle.adt_tracking_id = por_vehiculo.get(vehicle.id, False)

    def _adt_aplica_tracking(self):
        """Criterio de ingreso: moto activa, sin dueño y sin placa real."""
        self.ensure_one()
        return self.active and not self.driver_id and not plate_is_ready(self.license_plate)

    def _adt_crear_tracking_si_aplica(self, etapa=None, taller=None):
        con_tracking = self._adt_trackings().vehicle_id
        candidatos = self.filtered(lambda v: v not in con_tracking and v._adt_aplica_tracking())
        extra = {}
        if etapa:
            extra['etapa_id'] = etapa.id
        if taller:
            extra['taller_fibra_id'] = taller.id
        return self.env['adt.moto.tracking'].sudo().create(
            [dict(extra, vehicle_id=v.id) for v in candidatos])

    def _adt_es_existente_pendiente(self):
        """Carga de existentes: todo vehículo activo, salvo los que ya tienen placa y dueño."""
        self.ensure_one()
        return self.active and not (plate_is_ready(self.license_plate) and self.driver_id)

    def _adt_incorporar_existentes(self, etapa, taller=None):
        """Incorpora al flujo los vehículos que ya estaban en flota.

        Sin placa → trámite Pendiente. Con dueño → etapa "listo" (ya pasó la logística);
        sin dueño → la etapa elegida.
        """
        con_tracking = self._adt_trackings().vehicle_id
        candidatos = self.filtered(lambda v: v not in con_tracking and v._adt_es_existente_pendiente())
        candidatos._adt_crear_tramite_placa(solo_facturados=False)
        Tracking = self.env['adt.moto.tracking'].sudo()
        listo = Tracking._etapa('listo')
        vals_list = []
        for vehicle in candidatos:
            vals = {'vehicle_id': vehicle.id, 'etapa_id': etapa.id}
            if vehicle.driver_id:
                vals['etapa_id'] = listo.id
            elif etapa.codigo == 'fibra':
                vals['taller_fibra_id'] = taller.id
            vals_list.append(vals)
        return Tracking.create(vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        vehicles = super().create(vals_list)
        vehicles._adt_crear_tracking_si_aplica()
        return vehicles

    def write(self, vals):
        if 'driver_id' in vals:
            drivers_previos = {v.id: v.driver_id for v in self}
        res = super().write(vals)
        if not {'driver_id', 'license_plate', 'fecha_entrega'} & vals.keys():
            return res
        trackings = self._adt_trackings()
        if not trackings:
            return res
        if 'driver_id' in vals:
            cambiados = self.filtered(lambda v: v.driver_id != drivers_previos[v.id])
            trackings.filtered(lambda t: t.vehicle_id in cambiados)._registrar_asignacion()
        if 'license_plate' in vals:
            trackings._sync_estado_placa()
        if 'fecha_entrega' in vals:
            trackings._registrar_entrega()
        return res

    @api.onchange('driver_id')
    def _onchange_driver_id_adt_tracking(self):
        """Solo advierte: se permite asignar una moto que aún no terminó la logística."""
        if not self.driver_id or not self._origin:
            return
        tracking = self._origin._adt_trackings()[:1]
        if tracking and tracking.etapa_codigo != 'listo':
            return {'warning': {
                'title': _('La moto aún no está lista'),
                'message': _(
                    'La moto está en la etapa «%(etapa)s» del tracking %(ref)s. Puede asignarla igual, '
                    'pero quedará registrado que se asignó antes de estar lista.',
                    etapa=tracking.etapa_id.name, ref=tracking.name),
            }}

    def action_ver_adt_tracking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tracking'),
            'res_model': 'adt.moto.tracking',
            'res_id': self.adt_tracking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
