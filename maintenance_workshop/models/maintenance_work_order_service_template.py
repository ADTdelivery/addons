# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class MaintenanceWorkOrderServiceTemplate(models.Model):
    _name = 'maintenance.work.order.service.template'
    _description = 'Plantilla de Servicio - Taller'

    name = fields.Char(string='Nombre del Servicio', required=True)
    description = fields.Text(string='Descripción')
    default_unit_price = fields.Float(string='Precio Unitario (por defecto)')

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Moneda', readonly=True)
