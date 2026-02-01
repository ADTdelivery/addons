# -*- coding: utf-8 -*-
from odoo import models, fields


from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nationality = fields.Selection([
        ('peruana', 'Peruana'),
        ('argentina', 'Argentina'),
        ('bolivia', 'Bolivia'),
        ('brasil', 'Brasil'),
        ('chile', 'Chile'),
        ('colombia', 'Colombia'),
        ('costa_rica', 'Costa Rica'),
        ('cuba', 'Cuba'),
        ('republica_dominicana', 'República Dominicana'),
        ('ecuador', 'Ecuador'),
        ('el_salvador', 'El Salvador'),
        ('guatemala', 'Guatemala'),
        ('honduras', 'Honduras'),
        ('mexico', 'México'),
        ('nicaragua', 'Nicaragua'),
        ('panama', 'Panamá'),
        ('paraguay', 'Paraguay'),
        ('puerto_rico', 'Puerto Rico'),
        ('uruguay', 'Uruguay'),
        ('venezuela', 'Venezuela'),
        ('belice', 'Belice'),
        ('haiti', 'Haití'),
        ('guyana', 'Guyana'),
        ('suriname', 'Surinam'),
        ('guayana_francesa', 'Guayana Francesa'),
        ('otro', 'Otro'),
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

    occupation = fields.Selection(
        [
            # Mototaxi / Transporte
            ('mototaxista', 'Mototaxista'),
            ('mototaxista_empleado', 'Chofer de mototaxi (empleado)'),
            ('delivery', 'Repartidor / Delivery'),
            ('conductor_informal', 'Conductor de transporte informal (taxi, combi)'),

            # Comercio
            ('comerciante_ambulante', 'Comerciante ambulante'),
            ('tiendecista', 'Pequeño comerciante / Tiendecista'),
            ('microempresario', 'Microempresario'),

            # Construcción / Oficios
            ('obrero_construccion', 'Trabajador de construcción'),
            ('obrero_general', 'Obrero general'),
            ('electricista', 'Electricista'),
            ('plomero', 'Plomero'),
            ('carpintero', 'Carpintero'),
            ('mecanico', 'Mecánico'),
            ('soldador', 'Soldador'),
            ('cerrajero', 'Cerrajero'),

            # Servicios / Otros trabajos
            ('empleado_servicios', 'Empleado de servicios (hotel, retail, atención al cliente)'),
            ('jornalero', 'Trabajador por días / Jornalero'),
            ('agricultor', 'Agricultor / Campesino'),
            ('estudiante_trabajador', 'Estudiante con trabajo informal'),

            # Otros
            ('otro', 'Otro'),
        ],
        string="Ocupación",
        required=True
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

