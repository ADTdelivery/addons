# -*- coding: utf-8 -*-
# from odoo import http


# class ContactoAddons(http.Controller):
#     @http.route('/contacto_addons/contacto_addons', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/contacto_addons/contacto_addons/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('contacto_addons.listing', {
#             'root': '/contacto_addons/contacto_addons',
#             'objects': http.request.env['contacto_addons.contacto_addons'].search([]),
#         })

#     @http.route('/contacto_addons/contacto_addons/objects/<model("contacto_addons.contacto_addons"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('contacto_addons.object', {
#             'object': obj
#         })
