from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CreditoRegistrarPago(models.TransientModel):
    _name = 'credito.registrar.pago'
    _description = 'Registrar pago de una cuota de crédito'

    contrato_id = fields.Many2one('credito.contrato', string="Contrato", required=True)
    currency_id = fields.Many2one(related='contrato_id.currency_id')
    cuota_id = fields.Many2one(
        'credito.cuota', string="Cuota", required=True,
        domain="[('contrato_id', '=', contrato_id), ('estado', 'not in', ('pagada', 'condonada'))]",
    )
    tipo = fields.Selection([
        ('cuota', 'Cuota'),
        ('mora', 'Mora'),
    ], string="Aplica a", default='cuota', required=True)
    monto = fields.Monetary(string="Monto a pagar", required=True)
    fecha_pago = fields.Date(string="Fecha de pago", default=fields.Date.context_today, required=True)
    metodo_pago = fields.Selection([
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro'),
    ], string="Método de pago", default='efectivo')
    referencia = fields.Char(string="Referencia / # operación")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        cuota_id = self.env.context.get('default_cuota_id')
        contrato_id = self.env.context.get('default_contrato_id')

        if cuota_id:
            cuota = self.env['credito.cuota'].browse(cuota_id)
            res.setdefault('contrato_id', cuota.contrato_id.id)
            res.setdefault('cuota_id', cuota.id)
        elif contrato_id and 'cuota_id' in fields_list:
            cuota = self.env['credito.cuota'].search([
                ('contrato_id', '=', contrato_id),
                ('estado', 'not in', ('pagada', 'condonada')),
            ], order='numero_cuota asc', limit=1)
            if cuota:
                res.setdefault('cuota_id', cuota.id)

        cuota_final = self.env['credito.cuota'].browse(res.get('cuota_id')) if res.get('cuota_id') else None
        if cuota_final and 'monto' in fields_list:
            res.setdefault('monto', cuota_final.saldo)
        return res

    @api.onchange('cuota_id', 'tipo')
    def _onchange_cuota_tipo(self):
        if self.cuota_id:
            self.monto = self.cuota_id.mora_pendiente if self.tipo == 'mora' else self.cuota_id.saldo

    def action_confirmar(self):
        self.ensure_one()
        if self.monto <= 0:
            raise UserError(_("El monto a pagar debe ser mayor a cero."))
        self.env['credito.pago'].create({
            'contrato_id': self.contrato_id.id,
            'cuota_id': self.cuota_id.id,
            'tipo': self.tipo,
            'monto': self.monto,
            'fecha_pago': self.fecha_pago,
            'metodo_pago': self.metodo_pago,
            'referencia': self.referencia,
        })
        return {'type': 'ir.actions.act_window_close'}
