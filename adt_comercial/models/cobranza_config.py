from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTCobranzaConfigRecuperacion(models.Model):
    _name = 'adt.cobranza.config.recuperacion'
    _description = 'Configuración de cobranza'

    dias_retraso = fields.Integer(string="Días de retraso")
    periodicidad = fields.Selection(
        [('semanal', 'Semanal'), ('quincena', 'Quincenal'), ('mensual', 'Mensual')], string="Periodo de pago")
