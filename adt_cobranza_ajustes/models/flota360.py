# -*- coding: utf-8 -*-
"""Ajustes de cronograma en Flota 360: acciones por cuota y por cuenta, formularios con vista
previa, editor de cronograma e historial de ajustes con «Deshacer»."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.adt_flota_360.models.flota_360 import accion_form

from .ajuste import TIPOS, _abierta

FORMULARIOS = ('reprogramar', 'trasladar', 'mora', 'insertar', 'eliminar')
MORA_EDITOR = ('perdonar', 'incluir', 'cargo', 'mantener')


class Flota360Ajustes(models.AbstractModel):
    _inherit = 'adt.flota360'

    # ------------------------------------------------------------------
    # Acceso
    # ------------------------------------------------------------------

    def _ajuste_destino(self, vehicle_id, params):
        """(cuenta, cuota) del ajuste, validando vehículo, empresa, permisos y estado."""
        v = self._vehiculo(vehicle_id)
        cuota = self.env['adt.comercial.cuotas']
        if params.get('cuota_id'):
            cuota = cuota.browse(int(params['cuota_id'])).exists()
            if not cuota:
                raise UserError(_('La cuota ya no existe.'))
            cuenta = cuota.cuenta_id
        else:
            cuenta = self.env['adt.comercial.cuentas'].browse(int(params.get('cuenta_id') or 0)).exists()
        if not cuenta:
            raise UserError(_('La cuenta ya no existe.'))
        if cuenta.vehiculo_id != v or cuenta.company_id not in self.env.companies:
            raise AccessError(_('La cuenta no corresponde a este vehículo o empresa.'))
        for rec in (cuenta, cuota):
            if rec:
                rec.check_access_rights('write')
                rec.check_access_rule('write')
        if cuenta.state != 'en_curso':
            raise ValidationError(_('Solo se ajustan cronogramas de cuentas en curso.'))
        return cuenta, cuota

    def _etiqueta_cuota(self, q):
        return '%s · %s · %s' % (q.name, q.fecha_cronograma.strftime('%d/%m/%Y') if q.fecha_cronograma else '—',
                                 self._soles(q.saldo))

    # ------------------------------------------------------------------
    # Formularios (clave «ajuste»)
    # ------------------------------------------------------------------

    def _form_ajuste_spec(self, tipo, cuenta, q):
        A = self.env['adt.cobranza.ajuste']
        campo = lambda nombre, **kw: self._campo_spec(A, nombre, **kw)
        hoy = fields.Date.context_today(self)
        abiertas = cuenta.cuota_ids.filtered(lambda x: _abierta(x) and x != q).sorted(
            lambda x: (x.fecha_cronograma or hoy, x.id))
        opciones = [[x.id, self._etiqueta_cuota(x)] for x in abiertas]
        motivo = campo('motivo', label='Motivo / acuerdo con el cliente', required=True, col=2,
                       placeholder='Ej.: el cliente pagará el resto con la siguiente cuota; acordado con la cobradora.')
        valores = {'motivo': ''}
        secciones = []

        def ubicacion(titulo):
            secciones.append({'titulo': titulo, 'campos': [
                campo('destino', label='¿Dónde va?', segmentado=True, required=True, col=2),
                campo('cuota_ref_id', label='Después de', type='selection', options=opciones,
                      visible=['destino', 'despues'], help='Las cuotas siguientes se corren un periodo.'),
                campo('fecha', label='Vence el', visible=['destino', 'fecha']),
                campo('correr_fechas', visible=['destino', 'fecha'], col=2),
            ]})
            valores.update({'destino': 'final', 'cuota_ref_id': opciones[0][0] if opciones else False,
                            'fecha': str(hoy), 'correr_fechas': False})

        def mora(acciones, defecto):
            pendiente = round(q.mora_pendiente or 0.0, 2) if q else 0.0
            if pendiente <= 0:
                return
            etiquetas = dict(A._fields['mora_accion'].selection)
            secciones.append({'titulo': 'Mora', 'campos': [
                campo('mora_accion', segmentado=True, required=True, col=2, options=[[a, etiquetas[a]] for a in acciones],
                      help='Calculada a hoy: %s%s.' % (self._soles(pendiente),
                                                         ' (%s días)' % q.mora_dias if q.mora_dias else '')),
                campo('mora_acordada', visible=['mora_accion', ['cuota', 'cargo']],
                      help='Lo que se cobrará. La diferencia con la calculada queda como perdonada.'),
                campo('mora_fecha', visible=['mora_accion', 'cargo']),
            ]})
            valores.update({'mora_accion': defecto, 'mora_acordada': pendiente, 'mora_fecha': str(hoy)})

        if tipo == 'reprogramar':
            titulo = _('Reprogramar %s') % q.name
            ayuda = _('Saldo %s · vence el %s. Lo pagado queda en la cuota; el saldo pasa a la nueva fecha.') % (
                self._soles(q.saldo), q.fecha_cronograma.strftime('%d/%m/%Y') if q.fecha_cronograma else '—')
            ubicacion('Nueva fecha')
            mora(['cuota', 'cargo', 'perdonar'], 'cuota')
        elif tipo == 'trasladar':
            titulo = _('Trasladar el saldo de %s') % q.name
            ayuda = _('%s pasa a otra cuota y %s queda cerrada (pagada con lo abonado).') % (self._soles(q.saldo), q.name)
            siguiente = abiertas.filtered(lambda x: x.fecha_cronograma and q.fecha_cronograma
                                          and x.fecha_cronograma > q.fecha_cronograma)[:1] or abiertas[:1]
            secciones.append({'titulo': 'Destino', 'campos': [
                campo('cuota_ref_id', label='Se suma a', type='selection', options=opciones, required=True, col=2)]})
            valores['cuota_ref_id'] = siguiente.id or False
            mora(['cargo', 'perdonar'], 'cargo')
        elif tipo == 'eliminar':
            titulo = _('Eliminar %s') % q.name
            ayuda = _('%s · vence el %s. Se quita del cronograma; puedes deshacerlo desde la pestaña Ajustes.') % (
                self._soles(q.saldo), q.fecha_cronograma.strftime('%d/%m/%Y') if q.fecha_cronograma else '—')
            motivo['label'] = 'Motivo de la eliminación'
            motivo['placeholder'] = 'Ej.: cuota duplicada; cargo registrado por error.'
        elif tipo == 'mora':
            titulo = _('Acordar la mora de %s') % q.name
            ayuda = _('Perdona la mora, fija un monto acordado o pásala a un cargo con su propia fecha.')
            mora((['cuota'] if _abierta(q) else []) + ['cargo', 'perdonar'], 'cuota' if _abierta(q) else 'cargo')
        else:
            titulo = _('Agregar cuota')
            ayuda = _('Una cuota o cargo nuevo en cualquier punto del cronograma.')
            secciones.append({'titulo': 'Cuota', 'campos': [
                campo('nombre', label='Nombre', required=True),
                campo('monto', label='Monto', required=True),
                campo('cuota_tipo', segmentado=True, required=True),
                campo('origen', segmentado=True, required=True,
                      help='«Sale de las últimas cuotas» descuenta el monto desde la última cuota sin pagos: el total no cambia.'),
            ]})
            valores.update({'nombre': _('Cuota adicional'), 'monto': cuenta.monto_cuota or 0.0,
                            'cuota_tipo': 'cuota', 'origen': 'adicional'})
            ubicacion('Ubicación')
        secciones.append({'titulo': 'Acuerdo', 'campos': [motivo]})
        for sec in secciones:
            sec['campos'] = [c for c in sec['campos'] if c]
        return titulo, ayuda, secciones, valores

    def _vals_ajuste(self, tipo, cuenta, q, valores, secciones):
        """Valores del formulario → vals de adt.cobranza.ajuste (solo los campos ofrecidos)."""
        permitidos = {c['name']: c for s in secciones for c in s['campos']}
        A = self.env['adt.cobranza.ajuste']
        vals = {'tipo': tipo, 'cuenta_id': cuenta.id, 'cuota_id': q.id or False}
        for nombre, valor in (valores or {}).items():
            spec = permitidos.get(nombre)
            if not spec:
                continue
            if valor in ('', None):
                valor = False
            tipo_campo = A._fields[nombre].type
            if spec.get('options') and valor and str(valor) not in {str(o[0]) for o in spec['options']}:
                raise ValidationError(_('Valor no válido para %s.') % spec['label'])
            if tipo_campo == 'many2one':
                valor = int(valor) if valor else False
            elif tipo_campo in ('float', 'monetary'):
                valor = float(valor or 0.0)
            elif tipo_campo == 'boolean':
                valor = bool(valor)
            vals[nombre] = valor
        return vals

    @api.model
    def formulario(self, clave, vehicle_id, res_id=False, params=None):
        if clave != 'ajuste':
            return super().formulario(clave, vehicle_id, res_id=res_id, params=params)
        params = params or {}
        if params.get('tipo') not in FORMULARIOS:
            raise ValidationError(_('Tipo de ajuste no válido.'))
        cuenta, q = self._ajuste_destino(vehicle_id, params)
        if params['tipo'] in ('reprogramar', 'trasladar') and (not _abierta(q) or q.saldo <= 0):
            raise ValidationError(_('La %s no tiene saldo pendiente.') % q.name)
        if params['tipo'] == 'eliminar' and q.payment_ids:
            raise ValidationError(_('La %s tiene pagos: usa «Quitar pagos» antes de eliminarla.') % q.name)
        if params['tipo'] == 'mora' and (q.mora_pendiente or 0.0) <= 0:
            raise ValidationError(_('La %s no tiene mora pendiente.') % q.name)
        titulo, ayuda, secciones, valores = self._form_ajuste_spec(params['tipo'], cuenta, q)
        return {'clave': 'ajuste', 'res_id': False, 'titulo': titulo,
                'ayuda': '%s · %s · %s' % (cuenta.partner_id.display_name, cuenta.reference_no, ayuda),
                'secciones': secciones, 'valores': valores, 'lateral': False}

    def _ajuste_desde_form(self, vehicle_id, params, valores, simular=False):
        params = params or {}
        if params.get('tipo') not in FORMULARIOS:
            raise ValidationError(_('Tipo de ajuste no válido.'))
        cuenta, q = self._ajuste_destino(vehicle_id, params)
        _t, _a, secciones, _v = self._form_ajuste_spec(params['tipo'], cuenta, q)
        vals = self._vals_ajuste(params['tipo'], cuenta, q, valores, secciones)
        A = self.env['adt.cobranza.ajuste']
        if simular:
            vals['motivo'] = vals.get('motivo') or _('Vista previa')
            return A.simular(vals)
        return A.aplicar(vals)

    @api.model
    def guardar(self, clave, vehicle_id, valores, res_id=False, params=None):
        if clave != 'ajuste':
            return super().guardar(clave, vehicle_id, valores, res_id=res_id, params=params)
        ajuste = self._ajuste_desde_form(vehicle_id, params, valores)
        return {'id': ajuste.id, 'nombre': ajuste.name, 'mensaje': _('%s aplicado.') % ajuste.name}

    @api.model
    def simular_ajuste(self, vehicle_id, params, valores):
        try:
            return self._ajuste_desde_form(vehicle_id, params, valores, simular=True)
        except (UserError, ValidationError) as e:
            return {'error': e.args[0] if e.args else str(e)}

    # ------------------------------------------------------------------
    # Editor de cronograma
    # ------------------------------------------------------------------

    @api.model
    def editor_cronograma(self, vehicle_id, cuenta_id):
        cuenta, _q = self._ajuste_destino(vehicle_id, {'cuenta_id': cuenta_id})
        hoy = fields.Date.context_today(self)
        abiertas = cuenta.cuota_ids.filtered(_abierta).sorted(lambda x: (x.fecha_cronograma or hoy, x.id))
        mora = round(sum(q.mora_pendiente or 0.0 for q in cuenta.cuota_ids), 2)
        dias = {'semanal': 7, 'quincena': 15, 'mensual': 30}.get(cuenta.periodicidad, 15)
        return {
            'cuenta_id': cuenta.id,
            'referencia': cuenta.reference_no or cuenta.display_name,
            'titular': cuenta.partner_id.display_name,
            'periodo': self._etiqueta(cuenta, 'periodicidad', cuenta.periodicidad) if cuenta.periodicidad else '',
            'dias': dias,
            'periodicidad': cuenta.periodicidad or 'quincena',
            'monto_cuota': cuenta.monto_cuota or 0.0,
            'hoy': fields.Date.to_string(hoy),
            'moneda': cuenta.company_id.currency_id.symbol or 'S/',
            'deuda': round(sum(max(q.saldo, 0.0) for q in abiertas), 2),
            'mora': mora,
            'filas': [{
                'id': q.id, 'nombre': q.name or '', 'tipo': 'Cargo' if q.type == 'mora' else '',
                'fecha': fields.Date.to_string(q.fecha_cronograma) if q.fecha_cronograma else '',
                'saldo': round(max(q.saldo, 0.0), 2), 'pagado': round(sum(q.payment_ids.mapped('amount')), 2),
                'vencida': bool(q.fecha_cronograma and q.fecha_cronograma < hoy),
            } for q in abiertas],
        }

    @api.model
    def aplicar_editor(self, vehicle_id, cuenta_id, datos, simular=False):
        cuenta, _q = self._ajuste_destino(vehicle_id, {'cuenta_id': cuenta_id})
        datos = datos or {}
        accion = datos.get('mora_accion') or 'mantener'
        if accion not in MORA_EDITOR:
            raise ValidationError(_('Opción de mora no válida.'))
        vals = {
            'tipo': 'editar', 'cuenta_id': cuenta.id, 'motivo': datos.get('motivo') or '',
            'adicional': float(datos.get('adicional') or 0.0), 'mora_accion': accion,
            'diferencia_motivo': (datos.get('diferencia_motivo') or '').strip() or False,
            'mora_acordada': float(datos['mora_acordada']) if datos.get('mora_acordada') not in (None, '', False) else False,
            'mora_fecha': datos.get('mora_fecha') or False,
        }
        if vals['adicional'] < 0:
            raise ValidationError(_('El monto adicional no puede ser negativo.'))
        A = self.env['adt.cobranza.ajuste']
        if simular:
            vals['motivo'] = vals['motivo'] or _('Vista previa')
            return A.simular(vals, datos.get('filas') or [])
        ajuste = A.aplicar(vals, datos.get('filas') or [])
        return {'id': ajuste.id, 'nombre': ajuste.name, 'resumen': ajuste._resumen_dict(),
                'mensaje': _('%s aplicado: cronograma actualizado.') % ajuste.name}

    @api.model
    def revertir_ajuste(self, vehicle_id, ajuste_id):
        ajuste = self.env['adt.cobranza.ajuste'].browse(int(ajuste_id)).exists()
        if not ajuste:
            raise UserError(_('El ajuste ya no existe.'))
        self._ajuste_destino(vehicle_id, {'cuenta_id': ajuste.cuenta_id.id})
        ajuste._revertir()
        return {'mensaje': _('%s deshecho: las cuotas volvieron a como estaban.') % ajuste.name}

    # ------------------------------------------------------------------
    # Ficha del vehículo
    # ------------------------------------------------------------------

    def _acciones_cuota(self, q, mora_registrada):
        principal, mas = super()._acciones_cuota(q, mora_registrada)
        if q.cuenta_id.state != 'en_curso':
            return principal, mas
        extra = []
        if _abierta(q) and q.saldo > 0:
            extra += [dict(accion_form('ajuste', 'Reprogramar cuota', 'fa-calendar-plus-o', params={'tipo': 'reprogramar', 'cuota_id': q.id}), corto='Reprogramar'),
                      dict(accion_form('ajuste', 'Trasladar saldo a otra cuota', 'fa-share', params={'tipo': 'trasladar', 'cuota_id': q.id}), corto='Trasladar')]
        if (q.mora_pendiente or 0.0) > 0:
            extra.append(dict(accion_form('ajuste', 'Acordar o perdonar mora', 'fa-handshake-o', params={'tipo': 'mora', 'cuota_id': q.id}), corto='Mora'))
            # «Editar mora» queda cubierto por «Acordar o perdonar mora».
            mas = [a for a in mas if a.get('method') != 'action_editar_mora']
        # Eliminar como ajuste: un solo popup con motivo, queda en el historial y se puede deshacer.
        mas = [a for a in mas if a.get('method') != 'action_eliminar_cuota']
        if not q.payment_ids and q.ajuste_estado != 'eliminada':
            mas.append(dict(accion_form('ajuste', 'Eliminar cuota', 'fa-trash', params={'tipo': 'eliminar', 'cuota_id': q.id}),
                            corto='Eliminar', danger=True))
        return principal, extra + mas

    # Asistentes de adt_comercial que los ajustes reemplazan: «Agregar cuota o cargo» (→ Agregar cuota),
    # «Refinanciar» y «Cronograma por tramos» (→ Editar o refinanciar cronograma).
    REEMPLAZADOS = ('agregar_mora', 'refinanciar_cuotas', 'action_cronograma_tramos')

    def _acciones_cuenta(self, c):
        principal, grupos, documentos = super()._acciones_cuenta(c)
        if c.state == 'en_curso':
            grupos = [dict(g, acciones=[a for a in g['acciones'] if a.get('method') not in self.REEMPLAZADOS]) for g in grupos]
            grupos = [g for g in grupos if g['acciones']]
            grupos.insert(0, {'titulo': 'Cronograma', 'acciones': [
                dict(accion_form('ajuste', 'Agregar cuota o cargo', 'fa-plus-square-o', params={'tipo': 'insertar', 'cuenta_id': c.id}),
                     descripcion='En cualquier punto del cronograma; corre o no las siguientes.'),
                {'tipo': 'editor_crono', 'cuenta_id': c.id, 'label': 'Refinanciar o editar el cronograma', 'icon': 'fa-table',
                 'descripcion': 'Montos, fechas y cuotas libres; el total debe cuadrar.'},
            ]})
        return principal, grupos, documentos

    def _estado_cuota(self, q, hoy):
        if q.ajuste_estado == 'cerrada':
            return 'pagada', 'Pagada · ajuste', 'ok'
        if q.ajuste_estado == 'trasladada':
            return 'pagada', 'Trasladada', 'neutral'
        if q.ajuste_estado == 'eliminada':
            return 'anulada', 'Eliminada', 'neutral'
        return super()._estado_cuota(q, hoy)

    def _orden_cuota(self, q, hoy):
        # Una subcuota reprogramada va en su nueva fecha, no debajo de su cuota de origen.
        if q.ajuste_estado == 'reprogramada':
            return q.fecha_cronograma or hoy, q.id, q.id
        return super()._orden_cuota(q, hoy)

    def _aviso_cuota(self, q):
        partes = [super()._aviso_cuota(q), q.ajuste_nota or '']
        if q.monto_pactado and q.currency_id.compare_amounts(q.monto_pactado, q.monto):
            partes.append(_('Monto pactado originalmente: %s.') % self._soles(q.monto_pactado))
        return ' '.join(p for p in partes if p)

    def _seccion_cuentas(self, v, hoy):
        seccion = super()._seccion_cuentas(v, hoy)
        if not seccion:
            return seccion
        Ajuste = self.env['adt.cobranza.ajuste']
        for c in seccion.get('deuda') or []:
            ajustes = Ajuste.search([('cuenta_id', '=', c['id'])], limit=50)
            ultimo = ajustes.filtered(lambda a: a.estado == 'aplicado')[:1]
            c['ajustes'] = [dict(a._resumen_dict(), deshacer=a == ultimo and c['state'] == 'en_curso') for a in ajustes]
            reprogramadas = set(self.env['adt.comercial.cuotas'].search(
                [('cuenta_id', '=', c['id']), ('ajuste_estado', '=', 'reprogramada')]).ids)
            for f in c['cuotas']:
                if f['id'] in reprogramadas and not f['tipo']:
                    f['tipo'] = 'Reprogramada'
        return seccion
