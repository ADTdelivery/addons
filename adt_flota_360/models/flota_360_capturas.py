# -*- coding: utf-8 -*-
"""Capturas paso a paso (acción JS: adt_flota_360_capturas).

El proceso de captura en etapas claras, cada una con su lista y su acción:

1. Por capturar: cuentas con cuotas vencidas del cronograma o papeletas del SAT
   Lima pendientes de pago (vista adt.captura.mora de adt_captura). Una papeleta
   SAT pendiente basta para que el cliente aparezca aquí.
2. Cobrar intervención: vehículo capturado con la intervención sin pagar.
3. Liberar o retener: el supervisor libera el vehículo o inicia la disolución.
4. Disolución: falta recolocar el vehículo.
5. Cerradas: liberadas, recolocadas o canceladas.

Las reglas (validaciones, estados del vehículo, chatter) son las de adt_captura;
aquí solo se arman los datos de la vista y se llaman sus métodos.
"""
import base64
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .flota_360 import PAPELETA_DIAS_ALERTA, nivel_sat, plural

GRUPO_SUPERVISOR = 'adt_captura.group_captura_supervisor'
CUOTAS_VENCIDAS = ('pendiente', 'retrasado')  # mismo criterio que adt.captura.mora
DIAS_CERRADAS = 90
MAX_FILAS = 300
MAX_ARCHIVO = 10 * 1024 * 1024
MONTO_INTERVENCION = 50.0

# Etapas del tablero: clave, título, icono y qué se hace en ella.
ETAPAS = [
    ('por_capturar', 'Por capturar', 'fa-search',
     'Clientes con cuotas vencidas o papeletas SAT pendientes. Revisa el motivo y registra la captura.'),
    ('por_cobrar', 'Cobrar intervención', 'fa-money',
     'Vehículos capturados con la intervención sin pagar. Registra el voucher o la exoneración.'),
    ('por_decidir', 'Liberar o retener', 'fa-balance-scale',
     'Intervención resuelta. El supervisor libera el vehículo o inicia la disolución del contrato.'),
    ('disolucion', 'Disolución', 'fa-file-text-o',
     'Contratos en disolución. Adjunta la desafiliación y la entrega para recolocar el vehículo.'),
    ('cerradas', 'Cerradas', 'fa-check-circle',
     'Capturas liberadas, recolocadas o canceladas en los últimos %s días.' % DIAS_CERRADAS),
]
ORIGENES = [('mora', 'Cuotas vencidas'), ('papeleta', 'Papeletas SAT'), ('ambos', 'Cuotas y papeletas SAT')]


class AdtFlota360Capturas(models.AbstractModel):
    _inherit = 'adt.flota360'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _cap_modelos(self):
        Mora = self._modelo('adt.captura.mora', 'papeletas_sat', 'deuda_sat')
        Captura = self._modelo('adt.captura.record', 'papeleta_sat_ids')
        return Mora, Captura

    def _cap_registro(self, captura_id):
        _mora, Captura = self._cap_modelos()
        captura = Captura.browse(int(captura_id)).exists() if Captura is not None and captura_id else None
        if not captura:
            raise UserError(_('La captura ya no existe.'))
        return captura

    def _cap_dominio_etapa(self, etapa):
        hoy = fields.Date.context_today(self)
        return {
            'por_cobrar': [('state', '=', 'capturado'), ('payment_state', '=', 'pendiente')],
            'por_decidir': [('state', '=', 'capturado'), ('payment_state', '=', 'pagado')],
            'disolucion': [('state', '=', 'disolucion_contrato')],
            'cerradas': [('state', 'in', ('liberado', 'recolocada', 'cancelado')),
                         ('write_date', '>=', fields.Date.to_string(hoy - timedelta(days=DIAS_CERRADAS)))],
        }.get(etapa)

    def _cap_fecha(self, dt):
        """Fecha local (Lima) de un datetime de Odoo."""
        return fields.Datetime.context_timestamp(self, dt).date() if dt else False

    def _cap_archivo(self, archivo, obligatorio=False, etiqueta=''):
        """Archivo enviado por la vista: {'nombre', 'datos'} con datos en base64."""
        if not archivo or not archivo.get('datos'):
            if obligatorio:
                raise ValidationError(_('Adjunte %s.') % etiqueta)
            return None
        datos = archivo['datos'].split(',', 1)[-1]  # admite data URL
        try:
            tamano = len(base64.b64decode(datos, validate=True))
        except Exception:
            raise ValidationError(_('El archivo %s no es válido.') % (archivo.get('nombre') or ''))
        if tamano > MAX_ARCHIVO:
            raise ValidationError(_('El archivo %s supera los 10 MB.') % (archivo.get('nombre') or ''))
        return {'nombre': archivo.get('nombre') or 'archivo', 'datos': datos}

    def _cap_papeleta(self, p):
        pendiente = p.estado_pago == 'pendiente'
        nivel_estado = nivel_sat(p.estado_sat) if p.vigente else 'neutral'
        nivel = 'ok' if not pendiente else (
            'critico' if nivel_estado == 'critico' or (p.dias or 0) > PAPELETA_DIAS_ALERTA else 'atencion')
        return {
            'id': p.id, 'numero': p.name, 'fecha': fields.Date.to_string(p.fecha_infraccion) or False,
            'estado_sat': p.estado_sat or '', 'pendiente': pendiente, 'dias': p.dias or 0,
            'deuda': p.deuda or p.importe or 0.0, 'falta': p.codigo_falta or '', 'nivel': nivel,
        }

    # ------------------------------------------------------------------
    # Tablero
    # ------------------------------------------------------------------

    @api.model
    def capturas_tablero(self, etapa='por_capturar', origen=None, buscar=None, urgentes=False):
        Mora, Captura = self._cap_modelos()
        base = {'disponible': Mora is not None and Captura is not None}
        if not base['disponible']:
            return base
        etapa = etapa if etapa in dict((e[0], e) for e in ETAPAS) else 'por_capturar'
        buscar = (buscar or '').strip()

        dominio_mora = [('captura_existente', '=', False)]
        conteos = {'por_capturar': Mora.search_count(dominio_mora)}
        for clave, *_resto in ETAPAS[1:]:
            conteos[clave] = Captura.search_count(self._cap_dominio_etapa(clave))

        res = dict(base, etapa=etapa, supervisor=self.env.user.has_group(GRUPO_SUPERVISOR),
                   etapas=[{'key': k, 'label': l, 'icon': i, 'desc': d, 'n': conteos[k]} for k, l, i, d in ETAPAS],
                   limite=MAX_FILAS)
        if etapa == 'por_capturar':
            res.update(self._cap_por_capturar(Mora, dominio_mora, origen, buscar, urgentes))
        else:
            dominio = self._cap_dominio_etapa(etapa)
            if buscar:
                dominio = dominio + ['|', '|', '|', '|', ('name', 'ilike', buscar), ('partner_id.name', 'ilike', buscar),
                                     ('partner_id.vat', 'ilike', buscar), ('vehicle_id.license_plate', 'ilike', buscar),
                                     ('cuenta_id.reference_no', 'ilike', buscar)]
            capturas = Captura.search(dominio, order='create_date desc', limit=MAX_FILAS)
            res['items'] = [self._cap_fila_captura(c) for c in capturas]
        return res

    def _cap_por_capturar(self, Mora, dominio, origen, buscar, urgentes):
        por_origen = {g['source_type']: g['source_type_count']
                      for g in Mora.read_group(dominio, ['source_type'], ['source_type'])}
        n_urgentes = Mora.search_count(dominio + [('cuenta_id.captura_prioridad', '=', 'urgente')])
        if origen in dict(ORIGENES):
            dominio = dominio + [('source_type', '=', origen)]
        if urgentes:
            dominio = dominio + [('cuenta_id.captura_prioridad', '=', 'urgente')]
        if buscar:
            dominio = dominio + ['|', '|', '|', '|', ('partner_id.name', 'ilike', buscar), ('vat', 'ilike', buscar),
                                 ('vehicle_id.license_plate', 'ilike', buscar), ('reference_no', 'ilike', buscar),
                                 ('mobile', 'ilike', buscar)]
        filas = Mora.search(dominio, limit=MAX_FILAS)
        items = []
        for m in filas:
            urgente = m.cuenta_id.captura_prioridad == 'urgente'
            nivel = 'critico' if urgente or m.dias_mora >= 30 or m.source_type == 'ambos' else (
                'atencion' if m.dias_mora >= 14 or m.papeletas_sat else 'info')
            items.append({
                'cuenta_id': m.cuenta_id.id, 'vehicle_id': m.vehicle_id.id,
                'prioridad': m.cuenta_id.captura_prioridad or '',
                'cliente': m.partner_id.display_name or '', 'documento': m.vat or '',
                'telefono': m.mobile or m.phone or '', 'placa': m.vehicle_id.license_plate or '',
                'vehiculo': m.vehicle_id.display_name or '', 'cuenta': m.reference_no or '',
                'asesor': m.user_id.name or '', 'origen': m.source_type,
                'dias_mora': m.dias_mora, 'cuotas': m.numero_cuotas_vencidas, 'monto_vencido': m.monto_vencido,
                'papeletas_sat': m.papeletas_sat, 'deuda_sat': m.deuda_sat,
                'fecha_papeleta_sat': fields.Date.to_string(m.fecha_papeleta_sat) or False,
                'gps': bool(m.gps_activo), 'tvs': bool(m.en_mantenimiento_tvs), 'tvs_dias': m.dias_en_mantenimiento_tvs,
                'urgente': urgente, 'nivel': nivel,
            })
        return {
            'items': items,
            'origenes': [{'id': k, 'name': l, 'n': por_origen.get(k, 0)} for k, l in ORIGENES],
            'urgentes_n': n_urgentes,
        }

    def _cap_fila_captura(self, c):
        hoy = fields.Date.context_today(self)
        desde = self._cap_fecha(c.create_date)
        retraso = c.commitment_delay_days if c.capture_type == 'compromiso' else 0
        activa = c.state in ('capturado', 'disolucion_contrato')
        nivel = 'critico' if activa and (retraso or c.payment_state == 'pendiente') else (
            'atencion' if activa else ('ok' if c.state in ('liberado', 'recolocada') else 'neutral'))
        return {
            'captura_id': c.id, 'numero': c.name, 'cuenta_id': c.cuenta_id.id, 'vehicle_id': c.vehicle_id.id,
            'prioridad': c.cuenta_id.captura_prioridad or '',
            'cliente': c.partner_id.display_name or '', 'placa': c.vehicle_id.license_plate or '',
            'cuenta': c.cuenta_id.reference_no or '', 'tipo': self._etiqueta(c, 'capture_type', c.capture_type),
            'compromiso': fields.Date.to_string(c.commitment_date) if c.capture_type == 'compromiso' else False,
            'retraso': retraso, 'fecha': fields.Date.to_string(desde) if desde else False,
            'dias': (hoy - desde).days if desde else 0, 'intervencion': c.intervention_fee,
            'pagado': c.payment_state == 'pagado', 'exonerado': c.payment_state == 'pagado' and not c.pagar_monto,
            'papeletas_sat': c.papeletas_sat_pendientes, 'deuda_sat': c.deuda_sat,
            'estado': self._etiqueta(c, 'state', c.state), 'state': c.state,
            'cierre': self._etiqueta(c, 'liberacion_tipo', c.liberacion_tipo) if c.state == 'liberado' else '',
            'recogida': c.moto_recogida, 'nivel': nivel,
        }

    # ------------------------------------------------------------------
    # Caso: todo lo de una cuenta (o captura) para recorrer los pasos
    # ------------------------------------------------------------------

    @api.model
    def captura_caso(self, cuenta_id=None, captura_id=None):
        Mora, Captura = self._cap_modelos()
        if Mora is None or Captura is None:
            raise UserError(_('El módulo de capturas no está disponible.'))
        captura = self._cap_registro(captura_id) if captura_id else Captura
        cuenta = captura.cuenta_id if captura else self.env['adt.comercial.cuentas'].browse(int(cuenta_id or 0)).exists()
        if not cuenta:
            raise UserError(_('La cuenta ya no existe.'))
        if not captura:
            captura = Captura.search([('cuenta_id', '=', cuenta.id),
                                      ('state', 'in', ('capturado', 'disolucion_contrato'))], order='id desc', limit=1)
        hoy = fields.Date.context_today(self)
        partner, vehiculo = cuenta.partner_id, cuenta.vehiculo_id
        mora = Mora.search([('cuenta_id', '=', cuenta.id)], limit=1)

        cuotas = cuenta.cuota_ids.filtered(
            lambda q: q.type == 'cuota' and q.state in CUOTAS_VENCIDAS and q.fecha_cronograma and q.fecha_cronograma < hoy
        ).sorted('fecha_cronograma')
        papeletas = captura.papeleta_sat_ids if captura else Captura._papeletas_sat_pendientes(cuenta)

        alertas = []
        if mora.en_mantenimiento_tvs:
            alertas.append({'nivel': 'atencion', 'texto': _('El vehículo está en el taller TVS hace %s: '
                                                           'coordina con el taller antes de capturar.')
                                                         % plural(mora.dias_en_mantenimiento_tvs, 'día', 'días')})
        if not cuenta.gps_activo:
            alertas.append({'nivel': 'atencion', 'texto': _('La cuenta no tiene el GPS activo: ubica el vehículo por '
                                                           'otros medios.')})
        deuda_anterior = Captura.search([('cuenta_id', '=', cuenta.id), ('payment_state', '=', 'pendiente'),
                                         ('state', 'in', ('capturado', 'disolucion_contrato')),
                                         ('id', '!=', captura.id or 0)])
        if deuda_anterior:
            alertas.append({'nivel': 'critico', 'texto': _('Tiene %s sin pagar en esta cuenta (%s): S/ %.2f.') % (
                plural(len(deuda_anterior), 'intervención anterior', 'intervenciones anteriores'),
                ', '.join(deuda_anterior.mapped('name')), sum(deuda_anterior.mapped('intervention_fee')))})
        if captura and captura.capture_type == 'compromiso' and captura.commitment_delay_days \
                and captura.state == 'capturado':
            alertas.append({'nivel': 'critico', 'texto': _('El compromiso de pago venció hace %s.')
                                                        % plural(captura.commitment_delay_days, 'día', 'días')})

        historial = Captura.search([('cuenta_id', '=', cuenta.id), ('id', '!=', captura.id or 0)], order='id desc')
        supervisor = self.env.user.has_group(GRUPO_SUPERVISOR)
        return {
            'cuenta_id': cuenta.id,
            'vehicle_id': vehiculo.id,
            'cliente': {'nombre': partner.display_name or '', 'documento': partner.vat or '',
                        'telefono': partner.mobile or partner.phone or '', 'direccion': partner.contact_address or ''},
            'vehiculo': {'placa': vehiculo.license_plate or '', 'nombre': vehiculo.display_name or '',
                         'gps_chip': cuenta.gps_chip or '', 'gps': bool(cuenta.gps_activo)},
            'cuenta': {'referencia': cuenta.reference_no or '', 'estado': self._etiqueta(cuenta, 'state', cuenta.state),
                       'asesor': cuenta.user_id.name or '', 'prioridad': cuenta.captura_prioridad or '',
                       'periodicidad': self._etiqueta(cuenta, 'periodicidad', cuenta.periodicidad)},
            'origen': mora.source_type or (captura.source_type if captura else False) or False,
            'origen_label': self._etiqueta(Mora, 'source_type', mora.source_type) if mora else '',
            'cuotas': [{'nombre': q.name or '', 'fecha': fields.Date.to_string(q.fecha_cronograma),
                        'dias': (hoy - q.fecha_cronograma).days, 'monto': q.monto, 'saldo': q.saldo} for q in cuotas],
            'cuotas_total': sum(cuotas.mapped('saldo')),
            'papeletas': [self._cap_papeleta(p) for p in papeletas],
            'papeletas_total': sum(p.deuda or p.importe or 0.0 for p in papeletas if p.estado_pago == 'pendiente'),
            'alertas': alertas,
            'captura': self._cap_detalle(captura) if captura else None,
            'paso': self._cap_paso(captura),
            'historial': [{'id': h.id, 'numero': h.name, 'estado': self._etiqueta(h, 'state', h.state),
                           'fecha': fields.Date.to_string(self._cap_fecha(h.create_date))} for h in historial],
            'permisos': {
                'capturar': Captura.check_access_rights('create', raise_exception=False),
                'supervisor': supervisor,
            },
            'opciones': {
                'monto_intervencion': MONTO_INTERVENCION,
                'hoy': fields.Date.to_string(hoy),
                'liberacion': Captura._fields['liberacion_tipo']._description_selection(self.env),
                'retencion': Captura._fields['retention_reason']._description_selection(self.env),
            },
        }

    def _cap_paso(self, captura):
        if not captura:
            return 'capturar'
        if captura.state == 'capturado':
            return 'cobrar' if captura.payment_state == 'pendiente' else 'decidir'
        if captura.state == 'disolucion_contrato':
            return 'recolocar'
        return 'cerrada'

    def _cap_documentos(self, c):
        """Lo que se subió a la captura, por el paso en que se subió: la captura (evidencias
        y lo adjuntado desde el chatter), el cobro (voucher), la decisión (apelaciones) y la
        recolocación (desafiliación y entrega)."""
        otros = self.env['ir.attachment'].search([
            ('res_model', '=', c._name), ('res_id', '=', c.id), ('res_field', '=', False),
            ('id', 'not in', c.evidencia_archivos.ids)])
        apelaciones = c.appeal_ids if 'appeal_ids' in c._fields else []
        docs = {
            'capturar': self._evidencias(c.evidencia_archivos) + self._evidencias(otros),
            'cobrar': [self._archivo_campo(c, 'voucher_file', c.voucher_filename or 'Voucher de pago')],
            'decidir': [self._archivo_campo(a, 'appeal_evidence', a.appeal_reason or 'Apelación') for a in apelaciones],
            'recolocar': [self._archivo_campo(c, 'documento_desafiliacion', 'Documento de desafiliación'),
                          self._archivo_campo(c, 'evidencia_entrega', 'Evidencia de la entrega')],
        }
        return {paso: [d for d in archivos if d] for paso, archivos in docs.items()}

    def _cap_detalle(self, c):
        return {
            'id': c.id, 'numero': c.name, 'state': c.state, 'estado': self._etiqueta(c, 'state', c.state),
            'tipo': c.capture_type, 'tipo_label': self._etiqueta(c, 'capture_type', c.capture_type),
            'compromiso': fields.Date.to_string(c.commitment_date) if c.commitment_date else False,
            'fecha': fields.Date.to_string(self._cap_fecha(c.create_date)),
            'capturador': c.capturador_id.name or '', 'supervisor': c.supervisor_id.name or '',
            'recogida': c.moto_recogida, 'motivo_no_recogida': c.motivo_no_recogida or '',
            'comentarios': c.comentarios_captura or '',
            'intervencion': c.intervention_fee, 'pagado': c.payment_state == 'pagado', 'pagar_monto': c.pagar_monto,
            'fecha_pago': fields.Date.to_string(c.payment_date) if c.payment_date else False,
            'voucher': c.voucher_number or '', 'motivo_no_pago': c.motivo_no_pago or '',
            'liberacion': self._etiqueta(c, 'liberacion_tipo', c.liberacion_tipo),
            'observaciones': c.observaciones or '',
            'retencion': self._etiqueta(c, 'retention_reason', c.retention_reason),
            'fecha_retencion': fields.Date.to_string(c.retention_date) if c.retention_date else False,
            'notas_retencion': c.notes or '',
            'evidencias': len(c.evidencia_archivos),
            'documentos': self._cap_documentos(c),
            'papeletas_sat': c.papeletas_sat_pendientes, 'deuda_sat': c.deuda_sat,
        }

    # ------------------------------------------------------------------
    # Acciones de cada paso
    # ------------------------------------------------------------------

    @api.model
    def captura_registrar(self, cuenta_id, datos):
        """Paso 1: registra la captura de la cuenta."""
        _mora, Captura = self._cap_modelos()
        if Captura is None:
            raise UserError(_('El módulo de capturas no está disponible.'))
        cuenta = self.env['adt.comercial.cuentas'].browse(int(cuenta_id or 0)).exists()
        if not cuenta:
            raise UserError(_('La cuenta ya no existe.'))
        if Captura.search_count([('cuenta_id', '=', cuenta.id), ('state', 'in', ('capturado', 'disolucion_contrato'))]):
            raise UserError(_('Esta cuenta ya tiene una captura activa.'))
        tipo = datos.get('tipo') if datos.get('tipo') in ('inmediata', 'compromiso') else 'inmediata'
        recogida = bool(datos.get('recogida'))
        if not recogida and not (datos.get('motivo_no_recogida') or '').strip():
            raise ValidationError(_('Indique por qué no se recogió la moto.'))
        try:
            monto = float(datos.get('monto') or 0.0)
        except (TypeError, ValueError):
            raise ValidationError(_('El monto de la intervención no es válido.'))
        if monto < 0:
            raise ValidationError(_('El monto de la intervención no puede ser negativo.'))
        archivos = [self._cap_archivo(a) for a in (datos.get('evidencias') or [])]
        captura = Captura.create({
            'partner_id': cuenta.partner_id.id,
            'cuenta_id': cuenta.id,
            'capture_type': tipo,
            'commitment_date': datos.get('compromiso') if tipo == 'compromiso' else False,
            'intervention_fee': monto,
            'moto_recogida': recogida,
            'motivo_no_recogida': False if recogida else datos.get('motivo_no_recogida'),
            'comentarios_captura': datos.get('comentarios') or False,
        })
        # Tal como se subieron (sin el redimensionado de imágenes de Odoo).
        adjuntos = self.env['ir.attachment'].with_context(image_no_postprocess=True).create([{
            'name': a['nombre'], 'datas': a['datos'], 'res_model': captura._name, 'res_id': captura.id,
        } for a in archivos if a])
        if adjuntos:
            captura.evidencia_archivos = [(6, 0, adjuntos.ids)]
        return {'captura_id': captura.id}

    @api.model
    def captura_cobrar(self, captura_id, datos):
        """Paso 2: pago de la intervención (o exoneración con su motivo)."""
        captura = self._cap_registro(captura_id)
        pagar = bool(datos.get('pagar', True))
        voucher = self._cap_archivo(datos.get('voucher'), obligatorio=pagar, etiqueta=_('el voucher de pago'))
        try:
            monto = float(datos.get('monto') or 0.0)
        except (TypeError, ValueError):
            raise ValidationError(_('El monto no es válido.'))
        captura.registrar_pago_intervencion(
            monto, datos.get('fecha'), voucher_number=(datos.get('voucher_numero') or '').strip(),
            voucher_file=voucher and voucher['datos'], voucher_filename=voucher and voucher['nombre'],
            pagar_monto=pagar, motivo_no_pago=datos.get('motivo'))
        return True

    @api.model
    def captura_liberar(self, captura_id, tipo, observaciones=None):
        """Paso 3: el supervisor libera el vehículo."""
        self._cap_registro(captura_id).liberar_vehiculo(tipo, observaciones or False)
        return True

    @api.model
    def captura_disolucion(self, captura_id, motivo, fecha, notas=None):
        """Paso 3: el supervisor retiene el vehículo e inicia la disolución del contrato."""
        self._cap_registro(captura_id).iniciar_disolucion(motivo, fecha, notas or False)
        return True

    @api.model
    def captura_recolocar(self, captura_id, documento, evidencia):
        """Paso 4: recoloca el vehículo (cancela la cuenta)."""
        doc = self._cap_archivo(documento, obligatorio=True, etiqueta=_('el documento de desafiliación'))
        evi = self._cap_archivo(evidencia, obligatorio=True, etiqueta=_('la evidencia de la entrega'))
        self._cap_registro(captura_id).recolocar_vehiculo(doc['datos'], evi['datos'])
        return True

    @api.model
    def captura_cancelar(self, captura_id):
        self._cap_registro(captura_id).action_cancelar()
        return True

    @api.model
    def captura_prioridad(self, cuenta_id, prioridad):
        cuenta = self.env['adt.comercial.cuentas'].browse(int(cuenta_id or 0)).exists()
        if not cuenta:
            raise UserError(_('La cuenta ya no existe.'))
        cuenta.captura_prioridad = prioridad if prioridad in ('normal', 'urgente') else False
        return True
