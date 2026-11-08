# -*- coding: utf-8 -*-
from odoo import models, fields
from datetime import date as date_cls

_MESES_ES = ['', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
             'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']

_PERIODICIDAD_LABEL = {'semanal': 'Semanal', 'quincena': 'Quincenal', 'mensual': 'Mensual'}
_PERIODICIDAD_POR_MES = {'semanal': 4.33, 'quincena': 2.0, 'mensual': 1.0}


class AdtFleetVehicleModel(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type = fields.Selection(
        selection_add=[('mototaxi', 'Mototaxi')],
        ondelete={'mototaxi': lambda recs: recs.write({'vehicle_type': False})},
    )


class FieldModels(models.Model):
    _inherit = 'fleet.vehicle'

    razon_social = fields.Selection(
        [
            ('adt', 'CORPORACION ADT S.A.C'),
            ('adt_dkirjm', 'CORPORACION ADT DKIRJM S.A.C'),
        ],
        string="Razón Social",
        default='adt_dkirjm',
        tracking=True,
    )

    fecha_entrega = fields.Date(string="Fecha de Entrega")
    foto_entrega = fields.Binary(string="Foto de Entrega", attachment=True)
    foto_entrega_filename = fields.Char(string="Nombre foto entrega")

    tarjeta_propiedad_attachment = fields.Binary(
        string="Tarjeta de Propiedad (PDF/Imagen)", attachment=True,
    )
    chip_gnv_attachment = fields.Binary(
        string="Chip GNV (PDF/Imagen)", attachment=True,
    )
    soat_attachment = fields.Binary(
        string="SOAT (PDF/Imagen)", attachment=True,
    )
    contrato_attachment = fields.Binary(
        string="Contrato (PDF)", attachment=True,
    )
    tarjeta_propiedad_filename = fields.Char(string="Nombre archivo Tarjeta")
    chip_gnv_filename = fields.Char(string="Nombre archivo Chip GNV")
    soat_filename = fields.Char(string="Nombre archivo SOAT")
    contrato_filename = fields.Char(string="Nombre archivo Contrato")

    # ── Helpers internos ─────────────────────────────────────────────────────

    def _get_cuenta_for_report(self):
        """Cuenta comercial activa del vehículo."""
        self.ensure_one()
        CM = self.env['adt.comercial.cuentas']
        return (
            CM.search([('vehiculo_id', '=', self.id), ('state', '=', 'en_curso')],  limit=1, order='id desc')
            or CM.search([('vehiculo_id', '=', self.id), ('state', '=', 'aprobado')], limit=1, order='id desc')
            or CM.search([('vehiculo_id', '=', self.id)], limit=1, order='id desc')
        )

    def _get_partner_for_report(self):
        """Partner (cliente) del vehículo."""
        self.ensure_one()
        partner = self.driver_id
        if not partner:
            cuenta = self._get_cuenta_for_report()
            if cuenta:
                partner = cuenta.partner_id
        return partner or self.env['res.partner']

    def _fecha_es(self, fecha=None):
        """Devuelve dict con dia/mes/anio para usar en QWeb sin ambigüedad de tipos."""
        if not fecha:
            fecha = date_cls.today()
        return {
            'dia': '%02d' % fecha.day,
            'mes': _MESES_ES[fecha.month],
            'anio': str(fecha.year),
        }

    def _plazo_meses(self, cuenta):
        """Plazo aproximado en meses."""
        if not cuenta or not cuenta.qty_cuotas:
            return 0
        divisor = _PERIODICIDAD_POR_MES.get(cuenta.periodicidad or '', 1.0)
        return round(cuenta.qty_cuotas / divisor)

    def _periodicidad_label(self, cuenta):
        """Etiqueta legible de la periodicidad."""
        if not cuenta:
            return ''
        return _PERIODICIDAD_LABEL.get(cuenta.periodicidad or '', (cuenta.periodicidad or '').capitalize())

    def _get_company_rep_info(self):
        """Lee parámetros de sistema para datos del representante y cuenta bancaria."""
        p = self.env['ir.config_parameter'].sudo()
        return {
            'nombre': p.get_param('adt_fleet.rep_nombre', 'Representante Legal'),
            'dni':    p.get_param('adt_fleet.rep_dni', ''),
            'partida': p.get_param('adt_fleet.partida_registral', ''),
            'cuenta_bancaria': p.get_param('adt_fleet.cuenta_bancaria', ''),
        }

    # ── Datos para Acta / Contrato (plantillas context/*.docx) ──────────────

    @staticmethod
    def _monto_letras(amount):
        """37650.0 -> 'Treinta y Siete Mil Seiscientos Cincuenta y 00/100 Soles'."""
        amount = round(amount or 0.0, 2)
        entero = int(amount)
        centimos = int(round((amount - entero) * 100))
        try:
            from num2words import num2words
            palabras = num2words(entero, lang='es')
        except Exception:
            palabras = str(entero)
        palabras = ' '.join(w if w == 'y' else w.capitalize() for w in palabras.split())
        return '%s y %02d/100 Soles' % (palabras, centimos)

    @staticmethod
    def _monto_fmt(amount):
        return '{:,.2f}'.format(amount or 0.0)

    @staticmethod
    def _tipo_documento_partner(partner):
        """Ciudadano extranjero -> CE; peruano (o sin nacionalidad) -> DNI."""
        if partner and partner.nationality and partner.nationality != 'peruana':
            return ('CE', 'C.E.')
        return ('DNI', 'D.N.I.')

    def _adt_report_values(self):
        """Valores dinámicos compartidos por el Acta y el Contrato."""
        self.ensure_one()
        cuenta = self._get_cuenta_for_report()
        # El firmante es el titular de la cuenta (el conductor asignado puede ser otro).
        partner = (cuenta.partner_id if cuenta else False) or self._get_partner_for_report()
        rep = self._get_company_rep_info()

        # Fecha de impresión del documento (zona horaria del usuario)
        fecha = fields.Date.context_today(self)

        tipo_doc, tipo_doc_puntos = self._tipo_documento_partner(partner)

        direccion = ', '.join(p.strip() for p in [
            partner.street, partner.street2,
            partner.l10n_pe_district_name if 'l10n_pe_district_name' in partner._fields else '',
            partner.state_id.name if partner.state_id else partner.city,
        ] if p and p.strip())

        tipo_vehiculo = {
            'mototaxi': 'Motocicleta (Mototaxi)',
            'bike': 'Motocicleta',
            'car': 'Automóvil',
        }.get(self.model_id.vehicle_type if self.model_id else '', 'Motocicleta (Mototaxi)')

        periodicidad = (cuenta.periodicidad if cuenta else '') or 'semanal'
        cuota_plural, periodo_plural = {
            'semanal': ('semanales', 'semanas'),
            'quincena': ('quincenales', 'quincenas'),
            'mensual': ('mensuales', 'meses'),
        }.get(periodicidad, ('semanales', 'semanas'))
        qty_cuotas = (cuenta.qty_cuotas or 0) if cuenta else 0
        if cuenta and (cuenta.cuota_gracia or 0) > 0:
            qty_cuotas += 1
        meses = int(qty_cuotas / _PERIODICIDAD_POR_MES.get(periodicidad, 1.0)) if qty_cuotas else 0

        inicial = cuenta.monto_inicial if cuenta else 0.0
        financiado = cuenta.monto_fraccionado if cuenta else 0.0
        total = inicial + financiado
        garantia = (cuenta.fin_monto_credito or cuenta.cf_monto_credito) if cuenta else 0.0

        return {
            'cuenta': cuenta,
            'partner': partner,
            'nombre': (partner.name or '').upper(),
            'tipo_doc': tipo_doc,
            'tipo_doc_puntos': tipo_doc_puntos,
            'num_doc': partner.vat or '',
            'direccion': direccion,
            'rep_nombre': rep['nombre'] if rep['nombre'] != 'Representante Legal' else 'Ayte Cueva Dalia Rubí',
            'rep_dni': rep['dni'] or '48565333',
            'tipo_vehiculo': tipo_vehiculo,
            'marca': (self.model_id.brand_id.name or '').upper() if self.model_id else '',
            'modelo': self.model_id.name or '',
            'color': (self.color or '').upper(),
            'chasis': self.vin_sn or '',
            'placa': self.license_plate or '',
            'fecha_dia': str(fecha.day),
            'fecha_mes': _MESES_ES[fecha.month].lower(),
            'fecha_anio': str(fecha.year),
            'qty_cuotas': qty_cuotas,
            'cuota_plural': cuota_plural,
            'periodo_plural': periodo_plural,
            'periodicidad_label': _PERIODICIDAD_LABEL.get(periodicidad, periodicidad.capitalize()),
            'plazo_meses': meses,
            'total_fmt': self._monto_fmt(total),
            'total_letras': self._monto_letras(total),
            'inicial_fmt': self._monto_fmt(inicial),
            'inicial_letras': self._monto_letras(inicial),
            'financiado_fmt': self._monto_fmt(financiado),
            'financiado_letras': self._monto_letras(financiado),
            'cuota_fmt': self._monto_fmt(cuenta.monto_cuota if cuenta else 0.0),
            'garantia_fmt': self._monto_fmt(garantia),
        }

    # ── Acciones de impresión ────────────────────────────────────────────────

    def action_print_acta_vehicular(self):
        return self.env.ref('adt_fleet.action_report_acta_vehicular').report_action(self)

    def action_print_contrato_tvs(self):
        return self.env.ref('adt_fleet.action_report_contrato_tvs').report_action(self)
