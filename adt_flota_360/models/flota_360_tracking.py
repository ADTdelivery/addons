# -*- coding: utf-8 -*-
"""Tracking de motos en una sola vista (acción JS: adt_flota_360_tracking).

* Indicadores: motos en cada etapa logística (Gambeta, Base, Fibra por taller y
  Base con fibra) y el estado de su placa.
* Tablero por etapa: cada tarjeta avanza la logística y también inicia el trámite
  de placa, sin cambiar de pantalla.
* Detalle de la moto (drawer): los dos flujos en paralelo (logística y placa),
  cada uno con su paso actual y su acción, más el historial.
* Configuración (drawer): etapas, talleres de fibra y parámetros de placa.

Las reglas (validaciones, saltos de etapa, historial, sincronización con el
trámite) son las de adt_tracking_moto y adt_tramite_placa; aquí solo se arman
los datos de la vista y se llaman sus métodos. Ambos módulos son opcionales.
"""
import base64

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .flota_360 import placa_valida

GRUPO_TRK_MANAGER = 'adt_tracking_moto.group_tracking_manager'
GRUPO_FLOTA_MANAGER = 'fleet.fleet_group_manager'
PARAM_DIAS_FINALIZADO = 'adt_tramite_placa.dias_finalizado'
ORDEN_ETAPAS = ('recojo', 'almacen', 'fibra', 'listo')
FECHA_ETAPA = {'recojo': 'fecha_recojo', 'almacen': 'fecha_ingreso_almacen',
               'fibra': 'fecha_envio_fibra', 'listo': 'fecha_listo'}
ICONO_ETAPA = {'recojo': 'fa-truck', 'almacen': 'fa-home', 'fibra': 'fa-wrench', 'listo': 'fa-check-square-o'}
# Verbo del botón que lleva la moto a esa etapa.
VERBO_ETAPA = {'recojo': 'Volver a %s', 'almacen': 'Llegó a %s', 'fibra': 'Enviar a %s', 'listo': 'Regresó a %s'}
NIVEL_PLACA = {'pendiente': 'neutral', 'en_tramite': 'info', 'observado': 'atencion', 'finalizado': 'ok'}
MAX_TARJETAS = 800
MAX_ARCHIVO = 10 * 1024 * 1024


class AdtFlota360Tracking(models.AbstractModel):
    _inherit = 'adt.flota360'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _trk_modelos(self):
        Tracking = self._modelo('adt.moto.tracking', 'etapa_id', 'estado_placa', 'taller_fibra_id')
        Tramite = self._modelo('adt.tramite.placa', 'vehicle_id', 'state')
        return Tracking, Tramite

    def _trk_manager(self):
        return self.env.user.has_group(GRUPO_TRK_MANAGER)

    def _trk_registro(self, tracking_id):
        Tracking, _tramite = self._trk_modelos()
        if Tracking is None:
            raise UserError(_('El tracking de motos no está disponible.'))
        tracking = Tracking.browse(int(tracking_id or 0)).exists()
        if not tracking:
            raise UserError(_('El tracking ya no existe.'))
        return tracking

    def _trk_solo_manager(self):
        if not self._trk_manager():
            raise AccessError(_('Solo un administrador del tracking puede cambiar la configuración.'))

    def _trk_fecha(self, dt):
        """Datetime de Odoo en hora local, 'YYYY-MM-DD HH:MM'."""
        return fields.Datetime.to_string(fields.Datetime.context_timestamp(self, dt))[:16] if dt else False

    def _trk_dias(self, inicio, fin=None):
        if not inicio:
            return 0.0
        return round(((fin or fields.Datetime.now()) - inicio).total_seconds() / 86400, 1)

    def _trk_etapas(self):
        etapas = self.env['adt.moto.tracking.etapa'].search([])
        return sorted(etapas, key=lambda e: ORDEN_ETAPAS.index(e.codigo) if e.codigo in ORDEN_ETAPAS else 99)

    def _trk_siguiente(self, tracking, etapas):
        """Siguiente etapa logística (o None si ya está en la última)."""
        codigo = tracking.etapa_codigo
        if codigo not in ORDEN_ETAPAS or codigo == ORDEN_ETAPAS[-1]:
            return None
        sig = ORDEN_ETAPAS[ORDEN_ETAPAS.index(codigo) + 1]
        etapa = next((e for e in etapas if e.codigo == sig), None)
        if not etapa:
            return None
        return {'codigo': sig, 'etapa_id': etapa.id, 'label': VERBO_ETAPA[sig] % etapa.name,
                'icon': ICONO_ETAPA[sig], 'requiere_taller': sig == 'fibra'}

    def _trk_placa_accion(self, estado):
        """Acción principal de la placa para la tarjeta del tablero."""
        return {
            'pendiente': {'accion': 'iniciar', 'label': 'Iniciar trámite de placa', 'icon': 'fa-play'},
            'observado': {'accion': 'levantar', 'label': 'Levantar observación', 'icon': 'fa-undo'},
        }.get(estado)

    def _trk_archivo(self, archivo):
        if not archivo or not archivo.get('datos'):
            return None
        datos = archivo['datos'].split(',', 1)[-1]
        try:
            tamano = len(base64.b64decode(datos, validate=True))
        except Exception:
            raise ValidationError(_('El archivo %s no es válido.') % (archivo.get('nombre') or ''))
        if tamano > MAX_ARCHIVO:
            raise ValidationError(_('El archivo %s supera los 10 MB.') % (archivo.get('nombre') or ''))
        return {'nombre': archivo.get('nombre') or 'archivo', 'datos': datos}

    # ------------------------------------------------------------------
    # Tablero: indicadores y tarjetas
    # ------------------------------------------------------------------

    @api.model
    def tracking_tablero(self, buscar=None, taller_id=None, placa=None, demorados=False, cliente=None):
        Tracking, Tramite = self._trk_modelos()
        if Tracking is None:
            return {'disponible': False}
        etapas = self._trk_etapas()
        talleres = self.env['adt.moto.tracking.taller'].search([])
        abiertos = Tracking.search([('estado_global', '!=', 'entregado')], order='fecha_etapa asc, id asc')

        # Indicadores: sobre todas las motos abiertas (sin filtros).
        kpis = {e.codigo: {'n': 0, 'demorados': 0, 'con_cliente': 0} for e in etapas}
        por_taller = {t.id: {'n': 0, 'demorados': 0} for t in talleres}
        sin_taller = {'n': 0, 'demorados': 0}
        placas = {k: 0 for k in NIVEL_PLACA}
        for t in abiertos:
            k = kpis.setdefault(t.etapa_codigo, {'n': 0, 'demorados': 0, 'con_cliente': 0})
            k['n'] += 1
            k['demorados'] += int(t.demorado)
            k['con_cliente'] += int(bool(t.partner_id))
            if t.etapa_codigo == 'fibra':
                destino = por_taller.setdefault(t.taller_fibra_id.id, {'n': 0, 'demorados': 0}) \
                    if t.taller_fibra_id else sin_taller
                destino['n'] += 1
                destino['demorados'] += int(t.demorado)
            placas[t.estado_placa] = placas.get(t.estado_placa, 0) + 1

        # Tarjetas: con los filtros.
        buscar = (buscar or '').strip().lower()
        filas = abiertos
        if taller_id:
            filas = filas.filtered(lambda t: t.etapa_codigo == 'fibra' and t.taller_fibra_id.id == int(taller_id))
        if placa in NIVEL_PLACA:
            filas = filas.filtered(lambda t: t.estado_placa == placa)
        if demorados:
            filas = filas.filtered('demorado')
        if cliente == 'con':
            filas = filas.filtered('partner_id')
        elif cliente == 'sin':
            filas = filas.filtered(lambda t: not t.partner_id)
        if buscar:
            filas = filas.filtered(lambda t: buscar in ' '.join(filter(None, [
                t.name, t.vehicle_id.name, t.vehicle_id.vin_sn, t.vehicle_id.license_plate,
                t.vehicle_id.x_motor_sn if 'x_motor_sn' in t.vehicle_id._fields else '',
                t.modelo_id.name, t.partner_id.name, t.partner_id.vat, t.taller_fibra_id.name,
                t.factura_id.sudo().name if t.factura_id else '',
            ])).lower())

        recortado = len(filas) > MAX_TARJETAS
        tarjetas = [self._trk_tarjeta(t, etapas) for t in filas[:MAX_TARJETAS]]
        total = len(abiertos)
        return {
            'disponible': True,
            'manager': self._trk_manager(),
            'placa_disponible': Tramite is not None,
            'total': total,
            'demorados': sum(k['demorados'] for k in kpis.values()),
            'etapas': [{
                'id': e.id, 'codigo': e.codigo, 'nombre': e.name, 'descripcion': e.descripcion or '',
                'icon': ICONO_ETAPA.get(e.codigo, 'fa-circle-o'), 'sla_horas': e.sla_horas,
                'n': kpis.get(e.codigo, {}).get('n', 0),
                'demorados': kpis.get(e.codigo, {}).get('demorados', 0),
                'con_cliente': kpis.get(e.codigo, {}).get('con_cliente', 0),
            } for e in etapas],
            'talleres': [{
                'id': t.id, 'nombre': t.name, 'codigo': t.codigo or '',
                'n': por_taller.get(t.id, {}).get('n', 0), 'demorados': por_taller.get(t.id, {}).get('demorados', 0),
            } for t in talleres] + ([{'id': False, 'nombre': 'Sin taller', 'codigo': '', **sin_taller}]
                                    if sin_taller['n'] else []),
            'placas': [{'estado': k, 'label': self._etiqueta(Tracking, 'estado_placa', k), 'n': placas.get(k, 0),
                        'nivel': n} for k, n in NIVEL_PLACA.items()],
            'items': tarjetas,
            'recortado': recortado,
            'limite': MAX_TARJETAS,
        }

    def _trk_tarjeta(self, t, etapas):
        v = t.vehicle_id
        sla = t._sla_horas()
        return {
            'id': t.id, 'ref': t.name, 'vehicle_id': v.id,
            'modelo': t.modelo_id.name or v.name or '', 'marca': v.model_id.brand_id.name or '',
            'chasis': v.vin_sn or '', 'color': v.color or '',
            'placa': v.license_plate if placa_valida(v.license_plate) else '',
            'cliente': t.partner_id.display_name or '',
            'etapa': t.etapa_codigo, 'etapa_nombre': t.etapa_id.name,
            'taller': t.taller_fibra_id.codigo or t.taller_fibra_id.name or '',
            'taller_id': t.taller_fibra_id.id or False,
            'taller_nombre': t.taller_fibra_id.name or '',
            'dias_etapa': round(t.dias_etapa or 0, 1), 'dias_totales': round(t.dias_totales or 0, 1),
            'sla_dias': round(sla / 24, 1) if sla else 0,
            'demorado': t.demorado, 'antes_de_tiempo': t.asignado_antes_listo,
            'estado_placa': t.estado_placa,
            'estado_placa_label': self._etiqueta(t, 'estado_placa', t.estado_placa),
            'nivel_placa': NIVEL_PLACA.get(t.estado_placa, 'neutral'),
            'observaciones': t.cant_observaciones or 0,
            'estado': self._etiqueta(t, 'estado_global', t.estado_global), 'estado_global': t.estado_global,
            'siguiente': self._trk_siguiente(t, etapas),
            'accion_placa': self._trk_placa_accion(t.estado_placa),
        }

    # ------------------------------------------------------------------
    # Detalle de una moto
    # ------------------------------------------------------------------

    @api.model
    def tracking_caso(self, tracking_id):
        t = self._trk_registro(tracking_id)
        _tracking, Tramite = self._trk_modelos()
        etapas = self._trk_etapas()
        v = t.vehicle_id
        manager = self._trk_manager()
        puede_editar = t.check_access_rights('write', raise_exception=False)

        # Duración de cada etapa: la última vez que pasó por ella (líneas del historial).
        logs = t.log_ids.sorted(lambda l: (l.fecha_inicio, l.id))
        por_codigo = {}
        for log in logs.filtered(lambda l: l.flujo == 'logistica'):
            por_codigo[log.codigo_hasta] = log
        actual = ORDEN_ETAPAS.index(t.etapa_codigo) if t.etapa_codigo in ORDEN_ETAPAS else 0
        pasos = []
        for e in etapas:
            i = ORDEN_ETAPAS.index(e.codigo) if e.codigo in ORDEN_ETAPAS else 0
            log = por_codigo.get(e.codigo)
            estado = 'hecho' if i < actual else ('actual' if i == actual else 'pendiente')
            fecha = t[FECHA_ETAPA[e.codigo]] if e.codigo in FECHA_ETAPA else False
            pasos.append({
                'codigo': e.codigo, 'nombre': e.name, 'descripcion': e.descripcion or '',
                'icon': ICONO_ETAPA.get(e.codigo, 'fa-circle-o'), 'estado': estado,
                'fecha': self._trk_fecha(fecha) if estado != 'pendiente' else False,
                'dias': self._trk_dias(log.fecha_inicio, log.fecha_fin) if log and estado == 'hecho' else (
                    round(t.dias_etapa or 0, 1) if estado == 'actual' else 0),
                'usuario': log.user_id.name if log and estado != 'pendiente' else '',
                'taller': (log.taller_fibra_id.name if log and log.taller_fibra_id else t.taller_fibra_id.name or '')
                if e.codigo == 'fibra' and estado != 'pendiente' else '',
            })

        sla = t._sla_horas()
        tramite = t.tramite_placa_id
        if not tramite and Tramite is not None:
            tramite = Tramite.search([('vehicle_id', '=', v.id)], limit=1)
        return {
            'id': t.id, 'ref': t.name, 'vehicle_id': v.id,
            'estado': self._etiqueta(t, 'estado_global', t.estado_global), 'estado_global': t.estado_global,
            'demorado': t.demorado,
            'moto': {
                'nombre': v.display_name or '', 'modelo': t.modelo_id.name or '', 'marca': v.model_id.brand_id.name or '',
                'chasis': v.vin_sn or '', 'motor': v.x_motor_sn if 'x_motor_sn' in v._fields else '',
                'color': v.color or '', 'anio': v.model_year if 'model_year' in v._fields else '',
                'placa': v.license_plate if placa_valida(v.license_plate) else '',
                # La factura se lee con sudo: el usuario del tracking no siempre tiene Contabilidad.
                'factura': t.factura_id.sudo().name if t.factura_id else '',
                'proveedor': t.factura_id.sudo().partner_id.display_name if t.factura_id else '',
            },
            'cliente': {
                'nombre': t.partner_id.display_name or '', 'documento': t.partner_id.vat or '',
                'telefono': t.partner_id.mobile or t.partner_id.phone or '',
                'asignacion': self._trk_fecha(t.fecha_asignacion), 'antes_de_tiempo': t.asignado_antes_listo,
                'entrega': fields.Date.to_string(t.fecha_entrega) if t.fecha_entrega else False,
            },
            'logistica': {
                'etapa': t.etapa_codigo, 'etapa_nombre': t.etapa_id.name, 'pasos': pasos,
                'dias_etapa': round(t.dias_etapa or 0, 1), 'dias_totales': round(t.dias_totales or 0, 1),
                'sla_dias': round(sla / 24, 1) if sla else 0,
                'taller_id': t.taller_fibra_id.id or False, 'taller': t.taller_fibra_id.name or '',
                'siguiente': self._trk_siguiente(t, etapas),
                'cerrado': t.estado_global == 'entregado',
            },
            'placa': self._trk_placa_detalle(t, tramite),
            'historial': [{
                'fecha': self._trk_fecha(l.fecha_inicio), 'flujo': l.flujo,
                'flujo_label': self._etiqueta(l, 'flujo', l.flujo),
                'desde': l.etapa_desde or '', 'hasta': l.etapa_hasta or '',
                'taller': l.taller_fibra_id.name or '', 'dias': round(l.duracion_dias or 0, 1),
                'abierta': not l.fecha_fin and l.flujo != 'hito', 'usuario': l.user_id.name or '', 'nota': l.nota or '',
            } for l in reversed(logs)],
            'opciones': {
                'talleres': [{'id': x.id, 'nombre': x.name, 'codigo': x.codigo or '', 'direccion': x.direccion or '',
                              'sla_dias': round(x.sla_horas / 24, 1) if x.sla_horas else 0}
                             for x in self.env['adt.moto.tracking.taller'].search([])],
                'etapas': [{'id': e.id, 'codigo': e.codigo, 'nombre': e.name} for e in etapas],
            },
            'permisos': {'editar': puede_editar, 'manager': manager,
                         'reabrir_placa': manager or self.env.user.has_group(GRUPO_FLOTA_MANAGER)},
        }

    def _trk_placa_detalle(self, t, tramite):
        base = {
            'disponible': tramite is not None, 'estado': t.estado_placa,
            'estado_label': self._etiqueta(t, 'estado_placa', t.estado_placa),
            'nivel': NIVEL_PLACA.get(t.estado_placa, 'neutral'),
            'placa': t.vehicle_id.license_plate if placa_valida(t.vehicle_id.license_plate) else '',
            'tramite': None,
        }
        if tramite:
            base['tramite'] = {
                'id': tramite.id, 'ref': tramite.name, 'state': tramite.state,
                'state_label': self._etiqueta(tramite, 'state', tramite.state),
                'inicio': self._trk_fecha(tramite.fecha_inicio), 'fin': self._trk_fecha(tramite.fecha_fin),
                'ultima_observacion': self._trk_fecha(tramite.fecha_ultima_observacion),
                'dias_tramite': round(tramite.dias_tramite or 0, 1),
                'dias_sin_iniciar': round(tramite.dias_sin_iniciar or 0, 1),
                'num_placa': tramite.num_placa or '', 'motivo': tramite.motivo_observacion or '',
                'observaciones': tramite.cant_observaciones or 0, 'notas': tramite.notas or '',
                'tarjeta': self._archivo_campo(tramite, 'tarjeta_propiedad',
                                               tramite.tarjeta_propiedad_filename or 'Tarjeta de propiedad'),
            }
        return base

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    @api.model
    def tracking_mover(self, tracking_id, etapa_id, taller_id=None):
        """Lleva la moto a otra etapa. Fibra exige taller. Las reglas de salto
        (solo a la siguiente, salvo administradores) son las del tracking."""
        t = self._trk_registro(tracking_id)
        etapa = self.env['adt.moto.tracking.etapa'].browse(int(etapa_id or 0)).exists()
        if not etapa:
            raise UserError(_('La etapa ya no existe.'))
        vals = {'etapa_id': etapa.id}
        if etapa.codigo == 'fibra':
            taller = self.env['adt.moto.tracking.taller'].browse(int(taller_id or 0)).exists()
            if not taller:
                raise ValidationError(_('Elige el taller de fibra.'))
            vals['taller_fibra_id'] = taller.id
        t.write(vals)
        return True

    @api.model
    def tracking_placa(self, tracking_id, accion, datos=None):
        """Paso del trámite de placa desde la tarjeta o el detalle de la moto."""
        datos = datos or {}
        t = self._trk_registro(tracking_id)
        _tracking, Tramite = self._trk_modelos()
        if Tramite is None:
            raise UserError(_('El trámite de placa no está disponible.'))
        if accion == 'iniciar':
            t.action_iniciar_tramite()
            return True
        tramite = t.tramite_placa_id or Tramite.search([('vehicle_id', '=', t.vehicle_id.id)], limit=1)
        if not tramite:
            raise UserError(_('La moto aún no tiene trámite de placa: inícialo primero.'))
        if accion == 'observar':
            motivo = (datos.get('motivo') or '').strip()
            if not motivo:
                raise ValidationError(_('Indica el motivo de la observación.'))
            tramite._observar(motivo)
        elif accion == 'levantar':
            tramite.action_levantar_observacion()
        elif accion == 'finalizar':
            num = (datos.get('num_placa') or '').strip().upper()
            if not num:
                raise ValidationError(_('Ingresa el N° de placa.'))
            vals = {'num_placa': num}
            tarjeta = self._trk_archivo(datos.get('tarjeta'))
            if tarjeta:
                vals.update(tarjeta_propiedad=tarjeta['datos'], tarjeta_propiedad_filename=tarjeta['nombre'])
            if (datos.get('notas') or '').strip():
                vals['notas'] = datos['notas'].strip()
            tramite.write(vals)
            tramite.action_finalizar()
        elif accion == 'reabrir':
            if not (self._trk_manager() or self.env.user.has_group(GRUPO_FLOTA_MANAGER)):
                raise AccessError(_('Solo un administrador puede reabrir el trámite de placa.'))
            tramite.action_reabrir()
        else:
            raise UserError(_('Acción no válida.'))
        return True

    # ------------------------------------------------------------------
    # Configuración: etapas, talleres de fibra y parámetros de placa
    # ------------------------------------------------------------------

    @api.model
    def tracking_config(self):
        Tracking, Tramite = self._trk_modelos()
        if Tracking is None:
            raise UserError(_('El tracking de motos no está disponible.'))
        Taller = self.env['adt.moto.tracking.taller'].with_context(active_test=False)
        en_taller = {g['taller_fibra_id'][0]: g['taller_fibra_id_count'] for g in Tracking.read_group(
            [('etapa_codigo', '=', 'fibra'), ('estado_global', '!=', 'entregado'), ('taller_fibra_id', '!=', False)],
            ['taller_fibra_id'], ['taller_fibra_id'])}
        return {
            'manager': self._trk_manager(),
            'etapas': [{'id': e.id, 'codigo': e.codigo, 'nombre': e.name, 'descripcion': e.descripcion or '',
                        'sla_horas': e.sla_horas, 'icon': ICONO_ETAPA.get(e.codigo, 'fa-circle-o')}
                       for e in self._trk_etapas()],
            'talleres': [{'id': x.id, 'nombre': x.name, 'codigo': x.codigo or '', 'direccion': x.direccion or '',
                          'sla_horas': x.sla_horas, 'activo': x.active, 'motos': en_taller.get(x.id, 0)}
                         for x in Taller.search([], order='active desc, sequence, name')],
            'placa': {'disponible': Tramite is not None,
                      'dias_finalizado': Tramite._dias_finalizado() if Tramite is not None else 0},
        }

    @api.model
    def tracking_config_etapa(self, etapa_id, datos):
        self._trk_solo_manager()
        etapa = self.env['adt.moto.tracking.etapa'].browse(int(etapa_id or 0)).exists()
        if not etapa:
            raise UserError(_('La etapa ya no existe.'))
        nombre = (datos.get('nombre') or '').strip()
        if not nombre:
            raise ValidationError(_('El nombre de la etapa es obligatorio.'))
        sla = self._trk_numero(datos.get('sla_horas'), _('El SLA'))
        etapa.write({'name': nombre, 'descripcion': (datos.get('descripcion') or '').strip() or False, 'sla_horas': sla})
        return True

    @api.model
    def tracking_config_taller(self, taller_id, datos):
        """Crea (sin taller_id) o modifica un taller de fibra."""
        self._trk_solo_manager()
        Taller = self.env['adt.moto.tracking.taller'].with_context(active_test=False)
        nombre = (datos.get('nombre') or '').strip()
        if not nombre:
            raise ValidationError(_('El nombre del taller es obligatorio.'))
        vals = {
            'name': nombre,
            'codigo': (datos.get('codigo') or '').strip().upper() or False,
            'direccion': (datos.get('direccion') or '').strip() or False,
            'sla_horas': self._trk_numero(datos.get('sla_horas'), _('El SLA')),
        }
        if 'activo' in datos:
            vals['active'] = bool(datos['activo'])
        if taller_id:
            taller = Taller.browse(int(taller_id)).exists()
            if not taller:
                raise UserError(_('El taller ya no existe.'))
            taller.write(vals)
        else:
            taller = Taller.create(vals)
        return {'id': taller.id}

    @api.model
    def tracking_config_placa(self, dias_finalizado):
        self._trk_solo_manager()
        _tracking, Tramite = self._trk_modelos()
        if Tramite is None:
            raise UserError(_('El trámite de placa no está disponible.'))
        try:
            dias = int(dias_finalizado)
        except (TypeError, ValueError):
            raise ValidationError(_('Los días deben ser un número entero.'))
        if dias < 0:
            raise ValidationError(_('Los días en Finalizado no pueden ser negativos.'))
        self.env['ir.config_parameter'].sudo().set_param(PARAM_DIAS_FINALIZADO, dias)
        return True

    def _trk_numero(self, valor, etiqueta):
        try:
            n = float(valor or 0)
        except (TypeError, ValueError):
            raise ValidationError(_('%s debe ser un número.') % etiqueta)
        if n < 0:
            raise ValidationError(_('%s no puede ser negativo.') % etiqueta)
        return n
