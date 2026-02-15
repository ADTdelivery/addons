# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AdtManoObra(models.Model):
    _name = 'adt.mano.obra'
    _description = 'Mano de Obra'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Secuencia', default=10)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')
    trabajo_id = fields.Many2one('adt.trabajo', string='Trabajo Relacionado', required=True)

    # Descripción
    name = fields.Char(string='Descripción', required=True)
    detalle = fields.Text(string='Detalle del Trabajo')

    # Mecánico
    mecanico_id = fields.Many2one('adt.mecanico', string='Mecánico', required=True)
    especialidad = fields.Selection(related='mecanico_id.especialidad', string='Especialidad')
    nivel_experiencia = fields.Selection(related='mecanico_id.nivel_experiencia', string='Nivel')

    # Tiempos
    horas_estimadas = fields.Float(string='Horas Estimadas', required=True)
    horas_reales = fields.Float(string='Horas Reales Trabajadas')
    fecha_inicio = fields.Datetime(string='Inicio')
    fecha_fin = fields.Datetime(string='Fin')

    # Pausas
    total_pausas = fields.Float(string='Total Pausas (hrs)', default=0.0,
                                 help='Tiempo en pausas que no se debe facturar')
    horas_efectivas = fields.Float(string='Horas Efectivas', compute='_compute_horas_efectivas', store=True)

    # Complejidad y Tarifa
    complejidad = fields.Selection([
        ('basico', 'Básico'),
        ('estandar', 'Estándar'),
        ('avanzado', 'Avanzado'),
        ('experto', 'Experto')
    ], string='Nivel de Complejidad', default='estandar', required=True)

    precio_hora_base = fields.Monetary(string='Precio/Hora Base', required=True, currency_field='currency_id')
    factor_complejidad = fields.Float(string='Factor Complejidad', compute='_compute_factor_complejidad')
    precio_hora_final = fields.Monetary(string='Precio/Hora Final', compute='_compute_precio_final',
                                         store=True, currency_field='currency_id')

    # Cálculos
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Eficiencia
    eficiencia = fields.Float(string='Eficiencia %', compute='_compute_eficiencia', store=True)
    eficiencia_color = fields.Char(string='Color Eficiencia', compute='_compute_eficiencia_color')

    # Comisiones
    porcentaje_comision = fields.Float(string='% Comisión Base', default=10.0)
    bonificacion_eficiencia = fields.Float(string='Bonificación Eficiencia %', default=0.0)
    comision_total = fields.Monetary(string='Comisión Total', compute='_compute_comision',
                                      store=True, currency_field='currency_id')

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('in_progress', 'En Proceso'),
        ('paused', 'Pausado'),
        ('done', 'Completado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', related='trabajo_id.state', store=True)

    # Observaciones
    observaciones = fields.Text(string='Observaciones')

    @api.depends('horas_reales', 'total_pausas')
    def _compute_horas_efectivas(self):
        for record in self:
            if record.horas_reales:
                record.horas_efectivas = record.horas_reales - record.total_pausas
            else:
                record.horas_efectivas = 0.0

    @api.depends('complejidad')
    def _compute_factor_complejidad(self):
        factores = {
            'basico': 1.0,
            'estandar': 1.25,
            'avanzado': 1.50,
            'experto': 2.0
        }
        for record in self:
            record.factor_complejidad = factores.get(record.complejidad, 1.0)

    @api.depends('precio_hora_base', 'factor_complejidad')
    def _compute_precio_final(self):
        for record in self:
            record.precio_hora_final = record.precio_hora_base * record.factor_complejidad

    @api.depends('horas_estimadas', 'precio_hora_final')
    def _compute_subtotal(self):
        for record in self:
            # Facturar según horas estimadas, no reales (beneficio para taller si es eficiente)
            record.subtotal = record.horas_estimadas * record.precio_hora_final

    @api.depends('horas_estimadas', 'horas_efectivas')
    def _compute_eficiencia(self):
        for record in self:
            if record.horas_efectivas and record.horas_efectivas > 0:
                record.eficiencia = (record.horas_estimadas / record.horas_efectivas) * 100
            else:
                record.eficiencia = 0.0

    @api.depends('eficiencia')
    def _compute_eficiencia_color(self):
        for record in self:
            if record.eficiencia >= 100:
                record.eficiencia_color = 'success'  # Verde
            elif record.eficiencia >= 80:
                record.eficiencia_color = 'warning'  # Amarillo
            else:
                record.eficiencia_color = 'danger'   # Rojo

    @api.depends('subtotal', 'porcentaje_comision', 'eficiencia', 'bonificacion_eficiencia')
    def _compute_comision(self):
        for record in self:
            comision_base = record.subtotal * (record.porcentaje_comision / 100)

            # Bonificación si eficiencia > 100%
            if record.eficiencia > 100:
                bonus = comision_base * (record.bonificacion_eficiencia / 100)
                record.comision_total = comision_base + bonus
            # Penalización si eficiencia < 70%
            elif record.eficiencia < 70 and record.eficiencia > 0:
                penalizacion = comision_base * 0.10
                record.comision_total = comision_base - penalizacion
            else:
                record.comision_total = comision_base

    @api.onchange('mecanico_id')
    def _onchange_mecanico_id(self):
        """Sugerir precio/hora según nivel del mecánico"""
        if self.mecanico_id:
            # Tarifas sugeridas según nivel
            tarifas = {
                'aprendiz': 25.0,
                'junior': 30.0,
                'senior': 40.0,
                'experto': 50.0,
                'master': 60.0
            }
            nivel = self.mecanico_id.nivel_experiencia
            self.precio_hora_base = tarifas.get(nivel, 30.0)

    @api.constrains('horas_reales')
    def _check_horas_reales(self):
        """Alertar si horas reales exceden significativamente las estimadas"""
        for record in self:
            if record.horas_reales and record.horas_estimadas:
                if record.horas_reales > (record.horas_estimadas * 2.5):
                    # Solo advertencia en log, no bloqueo
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning(
                        f"Mano de obra {record.id}: Horas reales ({record.horas_reales}) "
                        f"exceden 250% de las estimadas ({record.horas_estimadas})"
                    )

    def action_iniciar(self):
        """Iniciar trabajo"""
        self.ensure_one()
        self.fecha_inicio = fields.Datetime.now()
        self.trabajo_id.action_iniciar()

    def action_pausar(self):
        """Pausar trabajo"""
        self.ensure_one()
        self.trabajo_id.action_pausar()

    def action_completar(self):
        """Completar trabajo"""
        self.ensure_one()
        if not self.horas_reales:
            raise UserError(_('Debe registrar las horas reales trabajadas.'))

        self.fecha_fin = fields.Datetime.now()
        self.trabajo_id.horas_reales = self.horas_reales
        self.trabajo_id.action_completar()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Trabajo Completado'),
                'message': _('Eficiencia: %.1f%% - Comisión: %.2f') % (self.eficiencia, self.comision_total),
                'type': 'success' if self.eficiencia >= 100 else 'warning',
            }
        }


class AdtTarifaManoObra(models.Model):
    _name = 'adt.tarifa.mano.obra'
    _description = 'Tarifa de Mano de Obra'
    _order = 'sequence'

    sequence = fields.Integer(string='Secuencia', default=10)
    name = fields.Char(string='Nombre de Tarifa', required=True)
    codigo = fields.Char(string='Código')

    # Tipo de Trabajo
    tipo_trabajo = fields.Selection([
        ('preventivo', 'Preventivo'),
        ('correctivo', 'Correctivo'),
        ('diagnostico', 'Diagnóstico'),
        ('reparacion', 'Reparación'),
        ('general', 'General')
    ], string='Tipo de Trabajo', default='general')

    # Complejidad
    complejidad = fields.Selection([
        ('basico', 'Básico'),
        ('estandar', 'Estándar'),
        ('avanzado', 'Avanzado'),
        ('experto', 'Experto')
    ], string='Complejidad', required=True)

    # Tarifa
    precio_hora = fields.Monetary(string='Precio por Hora', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Vigencia
    fecha_inicio = fields.Date(string='Válido Desde', required=True, default=fields.Date.today)
    fecha_fin = fields.Date(string='Válido Hasta')
    active = fields.Boolean(string='Activo', default=True)

    # Descripción
    descripcion = fields.Text(string='Descripción')
