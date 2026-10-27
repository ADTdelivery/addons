# -*- coding: utf-8 -*-
"""Programas y ejecuciones del monitor SAT.

Odoo decide qué placas consultar y cuándo; el monitor (agente en EC2) pregunta
cada minuto por ejecuciones pendientes, las corre y devuelve el informe:

    Programa (alcance + horario) --cron / botón--> Ejecución (pendiente)
    agente: tomar -> latido por placa -> import por placa -> finalizar

Un cron cada 5 minutos lanza los programas a su hora y marca como fallidas las
ejecuciones que el agente no tomó o dejó de atender.
"""
import json
import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

from .papeleta_sat import CON_PAPELETAS, SIN_PAPELETAS, normalizar

_logger = logging.getLogger(__name__)

PARAM_MIN_SIN_TOMAR = 'adt_papeletas.sat_minutos_sin_tomar'
PARAM_MIN_SIN_LATIDO = 'adt_papeletas.sat_minutos_sin_latido'
# Una programación perdida (Odoo apagado, otra corrida en curso) se lanza tarde
# solo dentro de esta ventana; pasado ese tiempo se espera al día siguiente.
VENTANA_PROGRAMACION = timedelta(hours=3)
ACTIVAS = ('pendiente', 'en_proceso')
DIAS = ('lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo')


def _placas_de(vehiculos):
    """[{placa, vehicle_id, conductor}] sin repetir placa; gana el vehículo más reciente."""
    vistas, placas = set(), []
    for v in vehiculos.sorted('id', reverse=True):
        placa = normalizar(v.license_plate)
        if not placa or placa in vistas:
            continue
        vistas.add(placa)
        placas.append({'placa': placa, 'vehicle_id': v.id, 'conductor': v.driver_id.name or ''})
    return placas


class ADTPapeletaSatEstadoCuenta(models.Model):
    """Estados de adt.comercial.cuentas para filtrar programas (sin depender de adt_comercial)."""
    _name = 'adt.papeleta.sat.estado.cuenta'
    _description = 'Estado de cuenta para programas SAT'
    _order = 'sequence, id'

    name = fields.Char(string='Estado', required=True, translate=True)
    code = fields.Char(string='Código', required=True)
    sequence = fields.Integer(default=10)
    vigente = fields.Boolean(string='Vigente', help='Se marca por defecto en los programas nuevos.')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'El estado ya existe.'),
    ]


class ADTPapeletaSatPrograma(models.Model):
    _name = 'adt.papeleta.sat.programa'
    _description = 'Programa de consulta SAT'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    alcance = fields.Selection([
        ('todas', 'Toda la flota'),
        ('financiera', 'Por financiera'),
        ('filtro', 'Filtro de vehículos'),
        ('lista', 'Lista de vehículos'),
    ], string='Placas a consultar', required=True, default='financiera', tracking=True)
    # Las financieras (financiera_ids) las agrega adt_comercial, que depende de este módulo.
    estado_cuenta_ids = fields.Many2many('adt.papeleta.sat.estado.cuenta', 'adt_papeleta_sat_programa_estado_rel',
                                         'programa_id', 'estado_id', string='Estados del cronograma',
                                         default=lambda self: self._estados_vigentes(),
                                         help='Estados de la cuenta comercial a incluir. Vacío: todos los estados.')
    vehicle_domain = fields.Char(string='Filtro', default='[]')
    vehicle_ids = fields.Many2many('fleet.vehicle', 'adt_papeleta_sat_programa_vehicle_rel',
                                   'programa_id', 'vehicle_id', string='Vehículos')
    total_placas = fields.Integer(string='Placas', compute='_compute_total_placas')

    programado = fields.Boolean(string='Ejecutar automáticamente', tracking=True)
    hora = fields.Float(string='Hora', default=23.0, tracking=True, help='Hora local (zona del programa).')
    tz = fields.Selection('_tz_get', string='Zona horaria', default='America/Lima', required=True)
    lunes = fields.Boolean(default=True)
    martes = fields.Boolean(default=True)
    miercoles = fields.Boolean(string='Miércoles', default=True)
    jueves = fields.Boolean(default=True)
    viernes = fields.Boolean(default=True)
    sabado = fields.Boolean(string='Sábado', default=True)
    domingo = fields.Boolean(default=True)
    ultima_programada = fields.Datetime(string='Último lanzamiento automático', readonly=True, copy=False)

    responsable_ids = fields.Many2many('res.users', 'adt_papeleta_sat_programa_user_rel', 'programa_id', 'user_id',
                                       string='Notificar a', default=lambda self: self.env.user,
                                       help='Reciben el informe de cada ejecución y una actividad si hubo errores.')
    ejecucion_ids = fields.One2many('adt.papeleta.sat.ejecucion', 'programa_id', string='Ejecuciones')
    ejecucion_count = fields.Integer(compute='_compute_ultima')
    ultima_ejecucion_id = fields.Many2one('adt.papeleta.sat.ejecucion', string='Última ejecución',
                                          compute='_compute_ultima')
    ultimo_estado = fields.Selection(lambda self: self.env['adt.papeleta.sat.ejecucion']._fields['state'].selection,
                                     string='Último resultado', compute='_compute_ultima')

    @api.model
    def _estados_vigentes(self):
        return self.env['adt.papeleta.sat.estado.cuenta'].search([('vigente', '=', True)])

    @api.model
    def _tz_get(self):
        return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

    @api.depends('alcance', 'estado_cuenta_ids', 'vehicle_domain', 'vehicle_ids')
    def _compute_total_placas(self):
        for rec in self:
            try:
                rec.total_placas = len(rec._placas())
            except UserError:
                rec.total_placas = 0

    def _compute_ultima(self):
        Ejecucion = self.env['adt.papeleta.sat.ejecucion']
        for rec in self:
            ultima = Ejecucion.search([('programa_id', '=', rec.id)], limit=1) if rec.id else Ejecucion
            rec.ultima_ejecucion_id = ultima
            rec.ultimo_estado = ultima.state
            rec.ejecucion_count = Ejecucion.search_count([('programa_id', '=', rec.id)]) if rec.id else 0

    # ------------------------------------------------------------- alcance
    def _vehiculos(self):
        self.ensure_one()
        Vehiculo = self.env['fleet.vehicle'].sudo()
        if self.alcance == 'todas':
            return Vehiculo.search([('license_plate', '!=', False)])
        if self.alcance == 'lista':
            return self.vehicle_ids.sudo()
        if self.alcance == 'filtro':
            try:
                dominio = safe_eval(self.vehicle_domain or '[]')
            except Exception as exc:
                raise UserError(_('El filtro de vehículos no es válido: %s') % exc)
            return Vehiculo.search(dominio + [('license_plate', '!=', False)])
        # financiera
        if 'adt.comercial.cuentas' not in self.env:
            raise UserError(_('El módulo comercial (adt_comercial) no está instalado.'))
        codigos = self._financiera_codigos()
        if not codigos:
            raise UserError(_('Elija al menos una financiera del programa «%s».') % self.name)
        dominio = [('tipo_financiera_id.code', 'in', codigos), ('vehiculo_id', '!=', False)]
        if self.estado_cuenta_ids:
            dominio.append(('state', 'in', self.estado_cuenta_ids.mapped('code')))
        return self.env['adt.comercial.cuentas'].sudo().search(dominio).mapped('vehiculo_id')

    def _financiera_codigos(self):
        """Códigos de financiera elegidos; adt_comercial lo implementa con financiera_ids."""
        return []

    def _placas(self):
        return _placas_de(self._vehiculos())

    # ------------------------------------------------------------- acciones
    def action_ejecutar_ahora(self):
        self.ensure_one()
        ejecucion = self._lanzar('manual')
        return ejecucion.action_abrir()

    def action_ver_placas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Placas de «%s»') % self.name,
            'res_model': 'fleet.vehicle',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', [p['vehicle_id'] for p in self._placas()])],
        }

    def action_ver_ejecuciones(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ejecuciones'),
            'res_model': 'adt.papeleta.sat.ejecucion',
            'view_mode': 'tree,form',
            'domain': [('programa_id', '=', self.id)],
            'context': {'default_programa_id': self.id},
        }

    def _lanzar(self, origen):
        self.ensure_one()
        Ejecucion = self.env['adt.papeleta.sat.ejecucion'].sudo()
        activa = Ejecucion.search([('programa_id', '=', self.id), ('state', 'in', ACTIVAS)], limit=1)
        if activa:
            raise UserError(_('El programa «%s» ya tiene una ejecución en curso (%s).') % (self.name, activa.name))
        placas = self._placas()
        if not placas:
            raise UserError(_('El programa «%s» no tiene placas que consultar.') % self.name)
        return Ejecucion._crear(placas, origen=origen, programa=self)

    # ----------------------------------------------------------------- cron
    def _ultima_hora_programada(self, ahora_utc):
        """Último instante programado (UTC naive) igual o anterior a ahora, o None si ese día no toca."""
        self.ensure_one()
        tz = pytz.timezone(self.tz or 'America/Lima')
        local = pytz.utc.localize(ahora_utc).astimezone(tz)
        minutos = int(round((self.hora or 0.0) * 60)) % (24 * 60)
        objetivo = local.replace(hour=minutos // 60, minute=minutos % 60, second=0, microsecond=0)
        if objetivo > local:
            objetivo -= timedelta(days=1)
        if not self[DIAS[objetivo.weekday()]]:
            return None
        return objetivo.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _cron_programar_y_vigilar(self):
        ahora = fields.Datetime.now()
        for programa in self.search([('programado', '=', True)]):
            objetivo = programa._ultima_hora_programada(ahora)
            if not objetivo or ahora - objetivo > VENTANA_PROGRAMACION:
                continue
            if programa.ultima_programada and programa.ultima_programada >= objetivo:
                continue
            try:
                with self.env.cr.savepoint():
                    programa._lanzar('programado')
                    programa.ultima_programada = objetivo
            except UserError as exc:
                # Otra corrida en curso o sin placas: se reintenta en el próximo ciclo dentro de la ventana.
                _logger.info('Programa SAT %s no lanzado: %s', programa.name, exc)
        self.env['adt.papeleta.sat.ejecucion']._vigilar()


class ADTPapeletaSatEjecucion(models.Model):
    _name = 'adt.papeleta.sat.ejecucion'
    _description = 'Ejecución del monitor SAT'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _mail_post_access = 'read'  # los usuarios solo leen; pueden comentar y cancelar
    _order = 'id desc'

    name = fields.Char(string='Referencia', required=True, readonly=True, default='/', copy=False)
    programa_id = fields.Many2one('adt.papeleta.sat.programa', string='Programa', readonly=True, index=True,
                                  ondelete='set null')
    origen = fields.Selection([('manual', 'Manual'), ('programado', 'Programado')], string='Origen',
                              required=True, default='manual', readonly=True)
    usuario_id = fields.Many2one('res.users', string='Lanzada por', readonly=True,
                                 default=lambda self: self.env.user)
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En proceso'),
        ('completada', 'Completada'),
        ('con_errores', 'Con errores'),
        ('fallida', 'Fallida'),
        ('cancelada', 'Cancelada'),
    ], string='Estado', default='pendiente', required=True, readonly=True, index=True, tracking=True)
    cancelar_solicitado = fields.Boolean(readonly=True, copy=False)

    fecha_inicio = fields.Datetime(string='Inicio', readonly=True)
    fecha_fin = fields.Datetime(string='Fin', readonly=True)
    ultimo_latido = fields.Datetime(string='Último aviso del monitor', readonly=True)
    duracion = fields.Char(string='Duración', compute='_compute_duracion')
    placa_actual = fields.Char(string='Consultando', readonly=True)
    error = fields.Text(string='Problema', readonly=True)
    archivo_monitor = fields.Char(string='Resumen en el monitor', readonly=True)

    linea_ids = fields.One2many('adt.papeleta.sat.ejecucion.linea', 'ejecucion_id', string='Placas', readonly=True)
    importacion_ids = fields.One2many('adt.papeleta.sat.import', 'ejecucion_id', string='Importaciones',
                                      readonly=True)
    total_placas = fields.Integer(string='Placas', compute='_compute_totales', store=True)
    procesadas = fields.Integer(string='Procesadas', compute='_compute_totales', store=True)
    con_papeletas = fields.Integer(string='Con papeletas', compute='_compute_totales', store=True)
    sin_papeletas = fields.Integer(string='Sin papeletas', compute='_compute_totales', store=True)
    con_error = fields.Integer(string='Con error', compute='_compute_totales', store=True)
    papeletas_nuevas = fields.Integer(string='Papeletas nuevas', compute='_compute_totales', store=True)
    dejaron_de_figurar = fields.Integer(string='Dejaron de figurar', compute='_compute_totales', store=True)
    papeletas_pagadas = fields.Integer(string='Marcadas pagadas', compute='_compute_totales', store=True)
    internas_actualizadas = fields.Integer(string='Internas actualizadas', compute='_compute_totales', store=True)
    total_deuda = fields.Float(string='Deuda SAT', compute='_compute_totales', store=True)
    avance = fields.Float(string='Avance (%)', compute='_compute_totales', store=True, group_operator='avg')

    @api.depends('linea_ids.state', 'linea_ids.es_error', 'linea_ids.nuevas', 'linea_ids.resueltas',
                 'linea_ids.total_deuda', 'linea_ids.pagadas', 'linea_ids.internas_actualizadas')
    def _compute_totales(self):
        for rec in self:
            lineas = rec.linea_ids
            estados = lineas.mapped('state')
            rec.total_placas = len(lineas)
            rec.procesadas = sum(1 for e in estados if e != 'pendiente')
            rec.con_papeletas = estados.count('con_papeletas')
            rec.sin_papeletas = estados.count('sin_papeletas')
            rec.con_error = len(lineas.filtered('es_error'))
            rec.papeletas_nuevas = sum(lineas.mapped('nuevas'))
            rec.dejaron_de_figurar = sum(lineas.mapped('resueltas'))
            rec.papeletas_pagadas = sum(lineas.mapped('pagadas'))
            rec.internas_actualizadas = sum(lineas.mapped('internas_actualizadas'))
            rec.total_deuda = sum(lineas.mapped('total_deuda'))
            rec.avance = 100.0 * rec.procesadas / rec.total_placas if rec.total_placas else 0.0

    @api.depends('fecha_inicio', 'fecha_fin')
    def _compute_duracion(self):
        for rec in self:
            if not rec.fecha_inicio:
                rec.duracion = False
                continue
            segundos = int(((rec.fecha_fin or fields.Datetime.now()) - rec.fecha_inicio).total_seconds())
            rec.duracion = '%d h %02d min' % (segundos // 3600, segundos % 3600 // 60)

    # ------------------------------------------------------------ creación
    @api.model
    def _crear(self, placas, origen='manual', programa=None):
        return self.create({
            'name': self.env['ir.sequence'].next_by_code('adt.papeleta.sat.ejecucion') or '/',
            'programa_id': programa.id if programa else False,
            'origen': origen,
            'linea_ids': [(0, 0, {
                'placa': p['placa'], 'vehicle_id': p.get('vehicle_id') or False, 'conductor': p.get('conductor'),
            }) for p in placas],
        })

    @api.model
    def action_desde_vehiculos(self):
        """Acción de servidor en Flota: consulta ya las placas de los vehículos seleccionados."""
        vehiculos = self.env['fleet.vehicle'].browse(self.env.context.get('active_ids') or [])
        placas = _placas_de(vehiculos)
        if not placas:
            raise UserError(_('Los vehículos seleccionados no tienen placa.'))
        return self.sudo()._crear(placas, origen='manual').action_abrir()

    def action_abrir(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------- botones
    def action_cancelar(self):
        for rec in self:
            if rec.state == 'pendiente':
                rec.sudo()._cerrar('cancelada', error=_('Cancelada por %s antes de empezar.') % self.env.user.name)
            elif rec.state == 'en_proceso':
                rec.sudo().cancelar_solicitado = True
                rec.message_post(body=_('%s pidió cancelar; el monitor se detendrá antes de la siguiente placa.')
                                 % self.env.user.name)
        return True

    def action_reintentar_fallidas(self):
        self.ensure_one()
        lineas = self.linea_ids.filtered(lambda l: l.state in ('error', 'no_consultada', 'pendiente'))
        if not lineas:
            raise UserError(_('No hay placas con error en esta ejecución.'))
        if self.state in ACTIVAS:
            raise UserError(_('Espere a que termine la ejecución.'))
        nueva = self.sudo()._crear(
            [{'placa': l.placa, 'vehicle_id': l.vehicle_id.id, 'conductor': l.conductor} for l in lineas],
            origen='manual', programa=self.programa_id)
        nueva.message_post(body=_('Reintento de las placas con error de %s.') % self.name)
        return nueva.action_abrir()

    # ------------------------------------------------------- API del agente
    @api.model
    def _tomar(self):
        """Marca en proceso la ejecución pendiente más antigua (seguro con varios agentes)."""
        self.flush()
        self.env.cr.execute("""
            SELECT id FROM adt_papeleta_sat_ejecucion
             WHERE state = 'pendiente'
             ORDER BY id
             LIMIT 1
             FOR UPDATE SKIP LOCKED
        """)
        fila = self.env.cr.fetchone()
        if not fila:
            return None
        rec = self.browse(fila[0])
        ahora = fields.Datetime.now()
        rec.write({'state': 'en_proceso', 'fecha_inicio': ahora, 'ultimo_latido': ahora})
        rec.message_post(body=_('El monitor tomó la ejecución (%s placas).') % len(rec.linea_ids))
        return {
            'id': rec.id,
            'name': rec.name,
            'placas': [{'placa': l.placa, 'vehicle_id': str(l.vehicle_id.id or ''), 'conductor': l.conductor or ''}
                       for l in rec.linea_ids],
        }

    def _latido(self, datos):
        self.ensure_one()
        if self.state != 'en_proceso':
            return {'cancelar': True}
        self.write({'ultimo_latido': fields.Datetime.now(), 'placa_actual': (datos.get('placa') or '')[:20]})
        return {'cancelar': self.cancelar_solicitado}

    def _registrar_import(self, importacion, payload):
        """Llamado por cada consulta que llega a /import con metadata.ejecucion_id."""
        self.ensure_one()
        placa = normalizar(payload.get('placa'))
        linea = self.linea_ids.filtered(lambda l: l.placa == placa)[:1]
        if not linea:
            linea = self.env['adt.papeleta.sat.ejecucion.linea'].create({'ejecucion_id': self.id, 'placa': placa})
        linea._aplicar_resultado(payload, importacion)
        if self.state == 'en_proceso':
            self.ultimo_latido = fields.Datetime.now()

    def _finalizar(self, informe):
        self.ensure_one()
        if self.state not in ACTIVAS:
            return self.state  # informe duplicado o ejecución ya cerrada por el vigilante
        por_placa = {normalizar(r.get('placa')): r for r in informe.get('resultados') or []}
        for linea in self.linea_ids:
            r = por_placa.get(linea.placa)
            if r and linea.state == 'pendiente':
                # La consulta se hizo pero no llegó por /import (Odoo caído en ese momento).
                linea._aplicar_resultado(r, None)
                if r.get('odoo_entregado') is False:
                    linea.mensaje = ((linea.mensaje or '') + ' ' + _('(detalle no entregado a Odoo)')).strip()
        self.archivo_monitor = informe.get('archivo') or False
        error = informe.get('error')
        if error:
            estado = 'fallida'
        elif informe.get('cancelada'):
            estado = 'cancelada'
            error = _('Cancelada a pedido del usuario.')
        else:
            # Las placas que el monitor no informó pasan a "no consultada" al cerrar.
            estado = 'con_errores' if self.linea_ids.filtered(lambda l: l.es_error or l.state == 'pendiente') \
                else 'completada'
        self._cerrar(estado, error=error)
        return estado

    # ------------------------------------------------------------- cierre
    def _cerrar(self, estado, error=None):
        self.ensure_one()
        self.linea_ids.filtered(lambda l: l.state == 'pendiente').write({
            'state': 'no_consultada', 'mensaje': _('No se llegó a consultar.')})
        self.write({'state': estado, 'fecha_fin': fields.Datetime.now(), 'placa_actual': False,
                    'error': error or False})
        self._notificar()

    def _notificar(self):
        self.ensure_one()
        etiqueta = dict(self._fields['state'].selection)[self.state]
        lineas_error = self.linea_ids.filtered('es_error')
        cuerpo = _(
            '<p><b>%(estado)s</b>: %(proc)s de %(total)s placas · %(con)s con papeletas · '
            '%(nuevas)s papeletas nuevas · %(resueltas)s dejaron de figurar · %(pagadas)s marcadas pagadas · '
            '%(act)s actualizadas · %(err)s con error.</p>'
        ) % {'estado': etiqueta, 'proc': self.procesadas, 'total': self.total_placas, 'con': self.con_papeletas,
             'nuevas': self.papeletas_nuevas, 'resueltas': self.dejaron_de_figurar, 'pagadas': self.papeletas_pagadas,
             'act': self.internas_actualizadas, 'err': len(lineas_error)}
        if self.error:
            cuerpo += '<p><b>%s</b> %s</p>' % (_('Problema:'), self.error)
        if lineas_error:
            items = ''.join('<li>%s: %s</li>' % (l.placa, l.mensaje or l.state) for l in lineas_error[:15])
            if len(lineas_error) > 15:
                items += '<li>%s</li>' % (_('… y %s más') % (len(lineas_error) - 15))
            cuerpo += '<ul>%s</ul>' % items
        usuarios = (self.programa_id.responsable_ids | self.usuario_id).filtered(
            lambda u: u.active and not u.share and u != self.env.ref('base.user_root'))
        self.message_post(body=cuerpo, subject=_('SAT %s: %s') % (self.name, etiqueta),
                          partner_ids=usuarios.mapped('partner_id').ids, subtype_xmlid='mail.mt_comment')
        if self.state in ('fallida', 'con_errores'):
            for usuario in usuarios:
                try:
                    self.activity_schedule('mail.mail_activity_data_todo', user_id=usuario.id,
                                           summary=_('Revisar ejecución SAT %s') % self.name,
                                           note=self.error or _('Hubo placas con error.'))
                except Exception:
                    _logger.exception('No se pudo programar la actividad de la ejecución %s', self.id)

    @api.model
    def _vigilar(self):
        """Cierra lo que el agente no tomó o abandonó (contenedor detenido, EC2 apagada…)."""
        icp = self.env['ir.config_parameter'].sudo()
        sin_tomar = int(icp.get_param(PARAM_MIN_SIN_TOMAR, 30))
        sin_latido = int(icp.get_param(PARAM_MIN_SIN_LATIDO, 30))
        ahora = fields.Datetime.now()
        for rec in self.search([('state', '=', 'pendiente'),
                                ('create_date', '<', ahora - timedelta(minutes=sin_tomar))]):
            rec._cerrar('fallida', error=_(
                'El monitor no tomó la ejecución en %s minutos. Revise que el contenedor del agente '
                'esté encendido en la EC2 (docker ps) y que ODOO_URL/ODOO_SAT_TOKEN sean correctos.') % sin_tomar)
        for rec in self.search([('state', '=', 'en_proceso'),
                                ('ultimo_latido', '<', ahora - timedelta(minutes=sin_latido))]):
            rec._cerrar('fallida', error=_(
                'El monitor dejó de responder durante %s minutos (última placa: %s). '
                'Revise los registros del contenedor: docker logs sat-agente') % (sin_latido, rec.placa_actual or '-'))


class ADTPapeletaSatEjecucionLinea(models.Model):
    _name = 'adt.papeleta.sat.ejecucion.linea'
    _description = 'Placa de una ejecución SAT'
    _order = 'id'

    ejecucion_id = fields.Many2one('adt.papeleta.sat.ejecucion', required=True, ondelete='cascade', index=True)
    placa = fields.Char(string='Placa', required=True, index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo')
    conductor = fields.Char(string='Conductor')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('con_papeletas', 'Con papeletas'),
        ('sin_papeletas', 'Sin papeletas'),
        ('error', 'Error'),
        ('no_consultada', 'No consultada'),
    ], string='Resultado', default='pendiente', required=True)
    es_error = fields.Boolean(compute='_compute_es_error', store=True)
    mensaje = fields.Char(string='Detalle')
    total_papeletas = fields.Integer(string='Papeletas')
    nuevas = fields.Integer(string='Nuevas')
    resueltas = fields.Integer(string='Dejaron de figurar')
    pagadas = fields.Integer(string='Marcadas pagadas')
    internas_actualizadas = fields.Integer(string='Internas actualizadas')
    total_deuda = fields.Float(string='Deuda SAT')
    consultado_en = fields.Datetime(string='Consultada')
    importacion_id = fields.Many2one('adt.papeleta.sat.import', string='Importación', ondelete='set null')

    @api.depends('state', 'importacion_id.state')
    def _compute_es_error(self):
        for rec in self:
            rec.es_error = rec.state in ('error', 'no_consultada') or rec.importacion_id.state == 'error'

    def _aplicar_resultado(self, datos, importacion):
        self.ensure_one()
        estado = datos.get('estado')
        nuevas, resueltas = datos.get('nuevas'), datos.get('resueltas')
        valores = {
            'state': estado if estado in (CON_PAPELETAS, SIN_PAPELETAS) else 'error',
            'mensaje': (datos.get('mensaje') or '')[:250] or False,
            'total_papeletas': datos.get('total_papeletas') or 0,
            'nuevas': len(nuevas) if isinstance(nuevas, list) else (nuevas or 0),
            'resueltas': len(resueltas) if isinstance(resueltas, list) else (resueltas or 0),
            'total_deuda': datos.get('total_deuda') or 0.0,
            'consultado_en': fields.Datetime.now(),
        }
        if importacion:
            valores.update(importacion_id=importacion.id, pagadas=importacion.pagadas,
                           internas_actualizadas=importacion.internas_actualizadas)
            if importacion.state == 'error':
                valores['mensaje'] = (_('Error al registrar en Odoo: %s') % (importacion.error or ''))[:250]
        self.write(valores)
