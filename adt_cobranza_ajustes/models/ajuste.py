# -*- coding: utf-8 -*-
"""Ajustes de cronograma: los acuerdos de cobranza (diferir, trasladar saldo, mora negociada,
cuotas nuevas, refinanciamiento con montos libres) como operaciones registradas y reversibles.

Cada ajuste guarda una foto de las cuotas antes de tocarlas; deshacer el último ajuste de una
cuenta las devuelve a ese estado. El dinero recibido (account.payment) no se modifica, salvo la
mora pendiente registrada en los pagos cuando se perdona o se cambia por un monto acordado."""
import json
from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, format_date

DIAS_PERIODO = {'semanal': 7, 'quincena': 15, 'mensual': 30}
CAMPOS_FOTO = ('name', 'monto', 'fecha_cronograma', 'type', 'periodicidad', 'parent_id', 'cuenta_id', 'company_id',
               'mora_manual', 'mora_manual_monto', 'ajuste_estado', 'ajuste_nota', 'monto_pactado')
TIPOS = [
    ('reprogramar', 'Reprogramar cuota'),
    ('trasladar', 'Trasladar saldo'),
    ('mora', 'Acordar mora'),
    ('insertar', 'Agregar cuota'),
    ('editar', 'Refinanciamiento'),
    ('eliminar', 'Eliminar cuota'),
]
MORA_ACCIONES = [
    ('perdonar', 'Perdonar'),
    ('cuota', 'Dejar en la cuota'),
    ('cargo', 'Cobrar como cargo aparte'),
    ('incluir', 'Repartir en el cronograma'),
    ('mantener', 'Sin cambios'),
]


def _abierta(q):
    return q.state not in ('pagado', 'anulada')


def _pagado(q):
    return sum(q.payment_ids.mapped('amount'))


class AdtComercialCuotas(models.Model):
    _inherit = 'adt.comercial.cuotas'

    monto_pactado = fields.Monetary('Monto pactado', copy=False,
                                    help='Monto original de la cuota, antes de cualquier ajuste del cronograma.')
    ajuste_estado = fields.Selection([
        ('cerrada', 'Cerrada por ajuste'),
        ('trasladada', 'Saldo trasladado'),
        ('reprogramada', 'Reprogramada'),
        ('eliminada', 'Eliminada'),
    ], string='Ajuste', copy=False)
    ajuste_nota = fields.Char('Nota del ajuste', copy=False)

    # El saldo y el estado se recalculan también al cambiar el monto (antes solo con los pagos:
    # editar el monto dejaba el saldo desfasado).
    @api.depends('payment_ids', 'payment_ids.amount', 'monto')
    def _compute_saldo(self):
        for record in self:
            record.saldo = record.monto - _pagado(record)

    @api.depends('payment_ids', 'payment_ids.amount', 'monto', 'cuenta_id.state', 'ajuste_estado')
    def _compute_state(self):
        super()._compute_state()
        for record in self:
            if record.ajuste_estado in ('cerrada', 'trasladada', 'eliminada'):
                record.state = 'pagado' if record.payment_ids else 'anulada'
            # Comparación con redondeo: con igualdad exacta una diferencia de centavos dejaba la cuota «a cuenta».
            elif record.payment_ids and float_compare(_pagado(record), record.monto,
                                                      precision_rounding=record.currency_id.rounding or 0.01) >= 0:
                record.state = 'pagado'


class AdtCobranzaAjuste(models.Model):
    _name = 'adt.cobranza.ajuste'
    _description = 'Ajuste de cronograma'
    _order = 'id desc'

    name = fields.Char('Ajuste', compute='_compute_name')
    cuenta_id = fields.Many2one('adt.comercial.cuentas', 'Cuenta', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='cuenta_id.company_id', store=True)
    currency_id = fields.Many2one(related='cuenta_id.company_id.currency_id')
    partner_id = fields.Many2one(related='cuenta_id.partner_id', string='Cliente')
    tipo = fields.Selection(TIPOS, 'Tipo', required=True)
    estado = fields.Selection([('aplicado', 'Aplicado'), ('revertido', 'Deshecho')], default='aplicado', required=True)
    user_id = fields.Many2one('res.users', 'Registrado por', default=lambda self: self.env.user, readonly=True)
    motivo = fields.Text('Motivo / acuerdo con el cliente')

    cuota_id = fields.Many2one('adt.comercial.cuotas', 'Cuota', ondelete='set null')
    cuota_ref_id = fields.Many2one('adt.comercial.cuotas', 'Cuota de referencia', ondelete='set null')
    destino = fields.Selection([
        ('final', 'Al final'),
        ('despues', 'Después de una cuota'),
        ('fecha', 'En una fecha'),
    ], 'Ubicación')
    fecha = fields.Date('Fecha')
    correr_fechas = fields.Boolean('Correr un periodo las cuotas siguientes')
    nombre = fields.Char('Nombre')
    cuota_tipo = fields.Selection([('cuota', 'Cuota'), ('mora', 'Cargo')], 'Tipo de cuota', default='cuota')
    monto = fields.Monetary('Monto')
    origen = fields.Selection([
        ('adicional', 'Aumenta la deuda'),
        ('redistribuir', 'Sale de las últimas cuotas'),
    ], 'De dónde sale el monto', default='adicional')
    adicional = fields.Monetary('Monto adicional')
    # Refinanciamiento cuyo cronograma suma más o menos que lo refinanciado: la diferencia y por qué.
    diferencia = fields.Monetary('Diferencia con lo refinanciado', readonly=True)
    diferencia_motivo = fields.Text('Motivo de la diferencia')

    mora_accion = fields.Selection(MORA_ACCIONES, 'Qué hacer con la mora')
    mora_calculada = fields.Monetary('Mora calculada', readonly=True)
    mora_acordada = fields.Monetary('Mora acordada')
    mora_perdonada = fields.Monetary('Mora perdonada', readonly=True)
    mora_fecha = fields.Date('Vence el cargo de mora')

    deuda_antes = fields.Monetary('Deuda antes', readonly=True)
    deuda_despues = fields.Monetary('Deuda después', readonly=True)
    resumen = fields.Text('Cambios', readonly=True)
    linea_ids = fields.One2many('adt.cobranza.ajuste.linea', 'ajuste_id', 'Cuotas afectadas', readonly=True)
    revertido_por = fields.Many2one('res.users', 'Deshecho por', readonly=True)
    revertido_fecha = fields.Datetime('Deshecho el', readonly=True)
    # Refinanciamientos: el cronograma pendiente completo antes y después (JSON), para el historial.
    cronograma_antes = fields.Text(readonly=True)
    cronograma_despues = fields.Text(readonly=True)

    def _compute_name(self):
        for a in self:
            a.name = _('Ajuste N° %05d') % a.id if a.id else _('Nuevo ajuste')

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _redondeo(self):
        return self.currency_id.rounding or 0.01

    def _es_cero(self, monto):
        return float_is_zero(monto, precision_rounding=self._redondeo())

    def _soles(self, monto):
        return '%s %s' % (self.currency_id.symbol or 'S/', '{:,.2f}'.format(monto or 0.0))

    def _f(self, valor):
        return format_date(self.env, valor, date_format='dd/MM/yyyy') if valor else '—'

    def _periodo(self):
        return timedelta(days=DIAS_PERIODO.get(self.cuenta_id.periodicidad, 15))

    def _abiertas(self, excluir=None):
        return self.cuenta_id.cuota_ids.filtered(lambda q: _abierta(q) and q != excluir).sorted(
            lambda q: (q.fecha_cronograma or date.max, q.id))

    def _deuda(self):
        return round(sum(max(q.saldo, 0.0) for q in self.cuenta_id.cuota_ids if _abierta(q)), 2)

    def _foto(self, q):
        foto = {}
        for campo in CAMPOS_FOTO:
            valor = q[campo]
            if isinstance(valor, models.BaseModel):
                valor = valor.id or False
            elif isinstance(valor, date):
                valor = fields.Date.to_string(valor)
            foto[campo] = valor
        # Mora pendiente registrada en los pagos (se reduce al perdonar).
        foto['_pagos_mora'] = {str(p.id): p.mora for p in q.payment_ids}
        return foto

    def _linea(self, q):
        return self.linea_ids.filtered(lambda l: l.cuota_id == q)[:1]

    def _tocar(self, q, vals, accion='modificada'):
        """Modifica una cuota guardando antes su foto (una vez por ajuste)."""
        linea = self._linea(q)
        if not linea:
            self.env['adt.cobranza.ajuste.linea'].create({
                'ajuste_id': self.id, 'cuota_id': q.id, 'cuota_nombre': q.name, 'accion': accion,
                'antes': json.dumps(self._foto(q)), 'pagos_antes': len(q.payment_ids)})
        elif accion == 'eliminada':
            linea.accion = accion
        if 'monto' in vals and not q.monto_pactado:
            vals = dict(vals, monto_pactado=q.monto)
        q.write(vals)

    def _crear(self, vals):
        vals = dict({'cuenta_id': self.cuenta_id.id, 'company_id': self.cuenta_id.company_id.id,
                     'periodicidad': self.cuenta_id.periodicidad, 'type': 'cuota'}, **vals)
        vals.setdefault('monto_pactado', vals.get('monto'))
        q = self.env['adt.comercial.cuotas'].create(vals)
        self.env['adt.cobranza.ajuste.linea'].create({
            'ajuste_id': self.id, 'cuota_id': q.id, 'cuota_nombre': q.name, 'accion': 'creada', 'pagos_antes': 0})
        return q

    def _cronograma(self):
        """Cuotas pendientes de la cuenta, en orden de vencimiento."""
        return [{'nombre': q.name or '', 'fecha': fields.Date.to_string(q.fecha_cronograma) if q.fecha_cronograma else '',
                 'monto': round(q.monto, 2), 'pagado': round(_pagado(q), 2), 'saldo': round(max(q.saldo, 0.0), 2),
                 'tipo': 'Cargo' if q.type == 'mora' else ''}
                for q in self._abiertas()]

    def _nota(self, titulo, deshecho=False):
        """Deja el ajuste en el historial (chatter) de la cuenta."""
        if self.env.context.get('ajuste_simulacion') or not hasattr(self.cuenta_id, 'message_post'):
            return
        esc = lambda t: (t or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        cuerpo = '<b>%s</b> · %s<br/><b>Motivo:</b> %s<br/>%s<b>Deuda pendiente:</b> %s → %s' % (
            esc(titulo), esc(self.name), esc(self.motivo),
            ''.join('%s<br/>' % esc(linea) for linea in (self.resumen or '').split('\n') if linea),
            *((self._soles(self.deuda_despues), self._soles(self.deuda_antes)) if deshecho
              else (self._soles(self.deuda_antes), self._soles(self.deuda_despues))))
        self.cuenta_id.message_post(body=cuerpo, message_type='comment', subtype_xmlid='mail.mt_note')

    def _quitar(self, q):
        """Quita una cuota sin pagos. No se borra: queda «Eliminada» (monto 0, fuera de los cálculos) para el
        historial y porque otras tablas la referencian (carteras de cobranza, reportes de la app)."""
        if q.payment_ids:
            raise ValidationError(_('La %s tiene pagos; no se puede quitar.') % q.name)
        linea = self._linea(q)
        if linea and linea.accion == 'creada':
            linea.unlink()
            q.unlink()
            return
        self._tocar(q, {'monto': 0.0, 'ajuste_estado': 'eliminada',
                        'ajuste_nota': _('Eliminada por %s (antes %s).') % (self.name, self._soles(q.monto))}, accion='eliminada')

    def _correr(self, desde, excluir, inclusive=False):
        """Corre un periodo las cuotas abiertas que vencen después de `desde`."""
        paso = self._periodo()
        for q in self._abiertas(excluir).sorted(lambda q: q.fecha_cronograma or date.max, reverse=True):
            if q.fecha_cronograma and (q.fecha_cronograma > desde or (inclusive and q.fecha_cronograma == desde)):
                self._tocar(q, {'fecha_cronograma': q.fecha_cronograma + paso})

    def _ubicar(self, excluir=None):
        """Fecha para una cuota según `destino`; corre las siguientes si corresponde."""
        if self.destino == 'final':
            fechas = self.cuenta_id.cuota_ids.filtered(
                lambda q: q.type == 'cuota' and q != excluir and q.fecha_cronograma).mapped('fecha_cronograma')
            return (max(fechas) if fechas else fields.Date.context_today(self)) + self._periodo()
        if self.destino == 'despues':
            ref = self.cuota_ref_id
            if not ref or ref == excluir or ref.cuenta_id != self.cuenta_id or not ref.fecha_cronograma:
                raise ValidationError(_('Elige la cuota después de la cual va.'))
            self._correr(ref.fecha_cronograma, excluir)
            return ref.fecha_cronograma + self._periodo()
        if not self.fecha:
            raise ValidationError(_('Indica la fecha.'))
        if self.correr_fechas:
            self._correr(self.fecha, excluir, inclusive=True)
        return self.fecha

    # ------------------------------------------------------------------
    # Mora
    # ------------------------------------------------------------------

    def _mora_cuotas(self, cuotas):
        """{cuota: (pendiente, ya pagada)} leída antes de cualquier cambio."""
        return {q: (round(q.mora_pendiente or 0.0, 2), round(max((q.mora_total or 0.0) - (q.mora_pendiente or 0.0), 0.0), 2))
                for q in cuotas}

    def _anular_mora(self, q, ya_pagada, queda=0.0):
        """Deja en `queda` la mora pendiente de la cuota: reduce la mora registrada en los pagos
        y fija la mora manual (detiene el cálculo automático)."""
        self._tocar(q, {'mora_manual': True, 'mora_manual_monto': round(ya_pagada + queda, 2)})
        for p in q.payment_ids.filtered(lambda p: p.mora_state == 'pending' and (p.mora or 0.0) > (p.mora_pagado or 0.0)):
            p.mora = p.mora_pagado or 0.0

    def _resolver_mora(self, moras, destino=None):
        """Aplica `mora_accion` a la mora leída en `moras`. `destino`: cuota que conserva la mora (opción «cuota»)."""
        calculada = round(sum(p for p, _y in moras.values()), 2)
        self.mora_calculada = calculada
        accion = self.mora_accion or 'mantener'
        if self._es_cero(calculada) or accion == 'mantener':
            self.mora_perdonada = 0.0
            return 0.0
        acordada = 0.0 if accion == 'perdonar' else round(min(max(self.mora_acordada or 0.0, 0.0), calculada), 2)
        if accion != 'perdonar' and self.mora_acordada and float_compare(self.mora_acordada, calculada,
                                                                         precision_rounding=self._redondeo()) > 0:
            raise ValidationError(_('La mora acordada no puede superar la calculada (%s).') % self._soles(calculada))
        for q, (pendiente, ya) in moras.items():
            if pendiente > 0:
                queda = acordada if accion == 'cuota' and q == destino else 0.0
                self._anular_mora(q, ya, queda)
        if accion == 'cuota' and destino and destino not in moras:
            _p, ya = self._mora_cuotas(destino)[destino]
            self._anular_mora(destino, ya, acordada)
        if accion == 'cargo' and acordada > 0:
            origen = ', '.join(q.name for q, (p, _y) in moras.items() if p > 0)
            self._crear({'name': _('Mora acordada · %s') % origen, 'type': 'mora', 'monto': acordada,
                         'fecha_cronograma': self.mora_fecha or fields.Date.context_today(self),
                         'ajuste_nota': _('Mora acordada en %s.') % self.name})
        self.mora_perdonada = round(calculada - acordada, 2)
        return acordada

    # ------------------------------------------------------------------
    # Operaciones
    # ------------------------------------------------------------------

    def _validar_cuota(self, q):
        if not q or q.cuenta_id != self.cuenta_id:
            raise ValidationError(_('La cuota no pertenece a esta cuenta.'))
        if not _abierta(q) or q.saldo <= 0:
            raise ValidationError(_('La %s no tiene saldo pendiente.') % q.name)

    def _aplicar_reprogramar(self):
        q = self.cuota_id
        self._validar_cuota(q)
        moras = self._mora_cuotas(q)
        saldo, pagado = q.saldo, _pagado(q)
        nueva = self._ubicar(excluir=q)
        if pagado > 0:
            # Lo pagado queda en la cuota; el saldo pasa a una cuota nueva en la fecha elegida.
            self._tocar(q, {'monto': pagado, 'ajuste_estado': 'cerrada',
                            'ajuste_nota': _('Saldo de %s reprogramado al %s.') % (self._soles(saldo), self._f(nueva))})
            destino = self._crear({'name': _('%s (saldo)') % q.name, 'monto': saldo, 'fecha_cronograma': nueva,
                                   'type': q.type, 'ajuste_estado': 'reprogramada',
                                   'ajuste_nota': _('Saldo de %s reprogramado; vencía el %s.') % (q.name, self._f(q.fecha_cronograma))})
        else:
            destino = q
            self._tocar(q, {'fecha_cronograma': nueva, 'ajuste_estado': 'reprogramada',
                            'ajuste_nota': _('Reprogramada; vencía el %s.') % self._f(q.fecha_cronograma)})
        self._resolver_mora(moras, destino)

    def _aplicar_trasladar(self):
        q, dest = self.cuota_id, self.cuota_ref_id
        self._validar_cuota(q)
        if not dest or dest == q or dest.cuenta_id != self.cuenta_id or not _abierta(dest):
            raise ValidationError(_('Elige la cuota que recibe el saldo.'))
        moras = self._mora_cuotas(q)
        self._resolver_mora(moras)
        saldo, pagado = q.saldo, _pagado(q)
        self._tocar(dest, {'monto': dest.monto + saldo,
                           'ajuste_nota': _('Incluye %s trasladados de %s.') % (self._soles(saldo), q.name)})
        self._tocar(q, {'monto': pagado, 'ajuste_estado': 'cerrada' if pagado > 0 else 'trasladada',
                        'ajuste_nota': _('Saldo de %s trasladado a %s.') % (self._soles(saldo), dest.name)})

    def _aplicar_mora(self):
        q = self.cuota_id
        if not q or q.cuenta_id != self.cuenta_id:
            raise ValidationError(_('La cuota no pertenece a esta cuenta.'))
        moras = self._mora_cuotas(q)
        if self._es_cero(moras[q][0]):
            raise ValidationError(_('La %s no tiene mora pendiente.') % q.name)
        if self.mora_accion == 'cuota' and not _abierta(q):
            raise ValidationError(_('La cuota ya está pagada: cobra la mora como cargo aparte.'))
        self._resolver_mora(moras, q)

    def _aplicar_insertar(self):
        monto = round(self.monto or 0.0, 2)
        if monto <= 0:
            raise ValidationError(_('Indica el monto de la cuota.'))
        fecha = self._ubicar()
        nueva = self._crear({'name': (self.nombre or '').strip() or _('Cuota adicional'), 'monto': monto,
                             'fecha_cronograma': fecha, 'type': self.cuota_tipo or 'cuota',
                             'ajuste_nota': _('Agregada por %s.') % self.name})
        if self.origen == 'redistribuir':
            resta = monto
            for q in self._abiertas(nueva).filtered(lambda q: q.type == 'cuota' and not q.payment_ids).sorted(
                    lambda q: (q.fecha_cronograma or date.max, q.id), reverse=True):
                if resta <= 0:
                    break
                quita = min(q.monto, resta)
                resta = round(resta - quita, 2)
                if float_compare(quita, q.monto, precision_rounding=self._redondeo()) >= 0:
                    self._quitar(q)
                else:
                    self._tocar(q, {'monto': round(q.monto - quita, 2),
                                    'ajuste_nota': _('Reducida en %s por %s.') % (self._soles(quita), self.name)})
            if resta > 0:
                raise ValidationError(_('Las cuotas sin pagos no alcanzan para descontar %s.') % self._soles(monto))

    def _aplicar_eliminar(self):
        q = self.cuota_id
        if not q or q.cuenta_id != self.cuenta_id:
            raise ValidationError(_('La cuota no pertenece a esta cuenta.'))
        if q.ajuste_estado == 'eliminada':
            raise ValidationError(_('La %s ya está eliminada.') % q.name)
        if q.payment_ids:
            raise ValidationError(_('La %s tiene pagos: usa «Quitar pagos» antes de eliminarla.') % q.name)
        if q.cuota_pendiente_ids.filtered(lambda r: r.estado == 'PENDIENTE_VALIDAR'):
            raise ValidationError(_('La %s tiene un pago informado desde la app por validar.') % q.name)
        self._quitar(q)

    def _aplicar_editar(self, filas):
        """filas: [{'id', 'nombre', 'fecha', 'saldo'}] con el cronograma pendiente completo."""
        abiertas = self._abiertas()
        moras = self._mora_cuotas(self.cuenta_id.cuota_ids.filtered(lambda q: (q.mora_pendiente or 0.0) > 0))
        if self.mora_accion == 'cuota':
            raise ValidationError(_('Opción de mora no válida para el editor.'))
        mora = round(sum(p for p, _y in moras.values()), 2)
        objetivo = round(sum(max(q.saldo, 0.0) for q in abiertas) + (self.adicional or 0.0), 2)
        if self.mora_accion == 'incluir':
            acordada = mora if self.mora_acordada in (False, None) else round(min(max(self.mora_acordada, 0.0), mora), 2)
            objetivo = round(objetivo + acordada, 2)
            # Se reparte en el cronograma: la mora de las cuotas queda en cero y no hay cargo aparte.
            self.mora_accion, self.mora_acordada = 'perdonar', 0.0
            self._resolver_mora(moras)
            self.mora_accion, self.mora_acordada, self.mora_perdonada = 'incluir', acordada, round(mora - acordada, 2)
        else:
            self._resolver_mora(moras)
        total = 0.0
        vistos = self.env['adt.comercial.cuotas']
        for i, f in enumerate(filas or []):
            saldo = round(float(f.get('saldo') or 0.0), 2)
            if saldo < 0:
                raise ValidationError(_('Fila %s: el monto no puede ser negativo.') % (i + 1))
            total += saldo
            fecha = fields.Date.to_date(f.get('fecha')) if f.get('fecha') else False
            nombre = (f.get('nombre') or '').strip()
            if f.get('id'):
                q = abiertas.filtered(lambda x: x.id == int(f['id']))
                if not q:
                    raise ValidationError(_('Fila %s: la cuota ya no está pendiente. Vuelve a abrir el editor.') % (i + 1))
                vistos |= q
                pagado = _pagado(q)
                if self._es_cero(saldo) and not pagado:
                    self._quitar(q)
                    continue
                vals = {}
                if nombre and nombre != q.name:
                    vals['name'] = nombre
                if fecha and fecha != q.fecha_cronograma:
                    vals['fecha_cronograma'] = fecha
                if float_compare(pagado + saldo, q.monto, precision_rounding=self._redondeo()):
                    vals['monto'] = round(pagado + saldo, 2)
                    if self._es_cero(saldo):
                        vals.update(ajuste_estado='cerrada', ajuste_nota=_('Cerrada con lo pagado por %s.') % self.name)
                if vals:
                    self._tocar(q, vals)
            elif saldo > 0:
                if not fecha:
                    raise ValidationError(_('Fila %s: indica la fecha.') % (i + 1))
                self._crear({'name': nombre or _('Cuota R-%s') % (i + 1), 'monto': saldo, 'fecha_cronograma': fecha,
                             'ajuste_nota': _('Creada por %s.') % self.name})
        for q in abiertas - vistos:
            if not q.exists():
                continue
            if q.payment_ids:
                raise ValidationError(_('La %s tiene pagos: no se puede quitar; deja su monto en 0 para cerrarla.') % q.name)
            self._quitar(q)
        # El cronograma puede sumar más o menos que lo refinanciado, pero la diferencia se explica.
        if float_compare(round(total, 2), objetivo, precision_rounding=self._redondeo()):
            if not (self.diferencia_motivo or '').strip():
                raise ValidationError(_('El cronograma suma %s y lo refinanciado es %s: explica el motivo de la diferencia.')
                                      % (self._soles(total), self._soles(objetivo)))
            self.diferencia = round(total - objetivo, 2)
        else:
            self.diferencia_motivo = False

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------

    def _describir(self, linea):
        antes = json.loads(linea.antes or '{}')
        q = linea.cuota_id
        if linea.accion == 'eliminada':
            fecha = fields.Date.to_date(antes['fecha_cronograma']) if antes.get('fecha_cronograma') else False
            return _('Se elimina · vencía el %s · %s') % (self._f(fecha), self._soles(antes.get('monto')))
        if linea.accion == 'creada':
            return _('Nueva · vence el %s · %s') % (self._f(q.fecha_cronograma), self._soles(q.monto)) if q else ''
        if not q:
            return ''
        partes = []
        if antes.get('name') != q.name:
            partes.append(_('antes «%s»') % antes.get('name'))
        fecha_antes = fields.Date.to_date(antes.get('fecha_cronograma')) if antes.get('fecha_cronograma') else False
        if fecha_antes != q.fecha_cronograma:
            partes.append(_('vence %s → %s') % (self._f(fecha_antes), self._f(q.fecha_cronograma)))
        if float_compare(antes.get('monto') or 0.0, q.monto or 0.0, precision_rounding=self._redondeo()):
            partes.append(_('monto %s → %s') % (self._soles(antes.get('monto')), self._soles(q.monto)))
        if q.ajuste_estado != antes.get('ajuste_estado') and q.ajuste_estado in ('cerrada', 'trasladada'):
            partes.append(dict(q._fields['ajuste_estado'].selection)[q.ajuste_estado].lower())
        if q.mora_manual and not antes.get('mora_manual') or float_compare(
                antes.get('mora_manual_monto') or 0.0, q.mora_manual_monto or 0.0, precision_rounding=self._redondeo()):
            partes.append(_('mora pendiente %s') % self._soles(q.mora_pendiente))
        return ' · '.join(partes)

    def _cerrar(self):
        self.flush()
        self.cuenta_id.cuota_ids.invalidate_cache()
        for linea in self.linea_ids:
            if linea.cuota_id:
                linea.despues = json.dumps(self._foto(linea.cuota_id))
            linea.descripcion = self._describir(linea)
        self.deuda_despues = self._deuda()
        lineas = ['%s: %s' % (l.cuota_nombre, l.descripcion) for l in self.linea_ids if l.descripcion]
        if self.diferencia:
            lineas.append(_('Diferencia con lo refinanciado: %s%s · %s') % (
                '+' if self.diferencia > 0 else '−', self._soles(abs(self.diferencia)), self.diferencia_motivo or ''))
        if self.mora_perdonada:
            lineas.append(_('Mora perdonada: %s') % self._soles(self.mora_perdonada))
        self.resumen = '\n'.join(lineas)

    @api.model
    def aplicar(self, vals, filas=None):
        """Crea y aplica un ajuste. `filas` solo para el editor de cronograma."""
        cuenta = self.env['adt.comercial.cuentas'].browse(vals.get('cuenta_id')).exists()
        if not cuenta:
            raise UserError(_('La cuenta ya no existe.'))
        if cuenta.state != 'en_curso':
            raise ValidationError(_('Solo se ajustan cronogramas de cuentas en curso.'))
        if not (vals.get('motivo') or '').strip():
            raise ValidationError(_('Escribe el motivo o el acuerdo con el cliente.'))
        self.env.cr.execute('SELECT id FROM adt_comercial_cuentas WHERE id = %s FOR UPDATE', [cuenta.id])
        ajuste = self.create(vals)
        ajuste.deuda_antes = ajuste._deuda()
        if ajuste.tipo == 'editar':
            ajuste.cronograma_antes = json.dumps(ajuste._cronograma())
        getattr(ajuste, '_aplicar_%s' % ajuste.tipo)(*([filas] if ajuste.tipo == 'editar' else []))
        ajuste._cerrar()
        if ajuste.tipo == 'editar':
            ajuste.cronograma_despues = json.dumps(ajuste._cronograma())
        ajuste._nota(dict(TIPOS)[ajuste.tipo])
        return ajuste

    @api.model
    def simular(self, vals, filas=None):
        """Aplica el ajuste dentro de un savepoint y lo descarta: devuelve lo que cambiaría."""
        class _Simulacion(Exception):
            pass
        resultado = {}
        self.flush()
        try:
            with self.env.cr.savepoint():
                ajuste = self.with_context(ajuste_simulacion=True).aplicar(vals, filas)
                resultado = ajuste._resumen_dict()
                raise _Simulacion()
        except _Simulacion:
            pass
        finally:
            self.env.clear()
        return resultado

    def _resumen_dict(self):
        self.ensure_one()
        # En orden de vencimiento, y marcada la cuota que motivó el ajuste (o las que se crearon)
        # para que la vista la enfoque aunque el ajuste haya corrido muchas otras.
        lineas = self.linea_ids.filtered('descripcion').sorted(lambda l: (
            l.accion == 'eliminada', l.cuota_id.fecha_cronograma or date.max, l.id))
        principales = lineas.filtered(lambda l: (self.cuota_id and l.cuota_id == self.cuota_id) or l.accion == 'creada')
        return {
            'id': self.id,
            'tipo': dict(TIPOS)[self.tipo],
            'clave': self.tipo,
            'cronograma': self.tipo == 'editar' and {
                'antes': json.loads(self.cronograma_antes or '[]'),
                'despues': json.loads(self.cronograma_despues or '[]'),
            },
            'estado': self.estado,
            'fecha': fields.Datetime.to_string(self.create_date) if self.create_date else '',
            'usuario': self.user_id.name or '',
            'motivo': self.motivo or '',
            'lineas': [{'cuota': l.cuota_nombre, 'texto': l.descripcion, 'accion': l.accion,
                        'principal': l in principales}
                       for l in lineas],
            'deuda_antes': self.deuda_antes,
            'deuda_despues': self.deuda_despues,
            'mora_calculada': self.mora_calculada,
            'mora_perdonada': self.mora_perdonada,
            'diferencia': self.diferencia,
            'diferencia_motivo': self.diferencia_motivo or '',
        }

    # ------------------------------------------------------------------
    # Deshacer
    # ------------------------------------------------------------------

    def action_revertir(self):
        for ajuste in self:
            ajuste._revertir()
        return True

    def _revertir(self):
        self.ensure_one()
        if self.estado != 'aplicado':
            raise UserError(_('Este ajuste ya se deshizo.'))
        ultimo = self.search([('cuenta_id', '=', self.cuenta_id.id), ('estado', '=', 'aplicado')], limit=1)
        if ultimo != self:
            raise UserError(_('Solo se puede deshacer el último ajuste de la cuenta (%s).') % ultimo.name)
        for linea in self.linea_ids:
            q = linea.cuota_id
            if q and len(q.payment_ids) != linea.pagos_antes:
                raise UserError(_('La %s recibió pagos después del ajuste; deshacerlo descuadraría esos pagos.') % q.name)
        for linea in self.linea_ids.sorted('id', reverse=True):
            q = linea.cuota_id
            if linea.accion == 'creada':
                if q:
                    q.unlink()
                continue
            antes = json.loads(linea.antes or '{}')
            pagos_mora = antes.pop('_pagos_mora', {})
            if linea.accion == 'eliminada' and not q:
                q = self.env['adt.comercial.cuotas'].create(antes)
                linea.cuota_id = q
                continue
            if q:
                q.write(antes)
                for pago in q.payment_ids:
                    if str(pago.id) in pagos_mora:
                        pago.mora = pagos_mora[str(pago.id)]
        self.write({'estado': 'revertido', 'revertido_por': self.env.user.id, 'revertido_fecha': fields.Datetime.now()})
        self._nota(_('Ajuste deshecho: %s') % dict(TIPOS)[self.tipo], deshecho=True)


class AdtCobranzaAjusteLinea(models.Model):
    _name = 'adt.cobranza.ajuste.linea'
    _description = 'Cuota afectada por un ajuste'
    _order = 'id'

    ajuste_id = fields.Many2one('adt.cobranza.ajuste', required=True, ondelete='cascade', index=True)
    cuota_id = fields.Many2one('adt.comercial.cuotas', 'Cuota', ondelete='set null')
    cuota_nombre = fields.Char('Cuota')
    accion = fields.Selection([('modificada', 'Modificada'), ('creada', 'Creada'), ('eliminada', 'Quitada')], required=True)
    descripcion = fields.Char('Cambio')
    antes = fields.Text()
    despues = fields.Text()
    pagos_antes = fields.Integer()
