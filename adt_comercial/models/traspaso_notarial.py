from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ESTADO_TRASPASO = [
    ('pendiente', 'Por iniciar'),
    ('documentos', 'Reuniendo documentos'),
    ('en_notaria', 'Firma en notaría'),
    ('en_registros', 'Inscripción en SUNARP'),
    ('completado', 'Traspaso completado'),
]
# Etapas que solo pueden empezar cuando el cliente terminó de pagar.
ESTADOS_REQUIEREN_PAGO = ('en_notaria', 'en_registros', 'completado')


class AdtTraspasoNotarial(models.Model):
    """Traspaso notarial de la moto al nombre del cliente cuando termina de pagar su crédito (uno por cuenta).

    El Dashboard de Clientes lista las cuentas que terminan pronto (para ir preparando documentos)
    y las ya pagadas; aquí se registra en qué etapa está cada traspaso.
    """
    _name = 'adt.traspaso.notarial'
    _description = 'Traspaso notarial de la moto al cliente'
    _inherit = ['mail.thread']
    _order = 'write_date desc, id desc'

    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='cuenta_id.partner_id', string='Cliente', store=True)
    vehiculo_id = fields.Many2one(related='cuenta_id.vehiculo_id', string='Moto', store=True)
    moto_placa = fields.Char(related='cuenta_id.moto_placa', string='Placa')
    estado = fields.Selection(ESTADO_TRASPASO, string='Etapa', default='pendiente', required=True, tracking=True)
    notaria = fields.Char(string='Notaría', tracking=True)
    fecha_firma = fields.Date(string='Fecha de firma en notaría', tracking=True)
    fecha_completado = fields.Date(string='Fecha de traspaso completado', tracking=True)
    notas = fields.Text(string='Notas')
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, tracking=True)

    _sql_constraints = [
        ('cuenta_unica', 'unique(cuenta_id)', 'La cuenta ya tiene un traspaso registrado.'),
    ]

    def name_get(self):
        return [(r.id, _('Traspaso %s') % (r.cuenta_id.display_name or '')) for r in self]

    @staticmethod
    def cuenta_terminada(cuenta):
        """El cliente terminó de pagar: cuenta pagada, o en curso sin cuotas ni mora por pagar
        (el estado de la cuenta se actualiza recién cuando alguien la abre)."""
        if cuenta.state == 'pagado':
            return True
        return (cuenta.state == 'en_curso' and bool(cuenta.cuota_ids)
                and not cuenta.qty_cuotas_restantes and not cuenta.mora_pendiente)

    @api.constrains('estado', 'cuenta_id')
    def _check_cuenta_pagada(self):
        for r in self:
            if r.estado in ESTADOS_REQUIEREN_PAGO and not self.cuenta_terminada(r.cuenta_id):
                raise ValidationError(_(
                    "La cuenta %s todavía no termina de pagar: solo se pueden reunir documentos "
                    "hasta que pague su última cuota.") % r.cuenta_id.display_name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('estado') == 'completado' and not vals.get('fecha_completado'):
                vals['fecha_completado'] = fields.Date.context_today(self)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('estado') == 'completado' and 'fecha_completado' not in vals:
            self.filtered(lambda r: not r.fecha_completado).write({'fecha_completado': fields.Date.context_today(self)})
        return res
