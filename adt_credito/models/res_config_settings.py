from odoo import fields, models


class CreditoConfigWizard(models.TransientModel):
    """Pantalla ligera para editar la configuración de mora de la compañía actual,
    sin depender de la vista estándar (más frágil) de Ajustes generales."""
    _name = 'credito.config.wizard'
    _description = 'Configuración de crédito'

    company_id = fields.Many2one('res.company', string="Compañía", required=True,
                                  default=lambda self: self.env.company)
    credito_mora_tipo = fields.Selection(related='company_id.credito_mora_tipo', readonly=False)
    credito_mora_valor = fields.Float(related='company_id.credito_mora_valor', readonly=False)
    credito_mora_dias_gracia = fields.Integer(related='company_id.credito_mora_dias_gracia', readonly=False)
    credito_mora_tope = fields.Float(related='company_id.credito_mora_tope', readonly=False)

    def action_guardar(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window_close'}
