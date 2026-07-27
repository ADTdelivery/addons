# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdtMantenimientoVehicleRuleState(models.Model):
    """
    Estado de una Regla de Mantenimiento por Vehículo.

    Guarda, por cada par (vehículo, regla), cuál fue el último umbral ya
    disparado -por orden, no por km, para no romperse si se insertan nuevos
    umbrales- de forma de no reprocesar el mismo umbral dos veces.

    Ver propuesta-mantenimiento-preventivo-traccar.md, secciones 2.3 y 4.
    """
    _name = 'adt.mantenimiento.vehicle.rule.state'
    _description = 'Estado de Regla de Mantenimiento por Vehículo'
    _rec_name = 'vehicle_id'
    _order = 'id desc'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo', required=True, ondelete='cascade', index=True,
    )
    regla_id = fields.Many2one(
        'adt.mantenimiento.regla', string='Regla', required=True, ondelete='cascade', index=True,
    )
    ultimo_umbral_orden = fields.Integer(
        string='Último umbral disparado (orden)', default=0,
    )
    estado = fields.Selection([
        ('pendiente', 'Pendiente de evaluar'),
        ('campana_activa', 'Campaña activa'),
        ('completada_por_usuario', 'Completada por usuario'),
        ('campana_finalizada', 'Campaña finalizada'),
    ], string='Estado', default='pendiente', required=True)
    fecha_disparo = fields.Datetime(string='Fecha de disparo')
    atendida_en = fields.Datetime(
        string='Atendida en',
        help='Fecha en que se confirmó que el mantenimiento fue realizado '
             '(ver adt.mantenimiento.orden.atencion).',
    )

    _sql_constraints = [
        ('vehicle_regla_uniq', 'unique(vehicle_id, regla_id)',
         'Ya existe un estado registrado para este vehículo y esta regla.'),
    ]

    @api.model
    def _get_or_create(self, vehicle_id, regla_id):
        state = self.search([
            ('vehicle_id', '=', vehicle_id), ('regla_id', '=', regla_id),
        ], limit=1)
        if not state:
            state = self.create({'vehicle_id': vehicle_id, 'regla_id': regla_id})
        return state

    # ─────────────────────────────────────────────────────────────
    # Servicio de "mantenimientos pendientes" (para la app)
    # ─────────────────────────────────────────────────────────────
    @api.model
    def get_pendientes_vehiculo(self, vehicle_id):
        """
        Lista los mantenimientos pendientes de confirmar para un vehículo:
        cualquier regla cuyo último umbral disparado todavía no fue marcado
        como atendido, esté o no la campaña de notificaciones todavía activa
        (una campaña puede terminar sus días de envío sin que el
        mantenimiento se haya confirmado como realizado).

        Devuelve una lista de dicts, uno por regla pendiente.
        """
        states = self.search([
            ('vehicle_id', '=', vehicle_id),
            ('estado', 'in', ('campana_activa', 'campana_finalizada')),
        ])
        return [state._to_pendiente_dict() for state in states]

    def _to_pendiente_dict(self):
        self.ensure_one()
        regla = self.regla_id
        umbral = regla.umbral_ids.filtered(lambda u: u.orden == self.ultimo_umbral_orden)[:1]
        campana_activa = self.env['adt.mantenimiento.campana'].search([
            ('vehicle_id', '=', self.vehicle_id.id),
            ('regla_id', '=', regla.id),
            ('estado', '=', 'activa'),
        ], limit=1)
        return {
            'vehicle_rule_state_id': self.id,
            'vehicle_id': self.vehicle_id.id,
            'placa': self.vehicle_id.license_plate,
            'regla_id': regla.id,
            'regla_nombre': regla.name,
            'umbral_orden': self.ultimo_umbral_orden,
            'umbral_km': umbral.km_umbral if umbral else None,
            'fecha_disparo': self.fecha_disparo.isoformat() if self.fecha_disparo else None,
            'estado': self.estado,
            'campana_id': campana_activa.id if campana_activa else None,
            'es_oferta': regla.es_oferta,
            'oferta_titulo': regla.oferta_titulo if regla.es_oferta else None,
            'oferta_descripcion': regla.oferta_descripcion if regla.es_oferta else None,
            'oferta_precio': regla.oferta_precio if regla.es_oferta else None,
            'oferta_moneda': regla.oferta_moneda_id.name if regla.es_oferta else None,
            'oferta_dias_duracion': regla.oferta_dias_duracion if regla.es_oferta else None,
            'oferta_wsp_link': regla.oferta_wsp_link if regla.es_oferta else None,
            'oferta_imagenes_urls': regla._get_oferta_imagen_urls() if regla.es_oferta else [],
        }
