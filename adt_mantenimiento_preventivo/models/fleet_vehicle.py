# -*- coding: utf-8 -*-
"""
Extiende fleet.vehicle con:
    - los campos de sincronización con Traccar (kilometraje leído, última
      sincronización, id de dispositivo).
    - el helper para resolver el "cliente" (res.partner) a notificar, que es
      el dato que permite hacer match con mobile.fcm.device (ver sección 2.1
      de la propuesta: "propietario/conductor" del vehículo).

Flujo de match pedido explícitamente: placa (Traccar) → vehículo (Flota) →
cliente del contrato comercial vigente (adt.comercial.cuentas) → res.partner
→ dispositivos FCM de ese cliente (mobile.fcm.device).
"""
from odoo import fields, models


class FleetVehicleMantenimientoPreventivo(models.Model):
    _inherit = 'fleet.vehicle'

    traccar_device_id = fields.Integer(
        string='Traccar Device ID',
        help='ID del dispositivo en Traccar, cacheado tras el último match por placa.',
    )
    traccar_km_actual = fields.Float(
        string='Km actual (Traccar)', digits=(10, 1),
        help='Último kilometraje acumulado leído desde Traccar (attributes.totalDistance).',
    )
    traccar_ultima_sincronizacion = fields.Datetime(string='Última sincronización Traccar')

    mantenimiento_rule_state_ids = fields.One2many(
        'adt.mantenimiento.vehicle.rule.state', 'vehicle_id', string='Estados de reglas de mantenimiento',
    )
    mantenimiento_campana_ids = fields.One2many(
        'adt.mantenimiento.campana', 'vehicle_id', string='Campañas de mantenimiento',
    )
    mantenimiento_campana_count = fields.Integer(
        string='N° Campañas', compute='_compute_mantenimiento_campana_count',
    )
    mantenimiento_orden_atencion_ids = fields.One2many(
        'adt.mantenimiento.orden.atencion', 'vehicle_id', string='Órdenes de atención',
    )

    def _compute_mantenimiento_campana_count(self):
        for rec in self:
            rec.mantenimiento_campana_count = len(rec.mantenimiento_campana_ids)

    def _adt_mant_get_partner(self):
        """
        Resuelve el cliente (res.partner) a quien notificar para este vehículo.

        Orden de búsqueda:
            1. Contrato comercial vigente (adt.comercial.cuentas) del vehículo
               → partner_id (es el dato de negocio real: el cliente que
               compró/financia el vehículo).
            2. driver_id estándar de fleet.vehicle, como respaldo.
        """
        self.ensure_one()
        Cuenta = self.env['adt.comercial.cuentas'].sudo()
        cuenta = Cuenta.search([
            ('vehiculo_id', '=', self.id), ('state', 'in', ('en_curso', 'aprobado')),
        ], limit=1, order='id desc')
        if not cuenta:
            cuenta = Cuenta.search([('vehiculo_id', '=', self.id)], limit=1, order='id desc')
        if cuenta and cuenta.partner_id:
            return cuenta.partner_id
        return self.driver_id or self.env['res.partner']

    def action_ver_campanas_mantenimiento(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Campañas de mantenimiento',
            'res_model': 'adt.mantenimiento.campana',
            'view_mode': 'tree,form',
            'domain': [('vehicle_id', '=', self.id)],
        }
