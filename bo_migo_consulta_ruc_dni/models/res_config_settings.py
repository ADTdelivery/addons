from odoo import models,fields,api
from odoo.http import request

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    api_migo_endpoint = fields.Char(string="API Migo - Endpoint")
    api_migo_token = fields.Char(string="API Migo - Token")

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICPSudo = self.env["ir.config_parameter"].sudo()
        api_migo_endpoint = ICPSudo.get_param("api.migo.endpoint", default="")
        api_migo_token = ICPSudo.get_param("api.migo.token", default="")

        res.update(
            api_migo_token=api_migo_token,
            api_migo_endpoint=api_migo_endpoint
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICPSudo = self.env["ir.config_parameter"].sudo()
        ICPSudo.set_param("api.migo.endpoint", self.api_migo_endpoint or "")
        ICPSudo.set_param("api.migo.token", self.api_migo_token or "")
