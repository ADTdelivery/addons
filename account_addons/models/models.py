# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api
from datetime import datetime
import xmlrpc.client
import json
import base64


class AccountAddons(models.Model):
    _inherit = 'account.move'

    @api.model
    def create(self, vals):

        try:
            # Database connection
            url = 'http://190.232.26.249:8070'
            db = 'odoo'
            username = 'rapitash@gmail.com'
            password = 'Krishnna17'

            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
            uid = common.authenticate(db, username, password, {})
            models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
            record = super(AccountAddons, self).create(vals)
            # logging.info("id model  " + str(vals['x_quotation_model_id']))

            data_template = models.execute_kw(db, uid, password, 'fleet.vehicle.model', 'search_read',
                                              [[['id', '=', vals['x_quotation_model_id']]]],
                                              {'fields': ['name'], 'limit': 1})

            # Create fleet.vehicle
            if vals['x_quotation_model_id'] is not None:
                fleet_data = {
                    'name': data_template[0]['name'],
                    'active': True,
                    #'company_id': 1,
                    'vin_sn': vals['x_quotation_chasis'],
                    'trailer_hook': False,
                    'driver_id': vals['x_quotation_driver_id'],
                    'model_id': vals['x_quotation_model_id'],
                    'color': vals['x_quotation_color'],
                    'state_id': 3,
                    'model_year': vals['x_quotation_ano_modelo'],
                    'fuel_type': 'diesel',
                    'horsepower': 0,
                    'power': 0,
                    'co2': 0,
                    'car_value': 0,
                    'net_car_value': 0,
                    'residual_value': 0,
                    'plan_to_change_car': False,
                    'plan_to_change_bike': False,
                    'create_uid': 2,
                    'write_uid': 2,
                    'x_motor_sn': vals['x_quotation_motor'],
                    'disponible': True,
                    'x_id_facturacion': record.id
                }
                id = models.execute_kw(db, uid, password, 'fleet.vehicle', 'create', [fleet_data])

            logging.info("id de account " + str(record.id) + " and  id partner ")

        except Exception as e:
            logging.info('exception ' + str(e))
            logging.info('no data account')
            logging.info(str(vals))
            record = super(AccountAddons, self).create(vals)

        return record
