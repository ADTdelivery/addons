#-*- coding: utf-8 -*-

from odoo import models, fields, api


class res_partner_addons(models.Model):
    _name = 'res_partner_addons.res_partner_addons'
    _description = 'res_partner_addons.res_partner_addons'

    session = fields.Integer(string="Session")
    password = fields.Text(string="Password")

