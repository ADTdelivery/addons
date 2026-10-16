# -*- coding: utf-8 -*-
"""Indicadores para la app de gerencia.

No hay cálculos propios de dinero: todo sale de los reportes que ya usa el equipo,
para que la app y Odoo muestren las mismas cifras.

* Cartera y montos por cuenta: adt.comercial.cartera.reporte (Cartera y financieras),
  solo cuentas en curso, en céntimos exactos.
* Estado de cobranza, asesor, teléfono y recaudo: adt.comercial.cobranza.dashboard.
* Candidatos a préstamo y traspasos: adt.comercial.clientes.dashboard.

Los montos se devuelven en soles con dos decimales. Este modelo no hace control de
acceso: lo hace el controlador (token + grupo) antes de llamarlo.
"""
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, fields, models

TZ = 'America/Lima'
MESES_TENDENCIA = 12
DIAS_FLUJO = 30
TOP = 10

# Umbrales de las alertas (se pueden cambiar en Ajustes > Técnico > Parámetros del sistema).
UMBRALES = {
    'par30': ('adt_gerencia_api.umbral_par30', 10.0),             # % de la cartera con +30 días
    'cumplimiento': ('adt_gerencia_api.umbral_cumplimiento', 85.0),  # % de recaudo a la fecha
    'traspaso_dias': ('adt_gerencia_api.umbral_traspaso_dias', 30),  # días sin avance en una etapa
}

TRAMOS = [('1_30', '1 a 30 días'), ('31_60', '31 a 60 días'), ('61_90', '61 a 90 días'), ('91_mas', 'Más de 90 días')]
ESTADOS_COBRANZA = [('al_dia', 'Al día'), ('deuda', 'Con cuotas vencidas'),
                    ('orden', 'Con orden de captura'), ('capturada', 'Capturada')]
SEGMENTOS = [('apto', 'Listo para nuevo préstamo'), ('evaluar', 'Evaluar antes de prestar'),
             ('pagando_bien', 'Pagando, buen pagador'), ('pagando_alerta', 'Pagando, con alertas'),
             ('no_prestar', 'No prestar')]
ETAPAS_TRASPASO = [('preparar', 'Por terminar de pagar: preparar documentos'),
                   ('listo', 'Pagado: listo para iniciar'),
                   ('en_tramite', 'En trámite'), ('completado', 'Completado')]
ESTADOS_EN_TRAMITE = ('documentos', 'en_notaria', 'en_registros')
DIAS_PIPELINE = 90
PLACAS_FALSAS = {'S/P', 'SP', 'S/N', 'SN', 'SIN PLACA', 'EN TRAMITE', 'EN TRÁMITE', 'TRAMITE', 'TRÁMITE',
                 'PENDIENTE', 'NULL', 'NONE', 'N/A', 'NA', '-', '--'}


def soles(centimos):
    return round((centimos or 0) / 100.0, 2)


def pct(parte, total):
    return round(parte * 100.0 / total, 2) if total else 0.0


def placa_valida(placa):
    return bool(placa and placa.strip() and placa.strip().upper() not in PLACAS_FALSAS)


def paginar(filas, pagina, por_pagina):
    pagina = max(int(pagina or 1), 1)
    por_pagina = min(max(int(por_pagina or 20), 1), 100)
    inicio = (pagina - 1) * por_pagina
    return filas[inicio:inicio + por_pagina], {
        'pagina': pagina, 'por_pagina': por_pagina, 'total': len(filas),
        'paginas': (len(filas) + por_pagina - 1) // por_pagina,
    }


class AdtGerenciaIndicadores(models.AbstractModel):
    _name = 'adt.gerencia.indicadores'
    _description = 'Indicadores de la app de gerencia'

    # ------------------------------------------------------------------
    # Fuentes
    # ------------------------------------------------------------------

    def _env_calculo(self):
        # Los reportes de origen comprueban grupos de Odoo y usan la fecha local: se ejecutan
        # como superusuario (pasa sus controles de grupo), en modo sudo y con la hora de Lima.
        return self.with_user(SUPERUSER_ID).sudo().with_context(tz=TZ).env

    def _hoy(self):
        return fields.Date.context_today(self.with_context(tz=TZ))

    def _umbral(self, clave):
        param, defecto = UMBRALES[clave]
        valor = self.env['ir.config_parameter'].sudo().get_param(param)
        try:
            return type(defecto)(valor) if valor not in (None, False, '') else defecto
        except ValueError:
            return defecto

    def _cuentas(self, financiera_id=None):
        """Cuentas en curso con los montos de Cartera y financieras y los datos de Cobranzas, unidas por cuenta."""
        env = self._env_calculo()
        hoy = self._hoy()
        cartera = env['adt.comercial.cartera.reporte'].get_report_data()
        cobranza, _carteras = env['adt.comercial.cobranza.dashboard']._cartera(hoy)
        cobranza = {c['id']: c for c in cobranza}
        nombres_fin = {f['id']: f['name'] for f in cartera['financieras']}
        extra = {c['id']: c for c in env['adt.comercial.cuentas'].search_read(
            [('id', 'in', [f['id'] for f in cartera['cuentas']])],
            ['partner_id', 'mora_pendiente', 'user_id', 'vehiculo_id'])}
        filas = []
        for f in cartera['cuentas']:
            if financiera_id is not None and f['financiera_id'] != financiera_id:
                continue
            cli = f['cliente_resumen']
            cob = cobranza.get(f['id'], {})
            ex = extra.get(f['id'], {})
            filas.append({
                'cuenta_id': f['id'],
                'referencia': f['referencia'],
                'cliente_id': ex.get('partner_id') and ex['partner_id'][0],
                'cliente': f['cliente'],
                'documento': f['documento'],
                'telefono': cob.get('telefono', ''),
                'placa': f['placa'],
                'vehiculo_id': ex.get('vehiculo_id') and ex['vehiculo_id'][0],
                'financiera_id': f['financiera_id'],
                'financiera': nombres_fin.get(f['financiera_id'], 'Sin financiera'),
                'asesor': cob.get('asesor', ''),
                'estado_cobranza': cob.get('estado', 'al_dia'),
                'prioridad_captura': cob.get('prioridad', ''),
                # céntimos
                '_total': cli['total'], '_cobrado': cli['cobrado'], '_por_cobrar': cli['por_cobrar'],
                '_vencido': cli['vencido'], '_vigente': cli['vigente'], '_tramos': cli['tramos'],
                '_fin_pendiente': f['financiera']['pendiente'], '_fin_liquidar': f['financiera']['para_liquidar'],
                '_fin_fuente': f['financiera']['fuente'], '_posicion': f['posicion'],
                '_mora': int(round((ex.get('mora_pendiente') or 0.0) * 100)),
                'dias_atraso': cli['dias_atraso'],
                'cuotas_vencidas': cli['cuotas_vencidas'],
                'cuotas_restantes': cli['cuotas_restantes'],
                'fin_credito': f['fin'],
            })
        return filas, cartera['financieras']

    def _clientes(self, financiera_id=None):
        datos = self._env_calculo()['adt.comercial.clientes.dashboard'].get_dashboard_data(traspasos=True)
        clientes, traspasos = datos['clientes'], datos['traspasos']
        if financiera_id is not None:
            clientes = [c for c in clientes if c['financiera_id'] == financiera_id]
            traspasos = [t for t in traspasos if t['financiera_id'] == financiera_id]
        return clientes, traspasos

    # ------------------------------------------------------------------
    # Secciones del dashboard
    # ------------------------------------------------------------------

    def _vehiculos(self):
        V = self.env['fleet.vehicle'].sudo()
        vehiculos = V.search_read([], ['license_plate', 'state_id', 'disponible'] if 'disponible' in V._fields
                                  else ['license_plate', 'state_id'])
        financiados = set(self.env['adt.comercial.cuentas'].sudo().search(
            [('state', '=', 'en_curso'), ('vehiculo_id', '!=', False)]).mapped('vehiculo_id').ids)
        capturados = set()
        if 'adt.captura.record' in self.env:
            capturados = set(self.env['adt.captura.record'].sudo().search(
                [('state', 'in', ('capturado', 'disolucion_contrato')), ('vehicle_id', '!=', False)]).mapped('vehicle_id').ids)
        por_estado = defaultdict(int)
        for v in vehiculos:
            por_estado[v['state_id'][1] if v['state_id'] else 'Sin estado'] += 1
        disponibles = [v for v in vehiculos if v['id'] not in financiados and v.get('disponible', True)]
        return {
            'total': len(vehiculos),
            'financiados': len(financiados),
            'disponibles': len(disponibles),
            'capturados': len(capturados),
            'sin_placa': sum(1 for v in vehiculos if not placa_valida(v['license_plate'])),
            'por_estado': [{'estado': k, 'cantidad': n} for k, n in sorted(por_estado.items(), key=lambda x: -x[1])],
        }

    def _cartera(self, filas):
        por_cobrar = sum(f['_por_cobrar'] for f in filas)
        vencido = sum(f['_vencido'] for f in filas)
        total = sum(f['_total'] for f in filas)
        par = lambda dias: sum(f['_por_cobrar'] for f in filas if f['dias_atraso'] > dias)

        tramos = []
        for clave, label in TRAMOS:
            cuentas = [f for f in filas if f['_tramos'].get(clave)]
            tramos.append({'tramo': clave, 'nombre': label, 'monto': soles(sum(f['_tramos'][clave] for f in filas)),
                           'cuentas': len(cuentas)})

        estados = []
        for clave, label in ESTADOS_COBRANZA:
            grupo = [f for f in filas if f['estado_cobranza'] == clave]
            estados.append({'estado': clave, 'nombre': label, 'cuentas': len(grupo),
                            'por_cobrar': soles(sum(f['_por_cobrar'] for f in grupo)),
                            'vencido': soles(sum(f['_vencido'] for f in grupo))})

        ordenados = sorted((f['_vencido'] for f in filas if f['_vencido']), reverse=True)
        return {
            'cuentas': len(filas),
            'clientes': len({f['cliente_id'] or f['documento'] for f in filas}),
            'monto_financiado': soles(total),
            'cobrado': soles(sum(f['_cobrado'] for f in filas)),
            'por_cobrar': soles(por_cobrar),
            'por_vencer': soles(sum(f['_vigente'] for f in filas)),
            'vencido': soles(vencido),
            'mora_pendiente': soles(sum(f['_mora'] for f in filas)),
            'morosidad_pct': pct(vencido, por_cobrar),
            'par30_pct': pct(par(30), por_cobrar),
            'par60_pct': pct(par(60), por_cobrar),
            'par90_pct': pct(par(90), por_cobrar),
            'ticket_promedio': soles(total / len(filas)) if filas else 0.0,
            'cuentas_con_atraso': sum(1 for f in filas if f['_vencido']),
            'tramos_atraso': tramos,
            'estados': estados,
            # Qué parte de lo vencido está en los 10 mayores deudores.
            'concentracion_top10_pct': pct(sum(ordenados[:TOP]), vencido),
        }

    def _por_financiera(self, filas, financieras):
        grupos = defaultdict(list)
        for f in filas:
            grupos[f['financiera_id']].append(f)
        nombres = {f['id']: f['name'] for f in financieras}
        salida = []
        for fid, grupo in grupos.items():
            por_cobrar = sum(f['_por_cobrar'] for f in grupo)
            vencido = sum(f['_vencido'] for f in grupo)
            deuda = sum(f['_fin_pendiente'] for f in grupo)
            salida.append({
                'financiera_id': fid,
                'nombre': nombres.get(fid, 'Sin financiera'),
                'cuentas': len(grupo),
                'por_cobrar': soles(por_cobrar),
                'vencido': soles(vencido),
                'morosidad_pct': pct(vencido, por_cobrar),
                'deuda_con_financiera': soles(deuda),
                'posicion_neta': soles(por_cobrar - deuda),
            })
        return sorted(salida, key=lambda x: -x['por_cobrar'])

    def _posicion_financieras(self, filas):
        por_cobrar = sum(f['_por_cobrar'] for f in filas)
        deuda = sum(f['_fin_pendiente'] for f in filas)
        liquidables = [f for f in filas if f['_fin_liquidar'] is not None]
        p = lambda clave: sum(f['_posicion'][clave] for f in filas)
        return {
            'nos_deben_clientes': soles(por_cobrar),
            'debemos_financieras': soles(deuda),
            'posicion_neta': soles(por_cobrar - deuda),
            'cancelar_hoy_financieras': soles(sum(f['_fin_liquidar'] for f in liquidables)),
            'cuentas_sin_monto_para_cancelar': len(filas) - len(liquidables),
            'cuentas_sin_cronograma_financiera': sum(1 for f in filas if f['_fin_fuente'] == 'sin_datos'),
            'ganancia_esperada': soles(p('ganancia_esperada')),
            'ganancia_realizada': soles(p('ganancia_realizada')),
            'ganancia_por_realizar': soles(p('ganancia_por_realizar')),
        }

    def _flujo(self, financiera_id, hoy):
        env = self._env_calculo()
        desde = (hoy - relativedelta(months=MESES_TENDENCIA - 1)).replace(day=1)
        fin_mes = hoy + relativedelta(day=31)
        agregados, programado = env['adt.comercial.cobranza.dashboard']._recaudo(desde, fin_mes)
        meses = defaultdict(lambda: {'programado': 0.0, 'programado_a_la_fecha': 0.0, 'cobrado': 0.0, 'mora': 0.0, 'pagos': 0})
        hoy_s = fields.Date.to_string(hoy)
        for (fecha, _cartera, fid, _diario, _usuario), a in agregados.items():
            if financiera_id is None or fid == financiera_id:
                m = meses[fecha[:7]]
                m['cobrado'] += a['cuota']
                m['mora'] += a['mora']
                m['pagos'] += a['pagos']
        for (fecha, _cartera, fid), monto in programado.items():
            if financiera_id is None or fid == financiera_id:
                meses[fecha[:7]]['programado'] += monto
                if fecha <= hoy_s:
                    meses[fecha[:7]]['programado_a_la_fecha'] += monto

        tendencia = []
        cursor = desde
        while cursor <= hoy:
            clave = cursor.strftime('%Y-%m')
            m = meses[clave]
            tendencia.append({
                'mes': clave,
                'programado': round(m['programado'], 2),
                'cobrado': round(m['cobrado'], 2),
                'mora_cobrada': round(m['mora'], 2),
                'cumplimiento_pct': pct(m['cobrado'], m['programado']),
            })
            cursor += relativedelta(months=1)

        actual = meses[hoy.strftime('%Y-%m')]
        anterior = meses[(hoy - relativedelta(months=1)).strftime('%Y-%m')]
        mes_actual = {
            'mes': hoy.strftime('%Y-%m'),
            'cobrado': round(actual['cobrado'], 2),
            'mora_cobrada': round(actual['mora'], 2),
            'pagos': actual['pagos'],
            'programado_mes': round(actual['programado'], 2),
            'programado_a_la_fecha': round(actual['programado_a_la_fecha'], 2),
            # El cumplimiento compara con lo que debía cobrarse hasta hoy, no con el mes completo.
            'cumplimiento_a_la_fecha_pct': pct(actual['cobrado'], actual['programado_a_la_fecha']),
        }

        # Lo que vence en los próximos días (cuotas por cobrar de cuentas en curso).
        dominio = [('cuenta_id.state', '=', 'en_curso'), ('type', '=', 'cuota'),
                   ('state', 'in', ('pendiente', 'a_cuenta', 'retrasado')), ('saldo', '>', 0),
                   ('fecha_cronograma', '>=', hoy), ('fecha_cronograma', '<=', hoy + timedelta(days=DIAS_FLUJO))]
        if financiera_id is not None:
            dominio.append(('cuenta_id.tipo_financiera_id', '=', financiera_id or False))
        proximas = self.env['adt.comercial.cuotas'].sudo().search_read(dominio, ['saldo', 'cuenta_id'])
        return {
            'mes_actual': mes_actual,
            'mes_anterior': {'mes': (hoy - relativedelta(months=1)).strftime('%Y-%m'),
                             'cobrado': round(anterior['cobrado'], 2),
                             'programado': round(anterior['programado'], 2),
                             'cumplimiento_pct': pct(anterior['cobrado'], anterior['programado'])},
            'variacion_cobrado_pct': round(pct(actual['cobrado'] - anterior['cobrado'], anterior['cobrado']), 2)
            if anterior['cobrado'] else None,
            'proximos_dias': {'dias': DIAS_FLUJO, 'monto': round(sum(q['saldo'] for q in proximas), 2),
                              'cuotas': len(proximas), 'cuentas': len({q['cuenta_id'][0] for q in proximas})},
            'tendencia': tendencia,
        }

    def _candidatos_resumen(self, clientes, hoy):
        limite = fields.Date.to_string(hoy + timedelta(days=DIAS_PIPELINE))
        hoy_s = fields.Date.to_string(hoy)
        por_segmento = {k: [c for c in clientes if c['segmento'] == k] for k, _l in SEGMENTOS}
        aptos = por_segmento['apto']
        pipeline = [c for c in por_segmento['pagando_bien'] if c['termina'] and hoy_s <= c['termina'] <= limite]
        con_terminado = [c for c in clientes if c['n_terminados']]
        mejores = sorted(aptos + por_segmento['evaluar'], key=lambda c: (c['segmento'] != 'apto', -c['puntaje']))
        return {
            'segmentos': [{'segmento': k, 'nombre': l, 'clientes': len(por_segmento[k])} for k, l in SEGMENTOS],
            'listos': len(aptos),
            'monto_potencial': round(sum(c['ultimo_monto'] or 0.0 for c in aptos), 2),
            'pipeline_90_dias': {'clientes': len(pipeline),
                                 'monto_potencial': round(sum(c['ultimo_monto'] or 0.0 for c in pipeline), 2)},
            'tasa_recompra_pct': pct(sum(1 for c in con_terminado if c['recompra']), len(con_terminado)),
            'top': [self._candidato(c) for c in mejores[:TOP]],
        }

    @staticmethod
    def _candidato(c):
        seg = c.get('seguimiento') or {}
        return {
            'cliente_id': c['id'],
            'nombre': c['nombre'],
            'documento': c['documento'],
            'telefono': c['telefono'],
            'financiera': c['financiera'],
            'segmento': c['segmento'],
            'segmento_nombre': dict(SEGMENTOS).get(c['segmento'], ''),
            'puntaje': c['puntaje'],
            'puntualidad_pct': c['puntualidad'],
            'atraso_promedio_dias': c['atraso_promedio'],
            'creditos': c['n_creditos'],
            'creditos_terminados': c['n_terminados'],
            'ultimo_monto': round(c['ultimo_monto'] or 0.0, 2),
            'termino': c['termino'],
            'termina': c['termina'],
            'recompra': c['recompra'],
            'bloqueos': c['bloqueos'],
            'seguimiento': seg.get('estado') if isinstance(seg, dict) else None,
        }

    def _traspasos_info(self, traspasos):
        """Agrega a cada traspaso los días sin avance (desde la última actualización del registro)."""
        ahora = fields.Datetime.now()
        ids = [t['traspaso']['id'] for t in traspasos if t['traspaso']]
        creados = {r['id']: r['create_date'] for r in self.env['adt.traspaso.notarial'].sudo().search_read(
            [('id', 'in', ids)], ['create_date'])} if ids else {}
        for t in traspasos:
            tr = t['traspaso']
            t['_dias_sin_avance'] = (ahora - fields.Datetime.from_string(tr['actualizado'])).days \
                if tr and tr['actualizado'] else None
            t['_creado'] = creados.get(tr['id']) if tr else None
        return traspasos

    def _traspasos_resumen(self, traspasos, hoy):
        umbral = self._umbral('traspaso_dias')
        traspasos = self._traspasos_info(traspasos)
        mes = hoy.strftime('%Y-%m')
        completados = [t for t in traspasos if t['etapa'] == 'completado']
        duraciones = [(fields.Date.from_string(t['traspaso']['fecha_completado']) - t['_creado'].date()).days
                      for t in completados if t['traspaso']['fecha_completado'] and t['_creado']]
        en_tramite = [t for t in traspasos if t['traspaso'] and t['traspaso']['estado'] in ESTADOS_EN_TRAMITE]
        estancados = [t for t in en_tramite if (t['_dias_sin_avance'] or 0) > umbral]
        estados = dict(self.env['adt.traspaso.notarial']._fields['estado']._description_selection(self.env))
        return {
            'etapas': [{'etapa': k, 'nombre': l, 'cantidad': sum(1 for t in traspasos if t['etapa'] == k)}
                       for k, l in ETAPAS_TRASPASO],
            'en_tramite_por_estado': [{'estado': k, 'nombre': estados.get(k, k),
                                       'cantidad': sum(1 for t in en_tramite if t['traspaso']['estado'] == k)}
                                      for k in ESTADOS_EN_TRAMITE],
            'pagados_sin_iniciar': sum(1 for t in traspasos if t['etapa'] == 'listo'),
            'por_preparar_60_dias': sum(1 for t in traspasos if t['etapa'] == 'preparar'),
            'completados_mes': sum(1 for t in completados if (t['traspaso']['fecha_completado'] or '')[:7] == mes),
            'duracion_promedio_dias': round(sum(duraciones) / len(duraciones), 1) if duraciones else None,
            'estancados': len(estancados),
            'umbral_estancado_dias': umbral,
        }

    def _alertas(self, cartera, flujo, por_financiera, traspasos):
        alertas = []

        def alerta(nivel, codigo, mensaje, valor=None):
            alertas.append({'nivel': nivel, 'codigo': codigo, 'mensaje': mensaje, 'valor': valor})

        u_par = self._umbral('par30')
        if cartera['par30_pct'] > u_par:
            alerta('critico', 'PAR30_ALTO', 'El %.1f%% de la cartera tiene más de 30 días de atraso (meta: hasta %.0f%%).'
                   % (cartera['par30_pct'], u_par), cartera['par30_pct'])
        mas90 = next((t for t in cartera['tramos_atraso'] if t['tramo'] == '91_mas'), None)
        if mas90 and mas90['cuentas']:
            alerta('critico', 'ATRASO_MAS_90', '%d cuenta(s) con más de 90 días de atraso: S/ %s vencidos.'
                   % (mas90['cuentas'], '{:,.2f}'.format(mas90['monto'])), mas90['monto'])
        u_cum = self._umbral('cumplimiento')
        ma = flujo['mes_actual']
        if ma['programado_a_la_fecha'] and ma['cumplimiento_a_la_fecha_pct'] < u_cum:
            alerta('atencion', 'RECAUDO_BAJO', 'El recaudo del mes va al %.1f%% de lo programado a la fecha (meta: %.0f%%).'
                   % (ma['cumplimiento_a_la_fecha_pct'], u_cum), ma['cumplimiento_a_la_fecha_pct'])
        for f in por_financiera:
            if f['cuentas'] >= 3 and f['morosidad_pct'] > max(u_par * 2, 20):
                alerta('atencion', 'FINANCIERA_MORA_ALTA', '%s: %.1f%% de su cartera está vencida.'
                       % (f['nombre'], f['morosidad_pct']), f['morosidad_pct'])
        if cartera['concentracion_top10_pct'] > 50 and cartera['cuentas_con_atraso'] > TOP:
            alerta('atencion', 'CONCENTRACION', 'Los 10 mayores deudores concentran el %.1f%% de lo vencido.'
                   % cartera['concentracion_top10_pct'], cartera['concentracion_top10_pct'])
        if traspasos['estancados']:
            alerta('atencion', 'TRASPASOS_ESTANCADOS', '%d traspaso(s) sin avance por más de %d días.'
                   % (traspasos['estancados'], traspasos['umbral_estancado_dias']), traspasos['estancados'])
        if traspasos['pagados_sin_iniciar']:
            alerta('info', 'TRASPASOS_POR_INICIAR', '%d cliente(s) terminaron de pagar y su traspaso no empezó.'
                   % traspasos['pagados_sin_iniciar'], traspasos['pagados_sin_iniciar'])
        orden = {'critico': 0, 'atencion': 1, 'info': 2}
        return sorted(alertas, key=lambda a: orden[a['nivel']])

    # ------------------------------------------------------------------
    # API pública (la llama el controlador)
    # ------------------------------------------------------------------

    @api.model
    def dashboard(self, financiera_id=None):
        hoy = self._hoy()
        filas, financieras = self._cuentas(financiera_id)
        clientes, traspasos = self._clientes(financiera_id)
        vehiculos = self._vehiculos()
        cartera = self._cartera(filas)
        por_financiera = self._por_financiera(filas, financieras)
        flujo = self._flujo(financiera_id, hoy)
        candidatos = self._candidatos_resumen(clientes, hoy)
        tr = self._traspasos_resumen(traspasos, hoy)
        deudores = sorted([f for f in filas if f['_vencido']], key=lambda f: (-f['_vencido'], -f['dias_atraso']))
        posicion = self._posicion_financieras(filas)

        titulares = [
            {'clave': 'vehiculos', 'nombre': 'Vehículos', 'valor': vehiculos['total'], 'tipo': 'entero',
             'detalle': '%d financiados · %d disponibles' % (vehiculos['financiados'], vehiculos['disponibles'])},
            {'clave': 'por_cobrar', 'nombre': 'Cartera por cobrar', 'valor': cartera['por_cobrar'], 'tipo': 'soles',
             'detalle': '%d cuentas en curso' % cartera['cuentas']},
            {'clave': 'vencido', 'nombre': 'Cartera vencida', 'valor': cartera['vencido'], 'tipo': 'soles',
             'detalle': '%.1f%% de la cartera · %d cuentas' % (cartera['morosidad_pct'], cartera['cuentas_con_atraso'])},
            {'clave': 'par30', 'nombre': 'Cartera en riesgo +30 días (PAR30)', 'valor': cartera['par30_pct'], 'tipo': 'porcentaje',
             'detalle': 'Meta: hasta %.0f%%' % self._umbral('par30')},
            {'clave': 'recaudo_mes', 'nombre': 'Recaudo del mes', 'valor': flujo['mes_actual']['cobrado'], 'tipo': 'soles',
             'detalle': '%.1f%% de lo programado a la fecha' % flujo['mes_actual']['cumplimiento_a_la_fecha_pct'],
             'variacion_pct': flujo['variacion_cobrado_pct']},
            {'clave': 'posicion_neta', 'nombre': 'Posición neta con financieras', 'valor': posicion['posicion_neta'],
             'tipo': 'soles', 'detalle': 'Nos deben menos lo que debemos'},
            {'clave': 'candidatos', 'nombre': 'Listos para nuevo préstamo', 'valor': candidatos['listos'], 'tipo': 'entero',
             'detalle': 'S/ {:,.2f} de colocación potencial'.format(candidatos['monto_potencial'])},
            {'clave': 'traspasos', 'nombre': 'Traspasos pendientes', 'valor': tr['pagados_sin_iniciar'] + sum(
                e['cantidad'] for e in tr['en_tramite_por_estado']), 'tipo': 'entero',
             'detalle': '%d por iniciar · %d en trámite' % (tr['pagados_sin_iniciar'], sum(e['cantidad'] for e in tr['en_tramite_por_estado']))},
        ]
        moneda = self.env.company.currency_id
        return {
            'fecha_corte': fields.Date.to_string(hoy),
            'moneda': moneda.name,
            'simbolo': moneda.symbol,
            'filtro_financiera_id': financiera_id,
            'financieras': [{'id': f['id'], 'nombre': f['name']} for f in financieras],
            'titulares': titulares,
            'alertas': self._alertas(cartera, flujo, por_financiera, tr),
            'vehiculos': vehiculos,
            'cartera': cartera,
            'top_deudores': [self._deudor(f) for f in deudores[:TOP]],
            'por_financiera': por_financiera,
            'flujo': flujo,
            'posicion_financieras': posicion,
            'candidatos': candidatos,
            'traspasos': tr,
        }

    @staticmethod
    def _deudor(f):
        # El tramo de la cuenta es el de su cuota más atrasada.
        tramo = next((k for k, _l in reversed(TRAMOS) if f['_tramos'].get(k)), None)
        return {
            'cuenta_id': f['cuenta_id'],
            'referencia': f['referencia'],
            'cliente_id': f['cliente_id'],
            'cliente': f['cliente'],
            'documento': f['documento'],
            'telefono': f['telefono'],
            'placa': f['placa'],
            'financiera': f['financiera'],
            'asesor': f['asesor'],
            'estado_cobranza': f['estado_cobranza'],
            'estado_cobranza_nombre': dict(ESTADOS_COBRANZA).get(f['estado_cobranza'], ''),
            'vencido': soles(f['_vencido']),
            'mora_pendiente': soles(f['_mora']),
            'por_cobrar': soles(f['_por_cobrar']),
            'dias_atraso': f['dias_atraso'],
            'cuotas_vencidas': f['cuotas_vencidas'],
            'tramo': tramo,
        }

    @api.model
    def deudores(self, financiera_id=None, tramo=None, estado=None, buscar=None, orden='vencido', pagina=1, por_pagina=20):
        filas, _f = self._cuentas(financiera_id)
        filas = [f for f in filas if f['_vencido']]
        lista = [self._deudor(f) for f in filas]
        if tramo:
            lista = [d for d in lista if d['tramo'] == tramo]
        if estado:
            lista = [d for d in lista if d['estado_cobranza'] == estado]
        if buscar:
            q = buscar.strip().lower()
            lista = [d for d in lista if any(q in (d[k] or '').lower() for k in ('cliente', 'documento', 'placa', 'referencia'))]
        clave = {'dias': lambda d: (-d['dias_atraso'], -d['vencido']),
                 'cliente': lambda d: d['cliente'].lower()}.get(orden, lambda d: (-d['vencido'], -d['dias_atraso']))
        lista.sort(key=clave)
        pagina_items, meta = paginar(lista, pagina, por_pagina)
        meta['total_vencido'] = round(sum(d['vencido'] for d in lista), 2)
        return pagina_items, meta

    @api.model
    def candidatos(self, financiera_id=None, segmento='apto', buscar=None, pagina=1, por_pagina=20):
        clientes, _t = self._clientes(financiera_id)
        if segmento:
            clientes = [c for c in clientes if c['segmento'] == segmento]
        if buscar:
            q = buscar.strip().lower()
            clientes = [c for c in clientes if q in (c['nombre'] or '').lower() or q in (c['documento'] or '').lower()]
        clientes.sort(key=lambda c: (-c['puntaje'], c['nombre']))
        pagina_items, meta = paginar([self._candidato(c) for c in clientes], pagina, por_pagina)
        return pagina_items, meta

    @api.model
    def traspasos(self, financiera_id=None, etapa=None, buscar=None, pagina=1, por_pagina=20):
        _c, traspasos = self._clientes(financiera_id)
        traspasos = self._traspasos_info(traspasos)
        if etapa:
            traspasos = [t for t in traspasos if t['etapa'] == etapa]
        if buscar:
            q = buscar.strip().lower()
            traspasos = [t for t in traspasos if any(q in (t[k] or '').lower() for k in ('nombre', 'documento', 'placa', 'referencia'))]
        orden = {k: i for i, (k, _l) in enumerate(ETAPAS_TRASPASO)}
        traspasos.sort(key=lambda t: (orden.get(t['etapa'], 9), -(t['_dias_sin_avance'] or 0), t['fin'] or ''))
        estados = dict(self.env['adt.traspaso.notarial']._fields['estado']._description_selection(self.env))
        lista = [{
            'cuenta_id': t['cuenta_id'],
            'referencia': t['referencia'],
            'cliente_id': t['cliente_id'],
            'cliente': t['nombre'],
            'documento': t['documento'],
            'telefono': t['telefono'],
            'placa': t['placa'],
            'moto': t['moto'],
            'financiera': t['financiera'],
            'etapa': t['etapa'],
            'etapa_nombre': dict(ETAPAS_TRASPASO).get(t['etapa'], ''),
            'estado_traspaso': t['traspaso']['estado'] if t['traspaso'] else None,
            'estado_traspaso_nombre': estados.get(t['traspaso']['estado']) if t['traspaso'] else None,
            'credito_terminado': t['terminada'],
            'fin_credito': t['fin'],
            'cuotas_restantes': t['restantes'],
            'notaria': t['traspaso']['notaria'] if t['traspaso'] else '',
            'fecha_firma': t['traspaso']['fecha_firma'] if t['traspaso'] else None,
            'fecha_completado': t['traspaso']['fecha_completado'] if t['traspaso'] else None,
            'responsable': t['traspaso']['responsable'] if t['traspaso'] else '',
            'dias_sin_avance': t['_dias_sin_avance'],
            'alertas': t['alertas'],
        } for t in traspasos]
        return paginar(lista, pagina, por_pagina)
