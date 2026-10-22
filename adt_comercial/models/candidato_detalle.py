# -*- coding: utf-8 -*-
"""Expediente de evaluación consultado al abrir el drawer, respetando permisos."""
import mimetypes
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext


class CandidatoDetalle(models.AbstractModel):
    _inherit = 'adt.comercial.clientes.dashboard'

    def _riesgo_etiqueta(self, rec, name):
        field = rec._fields.get(name)
        if not field:
            return ''
        value = rec[name]
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value or '')
        if field.type == 'many2one':
            return value.display_name if value else ''
        if field.type in ('date', 'datetime'):
            return str(value) if value else ''
        if field.type == 'boolean':
            return 'Sí' if value else 'No'
        if field.type in ('float', 'monetary', 'integer'):
            return value or 0
        if field.type == 'html':
            return html2plaintext(value or '')
        return value if value not in (False, None) else ''

    def _riesgo_campos(self, rec, names):
        return [{'label': rec._fields[n].string, 'valor': self._riesgo_etiqueta(rec, n),
                 'tipo': rec._fields[n].type}
                for n in names if n in rec._fields and (rec._fields[n].type in ('boolean', 'float', 'monetary', 'integer') or rec[n] not in (False, None, ''))]

    def _riesgo_adjuntos(self, attachments):
        out = []
        for a in attachments:
            try:
                a.check_access_rights('read')
                a.check_access_rule('read')
                mime = a.mimetype or 'application/octet-stream'
                out.append({'nombre': a.name, 'mime': mime, 'url': '/web/content/%s?download=false' % a.id,
                            'miniatura': '/web/image/%s/240x160' % a.id if mime.startswith('image/') else '',
                            'descarga': '/web/content/%s?download=true' % a.id})
            except AccessError:
                continue
        return out

    def _riesgo_binarios(self, rec, specs):
        result = []
        for field, label, filename, default_mime in specs:
            if field not in rec._fields or not rec.with_context(bin_size=True)[field]:
                continue
            name = (rec[filename] if filename and filename in rec._fields else '') or label
            mime = mimetypes.guess_type(name)[0] or default_mime
            url = '/web/content/%s/%s/%s' % (rec._name, rec.id, field)
            result.append({'nombre': name, 'mime': mime, 'url': url + '?download=false',
                           'miniatura': url if mime.startswith('image/') else '',
                           'descarga': url + '?download=true'})
        return result

    def _riesgo_historial(self, rec):
        events = []
        if 'message_ids' not in rec._fields:
            return events
        for message in rec.message_ids:
            try:
                body = html2plaintext(message.body or '').strip()
                changes = []
                try:
                    message.check_field_access_rights('read', ['tracking_value_ids'])
                    tracking = message.tracking_value_ids
                    tracking.check_access_rights('read')
                    tracking.check_access_rule('read')
                    for t in tracking:
                        old = (t.get_old_display_value() or [''])[0]
                        new = (t.get_new_display_value() or [''])[0]
                        changes.append('%s: %s → %s' % (t.field_desc, old or '—', new or '—'))
                except AccessError:
                    pass
                files = self._riesgo_adjuntos(message.attachment_ids)
                if body or changes or files:
                    events.append({'fecha': str(message.date), 'autor': message.author_id.name or '',
                                   'texto': body, 'cambios': changes, 'evidencias': files})
            except AccessError:
                continue
        return events

    def _riesgo_capturas(self, accounts):
        model = 'adt.captura.record'
        if model not in self.env:
            return {'disponible': False, 'motivo': 'El módulo de capturas no está instalado.', 'items': []}
        if not self.env[model].check_access_rights('read', raise_exception=False):
            return {'disponible': False, 'motivo': 'Tu usuario no tiene permiso para consultar los detalles de capturas.', 'items': []}
        captures = self.env[model].with_context(active_test=False).search([
            ('cuenta_id', 'in', accounts.ids), ('company_id', 'in', self.env.companies.ids)], order='create_date desc, id desc')
        items = []
        for rec in captures:
            evidence = self._riesgo_adjuntos(rec.evidencia_archivos)
            evidence += self._riesgo_binarios(rec, [
                ('voucher_file', 'Voucher de intervención', 'voucher_filename', 'application/octet-stream'),
                ('documento_desafiliacion', 'Documento de desafiliación', None, 'application/pdf'),
                ('evidencia_entrega', 'Evidencia de entrega', None, 'image/jpeg')])
            appeals = []
            if 'appeal_ids' in rec._fields and self.env[rec._fields['appeal_ids'].comodel_name].check_access_rights('read', raise_exception=False):
                for appeal in rec.appeal_ids:
                    appeals.append({'fecha': str(appeal.create_date), 'motivo': appeal.appeal_reason,
                                    'evidencias': self._riesgo_binarios(appeal, [('appeal_evidence', 'Evidencia de apelación', None, 'application/octet-stream')])})
            items.append({'id': rec.id, 'numero': rec.name, 'cuenta': rec.cuenta_id.reference_no,
                          'placa': rec.vehicle_id.license_plate or '', 'fecha': str(rec.create_date),
                          'cuenta_id': rec.cuenta_id.id, 'papeleta_id': rec.papeleta_id.id,
                          'estado': self._riesgo_etiqueta(rec, 'state'), 'estado_clave': rec.state,
                          'origen': self._riesgo_etiqueta(rec, 'source_type') or 'Origen no registrado',
                          'motivo': rec.comentarios_captura or rec.observaciones or rec.notes or self._riesgo_etiqueta(rec, 'retention_reason') or '',
                          'campos': self._riesgo_campos(rec, [
                              'capture_type', 'source_type', 'commitment_date', 'moto_recogida', 'motivo_no_recogida',
                              'retention_reason', 'retention_date', 'liberacion_tipo', 'payment_state',
                              'intervention_fee', 'voucher_number', 'payment_date', 'motivo_no_pago',
                              'dias_mora', 'numero_cuotas_vencidas', 'papeleta_id',
                              'comentarios_captura', 'observaciones', 'notes', 'capturador_id', 'supervisor_id', 'write_date']),
                          'moneda': rec.company_currency_id.name, 'evidencias': evidence,
                          'apelaciones': appeals, 'historial': self._riesgo_historial(rec)})
        return {'disponible': True, 'items': items,
                'activas': len(captures.filtered(lambda c: c.state in ('capturado', 'disolucion_contrato'))),
                'canceladas': len(captures.filtered(lambda c: c.state == 'cancelado'))}

    def _riesgo_papeletas(self, accounts, today, captures):
        model = 'adt.papeleta'
        if model not in self.env or not self.env[model].check_access_rights('read', raise_exception=False):
            return {'disponible': False, 'motivo': 'No hay acceso al detalle de papeletas.', 'items': []}
        tickets = self.env[model].search([('vehicle_id', 'in', accounts.mapped('vehiculo_id').ids),
                                         ('company_id', 'in', self.env.companies.ids)], order='fecha_papeleta desc, id desc')
        # Se atribuye la papeleta al periodo de titularidad, sin incluir infracciones del siguiente cliente.
        vehicle_accounts = self.env['adt.comercial.cuentas'].search([
            ('vehiculo_id', 'in', accounts.mapped('vehiculo_id').ids),
            ('company_id', 'in', self.env.companies.ids), ('state', '!=', 'borrador')], order='fecha_desembolso asc, id asc')
        linked = {c['papeleta_id']: c['cuenta_id'] for c in captures['items'] if c['papeleta_id']}
        items = []
        for p in tickets:
            matched = self.env['adt.comercial.cuentas']
            for account in accounts.filtered(lambda a: a.vehiculo_id == p.vehicle_id):
                start = account.fecha_desembolso
                dates = account.cuota_ids.mapped('fecha_cronograma')
                end = max(filter(None, dates), default=today)
                later = vehicle_accounts.filtered(lambda a: a.id != account.id and a.partner_id != account.partner_id
                    and a.fecha_desembolso and start and a.fecha_desembolso >= start)
                if later:
                    end = min(end, min(later.mapped('fecha_desembolso')) - timedelta(days=1))
                if p.fecha_papeleta and (not start or p.fecha_papeleta >= start) and p.fecha_papeleta <= end:
                    matched |= account
            if p.id in linked:
                matched |= accounts.filtered(lambda a: a.id == linked[p.id])
            if not matched:
                continue
            installments = p.cuotas_ids
            pending = installments.filtered(lambda q: q.state == 'pendiente')
            balance = 0 if p.state == 'pagado' else (sum(pending.mapped('amount')) if p.payment_method == 'fraccionado' and installments else p.monto)
            evidence = self._riesgo_adjuntos(p.attachment_ids | p.attachment_cuotas_ids)
            items.append({'id': p.id, 'numero': p.name, 'fecha': str(p.fecha_papeleta), 'cuentas': matched.mapped('reference_no'),
                          'placa': p.vehicle_id.license_plate or '', 'estado': self._riesgo_etiqueta(p, 'state'),
                          'estado_clave': p.state, 'importe': p.monto, 'saldo': balance,
                          'moneda': p.company_currency_id.name, 'detalle': p.detalle or 'Detalle de la infracción no registrado.',
                          'campos': self._riesgo_campos(p, ['payment_method', 'fecha_pago', 'fecha_captura',
                              'fecha_vencimiento_final', 'tiene_prorroga', 'dias_prorroga', 'motivo_prorroga', 'capturado', 'recolocada']),
                          'cuotas': [{'nombre': q.name, 'fecha': str(q.due_date) if q.due_date else '',
                                      'monto': q.amount, 'estado': self._riesgo_etiqueta(q, 'state')} for q in installments],
                          'evidencias': evidence, 'historial': self._riesgo_historial(p)})
        return {'disponible': True, 'items': items}

    def _riesgo_creditos(self, accounts, today):
        rows = []
        can_payments = self.env['account.payment'].check_access_rights('read', raise_exception=False)
        can_observations = self.env['adt.comercial.observaciones'].check_access_rights('read', raise_exception=False)
        for account in accounts:
            quotas = []
            for q in account.cuota_ids.sorted(key=lambda r: (r.fecha_cronograma or today, r.id)):
                valid = q.state != 'anulada'
                paid = []
                if can_payments:
                    for p in q.payment_ids.sorted(key=lambda r: (r.date or today, r.id), reverse=True):
                        paid.append({'fecha': str(p.date), 'importe': p.amount, 'operacion': p.ref or '',
                                     'estado': self._riesgo_etiqueta(p, 'state'), 'contabilizado': p.state == 'posted',
                                     'diario': p.journal_id.display_name, 'mora': p.mora,
                                     'mora_estado': self._riesgo_etiqueta(p, 'mora_state'),
                                     'mora_pagada_parcial': p.mora_pagado})
                observations = []
                if can_observations:
                    for obs in q.observacion_ids:
                        observations.append({'fecha': str(obs.fecha) if obs.fecha else '', 'texto': obs.comentario or '',
                                             'evidencias': self._riesgo_adjuntos(obs.attachment_ids)})
                quota_files = self._riesgo_binarios(q, [('voucher_image', 'Voucher de cuota', None, 'image/jpeg')])
                quotas.append({'id': q.id, 'nombre': q.name or str(q.id), 'fecha': str(q.fecha_cronograma) if q.fecha_cronograma else '',
                               'monto': q.monto, 'saldo': max(q.saldo, 0) if valid else 0,
                               'estado': self._riesgo_etiqueta(q, 'state'), 'estado_clave': q.state,
                               'atraso_dias': max((today - q.fecha_cronograma).days, 0) if valid and q.saldo > 0 and q.fecha_cronograma else 0,
                               'mora': q.mora_pendiente if valid and can_payments else None,
                               'subcuota': bool(q.parent_id), 'pagos': paid, 'observaciones': observations, 'evidencias': quota_files})
            files = self._riesgo_adjuntos(account.attachment_ids) if 'attachment_ids' in account._fields else []
            rows.append({'id': account.id, 'referencia': account.reference_no, 'estado': self._riesgo_etiqueta(account, 'state'),
                         'estado_clave': account.state, 'recuperado': account.recuperado,
                         'placa': account.vehiculo_id.license_plate or '', 'moneda': account.currency_id.name,
                         'fecha_desembolso': str(account.fecha_desembolso) if account.fecha_desembolso else '',
                         'saldo': sum(q['saldo'] for q in quotas),
                         'vencido': sum(q['saldo'] for q in quotas if q['atraso_dias'] > 0),
                         'mora': sum(q['mora'] or 0 for q in quotas) if can_payments else None,
                         'cuotas': quotas, 'evidencias': files, 'historial': self._riesgo_historial(account),
                         'pagos_disponibles': can_payments})
        return {'disponible': True, 'items': rows}

    @api.model
    def detalle_candidato(self, partner_id):
        self._check_acceso()
        partner = self.env['res.partner'].browse(int(partner_id)).exists()
        if not partner:
            raise UserError(_('El cliente ya no existe.'))
        partner.check_access_rights('read')
        partner.check_access_rule('read')
        accounts = self.env['adt.comercial.cuentas'].with_context(active_test=False).search([
            ('partner_id', '=', partner.id), ('company_id', 'in', self.env.companies.ids),
            ('state', 'in', ['en_curso', 'pagado', 'cancelado'])], order='fecha_desembolso desc, id desc')
        if not accounts:
            raise AccessError(_('No tienes cuentas accesibles de este cliente en las empresas seleccionadas.'))
        today = fields.Date.context_today(self)
        captures = self._riesgo_capturas(accounts)
        tickets = self._riesgo_papeletas(accounts, today, captures)
        credits = self._riesgo_creditos(accounts, today)
        totals = defaultdict(lambda: {'saldo': 0, 'vencido': 0, 'mora': 0, 'papeletas': 0})
        for account in credits['items']:
            if account['estado_clave'] != 'en_curso':
                continue
            currency = totals[account['moneda']]
            for key in ('saldo', 'vencido', 'mora'):
                currency[key] += account[key] or 0
        for ticket in tickets['items']:
            totals[ticket['moneda']]['papeletas'] += ticket['saldo']
        Seguimiento = self.env['adt.cliente.seguimiento']
        seguimiento = Seguimiento.search([('partner_id', '=', partner.id)], limit=1) if Seguimiento.check_access_rights('read', raise_exception=False) else Seguimiento
        return {'cliente_id': partner.id, 'actualizado': str(fields.Datetime.now()),
                'capturas': captures, 'papeletas': tickets, 'creditos': credits,
                'totales': dict(totals), 'seguimiento_historial': self._riesgo_historial(seguimiento) if seguimiento else [],
                'pagos_disponibles': self.env['account.payment'].check_access_rights('read', raise_exception=False)}
