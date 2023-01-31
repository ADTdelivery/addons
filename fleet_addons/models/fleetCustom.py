import logging

from odoo import models, fields, api
from odoo.http import request


class FleetCustomReport(models.Model):
    _inherit = 'fleet.vehicle'

    def getLines(self):
        vehicle_price = request.env['product.template'].search([('product_model_id', '=', self.model_id.id)]).read([
            'list_price'
        ])
        if len(vehicle_price) > 0 :
            total_vehicle = vehicle_price[0]['list_price'] + 2250.0
        else :
            total_vehicle = 0

        return total_vehicle

