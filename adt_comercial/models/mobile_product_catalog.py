# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    mobile_published = fields.Boolean(
        string='Disponible en App Móvil',
        default=False,
        help='Si está activo, el producto podrá consultarse desde la app móvil.',
    )
    mobile_sequence = fields.Integer(
        string='Orden App Móvil',
        default=10,
        help='Menor número = se muestra primero en el catálogo móvil.',
    )
    mobile_short_description = fields.Char(
        string='Descripción corta App',
        help='Texto breve para tarjetas/listados del catálogo móvil.',
    )
    mobile_badge = fields.Char(
        string='Etiqueta App',
        help='Texto corto destacado, por ejemplo: Nuevo, Oferta, Top.',
    )
    mobile_qty_available = fields.Float(
        string='Stock visible App',
        default=0.0,
        help='Cantidad mostrada en la app móvil como stock disponible.',
    )
    mobile_buy_cta_enabled = fields.Boolean(
        string='Botón comprar activo',
        default=True,
        help='Si está activo, la app mostrará el botón de compra por WhatsApp.',
    )
    mobile_buy_whatsapp_phone = fields.Char(
        string='WhatsApp de ventas',
        help='Número para redirección de compra. Ejemplo: 51999111222',
    )
    mobile_buy_button_color = fields.Char(
        string='Color botón comprar',
        default='#25D366',
        help='Color del botón en formato HEX. Ejemplo: #25D366',
    )
    mobile_buy_button_icon = fields.Char(
        string='Ícono botón comprar',
        default='whatsapp',
        help='Nombre lógico del ícono para la app. Ejemplo: whatsapp, cart, bag.',
    )
    mobile_buy_button_text = fields.Char(
        string='Texto botón comprar',
        default='Comprar por WhatsApp',
        help='Texto mostrado en el botón de compra.',
    )
    mobile_product_image_ids = fields.One2many(
        'mobile.catalog.product.image',
        'product_tmpl_id',
        string='Galería de imágenes App',
    )


class MobileCatalogProductImage(models.Model):
    _name = 'mobile.catalog.product.image'
    _description = 'Imagen adicional de producto móvil'
    _order = 'sequence asc, id asc'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Nombre', required=True, default='Imagen')
    sequence = fields.Integer(string='Orden', default=10)
    image_1920 = fields.Binary(string='Imagen', required=True, attachment=True)
    active = fields.Boolean(default=True)

