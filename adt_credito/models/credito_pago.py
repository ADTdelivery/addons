from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CreditoPago(models.Model):
    _name = 'credito.pago'
    _description = 'Pago de una cuota de crédito'
    _order = 'fecha_pago desc, id desc'

    contrato_id = fields.Many2one('credito.contrato', string="Contrato", required=True, ondelete='cascade')
    cuota_id = fields.Many2one('credito.cuota', string="Cuota", required=True, ondelete='cascade')
    partner_id = fields.Many2one(related='contrato_id.partner_id', store=True, string="Cliente")
    currency_id = fields.Many2one(related='contrato_id.currency_id')

    tipo = fields.Selection([
        ('cuota', 'Cuota'),
        ('mora', 'Mora'),
    ], string="Aplica a", default='cuota', required=True,
        help="Indica si el monto se aplica al capital de la cuota o a la mora acumulada.")

    fecha_pago = fields.Date(string="Fecha de pago", default=fields.Date.context_today, required=True)
    monto = fields.Monetary(string="Monto pagado", required=True)
    metodo_pago = fields.Selection([
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro'),
    ], string="Método de pago", default='efectivo')
    referencia = fields.Char(string="Referencia / # operación")
    cobrador_id = fields.Many2one('res.users', string="Registrado por", default=lambda self: self.env.user)

    @api.constrains('monto')
    def _check_monto(self):
        for rec in self:
            if rec.monto <= 0:
                raise UserError(_("El monto del pago debe ser mayor a cero."))

    @api.onchange('cuota_id', 'tipo')
    def _onchange_cuota_id(self):
        if self.cuota_id:
            self.contrato_id = self.cuota_id.contrato_id
            self.monto = self.cuota_id.mora_pendiente if self.tipo == 'mora' else self.cuota_id.saldo

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('contrato_id') and vals.get('cuota_id'):
                vals['contrato_id'] = self.env['credito.cuota'].browse(vals['cuota_id']).contrato_id.id
        return super().create(vals_list)
