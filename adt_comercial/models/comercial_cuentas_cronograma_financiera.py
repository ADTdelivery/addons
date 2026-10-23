import base64
import json
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from ..services.plan_pagos_parser import PlanPagosParseError, parse_pdf

_logger = logging.getLogger(__name__)

# Campos de la cabecera, el pie, el resumen y la lectura del PDF. El plan de la financiera es
# del vehículo (la moto se financia una vez); las cuentas los muestran desde su vehículo.
CF_CAMPOS = [
    'cf_pdf', 'cf_pdf_nombre',
    'cf_nro_solicitud', 'cf_nro_expediente', 'cf_agencia', 'cf_socio', 'cf_codigo_socio', 'cf_dni',
    'cf_monto_credito', 'cf_fecha_desembolso', 'cf_plazo_dias', 'cf_frecuencia_cuota',
    'cf_tasa_interes_anual', 'cf_producto', 'cf_tipo_credito', 'cf_tipo_cobro', 'cf_analista',
    'cf_oficina', 'cf_usuario_emisor', 'cf_fecha_sistema', 'cf_fecha_emision',
    'cf_cuotas_pendientes', 'cf_primera_cuota', 'cf_ultima_cuota', 'cf_capital_pendiente',
    'cf_capital_amortizado', 'cf_monto_cuota', 'cf_total_pdf', 'cf_tasa_desgravamen',
    'cf_proximo_vencimiento', 'cf_estado', 'cf_confianza', 'cf_validacion_html', 'cf_json',
    'cf_cuota_ids',
]

# Campos fin_* de la cuenta que se llenan desde el plan del vehículo (dashboard y reportes).
FIN_VACIO = {
    'fin_fecha_desembolso': False, 'fin_fecha_inicio': False, 'fin_es_mensual': True,
    'fin_fecha_fin': False, 'fin_plazo_dias': 0, 'fin_monto_credito': 0.0, 'fin_monto_cuota': 0.0,
    'fin_monto_total': 0.0, 'fin_tasa_interes': 0.0, 'fin_cancelada_manual': False,
}

ESTADOS_VIGENTES = ('en_curso', 'aprobado')


class ADTFleetVehicleCronogramaFinanciera(models.Model):
    """Cronograma de la financiera leído desde el PDF "Plan de Pagos", guardado en el vehículo.

    Al subir el PDF se llenan estos campos y las filas del cronograma. Para que el dashboard y
    los reportes de financiera (que trabajan por cuenta) sigan funcionando, los campos fin_* se
    copian a UNA cuenta del vehículo: la vigente, o la última si no hay vigente. Así la deuda con
    la financiera se cuenta una sola vez por moto.
    """
    _inherit = 'fleet.vehicle'

    cf_pdf = fields.Binary(string="PDF del plan de pagos", attachment=True, copy=False)
    cf_pdf_nombre = fields.Char(string="Nombre del PDF", copy=False)
    # Moneda de los montos del plan (no depende de que fleet.vehicle tenga currency_id).
    cf_currency_id = fields.Many2one('res.currency', compute='_compute_cf_currency_id')

    # --- Cabecera del PDF ---
    cf_nro_solicitud = fields.Char(string="Nro. solicitud", readonly=True, copy=False)
    cf_nro_expediente = fields.Char(string="Nro. expediente", readonly=True, copy=False)
    cf_agencia = fields.Char(string="Agencia", readonly=True, copy=False)
    cf_socio = fields.Char(string="Socio (PDF)", readonly=True, copy=False)
    cf_codigo_socio = fields.Char(string="Código de socio", readonly=True, copy=False)
    cf_dni = fields.Char(string="DNI", readonly=True, copy=False)
    cf_monto_credito = fields.Monetary(string="Monto crédito", readonly=True, copy=False, currency_field='cf_currency_id')
    cf_fecha_desembolso = fields.Date(string="Desembolso de la financiera", readonly=True, copy=False)
    cf_plazo_dias = fields.Integer(string="Plazo de la financiera (días)", readonly=True, copy=False)
    cf_frecuencia_cuota = fields.Char(string="Frecuencia de cuota", readonly=True, copy=False)
    cf_tasa_interes_anual = fields.Float(
        string="Tasa de interés anual (%)", digits=(16, 4), readonly=True, copy=False)
    cf_producto = fields.Char(string="Producto", readonly=True, copy=False)
    cf_tipo_credito = fields.Char(string="Tipo de crédito", readonly=True, copy=False)
    cf_tipo_cobro = fields.Char(string="Tipo de cobro", readonly=True, copy=False)
    cf_analista = fields.Char(string="Analista", readonly=True, copy=False)

    # --- Pie del PDF ---
    cf_oficina = fields.Char(string="Oficina", readonly=True, copy=False)
    cf_usuario_emisor = fields.Char(string="Usuario que emitió", readonly=True, copy=False)
    cf_fecha_sistema = fields.Date(string="Fecha sistema", readonly=True, copy=False)
    cf_fecha_emision = fields.Datetime(string="Fecha de emisión", readonly=True, copy=False)

    # --- Resumen calculado al leer el PDF ---
    cf_cuotas_pendientes = fields.Integer(string="Cuotas en el PDF", readonly=True, copy=False)
    cf_primera_cuota = fields.Integer(string="Primera cuota", readonly=True, copy=False)
    cf_ultima_cuota = fields.Integer(string="Última cuota", readonly=True, copy=False)
    cf_capital_pendiente = fields.Monetary(string="Capital pendiente", readonly=True, copy=False, currency_field='cf_currency_id')
    cf_capital_amortizado = fields.Monetary(string="Capital amortizado", readonly=True, copy=False, currency_field='cf_currency_id')
    cf_monto_cuota = fields.Monetary(string="Cuota de la financiera", readonly=True, copy=False, currency_field='cf_currency_id')
    cf_total_pdf = fields.Monetary(string="Total a pagar (PDF)", readonly=True, copy=False, currency_field='cf_currency_id')
    cf_tasa_desgravamen = fields.Float(
        string="Tasa desgravamen mensual (%)", digits=(16, 4), readonly=True, copy=False)
    cf_proximo_vencimiento = fields.Date(string="Próximo vencimiento", readonly=True, copy=False)

    # --- Calidad de la lectura ---
    cf_estado = fields.Selection(
        [('valido', 'Válido'), ('observado', 'Observado')],
        string="Lectura del PDF", readonly=True, copy=False)
    cf_confianza = fields.Float(string="Confianza (%)", readonly=True, copy=False, digits=(16, 1))
    cf_validacion_html = fields.Html(
        string="Validaciones", readonly=True, copy=False, sanitize=False)
    cf_json = fields.Text(string="JSON del PDF", readonly=True, copy=False)

    cf_cuota_ids = fields.One2many(
        'adt.comercial.cuentas.cronograma.fin', 'vehicle_id',
        string="Cronograma de la financiera", readonly=True, copy=False)

    def _compute_cf_currency_id(self):
        for rec in self:
            rec.cf_currency_id = rec.company_id.currency_id or self.env.company.currency_id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('cf_pdf').cf_leer_pdf()
        return records

    def write(self, vals):
        res = super().write(vals)
        # cf_sin_leer: quien escribe ya leyó el PDF y aplica los datos (carga masiva).
        if 'cf_pdf' in vals and not self.env.context.get('cf_sin_leer'):
            con_pdf = self.filtered('cf_pdf')
            con_pdf.cf_leer_pdf()
            (self - con_pdf)._cf_limpiar()
        return res

    def cf_leer_pdf(self):
        for rec in self:
            if not rec.cf_pdf:
                raise UserError(_("Primero sube el PDF del plan de pagos."))
            try:
                _texto, data = parse_pdf(base64.b64decode(rec.cf_pdf))
            except PlanPagosParseError as e:
                raise UserError(_("El PDF no tiene el formato de Plan de Pagos: %s") % e)
            except Exception as e:
                _logger.exception("Error leyendo el plan de pagos del vehículo %s", rec.id)
                raise UserError(_("No se pudo leer el PDF: %s") % e)
            rec._cf_validar_cliente(data)
            rec._cf_aplicar(data)
        return True

    def _cf_validar_cliente(self, data):
        """Agrega la regla 'el DNI del PDF es de un cliente de la moto' (titular o socio de una cuenta)."""
        self.ensure_one()
        dni_pdf = data['pie'].get('dni') or ''
        clientes = self.driver_id | self.cuenta_ids.mapped('partner_id')
        documentos = {(p.vat or '').strip() for p in clientes} - {''}
        if not documentos:
            return
        validacion = data['validacion']
        validacion['reglas'].append({
            'regla': 'dni_coincide_cliente',
            'ok': dni_pdf in documentos,
            'detalle': 'PDF: %s · Clientes de la moto: %s' % (dni_pdf or 'sin DNI', ', '.join(sorted(documentos))),
        })
        reglas = validacion['reglas']
        ok = sum(1 for r in reglas if r['ok'])
        validacion['confianza'] = round(100.0 * ok / len(reglas), 1)
        validacion['estado'] = 'valido' if ok == len(reglas) else 'observado'

    def _cf_aplicar(self, data):
        self.ensure_one()
        cab, pie = data['cabecera'], data['pie']
        resumen = data.get('resumen') or {}
        totales = data.get('totales') or {}
        cuotas = data['cuotas']
        validacion = data['validacion']

        vals = {
            'cf_nro_solicitud': cab['nro_solicitud'],
            'cf_nro_expediente': cab['nro_expediente'],
            'cf_agencia': cab['agencia'],
            'cf_socio': cab['socio'],
            'cf_codigo_socio': cab['codigo_socio'],
            'cf_dni': pie.get('dni'),
            'cf_monto_credito': cab['monto_credito'],
            'cf_fecha_desembolso': cab['fecha_desembolso'],
            'cf_plazo_dias': cab['plazo_dias'],
            'cf_frecuencia_cuota': cab['frecuencia_cuota'],
            'cf_tasa_interes_anual': cab['tasa_interes_anual'],
            'cf_producto': cab['producto'],
            'cf_tipo_credito': cab['tipo_credito'],
            'cf_tipo_cobro': cab['tipo_cobro'],
            'cf_analista': cab['analista'],
            'cf_oficina': pie.get('oficina'),
            'cf_usuario_emisor': pie.get('usuario_emisor'),
            'cf_fecha_sistema': pie.get('fecha_sistema'),
            'cf_fecha_emision': (pie.get('fecha_maquina') or '').replace('T', ' ') or False,
            'cf_cuotas_pendientes': resumen.get('cuotas_pendientes', 0),
            'cf_primera_cuota': resumen.get('primera_cuota', 0),
            'cf_ultima_cuota': resumen.get('ultima_cuota', 0),
            'cf_capital_pendiente': resumen.get('capital_pendiente', 0.0),
            'cf_capital_amortizado': resumen.get('capital_amortizado', 0.0),
            'cf_monto_cuota': resumen.get('monto_cuota_referencial', 0.0),
            'cf_total_pdf': totales.get('total', 0.0),
            'cf_tasa_desgravamen': resumen.get('tasa_desgravamen_mensual', 0.0),
            'cf_proximo_vencimiento': resumen.get('proximo_vencimiento') or False,
            'cf_estado': validacion['estado'],
            'cf_confianza': validacion['confianza'],
            'cf_validacion_html': self._cf_render_validacion(validacion['reglas']),
            'cf_json': json.dumps(data, ensure_ascii=False, indent=2),
        }
        # Las filas se reemplazan explícitamente: (5, 0, 0) en un one2many con inverso
        # opcional solo las desvincularía y quedarían huérfanas.
        self.cf_cuota_ids.unlink()
        vals['cf_cuota_ids'] = [(0, 0, {
            'nro_cuota': c['nro_cuota'],
            'fecha_vencimiento': c['fecha_vencimiento'],
            'capital': c['capital'],
            'interes': c['interes'],
            'seguro_desgravamen': c['seguro_desgravamen'],
            'comision_operativa': c['comision_operativa'],
            'interes_vencido': c['interes_vencido'],
            'interes_moratorio': c['interes_moratorio'],
            'interes_compensatorio': c['interes_compensatorio'],
            'aporte': c['aporte'],
            'otros': c['otros'],
            'total': c['total'],
            'estado': c['estado'],
        }) for c in cuotas]
        # super().write para no volver a disparar la lectura del PDF
        super(ADTFleetVehicleCronogramaFinanciera, self).write(vals)
        self._cf_sincronizar_cuenta()

    def _cf_limpiar(self):
        """Sin PDF no hay plan: se borran sus datos y la cuenta deja de llevar la financiera."""
        vacio = {campo: False for campo in CF_CAMPOS if campo not in ('cf_pdf', 'cf_pdf_nombre', 'cf_cuota_ids')}
        for rec in self:
            rec.cf_cuota_ids.unlink()
            super(ADTFleetVehicleCronogramaFinanciera, rec).write(dict(vacio, cf_pdf_nombre=False))
        self._cf_sincronizar_cuenta()

    def cf_total_plan(self):
        """Total a pagar a la financiera por el plan completo: lo que trae el PDF más las cuotas
        anteriores al PDF (ya pagadas), estimadas con el monto de cuota."""
        self.ensure_one()
        total = sum(self.cf_cuota_ids.mapped('total')) or self.cf_total_pdf or 0.0
        ya_pagadas = max((self.cf_primera_cuota or 1) - 1, 0)
        return round(total + ya_pagadas * (self.cf_monto_cuota or 0.0), 2)

    def _cf_valores_financiera(self):
        """Campos fin_* de la cuenta (los usan el dashboard y el reporte).

        El PDF sólo trae las cuotas que faltan pagar; las ya pagadas se estiman
        con el monto de cuota para que el total y la fecha de inicio describan
        el cronograma completo, tal como lo espera calcular_resumen().
        """
        self.ensure_one()
        cuotas = self.cf_cuota_ids.sorted(lambda q: (q.nro_cuota, q.id))
        if not cuotas:
            return {}
        ya_pagadas = max(cuotas[0].nro_cuota - 1, 0)
        return {
            'fin_fecha_desembolso': self.cf_fecha_desembolso,
            'fin_fecha_inicio': cuotas[0].fecha_vencimiento and (
                cuotas[0].fecha_vencimiento - relativedelta(months=ya_pagadas)),
            'fin_es_mensual': (self.cf_frecuencia_cuota or '').upper() == 'MENSUAL',
            'fin_fecha_fin': cuotas[-1].fecha_vencimiento,
            'fin_plazo_dias': self.cf_plazo_dias,
            'fin_monto_credito': self.cf_monto_credito,
            'fin_monto_cuota': self.cf_monto_cuota,
            'fin_monto_total': self.cf_total_plan(),
            'fin_tasa_interes': self.cf_tasa_interes_anual,
        }

    def _cf_cuenta_financiera(self):
        """La cuenta que lleva la financiera en los reportes: la vigente; si no hay, la última."""
        self.ensure_one()
        cuentas = self.cuenta_ids.sorted(lambda c: (c.fecha_desembolso or fields.Date.to_date('1900-01-01'), c.id),
                                         reverse=True)
        return (cuentas.filtered(lambda c: c.state in ESTADOS_VIGENTES)[:1]
                or cuentas.filtered(lambda c: c.state != 'borrador')[:1]
                or cuentas[:1])

    def _cf_sincronizar_cuenta(self):
        """Copia el plan del vehículo a su cuenta financiera y lo quita de las demás cuentas
        que lo llevaban, para que la deuda con la financiera se cuente una sola vez."""
        Cuenta = self.env['adt.comercial.cuentas'].with_context(cf_sincronizando=True)
        for rec in self:
            valores = rec._cf_valores_financiera() if rec.cf_cuota_ids else {}
            destino = rec._cf_cuenta_financiera() if valores else Cuenta
            previas = Cuenta.search([('vehiculo_id', '=', rec.id), ('fin_desde_vehiculo', '=', True)]) - destino
            if destino:
                cancelada = destino.fin_cancelada_manual or any(previas.mapped('fin_cancelada_manual'))
                destino.with_context(cf_sincronizando=True).write(
                    dict(valores, fin_cancelada_manual=cancelada, fin_desde_vehiculo=True))
            if previas:
                previas.write(dict(FIN_VACIO, fin_desde_vehiculo=False))

    @api.model
    def _cf_render_validacion(self, reglas):
        filas = ''.join(
            '<tr><td>%s</td><td><b>%s</b></td><td>%s</td></tr>'
            % ('✅' if r['ok'] else '❌', html_escape(r['regla']), html_escape(r['detalle']))
            for r in reglas)
        return ('<table class="table table-sm"><thead><tr><th></th><th>Regla</th>'
                '<th>Detalle</th></tr></thead><tbody>%s</tbody></table>' % filas)


class ADTComercialCuentasCronogramaFinanciera(models.Model):
    """La cuenta muestra el plan de la financiera de su vehículo (solo lectura)."""
    _inherit = 'adt.comercial.cuentas'

    cf_pdf = fields.Binary(related='vehiculo_id.cf_pdf', readonly=True)
    cf_pdf_nombre = fields.Char(related='vehiculo_id.cf_pdf_nombre', readonly=True)
    cf_nro_solicitud = fields.Char(related='vehiculo_id.cf_nro_solicitud', readonly=True)
    cf_nro_expediente = fields.Char(related='vehiculo_id.cf_nro_expediente', readonly=True)
    cf_agencia = fields.Char(related='vehiculo_id.cf_agencia', readonly=True)
    cf_socio = fields.Char(related='vehiculo_id.cf_socio', readonly=True)
    cf_codigo_socio = fields.Char(related='vehiculo_id.cf_codigo_socio', readonly=True)
    cf_dni = fields.Char(related='vehiculo_id.cf_dni', readonly=True)
    cf_monto_credito = fields.Monetary(related='vehiculo_id.cf_monto_credito', readonly=True)
    cf_fecha_desembolso = fields.Date(related='vehiculo_id.cf_fecha_desembolso', readonly=True)
    cf_plazo_dias = fields.Integer(related='vehiculo_id.cf_plazo_dias', readonly=True)
    cf_frecuencia_cuota = fields.Char(related='vehiculo_id.cf_frecuencia_cuota', readonly=True)
    cf_tasa_interes_anual = fields.Float(related='vehiculo_id.cf_tasa_interes_anual', readonly=True)
    cf_producto = fields.Char(related='vehiculo_id.cf_producto', readonly=True)
    cf_tipo_credito = fields.Char(related='vehiculo_id.cf_tipo_credito', readonly=True)
    cf_tipo_cobro = fields.Char(related='vehiculo_id.cf_tipo_cobro', readonly=True)
    cf_analista = fields.Char(related='vehiculo_id.cf_analista', readonly=True)
    cf_oficina = fields.Char(related='vehiculo_id.cf_oficina', readonly=True)
    cf_usuario_emisor = fields.Char(related='vehiculo_id.cf_usuario_emisor', readonly=True)
    cf_fecha_sistema = fields.Date(related='vehiculo_id.cf_fecha_sistema', readonly=True)
    cf_fecha_emision = fields.Datetime(related='vehiculo_id.cf_fecha_emision', readonly=True)
    cf_cuotas_pendientes = fields.Integer(related='vehiculo_id.cf_cuotas_pendientes', readonly=True)
    cf_primera_cuota = fields.Integer(related='vehiculo_id.cf_primera_cuota', readonly=True)
    cf_ultima_cuota = fields.Integer(related='vehiculo_id.cf_ultima_cuota', readonly=True)
    cf_capital_pendiente = fields.Monetary(related='vehiculo_id.cf_capital_pendiente', readonly=True)
    cf_capital_amortizado = fields.Monetary(related='vehiculo_id.cf_capital_amortizado', readonly=True)
    cf_monto_cuota = fields.Monetary(related='vehiculo_id.cf_monto_cuota', readonly=True)
    cf_total_pdf = fields.Monetary(related='vehiculo_id.cf_total_pdf', readonly=True)
    cf_tasa_desgravamen = fields.Float(related='vehiculo_id.cf_tasa_desgravamen', readonly=True)
    cf_proximo_vencimiento = fields.Date(related='vehiculo_id.cf_proximo_vencimiento', readonly=True)
    cf_estado = fields.Selection(related='vehiculo_id.cf_estado', readonly=True)
    cf_confianza = fields.Float(related='vehiculo_id.cf_confianza', readonly=True)
    cf_validacion_html = fields.Html(related='vehiculo_id.cf_validacion_html', readonly=True)
    cf_json = fields.Text(related='vehiculo_id.cf_json', readonly=True)
    cf_cuota_ids = fields.One2many(related='vehiculo_id.cf_cuota_ids', readonly=True)

    fin_desde_vehiculo = fields.Boolean(
        string="Lleva la financiera del vehículo", readonly=True, copy=False,
        help="Los datos de la financiera de esta cuenta vienen del plan de pagos cargado en el vehículo. "
             "Solo una cuenta por vehículo los lleva, para no contar dos veces la deuda con la financiera.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped('vehiculo_id').filtered('cf_cuota_ids')._cf_sincronizar_cuenta()
        return records

    def write(self, vals):
        cambia = not self.env.context.get('cf_sincronizando') and bool({'state', 'vehiculo_id'} & set(vals))
        vehiculos = self.mapped('vehiculo_id') if cambia else self.env['fleet.vehicle']
        res = super().write(vals)
        if cambia:
            # Cambia la cuenta vigente (o la moto): la financiera pasa a la cuenta que corresponde.
            (vehiculos | self.mapped('vehiculo_id'))._cf_sincronizar_cuenta()
        return res

    def cf_leer_pdf(self):
        vehiculos = self.mapped('vehiculo_id')
        if not vehiculos:
            raise UserError(_("La cuenta no tiene vehículo: el plan de la financiera se carga en el vehículo."))
        return vehiculos.cf_leer_pdf()


class ADTComercialCuentasCronogramaFin(models.Model):
    _name = 'adt.comercial.cuentas.cronograma.fin'
    _description = 'Cuota del cronograma de la financiera'
    _order = 'vehicle_id, nro_cuota, id'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string="Vehículo", ondelete='cascade', index=True)
    # Histórico: antes el plan se guardaba por cuenta. Las filas nuevas solo llevan el vehículo.
    cuenta_id = fields.Many2one(
        'adt.comercial.cuentas', string="Cuenta", ondelete='cascade', index=True)
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    nro_cuota = fields.Integer(string="Cuota")
    fecha_vencimiento = fields.Date(string="Fecha")
    capital = fields.Monetary(string="Capital")
    interes = fields.Monetary(string="Interés")
    seguro_desgravamen = fields.Monetary(string="S. Desgrav.")
    comision_operativa = fields.Monetary(string="C. Operat.")
    interes_vencido = fields.Monetary(string="Int. Vencido")
    interes_moratorio = fields.Monetary(string="Int. Mora")
    interes_compensatorio = fields.Monetary(string="Int. Comp.")
    aporte = fields.Monetary(string="Aporte")
    otros = fields.Monetary(string="Otros")
    total = fields.Monetary(string="Total")
    estado = fields.Char(string="Estado")

    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.cuenta_id.currency_id or self.env.company.currency_id
