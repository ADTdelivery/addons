# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AdtMecanico(models.Model):
    _name = 'adt.mecanico'
    _description = 'Mecánico Responsable'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # Información Personal
    name = fields.Char(string='Nombre Completo', required=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Usuario Relacionado',
                               help='Usuario de Odoo asociado a este mecánico')
    dni = fields.Char(string='DNI', required=True, index=True, tracking=True)
    fecha_nacimiento = fields.Date(string='Fecha de Nacimiento')
    edad = fields.Integer(string='Edad', compute='_compute_edad')
    foto = fields.Image(string='Fotografía', max_width=300, max_height=300)

    # Contacto
    telefono = fields.Char(string='Teléfono', tracking=True)
    email = fields.Char(string='Correo Electrónico')
    direccion = fields.Text(string='Dirección')

    # Información Laboral
    fecha_ingreso = fields.Date(string='Fecha de Ingreso', required=True, default=fields.Date.today, tracking=True)
    estado = fields.Selection([
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('licencia', 'Licencia'),
        ('vacaciones', 'Vacaciones')
    ], string='Estado', default='activo', required=True, tracking=True)

    # Especialización
    especialidad = fields.Selection([
        ('general', 'Mecánica General'),
        ('motor', 'Motor'),
        ('electrico', 'Sistema Eléctrico'),
        ('frenos', 'Frenos y Suspensión'),
        ('transmision', 'Transmisión'),
        ('carroceria', 'Carrocería'),
        ('pintura', 'Pintura'),
        ('diagnostico', 'Diagnóstico Electrónico')
    ], string='Especialidad Principal', default='general', required=True)

    nivel_experiencia = fields.Selection([
        ('aprendiz', 'Aprendiz'),
        ('junior', 'Junior'),
        ('senior', 'Senior'),
        ('experto', 'Experto'),
        ('master', 'Master')
    ], string='Nivel de Experiencia', default='junior', required=True)

    anos_experiencia = fields.Integer(string='Años de Experiencia')
    certificaciones = fields.Text(string='Certificaciones')
    marcas_especializadas = fields.Char(string='Marcas Especializadas')

    # Firma Digital
    firma_digital = fields.Binary(string='Firma Digital', attachment=True)

    # Trabajos y Desempeño
    trabajo_ids = fields.One2many('adt.trabajo', 'mecanico_id', string='Trabajos Asignados')
    trabajos_activos = fields.Integer(string='Trabajos Activos', compute='_compute_carga_trabajo', store=True)
    trabajos_completados = fields.Integer(string='Trabajos Completados', compute='_compute_estadisticas', store=True)

    # Métricas de Desempeño
    eficiencia_promedio = fields.Float(string='Eficiencia Promedio %', compute='_compute_estadisticas', store=True)
    tasa_retrabajo = fields.Float(string='Tasa de Retrabajo %', compute='_compute_estadisticas', store=True)
    horas_trabajadas_total = fields.Float(string='Horas Trabajadas Total', compute='_compute_estadisticas')

    # Comisiones
    comision_acumulada = fields.Monetary(string='Comisión Acumulada', compute='_compute_comisiones', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)

    # Control
    active = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        ('dni_unique', 'UNIQUE(dni)', 'Ya existe un mecánico con este DNI.')
    ]

    @api.depends('fecha_nacimiento')
    def _compute_edad(self):
        for record in self:
            if record.fecha_nacimiento:
                today = fields.Date.today()
                record.edad = today.year - record.fecha_nacimiento.year - (
                    (today.month, today.day) < (record.fecha_nacimiento.month, record.fecha_nacimiento.day)
                )
            else:
                record.edad = 0

    @api.depends('trabajo_ids', 'trabajo_ids.state')
    def _compute_carga_trabajo(self):
        for record in self:
            record.trabajos_activos = len(record.trabajo_ids.filtered(lambda t: t.state == 'in_progress'))

    @api.depends('trabajo_ids', 'trabajo_ids.eficiencia', 'trabajo_ids.state')
    def _compute_estadisticas(self):
        for record in self:
            trabajos_completados = record.trabajo_ids.filtered(lambda t: t.state == 'done')
            record.trabajos_completados = len(trabajos_completados)

            # Eficiencia promedio
            if trabajos_completados:
                eficiencias = trabajos_completados.filtered(lambda t: t.eficiencia > 0).mapped('eficiencia')
                record.eficiencia_promedio = sum(eficiencias) / len(eficiencias) if eficiencias else 0
            else:
                record.eficiencia_promedio = 0

            # Tasa de retrabajo
            trabajos_con_retrabajo = record.trabajo_ids.filtered(lambda t: t.es_retrabajo)
            if record.trabajos_completados > 0:
                record.tasa_retrabajo = (len(trabajos_con_retrabajo) / record.trabajos_completados) * 100
            else:
                record.tasa_retrabajo = 0

            # Horas trabajadas
            record.horas_trabajadas_total = sum(trabajos_completados.mapped('horas_reales'))

    @api.depends('trabajo_ids', 'trabajo_ids.comision_mecanico')
    def _compute_comisiones(self):
        for record in self:
            trabajos_completados = record.trabajo_ids.filtered(lambda t: t.state == 'done')
            record.comision_acumulada = sum(trabajos_completados.mapped('comision_mecanico'))

    @api.constrains('trabajos_activos')
    def _check_carga_trabajo(self):
        """Alertar si mecánico está sobrecargado (más de 5 trabajos activos)"""
        for record in self:
            if record.trabajos_activos > 5:
                # Solo advertencia, no bloqueamos
                _logger = logging.getLogger(__name__)
                _logger.warning(f"Mecánico {record.name} tiene {record.trabajos_activos} trabajos activos (sobrecargado)")

    def action_ver_trabajos(self):
        """Ver trabajos del mecánico"""
        self.ensure_one()
        return {
            'name': _('Trabajos de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'adt.trabajo',
            'view_mode': 'tree,form,kanban',
            'domain': [('mecanico_id', '=', self.id)],
            'context': {'default_mecanico_id': self.id}
        }

    def action_ver_estadisticas(self):
        """Ver estadísticas detalladas"""
        self.ensure_one()
        return {
            'name': _('Estadísticas de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'adt.mecanico',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
