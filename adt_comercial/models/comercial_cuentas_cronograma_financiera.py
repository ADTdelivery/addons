import base64
import json
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from ..services.plan_pagos_parser import PlanPagosParseError, parse_pdf

_logger = logging.getLogger(__name__)


class ADTComercialCuentasCronogramaFinanciera(models.Model):
    """Cronograma de la financiera leído desde el PDF "Plan de Pagos".

    Reemplaza a la pestaña "Financiera": al subir el PDF se llenan estos campos,
    las filas del cronograma y, para que el dashboard y el reporte de financiera
    sigan funcionando, también los campos fin_* existentes.
    """
    _inherit = 'adt.comercial.cuentas'

    cf_pdf = fields.Binary(string="PDF del plan de pagos", attachment=True, copy=False)
    cf_pdf_nombre = fields.Char(string="Nombre del PDF", copy=False)

    # --- Cabecera del PDF ---
    cf_nro_solicitud = fields.Char(string="Nro. solicitud", readonly=True, copy=False)
    cf_nro_expediente = fields.Char(string="Nro. expediente", readonly=True, copy=False)
    cf_agencia = fields.Char(string="Agencia", readonly=True, copy=False)
    cf_socio = fields.Char(string="Socio (PDF)", readonly=True, copy=False)
    cf_codigo_socio = fields.Char(string="Código de socio", readonly=True, copy=False)
    cf_dni = fields.Char(string="DNI", readonly=True, copy=False)
    cf_monto_credito = fields.Monetary(string="Monto crédito", readonly=True, copy=False)
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
    cf_capital_pendiente = fields.Monetary(string="Capital pendiente", readonly=True, copy=False)
    cf_capital_amortizado = fields.Monetary(string="Capital amortizado", readonly=True, copy=False)
    cf_monto_cuota = fields.Monetary(string="Cuota de la financiera", readonly=True, copy=False)
    cf_total_pdf = fields.Monetary(string="Total a pagar (PDF)", readonly=True, copy=False)
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
        'adt.comercial.cuentas.cronograma.fin', 'cuenta_id',
        string="Cronograma de la financiera", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('cf_pdf').cf_leer_pdf()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('cf_pdf'):
            self.cf_leer_pdf()
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
                _logger.exception("Error leyendo el plan de pagos de la cuenta %s", rec.id)
                raise UserError(_("No se pudo leer el PDF: %s") % e)
            rec._cf_validar_cliente(data)
            rec._cf_aplicar(data)
        return True

    def _cf_validar_cliente(self, data):
        """Agrega la regla 'el DNI del PDF es el del cliente de la cuenta'."""
        self.ensure_one()
        dni_pdf = data['pie'].get('dni') or ''
        dni_cliente = (self.partner_id.vat or '').strip()
        if not dni_cliente:
            return
        validacion = data['validacion']
        validacion['reglas'].append({
            'regla': 'dni_coincide_cliente',
            'ok': dni_pdf == dni_cliente,
            'detalle': 'PDF: %s · Cliente: %s' % (dni_pdf or 'sin DNI', dni_cliente),
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
            'cf_cuota_ids': [(5, 0, 0)] + [(0, 0, {
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
            }) for c in cuotas],
        }
        vals.update(self._cf_valores_financiera(cab, cuotas, resumen, totales))
        # super().write para no volver a disparar la lectura del PDF
        super(ADTComercialCuentasCronogramaFinanciera, self).write(vals)

    @api.model
    def _cf_valores_financiera(self, cab, cuotas, resumen, totales):
        """Campos fin_* de la pestaña Financiera (los usan el dashboard y el reporte).

        El PDF sólo trae las cuotas que faltan pagar; las ya pagadas se estiman
        con el monto de cuota para que el total y la fecha de inicio describan
        el cronograma completo, tal como lo espera calcular_resumen().
        """
        if not cuotas:
            return {}
        primera = fields.Date.to_date(cuotas[0]['fecha_vencimiento'])
        ya_pagadas = cuotas[0]['nro_cuota'] - 1
        monto_cuota = resumen.get('monto_cuota_referencial', 0.0)
        return {
            'fin_fecha_desembolso': cab['fecha_desembolso'],
            'fin_fecha_inicio': primera - relativedelta(months=ya_pagadas),
            'fin_es_mensual': cab['frecuencia_cuota'].upper() == 'MENSUAL',
            'fin_fecha_fin': cuotas[-1]['fecha_vencimiento'],
            'fin_plazo_dias': cab['plazo_dias'],
            'fin_monto_credito': cab['monto_credito'],
            'fin_monto_cuota': monto_cuota,
            'fin_monto_total': round(totales.get('total', 0.0) + ya_pagadas * monto_cuota, 2),
            'fin_tasa_interes': cab['tasa_interes_anual'],
        }

    @api.model
    def _cf_render_validacion(self, reglas):
        filas = ''.join(
            '<tr><td>%s</td><td><b>%s</b></td><td>%s</td></tr>'
            % ('✅' if r['ok'] else '❌', html_escape(r['regla']), html_escape(r['detalle']))
            for r in reglas)
        return ('<table class="table table-sm"><thead><tr><th></th><th>Regla</th>'
                '<th>Detalle</th></tr></thead><tbody>%s</tbody></table>' % filas)


class ADTComercialCuentasCronogramaFin(models.Model):
    _name = 'adt.comercial.cuentas.cronograma.fin'
    _description = 'Cuota del cronograma de la financiera'
    _order = 'cuenta_id, nro_cuota'

    cuenta_id = fields.Many2one(
        'adt.comercial.cuentas', string="Cuenta", required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='cuenta_id.currency_id')
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
