# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdtMantenimientoVehicleReportStatus(models.Model):
    """
    Estado de reporte GPS del vehículo: permite alertar cuando un vehículo
    deja de reportar posición/kilometraje por N días (configurable).

    Ver propuesta-mantenimiento-preventivo-traccar.md, secciones 2.6 y 4.1.
    Es una alerta operativa para el administrador de flota (se publica en el
    chatter del vehículo), distinta de las campañas de mantenimiento del
    conductor.
    """
    _name = 'adt.mantenimiento.vehicle.report.status'
    _description = 'Estado de Reporte GPS por Vehículo'
    _rec_name = 'vehicle_id'
    _order = 'ultima_fecha_reporte desc'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo', required=True, ondelete='cascade',
        index=True,
    )
    ultima_fecha_reporte = fields.Datetime(string='Última fecha de reporte')
    dias_sin_reportar = fields.Integer(
        string='Días sin reportar', compute='_compute_dias_sin_reportar', store=True,
    )
    alerta_sin_reporte_enviada = fields.Boolean(
        string='Alerta enviada', default=False,
        help='Evita reenviar la misma alerta todos los días; se resetea cuando '
             'el vehículo vuelve a reportar.',
    )

    _sql_constraints = [
        ('vehicle_report_status_uniq', 'unique(vehicle_id)',
         'Ya existe un estado de reporte GPS para este vehículo.'),
    ]

    @api.depends('ultima_fecha_reporte')
    def _compute_dias_sin_reportar(self):
        hoy = fields.Datetime.now()
        for rec in self:
            if not rec.ultima_fecha_reporte:
                rec.dias_sin_reportar = 0
                continue
            delta = hoy - rec.ultima_fecha_reporte
            rec.dias_sin_reportar = max(0, delta.days)

    @api.model
    def _get_or_create(self, vehicle_id):
        status = self.search([('vehicle_id', '=', vehicle_id)], limit=1)
        if not status:
            status = self.create({'vehicle_id': vehicle_id})
        return status
