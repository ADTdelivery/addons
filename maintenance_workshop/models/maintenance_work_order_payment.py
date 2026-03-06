# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class MaintenanceWorkOrderPayment(models.Model):
    _name = 'maintenance.work.order.payment'
    _description = 'Pago programado para Orden de Trabajo'

    work_order_id = fields.Many2one('maintenance.work.order', string='Orden de Trabajo', ondelete='cascade')
    name = fields.Char(string='Descripción')
    due_date = fields.Date(string='Fecha de Vencimiento')
    amount = fields.Monetary(string='Monto', currency_field='company_currency_id')
    payer = fields.Selection([
        ('cliente', 'Cliente'),
        ('adt', 'ADT Corporación')
    ], string='Pagador', default='cliente')
    state = fields.Selection([('pending','Pendiente'),('paid','Pagado')], string='Estado', default='pending')

    company_currency_id = fields.Many2one('res.currency', related='work_order_id.company_currency_id', string='Moneda', readonly=True)

    @api.model
    def create(self, vals):
        if not vals.get('name') and vals.get('work_order_id'):
            wo = self.env['maintenance.work.order'].browse(vals.get('work_order_id'))
            seq = self.search_count([('work_order_id','=',wo.id)]) + 1
            vals['name'] = _('Cuota %s' % seq)
        return super(MaintenanceWorkOrderPayment, self).create(vals)
