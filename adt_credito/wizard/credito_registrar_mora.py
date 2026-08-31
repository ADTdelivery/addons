from odoo import fields, models


class CreditoRegistrarMora(models.TransientModel):
    _name = 'credito.registrar.mora'
    _description = 'Registrar mora manual sobre una cuota'

    cuota_id = fields.Many2one('credito.cuota', string="Cuota", required=True)
    currency_id = fields.Many2one(related='cuota_id.currency_id')
    mora_monto = fields.Monetary(string="Monto de mora", required=True)

    def action_confirmar(self):
        self.ensure_one()
        self.cuota_id.write({
            'mora_manual': True,
            'mora_manual_monto': self.mora_monto,
        })
