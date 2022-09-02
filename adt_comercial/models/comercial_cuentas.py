from datetime import timedelta, datetime, date
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, RedirectWarning, UserError

import math
import logging

_logger = logging.getLogger(__name__)


class ADTComercialCuentas(models.Model):
    _name = "adt.comercial.cuentas"
    _description = "ADT Módulo comercial - Cuentas"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    reference_no = fields.Char(
        string='Referencia', required=True, readonly=True, default=lambda self: _('Nuevo'))
    state = fields.Selection(
        [("borrador", "Borrador"), ("aprobado", "Aprobado"), ("en_curso", "En curso"), ("cancelado", "Cancelado"),
         ("pagado", "Pagado")], default="borrador", string="Estado", tracking=1)

    def aprobar_cuenta(self):
        for cuenta in self:
            cuenta.write({'state': 'aprobado', 'reference_no': self.env['ir.sequence'].next_by_code(
                'comercial.cuentas')})
            cuenta.vehiculo_id.write({'disponible': False})
            cuenta.generar_cuotas()

    def cancelar_cuenta(self):
        for cuenta in self:
            cuenta.write({'state': 'cancelado'})
            cuenta.vehiculo_id.write({'disponible': True})

    def recuperar_vehiculo(self):
        for cuenta in self:
            cuenta.write({'recuperado': True})
            cuenta.cancelar_cuenta()

    def restablecer_vehiculo(self):
        for cuenta in self:
            cuenta.write({'recuperado': False, 'state': 'en_curso'})
            cuenta.vehiculo_id.write({'disponible': False})

    @api.depends('state')
    def name_get(self):
        result = []
        for cuenta in self:
            name = cuenta.reference_no + " - " + cuenta.partner_id.name

            result.append((cuenta.id, name))
        return result

    partner_id = fields.Many2one("res.partner", "Socio", tracking=2)
    mobile = fields.Char(related="partner_id.phone_sanitized")
    user_id = fields.Many2one(
        "res.users", string="Asesor", default=lambda self: self.env.user)

    fecha_desembolso = fields.Date(
        string="Fecha de desembolso", default=fields.Date.today)
    fecha_entrega = fields.Date(
        string="Fecha de entrega", default=fields.Date.today)

    fecha_cierre = fields.Integer(string="Fecha de cierre", default=1)

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency",
                                  string="Company Currency", readonly=True, related="company_id.currency_id")

    periodicidad = fields.Selection(
        [('semanal', 'Semanal'), ('quincena', 'Quincenal'), ('mensual', 'Mensual')], default="quincena",
        string="Periodo")
    monto_total = fields.Monetary(string="Valor total del vehículo", default=0)
    # monto_financiado = fields.Monetary(string="Monto financiado", default=0)
    monto_inicial = fields.Monetary(string="Inicial", default=0)

    monto_fraccionado = fields.Monetary(string="Monto fraccionado", default=0)
    cuota_gracia = fields.Monetary(string="Cuota de gracia", default=0)
    fecha_gracia = fields.Date(
        string="Fecha de gracia", default=fields.Date.today)

    # @api.depends('monto_financiado', 'monto_inicial')
    # def _compute_monto_total(self):
    #     for record in self:
    #         record.monto_total = record.monto_financiado + record.monto_inicial

    # @api.onchange('monto_inicial')
    # def _compute_monto_financiado(self):
    #     for record in self:
    #         record.monto_financiado = record.monto_total - record.monto_inicial

    # @api.onchange('monto_financiado')
    # def _compute_monto_inicial(self):
    #     for record in self:
    #         record.monto_inicial = record.monto_total - record.monto_financiado

    # def create(self):

    # def write(self):

    qty_cuotas = fields.Integer(string="Total de cuotas", default=24)
    monto_cuota = fields.Monetary(string="Monto de cuota", default=0)

    vehiculo_id = fields.Many2one("fleet.vehicle", string="Moto")
    moto_marca = fields.Char(
        string="Marca", related="vehiculo_id.model_id.brand_id.name")
    moto_modelo = fields.Char(
        string="Modelo", related="vehiculo_id.model_id.name")
    moto_chasis = fields.Char(string="Chasis", related="vehiculo_id.vin_sn")
    moto_tarjeta = fields.Char(string="Tarjeta de propiedad")
    moto_placa = fields.Char(string="Número de placa",
                             related="vehiculo_id.license_plate")
    gps_chip = fields.Char(string="GPS Chip")
    gps_activo = fields.Boolean(string="GPS activo")
    soat_activo = fields.Boolean(string="SOAT")

    cuotas_saldo = fields.Monetary(
        string="Saldo restante", compute="_compute_pagado_restante")
    cuotas_pagado = fields.Monetary(
        string="Total pagado", compute="_compute_pagado_restante")
    qty_cuotas_restantes = fields.Integer(
        string="Cuotas restantes", compute="_compute_qty_cuotas")
    qty_cuotas_pagadas = fields.Integer(
        string="Cuotas pagadas", compute="_compute_qty_cuotas")

    recuperado = fields.Boolean(string="Recuperado", readonly=True)

    @api.depends('cuota_ids')
    def _compute_pagado_restante(self):
        self.cuotas_saldo = sum(self.cuota_ids.filtered(
            lambda x: x.state in ['pendiente', 'retrasado', 'a_cuenta'] and x.type == 'cuota').mapped('saldo'))

        # if self.cuotas_saldo == 0 and self.state == 'en_curso':
        #     self.write({'state': 'pagado'})

        self.cuotas_pagado = sum(self.cuota_ids.filtered(
            lambda x: x.state == 'pagado').mapped('monto'))
        # self.cuotas_pagado = (self.monto_financiado - self.monto_inicial)-self.cuotas_saldo

    @api.depends('cuota_ids')
    def _compute_qty_cuotas(self):
        self.qty_cuotas_restantes = len(self.cuota_ids.filtered(
            lambda x: x.state in ['pendiente', 'retrasado', 'a_cuenta'] and x.type == 'cuota'))
        pagadas = len(self.cuota_ids.filtered(
            lambda x: x.state == 'pagado' and x.type == 'cuota'))
        self.qty_cuotas_pagadas = pagadas

        if (pagadas > 0) and self.state != 'cancelado':
            self.state = 'en_curso'

        if (len(self.cuota_ids) > 0) and (
                len(self.cuota_ids.filtered(lambda x: x.state == 'pagado')) == len(self.cuota_ids)):
            self.state = 'pagado'

    cuota_ids = fields.One2many(
        "adt.comercial.cuotas", "cuenta_id", string="Pagos")

    attachment_ids = fields.Many2many("ir.attachment", string="Adjuntos")

    def refinanciar_cuotas(self):
        return {
            'name': "Refinanciar",
            'res_model': 'adt.registrar.refinanciamiento',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuentas',
                # 'active_ids': self.ids,
                # 'default_amount': self.monto,
                # 'default_fecha': date.today(),
                'default_monto_refinanciado': self.cuotas_saldo,
                'default_cuenta_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def agregar_mora(self):
        return {
            'name': 'Registrar mora',
            'res_model': 'adt.registrar.mora',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.comercial.cuentas',
                # 'active_ids': self.ids,
                # 'default_amount': self.monto,
                # 'default_fecha': date.today(),

                'default_cuenta_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def generar_cuotas(self):
        if self.monto_fraccionado <= 0:
            raise UserError(
                'Se debe establecer el monto fraccionado para continuar.')

        if self.monto_cuota <= 0 and self.qty_cuotas <= 0:
            raise UserError(
                'Se debe establecer el número de cuotas o el monto de la cuota para generar el cronograma.')

        monto_fraccionado = self.monto_fraccionado if self.monto_fraccionado else 0
        qty_cuotas = self.qty_cuotas if self.qty_cuotas else 0
        monto_cuota = self.monto_cuota if self.monto_cuota else 0
        cuota_gracia = self.cuota_gracia if self.cuota_gracia else 0

        if self.periodicidad == 'semanal':
            days = 7
        if self.periodicidad == 'quincena':
            days = 15
        elif self.periodicidad == 'mensual':
            days = 30

        a = []
        fecha_inicial = self.fecha_gracia + timedelta(days=0)

        # ? ASIGNACION DE CUOTAS
        a.append(self.env["adt.comercial.cuotas"].create(
            {'name': 'Cuota 0', 'monto': cuota_gracia, 'fecha_cronograma': self.fecha_gracia}).id)

        if monto_cuota == 0:
            monto_cuota_mod = (monto_fraccionado - cuota_gracia) % qty_cuotas

            if monto_cuota_mod > 0:
                monto_cuota_temp = (
                                           (monto_fraccionado - cuota_gracia) - monto_cuota_mod) / qty_cuotas
            else:
                monto_cuota_temp = (monto_fraccionado -
                                    cuota_gracia) / qty_cuotas

            self.monto_cuota = monto_cuota_temp

            for i in range(qty_cuotas):
                fecha_inicial = fecha_inicial + timedelta(days=days)

                if i == (qty_cuotas - 1):
                    monto_cuota_temp += monto_cuota_mod

                a.append(self.env["adt.comercial.cuotas"].create(
                    {'name': 'Cuota ' + str(i + 1), 'monto': monto_cuota_temp, 'fecha_cronograma': fecha_inicial}).id)

        else:
            total_temp = qty_cuotas * monto_cuota
            # if total_temp > monto_financiado:
            #     raise UserError(
            #         'El monto calculado [cuotas * monto] es mayor al saldo a pagar. Por favor corrija la cantidad de cuotas o el monto.')

            # ? ASIGNACION DE CUOTAS
            for i in range(qty_cuotas):
                fecha_inicial = fecha_inicial + timedelta(days=days)

                if i == (qty_cuotas - 1):
                    monto_cuota += ((monto_fraccionado -
                                     cuota_gracia) - total_temp)

                a.append(self.env["adt.comercial.cuotas"].create(
                    {'name': 'Cuota ' + str(i + 1), 'monto': monto_cuota, 'fecha_cronograma': fecha_inicial}).id)

        self.cuota_ids = [(6, 0, a)]

    def get_cronograma_report(self, cuenta):
        self.env.cr.execute("""
            select
                acc.name as cuota,
                TO_CHAR(acc.fecha_cronograma :: DATE, 'dd/mm/yyyy') as fecha_cronograma,
                round(coalesce(acc.monto, 0),2) as monto_cuota,
                round(coalesce(ap.amount, 0),2) as monto_pagado,
                TO_CHAR(coalesce(am.date, acc.fecha_cronograma) :: DATE, 'dd/mm/yyyy') as fecha_pago,
                coalesce(am.ref, 'Pendiente') as operacion,
                acc.resumen_observaciones as observaciones
            from adt_comercial_cuotas acc
            left join account_payment ap on acc.id=ap.cuota_id 
            left join account_move am on ap.move_id=am.id
            where acc.cuenta_id={}
            order by acc.fecha_cronograma
            """.format(cuenta))

        result = self.env.cr.dictfetchall()
        return result

    # def generar_cuotas(self):

    #     if self.monto_financiado <= 0:
    #         raise UserError(
    #             'Se debe establecer el monto financiado para continuar.')

    #     if self.monto_cuota <= 0 and self.qty_cuotas <= 0:
    #         raise UserError(
    #             'Se debe establecer el número de cuotas o el monto de la cuota para generar el cronograma.')

    #     monto_financiado = self.monto_financiado if self.monto_financiado else 0
    #     qty_cuotas = self.qty_cuotas if self.qty_cuotas else 0
    #     monto_cuota = self.monto_cuota if self.monto_cuota else 0

    #     if self.periodicidad == 'semanal':
    #         days = 7
    #     if self.periodicidad == 'quincena':
    #         days = 15
    #     elif self.periodicidad == 'mensual':
    #         days = 30

    #     a = []
    #     fecha_inicial = self.fecha_desembolso+timedelta(days=days)

    #     if monto_cuota == 0:
    #         monto_cuota_mod = monto_financiado % qty_cuotas

    #         if monto_cuota_mod > 0:
    #             monto_cuota_temp = (
    #                 monto_financiado-monto_cuota_mod)/qty_cuotas
    #         else:
    #             monto_cuota_temp = monto_financiado/qty_cuotas

    #         self.monto_cuota = monto_cuota_temp

    #         # ? ASIGNACION DE CUOTAS
    #         for i in range(qty_cuotas):
    #             fecha_inicial = fecha_inicial+timedelta(days=days)

    #             if i == (qty_cuotas-1):
    #                 monto_cuota_temp += monto_cuota_mod

    #             a.append(self.env["adt.comercial.cuotas"].create(
    #                 {'name': 'Cuota '+str(i+1), 'monto': monto_cuota_temp, 'fecha_cronograma': fecha_inicial}).id)

    #     elif qty_cuotas == 0:
    #         qty_cuotas = math.floor(monto_financiado/monto_cuota)
    #         total_temp = qty_cuotas*monto_cuota

    #         self.qty_cuotas = qty_cuotas

    #         # ? ASIGNACION DE CUOTAS
    #         for i in range(qty_cuotas):
    #             fecha_inicial = fecha_inicial+timedelta(days=days)

    #             if i == (qty_cuotas-1):
    #                 monto_cuota += (monto_financiado-total_temp)

    #             a.append(self.env["adt.comercial.cuotas"].create(
    #                 {'name': 'Cuota '+str(i+1), 'monto': monto_cuota, 'fecha_cronograma': fecha_inicial}).id)
    #     else:
    #         total_temp = qty_cuotas*monto_cuota
    #         if total_temp > monto_financiado:
    #             raise UserError(
    #                 'El monto calculado [cuotas * monto] es mayor al saldo a pagar. Por favor corrija la cantidad de cuotas o el monto.')

    #         # ? ASIGNACION DE CUOTAS
    #         for i in range(qty_cuotas):
    #             fecha_inicial = fecha_inicial+timedelta(days=days)

    #             if i == (qty_cuotas-1):
    #                 monto_cuota += (monto_financiado-total_temp)

    #             a.append(self.env["adt.comercial.cuotas"].create(
    #                 {'name': 'Cuota '+str(i+1), 'monto': monto_cuota, 'fecha_cronograma': fecha_inicial}).id)

    #     self.cuota_ids = [(6, 0, a)]


class ADTRegistrarMora(models.TransientModel):
    _name = "adt.registrar.mora"
    _description = "ADT Registro de mora"

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency",
                                  string="Company Currency", readonly=True, related="company_id.currency_id")
    fecha_cronograma = fields.Date(
        string="Fecha de cronograma", default=fields.Date.today)
    amount = fields.Monetary(currency_field='currency_id', readonly=False)
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string="Id de cuenta")

    def action_create_mora(self):
        if self.amount <= 0:
            raise UserError("El monto de mora no puede ser '0'.")
        # if self.fecha_cronograma < (datetime.now()-timedelta(hours=5)):
        #     raise UserError(
        #         "La fecha programada no puede ser anterior a la fecha actual.")
        cuota = self.env['adt.comercial.cuotas'].create({
            'type': 'mora',
            'cuenta_id': self.cuenta_id.id,
            'monto': self.amount,
            'fecha_cronograma': self.fecha_cronograma,
            'name': 'Mora'
        })


class ADTRegistrarRefinanciamiento(models.TransientModel):
    _name = "adt.registrar.refinanciamiento"
    _description = "ADT Registro de refinanciamiento"

    company_id = fields.Many2one("res.company", string="Company",
                                 required=True, readonly=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        "res.currency", string="Company Currency", readonly=True, related="company_id.currency_id")
    monto_refinanciado = fields.Monetary(
        currency_field='currency_id', readonly=True)
    monto_adicional = fields.Monetary(currency_field='currency_id')
    monto_cuota = fields.Monetary(currency_field='currency_id')
    qty_cuotas = fields.Integer(string="# de cuotas")
    fecha_refinanciamiento = fields.Date(
        string="Fecha de refinanciamiento", required="1")

    cuenta_id = fields.Many2one('adt.comercial.cuentas', string="Id de cuenta")

    def action_create_cuotas(self):
        global days
        for sin_pagar in self.cuenta_id.cuota_ids.filtered(lambda x: x.state in ['pendiente', 'a_cuenta', 'retrasado']):
            if sin_pagar.state == 'a_cuenta':
                sin_pagar.monto = sum(sin_pagar.payment_ids.mapped('amount'))
                sin_pagar.saldo = 0
                sin_pagar.state = 'pagado'
            else:
                sin_pagar.unlink()
        # ?

        if self.monto_cuota <= 0 and self.qty_cuotas <= 0:
            raise UserError(
                'Se debe establecer el número de cuotas o el monto de la cuota para generar el cronograma.')

        qty_cuotas = self.qty_cuotas if self.qty_cuotas else 0
        monto_cuota = self.monto_cuota if self.monto_cuota else 0
        total_a_pagar = self.monto_refinanciado + self.monto_adicional

        if self.cuenta_id.periodicidad == 'semanal':
            days = 7
        if self.cuenta_id.periodicidad == 'quincena':
            days = 15
        elif self.cuenta_id.periodicidad == 'mensual':
            days = 30

        a = []
        fecha_inicial = self.fecha_refinanciamiento  # +timedelta(days=days)

        if monto_cuota == 0:
            monto_cuota_mod = total_a_pagar % qty_cuotas

            if monto_cuota_mod > 0:
                monto_cuota_temp = (total_a_pagar - monto_cuota_mod) / qty_cuotas
            else:
                monto_cuota_temp = total_a_pagar / qty_cuotas

            self.monto_cuota = monto_cuota_temp

            # ? ASIGNACION DE CUOTAS
            for i in range(qty_cuotas):
                fecha_inicial = fecha_inicial + timedelta(days=days)

                if i == (qty_cuotas - 1):
                    monto_cuota_temp += monto_cuota_mod

                new_cuota = self.env["adt.comercial.cuotas"].create(
                    {'name': 'Cuota R. - ' + str(i + 1), 'monto': monto_cuota_temp,
                     'fecha_cronograma': fecha_inicial}).id
                self.cuenta_id.cuota_ids = [(4, new_cuota)]

        elif qty_cuotas == 0:
            qty_cuotas = math.floor(total_a_pagar / monto_cuota)
            total_temp = qty_cuotas * monto_cuota

            self.qty_cuotas = qty_cuotas

            # ? ASIGNACION DE CUOTAS
            for i in range(qty_cuotas):
                fecha_inicial = fecha_inicial + timedelta(days=days)

                if i == (qty_cuotas - 1):
                    monto_cuota += (total_a_pagar - total_temp)

                new_cuota = self.env["adt.comercial.cuotas"].create(
                    {'name': 'Cuota R. - ' + str(i + 1), 'monto': monto_cuota, 'fecha_cronograma': fecha_inicial}).id
                self.cuenta_id.cuota_ids = [(4, new_cuota)]
        else:
            total_temp = qty_cuotas * monto_cuota
            if total_temp > total_a_pagar:
                raise UserError(
                    'El monto calculado [cuotas * monto] es mayor al saldo a pagar. Por favor corrija la cantidad de cuotas o el monto.')

            # ? ASIGNACION DE CUOTAS
            for i in range(qty_cuotas):
                fecha_inicial = fecha_inicial + timedelta(days=days)

                if i == (qty_cuotas - 1):
                    monto_cuota += (total_a_pagar - total_temp)

                new_cuota = self.env["adt.comercial.cuotas"].create(
                    {'name': 'Cuota R. - ' + str(i + 1), 'monto': monto_cuota, 'fecha_cronograma': fecha_inicial}).id

                self.cuenta_id.cuota_ids = [(4, new_cuota)]


class ADTComercialCuentasFunction(models.Model):
    _inherit = 'adt.comercial.cuentas'

    def unlink(self):
        # Extract id from adt.comercial.cuentas
        data = self.env['adt.comercial.cuentas'].search([('id', '=', self.id)])

        # Then search into fleet.vehicle by id for update disponible state
        vehicle = self.env['fleet.vehicle'].search([('id', '=', data.vehiculo_id.id)])
        vehicle.write({'disponible': True})

        return super(ADTComercialCuentasFunction, self).unlink()
