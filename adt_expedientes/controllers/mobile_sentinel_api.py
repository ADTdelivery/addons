# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import logging
import re

from .mobile_api import AdtExpedientesMobileAPI

_logger = logging.getLogger(__name__)


class SentinelMobileAPI(AdtExpedientesMobileAPI):
    """Sentinel endpoints secured with the same token auth used by mobile_api."""

    def _validate_dni(self, document_number, kwargs):
        dni = self._get_param('document_number', document_number, kwargs)
        if not dni:
            return None, {'success': False, 'error': 'document_number required'}
        dni = str(dni).strip()
        if not re.match(r'^\d{8,14}$', dni):
            return None, {'success': False, 'error': 'document_number must be 8 digits'}
        return dni, None

    @http.route('/api/sentinel/report/get', type='json', auth='none', methods=['POST'], csrf=False)
    def sentinel_report_get(self, document_number=None, **kwargs):
        """
        Return current-month Sentinel report for a DNI (or null if none).

        Example Request JSON:
        {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "document_number": "12345678"
            },
            "id": null
        }

        Example Response (Report Exists):
        {
            "jsonrpc": "2.0",
            "id": null,
            "result": {
                "success": true,
                "data": {
                    "id": 15,
                    "document_number": "12345678",
                    "query_date": "2026-02-05",
                    "query_user": "María Torres",
                    "state": "vigente",
                    "images": [
                        {
                            "id": 1,
                            "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
                            "image_filename": "sentinel_12345678_1.jpg",
                            "description": "Página 1 - Resumen crediticio",
                            "sequence": 10
                        },
                        {
                            "id": 2,
                            "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
                            "image_filename": "sentinel_12345678_2.jpg",
                            "description": "Página 2 - Detalle de deudas",
                            "sequence": 20
                        }
                    ],
                    "image_count": 2
                }
            }
        }

        Example Response (No Report):
        {
            "jsonrpc": "2.0",
            "id": null,
            "result": {
                "success": true,
                "data": null
            }
        }
        """
        try:
            user, err = self._ensure_auth()
            if err:
                return err

            dni, validation_err = self._validate_dni(document_number, kwargs)
            if validation_err:
                return validation_err

            Sentinel = request.env['adt.sentinel.report'].sudo()
            report = Sentinel.search_current_report(dni)
            if not report:
                return {'success': True, 'data': None}

            # Build images list
            images = []
            for img in report.image_ids:
                images.append({
                    'id': img.id,
                    'image_base64': img.image,
                    'image_filename': img.image_filename,
                    'description': img.description,
                    'sequence': img.sequence,
                })

            return {
                'success': True,
                'data': {
                    'id': report.id,
                    'document_number': report.document_number,
                    'query_date': str(report.query_date),
                    'query_user': report.query_user_id.name if report.query_user_id else 'N/A',
                    'state': report.state,
                    'images': images,
                    'image_count': len(images),
                }
            }
        except Exception as e:
            _logger.error('Error getting Sentinel report for %s: %s', document_number, e, exc_info=True)
            return {'success': False, 'error': 'server_error', 'message': str(e)}

    @http.route('/api/sentinel/report/create', type='json', auth='none', methods=['POST'], csrf=False)
    def sentinel_report_create(self, document_number=None, images=None,
                               query_user_id=None, query_date=None, notes=None, **kwargs):
        """
        Create a new Sentinel report with multiple images if none exists for the current month.

        :param document_number: DNI (8 digits)
        :param images: List of image objects with keys: 'image_base64', 'image_filename', 'description'
        :param query_user_id: User ID who performs the query
        :param query_date: Date of the query
        :param notes: Additional notes

        Example Request JSON:
        {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "document_number": "12345678",
                "images": [
                    {
                        "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
                        "image_filename": "sentinel_febrero_pagina1.png",
                        "description": "Página 1 - Resumen crediticio",
                        "sequence": 10
                    },
                    {
                        "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
                        "image_filename": "sentinel_febrero_pagina2.png",
                        "description": "Página 2 - Detalle de deudas",
                        "sequence": 20
                    }
                ],
                "query_user_id": 8,
                "query_date": "2026-02-05",
                "notes": "Consulta solicitada por el cliente"
            },
            "id": null
        }

        Example Response (Success):
        {
            "jsonrpc": "2.0",
            "id": null,
            "result": {
                "success": true,
                "message": "Reporte Sentinel registrado correctamente",
                "record_id": 16,
                "images_count": 2
            }
        }

        Example Response (Error - Already Exists):
        {
            "jsonrpc": "2.0",
            "id": null,
            "result": {
                "success": false,
                "error": "existing_current_month",
                "message": "Ya existe un reporte vigente este mes",
                "data": {
                    "id": 15,
                    "query_date": "2026-02-05",
                    "query_user": "María Torres"
                }
            }
        }
        """
        try:
            user, err = self._ensure_auth()
            if err:
                return err

            dni, validation_err = self._validate_dni(document_number, kwargs)
            if validation_err:
                return validation_err

            images = self._get_param('images', images, kwargs)
            query_user_id = self._get_param('query_user_id', query_user_id, kwargs) or user.id
            query_date_val = self._get_param('query_date', query_date, kwargs)
            notes = self._get_param('notes', notes, kwargs)

            # Validate images
            if not images or not isinstance(images, list) or len(images) == 0:
                return {'success': False, 'error': 'images_required', 'message': 'Al menos una imagen es requerida'}

            # Validate each image before processing
            for idx, img_data in enumerate(images, 1):
                if not isinstance(img_data, dict):
                    return {'success': False, 'error': 'invalid_image_format',
                            'message': f'Imagen {idx}: formato inválido, debe ser un objeto'}

                image_base64 = img_data.get('image_base64')
                if not image_base64:
                    return {'success': False, 'error': 'missing_image_data',
                            'message': f'Imagen {idx}: campo image_base64 es requerido'}

            # parse query_date if provided
            qdate = None
            if query_date_val:
                try:
                    qdate = fields.Date.to_date(query_date_val)
                except Exception as e:
                    _logger.warning('Invalid query_date format: %s', query_date_val)
                    return {'success': False, 'error': 'invalid_query_date', 'message': 'Formato de fecha inválido'}
            else:
                qdate = fields.Date.context_today(request.env['adt.sentinel.report'])

            # Use new environment to avoid transaction issues
            with request.env.cr.savepoint():
                Sentinel = request.env['adt.sentinel.report'].sudo()

                # Check if report already exists
                existing = Sentinel.search_current_report(dni)
                if existing:
                    return {
                        'success': False,
                        'error': 'existing_current_month',
                        'message': 'Ya existe un reporte vigente este mes',
                        'data': {
                            'id': existing.id,
                            'query_date': str(existing.query_date),
                            'query_user': existing.query_user_id.name,
                        }
                    }

                # Process images
                image_lines = []
                for idx, img_data in enumerate(images, 1):
                    image_base64 = img_data.get('image_base64')

                    # strip data URL prefix if present
                    if isinstance(image_base64, str) and ',' in image_base64:
                        image_base64 = image_base64.split(',', 1)[1]

                    image_filename = img_data.get('image_filename') or f'sentinel_{dni}_{idx}.jpg'
                    description = img_data.get('description') or f'Imagen {idx}'
                    sequence = img_data.get('sequence', idx * 10)

                    image_lines.append((0, 0, {
                        'image': image_base64,
                        'image_filename': image_filename,
                        'description': description,
                        'sequence': sequence,
                    }))

                # Validate query_user_id
                user_id = int(query_user_id) if query_user_id else user.id
                User = request.env['res.users'].sudo()
                if not User.browse(user_id).exists():
                    return {'success': False, 'error': 'invalid_user', 'message': 'Usuario no válido'}

                # Create the report with images
                record = Sentinel.create({
                    'document_number': dni,
                    'query_user_id': user_id,
                    'query_date': qdate,
                    'notes': notes,
                    'image_ids': image_lines,
                })

                return {
                    'success': True,
                    'message': 'Reporte Sentinel registrado correctamente',
                    'record_id': record.id,
                    'images_count': len(image_lines),
                }

        except Exception as e:
            # Rollback is handled automatically by savepoint
            _logger.error('Error creating Sentinel report for %s: %s', dni, e, exc_info=True)
            return {'success': False, 'error': 'server_error', 'message': str(e)}
