from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTCobranzaConfigRecuperacion(models.Model):
    _name = 'adt.cobranza.config.recuperacion'
    _description = 'Configuración de cobranza'

    dias_retraso = fields.Integer(string="Días de retraso")
    periodicidad = fields.Selection(
        [('semanal', 'Semanal'), ('quincena', 'Quincenal'), ('mensual', 'Mensual')], string="Periodo de pago")


# adt_comercial/models/adt_cobranza_config.py

class AdtCobranzaConfigFactor(models.Model):
    _name = 'adt.cobranza.config.factor'
    _description = 'Cobranza Configuration'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company, required=True,index=True)
    factor_mora = fields.Float(string='Factor Mora', digits=(12, 2), default=0.0)
    active = fields.Boolean(string='Active', default=True)
    name = fields.Char()