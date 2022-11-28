# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging


class InfraccionAttributesModel(models.Model):
    _name = 'infraccion.attributes.model'
    _description = 'infraccion_addons.infraccion_addons'

    name = fields.Char(string="Nombre")
    description = fields.Char(string="Descripcion")
    monto_papeleta = fields.Float(string="Monto", default=0)
    file = fields.Binary(string="Documento")

    fleet_id = fields.Many2one("fleet.vehicle", string="Vehiculo id")

    def action_create_papeleta(self):
        logging.info('papeleta:' + str(self))

    """papeleta = self.env['infraccion.attributes.model'].create({
         'fleet_id': self.id,
         'name': self.name,
         'monto_papeleta': self.monto_papeleta,
     })"""
