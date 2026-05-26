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

    # ── Acciones de impresión ────────────────────────────────────────────────

    def action_print_acta_vehicular(self):
        return self.env.ref('adt_fleet.action_report_acta_vehicular').report_action(self)

    def action_print_contrato_tvs(self):
        return self.env.ref('adt_fleet.action_report_contrato_tvs').report_action(self)
