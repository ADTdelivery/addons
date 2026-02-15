# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AdtInspeccion(models.Model):
    _name = 'adt.inspeccion'
    _description = 'Inspección de Ingreso'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inspeccion desc'

    name = fields.Char(string='Número de Inspección', compute='_compute_name', store=True)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden de Mantenimiento', required=True, ondelete='cascade')
    vehiculo_id = fields.Many2one('adt.vehiculo', string='Vehículo', required=True)
    kilometraje = fields.Float(string='Kilometraje al Ingreso')

    # Inspector
    inspector_id = fields.Many2one('res.users', string='Inspector', default=lambda self: self.env.user, tracking=True)
    fecha_inspeccion = fields.Datetime(string='Fecha de Inspección', default=fields.Datetime.now, required=True)

    # Sistemas a Inspeccionar (8 sistemas)
    sistema_motor = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Motor', required=True, tracking=True)
    obs_motor = fields.Text(string='Observaciones Motor')

    sistema_transmision = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Transmisión', required=True, tracking=True)
    obs_transmision = fields.Text(string='Observaciones Transmisión')

    sistema_frenos = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Frenos', required=True, tracking=True)
    obs_frenos = fields.Text(string='Observaciones Frenos')

    sistema_suspension = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Suspensión', required=True, tracking=True)
    obs_suspension = fields.Text(string='Observaciones Suspensión')

    sistema_electrico = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Sistema Eléctrico', required=True, tracking=True)
    obs_electrico = fields.Text(string='Observaciones Sistema Eléctrico')

    sistema_llantas = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Llantas', required=True, tracking=True)
    obs_llantas = fields.Text(string='Observaciones Llantas')

    sistema_carroceria = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Carrocería', required=True, tracking=True)
    obs_carroceria = fields.Text(string='Observaciones Carrocería')

    sistema_accesorios = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Accesorios', required=True, tracking=True)
    obs_accesorios = fields.Text(string='Observaciones Accesorios')

    # Checklist Adicional
    nivel_combustible = fields.Selection([
        ('vacio', 'Vacío'),
        ('1/4', '1/4'),
        ('1/2', '1/2'),
        ('3/4', '3/4'),
        ('lleno', 'Lleno')
    ], string='Nivel de Combustible')
    objetos_personales = fields.Text(string='Objetos Personales en Vehículo')
    documentos_vehiculo = fields.Text(string='Documentos en el Vehículo')

    # Evidencia Fotográfica
    foto_frontal = fields.Binary(string='Foto Frontal', attachment=True)
    foto_lateral_izq = fields.Binary(string='Foto Lateral Izquierda', attachment=True)
    foto_lateral_der = fields.Binary(string='Foto Lateral Derecha', attachment=True)
    foto_trasera = fields.Binary(string='Foto Trasera', attachment=True)
    foto_tablero = fields.Binary(string='Foto Tablero', attachment=True)
    fotos_danos = fields.Many2many('ir.attachment', string='Fotos de Daños')

    # Estado
    completado = fields.Boolean(string='Inspección Completada', compute='_compute_completado', store=True)
    firma_cliente = fields.Binary(string='Firma del Cliente', attachment=True)
    fecha_firma = fields.Datetime(string='Fecha de Firma')

    # Observaciones Generales
    observaciones_generales = fields.Text(string='Observaciones Generales')

    @api.depends('orden_id.name')
    def _compute_name(self):
        for record in self:
            if record.orden_id:
                record.name = f"INS-{record.orden_id.name}"
            else:
                record.name = 'Nueva Inspección'

    @api.depends('sistema_motor', 'sistema_transmision', 'sistema_frenos',
                 'sistema_suspension', 'sistema_electrico', 'sistema_llantas',
                 'sistema_carroceria', 'sistema_accesorios')
    def _compute_completado(self):
        for record in self:
            record.completado = all([
                record.sistema_motor,
                record.sistema_transmision,
                record.sistema_frenos,
                record.sistema_suspension,
                record.sistema_electrico,
                record.sistema_llantas,
                record.sistema_carroceria,
                record.sistema_accesorios
            ])

    @api.onchange('sistema_motor', 'sistema_transmision', 'sistema_frenos',
                  'sistema_suspension', 'sistema_electrico', 'sistema_llantas',
                  'sistema_carroceria', 'sistema_accesorios')
    def _onchange_sistemas(self):
        """Sugerencias automáticas según estado"""
        sugerencias = []

        if self.sistema_motor == 'malo':
            sugerencias.append('Revisión completa de motor')
        if self.sistema_frenos in ['malo', 'regular']:
            sugerencias.append('Cambio de pastillas y/o revisión de sistema de frenos')
        if self.sistema_llantas == 'malo':
            sugerencias.append('Reemplazo de llantas')
        if self.sistema_electrico == 'malo':
            sugerencias.append('Diagnóstico del sistema eléctrico')

        if sugerencias and self.orden_id:
            return {
                'warning': {
                    'title': 'Trabajos Sugeridos',
                    'message': '\n'.join(f'• {s}' for s in sugerencias)
                }
            }

    def action_firmar(self):
        """Solicitar firma del cliente"""
        self.ensure_one()
        if not self.completado:
            raise UserError(_('Debe completar la inspección de todos los sistemas antes de firmar.'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.inspeccion',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'solicitar_firma': True}
        }

    def action_exportar_pdf(self):
        """Exportar inspección a PDF"""
        self.ensure_one()
        return self.env.ref('adt_mantenimiento_mecanico.action_report_inspeccion').report_action(self)


class AdtControlFluidos(models.Model):
    _name = 'adt.control.fluidos'
    _description = 'Control de Fluidos'
    _order = 'fecha_control desc'

    name = fields.Char(string='Número', compute='_compute_name', store=True)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')
    fecha_control = fields.Datetime(string='Fecha de Control', default=fields.Datetime.now)

    # Aceite de Motor
    aceite_nivel = fields.Selection([
        ('bajo', 'Bajo'),
        ('normal', 'Normal'),
        ('alto', 'Alto')
    ], string='Nivel de Aceite')
    aceite_estado = fields.Selection([
        ('limpio', 'Limpio'),
        ('sucio', 'Sucio'),
        ('muy_sucio', 'Muy Sucio'),
        ('contaminado', 'Contaminado')
    ], string='Estado del Aceite')
    aceite_obs = fields.Text(string='Observaciones Aceite')
    aceite_requiere_cambio = fields.Boolean(string='Requiere Cambio de Aceite', compute='_compute_requiere_cambio', store=True)

    # Refrigerante
    refrigerante_nivel = fields.Selection([
        ('bajo', 'Bajo'),
        ('normal', 'Normal'),
        ('alto', 'Alto')
    ], string='Nivel de Refrigerante')
    refrigerante_estado = fields.Selection([
        ('limpio', 'Limpio'),
        ('sucio', 'Sucio'),
        ('contaminado', 'Contaminado con Aceite')
    ], string='Estado del Refrigerante')
    refrigerante_obs = fields.Text(string='Observaciones Refrigerante')
    refrigerante_alerta = fields.Boolean(string='Alerta Refrigerante', compute='_compute_alertas')

    # Líquido de Frenos
    frenos_nivel = fields.Selection([
        ('bajo', 'Bajo'),
        ('normal', 'Normal'),
        ('alto', 'Alto')
    ], string='Nivel de Líquido de Frenos')
    frenos_estado = fields.Selection([
        ('limpio', 'Limpio'),
        ('sucio', 'Sucio'),
        ('contaminado', 'Contaminado')
    ], string='Estado del Líquido de Frenos')
    frenos_obs = fields.Text(string='Observaciones Líquido Frenos')
    frenos_alerta_seguridad = fields.Boolean(string='Alerta Seguridad Frenos', compute='_compute_alertas')

    # Aceite de Transmisión
    transmision_nivel = fields.Selection([
        ('bajo', 'Bajo'),
        ('normal', 'Normal'),
        ('alto', 'Alto')
    ], string='Nivel Aceite Transmisión')
    transmision_estado = fields.Selection([
        ('limpio', 'Limpio'),
        ('sucio', 'Sucio'),
        ('muy_sucio', 'Muy Sucio')
    ], string='Estado Aceite Transmisión')
    transmision_obs = fields.Text(string='Observaciones Transmisión')

    # Otros Fluidos
    otros_fluidos = fields.Text(string='Otros Fluidos Verificados')

    # Control
    completado = fields.Boolean(string='Control Completado', default=False)
    responsable_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user)

    @api.depends('orden_id.name')
    def _compute_name(self):
        for record in self:
            if record.orden_id:
                record.name = f"CF-{record.orden_id.name}"
            else:
                record.name = 'Nuevo Control'

    @api.depends('aceite_nivel', 'aceite_estado')
    def _compute_requiere_cambio(self):
        for record in self:
            record.aceite_requiere_cambio = (
                record.aceite_nivel == 'bajo' or
                record.aceite_estado in ['muy_sucio', 'contaminado']
            )

    @api.depends('refrigerante_estado', 'frenos_nivel')
    def _compute_alertas(self):
        for record in self:
            # Alerta crítica si refrigerante contaminado con aceite
            record.refrigerante_alerta = (record.refrigerante_estado == 'contaminado')

            # Alerta de seguridad si líquido de frenos bajo
            record.frenos_alerta_seguridad = (record.frenos_nivel == 'bajo')

    @api.constrains('aceite_nivel', 'refrigerante_nivel', 'frenos_nivel')
    def _check_niveles_altos(self):
        """Validar niveles altos requieren observación"""
        for record in self:
            if record.aceite_nivel == 'alto' and not record.aceite_obs:
                raise ValidationError(_('Nivel de aceite alto requiere observación explicativa.'))
            if record.refrigerante_nivel == 'alto' and not record.refrigerante_obs:
                raise ValidationError(_('Nivel de refrigerante alto requiere observación explicativa.'))
