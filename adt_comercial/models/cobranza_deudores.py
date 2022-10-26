from odoo import _,api, fields, models
from odoo import tools


class ADTCobranzaReporte(models.Model):
    _name = 'adt.reporte.cobranza.deudores'
    _description = 'Cobranza - Reporte'
    _auto = False
    _rec_name = 'cuenta_id'
    _order = "cuenta_id asc"

    # x_imei = fields.Char(string="IMEI")
    cuenta_id = fields.Char(string='cuenta')
    recuperado = fields.Boolean(string="Recuperado")

    """def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
                  CREATE or REPLACE VIEW {} as (
                select
                    acc.id as cuenta_id,
                    acc.vin_sn as recuperado
                from fleet_vehicle acc
            )
                '''.format(self._table))"""


class ADTCobranzaPagosPendientes1(models.Model):
    _name = 'adt.reporte.cobranza.pagos.pendientes1'
    _description = 'Cobranza - Reporte general'
    _auto = False
    _rec_name = 'cuenta_id'
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

    periodicidad = fields.Char(string="Periodicidad")
    monto_fraccionado = fields.Float(string="Monto cuota")

    numero_pagado = fields.Integer(string="# pagadas")
    numero_pendiente = fields.Integer(string="# pendiente")

    vat = fields.Char(string="DNI o CE")

    model_id = fields.Many2one('fleet.vehicle', string="Vehiculo modelo")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE or REPLACE VIEW {} as (
                select
                    DISTINCT ON (acc2.id) cuenta_id,
                    acc.id,
                    acc.id as cuota_id,
                    acc2.user_id as user_id,
                    acc2.reference_no as reference_no,
                    date_part('days', (now() - acc.fecha_cronograma)) as dias_retraso,
                    acc2.fecha_desembolso as fecha_desembolso,
                    acc.fecha_cronograma as fecha_cronograma,
                    acc2.partner_id as partner_id,
                    rp.mobile as mobile,
                    rp.phone as phone,
                    rp.vat,
                    acc.monto as monto,
                    fv.model_id as model_id,
                    
                    acc2.periodicidad,
                    acc2.monto_fraccionado,
                    (SELECT count(*) FROM adt_comercial_cuotas AS cuotas WHERE cuotas.state = 'pagado' AND cuotas.cuenta_id = acc.id) AS  numero_pagado ,
                    (SELECT count(*) FROM adt_comercial_cuotas AS cuotas WHERE cuotas.state = 'retrasado' AND cuotas.cuenta_id = acc.id ) AS numero_pendiente 
                    
                from adt_comercial_cuotas acc
                left join adt_comercial_cuentas acc2 on acc.cuenta_id=acc2.id
                left join res_partner rp on acc2.partner_id = rp.id
                left join fleet_vehicle fv on acc2.vehiculo_id = fv.id
                where acc2.state != 'cancelado'
            )
        '''.format(self._table))