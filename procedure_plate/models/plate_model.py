# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ProcedurePlateModel(models.Model):
     _name = 'procedure.plate.model'
     _description = 'Procedure for create a plate'
     _inherit = ['mail.thread', 'mail.activity.mixin']

     num_title = fields.Char(string="Numero titulo")
     init_date = fields.Date(string="Fecha de entrega", default=fields.Date.today)
     own_name = fields.Char(string="Nombre del vehiculo")
     provider_name = fields.Char(string="Nombre del proveedor")
     num_account = fields.Char(string="Numero de factura")
     state_procedure = fields.Selection([
          ("borrador","Borrador"),("en_notaria","Notaria"),("en_sunarp","SUNARP"),("inscrito","Inscrito"),("observado","Observado"),("tachado","Tachado")
     ], default = "borrador" , string= "Estado del tramite", tracking = 1)
     num_plate = fields.Char(string="Numero de placa")
     state_plate = fields.Selection([
          ("pagado","Pagado") , ("recogido","Recodigo") , ("entregado_cliente","Entregado Cliente")
     ], string = "Estado de placa" ,tracking = 1)
     information = fields.Char(string="Informacion")

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

