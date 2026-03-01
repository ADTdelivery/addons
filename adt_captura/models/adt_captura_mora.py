# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from odoo.tools import date_utils

import logging

_logger = logging.getLogger(__name__)


class ADTCapturaMora(models.Model):
    """Vista SQL para identificar clientes en mora que requieren captura"""
    _name = 'adt.captura.mora'
    _description = 'Clientes en Mora - Para Captura'
    _auto = False
    _rec_name = 'partner_id'
    _order = 'dias_mora desc, fecha_cronograma asc'

    # Datos principales
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', readonly=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', readonly=True)
    reference_no = fields.Char(string='N° Cuenta', readonly=True)

    # Información de mora
    dias_mora = fields.Integer(string='Días de Mora', readonly=True)
    tipo_cartera = fields.Selection([
        ('quincena', 'Qorilazo'),
        ('mensual', 'Los Andes'),
    ], string='Tipo de Cartera', readonly=True)

    # Información de cuotas
    fecha_cronograma = fields.Date(string='Fecha Vencimiento', readonly=True)
    monto_vencido = fields.Float(string='Monto Vencido', readonly=True)
    numero_cuotas_vencidas = fields.Integer(string='# Cuotas Vencidas', readonly=True)

    # Información de papeletas
    fecha_vencimiento_papeleta = fields.Date(string='Fecha Vencimiento Papeleta', readonly=True)
    papeleta_id = fields.Many2one('adt.papeleta', string='Papeleta', readonly=True)

    # Información GPS
    gps_chip = fields.Char(string='GPS Chip', readonly=True)
    gps_activo = fields.Boolean(string='GPS Activo', readonly=True)

    # Contacto
    phone = fields.Char(string='Teléfono', readonly=True)
    mobile = fields.Char(string='Celular', readonly=True)
    vat = fields.Char(string='DNI/CE', readonly=True)

    # Asesor
    user_id = fields.Many2one('res.users', string='Asesor', readonly=True)

    # Estado captura
    captura_existente = fields.Boolean(string='Tiene Captura', readonly=True)

    # Prioridad de captura (editable en cuenta)
    captura_prioridad = fields.Selection([
        ('', ''),
        ('normal', 'Normal'),
        ('urgente', 'Urgente')
    ], string='Prioridad de Captura', readonly=False, related='cuenta_id.captura_prioridad', store=False)

    # Nuevo: Origen del problema (mora / papeleta / ambos / none)
    source_type = fields.Selection([
        ('mora', 'Mora (Cuotas)'),
        ('papeleta', 'Papeleta'),
        ('ambos', 'Mora y Papeleta'),
        ('none', 'Ninguno')
    ], string='Origen', readonly=True)

    def init(self):
        """Crea la vista SQL para clientes en mora"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW {} AS (
                SELECT
                    cuenta.id,
                    cuenta.partner_id as partner_id,
                    cuenta.id as cuenta_id,
                    cuenta.vehiculo_id as vehicle_id,
                    cuenta.reference_no as reference_no,

                    -- Cálculo de días de mora (desde la cuota más antigua vencida)
                    CAST(date_part('days', (now() - MIN(cuota.fecha_cronograma))) AS INTEGER) as dias_mora,

                    -- Tipo de cartera
                    cuenta.periodicidad as tipo_cartera,

                    -- Información de cuotas vencidas
                    MIN(cuota.fecha_cronograma) as fecha_cronograma,
                    COALESCE(SUM(cuota.monto), 0) as monto_vencido,
                    COUNT(cuota.id) as numero_cuotas_vencidas,

                    -- Información de papeletas vencidas (si aplica)
                    MIN(p.fecha_vencimiento_final) as fecha_vencimiento_papeleta,
                    MIN(p.id) as papeleta_id,

                    -- GPS
                    cuenta.gps_chip as gps_chip,
                    cuenta.gps_activo as gps_activo,

                    -- Contacto
                    partner.phone as phone,
                    partner.mobile as mobile,
                    partner.vat as vat,

                    -- Asesor
                    cuenta.user_id as user_id,

                    -- Verificar si ya tiene captura activa
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM adt_captura_record
                            WHERE cuenta_id = cuenta.id
                            AND (state = 'capturado' OR state = 'disolucion_contrato')
                        ) THEN true
                        ELSE false
                    END as captura_existente,

                    -- Flags intermedios para determinar origen
                    CASE
                        WHEN (MIN(cuota.fecha_cronograma) IS NOT NULL AND date_part('days', (now() - MIN(cuota.fecha_cronograma))) > 0)
                        THEN true
                        ELSE false
                    END as has_mora,

                    CASE
                        WHEN (MIN(p.fecha_vencimiento_final) IS NOT NULL)
                        THEN true
                        ELSE false
                    END as has_papeleta,

                    -- Origen: mora / papeleta / ambos / none
                    CASE
                        WHEN ( (MIN(cuota.fecha_cronograma) IS NOT NULL AND date_part('days', (now() - MIN(cuota.fecha_cronograma))) > 0)
                               AND (MIN(p.fecha_vencimiento_final) IS NOT NULL) ) THEN 'ambos'
                        WHEN (MIN(cuota.fecha_cronograma) IS NOT NULL AND date_part('days', (now() - MIN(cuota.fecha_cronograma))) > 0) THEN 'mora'
                        WHEN (MIN(p.fecha_vencimiento_final) IS NOT NULL) THEN 'papeleta'
                        ELSE 'none'
                    END as source_type

                FROM adt_comercial_cuentas cuenta
                LEFT JOIN adt_comercial_cuotas cuota ON cuota.cuenta_id = cuenta.id
                    AND cuota.state IN ('pendiente', 'retrasado')
                    AND cuota.fecha_cronograma < now()
                LEFT JOIN adt_papeleta p ON p.vehicle_id = cuenta.vehiculo_id
                    AND COALESCE(p.state, '') != 'pagado'
                    AND (p.fecha_vencimiento_final < now() OR p.capturado = true)
                    AND p.recolocada = false
                LEFT JOIN res_partner partner ON cuenta.partner_id = partner.id

                WHERE cuenta.state != 'cancelado'

                GROUP BY
                    cuenta.id,
                    cuenta.partner_id,
                    cuenta.vehiculo_id,
                    cuenta.reference_no,
                    cuenta.periodicidad,
                    cuenta.gps_chip,
                    cuenta.gps_activo,
                    cuenta.user_id,
                    partner.phone,
                    partner.mobile,
                    partner.vat

                -- Incluir cuentas que tienen cuotas vencidas (min fecha_cronograma) OR papeletas vencidas
                HAVING (
                    (MIN(cuota.fecha_cronograma) IS NOT NULL
                     AND date_part('days', (now() - MIN(cuota.fecha_cronograma))) > 0)
                    OR (MIN(p.fecha_vencimiento_final) IS NOT NULL)
                )

                ORDER BY dias_mora DESC, fecha_cronograma ASC
            )
        '''.format(self._table))

    def action_iniciar_captura(self):
        """Abre el formulario para registrar una nueva captura"""
        self.ensure_one()

        # Verificar si ya existe una captura activa
        captura_existente = self.env['adt.captura.record'].search([
            ('cuenta_id', '=', self.cuenta_id.id),
            ('state', '=', 'capturado')
        ], limit=1)

        if captura_existente:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Aviso',
                    'message': 'Ya existe una captura activa para esta cuenta.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        return {
            'name': 'Nueva Captura',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.record',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_cuenta_id': self.cuenta_id.id,
                'default_intervention_fee': 50.0,
                'default_source_type': self.source_type,
                'default_papeleta_id': self.papeleta_id and self.papeleta_id.id or False,
            },
            'target': 'current',
        }

    def action_ver_detalle(self):
        """Abre el detalle de la cuenta"""
        self.ensure_one()

        return {
            'name': f'Cuenta {self.reference_no}',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.comercial.cuentas',
            'view_mode': 'form',
            'res_id': self.cuenta_id.id,
        }

    def action_set_prioridad_urgente(self):
        """Set the related cuenta's prioridad to 'urgente'"""
        self.ensure_one()
        if self.cuenta_id:
            self.cuenta_id.captura_prioridad = 'urgente'

    def action_set_prioridad_normal(self):
        """Set the related cuenta's prioridad to 'normal'"""
        self.ensure_one()
        if self.cuenta_id:
            self.cuenta_id.captura_prioridad = 'normal'
