# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class AdtDiagnostico(models.Model):
    _name = 'adt.diagnostico'
    _description = 'Diagnóstico Técnico'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Diagnóstico', compute='_compute_name', store=True)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')

    # Motivo del Cliente
    motivo_cliente = fields.Text(string='Motivo del Cliente', required=True, tracking=True,
                                  help='¿Qué problema reporta el cliente?')

    # Diagnóstico Técnico
    diagnostico_tecnico = fields.Text(string='Diagnóstico Técnico', required=True, tracking=True,
                                       help='Evaluación profesional del mecánico')
    causa_raiz = fields.Text(string='Causa Raíz', tracking=True)
    gravedad = fields.Selection([
        ('leve', 'Leve'),
        ('moderada', 'Moderada'),
        ('grave', 'Grave'),
        ('critica', 'Crítica')
    ], string='Gravedad', default='moderada', tracking=True)

    # Responsable
    mecanico_id = fields.Many2one('adt.mecanico', string='Mecánico Diagnosticador', tracking=True)
    fecha_diagnostico = fields.Datetime(string='Fecha de Diagnóstico', default=fields.Datetime.now)
    tiempo_diagnostico = fields.Float(string='Tiempo Empleado (min)', help='Tiempo en minutos')

    # Estado
    completado = fields.Boolean(string='Diagnóstico Completado', default=False, tracking=True)

    @api.depends('orden_id.name')
    def _compute_name(self):
        for record in self:
            if record.orden_id:
                record.name = f"DIAG-{record.orden_id.name}"
            else:
                record.name = 'Nuevo Diagnóstico'


class AdtTrabajo(models.Model):
    _name = 'adt.trabajo'
    _description = 'Trabajo a Realizar'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Código', readonly=True, copy=False)
    sequence = fields.Integer(string='Secuencia', default=10)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')

    # Descripción del Trabajo
    descripcion = fields.Text(string='Descripción del Trabajo', required=True, tracking=True)
    tipo = fields.Selection([
        ('preventivo', 'Preventivo'),
        ('correctivo', 'Correctivo'),
        ('diagnostico', 'Diagnóstico'),
        ('reparacion', 'Reparación'),
        ('reemplazo', 'Reemplazo')
    ], string='Tipo de Trabajo', required=True, default='correctivo', tracking=True)

    # Prioridad
    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente')
    ], string='Prioridad', default='media', tracking=True)

    # Asignación
    mecanico_id = fields.Many2one('adt.mecanico', string='Mecánico Asignado', tracking=True)
    especialidad_requerida = fields.Selection(related='mecanico_id.especialidad', string='Especialidad')

    # Tiempos
    tiempo_estimado = fields.Float(string='Tiempo Estimado (hrs)', required=True, tracking=True)
    fecha_inicio = fields.Datetime(string='Fecha de Inicio')
    fecha_fin = fields.Datetime(string='Fecha de Fin')
    horas_reales = fields.Float(string='Horas Reales', tracking=True)

    # Eficiencia
    eficiencia = fields.Float(string='Eficiencia %', compute='_compute_eficiencia', store=True,
                               help='(Tiempo Estimado / Tiempo Real) * 100')

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('assigned', 'Asignado'),
        ('in_progress', 'En Proceso'),
        ('paused', 'Pausado'),
        ('done', 'Completado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True)

    # Costos
    precio_hora = fields.Monetary(string='Precio por Hora', currency_field='currency_id')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Comisión del Mecánico
    porcentaje_comision = fields.Float(string='% Comisión', default=10.0)
    comision_mecanico = fields.Monetary(string='Comisión Mecánico', compute='_compute_comision', store=True, currency_field='currency_id')

    # Control de Calidad
    es_retrabajo = fields.Boolean(string='Es Retrabajo', default=False,
                                   help='Indica si este trabajo corrige un trabajo previo')
    trabajo_previo_id = fields.Many2one('adt.trabajo', string='Trabajo Previo Relacionado')

    # Observaciones
    observaciones = fields.Text(string='Observaciones')
    motivo_pausa = fields.Text(string='Motivo de Pausa')

    # Autorización
    autorizado = fields.Boolean(string='Autorizado por Cliente', default=False)
    motivo_rechazo = fields.Text(string='Motivo de Rechazo')

    @api.model
    def create(self, vals):
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('adt.trabajo') or _('Nuevo')
        return super(AdtTrabajo, self).create(vals)

    @api.depends('horas_reales', 'tiempo_estimado')
    def _compute_eficiencia(self):
        for record in self:
            if record.horas_reales and record.horas_reales > 0:
                record.eficiencia = (record.tiempo_estimado / record.horas_reales) * 100
            else:
                record.eficiencia = 0

    @api.depends('tiempo_estimado', 'precio_hora')
    def _compute_subtotal(self):
        for record in self:
            record.subtotal = record.tiempo_estimado * record.precio_hora

    @api.depends('subtotal', 'porcentaje_comision', 'eficiencia')
    def _compute_comision(self):
        for record in self:
            comision_base = record.subtotal * (record.porcentaje_comision / 100)

            # Bonificación por eficiencia > 100%
            if record.eficiencia > 100:
                bonus = comision_base * 0.05  # 5% extra
                record.comision_mecanico = comision_base + bonus
            # Penalización por retrabajo
            elif record.es_retrabajo:
                penalizacion = comision_base * 0.10  # -10%
                record.comision_mecanico = comision_base - penalizacion
            else:
                record.comision_mecanico = comision_base

    @api.constrains('horas_reales')
    def _check_horas_reales(self):
        """Alertar si las horas reales exceden significativamente las estimadas"""
        for record in self:
            if record.horas_reales and record.tiempo_estimado:
                if record.horas_reales > (record.tiempo_estimado * 2):
                    # Solo advertencia, no bloqueo
                    _logger = logging.getLogger(__name__)
                    _logger.warning(f"Trabajo {record.name}: Horas reales ({record.horas_reales}) exceden el doble del estimado ({record.tiempo_estimado})")

    def action_asignar(self):
        """Asignar trabajo a mecánico"""
        self.ensure_one()
        if not self.mecanico_id:
            raise UserError(_('Debe seleccionar un mecánico.'))
        self.state = 'assigned'

    def action_iniciar(self):
        """Iniciar trabajo"""
        self.ensure_one()
        self.state = 'in_progress'
        self.fecha_inicio = fields.Datetime.now()

    def action_pausar(self):
        """Pausar trabajo"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.trabajo',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'solicitar_motivo_pausa': True}
        }

    def action_completar(self):
        """Completar trabajo"""
        self.ensure_one()
        if not self.horas_reales:
            raise UserError(_('Debe registrar las horas reales trabajadas.'))
        self.state = 'done'
        self.fecha_fin = fields.Datetime.now()

    def action_cancelar(self):
        """Cancelar trabajo"""
        self.ensure_one()
        self.state = 'cancelled'
