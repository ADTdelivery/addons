# -*- coding: utf-8 -*-
"""Adaptador de los asistentes comerciales para el popup nativo de Flota 360."""
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


WIZARDS = {
    'cuota': ('adt.register.payment', 'action_create_payments'),
    'mora': ('adt.pagar.mora.wizard', 'action_confirm_pagar_mora'),
    'cascada': ('adt.cancelar.credito.wizard', 'action_pagar'),
    # Todas las moras registradas pendientes de la cuenta, con un solo N° de operación.
    'moras': ('adt.pagar.mora.wizard', None),
}
POR_CUENTA = ('cascada', 'moras')


class Flota360Pagos(models.AbstractModel):
    _inherit = 'adt.flota360'

    def _pago_target(self, vehicle_id, params):
        tipo = params.get('tipo')
        if tipo not in WIZARDS:
            raise ValidationError(_('Tipo de pago no válido.'))
        vehicle = self._vehiculo(vehicle_id)
        vehicle.check_access_rights('read')
        model = 'adt.comercial.cuentas' if tipo in POR_CUENTA else 'adt.comercial.cuotas'
        rec = self.env[model].browse(int(params.get('id') or 0)).exists()
        if not rec:
            raise ValidationError(_('La cuenta o cuota ya no existe.'))
        rec.check_access_rights('read')
        rec.check_access_rule('read')
        rec.check_access_rights('write')
        rec.check_access_rule('write')
        account = rec if tipo in POR_CUENTA else rec.cuenta_id
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
                    'cuotas': cantidad, 'mora_dias': 0, 'moneda': account.currency_id.name,
                    'detalle': self._cuotas_elegibles(account, fecha)}
        if tipo == 'moras':
            detalle = self._moras_pendientes(account)
            total = round(sum(d['mora'] for d in detalle), 2)
            return {'capital': 0, 'mora_auto': total, 'total': total, 'mora_dias': 0, 'cuotas': len(detalle),
                    'moneda': account.currency_id.name, 'detalle': detalle}
        if tipo == 'mora':
            wizard = wizard_model.new({'cuota_id': rec.id})
            mora = wizard.mora_pendiente_real
            return {'capital': 0, 'mora_auto': mora, 'total': mora, 'mora_dias': 0,
                    'moneda': account.currency_id.name}
        wizard = wizard_model.new({'cuota_id': rec.id, 'company_id': account.company_id.id, 'payment_date': fecha})
        return {'capital': max(rec.saldo, 0), 'mora_auto': wizard.mora_auto,
                'total': round(max(rec.saldo, 0) + wizard.mora_auto, 2),
                'mora_dias': wizard.mora_dias, 'moneda': account.currency_id.name}

    def _mora_cuota_pago(self, cuota, fecha):
        """Mora que se cobraría con la cuota al `fecha` (la registrada pendiente o la que se registrará)."""
        M = self.env['adt.comercial.cuotas.masivas.wizard']
        registrada = M._get_mora_pendiente_amount(cuota)
        if registrada > 0:
            return registrada
        return M._get_mora_para_nuevo_pago(cuota, fecha, cuota.company_id.id)[0]

    def _cuotas_elegibles(self, account, fecha):
        """Cuotas con saldo que se pueden elegir en «Pagar varias cuotas», en orden de vencimiento."""
        cuotas = account.cuota_ids.filtered(lambda q: q.state not in ('pagado', 'anulada') and q.saldo > 0).sorted(
            lambda q: (q.fecha_cronograma or fecha, q.id))
        return [{'id': q.id, 'nombre': q.name or '', 'fecha': fields.Date.to_string(q.fecha_cronograma) if q.fecha_cronograma else '',
                 'saldo': round(q.saldo, 2), 'mora': round(self._mora_cuota_pago(q, fecha), 2),
                 'vencida': bool(q.fecha_cronograma and q.fecha_cronograma < fecha), 'tipo': 'Cargo' if q.type == 'mora' else ''}
                for q in cuotas]

    def _moras_pendientes(self, account):
        """Cuotas de la cuenta con mora registrada pendiente (en los pagos), en orden de vencimiento."""
        M = self.env['adt.comercial.cuotas.masivas.wizard']
        cuotas = account.cuota_ids.filtered(lambda q: q.state != 'anulada').sorted(
            lambda q: (q.fecha_cronograma or fields.Date.today(), q.id))
        filas = [(q, M._get_mora_pendiente_amount(q)) for q in cuotas]
        return [{'id': q.id, 'nombre': q.name or '', 'mora': mora,
                 'fecha': fields.Date.to_string(q.fecha_cronograma) if q.fecha_cronograma else ''}
                for q, mora in filas if mora > 0]

    def _pagar_elegidas(self, account, cuotas, fecha, operacion, cobrar_mora):
        """Paga el saldo completo de cada cuota elegida con un mismo N° de operación (como la cascada)
        y, si se pide, también su mora. Devuelve (capital, mora cobrada)."""
        M = self.env['adt.comercial.cuotas.masivas.wizard']
        journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', account.company_id.id)], limit=1)
        if not journal:
            raise ValidationError(_('Configura un diario de banco o caja para esta empresa antes de cobrar.'))
        capital = mora_cobrada = 0.0
        for cuota in cuotas:
            mora, dias = M._get_mora_para_nuevo_pago(cuota, fecha, account.company_id.id)
            saldo = round(cuota.saldo, 2)
            pago = self.env['account.payment'].create({
                'payment_type': 'inbound', 'journal_id': journal.id, 'cuota_id': cuota.id, 'ref': operacion,
                'amount': saldo, 'date': fecha, 'partner_id': account.partner_id.id,
                'mora': mora, 'mora_dias': dias, 'mora_state': 'pending'})
            pago.action_post()
            capital += saldo
            if cobrar_mora:
                pendiente = M._get_mora_pendiente_amount(cuota)
                if pendiente > 0:
                    mora_cobrada += M._pagar_mora_pendiente(cuota, pendiente, fecha, operacion)[0]
        return round(capital, 2), round(mora_cobrada, 2)

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
                        required=True, options=[[j.id, j.display_name] for j in journals]) if tipo not in POR_CUENTA else None
        operation = 'numero_operacion' if tipo == 'cascada' else ('mora_operacion' if tipo in ('mora', 'moras') else 'communication')
        base = [date, campo(operation, label='N° de operación', required=True, placeholder='Número del depósito o transferencia')]
        if journal:
            base.append(journal)
        values = {'payment_date': str(today), operation: params.get('operacion') or ''}
        sections = []
        if tipo == 'cascada':
            base += [{'name': 'modo', 'label': '¿Qué vas a pagar?', 'type': 'selection', 'segmentado': True, 'required': True,
                      'col': 2, 'help': '', 'options': [['todo', 'Toda la deuda'], ['elegir', 'Elegir cuotas'], ['monto', 'Un monto en cascada']]},
                     campo('monto', label='Importe a aplicar', visible=['modo', 'monto'], required=False,
                           help='Se aplica desde la cuota más antigua: primero capital y luego mora.'),
                     {'name': 'cobrar_mora', 'label': 'Cobrar también la mora de las cuotas elegidas', 'type': 'boolean',
                      'required': False, 'help': '', 'col': 2, 'visible': ['modo', 'elegir']}]
            values.update({'modo': 'todo', 'cancelar_todo': True, 'monto': summary['total'], 'cobrar_mora': True, 'cuota_ids': []})
            help_text = _('Paga toda la deuda, elige qué cuotas pagar o abona un monto que se aplica desde la cuota más antigua.')
        elif tipo == 'moras':
            help_text = _('Cancela la mora registrada pendiente de todas las cuotas con un solo número de operación. '
                          'El capital de las cuotas no se toca.')
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
            'cascada': _('Registrar pago de varias cuotas'), 'moras': _('Pagar todas las moras')}[tipo],
            'ayuda': '%s · %s%s' % (account.partner_id.display_name, account.reference_no,
                                    ' · %s' % rec.name if tipo not in POR_CUENTA else ''),
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
        operation_field = 'numero_operacion' if tipo == 'cascada' else ('mora_operacion' if tipo in ('mora', 'moras') else 'communication')
        operation = str(values.get(operation_field) or '').strip()
        if not operation:
            raise ValidationError(_('Indica el número de operación.'))
        if self.env['account.payment'].search_count(['|', ('ref', '=', operation), ('mora_operacion', '=', operation)]):
            raise ValidationError(_('Ya existe un pago con ese número de operación.'))
        vals = {'payment_date': fecha, operation_field: operation}
        if tipo == 'moras':
            return self._pagar_todas_moras(account, summary, fecha, operation)
        if tipo == 'cascada' and values.get('modo') == 'elegir':
            ids = [int(i) for i in (values.get('cuota_ids') or [])]
            cuotas = account.cuota_ids.filtered(lambda q: q.id in ids and q.state not in ('pagado', 'anulada') and q.saldo > 0)
            if not ids or len(cuotas) != len(set(ids)):
                raise ValidationError(_('Elige al menos una cuota con saldo pendiente.'))
            cuotas = cuotas.sorted(lambda q: (q.fecha_cronograma or fecha, q.id))
            with self.env.cr.savepoint():
                capital, mora_cobrada = self._pagar_elegidas(account, cuotas, fecha, operation, bool(values.get('cobrar_mora')))
            account.message_post(body=_('Pago de %s cuota(s) elegidas por %s (operación %s): %s.') % (
                len(cuotas), account.currency_id.round(capital + mora_cobrada), operation, ', '.join(cuotas.mapped('name'))))
            return {'id': False, 'mensaje': _('Se pagaron %s cuota(s).') % len(cuotas),
                    'total': round(capital + mora_cobrada, 2), 'moneda': account.currency_id.name,
                    'concepto': ', '.join(cuotas.mapped('name')), 'operacion': operation,
                    'restante': 0.0, 'siguiente': False, 'mora_pendiente': 0.0}
        if tipo == 'cascada':
            modo = values.get('modo')
            full = modo == 'todo' if modo else bool(values.get('cancelar_todo'))
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
        # Datos para la confirmación del popup: cuánto se cobró y qué queda por pagar.
        cobrado_mora = vals.get('mora', 0.0) if vals.get('mora_state') == 'paid' else 0.0
        restante = max(round(limit - amount, 2), 0.0)
        siguiente = False
        if restante > 0:
            if tipo == 'cuota':
                # El asistente deja el saldo en una subcuota nueva colgada de la cuota raíz.
                raiz = rec.parent_id or rec
                sub = self.env['adt.comercial.cuotas'].search([
                    ('parent_id', '=', raiz.id), ('saldo', '>', 0), ('state', 'not in', ('pagado', 'anulada'))],
                    order='id desc', limit=1)
                if sub:
                    siguiente = {'tipo': 'cuota', 'id': sub.id, 'nombre': sub.name}
            elif tipo == 'mora':
                siguiente = {'tipo': 'mora', 'id': rec.id, 'nombre': rec.name}
            else:
                siguiente = {'tipo': 'cascada', 'id': account.id, 'nombre': account.reference_no}
        return {'id': wizard.id, 'mensaje': message or _('Pago registrado correctamente.'),
                'total': round(amount + cobrado_mora, 2), 'moneda': account.currency_id.name,
                'concepto': account.reference_no if tipo == 'cascada' else rec.name, 'operacion': operation,
                'restante': restante, 'siguiente': siguiente,
                'mora_pendiente': vals.get('mora', 0.0) if vals.get('mora_state') == 'pending' else 0.0}

    def _pagar_todas_moras(self, account, summary, fecha, operacion):
        """Paga completa la mora registrada pendiente de cada cuota (misma regla que la cascada)."""
        if summary['total'] <= 0:
            raise ValidationError(_('La cuenta no tiene mora pendiente.'))
        M = self.env['adt.comercial.cuotas.masivas.wizard']
        cuotas = self.env['adt.comercial.cuotas'].browse([d['id'] for d in summary['detalle']])
        total = 0.0
        with self.env.cr.savepoint():
            for cuota in cuotas:
                pendiente = M._get_mora_pendiente_amount(cuota)
                if pendiente > 0:
                    total += M._pagar_mora_pendiente(cuota, pendiente, fecha, operacion)[0]
        total = round(total, 2)
        nombres = ', '.join(cuotas.mapped('name'))
        account.message_post(body=_('Pago de todas las moras por %s (operación %s): %s.') % (
            account.currency_id.round(total), operacion, nombres))
        return {'id': False, 'mensaje': _('Se pagó la mora de %s cuota(s).') % len(cuotas),
                'total': total, 'moneda': account.currency_id.name, 'concepto': _('Moras: %s') % nombres,
                'operacion': operacion, 'restante': 0.0, 'siguiente': False, 'mora_pendiente': 0.0}
