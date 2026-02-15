# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class AdtOrdenMantenimiento(models.Model):
    _name = 'adt.orden.mantenimiento'
    _description = 'Orden de Mantenimiento'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    # Información Básica
    name = fields.Char(string='Número de Orden', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo'))
    fecha_ingreso = fields.Datetime(string='Fecha y Hora de Ingreso', required=True, default=fields.Datetime.now, tracking=True)

    # Tipo de Servicio
    tipo_servicio = fields.Selection([
        ('preventivo', 'Preventivo'),
        ('correctivo', 'Correctivo'),
        ('predictivo', 'Predictivo'),
        ('emergencia', 'Emergencia'),
        ('garantia', 'Garantía')
    ], string='Tipo de Servicio', required=True, default='correctivo', tracking=True)

    # Prioridad
    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica')
    ], string='Prioridad', required=True, default='media', tracking=True)

    # Ubicación y Responsable
    sucursal_id = fields.Many2one('res.company', string='Sucursal', default=lambda self: self.env.company)
    asesor_id = fields.Many2one('res.users', string='Asesor de Servicio', default=lambda self: self.env.user, required=True, tracking=True)

    # Cliente y Vehículo
    cliente_id = fields.Many2one('res.partner', string='Cliente', required=True, tracking=True)
    vehiculo_id = fields.Many2one('adt.vehiculo', string='Vehículo', required=True, tracking=True, domain="[('cliente_id', '=', cliente_id)]")

    # Datos del Vehículo (copiados para histórico)
    kilometraje = fields.Float(string='Kilometraje al Ingreso', tracking=True)
    vehiculo_placa = fields.Char(related='vehiculo_id.placa', string='Placa', store=True)
    vehiculo_marca = fields.Char(related='vehiculo_id.marca_id.name', string='Marca', store=True)
    vehiculo_modelo = fields.Char(related='vehiculo_id.modelo', string='Modelo', store=True)

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('inspeccion', 'En Inspección'),
        ('diagnostico', 'En Diagnóstico'),
        ('cotizacion', 'Cotización Pendiente'),
        ('aprobado', 'Aprobado'),
        ('in_progress', 'En Proceso'),
        ('quality_check', 'Control de Calidad'),
        ('done', 'Completado'),
        ('invoiced', 'Facturado'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True)

    # Inspección
    inspeccion_id = fields.Many2one('adt.inspeccion', string='Inspección de Ingreso')

    # Diagnóstico y Trabajos
    diagnostico_id = fields.Many2one('adt.diagnostico', string='Diagnóstico')
    trabajo_ids = fields.One2many('adt.trabajo', 'orden_id', string='Trabajos a Realizar')
    cantidad_trabajos = fields.Integer(string='Cantidad de Trabajos', compute='_compute_trabajos', store=True)

    # Control de Fluidos
    control_fluidos_id = fields.Many2one('adt.control.fluidos', string='Control de Fluidos')

    # Repuestos y Mano de Obra
    repuesto_ids = fields.One2many('adt.orden.repuesto', 'orden_id', string='Repuestos')
    mano_obra_ids = fields.One2many('adt.mano.obra', 'orden_id', string='Mano de Obra')

    # Control de Calidad
    control_calidad_id = fields.Many2one('adt.control.calidad', string='Control de Calidad')
    control_calidad_aprobado = fields.Boolean(string='CC Aprobado', related='control_calidad_id.aprobado', store=True)

    # Estado Final
    estado_final = fields.Selection([
        ('excelente', 'Excelente'),
        ('bueno', 'Bueno'),
        ('aceptable', 'Aceptable'),
        ('requiere_revision', 'Requiere Revisión Adicional')
    ], string='Estado Final', tracking=True)

    # Costos y Facturación
    total_repuestos = fields.Monetary(string='Total Repuestos', compute='_compute_totales', store=True, currency_field='currency_id')
    total_mano_obra = fields.Monetary(string='Total Mano de Obra', compute='_compute_totales', store=True, currency_field='currency_id')
    descuento = fields.Monetary(string='Descuento', currency_field='currency_id', tracking=True)
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_totales', store=True, currency_field='currency_id')
    impuesto = fields.Monetary(string='Impuesto (IGV)', compute='_compute_totales', store=True, currency_field='currency_id')
    total = fields.Monetary(string='Total a Pagar', compute='_compute_totales', store=True, currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)

    # Facturación
    factura_id = fields.Many2one('account.move', string='Factura')
    fecha_factura = fields.Date(string='Fecha de Factura')

    # Próxima Revisión
    proxima_revision_id = fields.Many2one('adt.proxima.revision', string='Próxima Revisión')

    # Autorización del Cliente
    autorizado = fields.Boolean(string='Autorizado por Cliente', tracking=True)
    fecha_autorizacion = fields.Datetime(string='Fecha de Autorización')
    firma_cliente = fields.Binary(string='Firma del Cliente', attachment=True)

    # Alertas
    alerta_credito_cliente = fields.Boolean(string='Cliente con Crédito Atrasado', compute='_compute_alertas', store=True)
    alerta_orden_previa = fields.Boolean(string='Trabajo Similar Reciente', compute='_compute_alertas', store=True)

    # Fechas
    fecha_promesa_entrega = fields.Datetime(string='Fecha Promesa de Entrega', tracking=True)
    fecha_entrega_real = fields.Datetime(string='Fecha de Entrega Real')

    # Observaciones
    observaciones = fields.Text(string='Observaciones')
    notas_internas = fields.Text(string='Notas Internas')

    # Control
    active = fields.Boolean(string='Activo', default=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name, company_id)', 'El número de orden debe ser único.')
    ]

    @api.model
    def create(self, vals):
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('adt.orden.mantenimiento') or _('Nuevo')

        # Si es emergencia, establecer prioridad alta automáticamente
        if vals.get('tipo_servicio') == 'emergencia' and vals.get('prioridad') in ['baja', 'media']:
            vals['prioridad'] = 'alta'

        return super(AdtOrdenMantenimiento, self).create(vals)

    @api.depends('trabajo_ids')
    def _compute_trabajos(self):
        for record in self:
            record.cantidad_trabajos = len(record.trabajo_ids)

    @api.depends('repuesto_ids.subtotal', 'mano_obra_ids.subtotal', 'descuento')
    def _compute_totales(self):
        for record in self:
            record.total_repuestos = sum(record.repuesto_ids.mapped('subtotal'))
            record.total_mano_obra = sum(record.mano_obra_ids.mapped('subtotal'))
            record.subtotal = record.total_repuestos + record.total_mano_obra - record.descuento
            record.impuesto = record.subtotal * 0.18  # IGV 18%
            record.total = record.subtotal + record.impuesto

    @api.depends('cliente_id', 'cliente_id.tiene_credito_atrasado', 'vehiculo_id', 'fecha_ingreso')
    def _compute_alertas(self):
        for record in self:
            # Alerta de crédito atrasado
            record.alerta_credito_cliente = record.cliente_id.tiene_credito_atrasado if record.cliente_id else False

            # Alerta de trabajo similar reciente (últimos 30 días)
            record.alerta_orden_previa = False
            if record.vehiculo_id and record.id:
                fecha_limite = fields.Datetime.now() - timedelta(days=30)
                ordenes_recientes = self.search([
                    ('vehiculo_id', '=', record.vehiculo_id.id),
                    ('id', '!=', record.id),
                    ('fecha_ingreso', '>=', fecha_limite),
                    ('state', 'not in', ['cancelled'])
                ])
                record.alerta_orden_previa = len(ordenes_recientes) > 0

    @api.constrains('vehiculo_id')
    def _check_vehiculo(self):
        """Validar que el vehículo esté registrado"""
        for record in self:
            if not record.vehiculo_id:
                raise ValidationError(_('No se puede crear una orden sin vehículo registrado.'))

    @api.constrains('tipo_servicio', 'vehiculo_id')
    def _check_garantia(self):
        """Validar orden previa para garantía"""
        for record in self:
            if record.tipo_servicio == 'garantia':
                # Buscar orden previa en últimos 90 días
                fecha_limite = fields.Datetime.now() - timedelta(days=90)
                orden_previa = self.search([
                    ('vehiculo_id', '=', record.vehiculo_id.id),
                    ('id', '!=', record.id),
                    ('fecha_ingreso', '>=', fecha_limite),
                    ('state', '=', 'delivered')
                ], limit=1)
                if not orden_previa:
                    raise ValidationError(_('No existe una orden previa válida para aplicar garantía.'))

    def action_iniciar_inspeccion(self):
        """Crear inspección de ingreso"""
        self.ensure_one()
        if not self.inspeccion_id:
            inspeccion = self.env['adt.inspeccion'].create({
                'orden_id': self.id,
                'vehiculo_id': self.vehiculo_id.id,
                'kilometraje': self.kilometraje
            })
            self.inspeccion_id = inspeccion.id
        self.state = 'inspeccion'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.inspeccion',
            'res_id': self.inspeccion_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_iniciar_diagnostico(self):
        """Avanzar a diagnóstico"""
        self.ensure_one()
        if not self.inspeccion_id or not self.inspeccion_id.completado:
            raise UserError(_('Debe completar la inspección antes de continuar.'))
        self.state = 'diagnostico'

    def action_generar_cotizacion(self):
        """Generar cotización"""
        self.ensure_one()
        if not self.trabajo_ids:
            raise UserError(_('Debe agregar al menos un trabajo antes de generar la cotización.'))
        self.state = 'cotizacion'

    def action_aprobar(self):
        """Aprobar cotización"""
        self.ensure_one()
        if not self.autorizado:
            raise UserError(_('Requiere autorización del cliente antes de aprobar.'))
        self.state = 'aprobado'
        # Reservar repuestos en inventario
        for repuesto in self.repuesto_ids:
            repuesto.action_reservar()

    def action_iniciar_trabajos(self):
        """Iniciar trabajos"""
        self.ensure_one()
        self.state = 'in_progress'

    def action_control_calidad(self):
        """Enviar a control de calidad"""
        self.ensure_one()
        # Validar que todos los trabajos estén completados
        trabajos_pendientes = self.trabajo_ids.filtered(lambda t: t.state != 'done')
        if trabajos_pendientes:
            raise UserError(_('Aún hay %s trabajo(s) pendiente(s).') % len(trabajos_pendientes))

        if not self.control_calidad_id:
            control = self.env['adt.control.calidad'].create({
                'orden_id': self.id
            })
            self.control_calidad_id = control.id

        self.state = 'quality_check'

    def action_completar(self):
        """Completar orden"""
        self.ensure_one()
        if not self.control_calidad_aprobado:
            raise UserError(_('El control de calidad debe estar aprobado.'))
        if not self.estado_final:
            raise UserError(_('Debe definir el estado final del vehículo.'))
        if self.estado_final == 'requiere_revision':
            raise UserError(_('No se puede completar una orden que requiere revisión adicional.'))

        self.state = 'done'
        # Actualizar kilometraje del vehículo
        if self.kilometraje:
            self.vehiculo_id.kilometraje = self.kilometraje

    def action_facturar(self):
        """Generar factura"""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Solo se pueden facturar órdenes completadas.'))
        if self.tipo_servicio == 'garantia':
            # Garantía sin cobro
            self.state = 'invoiced'
            return

        # Aquí iría la integración con account.move para generar factura
        self.state = 'invoiced'
        self.fecha_factura = fields.Date.today()

    def action_entregar(self):
        """Marcar como entregado"""
        self.ensure_one()
        if self.state != 'invoiced':
            raise UserError(_('Debe facturar antes de entregar.'))
        self.state = 'delivered'
        self.fecha_entrega_real = fields.Datetime.now()

    def action_cancelar(self):
        """Cancelar orden"""
        self.ensure_one()
        if self.state in ['done', 'invoiced', 'delivered']:
            raise UserError(_('No se puede cancelar una orden completada o facturada.'))
        self.state = 'cancelled'
        # Liberar repuestos reservados
        for repuesto in self.repuesto_ids:
            repuesto.action_liberar()

    def action_imprimir_orden(self):
        """Imprimir orden de trabajo"""
        self.ensure_one()
        return self.env.ref('adt_mantenimiento_mecanico.action_report_orden_mantenimiento').report_action(self)
