# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AgtComercialEgresoCaja(models.Model):
    _name = 'adt.comercial.egreso.caja'
    _description = 'Egreso de Caja'
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True,
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
    )
    descripcion = fields.Char(
        string='Descripción',
        required=True,
    )
    monto = fields.Float(
        string='Monto (S/)',
        required=True,
        digits=(16, 2),
    )
    numero_operacion = fields.Char(
        string='N° de Operación',
        required=True,
    )

    _sql_constraints = [
        (
            'numero_operacion_unique',
            'UNIQUE(numero_operacion)',
            'El número de operación ya existe en Egresos de Caja. Debe ser único.',
        ),
    ]

    @api.constrains('numero_operacion')
    def _check_numero_operacion_unique(self):
        for rec in self:
            if not rec.numero_operacion:
                continue
            duplicate = self.env['adt.comercial.egreso.caja'].search([
                ('numero_operacion', '=', rec.numero_operacion),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    'El número de operación "%s" ya está registrado en Egresos de Caja '
                    '(referencia: %s). Debe ser único.' % (
                        rec.numero_operacion,
                        duplicate.name or duplicate.id,
                    )
                )

    @api.depends('fecha', 'numero_operacion')
    def _compute_name(self):
        for rec in self:
            if rec.fecha and rec.numero_operacion:
                rec.name = 'EGR-%s-%s' % (
                    rec.fecha.strftime('%Y%m'),
                    rec.numero_operacion,
                )
            elif rec.numero_operacion:
                rec.name = 'EGR-%s' % rec.numero_operacion
            else:
                rec.name = 'EGR-BORRADOR'
