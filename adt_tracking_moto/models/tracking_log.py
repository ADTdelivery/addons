# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AdtMotoTrackingLog(models.Model):
    """Una línea por cada cambio de etapa (logística o placa) o hito. Base del reporte de tiempos."""
    _name = 'adt.moto.tracking.log'
    _description = 'Historial de tracking de moto'
    _order = 'fecha_inicio desc, id desc'

    tracking_id = fields.Many2one('adt.moto.tracking', string='Tracking', required=True, ondelete='cascade', index=True)
    vehicle_id = fields.Many2one(related='tracking_id.vehicle_id', string='Moto', store=True)
    modelo_id = fields.Many2one(related='tracking_id.modelo_id', string='Modelo', store=True)
    flujo = fields.Selection([
        ('logistica', 'Logística'),
        ('placa', 'Placa'),
        ('hito', 'Hito'),
    ], string='Flujo', required=True)
    # Nombres tal como estaban al momento del cambio (renombrar una etapa no altera el historial).
    etapa_desde = fields.Char(string='Desde')
    etapa_hasta = fields.Char(string='Hacia')
    codigo_hasta = fields.Char(string='Código')
    etapa_id = fields.Many2one('adt.moto.tracking.etapa', string='Etapa')
    taller_fibra_id = fields.Many2one('adt.moto.tracking.taller', string='Taller de fibra')
    fecha_inicio = fields.Datetime(string='Inicio', required=True)
    fecha_fin = fields.Datetime(string='Fin')
    duracion_horas = fields.Float(
        string='Duración (horas)', compute='_compute_duracion', store=True, group_operator='avg', digits=(16, 1))
    duracion_dias = fields.Float(
        string='Duración (días)', compute='_compute_duracion', store=True, group_operator='avg', digits=(16, 2))
    user_id = fields.Many2one('res.users', string='Usuario')
    nota = fields.Text(string='Nota')

    @api.depends('fecha_inicio', 'fecha_fin')
    def _compute_duracion(self):
        for rec in self:
            if rec.fecha_inicio and rec.fecha_fin:
                segundos = (rec.fecha_fin - rec.fecha_inicio).total_seconds()
                rec.duracion_horas = segundos / 3600
                rec.duracion_dias = segundos / 86400
            else:
                rec.duracion_horas = rec.duracion_dias = 0
