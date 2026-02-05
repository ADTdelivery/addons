# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions
from datetime import date
import re


class SentinelReport(models.Model):
    """
    Modelo para almacenar reportes crediticios de Sentinel.

    REGLA DE NEGOCIO CRÍTICA:
    - 1 solo reporte por DNI por mes
    - Vigencia: Solo mes actual
    - NO calcula ni interpreta scores
    - Solo almacena y controla acceso a imágenes
    """
    _name = 'adt.sentinel.report'
    _description = 'Reporte Crediticio Sentinel'
    _order = 'query_date desc, id desc'
    _rec_name = 'document_number'

    # ═══════════════════════════════════════════════════════════
    # CAMPOS PRINCIPALES
    # ═══════════════════════════════════════════════════════════

    document_number = fields.Char(
        string='Número de Documento (DNI)',
        required=True,
        size=8,
        index=True,
        readonly=True,
        help='DNI del cliente consultado (8 dígitos)'
    )

    report_image = fields.Binary(
        string='Imagen del Reporte',
        required=True,
        attachment=True,
        readonly=True,
        help='Captura de pantalla o imagen del reporte Sentinel'
    )

    image_filename = fields.Char(
        string='Nombre del Archivo',
        readonly=True
    )

    query_date = fields.Date(
        string='Fecha de Consulta',
        required=True,
        readonly=True,
        default=fields.Date.context_today,
        index=True,
        help='Fecha en que se realizó la consulta a Sentinel'
    )

    query_user_id = fields.Many2one(
        'res.users',
        string='Consultado Por',
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
        help='Usuario que realizó la consulta'
    )

    # ═══════════════════════════════════════════════════════════
    # CAMPOS COMPUTADOS (VIGENCIA)
    # ═══════════════════════════════════════════════════════════

    query_month = fields.Integer(
        string='Mes de Consulta',
        compute='_compute_query_period',
        store=True,
        index=True,
        help='Mes de vigencia (1-12)'
    )

    query_year = fields.Integer(
        string='Año de Consulta',
        compute='_compute_query_period',
        store=True,
        index=True,
        help='Año de vigencia'
    )

    state = fields.Selection([
        ('vigente', 'Vigente'),
        ('vencido', 'Vencido'),
    ], string='Estado',
        compute='_compute_state',
        store=True,
        index=True,
        help='Vigente = mes actual, Vencido = meses anteriores'
    )

    is_current_month = fields.Boolean(
        string='Es Mes Actual',
        compute='_compute_is_current_month',
        search='_search_is_current_month',
        help='True si el reporte pertenece al mes actual'
    )

    # ═══════════════════════════════════════════════════════════
    # CAMPOS ADICIONALES (INFO)
    # ═══════════════════════════════════════════════════════════

    notes = fields.Text(
        string='Observaciones',
        help='Notas adicionales sobre esta consulta'
    )

    # ═══════════════════════════════════════════════════════════
    # CONSTRAINTS
    # ═══════════════════════════════════════════════════════════

    _sql_constraints = [
        ('unique_document_month',
         'unique(document_number, query_month, query_year)',
         '⚠️ Ya existe un reporte vigente para este DNI en el mes actual. '
         'Solo se permite una consulta por DNI por mes.\n\n'
         'Reutilice el reporte existente o espere al próximo mes.'),
    ]

    @api.constrains('document_number')
    def _check_document_number(self):
        """Valida que el DNI tenga exactamente 8 dígitos numéricos."""
        for record in self:
            if not record.document_number:
                continue

            # Validar que sea exactamente 8 dígitos
            if not re.match(r'^\d{8}$', record.document_number):
                raise exceptions.ValidationError(
                    f"⚠️ El número de documento debe tener exactamente 8 dígitos.\n"
                    f"Recibido: '{record.document_number}'"
                )

    # ═══════════════════════════════════════════════════════════
    # MÉTODOS COMPUTE
    # ═══════════════════════════════════════════════════════════

    @api.depends('query_date')
    def _compute_query_period(self):
        """Extrae mes y año de la fecha de consulta."""
        for record in self:
            if record.query_date:
                record.query_month = record.query_date.month
                record.query_year = record.query_date.year
            else:
                record.query_month = 0
                record.query_year = 0

    @api.depends('query_month', 'query_year')
    def _compute_state(self):
        """
        Calcula el estado según vigencia mensual.
        Vigente = mes y año actuales
        Vencido = cualquier otro mes
        """
        today = fields.Date.context_today(self)
        current_month = today.month
        current_year = today.year

        for record in self:
            if record.query_month == current_month and record.query_year == current_year:
                record.state = 'vigente'
            else:
                record.state = 'vencido'

    @api.depends('query_month', 'query_year')
    def _compute_is_current_month(self):
        """Helper para búsquedas: indica si pertenece al mes actual."""
        today = fields.Date.context_today(self)
        current_month = today.month
        current_year = today.year

        for record in self:
            record.is_current_month = (
                record.query_month == current_month and
                record.query_year == current_year
            )

    def _search_is_current_month(self, operator, value):
        """
        Permite buscar por is_current_month en domains.
        Crítico para el wizard de búsqueda.
        """
        today = fields.Date.context_today(self)
        current_month = today.month
        current_year = today.year

        domain = [
            ('query_month', '=', current_month),
            ('query_year', '=', current_year)
        ]

        # Invertir dominio si operator es != o value es False
        if (operator == '=' and not value) or (operator == '!=' and value):
            domain = ['|',
                ('query_month', '!=', current_month),
                ('query_year', '!=', current_year)
            ]

        return domain

    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE BÚSQUEDA (API PÚBLICA)
    # ═══════════════════════════════════════════════════════════

    @api.model
    def search_current_report(self, document_number):
        """
        Busca un reporte vigente para el DNI especificado.

        Args:
            document_number (str): DNI a buscar (8 dígitos)

        Returns:
            recordset: Reporte vigente o empty recordset

        Uso desde wizard:
            report = self.env['adt.sentinel.report'].search_current_report('12345678')
            if report:
                # Mostrar reporte existente
            else:
                # Permitir nueva consulta
        """
        return self.search([
            ('document_number', '=', document_number),
            ('is_current_month', '=', True)
        ], limit=1)

    @api.model
    def get_report_history(self, document_number):
        """
        Obtiene el histórico completo de reportes para un DNI.

        Args:
            document_number (str): DNI a buscar

        Returns:
            recordset: Todos los reportes ordenados por fecha desc
        """
        return self.search([
            ('document_number', '=', document_number)
        ], order='query_date desc')

    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE ACCIÓN
    # ═══════════════════════════════════════════════════════════

    def action_view_image(self):
        """Abre el reporte en modo vista."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.sentinel.report',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('adt_sentinel.view_sentinel_report_form').id,
            'target': 'current',
        }

    def action_view_history(self):
        """Muestra el histórico completo del DNI."""
        self.ensure_one()
        return {
            'name': f'Histórico de Consultas - DNI {self.document_number}',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.sentinel.report',
            'view_mode': 'tree,form',
            'domain': [('document_number', '=', self.document_number)],
            'context': {'create': False},
        }

    # ═══════════════════════════════════════════════════════════
    # MÉTODOS OVERRIDE
    # ═══════════════════════════════════════════════════════════

    def unlink(self):
        """
        PROHIBIDO eliminar registros.
        El histórico debe mantenerse completo.
        """
        raise exceptions.UserError(
            '🚫 Operación no permitida\n\n'
            'Los reportes Sentinel NO pueden eliminarse.\n'
            'Se mantienen como histórico para trazabilidad y auditoría.\n\n'
            'Si necesita ocultar un reporte, contacte al administrador del sistema.'
        )

    def write(self, vals):
        """
        Bloquea modificación de campos críticos.
        Solo se permite editar 'notes'.
        """
        protected_fields = {
            'document_number', 'report_image', 'image_filename',
            'query_date', 'query_user_id'
        }

        # Verificar si se intenta modificar campos protegidos
        if any(field in vals for field in protected_fields):
            raise exceptions.UserError(
                '🚫 Operación no permitida\n\n'
                'No se pueden modificar los datos del reporte una vez creado.\n'
                'Los campos protegidos son: DNI, imagen, fecha y usuario.\n\n'
                'Solo puede editar el campo "Observaciones".'
            )

        return super(SentinelReport, self).write(vals)

    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE DISPLAY
    # ═══════════════════════════════════════════════════════════

    def name_get(self):
        """Display name: DNI - Mes/Año - Estado"""
        result = []
        month_names = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr',
            5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago',
            9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }

        for record in self:
            month_name = month_names.get(record.query_month, '??')
            state_icon = '✅' if record.state == 'vigente' else '📅'
            name = f"{state_icon} DNI {record.document_number} - {month_name}/{record.query_year}"
            result.append((record.id, name))

        return result
