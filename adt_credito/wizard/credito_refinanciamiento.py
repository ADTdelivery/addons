from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.credito_contrato import FRECUENCIAS


class CreditoRefinanciamiento(models.TransientModel):
    _name = 'credito.refinanciamiento'
    _description = 'Refinanciar un contrato de crédito'

    contrato_id = fields.Many2one('credito.contrato', string="Contrato a refinanciar", required=True)
    currency_id = fields.Many2one(related='contrato_id.currency_id')
    saldo_a_refinanciar = fields.Monetary(string="Saldo + mora a refinanciar", compute='_compute_saldo')

    frecuencia = fields.Selection(FRECUENCIAS, string="Nueva frecuencia", required=True, default='mensual')
    numero_cuotas = fields.Integer(string="Nuevo número de cuotas", required=True, default=1)
    fecha_inicio = fields.Date(string="Fecha de primera cuota", required=True, default=fields.Date.context_today)

    @api.depends('contrato_id')
    def _compute_saldo(self):
        for rec in self:
            rec.saldo_a_refinanciar = rec.contrato_id.saldo_pendiente + rec.contrato_id.mora_total

    def action_confirmar(self):
        self.ensure_one()
        origen = self.contrato_id
        if origen.estado not in ('activo', 'en_mora'):
            raise UserError(_("Solo se pueden refinanciar contratos activos o en mora."))
        if self.numero_cuotas <= 0:
            raise UserError(_("El número de cuotas debe ser mayor a cero."))

        saldo_product = self.env.ref('adt_credito.product_saldo_refinanciado')
        nuevo = self.env['credito.contrato'].create({
            'partner_id': origen.partner_id.id,
            'company_id': origen.company_id.id,
            'product_id': saldo_product.id,
            'cantidad': 1,
            'precio_unitario': self.saldo_a_refinanciar,
            'frecuencia': self.frecuencia,
            'numero_cuotas': self.numero_cuotas,
            'fecha_inicio': self.fecha_inicio,
            'contrato_origen_id': origen.id,
        })
        nuevo.action_confirmar()
        origen.write({'estado': 'refinanciado', 'contrato_refinanciado_id': nuevo.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'credito.contrato',
            'res_id': nuevo.id,
            'view_mode': 'form',
        }
