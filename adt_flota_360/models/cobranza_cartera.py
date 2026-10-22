# -*- coding: utf-8 -*-
"""Carteras de cobranza: objetivos fijos y pagos contabilizados."""
import json
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from odoo.osv import expression


class Cartera(models.Model):
    _name = 'adt.flota360.cartera'
    _description = 'Cartera de cobranza Flota 360'
    _order = 'id desc'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    fecha_limite = fields.Date(required=True)
    criterio = fields.Text(readonly=True)
    linea_ids = fields.One2many('adt.flota360.cartera.linea', 'cartera_id')

    @api.model
    def _manager(self):
        return self.env.user.has_group('adt_comercial.group_access_adt_comercial_gerencia')

    @api.model
    def _domain(self, domain):
        if isinstance(domain, str):
            domain = json.loads(domain)
        if not isinstance(domain, list):
            raise ValidationError(_('El filtro de cuentas no es válido.'))
        return expression.AND([domain, [('company_id', 'in', self.env.companies.ids),
                                         ('state', '=', 'en_curso')]])

    @api.model
    def _disponibles(self, domain, vencidas):
        if not self._manager():
            raise AccessError(_('Solo gerencia puede asignar carteras.'))
        domain = expression.AND([self._domain(domain or []), [('company_id', '=', self.env.company.id)]])
        accounts = self.env['adt.comercial.cuentas'].search(domain, order='id desc')
        occupied = self.env['adt.flota360.cartera.linea'].search([
            ('cuenta_id', 'in', accounts.ids), ('cerrada', '=', False)]).mapped('cuenta_id')
        accounts -= occupied
        quota_domain = [('cuenta_id', 'in', accounts.ids), ('state', '!=', 'anulada'), ('saldo', '>', 0)]
        if vencidas:
            quota_domain.append(('fecha_cronograma', '<=', fields.Date.context_today(self)))
        quotas = self.env['adt.comercial.cuotas'].search(quota_domain)
        totals = {}
        for q in quotas:
            totals[q.cuenta_id.id] = totals.get(q.cuenta_id.id, 0) + max(0, q.saldo)
        return accounts.filtered(lambda a: a.id in totals), totals

    @api.model
    def candidatos(self, domain=None, query='', offset=0, vencidas=True):
        domain = domain or []
        if query:
            domain = expression.AND([domain, ['|', '|', ('reference_no', 'ilike', query),
                      ('partner_id.name', 'ilike', query), ('partner_document', 'ilike', query)]])
        accounts, totals = self._disponibles(domain, vencidas)
        offset = max(0, int(offset))
        return {'total': len(accounts), 'rows': [
            {'id': a.id, 'name': a.reference_no, 'cliente': a.partner_id.display_name,
             'placa': a.moto_placa or '', 'moneda': a.currency_id.name, 'objetivo': totals[a.id]}
            for a in accounts[offset:offset + 50]]}

    @api.model
    def revisar_asignacion(self, domain=None, account_ids=None, vencidas=True):
        accounts, totals = self._disponibles(domain, vencidas)
        if account_ids is not None:
            accounts = accounts.filtered(lambda a: a.id in account_ids)
            if set(accounts.ids) != set(account_ids):
                raise ValidationError(_('Una cuenta seleccionada ya no está disponible. Vuelve a elegir los clientes.'))
        if not accounts:
            raise ValidationError(_('Selecciona al menos una cuenta con deuda disponible para asignar.'))
        if len(accounts) > 2000:
            raise ValidationError(_('Reduce la selección a un máximo de 2.000 cuentas.'))
        amounts = {}
        for account in accounts:
            currency = account.currency_id.name
            amounts[currency] = amounts.get(currency, 0) + totals[account.id]
        return {'account_ids': accounts.ids, 'cuentas': len(accounts),
                'clientes': len(accounts.mapped('partner_id')), 'importes': amounts}

    @api.model
    def asignar(self, name, user_id, fecha_limite, domain=None, account_ids=None, vencidas=True):
        if not self._manager():
            raise AccessError(_('Solo gerencia puede asignar carteras.'))
        if not (name or '').strip() or not fecha_limite or fields.Date.to_date(fecha_limite) < fields.Date.context_today(self):
            raise ValidationError(_('Indica un nombre y una fecha límite desde hoy.'))
        user = self.env['res.users'].search([('id', '=', int(user_id)), ('share', '=', False),
                                            ('company_ids', 'in', self.env.company.id)], limit=1)
        if not user or not (user.has_group('fleet.fleet_group_user') or user.has_group('adt_flota_360.group_cobrador')):
            raise ValidationError(_('Selecciona un usuario interno con perfil de cobrador o acceso a Flota de la empresa actual.'))
        domain = self._domain(domain or [])
        domain = expression.AND([domain, [('company_id', '=', self.env.company.id)]])
        if account_ids is not None:
            domain = expression.AND([domain, [('id', 'in', account_ids)]])
        accounts = self.env['adt.comercial.cuentas'].search(domain, limit=2001)
        if len(accounts) > 2000:
            raise ValidationError(_('Reduce el filtro a un máximo de 2.000 cuentas por cartera.'))
        # Bloquea las cuentas para evitar asignaciones activas simultáneas.
        if accounts:
            self.env.cr.execute('SELECT id FROM adt_comercial_cuentas WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(accounts.ids)])
        today = fields.Date.context_today(self)
        quota_domain = [('cuenta_id', 'in', accounts.ids), ('state', '!=', 'anulada'), ('saldo', '>', 0)]
        if vencidas:
            quota_domain.append(('fecha_cronograma', '<=', today))
        quotas = self.env['adt.comercial.cuotas'].search(quota_domain)
        occupied = self.env['adt.flota360.cartera.linea'].search([
            ('cuenta_id', 'in', accounts.ids), ('cerrada', '=', False)])
        if occupied:
            raise ValidationError(_('Hay cuentas con una asignación activa. Cierra su gestión antes de reasignarlas.'))
        grouped, families = {}, {}
        for q in quotas:
            root = q.parent_id or q
            item = families.setdefault(root.id, {'root': root, 'objetivo': 0})
            item['objetivo'] += max(0, q.saldo)
        for item in families.values():
            root = item['root']
            grouped.setdefault(root.cuenta_id.id, []).append((0, 0, {
                'cuota_id': root.id, 'objetivo': item['objetivo'],
                'pago_base': sum((root | root.child_ids).sudo().mapped('payment_ids').filtered(
                    lambda p: p.state == 'posted').mapped('amount'))}))
        if not grouped:
            raise ValidationError(_('La selección no tiene cuotas pendientes para el alcance elegido.'))
        portfolio = self.create({'name': name.strip(), 'user_id': user.id, 'fecha_limite': fecha_limite,
            'criterio': json.dumps({'domain': domain, 'vencidas': vencidas}),
            'linea_ids': [(0, 0, {'cuenta_id': aid, 'cuota_ids': values}) for aid, values in grouped.items()]})
        return portfolio.id

    @api.model
    def tablero(self):
        domain = [('company_id', 'in', self.env.companies.ids)]
        if not self._manager():
            domain.append(('user_id', '=', self.env.uid))
        portfolios = self.search(domain)
        rows = []
        for p in portfolios:
            for line in p.linea_ids:
                target = sum(line.cuota_ids.mapped('objetivo'))
                paid = line.cobrado_cierre if line.cerrada else line._cobrado()
                resolved = p.company_id.currency_id.is_zero(target - paid)
                rows.append({'id': line.id, 'cartera': p.name, 'user_id': p.user_id.id,
                    'responsable': p.user_id.name, 'cliente': line.cuenta_id.partner_id.display_name,
                    'cuenta': line.cuenta_id.reference_no, 'cuenta_id': line.cuenta_id.id,
                    'telefono': line.cuenta_id.partner_id.mobile or line.cuenta_id.partner_id.phone or '',
                    'moneda': line.cuenta_id.currency_id.name, 'objetivo': target, 'cobrado': paid,
                    'limite': str(p.fecha_limite), 'gestion': line.gestion,
                    'promesa': str(line.promesa) if line.promesa else '', 'nota': line.nota or '',
                    'cerrada': line.cerrada, 'resuelto': resolved,
                    'estado': 'Resuelto' if resolved else ('Cerrado sin resolver' if line.cerrada else (
                        'Vencido' if p.fecha_limite < fields.Date.context_today(self) else 'En gestión'))})
        users = self.env['res.users'].search([('share', '=', False), ('company_ids', 'in', self.env.company.id)]) if self._manager() else self.env.user
        return {'manager': self._manager(), 'rows': rows, 'users': [
            {'id': u.id, 'name': u.name} for u in users if u.has_group('fleet.fleet_group_user') or u.has_group('adt_flota_360.group_cobrador')]}


class CarteraLinea(models.Model):
    _name = 'adt.flota360.cartera.linea'
    _description = 'Seguimiento de cuenta asignada'

    cartera_id = fields.Many2one('adt.flota360.cartera', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='cartera_id.company_id', store=True)
    cuenta_id = fields.Many2one('adt.comercial.cuentas', required=True, ondelete='restrict')
    cuota_ids = fields.One2many('adt.flota360.cartera.cuota', 'linea_id')
    gestion = fields.Selection([('pendiente', 'Sin contactar'), ('contactado', 'Contactado'),
        ('promesa', 'Promesa de pago'), ('sin_respuesta', 'Sin respuesta')], default='pendiente', required=True)
    promesa = fields.Date()
    nota = fields.Text()
    cerrada = fields.Boolean(default=False)
    cobrado_cierre = fields.Float(readonly=True)

    def _cobrado(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        # El trabajador recibe solo el agregado de pagos de sus cuotas autorizadas.
        # No necesita acceso general a los asientos ni a los pagos contables.
        return sum(min(s.objetivo, max(0, sum((s.cuota_id | s.cuota_id.child_ids).sudo().mapped(
            'payment_ids').filtered(lambda p: p.state == 'posted').mapped('amount')) - s.pago_base))
            for s in self.cuota_ids)


    def registrar_gestion(self, gestion, promesa=False, nota=''):
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')
        if self.cerrada:
            raise ValidationError(_('La gestión está cerrada.'))
        if gestion not in dict(self._fields['gestion'].selection):
            raise ValidationError(_('Selecciona un resultado válido.'))
        if gestion == 'promesa' and not promesa:
            raise ValidationError(_('Indica la fecha de la promesa.'))
        self.write({'gestion': gestion, 'promesa': promesa if gestion == 'promesa' else False, 'nota': nota})
        return True

    def cerrar(self):
        if not self.env['adt.flota360.cartera']._manager():
            raise AccessError(_('Solo gerencia puede cerrar una asignación.'))
        for line in self:
            if not line.cerrada:
                line.write({'cerrada': True, 'cobrado_cierre': line._cobrado()})
        return True

    def write(self, vals):
        if not self.env['adt.flota360.cartera']._manager() and set(vals) - {'gestion', 'promesa', 'nota'}:
            raise AccessError(_('Solo gerencia puede cambiar la asignación.'))
        if not self.env['adt.flota360.cartera']._manager() and any(self.mapped('cerrada')):
            raise ValidationError(_('La gestión está cerrada.'))
        return super().write(vals)


class CarteraCuota(models.Model):
    _name = 'adt.flota360.cartera.cuota'
    _description = 'Objetivo de cuota al asignar la cartera'

    linea_id = fields.Many2one('adt.flota360.cartera.linea', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='linea_id.company_id', store=True)
    cuota_id = fields.Many2one('adt.comercial.cuotas', required=True, ondelete='restrict')
    objetivo = fields.Float(required=True)
    pago_base = fields.Float(required=True)


class CuentasCartera(models.Model):
    _inherit = 'adt.comercial.cuentas'

    cartera_gestion_ids = fields.One2many('adt.flota360.cartera.linea', 'cuenta_id', string='Asignaciones de cobranza')
