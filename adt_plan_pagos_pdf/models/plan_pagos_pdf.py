# -*- coding: utf-8 -*-
import base64
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.plan_pagos_parser import PlanPagosParseError, parse_pdf

_logger = logging.getLogger(__name__)


class PlanPagosPdf(models.Model):
    _name = 'adt.plan.pagos.pdf'
    _description = 'Plan de Pagos (PDF a JSON)'
    _order = 'id desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    pdf_file = fields.Binary(string='PDF', required=True, attachment=True)
    pdf_filename = fields.Char(string='Nombre del archivo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('valido', 'Válido'),
        ('observado', 'Observado'),
        ('error', 'Error'),
    ], string='Estado', default='draft', readonly=True)
    confianza = fields.Float(string='Confianza (%)', readonly=True)

    texto = fields.Text(string='Texto extraído', readonly=True)
    json_data = fields.Text(string='JSON', readonly=True)
    validacion_html = fields.Html(string='Validaciones', readonly=True, sanitize=False)
    error = fields.Text(string='Error', readonly=True)

    # Campos clave para búsqueda / listado
    socio = fields.Char(readonly=True)
    dni = fields.Char(string='DNI', readonly=True, index=True)
    nro_solicitud = fields.Char(string='Nro. Solicitud', readonly=True)
    nro_expediente = fields.Char(string='Nro. Expediente', readonly=True)
    monto_credito = fields.Float(string='Monto crédito', readonly=True)
    tasa_interes_anual = fields.Float(string='TEA (%)', readonly=True)
    plazo_dias = fields.Integer(string='Plazo (días)', readonly=True)
    cuotas_pendientes = fields.Integer(string='Cuotas pendientes', readonly=True)
    capital_pendiente = fields.Float(string='Capital pendiente', readonly=True)

    @api.depends('socio', 'nro_solicitud', 'pdf_filename')
    def _compute_name(self):
        for rec in self:
            if rec.socio:
                rec.name = '%s - %s' % (rec.nro_solicitud, rec.socio)
            else:
                rec.name = rec.pdf_filename or _('Nuevo')

    def action_procesar(self):
        for rec in self:
            if not rec.pdf_file:
                raise UserError(_('Adjunte el PDF del plan de pagos.'))
            try:
                texto, data = parse_pdf(base64.b64decode(rec.pdf_file))
            except PlanPagosParseError as e:
                rec.write({'state': 'error', 'error': str(e), 'confianza': 0.0})
                continue
            except Exception as e:
                _logger.exception('Error leyendo plan de pagos %s', rec.pdf_filename)
                rec.write({'state': 'error', 'error': _('No se pudo leer el PDF: %s') % e,
                           'confianza': 0.0})
                continue

            cab, pie = data['cabecera'], data['pie']
            resumen = data.get('resumen') or {}
            validacion = data['validacion']
            rec.write({
                'state': validacion['estado'],
                'confianza': validacion['confianza'],
                'texto': texto,
                'json_data': json.dumps(data, ensure_ascii=False, indent=2),
                'validacion_html': self._render_validacion(validacion['reglas']),
                'error': False,
                'socio': cab['socio'],
                'dni': pie.get('dni'),
                'nro_solicitud': cab['nro_solicitud'],
                'nro_expediente': cab['nro_expediente'],
                'monto_credito': cab['monto_credito'],
                'tasa_interes_anual': cab['tasa_interes_anual'],
                'plazo_dias': cab['plazo_dias'],
                'cuotas_pendientes': resumen.get('cuotas_pendientes', 0),
                'capital_pendiente': resumen.get('capital_pendiente', 0.0),
            })
        return True

    @api.model
    def _render_validacion(self, reglas):
        rows = ''.join(
            '<tr><td>%s</td><td><b>%s</b></td><td>%s</td></tr>'
            % ('✅' if r['ok'] else '❌', r['regla'], r['detalle'])
            for r in reglas
        )
        return ('<table class="table table-sm"><thead><tr><th></th><th>Regla</th>'
                '<th>Detalle</th></tr></thead><tbody>%s</tbody></table>' % rows)

    def get_json(self):
        """Uso desde otros módulos / API: devuelve el dict parseado."""
        self.ensure_one()
        return json.loads(self.json_data) if self.json_data else {}
