# -*- coding: utf-8 -*-
# from odoo import http


# class AccountAddons(http.Controller):
#     @http.route('/account_addons/account_addons', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/account_addons/account_addons/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('account_addons.listing', {
#             'root': '/account_addons/account_addons',
#             'objects': http.request.env['account_addons.account_addons'].search([]),
#         })

#     @http.route('/account_addons/account_addons/objects/<model("account_addons.account_addons"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('account_addons.object', {
#             'object': obj
#         })
