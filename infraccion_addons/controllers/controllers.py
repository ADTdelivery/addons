# -*- coding: utf-8 -*-
# from odoo import http


# class InfraccionAddons(http.Controller):
#     @http.route('/infraccion_addons/infraccion_addons', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/infraccion_addons/infraccion_addons/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('infraccion_addons.listing', {
#             'root': '/infraccion_addons/infraccion_addons',
#             'objects': http.request.env['infraccion_addons.infraccion_addons'].search([]),
#         })

#     @http.route('/infraccion_addons/infraccion_addons/objects/<model("infraccion_addons.infraccion_addons"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('infraccion_addons.object', {
#             'object': obj
#         })
