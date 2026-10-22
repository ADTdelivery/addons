# -*- coding: utf-8 -*-
"""Adaptador de los asistentes comerciales para el popup nativo de Flota 360."""
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


WIZARDS = {
    'cuota': ('adt.register.payment', 'action_create_payments'),
    'mora': ('adt.pagar.mora.wizard', 'action_confirm_pagar_mora'),
    'cascada': ('adt.cancelar.credito.wizard', 'action_pagar'),
}


class Flota360Pagos(models.AbstractModel):
    _inherit = 'adt.flota360'

    def _pago_target(self, vehicle_id, params):
        tipo = params.get('tipo')
        if tipo not in WIZARDS:
            raise ValidationError(_('Tipo de pago no válido.'))
        vehicle = self._vehiculo(vehicle_id)
        vehicle.check_access_rights('read')
        model = 'adt.comercial.cuentas' if tipo == 'cascada' else 'adt.comercial.cuotas'
        rec = self.env[model].browse(int(params.get('id') or 0)).exists()
        if not rec:
            raise ValidationError(_('La cuenta o cuota ya no existe.'))
        rec.check_access_rights('read')
        rec.check_access_rule('read')
        rec.check_access_rights('write')
        rec.check_access_rule('write')
        account = rec if tipo == 'cascada' else rec.cuenta_id
        account.check_access_rights('read')
        account.check_access_rule('read')
        if account.vehiculo_id != vehicle or account.company_id not in self.env.companies:
            raise AccessError(_('El pago no corresponde a este vehículo o empresa.'))
        if account.state != 'en_curso':
            raise ValidationError(_('Solo se pueden registrar pagos en cuentas en curso.'))
        wizard_model = self.env[WIZARDS[tipo][0]].with_company(account.company_id)
        wizard_model.check_access_rights('create')
        return tipo, rec, account, wizard_model

    def _pago_calculo(self, tipo, rec, account, wizard_model, fecha):
        fecha = fields.Date.to_date(fecha or fields.Date.context_today(self))
        if tipo == 'cascada':
            wizard = wizard_model.new({'cuenta_id': account.id, 'payment_date': fecha})
            cantidad, capital, mora = wizard._deuda()
            return {'capital': capital, 'mora_auto': mora, 'total': round(capital + mora, 2),
                    'cuotas': cantidad, 'mora_dias': 0, 'moneda': account.currency_id.name}
        if tipo == 'mora':
            wizard = wizard_model.new({'cuota_id': rec.id})
            mora = wizard.mora_pendiente_real
            return {'capital': 0, 'mora_auto': mora, 'total': mora, 'mora_dias': 0,
                    'moneda': account.currency_id.name}
        wizard = wizard_model.new({'cuota_id': rec.id, 'company_id': account.company_id.id, 'payment_date': fecha})
        return {'capital': max(rec.saldo, 0), 'mora_auto': wizard.mora_auto,
                'total': round(max(rec.saldo, 0) + wizard.mora_auto, 2),
                'mora_dias': wizard.mora_dias, 'moneda': account.currency_id.name}

    @api.model
    def simular_pago(self, vehicle_id, params, payment_date=False):
        tipo, rec, account, wizard_model = self._pago_target(vehicle_id, params or {})
        return self._pago_calculo(tipo, rec, account, wizard_model, payment_date)

    @api.model
    def formulario(self, clave, vehicle_id, res_id=False, params=None):
        if clave != 'pago':
            return super().formulario(clave, vehicle_id, res_id=res_id, params=params)
        params = params or {}
        tipo, rec, account, W = self._pago_target(vehicle_id, params)
        today = fields.Date.context_today(self)
        summary = self._pago_calculo(tipo, rec, account, W, today)
        if summary['capital' if tipo == 'cuota' else 'total'] <= 0:
            raise ValidationError(_('No hay saldo pendiente para este pago.'))
        journals = self.env['account.journal'].search([
            ('company_id', '=', account.company_id.id), ('type', 'in', ['bank', 'cash'])])
        if not journals:
            raise ValidationError(_('Configura un diario de banco o caja para esta empresa antes de cobrar.'))
        campo = lambda name, **kw: self._campo_spec(W, name, **kw)
        date = campo('payment_date', label='Fecha del pago', required=True)
        journal = campo('journal_id', label='Cuenta de destino / diario', type='selection',
                        required=True, options=[[j.id, j.display_name] for j in journals]) if tipo != 'cascada' else None
        operation = 'numero_operacion' if tipo == 'cascada' else ('mora_operacion' if tipo == 'mora' else 'communication')
        base = [date, campo(operation, label='N° de operación', required=True, placeholder='Número del depósito o transferencia')]
        if journal:
            base.append(journal)
        values = {'payment_date': str(today), operation: params.get('operacion') or ''}
        sections = []
        if tipo == 'cascada':
            base += [campo('cancelar_todo', label='Pagar toda la deuda de la cuenta'),
                     campo('monto', label='Importe a aplicar', visible=['cancelar_todo', False], required=False)]
            values.update({'cancelar_todo': True, 'monto': summary['total']})
            help_text = _('El pago se distribuye desde la cuota más antigua: primero capital y luego mora. Desmarca el pago total para abonar un importe parcial.')
        else:
            base.append(campo('amount', label='Importe de la cuota' if tipo == 'cuota' else 'Importe de mora', required=True))
            values.update({'journal_id': journals[0].id, 'amount': min(float(params.get('monto') or summary['capital' if tipo == 'cuota' else 'total']), summary['capital' if tipo == 'cuota' else 'total'])})
            help_text = _('El importe puede ser parcial. El cronograma y los indicadores se actualizarán después de registrar el pago.')
            if tipo == 'cuota':
                sections.append({'titulo': 'Mora de la cuota', 'campos': [
                    campo('mora_manual', label='Ajustar la mora manualmente'),
                    campo('mora', label='Importe de mora', required=False),
                    campo('mora_state', label='Estado de la mora', segmentado=True)]})
                values.update({'mora_manual': False, 'mora': summary['mora_auto'], 'mora_state': 'pending'})
        return {'clave': 'pago', 'res_id': False, 'titulo': {
            'cuota': _('Registrar pago de cuota'), 'mora': _('Registrar pago de mora'),
            'cascada': _('Registrar pago de varias cuotas')}[tipo],
            'ayuda': '%s · %s%s' % (account.partner_id.display_name, account.reference_no,
                                    ' · %s' % rec.name if tipo != 'cascada' else ''),
            'secciones': [{'titulo': 'Datos del pago', 'campos': [c for c in base if c]}] + sections,
            'valores': values, 'lateral': False, 'pago_resumen': summary, 'pago_ayuda': help_text}

    @api.model
    def guardar(self, clave, vehicle_id, valores, res_id=False, params=None):
        if clave != 'pago':
            return super().guardar(clave, vehicle_id, valores, res_id=res_id, params=params)
        params, values = params or {}, valores or {}
        tipo, rec, account, W = self._pago_target(vehicle_id, params)
        # Serializa los cobros de la cuenta y vuelve a leer el saldo antes de aplicar dinero.
        self.env.cr.execute('SELECT id FROM adt_comercial_cuentas WHERE id = %s FOR UPDATE', [account.id])
        self.env['adt.comercial.cuotas'].invalidate_cache()
        self.env['account.payment'].invalidate_cache()
        fecha = values.get('payment_date')
        if not fecha:
            raise ValidationError(_('Indica la fecha del pago.'))
        fecha = fields.Date.to_date(fecha)
        summary = self._pago_calculo(tipo, rec, account, W, fecha)
        operation_field = 'numero_operacion' if tipo == 'cascada' else ('mora_operacion' if tipo == 'mora' else 'communication')
        operation = str(values.get(operation_field) or '').strip()
        if not operation:
            raise ValidationError(_('Indica el número de operación.'))
        if self.env['account.payment'].search_count(['|', ('ref', '=', operation), ('mora_operacion', '=', operation)]):
            raise ValidationError(_('Ya existe un pago con ese número de operación.'))
        vals = {'payment_date': fecha, operation_field: operation}
        if tipo == 'cascada':
            full = bool(values.get('cancelar_todo'))
            amount = summary['total'] if full else float(values.get('monto') or 0)
            vals.update({'cuenta_id': account.id, 'cancelar_todo': full, 'monto': amount})
            limit = summary['total']
        else:
            journal = self.env['account.journal'].search([
                ('id', '=', int(values.get('journal_id') or 0)), ('company_id', '=', account.company_id.id),
                ('type', 'in', ['bank', 'cash'])], limit=1)
            if not journal:
                raise ValidationError(_('Elige un diario de banco o caja de la misma empresa.'))
            amount = float(values.get('amount') or 0)
            vals.update({'cuota_id': rec.id, 'journal_id': journal.id, 'amount': amount})
            limit = summary['capital' if tipo == 'cuota' else 'total']
            if tipo == 'cuota':
                manual = bool(values.get('mora_manual'))
                mora = float(values.get('mora') or 0) if manual else summary['mora_auto']
                if not math.isfinite(mora) or mora < 0:
                    raise ValidationError(_('La mora no puede ser negativa.'))
                state = values.get('mora_state', 'pending')
                if state not in ('pending', 'paid'):
                    raise ValidationError(_('Selecciona un estado válido para la mora.'))
                vals.update({'company_id': account.company_id.id, 'payment_type': 'inbound',
                             'mora_manual': manual, 'mora': mora, 'mora_state': state})
        if not math.isfinite(amount) or amount <= 0 or account.currency_id.compare_amounts(amount, limit) > 0:
            raise ValidationError(_('El importe debe ser mayor que cero y no superar el saldo pendiente.'))
        with self.env.cr.savepoint():
            wizard = W.create(vals)
            result = getattr(wizard, WIZARDS[tipo][1])()
        message = result.get('params', {}).get('message') if isinstance(result, dict) else False
        return {'id': wizard.id, 'mensaje': message or _('Pago registrado correctamente.')}
