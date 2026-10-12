# -*- coding: utf-8 -*-

from odoo import models, fields, api


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
          ("inscrito", "Inscrito"),
          ("observado","Observado"),
          ("tachado","Tachado"),
     ], default = "borrador" , string= "Estado del tramite", tracking = 1)
     num_plate = fields.Char(string="N° Placa", tracking = 1)
     state_plate = fields.Selection([
          ("pagado","Pagado") ,
          ("recogido","Recogido") ,
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

     # Placa y tarjeta de propiedad se pasan al vehículo al guardar (no en onchange).
     @api.model_create_multi
     def create(self, vals_list):
          records = super().create(vals_list)
          records._sync_vehiculo()
          return records

     def write(self, vals):
          res = super().write(vals)
          if {'num_plate', 'tarjeta_propiedad', 'vehiculo_id'} & vals.keys():
               self._sync_vehiculo()
          return res

     def _sync_vehiculo(self):
          for plate in self.filtered('vehiculo_id'):
               vehicle = plate.vehiculo_id.sudo()
               vals = {}
               if plate.num_plate and plate.num_plate != vehicle.license_plate:
                    vals['license_plate'] = plate.num_plate
               # tarjeta_propiedad_attachment lo agrega adt_fleet / fleet_addons, si están instalados.
               if plate.tarjeta_propiedad and 'tarjeta_propiedad_attachment' in vehicle._fields:
                    vals['tarjeta_propiedad_attachment'] = plate.tarjeta_propiedad
               if vals:
                    vehicle.write(vals)

