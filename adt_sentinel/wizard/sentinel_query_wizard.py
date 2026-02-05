# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions
import re
import logging

_logger = logging.getLogger(__name__)

class SentinelQueryWizard(models.TransientModel):
    """
    Wizard para búsqueda y carga de reportes Sentinel.

    FLUJO:
    1. Usuario ingresa DNI y busca
    2. Sistema verifica si existe reporte vigente
    3a. Si existe → Muestra información del reporte existente
    3b. Si no existe → Permite subir nueva imagen
    """
    _name = 'adt.sentinel.query.wizard'
    _description = 'Consulta de Reporte Sentinel'

    # ═══════════════════════════════════════════════════════════
    # PASO 1: BÚSQUEDA
    # ═══════════════════════════════════════════════════════════

    document_number = fields.Char(
        string='Número de Documento (DNI)',
        size=8,
        help='Ingrese el DNI del cliente (8 dígitos)'
    )

    # ═══════════════════════════════════════════════════════════
    # PASO 2: RESULTADO DE BÚSQUEDA
    # ═══════════════════════════════════════════════════════════

    state = fields.Selection([
        ('search', 'Búsqueda'),
        ('found', 'Reporte Encontrado'),
        ('not_found', 'Permitir Carga'),
    ], string='Estado',
        default='search',
        readonly=True
    )

    # Información del reporte encontrado (readonly)
    found_report_id = fields.Many2one(
        'adt.sentinel.report',
        string='Reporte Encontrado',
        readonly=True
    )

    found_report_date = fields.Date(
        string='Fecha de Consulta',
        readonly=True
    )

    found_report_user = fields.Char(
        string='Consultado Por',
        readonly=True
    )

    found_report_image = fields.Binary(
        string='Imagen del Reporte',
        related='found_report_id.report_image',
        readonly=True
    )

    validity_message = fields.Html(
        string='Mensaje de Vigencia',
        compute='_compute_validity_message',
        sanitize=False
    )

    # ═══════════════════════════════════════════════════════════
    # PASO 3: CARGA DE NUEVO REPORTE (solo si no existe)
    # ═══════════════════════════════════════════════════════════

    new_report_image = fields.Binary(
        string='Subir Imagen del Reporte',
        help='Adjunte la captura de pantalla o imagen del reporte Sentinel'
    )

    new_image_filename = fields.Char(
        string='Nombre del Archivo'
    )

    cost_warning = fields.Html(
        string='Advertencia de Costo',
        default='''
            <div style="padding: 10px; background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 5px;">
                <h4 style="color: #856404; margin-top: 0;">⚠️ ADVERTENCIA DE COSTO</h4>
                <p style="margin-bottom: 0; color: #856404;">
                    <strong>Esta acción generará un costo de S/ 10.00</strong><br/>
                    Asegúrese de que realmente necesita consultar este DNI antes de continuar.
                </p>
            </div>
        ''',
        readonly=True,
        sanitize=False
    )

    notes = fields.Text(
        string='Observaciones',
        help='Notas adicionales sobre esta consulta (opcional)'
    )

    # ═══════════════════════════════════════════════════════════
    # CAMPOS COMPUTADOS
    # ═══════════════════════════════════════════════════════════

    @api.depends('found_report_id', 'state')
    def _compute_validity_message(self):
        """Genera mensaje HTML sobre la vigencia del reporte."""
        for wizard in self:
            if wizard.state == 'found' and wizard.found_report_id:
                report = wizard.found_report_id
                message = f'''
                    <div style="padding: 15px; background-color: #d4edda; border: 2px solid #28a745; border-radius: 5px;">
                        <h3 style="color: #155724; margin-top: 0;">✅ Reporte Encontrado</h3>
                        <table style="width: 100%; color: #155724;">
                            <tr>
                                <td style="padding: 5px;"><strong>📄 DNI:</strong></td>
                                <td style="padding: 5px;">{report.document_number}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px;"><strong>📅 Consultado:</strong></td>
                                <td style="padding: 5px;">{report.query_date.strftime('%d/%m/%Y')}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px;"><strong>👤 Por:</strong></td>
                                <td style="padding: 5px;">{report.query_user_id.name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px;"><strong>📊 Estado:</strong></td>
                                <td style="padding: 5px;">
                                    <span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 3px;">
                                        VIGENTE
                                    </span>
                                </td>
                            </tr>
                        </table>
                        <hr style="border-color: #28a745;"/>
                        <p style="margin-bottom: 0; color: #155724;">
                            <strong>ℹ️ Este reporte es válido hasta fin de mes.</strong><br/>
                            No es necesario realizar una nueva consulta. Puede ver la imagen usando el botón "Ver Reporte".
                        </p>
                    </div>
                '''
                wizard.validity_message = message
            elif wizard.state == 'not_found':
                wizard.validity_message = '''
                    <div style="padding: 15px; background-color: #d1ecf1; border: 2px solid #17a2b8; border-radius: 5px;">
                        <h4 style="color: #0c5460; margin-top: 0;">📋 No se encontró reporte vigente</h4>
                        <p style="margin-bottom: 0; color: #0c5460;">
                            No existe un reporte válido para este DNI en el mes actual.<br/>
                            <strong>Puede proceder a subir la imagen del nuevo reporte.</strong>
                        </p>
                    </div>
                '''
            else:
                wizard.validity_message = False


    # ═══════════════════════════════════════════════════════════
    # ACCIONES PRINCIPALES
    # ═══════════════════════════════════════════════════════════

    def action_search(self):
        """
        Acción: Buscar reporte vigente por DNI.

        Resultado:
        - Si existe → state='found', muestra info
        - Si no existe → state='not_found', permite carga
        """
        self.ensure_one()

        # Gracias a force_save="1" en el botón, el valor ya está guardado
        dni = (self.document_number or '').strip()

        _logger.info("🔍 Buscando DNI: %s", dni)

        # Validar que el DNI esté presente
        if not dni:
            raise exceptions.UserError(
                '⚠️ DNI requerido\n\n'
                'Debe ingresar el número de DNI antes de buscar.'
            )

        # Validar formato del DNI (exactamente 8 dígitos)
        if not re.match(r'^\d{8}$', dni):
            raise exceptions.UserError(
                '⚠️ Formato de DNI inválido\n\n'
                'El número de documento debe tener exactamente 8 dígitos numéricos.\n\n'
                f'Valor ingresado: "{dni}"\n'
                f'Longitud: {len(dni)} caracteres\n\n'
                'Ejemplo válido: 12345678'
            )

        # Buscar reporte vigente
        report = self.env['adt.sentinel.report'].search_current_report(dni)

        if report:
            # CASO A: Reporte encontrado
            _logger.info("✅ Reporte encontrado: ID=%s, Fecha=%s", report.id, report.query_date)
            self.write({
                'state': 'found',
                'found_report_id': report.id,
                'found_report_date': report.query_date,
                'found_report_user': report.query_user_id.name,
                'document_number': report.document_number,
            })
        else:
            # CASO B: No existe reporte vigente
            _logger.info("❌ No se encontró reporte vigente para DNI: %s", dni)
            self.write({
                'state': 'not_found',
                'document_number': dni,
            })

        # Retornar acción para recargar el formulario del wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.sentinel.query.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('adt_sentinel.view_sentinel_query_wizard_form_search').id,
            'target': 'new',
            'context': dict(self.env.context, wizard_reloaded=True),
        }

    def action_upload_report(self):
        """
        Acción: Subir nuevo reporte.

        Validaciones:
        - Imagen requerida
        - DNI válido
        - No existe reporte vigente (doble verificación)

        Resultado:
        - Crea registro en adt.sentinel.report
        - Abre el reporte creado
        """
        self.ensure_one()

        # ────────────────────────────────────────────────────────
        # VALIDACIONES PRE-CREACIÓN
        # ────────────────────────────────────────────────────────

        if not self.new_report_image:
            raise exceptions.UserError(
                '⚠️ Imagen requerida\n\n'
                'Debe adjuntar la imagen del reporte Sentinel antes de continuar.\n\n'
                'Esta consulta tiene un costo de S/ 10.00, asegúrese de tener la imagen lista.'
            )

        # Doble verificación: ¿Realmente no existe?
        existing = self.env['adt.sentinel.report'].search_current_report(
            self.document_number
        )

        if existing:
            raise exceptions.UserError(
                '⚠️ Reporte duplicado detectado\n\n'
                f'Mientras preparaba la carga, se detectó que ya existe un reporte vigente '
                f'para el DNI {self.document_number}.\n\n'
                f'Consultado por: {existing.query_user_id.name}\n'
                f'Fecha: {existing.query_date.strftime("%d/%m/%Y")}\n\n'
                'Por favor cierre este asistente y vuelva a buscar el DNI.'
            )

        # ────────────────────────────────────────────────────────
        # CREACIÓN DEL REGISTRO
        # ────────────────────────────────────────────────────────

        try:
            report = self.env['adt.sentinel.report'].create({
                'document_number': self.document_number,
                'report_image': self.new_report_image,
                'image_filename': self.new_image_filename or f'sentinel_{self.document_number}.jpg',
                'query_date': fields.Date.context_today(self),
                'query_user_id': self.env.user.id,
                'notes': self.notes,
            })

            # ────────────────────────────────────────────────────
            # CONFIRMACIÓN Y APERTURA
            # ────────────────────────────────────────────────────

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'adt.sentinel.report',
                'res_id': report.id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'form_view_initial_mode': 'readonly',
                },
            }

        except exceptions.ValidationError as e:
            # Error de constraint (duplicado, formato, etc.)
            raise exceptions.UserError(
                f'⚠️ Error al crear el reporte\n\n{str(e)}'
            )

    def action_view_report(self):
        """Abre el reporte encontrado en modo solo lectura."""
        self.ensure_one()

        if not self.found_report_id:
            raise exceptions.UserError(
                '⚠️ No hay reporte para mostrar'
            )

        return self.found_report_id.action_view_image()

    def action_view_history(self):
        """Muestra el histórico completo de consultas del DNI."""
        self.ensure_one()

        return {
            'name': f'Histórico de Consultas - DNI {self.document_number}',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.sentinel.report',
            'view_mode': 'tree,form',
            'domain': [('document_number', '=', self.document_number)],
            'context': {'create': False},
            'target': 'current',
        }

    def action_cancel(self):
        """Cierra el wizard sin hacer nada."""
        return {'type': 'ir.actions.act_window_close'}
