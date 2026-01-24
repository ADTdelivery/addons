from datetime import timedelta, datetime, date
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, RedirectWarning, UserError
import xmlrpc.client
from odoo.http import request

import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    mora = fields.Float(string="Mora")
    mora_state = fields.Selection(
        [('paid', 'Mora pagada'), ('pending', 'Mora pendiente')],
        string="Estado de mora",
        default='pending'
    )
    mora_operacion = fields.Char(string="# Operación")
    mora_dias = fields.Integer(string="Días de mora")  # 👈 NUEVO
    mora_payment_date = fields.Date(string="Fecha pago de mora")  # <-- new field

class ADTComercialCuotas(models.Model):
    _name = "adt.comercial.cuotas"
    _description = "ADT Módulo comercial - Cuotas"
    _order = "parent_sort_id asc, id asc"
    
    parent_id = fields.Many2one('adt.comercial.cuotas', string="Cuota padre", index=True)
    child_ids = fields.One2many('adt.comercial.cuotas', 'parent_id', string="Subcuotas")
    es_subcuota = fields.Boolean(default=False)
    
    parent_sort_id = fields.Integer(compute="_compute_parent_sort",store=True)

    @api.depends('parent_id')
    def _compute_parent_sort(self):
        for r in self:
            r.parent_sort_id = r.parent_id.id if r.parent_id else r.id

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency",
                                  string="Company Currency", readonly=True, related="company_id.currency_id")

    cuenta_id = fields.Many2one("adt.comercial.cuentas", string="Cuenta id")
    name = fields.Char(string="# Cuota")

    # fecha_cierre = fields.Date(
    #     string="Fecha de cierre", default=fields.Date.today)
    monto = fields.Monetary(string="Monto de cuota")

    fecha_cronograma = fields.Date(
        string="Fecha de cronograma", default=fields.Date.today)
    fecha_compromiso = fields.Date(string="Fecha compromiso")

    resumen_pagos = fields.Html("Resumen de pagos")
    resumen_observaciones = fields.Html(
        "Resumen observaciones", compute="_compute_resumen_observaciones", store=True)

    real_date = fields.Char(string="Fecha de pago")

    numero_operacion = fields.Char(string="# Operación")

    periodicidad = fields.Char(string="Periodo")
    
    x_asesora = fields.Char(string='Asesora')
    
    mora_total = fields.Float(string="Mora total",compute="_compute_mora_total",store=True)
    
    mora_pendiente = fields.Float(string="Mora pendiente",compute="_compute_mora_total",store=True)
    
    mora_estado_texto = fields.Char(string="Estado de mora",compute="_compute_mora_total",store=True)

    mora_operacion = fields.Char(
        string="N° Operación Mora",
        compute="_compute_mora_total",
        store=True
    )

    mora_dias = fields.Integer(string="Días de mora",compute="_compute_mora_total",store=True)

    @api.model
    def _change_real_date(self):
        for data in self:
            print(str(data.cuota_ids))
            for cuota in data.cuota_ids:
                account_payment = request.env['account.payment'].search([('cuota_id', '=', cuota.id)]).read([
                    'move_id',
                ])
                print(account_payment)
                if len(account_payment) > 0:
                    account_move = request.env['account.move'].search(
                        [('id', '=', account_payment[0]['move_id'][0])]).read([
                        'date',
                        'ref'
                    ])
                    cuota.real_date = str(account_move[0]['date'])
                    cuota.numero_operacion = str(account_move[0]['ref'])

                else:
                    cuota.real_date = ""
                    cuota.numero_operacion = ""

    @api.depends('observacion_ids')
    def _compute_resumen_observaciones(self):
        for record in self:
            html = "<ul>"
            for obs in record.observacion_ids:
                html += "<li>" + obs.comentario + "</li>"
            html += "</ul>"
            record.resumen_observaciones = html

    payment_ids = fields.One2many(
        "account.payment", "cuota_id", string="Pagos")
    type = fields.Selection(
        [('cuota', 'Cuota'), ('mora', 'Mora')], default='cuota')

    @api.depends('payment_ids')
    def _compute_saldo(self):
        for record in self:
            record.saldo = record.monto - \
                           sum(record.payment_ids.mapped('amount'))

    @api.depends('payment_ids', 'cuenta_id.state')
    def _compute_state(self):
        for record in self:
            if len(record.payment_ids) > 0:
                if record.monto == sum(record.payment_ids.mapped('amount')):
                    record.state = 'pagado'
                elif (sum(record.payment_ids.mapped('amount')) > 0) and (
                        sum(record.payment_ids.mapped('amount')) < record.monto):
                    record.state = 'a_cuenta'
            else:
                if record.fecha_cronograma < date.today():
                    record.state = 'retrasado'
                elif record.cuenta_id.state == 'cancelado':
                    record.state = 'anulada'
                else:
                    record.state = 'pendiente'

    state = fields.Selection([("pendiente", "Pendiente"), ("a_cuenta", "A cuenta"), ("retrasado", "Retrasado"), (
        "pagado", "Pagado"), ("anulada", "Anulada")], string="Estado", compute="_compute_state", store=True)
    saldo = fields.Monetary(
        string="Saldo", compute="_compute_saldo", store=True)

    observacion_ids = fields.One2many(
        "adt.comercial.observaciones", "cuota_id", string="Observaciones")

    def action_register_payment(self):
        return {
            'name': _('Register Payment'),
            'res_model': 'adt.register.payment',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuotas',
                'active_ids': self.ids,
                'default_amount': self.saldo,
                'default_communication': self.name,
                'default_cuota_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def registrar_observacion(self):
        return {
            'name': 'Registrar observaciones',
            'res_model': 'adt.registrar.observacion',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuotas',
                'default_cuota_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    @api.model
    def prueba_data_2(self):
        print("Row data")

    def action_delete_payment(self):
        return {
            'name': _('Delete Payment'),
            'res_model': 'adt.warning.message',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuotas',
                'active_ids': self.ids,
                'default_amount': self.saldo,
                'default_communication': self.name,
                'default_cuota_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    @api.depends(
        'payment_ids',
        'payment_ids.mora',
        'payment_ids.mora_state',
        'payment_ids.mora_operacion'
    )
    def _compute_mora_total(self):
        for record in self:
            mora_total = 0.0
            mora_pendiente = 0.0
            total_dias = 0
            tiene_pendiente = False

            ultima_operacion = False

            for p in record.payment_ids:
                mora = p.mora or 0.0
                mora_total += mora
                total_dias += p.mora_dias or 0

                if p.mora_state == 'pending':
                    mora_pendiente += mora
                    tiene_pendiente = True
                    # priorizar operación pendiente
                    if p.mora_operacion:
                        ultima_operacion = p.mora_operacion
                else:
                    # si no hay pendiente, tomar la última pagada
                    if p.mora_operacion and not ultima_operacion:
                        ultima_operacion = p.mora_operacion

            record.mora_total = mora_total
            record.mora_pendiente = mora_pendiente
            record.mora_dias = total_dias
            record.mora_operacion = ultima_operacion or ''

            # Texto de estado
            if mora_total == 0:
                record.mora_estado_texto = 'Sin mora'
            elif tiene_pendiente:
                record.mora_estado_texto = 'Pendiente'
            else:
                record.mora_estado_texto = 'Pagado'

    def action_pagar_mora(self):
        self.ensure_one()
        return {
            'name': 'Pagar mora',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.pagar.mora.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_cuota_id': self.id,
                'default_amount': self.mora_pendiente,
            }
            }




class ADTComercialWarningMessage(models.TransientModel):
    _name = "adt.warning.message"
    _description = "ADT Warning messages"

    message = fields.Text(string="Esta seguro que desea eliminar el pago?", readonly=True, store=True)
    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")

    def action_delete_payment(self):
        data = self.env['account.payment'].search([('cuota_id', '=', self.cuota_id.id)])
        data.unlink()


class ADTComercialRegisterPayment(models.TransientModel):
    _name = "adt.register.payment"
    _description = "ADT Registro de pagos"

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency",
                                  string="Company Currency", readonly=True, related="company_id.currency_id")
    payment_date = fields.Date(
        string="Payment Date", required=True, default=fields.Date.context_today)
    amount = fields.Monetary(currency_field='currency_id', readonly=False)
    communication = fields.Char(string="Memo", readonly=False)
    journal_id = fields.Many2one('account.journal', store=True, readonly=False,
                                 compute='_compute_journal_id',
                                 domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]")
    payment_type = fields.Selection(
        [('outbound', 'Send Money'), ('inbound', 'Receive Money'), ], string='Payment Type', default='inbound')

    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")
    
    mora = fields.Float(string="Mora", compute="_compute_mora", readonly=False)
    
    mora_state = fields.Selection([('paid', 'Mora pagada'),('pending', 'Mora pendiente')],string="Estado de mora",default='pending',required=True)

    mora_dias = fields.Integer(string="Días de mora",compute="_compute_mora",store=True)

    def _generate_subcuota_name(self):
        self.ensure_one()

        parent = self.parent_id or self

        count = self.search_count([
            ('parent_id', '=', parent.id)
        ]) + 1

        return f"{parent.name}-{count}"


    @api.depends('company_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', wizard.company_id.id),
            ], limit=1)

    def action_create_payments(self):
        _logger = logging.getLogger(__name__)
        general_saldo = self.cuota_id.saldo

        # 1️⃣ Validar número de operación duplicado
        payment_exist = self.env['account.payment'].search(
            [('ref', '=', self.communication)], limit=1
        )

        if payment_exist:
            cuota = payment_exist.cuota_id
            raise UserError(
                'Ya existe un pago con el mismo número de operación.\n\n'
                'Usuario: %s' % cuota.cuenta_id.display_name
            )

        _logger.info("====== REGISTRO DE PAGO INICIADO ======")
        _logger.info("Cuota ID: %s", self.cuota_id.id)
        _logger.info("Monto ingresado: %s", self.amount)
        _logger.info("Fecha pago: %s", self.payment_date)
        _logger.info("Monto de la cuota actual: %s", self.cuota_id.monto)
        _logger.info("Saldo de la cuota actual: %s", self.cuota_id.saldo)

        # 2️⃣ Crear payment Odoo
        data = {
            'payment_type': self.payment_type,
            'journal_id': self.journal_id.id,
            'cuota_id': self.cuota_id.id,
            'ref': self.communication,
            'amount': self.amount,
            'date': self.payment_date,
            'partner_id': self.cuota_id.cuenta_id.partner_id.id,
            'mora': self.mora,
            'mora_state': self.mora_state,
            'mora_operacion': self.communication if self.mora_state == 'paid' else False,
            'mora_dias': self.mora_dias,
            'mora_payment_date': self.payment_date if self.mora_state == 'paid' else False,  # <-- set here
        }

        _logger.info("Datos payment: %s", data)

        try:
            payment = self.env['account.payment'].create(data)
            payment.action_post()

            _logger.info("Payment creado ID=%s", payment.id)

            cuota = self.cuota_id.sudo()

            saldo_actual = general_saldo
            monto_pagado = self.amount

            _logger.info("Saldo actual cuota: %s", saldo_actual)
            _logger.info("Monto pagado: %s", monto_pagado)

            # 3️⃣ Pago parcial → crear subcuota
            if monto_pagado < saldo_actual:

                restante = saldo_actual - monto_pagado

                _logger.info("Pago parcial detectado")
                _logger.info("Restante a pagar: %s", restante)

                # 🔥 ACTUALIZAR CUOTA ORIGINAL
                cuota.write({
                    'monto': monto_pagado,
                    'saldo': 0,
                    'state': 'pagado'
                })

                parent = cuota.parent_id or cuota

                num_sub = len(parent.child_ids) + 1
                sub_name = f"{parent.name}-{num_sub}"

                nueva_cuota = self.env['adt.comercial.cuotas'].sudo().create({
                    'name': sub_name,
                    'cuenta_id': cuota.cuenta_id.id,
                    'monto': restante,
                    'saldo': restante,
                    'fecha_cronograma': self.payment_date,  # 👈 fecha actual
                    'periodicidad': cuota.periodicidad,
                    'parent_id': parent.id,
                    'type': 'cuota',
                })

                _logger.info("Subcuota creada correctamente ID=%s monto=%s", nueva_cuota.id, restante)            

            # 4️⃣ Pago completo
            elif monto_pagado == saldo_actual:

                cuota.write({'state': 'pagado'})
                _logger.info("Pago completo de cuota")

            else:
                raise UserError("El monto pagado no puede ser mayor al saldo.")

            # 5️⃣ Recalcular moras
            cuota.invalidate_cache()
            cuota._compute_mora_total()

            _logger.info("Recompute de mora ejecutado")

            _logger.info("====== FIN REGISTRO DE PAGO ======")

        except Exception as e:
            _logger.exception("ERROR registrando pago")
            raise

    @api.depends('payment_date', 'cuota_id.fecha_cronograma', 'cuota_id.payment_ids.mora')
    def _compute_mora(self):
        default_factor = float(self.env['ir.config_parameter'].sudo()
                               .get_param('adt_comercial.mora_factor', 2))
        for record in self:
            record.mora = 0.0
            record.mora_dias = 0

            if not (record.payment_date and record.cuota_id and record.cuota_id.fecha_cronograma):
                continue

            fecha_pago = record.payment_date
            fecha_cronograma = record.cuota_id.fecha_cronograma
            diff_days = (fecha_pago - fecha_cronograma).days

            if diff_days <= 0:
                continue

            # load up to two factor records for the company, ordered deterministically by id
            factors = self.env['adt.cobranza.config.factor'].sudo().search(
                [('company_id', '=', record.company_id.id)],
                order='id asc',
                limit=2
            )

            # count previous payments on the cuota that already had mora (> 0)
            # ensure we count only actual stored payments (not the transient wizard)
            previous_mora_payments = record.cuota_id.cuenta_id.cuota_ids.filtered(lambda p: p.mora_total > 0.0)
            previous_mora_count = len(previous_mora_payments)

            # choose factor by occurrence: 0 -> first factor, 1 -> second factor, etc.
            if not factors:
                factor = default_factor
            else:
                index = min(previous_mora_count, len(factors) - 1)
                factor = float(factors[index].factor_mora)

            record.mora_dias = diff_days
            record.mora = diff_days * factor


class ADTRegistrarObservacion(models.TransientModel):
    _name = "adt.registrar.observacion"
    _description = "ADT Registro de observaciones"

    fecha = fields.Date(string="Fecha", default=fields.Date.today)
    comentario = fields.Text(string='Comentario')
    attachment_ids = fields.Many2many("ir.attachment", string="Adjuntos")

    cuota_id = fields.Many2one('adt.comercial.cuotas', string="Id de cuota")

    def action_create_observacion(self):
        observacion = self.env['adt.comercial.observaciones'].create({
            'cuota_id': self.cuota_id.id,
            'comentario': self.comentario,
            'fecha': self.fecha,
            'attachment_ids': self.attachment_ids,
        })


class ADTPagarMoraWizard(models.TransientModel):
    _name = 'adt.pagar.mora.wizard'
    _description = 'Pago de Mora'

    cuota_id = fields.Many2one('adt.comercial.cuotas', required=True)
    amount = fields.Float(string="Monto mora", required=True)
    payment_date = fields.Date(default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal',
        domain="[('type','in',('bank','cash'))]",
        required=True
    )
    mora_operacion = fields.Char(string="N° Operación")

    def action_confirm_pagar_mora(self):
        self.ensure_one()
        pagos_pendientes = self.cuota_id.payment_ids.filtered(lambda p: p.mora > 0 and p.mora_state == 'pending')
        
        if not pagos_pendientes:
            raise UserError("No hay mora pendiente para pagar.")
            
        # Marcar como pagada (NO crear nuevo payment)
        pagos_pendientes.write({'mora_state': 'paid', 'mora_operacion': self.mora_operacion,'mora_payment_date': self.payment_date})
        
        # Forzar recálculo en cuota
        self.cuota_id.invalidate_cache()
        self.cuota_id._compute_mora_total()
        
        return {'type': 'ir.actions.act_window_close'}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mora_factor = fields.Float(
        string="Factor de mora por día",
        config_parameter='adt_comercial.mora_factor',
        default=2.0
    )

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'adt_comercial.mora_factor',
            self.mora_factor
        )

    def get_values(self):
        res = super().get_values()
        param = self.env['ir.config_parameter'].sudo().get_param(
            'adt_comercial.mora_factor',
            default=2.0
        )
        res.update(
            mora_factor=float(param)
        )
        return res
# python
class ADTComercialCuotas(models.Model):
    _inherit = "adt.comercial.cuotas"

    mora_last_payment_date = fields.Date(
        string="Fecha de pago",
        compute="_compute_mora_last_payment_date",
        store=True,
    )

    @api.depends('payment_ids.mora', 'payment_ids.mora_payment_date')
    def _compute_mora_last_payment_date(self):
        for rec in self:
            pagos = rec.payment_ids.filtered(lambda p: p.mora > 0 and p.mora_payment_date)
            if not pagos:
                rec.mora_last_payment_date = False
                continue
            # pick the latest date (ISO string comparison is safe here)
            dates = pagos.mapped('mora_payment_date')
            rec.mora_last_payment_date = max(dates)