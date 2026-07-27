# -*- coding: utf-8 -*-
"""
Imágenes de la Oferta/Promoción asociada a una Regla de Mantenimiento.

Los campos propios de la oferta (título, descripción, precio, vigencia,
WhatsApp) viven directamente en adt.mantenimiento.regla (ver
mantenimiento_regla.py) porque una regla tiene UNA sola oferta asociada;
solo las imágenes necesitan su propio modelo porque son varias (galería).
"""
from odoo import fields, models


class AdtMantenimientoOfertaImagen(models.Model):
    _name = 'adt.mantenimiento.oferta.imagen'
    _description = 'Imagen de Oferta de Regla de Mantenimiento'
    _order = 'sequence, id'

    regla_id = fields.Many2one(
        'adt.mantenimiento.regla', string='Regla', required=True, ondelete='cascade', index=True,
    )
    image = fields.Binary(string='Imagen', required=True, attachment=True)
    image_filename = fields.Char(string='Nombre de archivo')
    sequence = fields.Integer(string='Orden', default=10)
