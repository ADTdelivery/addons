# -*- coding: utf-8 -*-
# from odoo import http


# class FleetAddons(http.Controller):
#     @http.route('/fleet_addons/fleet_addons', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/fleet_addons/fleet_addons/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('fleet_addons.listing', {
#             'root': '/fleet_addons/fleet_addons',
#             'objects': http.request.env['fleet_addons.fleet_addons'].search([]),
#         })

#     @http.route('/fleet_addons/fleet_addons/objects/<model("fleet_addons.fleet_addons"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('fleet_addons.object', {
#             'object': obj
#         })
