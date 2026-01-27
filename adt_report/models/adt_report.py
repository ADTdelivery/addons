# -*- coding: utf-8 -*-
from odoo import models, fields


class AdtReport(models.Model):
    _name = "adt.report"
    _description = "ADT Report"

    name = fields.Char(string="Name", required=True)
    date = fields.Date(string="Date")
    note = fields.Text(string="Notes")
