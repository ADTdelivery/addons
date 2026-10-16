# -*- coding: utf-8 -*-
"""Resumen de gerencia: 14 indicadores en 4 secciones, cada uno con su detalle.

Cada indicador se arma a partir de sus filas de detalle: el valor del resumen es
el conteo o la suma de esas mismas filas, así el número de la portada y la lista
que se abre al tocarlo siempre coinciden. Todas las filas llevan su financiera,
para seccionar el resumen y filtrar por financiera (0 = sin financiera).

Los montos de cartera salen de Cartera y financieras (cuentas en curso), igual que
en el dashboard. Los módulos de flota (trámite de placa, seguimiento de motos,
capturas) son opcionales: si no están instalados, el indicador sale con
"disponible": false.
"""
from collections import defaultdict

from odoo import api, fields, models

from .gerencia_indicadores import ESTADOS_COBRANZA, TRAMOS, paginar, placa_valida, soles

SECCIONES = [
    ('dinero', 'Dinero'),
    ('flota', 'Flota'),
    ('incidencias', 'Incidencias'),
    ('crecimiento', 'Crecimiento'),
]

ESTADOS_PLACA_TRAMITE = [('pendiente', 'Pendiente'), ('en_tramite', 'En trámite'), ('observado', 'Observado')]
ETAPAS_FIBRA = [('recojo', 'Recojo en distribuidor'), ('almacen', 'En almacén'),
                ('fibra', 'En taller de fibra'), ('listo', 'Listo para asignar')]
ESTADOS_EXPEDIENTE = [('por_revisar', 'Por revisar'), ('incompleto_expediente', 'Incompleto - Expediente'),
                      ('incompleto_fase_final', 'Incompleto - Fase final'), ('completo', 'Completo'),
                      ('aprobado_sin_desembolso', 'Aprobado sin desembolso'), ('rechazado', 'Rechazado')]
ESTADOS_VEHICULO = [('financiado', 'Con crédito en curso'), ('stock', 'Stock disponible'),
                    ('asignado', 'Asignado sin crédito en curso')]


def _sin_privados(fila):
    return {k: v for k, v in fila.items() if not k.startswith('_')}


def _texto(valor):
    return (valor or '').lower()


class _Contexto(object):
    """Datos compartidos por los indicadores; cada fuente se calcula una sola vez y solo si se usa."""

    def __init__(self, modelo):
        self.m = modelo
        self.hoy = modelo._hoy()
        self._cache = {}

    def _una_vez(self, clave, funcion):
        if clave not in self._cache:
            self._cache[clave] = funcion()
        return self._cache[clave]

    @property
    def cuentas(self):
        return self._una_vez('cuentas', lambda: self.m._cuentas(None))

    @property
    def financieras(self):
        return {f['id']: f['name'] for f in self.cuentas[1]}

    def nombre_financiera(self, fid):
        return self.financieras.get(fid or 0, 'Sin financiera')

    @property
    def vehiculo_cuenta(self):
        """Cuenta de cada moto: la que está en curso o, si no hay, la última pagada."""
        def calcular():
            mapa = {}
            for c in self.m.env['adt.comercial.cuentas'].sudo().search_read(
                    [('vehiculo_id', '!=', False), ('state', 'in', ('en_curso', 'pagado'))],
                    ['vehiculo_id', 'tipo_financiera_id', 'state', 'reference_no'], order='id desc'):
                vid = c['vehiculo_id'][0]
                if vid not in mapa or (c['state'] == 'en_curso' and mapa[vid]['state'] != 'en_curso'):
                    mapa[vid] = {'state': c['state'], 'referencia': c['reference_no'],
                                 'financiera_id': c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0}
            return mapa
        return self._una_vez('vehiculo_cuenta', calcular)

    def financiera_vehiculo(self, vehiculo_id):
        return self.vehiculo_cuenta.get(vehiculo_id, {}).get('financiera_id', 0)

    @property
    def cliente_financiera(self):
        """Financiera de la última cuenta de cada cliente (para los expedientes)."""
        def calcular():
            mapa = {}
            for c in self.m.env['adt.comercial.cuentas'].sudo().search_read(
                    [('partner_id', '!=', False), ('state', '!=', 'cancelado')],
                    ['partner_id', 'tipo_financiera_id'], order='id asc'):
                mapa[c['partner_id'][0]] = c['tipo_financiera_id'][0] if c['tipo_financiera_id'] else 0
            return mapa
        return self._una_vez('cliente_financiera', calcular)

    def con_financiera(self, fila, fid):
        fila['financiera_id'] = fid or 0
        fila['financiera'] = self.nombre_financiera(fid)
        return fila


class AdtGerenciaResumen(models.AbstractModel):
    _inherit = 'adt.gerencia.indicadores'

    # ------------------------------------------------------------------
    # Catálogo de indicadores
    # ------------------------------------------------------------------
    # valor: 'filas' (conteo), 'clientes' (clientes distintos) o el nombre de un campo en
    # céntimos (_c_...) que se suma. buscar: campos de texto para ?buscar=. filtro: campo de
    # la fila para ?filtro= y sus opciones (también son el desglose del resumen).

    def _catalogo(self):
        return [
            # Dinero
            {'clave': 'nos_deben_total', 'seccion': 'dinero', 'nombre': 'Nos deben los clientes',
             'descripcion': 'Saldo por cobrar de las cuentas en curso (vencido y por vencer).',
             'tipo': 'soles', 'valor': '_c_por_cobrar', 'filas': self._f_nos_deben_total,
             'buscar': ('cliente', 'documento', 'placa', 'referencia'), 'orden': lambda f: -f['_c_por_cobrar'],
             'secundario': ('_c_vencido', 'Vencido', 'soles')},
            {'clave': 'deuda_vencida', 'seccion': 'dinero', 'nombre': 'Deuda vencida',
             'descripcion': 'Cuotas cuya fecha ya pasó y siguen sin pagar.',
             'tipo': 'soles', 'valor': '_c_vencido', 'filas': self._f_deuda_vencida,
             'buscar': ('cliente', 'documento', 'placa', 'referencia'),
             'orden': lambda f: (-f['_c_vencido'], -f['dias_atraso']),
             'filtro': ('tramo', TRAMOS), 'secundario': ('filas', 'Cuentas', 'entero')},
            {'clave': 'clientes_deben', 'seccion': 'dinero', 'nombre': 'Clientes que nos deben',
             'descripcion': 'Clientes con al menos una cuota vencida.',
             'tipo': 'entero', 'valor': 'clientes', 'filas': self._f_clientes_deben,
             'buscar': ('cliente', 'documento', 'placas'), 'orden': lambda f: (-f['_c_vencido'], -f['dias_atraso']),
             'filtro': ('tramo', TRAMOS), 'secundario': ('_c_vencido', 'Vencido', 'soles')},
            {'clave': 'debemos_financiera', 'seccion': 'dinero', 'nombre': 'Debemos a las financieras',
             'descripcion': 'Saldo pendiente con las financieras por las cuentas en curso.',
             'tipo': 'soles', 'valor': '_c_deuda', 'filas': self._f_debemos_financiera,
             'buscar': ('cliente', 'documento', 'placa', 'referencia'), 'orden': lambda f: -f['_c_deuda']},
            {'clave': 'ganancia', 'seccion': 'dinero', 'nombre': 'Ganancia (posición neta)',
             'descripcion': 'Lo que nos deben los clientes menos lo que debemos a las financieras.',
             'tipo': 'soles', 'valor': '_c_posicion', 'filas': self._f_ganancia,
             'buscar': ('cliente', 'documento', 'placa', 'referencia'), 'orden': lambda f: -f['_c_posicion']},
            # Flota
            {'clave': 'flota_total', 'seccion': 'flota', 'nombre': 'Flota total',
             'descripcion': 'Todas las motos activas registradas.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_flota_total,
             'buscar': ('placa', 'modelo', 'cliente', 'chasis'), 'orden': lambda f: (f['estado'], f['placa'] or ''),
             'filtro': ('estado', ESTADOS_VEHICULO)},
            {'clave': 'stock', 'seccion': 'flota', 'nombre': 'Stock disponible',
             'descripcion': 'Motos sin cliente asignado.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_stock,
             'buscar': ('placa', 'modelo', 'chasis', 'color'), 'orden': lambda f: (f['modelo'] or '', f['placa'] or '')},
            {'clave': 'placas_tramite', 'seccion': 'flota', 'nombre': 'Placas en trámite',
             'descripcion': 'Motos cuya placa todavía no sale: pendientes, en trámite u observadas.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_placas_tramite, 'modelo': 'adt.tramite.placa',
             'buscar': ('referencia', 'chasis', 'modelo', 'cliente'), 'orden': lambda f: -(f['dias_tramite'] or 0),
             'filtro': ('estado', ESTADOS_PLACA_TRAMITE)},
            {'clave': 'ciclo_fibra', 'seccion': 'flota', 'nombre': 'Ciclo de fibra',
             'descripcion': 'Motos en el ciclo de fibra: recojo, almacén y taller de fibra. '
                            'El desglose incluye las que ya están listas para asignar.',
             'tipo': 'entero', 'valor': '_en_ciclo', 'filas': self._f_ciclo_fibra, 'modelo': 'adt.moto.tracking',
             'buscar': ('placa', 'chasis', 'modelo', 'taller', 'cliente'),
             'orden': lambda f: (dict((k, i) for i, (k, _l) in enumerate(ETAPAS_FIBRA)).get(f['etapa'], 9),
                                 -(f['dias_etapa'] or 0)),
             'filtro': ('etapa', ETAPAS_FIBRA), 'desglose_conteo': True,
             'secundario': ('_demorado', 'Demoradas', 'entero')},
            # Incidencias
            {'clave': 'papeletas_vencidas', 'seccion': 'incidencias', 'nombre': 'Papeletas vencidas sin pagar',
             'descripcion': 'Papeletas pendientes de pago cuya fecha de vencimiento ya pasó.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_papeletas_vencidas, 'modelo': 'adt.papeleta',
             'buscar': ('papeleta', 'placa', 'cliente'), 'orden': lambda f: -f['dias_vencida'],
             'secundario': ('_c_pendiente', 'Monto pendiente', 'soles')},
            {'clave': 'capturas', 'seccion': 'incidencias', 'nombre': 'Motos capturadas',
             'descripcion': 'Capturas activas: la moto está retenida.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_capturas, 'modelo': 'adt.captura.record',
             'buscar': ('captura', 'cliente', 'placa', 'referencia'), 'orden': lambda f: -(f['dias_capturada'] or 0)},
            {'clave': 'disoluciones', 'seccion': 'incidencias', 'nombre': 'Disoluciones de contrato',
             'descripcion': 'Capturas que pasaron a disolución de contrato.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_disoluciones, 'modelo': 'adt.captura.record',
             'buscar': ('captura', 'cliente', 'placa', 'referencia'), 'orden': lambda f: -(f['dias_capturada'] or 0)},
            # Crecimiento
            {'clave': 'candidatos', 'seccion': 'crecimiento', 'nombre': 'Candidatos a otro préstamo',
             'descripcion': 'Clientes listos para un nuevo préstamo según su historial de pago.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_candidatos,
             'buscar': ('nombre', 'documento'), 'orden': lambda f: (-f['puntaje'], f['nombre'] or ''),
             'secundario': ('_c_potencial', 'Colocación potencial', 'soles')},
            {'clave': 'expedientes_nuevos', 'seccion': 'crecimiento', 'nombre': 'Expedientes nuevos del mes',
             'descripcion': 'Expedientes creados este mes: clientes nuevos en proceso de adquirir su moto.',
             'tipo': 'entero', 'valor': 'filas', 'filas': self._f_expedientes_nuevos, 'modelo': 'adt.expediente',
             'buscar': ('cliente', 'documento', 'asesora'), 'orden': lambda f: (f['fecha'] or '', f['id']),
             'invertir': True, 'filtro': ('estado', ESTADOS_EXPEDIENTE)},
        ]

    # ------------------------------------------------------------------
    # Filas de cada indicador
    # ------------------------------------------------------------------

    def _fila_cuenta(self, ctx, f):
        return ctx.con_financiera({
            'cuenta_id': f['cuenta_id'], 'referencia': f['referencia'], 'cliente_id': f['cliente_id'],
            'cliente': f['cliente'], 'documento': f['documento'], 'telefono': f['telefono'], 'placa': f['placa'],
            'asesor': f['asesor'],
        }, f['financiera_id'])

    def _f_nos_deben_total(self, ctx):
        filas = []
        for f in ctx.cuentas[0]:
            if f['_por_cobrar'] <= 0:
                continue
            fila = self._fila_cuenta(ctx, f)
            fila.update({'por_cobrar': soles(f['_por_cobrar']), 'vencido': soles(f['_vencido']),
                         'por_vencer': soles(f['_vigente']), 'cuotas_restantes': f['cuotas_restantes'],
                         'fin_credito': f['fin_credito'],
                         '_c_por_cobrar': f['_por_cobrar'], '_c_vencido': f['_vencido']})
            filas.append(fila)
        return filas

    def _f_deuda_vencida(self, ctx):
        filas = []
        for f in ctx.cuentas[0]:
            if not f['_vencido']:
                continue
            fila = self._deudor(f)
            fila.update({'financiera_id': f['financiera_id'] or 0, 'tramo_nombre': dict(TRAMOS).get(fila['tramo'], ''),
                         '_c_vencido': f['_vencido']})
            filas.append(fila)
        return filas

    def _f_clientes_deben(self, ctx):
        grupos = defaultdict(list)
        for f in ctx.cuentas[0]:
            if f['_vencido']:
                grupos[(f['cliente_id'] or f['documento'], f['financiera_id'] or 0)].append(f)
        orden_tramo = [k for k, _l in TRAMOS]
        filas = []
        for (cliente, fid), cuentas in grupos.items():
            tramos = [next((k for k in reversed(orden_tramo) if c['_tramos'].get(k)), None) for c in cuentas]
            tramo = max((t for t in tramos if t), key=orden_tramo.index, default=None)
            vencido = sum(c['_vencido'] for c in cuentas)
            filas.append(ctx.con_financiera({
                'cliente_id': cuentas[0]['cliente_id'], 'cliente': cuentas[0]['cliente'],
                'documento': cuentas[0]['documento'], 'telefono': cuentas[0]['telefono'],
                'placas': ', '.join(sorted({c['placa'] for c in cuentas if c['placa']})),
                'cuentas': len(cuentas), 'vencido': soles(vencido),
                'mora_pendiente': soles(sum(c['_mora'] for c in cuentas)),
                'por_cobrar': soles(sum(c['_por_cobrar'] for c in cuentas)),
                'dias_atraso': max(c['dias_atraso'] for c in cuentas),
                'cuotas_vencidas': sum(c['cuotas_vencidas'] for c in cuentas),
                'tramo': tramo, 'tramo_nombre': dict(TRAMOS).get(tramo, ''),
                'estado_cobranza': max((c['estado_cobranza'] for c in cuentas),
                                       key=[k for k, _l in ESTADOS_COBRANZA].index),
                '_cliente': cliente, '_c_vencido': vencido,
            }, fid))
        for fila in filas:
            fila['estado_cobranza_nombre'] = dict(ESTADOS_COBRANZA).get(fila['estado_cobranza'], '')
        return filas

    def _f_debemos_financiera(self, ctx):
        filas = []
        for f in ctx.cuentas[0]:
            if f['_fin_pendiente'] <= 0:
                continue
            fila = self._fila_cuenta(ctx, f)
            fila.update({'deuda_financiera': soles(f['_fin_pendiente']),
                         'cancelar_hoy': soles(f['_fin_liquidar']) if f['_fin_liquidar'] is not None else None,
                         'fuente': f['_fin_fuente'], '_c_deuda': f['_fin_pendiente']})
            filas.append(fila)
        return filas

    def _f_ganancia(self, ctx):
        filas = []
        for f in ctx.cuentas[0]:
            fila = self._fila_cuenta(ctx, f)
            posicion = f['_por_cobrar'] - f['_fin_pendiente']
            fila.update({'nos_debe': soles(f['_por_cobrar']), 'debemos_financiera': soles(f['_fin_pendiente']),
                         'posicion_neta': soles(posicion), '_c_posicion': posicion})
            filas.append(fila)
        return filas

    def _vehiculos_filas(self, ctx, dominio):
        V = self.env['fleet.vehicle'].sudo()
        campos = ['license_plate', 'model_id', 'driver_id', 'vin_sn', 'color', 'state_id']
        tramites = {}
        if 'adt.tramite.placa' in self.env:
            tramites = {t['vehicle_id'][0]: t['state'] for t in self.env['adt.tramite.placa'].sudo().search_read(
                [('vehicle_id', '!=', False)], ['vehicle_id', 'state'])}
        etapas = {}
        if 'adt.moto.tracking' in self.env:
            etapas = {t['vehicle_id'][0]: t['etapa_codigo'] for t in self.env['adt.moto.tracking'].sudo().search_read(
                [('estado_global', '!=', 'entregado')], ['vehicle_id', 'etapa_codigo'])}
        filas = []
        for v in V.search_read(dominio, campos):
            cuenta = ctx.vehiculo_cuenta.get(v['id'], {})
            if cuenta.get('state') == 'en_curso':
                estado = 'financiado'
            elif not v['driver_id']:
                estado = 'stock'
            else:
                estado = 'asignado'
            tramite = tramites.get(v['id'])
            filas.append(ctx.con_financiera({
                'vehiculo_id': v['id'],
                'placa': v['license_plate'] if placa_valida(v['license_plate']) else None,
                'placa_lista': placa_valida(v['license_plate']) or tramite in ('finalizado', 'historial'),
                'tramite_placa': tramite,
                'etapa_fibra': etapas.get(v['id']),
                'modelo': v['model_id'][1] if v['model_id'] else '',
                'chasis': v['vin_sn'] or '', 'color': v['color'] or '',
                'cliente_id': v['driver_id'][0] if v['driver_id'] else None,
                'cliente': v['driver_id'][1] if v['driver_id'] else '',
                'cuenta': cuenta.get('referencia'),
                'estado': estado, 'estado_nombre': dict(ESTADOS_VEHICULO)[estado],
                'estado_flota': v['state_id'][1] if v['state_id'] else '',
            }, cuenta.get('financiera_id', 0)))
        return filas

    def _f_flota_total(self, ctx):
        return self._vehiculos_filas(ctx, [])

    def _f_stock(self, ctx):
        return [f for f in self._vehiculos_filas(ctx, [('driver_id', '=', False)]) if f['estado'] == 'stock']

    def _f_placas_tramite(self, ctx):
        filas = []
        for t in self.env['adt.tramite.placa'].sudo().search(
                [('state', 'in', [k for k, _l in ESTADOS_PLACA_TRAMITE])]):
            v = t.vehicle_id
            filas.append(ctx.con_financiera({
                'tramite_id': t.id, 'referencia': t.name, 'vehiculo_id': v.id,
                'chasis': t.chasis or '', 'modelo': t.modelo_id.name or '',
                'cliente': v.driver_id.name or '', 'estado': t.state,
                'estado_nombre': dict(ESTADOS_PLACA_TRAMITE).get(t.state, ''),
                'fecha_inicio': fields.Date.to_string(t.fecha_inicio.date()) if t.fecha_inicio else None,
                'dias_tramite': round(t.dias_tramite or 0, 1),
                'dias_sin_iniciar': round(t.dias_sin_iniciar or 0, 1) if t.state == 'pendiente' else None,
                'observaciones': t.cant_observaciones, 'motivo_observacion': t.motivo_observacion or '',
            }, ctx.financiera_vehiculo(v.id)))
        return filas

    def _f_ciclo_fibra(self, ctx):
        trackings = self.env['adt.moto.tracking'].sudo().search([
            ('estado_global', '!=', 'entregado'), '|',
            ('etapa_codigo', 'in', ('recojo', 'almacen', 'fibra')),
            '&', ('etapa_codigo', '=', 'listo'), ('partner_id', '=', False)])
        filas = []
        for t in trackings:
            v = t.vehicle_id
            filas.append(ctx.con_financiera({
                'tracking_id': t.id, 'vehiculo_id': v.id,
                'placa': t.license_plate if placa_valida(t.license_plate) else None,
                'chasis': t.chasis or '', 'modelo': t.modelo_id.name or '', 'color': t.color or '',
                'etapa': t.etapa_codigo, 'etapa_nombre': dict(ETAPAS_FIBRA).get(t.etapa_codigo, ''),
                'taller': t.taller_fibra_id.name or '',
                'fecha_envio_fibra': fields.Date.to_string(t.fecha_envio_fibra.date()) if t.fecha_envio_fibra else None,
                'dias_etapa': round(t.dias_etapa or 0, 1), 'dias_totales': round(t.dias_totales or 0, 1),
                'demorado': t.demorado, 'cliente': t.partner_id.name or '',
                '_en_ciclo': 1 if t.etapa_codigo != 'listo' else 0, '_demorado': 1 if t.demorado else 0,
            }, ctx.financiera_vehiculo(v.id)))
        return filas

    def _f_papeletas_vencidas(self, ctx):
        filas = []
        for p in self.env['adt.papeleta'].sudo().search(
                [('state', '=', 'pendiente'), ('fecha_vencimiento_final', '<', ctx.hoy)]):
            fraccionada = p.payment_method == 'fraccionado' and p.cuotas_ids
            pendientes = p.cuotas_ids.filtered(lambda c: c.state == 'pendiente') if fraccionada else None
            pendiente = sum(pendientes.mapped('amount')) if fraccionada else p.monto
            v = p.vehicle_id
            filas.append(ctx.con_financiera({
                'papeleta_id': p.id, 'papeleta': p.name, 'vehiculo_id': v.id,
                'placa': v.license_plate or '', 'cliente': v.driver_id.name or '',
                'fecha_papeleta': fields.Date.to_string(p.fecha_papeleta),
                'vencimiento': fields.Date.to_string(p.fecha_vencimiento_final),
                'dias_vencida': (ctx.hoy - p.fecha_vencimiento_final).days,
                'monto': round(p.monto, 2), 'pendiente': round(pendiente, 2),
                'fraccionada': bool(fraccionada),
                'cuotas_vencidas': len(pendientes.filtered(lambda c: c.due_date and c.due_date < ctx.hoy))
                if fraccionada else None,
                'capturada': p.capturado,
                '_c_pendiente': int(round(pendiente * 100)),
            }, ctx.financiera_vehiculo(v.id)))
        return filas

    def _capturas_filas(self, ctx, estado):
        filas = []
        for c in self.env['adt.captura.record'].sudo().search([('state', '=', estado)]):
            inicio = c.retention_date or (c.create_date and c.create_date.date())
            filas.append(ctx.con_financiera({
                'captura_id': c.id, 'captura': c.name, 'cuenta_id': c.cuenta_id.id,
                'referencia': c.cuenta_id.reference_no or '', 'cliente_id': c.partner_id.id,
                'cliente': c.partner_id.name or '', 'placa': c.vehicle_id.license_plate or '',
                'fecha': fields.Date.to_string(inicio) if inicio else None,
                'dias_capturada': (ctx.hoy - inicio).days if inicio else None,
                'dias_mora': c.dias_mora, 'cuotas_vencidas': c.numero_cuotas_vencidas,
                'monto_intervencion': round(c.intervention_fee or 0.0, 2),
                'pago_intervencion': c.payment_state,
                'capturador': c.capturador_id.name or '',
            }, c.cuenta_id.tipo_financiera_id.id))
        return filas

    def _f_capturas(self, ctx):
        return self._capturas_filas(ctx, 'capturado')

    def _f_disoluciones(self, ctx):
        return self._capturas_filas(ctx, 'disolucion_contrato')

    def _f_candidatos(self, ctx):
        filas = []
        for c in self._env_calculo()['adt.comercial.clientes.dashboard'].get_dashboard_data()['clientes']:
            if c['segmento'] != 'apto':
                continue
            fila = self._candidato(c)
            fila['financiera_id'] = c['financiera_id'] or 0
            fila['_c_potencial'] = int(round((c['ultimo_monto'] or 0.0) * 100))
            filas.append(fila)
        return filas

    def _f_expedientes_nuevos(self, ctx):
        desde = ctx.hoy.replace(day=1)
        filas = []
        for e in self.env['adt.expediente'].sudo().search([('fecha', '>=', desde), ('fecha', '<=', ctx.hoy)]):
            filas.append(ctx.con_financiera({
                'id': e.id, 'cliente_id': e.cliente_id.id, 'cliente': e.cliente_id.name or '',
                'documento': e.cliente_id.vat or '', 'telefono': e.cliente_id.mobile or e.cliente_id.phone or '',
                'asesora': e.asesora_id.name or '', 'fecha': fields.Date.to_string(e.fecha),
                'estado': e.state, 'estado_nombre': dict(ESTADOS_EXPEDIENTE).get(e.state, ''),
                'vehiculo': dict(e._fields['vehiculo'].selection).get(e.vehiculo, '') if e.vehiculo else '',
                'motivo_rechazo': e.motivo_rechazo or '',
            }, ctx.cliente_financiera.get(e.cliente_id.id, 0)))
        return filas

    # ------------------------------------------------------------------
    # Armado
    # ------------------------------------------------------------------

    @staticmethod
    def _valor(ind, filas):
        regla = ind['valor']
        if regla == 'filas':
            return len(filas)
        if regla == 'clientes':
            return len({f['_cliente'] for f in filas})
        total = sum(f[regla] for f in filas)
        return soles(total) if ind['tipo'] == 'soles' else total

    @staticmethod
    def _valor_secundario(regla, tipo, filas):
        if regla == 'filas':
            return len(filas)
        total = sum(f[regla] for f in filas)
        return soles(total) if tipo == 'soles' else total

    def _indicador(self, ind, filas, ctx):
        disponible = 'modelo' not in ind or ind['modelo'] in self.env
        salida = {
            'clave': ind['clave'], 'nombre': ind['nombre'], 'descripcion': ind['descripcion'],
            'tipo': ind['tipo'], 'disponible': disponible,
            'valor': self._valor(ind, filas) if disponible else None,
        }
        if not disponible:
            salida['mensaje'] = 'El módulo de origen no está instalado en este servidor.'
            return salida
        if ind.get('secundario'):
            regla, nombre, tipo = ind['secundario']
            salida['secundario'] = {'nombre': nombre, 'tipo': tipo,
                                    'valor': self._valor_secundario(regla, tipo, filas)}
        if ind.get('filtro'):
            campo, opciones = ind['filtro']
            # En el ciclo de fibra el valor no cuenta las listas, pero el desglose sí las muestra.
            contar = (lambda grupo: len(grupo)) if ind.get('desglose_conteo') else (lambda grupo: self._valor(ind, grupo))
            salida['desglose'] = [{'clave': k, 'nombre': l, 'valor': contar([f for f in filas if f[campo] == k])}
                                  for k, l in opciones]
        grupos = defaultdict(list)
        for f in filas:
            grupos[f['financiera_id']].append(f)
        salida['por_financiera'] = sorted(
            [{'financiera_id': fid, 'nombre': ctx.nombre_financiera(fid), 'valor': self._valor(ind, grupo)}
             for fid, grupo in grupos.items()], key=lambda x: -(x['valor'] or 0))
        return salida

    def _filas(self, ind, ctx, financiera_id):
        if 'modelo' in ind and ind['modelo'] not in self.env:
            return []
        filas = ind['filas'](ctx)
        if financiera_id is not None:
            filas = [f for f in filas if f['financiera_id'] == financiera_id]
        return filas

    @api.model
    def resumen(self, financiera_id=None):
        ctx = _Contexto(self)
        catalogo = self._catalogo()
        secciones = []
        for clave, nombre in SECCIONES:
            secciones.append({'clave': clave, 'nombre': nombre, 'indicadores': [
                self._indicador(ind, self._filas(ind, ctx, financiera_id), ctx)
                for ind in catalogo if ind['seccion'] == clave]})
        moneda = self.env.company.currency_id
        return {
            'fecha_corte': fields.Date.to_string(ctx.hoy),
            'mes': ctx.hoy.strftime('%Y-%m'),
            'moneda': moneda.name,
            'simbolo': moneda.symbol,
            'filtro_financiera_id': financiera_id,
            'financieras': [{'id': fid, 'nombre': n} for fid, n in sorted(ctx.financieras.items(), key=lambda x: x[1])],
            'secciones': secciones,
        }

    @api.model
    def resumen_detalle(self, clave, financiera_id=None, filtro=None, buscar=None, pagina=1, por_pagina=20):
        ind = next((i for i in self._catalogo() if i['clave'] == clave), None)
        if not ind:
            raise ValueError('Indicador "%s" no existe. Opciones: %s.'
                             % (clave, ', '.join(i['clave'] for i in self._catalogo())))
        ctx = _Contexto(self)
        filas = self._filas(ind, ctx, financiera_id)
        indicador = self._indicador(ind, filas, ctx)
        if filtro:
            if not ind.get('filtro'):
                raise ValueError('El indicador "%s" no acepta filtro.' % clave)
            campo, opciones = ind['filtro']
            if filtro not in dict(opciones):
                raise ValueError('Filtro inválido. Opciones: %s.' % ', '.join(k for k, _l in opciones))
            filas = [f for f in filas if f[campo] == filtro]
        if buscar:
            q = buscar.strip().lower()
            filas = [f for f in filas if any(q in _texto(f.get(k)) for k in ind['buscar'])]
        filas.sort(key=ind['orden'], reverse=bool(ind.get('invertir')))
        items, meta = paginar([_sin_privados(f) for f in filas], pagina, por_pagina)
        meta.update({'filtro': filtro, 'buscar': buscar or None,
                     'valor_filtrado': self._valor(ind, filas) if indicador['disponible'] else None})
        return {'indicador': indicador, 'filas': items}, meta
