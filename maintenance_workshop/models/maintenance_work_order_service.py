# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class MaintenanceWorkOrderService(models.Model):
    _name = 'maintenance.work.order.service'
    _description = 'Servicios / Mano de obra'

    work_order_id = fields.Many2one('maintenance.work.order', string='Orden', ondelete='cascade')
    name = fields.Char(string='Servicio')
    description = fields.Text(string='Descripción')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
