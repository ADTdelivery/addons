# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Clasificación de Cliente
    es_cliente_taller = fields.Boolean(string='Es Cliente del Taller', default=False)
    clasificacion_cliente = fields.Selection([
        ('nuevo', 'Nuevo'),
        ('frecuente', 'Frecuente'),
        ('vip', 'VIP'),
        ('inactivo', 'Inactivo')
    ], string='Clasificación', compute='_compute_clasificacion', store=True)

    # Vehículos
    vehiculo_ids = fields.One2many('adt.vehiculo', 'cliente_id', string='Vehículos')
    cantidad_vehiculos = fields.Integer(string='Cantidad de Vehículos', compute='_compute_vehiculos')

    # Historial Financiero
    orden_ids = fields.One2many('adt.orden.mantenimiento', 'cliente_id', string='Órdenes')
    total_gastado = fields.Monetary(string='Total Gastado', compute='_compute_historial_financiero', currency_field='currency_id')
    cantidad_visitas = fields.Integer(string='Cantidad de Visitas', compute='_compute_historial_financiero')
    promedio_ticket = fields.Monetary(string='Ticket Promedio', compute='_compute_historial_financiero', currency_field='currency_id')
    ultima_visita = fields.Date(string='Última Visita', compute='_compute_historial_financiero')

    # Créditos
    tiene_credito_atrasado = fields.Boolean(string='Tiene Crédito Atrasado', compute='_compute_estado_credito')
    credito_ids = fields.One2many('adt.credito.financiero', 'cliente_id', string='Créditos')

    @api.depends('vehiculo_ids')
    def _compute_vehiculos(self):
        for record in self:
            record.cantidad_vehiculos = len(record.vehiculo_ids)

    @api.depends('orden_ids', 'orden_ids.state', 'orden_ids.total')
    def _compute_historial_financiero(self):
        for record in self:
            ordenes_completadas = record.orden_ids.filtered(lambda o: o.state == 'done')
            record.cantidad_visitas = len(ordenes_completadas)
            record.total_gastado = sum(ordenes_completadas.mapped('total'))
            record.promedio_ticket = record.total_gastado / record.cantidad_visitas if record.cantidad_visitas > 0 else 0
            record.ultima_visita = max(ordenes_completadas.mapped('fecha_ingreso')) if ordenes_completadas else False

    @api.depends('cantidad_visitas', 'total_gastado', 'ultima_visita')
    def _compute_clasificacion(self):
        for record in self:
            if not record.es_cliente_taller:
                record.clasificacion_cliente = False
            elif record.cantidad_visitas == 0:
                record.clasificacion_cliente = 'nuevo'
            elif record.cantidad_visitas > 10 and record.total_gastado > 5000:
                record.clasificacion_cliente = 'vip'
            elif record.cantidad_visitas >= 5:
                record.clasificacion_cliente = 'frecuente'
            elif record.ultima_visita and (fields.Date.today() - record.ultima_visita).days > 180:
                record.clasificacion_cliente = 'inactivo'
            else:
                record.clasificacion_cliente = 'frecuente'

    @api.depends('credito_ids', 'credito_ids.estado')
    def _compute_estado_credito(self):
        for record in self:
            record.tiene_credito_atrasado = any(
                credito.estado in ['atrasado', 'mora']
                for credito in record.credito_ids
            )

    def action_ver_historial_financiero(self):
        """Ver historial completo de órdenes"""
        self.ensure_one()
        return {
            'name': _('Historial Financiero'),
            'type': 'ir.actions.act_window',
            'res_model': 'adt.orden.mantenimiento',
            'view_mode': 'tree,form,graph',
            'domain': [('cliente_id', '=', self.id)],
            'context': {'default_cliente_id': self.id}
        }

    def action_ver_vehiculos(self):
        """Ver vehículos del cliente"""
        self.ensure_one()
        return {
            'name': _('Vehículos del Cliente'),
            'type': 'ir.actions.act_window',
            'res_model': 'adt.vehiculo',
            'view_mode': 'tree,form',
            'domain': [('cliente_id', '=', self.id)],
            'context': {'default_cliente_id': self.id}
        }
