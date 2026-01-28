# -*- coding: utf-8 -*-
from odoo import models, fields


from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nationality = fields.Selection([
        ('peruana', 'Peruana'),
        ('extranjera', 'Extranjera')
    ], string="Nacionalidad")

    document_number = fields.Char(string="Documento de identidad", required=True)

    marital_status = fields.Selection([
        ('soltero', 'Soltero'),
        ('casado', 'Casado'),
        ('conviviente', 'Conviviente'),
        ('divorciado', 'Divorciado'),
        ('viudo', 'Viudo')
    ], string="Estado civil")

    children_count = fields.Selection([
        ('0', '0'),
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
        ('4+', '4 o más')
    ], string="Cantidad de hijos")

    occupation = fields.Selection([
        ('mototaxista', 'Mototaxista'),
        ('empleado', 'Empleado'),
        ('independiente', 'Independiente'),
        ('comerciante', 'Comerciante'),
        ('otro', 'Otro')
    ], string="Ocupación", required=True)

    reference_ids = fields.One2many(
        'res.partner.reference',
        'partner_id',
        string="Referencias personales"
    )

    _sql_constraints = [
        ('unique_document', 'unique(document_number)', 'Este documento ya está registrado.')
    ]

    @api.constrains('document_number', 'nationality')
    def _check_dni(self):
        for rec in self:
            if rec.document_number and rec.nationality == 'peruana':
                if not re.fullmatch(r'\d{8}', rec.document_number):
                    raise ValidationError("El DNI debe tener exactamente 8 dígitos.")

