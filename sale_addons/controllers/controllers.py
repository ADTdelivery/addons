# -*- coding: utf-8 -*-
# from odoo import http


# class SaleAddons(http.Controller):
#     @http.route('/sale_addons/sale_addons', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sale_addons/sale_addons/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('sale_addons.listing', {
#             'root': '/sale_addons/sale_addons',
#             'objects': http.request.env['sale_addons.sale_addons'].search([]),
#         })

#     @http.route('/sale_addons/sale_addons/objects/<model("sale_addons.sale_addons"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sale_addons.object', {
#             'object': obj
#         })
