# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SentinelReportImage(models.Model):
    """
    Modelo para almacenar múltiples imágenes asociadas a un reporte Sentinel.

    Permite adjuntar varias capturas de pantalla o documentos
    relacionados a una misma consulta de reporte crediticio.
    """
    _name = 'adt.sentinel.report.image'
    _description = 'Imágenes de Reporte Sentinel'
    _order = 'sequence, id'

    # ═══════════════════════════════════════════════════════════
    # CAMPOS PRINCIPALES
    # ═══════════════════════════════════════════════════════════

    report_id = fields.Many2one(
        'adt.sentinel.report',
        string='Reporte Sentinel',
        required=True,
        ondelete='cascade',
        index=True,
        help='Reporte al que pertenece esta imagen'
    )

    image = fields.Binary(
        string='Imagen',
        required=True,
        attachment=True,
        help='Captura de pantalla o documento relacionado'
    )

    image_filename = fields.Char(
        string='Nombre del Archivo',
        help='Nombre original del archivo subido'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de visualización de las imágenes'
    )

    description = fields.Char(
        string='Descripción',
        help='Descripción breve de esta imagen (ej: Página 1, Detalle de deudas, etc.)'
    )

    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE DISPLAY
    # ═══════════════════════════════════════════════════════════

    def name_get(self):
        """Display name: Reporte - Descripción"""
        result = []
        for record in self:
            if record.description:
                name = f"{record.report_id.document_number} - {record.description}"
            elif record.image_filename:
                name = f"{record.report_id.document_number} - {record.image_filename}"
            else:
                name = f"{record.report_id.document_number} - Imagen {record.id}"
            result.append((record.id, name))
        return result
