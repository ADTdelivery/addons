import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MASIVAS = 'adt.comercial.cuotas.masivas.wizard'


class AdtCancelarCreditoWizard(models.TransientModel):
    """Paga un monto sobre la cuenta y lo distribuye en cascada entre las cuotas
    (capital + mora de la más antigua a la más reciente), con la misma lógica de
    la importación masiva de cuotas."""
    _name = 'adt.cancelar.credito.wizard'
    _description = 'Cancelar crédito / pago en cascada'

    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', required=True, readonly=True)
    currency_id = fields.Many2one(related='cuenta_id.currency_id')
    payment_date = fields.Date(string='Fecha de pago', required=True, default=fields.Date.context_today)
    numero_operacion = fields.Char(string='N° de operación', required=True)

    cuotas_pendientes = fields.Integer(string='Cuotas pendientes', compute='_compute_deuda')
    capital_pendiente = fields.Monetary(string='Capital pendiente', compute='_compute_deuda')
    mora_pendiente = fields.Monetary(string='Mora pendiente', compute='_compute_deuda')
    total_adeudado = fields.Monetary(string='Total adeudado', compute='_compute_deuda')

    cancelar_todo = fields.Boolean(
        string='Cancelar todo el crédito', default=True,
        help='Paga el total adeudado (capital + moras). Desmarque para abonar un monto parcial.')
    monto = fields.Monetary(string='Monto a pagar')

    def _deuda(self):
        """(cuotas pendientes, capital, mora) al pagar en `payment_date`, con los
        mismos criterios que aplica la cascada de pagos."""
        self.ensure_one()
        masivas = self.env[MASIVAS]
        company_id = self.cuenta_id.company_id.id
        cantidad, capital, mora = 0, 0.0, 0.0
        for cuota in self._cuotas():
            saldo = cuota.saldo or 0.0
            mora_registrada = masivas._get_mora_pendiente_amount(cuota)
            if saldo > 0 and mora_registrada <= 0:
                mora_cuota = masivas._get_mora_para_nuevo_pago(cuota, self.payment_date, company_id)[0]
            else:
                mora_cuota = mora_registrada
            if saldo <= 0 and mora_cuota <= 0:
                continue
            cantidad += 1 if saldo > 0 else 0
            capital += max(saldo, 0.0)
            mora += mora_cuota
        return cantidad, round(capital, 2), round(mora, 2)

    def _cuotas(self):
        return self.env['adt.comercial.cuotas'].search(
            [('cuenta_id', '=', self.cuenta_id.id)], order='parent_sort_id asc, id asc')

    @api.depends('cuenta_id', 'payment_date')
    def _compute_deuda(self):
        for wizard in self:
            if not wizard.cuenta_id:
                wizard.update({'cuotas_pendientes': 0, 'capital_pendiente': 0.0,
                               'mora_pendiente': 0.0, 'total_adeudado': 0.0})
                continue
            cantidad, capital, mora = wizard._deuda()
            wizard.cuotas_pendientes = cantidad
            wizard.capital_pendiente = capital
            wizard.mora_pendiente = mora
            wizard.total_adeudado = round(capital + mora, 2)

    @api.onchange('cancelar_todo', 'payment_date', 'cuenta_id')
    def _onchange_cancelar_todo(self):
        if self.cancelar_todo:
            self.monto = self.total_adeudado

    def action_pagar(self):
        self.ensure_one()
        _cantidad, capital, mora = self._deuda()
        total = round(capital + mora, 2)
        monto = total if self.cancelar_todo else round(self.monto or 0.0, 2)

        if total <= 0:
            raise UserError(_('La cuenta no tiene deuda pendiente.'))
        if monto <= 0:
            raise UserError(_('El monto a pagar debe ser mayor que cero.'))
        if monto > total:
            raise UserError(_('El monto a pagar (S/ %.2f) no puede ser mayor al total adeudado (S/ %.2f).')
                            % (monto, total))

        numero_operacion = self.numero_operacion.strip()
        primera = self._cuotas()[:1]
        _logger.info('[CancelarCredito] Cuenta %s | Monto S/ %.2f | Total adeudado S/ %.2f | Ref %s',
                     self.cuenta_id.display_name, monto, total, numero_operacion)
        cuotas_pagadas, excedente = self.env[MASIVAS]._registrar_pago(
            primera, monto, self.payment_date, numero_operacion)

        detalle = Markup('').join(Markup('<li>%s</li>') % c for c in cuotas_pagadas)
        cuerpo = Markup('<p><b>%s</b> por S/ %.2f (operación %s, fecha %s).</p><ul>%s</ul>') % (
            _('Crédito cancelado') if monto == total else _('Pago en cascada'),
            monto, numero_operacion, self.payment_date, detalle)
        if excedente > 0:
            cuerpo += Markup('<p>%s</p>') % (_('Excedente no aplicado: S/ %.2f') % excedente)
        self.cuenta_id.message_post(body=cuerpo)

        mensaje = _('Se aplicaron S/ %.2f en %d cuota(s).') % (monto - excedente, len(cuotas_pagadas))
        if excedente > 0:
            mensaje += _(' Quedó un excedente sin aplicar de S/ %.2f.') % excedente
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pago registrado'),
                'message': mensaje,
                'type': 'warning' if excedente > 0 else 'success',
                'sticky': excedente > 0,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
