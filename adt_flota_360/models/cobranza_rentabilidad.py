from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.adt_comercial.models.cartera_calculo import cents

from .cobranza_calculo import (
    agrupar_cuotas, cuotas_financiera_manual, cuotas_financiera_pdf, pagado_financiera,
    refinanciamientos, rentabilidad_cuenta, semanal_credito, semanal_recuperada, semanas,
)

# Semanas cerradas que viajan al navegador; la vista elige cuántas mostrar.
SEMANAS = 26
GRUPO_GERENCIA = 'adt_comercial.group_access_adt_comercial_gerencia'

CAMPOS_CUENTA = [
    'reference_no', 'state', 'partner_id', 'partner_document', 'moto_placa', 'vehiculo_id', 'periodicidad',
    'recuperado', 'fin_desde_vehiculo', 'monto_inicial', 'monto_fraccionado', 'cf_monto_cuota', 'cf_dni',
    'fin_fecha_inicio', 'fin_es_mensual', 'fin_fecha_fin', 'fin_monto_cuota', 'fin_monto_total', 'write_date',
]


class AdtFlota360CobranzaRentabilidad(models.AbstractModel):
    """Datos de la vista "Cobranza y rentabilidad" (acción JS: adt_flota_360_cobranza_rentabilidad).

    Reutiliza los puntos 1 a 4 del reporte "Cartera y financieras" y agrega la morosidad semanal,
    lo que cubre ADT cuando el cliente no paga y la ganancia de cada moto con todos sus créditos.
    Montos en céntimos enteros.
    """
    _name = 'adt.flota360.cobranza.rentabilidad'
    _description = 'Cobranza semanal y rentabilidad por moto'

    @api.model
    def get_report_data(self):
        if not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(_('Solo gerencia puede ver la cobranza y rentabilidad.'))
        data = self.env['adt.comercial.cartera.reporte'].get_report_data()
        hoy = fields.Date.context_today(self)
        lunes_semanas = semanas(hoy, SEMANAS)

        cuentas = self.env['adt.comercial.cuentas'].search_read(
            [('state', '!=', 'borrador')], CAMPOS_CUENTA, order='id')
        ids = [c['id'] for c in cuentas]
        cuotas = self.env['adt.comercial.cuotas'].search_read(
            [('cuenta_id', 'in', ids)],
            ['cuenta_id', 'parent_id', 'name', 'type', 'monto', 'saldo', 'fecha_cronograma', 'state'])
        cuenta_de_cuota = {q['id']: q['cuenta_id'][0] for q in cuotas}
        cuotas_por_cuenta = defaultdict(list)
        for q in cuotas:
            cuotas_por_cuenta[q['cuenta_id'][0]].append(q)

        pagos = {}
        mora_por_cuenta = defaultdict(int)
        for p in self.env['account.payment'].search_read(
                [('cuota_id', 'in', list(cuenta_de_cuota)), ('state', '=', 'posted')],
                ['cuota_id', 'date', 'amount', 'mora', 'mora_state', 'mora_pagado']):
            cuota_id = p['cuota_id'][0]
            pagos.setdefault(cuota_id, []).append((p['date'], cents(p['amount'])))
            mora_por_cuenta[cuenta_de_cuota[cuota_id]] += cents(
                p['mora'] if p['mora_state'] == 'paid' else p['mora_pagado'])

        fin_por_cuenta = self._financiera_por_cuenta(cuentas)
        cierres = self._fechas_cierre(cuentas)

        creditos = []
        for c in cuentas:
            recuperada = c['state'] == 'cancelado' and c['recuperado']
            if c['state'] == 'cancelado' and not recuperada:
                continue  # anulada: no es deuda del cliente
            grupos = agrupar_cuotas([{
                'id': q['id'], 'parent_id': q['parent_id'] and q['parent_id'][0], 'monto': q['monto'],
                'saldo': q['saldo'], 'fecha': q['fecha_cronograma'], 'state': q['state'],
            } for q in cuotas_por_cuenta.get(c['id'], []) if q['type'] == 'cuota'])
            if not grupos:
                continue
            s = semanal_credito(hoy, lunes_semanas, grupos, pagos, fin_por_cuenta.get(c['id'], []),
                                c['periodicidad'], hasta=cierres.get(c['id']) if recuperada else None)
            if not s['semanas'] and not s['vencido']:
                continue
            activa = c['state'] == 'en_curso'
            creditos.append(dict(self._identidad(c), estado=c['state'], semanas=s['semanas'],
                                 # Lo de hoy solo para créditos en curso: cuadra con el punto 1.
                                 vencido=s['vencido'] if activa else 0,
                                 cubriendo=s['cubriendo'] if activa else 0,
                                 cuotas_vencidas=s['cuotas_vencidas'] if activa else 0,
                                 con_financiera=bool(fin_por_cuenta.get(c['id']))))

        for r in data['recuperadas']:
            desde = cierres.get(r['id'])
            r.update(semanal_recuperada(lunes_semanas, fin_por_cuenta.get(r['id'], []), desde, hoy),
                     desde=fields.Date.to_string(desde) if desde else None)

        data.update({
            'semanas': [fields.Date.to_string(d) for d in lunes_semanas],
            'creditos': creditos,
            'motos': self._motos(hoy, cuentas, cuotas_por_cuenta, mora_por_cuenta, fin_por_cuenta, cierres),
        })
        return data

    @staticmethod
    def _identidad(c):
        return {
            'id': c['id'],
            'referencia': c['reference_no'] or '',
            'cliente': c['partner_id'][1] if c['partner_id'] else _('Sin cliente'),
            'documento': c['partner_document'] or c['cf_dni'] or '',
            'placa': c['moto_placa'] or '',
        }

    def _financiera_por_cuenta(self, cuentas):
        """Cuotas de la financiera [(fecha, céntimos)] que corresponden a cada cuenta.

        El plan del PDF es del vehículo: vale para todas sus cuentas (la financiera se paga mientras
        la moto pase de un cliente a otro). Sin PDF, se usa la financiera cargada a mano en la cuenta.
        """
        vehiculos = {c['vehiculo_id'][0] for c in cuentas if c['vehiculo_id']}
        filas = defaultdict(list)
        for f in self.env['adt.comercial.cuentas.cronograma.fin'].search_read(
                [('vehicle_id', 'in', list(vehiculos))],
                ['vehicle_id', 'nro_cuota', 'fecha_vencimiento', 'total'], order='vehicle_id, nro_cuota'):
            filas[f['vehicle_id'][0]].append({'nro': f['nro_cuota'], 'fecha': f['fecha_vencimiento'], 'total': f['total']})
        # Monto de cuota del PDF para estimar las cuotas anteriores: el de la cuenta que lleva el plan.
        cuota_pdf = {}
        for c in cuentas:
            if c['vehiculo_id'] and (c['fin_desde_vehiculo'] or c['vehiculo_id'][0] not in cuota_pdf):
                cuota_pdf[c['vehiculo_id'][0]] = c['cf_monto_cuota']
        plan = {v: cuotas_financiera_pdf(f, cuota_pdf.get(v)) for v, f in filas.items()}
        resultado = {}
        for c in cuentas:
            vehiculo = c['vehiculo_id'] and c['vehiculo_id'][0]
            resultado[c['id']] = plan.get(vehiculo) or cuotas_financiera_manual(
                c['fin_fecha_inicio'], c['fin_es_mensual'], c['fin_fecha_fin'], c['fin_monto_cuota'],
                c['fin_monto_total'])
        return resultado

    def _fechas_cierre(self, cuentas):
        """Fecha en que cada cuenta cancelada pasó a ese estado (seguimiento del chatter). Si no hay
        seguimiento, la última modificación de la cuenta."""
        canceladas = [c for c in cuentas if c['state'] == 'cancelado']
        if not canceladas:
            return {}
        Cuenta = self.env['adt.comercial.cuentas']
        etiqueta = dict(Cuenta._fields['state']._description_selection(self.env)).get('cancelado')
        # Solo se leen fechas de cambio de estado: el historial técnico puede estar restringido al usuario.
        seguimiento = self.env['mail.tracking.value'].sudo().search([
            ('mail_message_id.model', '=', Cuenta._name),
            ('mail_message_id.res_id', 'in', [c['id'] for c in canceladas]),
            ('field.name', '=', 'state'), ('new_value_char', '=', etiqueta)])
        fechas = {}
        for t in seguimiento:
            m = t.mail_message_id
            fechas[m.res_id] = max(fechas.get(m.res_id) or m.date.date(), m.date.date())
        return {c['id']: fechas.get(c['id']) or c['write_date'].date() for c in canceladas}

    def _motos(self, hoy, cuentas, cuotas_por_cuenta, mora_por_cuenta, fin_por_cuenta, cierres):
        """Ganancia de cada moto con todos sus créditos: el original, refinanciamientos y reventas."""
        por_vehiculo = defaultdict(list)
        for c in cuentas:
            if c['vehiculo_id']:
                por_vehiculo[c['vehiculo_id'][0]].append(c)
        motos = []
        for vehiculo, propias in por_vehiculo.items():
            tot = defaultdict(int)
            titulares = {}
            for c in propias:
                r = rentabilidad_cuenta(c, cuotas_por_cuenta.get(c['id'], []), mora_por_cuenta[c['id']])
                for k, v in r.items():
                    tot[k] += v
                ident = self._identidad(c)
                t = titulares.setdefault(ident['documento'] or ident['cliente'], {
                    'cliente': ident['cliente'], 'documento': ident['documento'], 'nombres': []})
                t['nombres'].append([q['name'] for q in cuotas_por_cuenta.get(c['id'], []) if not q['parent_id']])
            # Plan de la financiera de la moto, contado una vez (el de la cuenta que lo lleva).
            lleva = next((c for c in propias if c['fin_desde_vehiculo']), None) or \
                next((c for c in reversed(propias) if fin_por_cuenta.get(c['id'])), propias[-1])
            fin = fin_por_cuenta.get(lleva['id'], [])
            fin_total = sum(m for _f, m in fin)
            fin_pagado = pagado_financiera(fin, None, hoy)
            ultima = propias[-1]
            situacion = ('recuperada' if ultima['state'] == 'cancelado' and ultima['recuperado']
                         else 'anulada' if ultima['state'] == 'cancelado' else ultima['state'])
            motos.append({
                'vehiculo_id': vehiculo,
                'placa': next((c['moto_placa'] for c in reversed(propias) if c['moto_placa']), ''),
                'cuenta_id': ultima['id'],
                'situacion': situacion,
                'desde': fields.Date.to_string(cierres[ultima['id']]) if ultima['id'] in cierres else None,
                'titulares': [{'cliente': t['cliente'], 'documento': t['documento']} for t in titulares.values()],
                'referencias': [c['reference_no'] or '' for c in propias],
                'creditos': len(propias),
                'refinanciamientos': sum(refinanciamientos(t['nombres']) for t in titulares.values()),
                'inicial': tot['inicial'], 'cuotas': tot['cuotas'], 'cargos': tot['cargos'],
                'recaudado': tot['recaudado'], 'por_cobrar': tot['por_cobrar'],
                'fin_total': fin_total, 'fin_pagado': fin_pagado,
                'ganado_hoy': tot['recaudado'] - fin_pagado,
                'ganancia': tot['recaudado'] + tot['por_cobrar'] - fin_total,
                'con_financiera': bool(fin),
            })
        return motos
