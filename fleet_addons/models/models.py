# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api
import xmlrpc.client


class FleetAddons(models.Model):
    _inherit = 'fleet.vehicle'

    def write(self, vals):

        logging.info(vals)
        try:
            logging.info(vals['driver_id'])
            # Database connection
            url = 'http://52.15.86.160:8070'
            db = 'postgresadt'
            username = 'admin'
            password = 'adtDelivery2024'

            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
            uid = common.authenticate(db, username, password, {})
            models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))

            # Search1
            # x_id_facturacion account.move  into fleet.vehicle
            fleet_data = models.execute_kw(db, uid, password, 'fleet.vehicle', 'search_read', [[['id', '=', self.id]]],
                                           {'fields': ['x_id_facturacion', 'driver_id', 'model_id'], 'limit': 1})

            # Add model_id into dictionary
            vals['model_id'] = fleet_data[0]['model_id'][0]

            driver_id = vals['driver_id']

            # Update account.move
            logging.info("driver id " + str(vals['driver_id']))
            models.execute_kw(db, uid, password, 'account.move', 'write',
                              [[fleet_data[0]['x_id_facturacion']], {'x_quotation_driver_id': driver_id}])

            models.execute_kw(db, uid, password, 'fleet.vehicle', 'write',
                              [self.id, {'x_quotation_driver_id': driver_id}])

        except Exception as e:
            logging.info('exception ' + str(e))
            logging.info('no data fleet')
            res = super(FleetAddons, self).write(vals)
