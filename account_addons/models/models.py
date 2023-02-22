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
        #print(str(vals))
        try:
            # Database connection
            url = 'http://190.238.200.63:8070/'
            db = 'odoo'
            username = 'rapitash@gmail.com'
            password = 'Krishnna17'

            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
            uid = common.authenticate(db, username, password, {})
            models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
            record = super(AccountAddons, self).create(vals)

            data_template = models.execute_kw(db, uid, password, 'fleet.vehicle.model', 'search_read',
                                              [[['id', '=', vals['x_quotation_model_id']]]],
                                              {'fields': ['name'], 'limit': 1})


            if vals['x_quotation_model_id'] is not None:
                fleet_data = {
                    'name': data_template[0]['name'],
                    'active': True,
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
                logging.info("FLEET _DATA")
                logging.info(str(fleet_data))
                id = models.execute_kw(db, uid, password, 'fleet.vehicle', 'create', [fleet_data])

                plate_data = {
                    'own_name' : 'CORPORACION ADT',
                    'provider_id' :vals['partner_id'],
                    'num_account' : self.document_type(vals['l10n_latam_document_type_id'])+" "+vals['l10n_latam_document_number'],
                    'vehiculo_id' : id,
                    'account_id' : record.id
                }

                #logging.info(str(plate_data))

                plate_id = models.execute_kw(db , uid, password, 'procedure.plate.model','create', [plate_data])

            logging.info("id de account " + str(record.id) + " and  id partner ")

        except Exception as e:
            logging.error('exception ' + str(e))
            logging.info('no data account')
            logging.info(str(vals))
            record = super(AccountAddons, self).create(vals)

        return record

    def document_type(self,id):
        if id == 1 or id == 3 or id == 5:
            result = "F"
        if id == 2 or id == 4 or id == 6:
            result = "B"
        if id == 7:
            result = "R"
        if id == 8:
            result = "P"
        return result