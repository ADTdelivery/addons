# -*- coding: utf-8 -*-
# from odoo import http


# class ProductAddons(http.Controller):
#     @http.route('/product_addons/product_addons', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/product_addons/product_addons/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('product_addons.listing', {
#             'root': '/product_addons/product_addons',
#             'objects': http.request.env['product_addons.product_addons'].search([]),
#         })

#     @http.route('/product_addons/product_addons/objects/<model("product_addons.product_addons"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('product_addons.object', {
#             'object': obj
#         })
