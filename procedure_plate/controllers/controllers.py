# -*- coding: utf-8 -*-
# from odoo import http


# class ProcedurePlate(http.Controller):
#     @http.route('/procedure_plate/procedure_plate', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/procedure_plate/procedure_plate/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('procedure_plate.listing', {
#             'root': '/procedure_plate/procedure_plate',
#             'objects': http.request.env['procedure_plate.procedure_plate'].search([]),
#         })

#     @http.route('/procedure_plate/procedure_plate/objects/<model("procedure_plate.procedure_plate"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('procedure_plate.object', {
#             'object': obj
#         })
