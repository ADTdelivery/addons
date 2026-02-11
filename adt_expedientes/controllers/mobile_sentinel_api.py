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
        """Return current-month Sentinel report for a DNI (or null if none)."""
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

        return {
            'success': True,
            'data': {
                'id': report.id,
                'document_number': report.document_number,
                'query_date': str(report.query_date),
                'query_user': report.query_user_id.name,
                'state': report.state,
                'image_base64': report.report_image,
                'image_filename': report.image_filename,
            }
        }

    @http.route('/api/sentinel/report/create', type='json', auth='none', methods=['POST'], csrf=False)
    def sentinel_report_create(self, document_number=None, image_base64=None, image_filename=None,
                               query_user_id=None, query_date=None, notes=None, **kwargs):
        """Create a new Sentinel report if none exists for the current month."""
        user, err = self._ensure_auth()
        if err:
            return err

        dni, validation_err = self._validate_dni(document_number, kwargs)
        if validation_err:
            return validation_err

        image_base64 = self._get_param('image_base64', image_base64, kwargs)
        image_filename = self._get_param('image_filename', image_filename, kwargs)
        query_user_id = self._get_param('query_user_id', query_user_id, kwargs) or user.id
        query_date_val = self._get_param('query_date', query_date, kwargs)
        notes = self._get_param('notes', notes, kwargs)

        if not image_base64:
            return {'success': False, 'error': 'image_base64 required'}

        # strip data URL prefix if present
        if isinstance(image_base64, str) and ',' in image_base64:
            image_base64 = image_base64.split(',', 1)[1]

        # parse query_date if provided
        qdate = None
        if query_date_val:
            try:
                qdate = fields.Date.to_date(query_date_val)
            except Exception:
                return {'success': False, 'error': 'invalid query_date'}
        else:
            qdate = fields.Date.context_today(request.env['adt.sentinel.report'])

        Sentinel = request.env['adt.sentinel.report'].sudo()
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

        try:
            record = Sentinel.create({
                'document_number': dni,
                'report_image': image_base64,
                'image_filename': image_filename or f'sentinel_{dni}.jpg',
                'query_user_id': int(query_user_id) if query_user_id else user.id,
                'query_date': qdate,
                'notes': notes,
            })
            return {
                'success': True,
                'message': 'Reporte Sentinel registrado correctamente',
                'record_id': record.id,
            }
        except Exception as e:
            _logger.error('Error creating Sentinel report for %s: %s', dni, e, exc_info=True)
            return {'success': False, 'error': 'server_error', 'message': str(e)}
