# -*- coding: utf-8 -*-

from odoo import models, fields, api


class contacto_addons(models.Model):
    _inherit = "res.partner"

    nombre_completo = fields.Char(string="Nombre(s)")
    apellido_paterno = fields.Char(string="Apellido Paterno")
    apellido_materno = fields.Char(string="Apellido Materno")

    @api.onchange('nombre_completo', 'apellido_paterno', 'apellido_materno')
    def _onchange_nombre_completo(self):
        """Autorellenar el campo name cuando se modifican los campos de nombre"""
        if self.nombre_completo or self.apellido_paterno or self.apellido_materno:
            nombres = []
            if self.nombre_completo:
                nombres.append(self.nombre_completo.strip())
            if self.apellido_paterno:
                nombres.append(self.apellido_paterno.strip())
            if self.apellido_materno:
                nombres.append(self.apellido_materno.strip())
            self.name = ' '.join(nombres)
