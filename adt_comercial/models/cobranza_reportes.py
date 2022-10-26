from odoo import _, api, fields, models
from odoo import tools

import logging
from odoo.http import request

_logger = logging.getLogger(__name__)


class ADTCobranzaPagosRealizados(models.Model):
    _name = 'adt.reporte.cobranza.pagos.realizados'
    _description = 'Cobranza - Pagos realizados'
    _auto = False
    _rec_name = 'payment_id'
    _order = "fecha desc"

    payment_id = fields.Many2one('account.payment', string='Pago')
    cuota_id = fields.Many2one('adt.comercial.cuotas', string='Cuota')

    # partner_id = fields.Many2one('res.partner', string='Socio', related="cuota_id.cuenta_id.partner_id")
    partner_id = fields.Many2one('res.partner', string='Socio')
    user_id = fields.Many2one("res.users", string="Asesor")
    phone = fields.Char(string="Teléfono")
    mobile = fields.Char(string="Celular")

    # cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', related="cuota_id.cuenta_id")
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo')
    fecha_desembolso = fields.Date(string="Fecha desembolso")

    fecha_cronograma = fields.Date(string="Fecha cronograma")

    monto = fields.Float(string='Monto')

    fecha = fields.Date(string='Fecha')
    journal_id = fields.Many2one('account.journal', string='Forma de pago')

    state = fields.Selection([("pendiente", "Pendiente"), ("a_cuenta", "A cuenta"), (
        "retrasado", "Retrasado"), ("pagado", "Pagado")], string="Estado")

    move_state = fields.Selection(
        [("posted", "Publicado"), ("draft", "Borrador"), ("cancel", "Cancelado")], string="Estado pago")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE or REPLACE VIEW {} as (
                select
                    ap.id,
                    ap.id as payment_id,
                    acc.id as cuota_id,
                    acc2.id as cuenta_id,
                    acc2.partner_id as partner_id,
                    acc2.user_id as user_id,
                    rp.mobile as mobile,
                    rp.phone as phone,
                    fv.id as vehicle_id,
                    acc2.fecha_desembolso as fecha_desembolso,
                    acc.fecha_cronograma as fecha_cronograma,
                    ap.amount as monto,
                    am.date as fecha,
                    am.journal_id as journal_id,
                    acc.state as state,
                    am.state as move_state
                from adt_comercial_cuotas acc
                left join account_payment ap on acc.id = ap.cuota_id
                left join account_move am on ap.move_id = am.id
                left join adt_comercial_cuentas acc2 on acc.cuenta_id =acc2.id
                left join res_partner rp on acc2.partner_id = rp.id
                left join fleet_vehicle fv on acc2.vehiculo_id =fv.id
                where am.state = 'posted' and acc.state = 'pagado'
            )
        '''.format(self._table))

    def ver_detalle_cuenta(self):
        view = self.env.ref("adt_comercial.adt_comercial_cuentas_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Cuenta {}".format(self.cuenta_id.reference_no),
            "res_id": self.cuenta_id.id,
            "res_model": "adt.comercial.cuentas",
            "view_mode": "form",
            "view_id": view.id
        }


class ADTCobranzaPagosPendientes(models.Model):
    _name = 'adt.reporte.cobranza.pagos.pendientes'
    _description = 'Cobranza - Pagos pendientes'
    _auto = False
    _rec_name = 'cuota_id'
    _order = "fecha_cronograma asc"

    # payment_id = fields.Many2one('account.payment', string='Pago')
    cuota_id = fields.Many2one('adt.comercial.cuotas', string='Cuota')

    # partner_id = fields.Many2one('res.partner', string='Socio', related="cuota_id.cuenta_id.partner_id")
    partner_id = fields.Many2one('res.partner', string='Socio')
    user_id = fields.Many2one("res.users", string="Asesor")
    phone = fields.Char(string="Teléfono")
    mobile = fields.Char(string="Celular")

    # cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', related="cuota_id.cuenta_id")
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta')
    reference_no = fields.Char(string='Referencia')
    fecha_desembolso = fields.Date(string="Fecha desembolso")

    fecha_cronograma = fields.Date(string="Fecha cronograma")

    monto = fields.Float(string='Monto')
    dias_retraso = fields.Integer(string="Días de retraso")
    vat = fields.Char(string="DNI o CE")
    model_id = fields.Many2one('fleet.vehicle', string="Vehiculo modelo")

    numero_pagado = fields.Integer(string="# cuotas pagadas")
    numero_pendiente = fields.Integer(string="# cuotas pendiente")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE or REPLACE VIEW {} as (
                select
                    acc.id,
                    acc.id as cuota_id,
                    acc2.id as cuenta_id,
                    acc2.user_id as user_id,
                    acc2.reference_no as reference_no,
                    date_part('days', (now() - acc.fecha_cronograma)) as dias_retraso,
                    acc2.fecha_desembolso as fecha_desembolso,
                    acc.fecha_cronograma as fecha_cronograma,
                    acc2.partner_id as partner_id,
                    rp.mobile as mobile,
                    rp.phone as phone,
                    rp.vat as vat,
                    fv.model_id as model_id,
                    acc.monto as monto,
                    (SELECT count(*) FROM adt_comercial_cuotas AS cuotas WHERE cuotas.state = 'pagado' AND cuotas.cuenta_id = acc.id) AS  numero_pagado ,
                    (SELECT count(*) FROM adt_comercial_cuotas AS cuotas WHERE cuotas.state = 'retrasado' AND cuotas.cuenta_id = acc.id ) AS numero_pendiente 
                    
                from adt_comercial_cuotas acc
                left join adt_comercial_cuentas acc2 on acc.cuenta_id=acc2.id
                left join res_partner rp on acc2.partner_id = rp.id
                left join fleet_vehicle fv on acc2.vehiculo_id = fv.id
                where acc2.state != 'cancelado' and acc.state = 'pendiente'
            )
        '''.format(self._table))

    def registrar_pago(self):
        return {
            'name': _('Register Payment'),
            'res_model': 'adt.register.payment',
            'view_mode': 'form',
            'context': {
                'active_model': 'adt.reporte.cobranza.pagos.pendientes',
                # 'active_ids': self.ids,
                'default_amount': self.monto,
                'default_communication': self.cuota_id.name,
                'default_cuota_id': self.cuota_id.id,
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
                'active_model': 'adt.reporte.cobranza.pagos.pendientes',
                'default_cuota_id': self.cuota_id.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def ver_detalle_cuenta(self):
        view = self.env.ref("adt_comercial.adt_comercial_cuentas_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Cuenta {}".format(self.cuenta_id.reference_no),
            "res_id": self.cuenta_id.id,
            "res_model": "adt.comercial.cuentas",
            "view_mode": "form",
            "view_id": view.id
        }


class ADTCobranzaCaptura(models.Model):
    _name = 'adt.reporte.cobranza.captura'
    _description = 'Cobranza - Captura'
    _auto = False
    _rec_name = 'cuenta_id'
    _order = "fecha_cronograma asc"

    partner_id = fields.Many2one('res.partner', string='Socio')
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta')
    vehiculo_id = fields.Many2one("fleet.vehicle", string="Moto")
    dias_retraso = fields.Integer(string="Días de retraso")
    periodicidad = fields.Selection(
        [('quincena', 'Quincenal'), ('mensual', 'Mensual')], string="Periodo")
    fecha_cronograma = fields.Date(string="Fecha de cronograma")
    monto = fields.Float(string='Monto')
    gps_chip = fields.Char(string="GPS Chip")
    gps_activo = fields.Boolean(string="GPS activo")
    recuperado = fields.Boolean(string="Recuperado")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE or REPLACE VIEW {} as (
                select
                    acc.id,
                    acc.partner_id as partner_id,
                    acc.id as cuenta_id,
                    acc.vehiculo_id as vehiculo_id,
                    date_part('days', (now() - acc2.fecha_cronograma)) as dias_retraso,
                    acc.periodicidad as periodicidad,
                    acc2.fecha_cronograma as fecha_cronograma,
                    acc2.monto as monto,
                    acc.gps_chip as gps_chip,
                    acc.gps_activo as gps_activo,
                    acc.recuperado as recuperado
                from adt_comercial_cuentas acc 
                inner join adt_comercial_cuotas acc2 on acc.id= (select acc3.cuenta_id from adt_comercial_cuotas acc3 where acc3.id=acc2.id and acc3.fecha_cronograma < now() and acc3.state != 'pagado')
            )
        '''.format(self._table))


class ADTCobranzaRecuperado(models.Model):
    _name = 'adt.reporte.cobranza.recuperado'
    _description = 'Cobranza - Recuperado'
    _auto = False
    _rec_name = 'cuenta_id'
    _order = "cuenta_id asc"

    partner_id = fields.Many2one('res.partner', string='Socio')
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta')
    vehiculo_id = fields.Many2one("fleet.vehicle", string="Moto")
    recuperado = fields.Boolean(string="Recuperado")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE or REPLACE VIEW {} as (
               select
                    acc.id,
                    acc.partner_id as partner_id,
                    acc.id as cuenta_id,
                    acc.vehiculo_id as vehiculo_id,
                    acc.recuperado as recuperado
                from adt_comercial_cuentas acc
                where acc.recuperado = true
            )
        '''.format(self._table))


