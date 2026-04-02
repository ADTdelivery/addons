# -*- coding: utf-8 -*-
from odoo import models, fields, api


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
