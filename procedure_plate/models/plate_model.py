# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.http import request


class ProcedurePlateModel(models.Model):
     _name = 'procedure.plate.model'
     _description = 'Procedure for create a plate'
     _inherit = ['mail.thread', 'mail.activity.mixin']

     num_title = fields.Char(string="N° Título", tracking = 1)
     init_date = fields.Date(string="Fecha de inicio", default=fields.Date.today, tracking = 1)
     own_name = fields.Char(string="Titular")
     provider_id = fields.Many2one("res.partner", "Proveedor")
     num_account = fields.Char(string="N° Factura")
     state_procedure = fields.Selection([
          ("borrador","Borrador"),
          ("en_notaria","Notaria"),
          ("en_sunarp","SUNARP"),
          ("observado","Observado"),
          ("tachado","Tachado"),
          ("inscrito","Inscrito")
     ], default = "borrador" , string= "Estado del tramite", tracking = 1)
     num_plate = fields.Char(string="N° Placa", tracking = 1)
     state_plate = fields.Selection([
          ("pagado","Pagado") ,
          ("recogido","Recodigo") ,
          ("entregado_cliente","Entregado Cliente")
     ], string = "Estado de placa" ,tracking = 1)
     information = fields.Char(string="Información")

     def aprobar_notaria(self):
          for plate in self:
               plate.write({'state_procedure': 'en_notaria'})

     def aprobar_sunarp(self):
          for plate in self:
               plate.write({'state_procedure' : 'en_sunarp'})

     def aprobar_inscrito(self):
          for plate in self:
               plate.write({'state_procedure' : 'inscrito'})

     def aprobar_observado(self):
          for plate in self:
               plate.write({'state_procedure' : 'observado'})

     def aprobar_tachado(self):
          for plate in self:
               plate.write({'state_procedure' : 'tachado'})

     vehiculo_id = fields.Many2one("fleet.vehicle","Vehículo")
     account_id = fields.Integer(string="ID Facturacion")
     #account_id = fields.Many2one("account.move","ID Facturacion")

     chasis = fields.Char(string="Chasis", related="vehiculo_id.vin_sn")
     tarjeta_propiedad = fields.Binary(string="Tarjeta de propiedad")

     @api.onchange('num_plate')
     def num_plate_change(self):
          vehicle_id = request.env['fleet.vehicle'].search([['id', '=', self.vehiculo_id.id ]])
          vehicle_id.write({'license_plate':self.num_plate})

     @api.onchange('tarjeta_propiedad')
     def tarjeta_propiedad_change(self):
          vehicle_tarjeta = request.env['fleet.vehicle'].create(self)
          data = self
          print("data")
          data2 = data
          print(str(vehicle_tarjeta))

