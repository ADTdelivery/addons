# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AdtVehiculo(models.Model):
    _name = 'adt.vehiculo'
    _description = 'Vehículo - Motocicleta o Mototaxi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    # Información Básica
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True,
        readonly=True
    )
    tipo = fields.Selection([
        ('motocicleta', 'Motocicleta'),
        ('mototaxi', 'Mototaxi')
    ], string='Tipo', required=True, default='motocicleta', tracking=True)

    # Información del Vehículo
    marca_id = fields.Many2one('adt.vehiculo.marca', string='Marca', required=True, tracking=True)
    modelo = fields.Char(string='Modelo', required=True, tracking=True)
    ano = fields.Integer(string='Año', required=True, tracking=True)
    color = fields.Char(string='Color', tracking=True)
    placa = fields.Char(string='Placa', required=True, index=True, tracking=True)
    vin_chasis = fields.Char(string='VIN / Chasis', index=True, tracking=True)
    numero_motor = fields.Char(string='Número de Motor', tracking=True)

    # Especificaciones Técnicas
    kilometraje = fields.Float(string='Kilometraje Actual', tracking=True)
    ultimo_kilometraje = fields.Float(string='Último Kilometraje Registrado', readonly=True)
    combustible = fields.Selection([
        ('gasolina', 'Gasolina'),
        ('electrico', 'Eléctrico'),
        ('gas', 'Gas'),
        ('hibrido', 'Híbrido')
    ], string='Tipo de Combustible', default='gasolina')
    cilindraje = fields.Integer(string='Cilindraje (cc)')

    # Cliente/Propietario
    cliente_id = fields.Many2one('res.partner', string='Propietario', required=True, tracking=True)
    fecha_compra = fields.Date(string='Fecha de Compra')

    # Crédito Financiero
    tiene_credito = fields.Boolean(string='Tiene Crédito Financiero', compute='_compute_tiene_credito', store=True)
    credito_ids = fields.One2many('adt.credito.financiero', 'vehiculo_id', string='Créditos')

    # Historial
    orden_ids = fields.One2many('adt.orden.mantenimiento', 'vehiculo_id', string='Órdenes de Mantenimiento')
    cantidad_ordenes = fields.Integer(string='Total Órdenes', compute='_compute_historial')
    ultima_fecha_servicio = fields.Date(string='Última Fecha de Servicio', compute='_compute_historial', store=True)

    # Alertas
    alerta_mantenimiento = fields.Boolean(string='Alerta Mantenimiento', compute='_compute_alertas', store=True)
    alerta_credito = fields.Boolean(string='Alerta Crédito', compute='_compute_alertas', store=True)

    # Estado
    active = fields.Boolean(string='Activo', default=True)

    # Documentación
    poliza_seguro = fields.Char(string='Póliza de Seguro')
    estado_documentacion = fields.Selection([
        ('completo', 'Completo'),
        ('incompleto', 'Incompleto'),
        ('vencido', 'Vencido')
    ], string='Estado de Documentación', default='completo')

    _sql_constraints = [
        ('placa_unique', 'UNIQUE(placa)', 'Ya existe un vehículo con esta placa.'),
        ('vin_unique', 'UNIQUE(vin_chasis)', 'Ya existe un vehículo con este VIN/Chasis.'),
    ]

    @api.depends('marca_id', 'modelo', 'placa')
    def _compute_name(self):
        for record in self:
            if record.marca_id and record.modelo and record.placa:
                record.name = f"{record.marca_id.name} {record.modelo} - {record.placa}"
            else:
                record.name = record.placa or 'Nuevo Vehículo'

    @api.depends('credito_ids', 'credito_ids.estado')
    def _compute_tiene_credito(self):
        for record in self:
            record.tiene_credito = any(
                credito.estado in ['al_dia', 'atrasado', 'mora']
                for credito in record.credito_ids
            )

    @api.depends('orden_ids')
    def _compute_historial(self):
        for record in self:
            record.cantidad_ordenes = len(record.orden_ids)
            if record.orden_ids:
                ordenes_completadas = record.orden_ids.filtered(lambda o: o.state == 'done')
                if ordenes_completadas:
                    record.ultima_fecha_servicio = max(ordenes_completadas.mapped('fecha_ingreso'))
                else:
                    record.ultima_fecha_servicio = False
            else:
                record.ultima_fecha_servicio = False

    @api.depends('kilometraje', 'ultima_fecha_servicio', 'credito_ids.estado', 'orden_ids.kilometraje', 'orden_ids.state', 'tipo')
    def _compute_alertas(self):
        for record in self:
            # Alerta de mantenimiento (más de 5000 km sin servicio)
            record.alerta_mantenimiento = False
            if record.ultima_fecha_servicio and record.kilometraje:
                ultima_orden = record.orden_ids.filtered(lambda o: o.state == 'done').sorted('fecha_ingreso', reverse=True)[:1]
                if ultima_orden and ultima_orden.kilometraje:
                    km_desde_ultimo = record.kilometraje - ultima_orden.kilometraje
                    # Alerta si excede 5000 km (o 3000 para mototaxi)
                    limite_km = 3000 if record.tipo == 'mototaxi' else 5000
                    record.alerta_mantenimiento = km_desde_ultimo > limite_km

            # Alerta de crédito atrasado
            record.alerta_credito = any(
                credito.estado in ['atrasado', 'mora']
                for credito in record.credito_ids
            )

    @api.constrains('ano')
    def _check_ano(self):
        """Validar que el año no sea futuro"""
        for record in self:
            if record.ano and record.ano > fields.Date.today().year:
                raise ValidationError(_('El año no puede ser futuro.'))

    @api.constrains('kilometraje', 'ultimo_kilometraje')
    def _check_kilometraje(self):
        """Validar que el kilometraje no disminuya"""
        for record in self:
            if record.kilometraje and record.ultimo_kilometraje:
                if record.kilometraje < record.ultimo_kilometraje:
                    raise ValidationError(
                        _('El kilometraje no puede ser menor al último registrado (%s km).') % record.ultimo_kilometraje
                    )

    def write(self, vals):
        """Actualizar último kilometraje antes de modificar"""
        if 'kilometraje' in vals:
            for record in self:
                if record.kilometraje:
                    vals['ultimo_kilometraje'] = record.kilometraje
        return super(AdtVehiculo, self).write(vals)

    def action_ver_historial(self):
        """Abrir historial de órdenes"""
        self.ensure_one()
        return {
            'name': _('Historial de Mantenimientos'),
            'type': 'ir.actions.act_window',
            'res_model': 'adt.orden.mantenimiento',
            'view_mode': 'tree,form',
            'domain': [('vehiculo_id', '=', self.id)],
            'context': {'default_vehiculo_id': self.id}
        }


class AdtVehiculoMarca(models.Model):
    _name = 'adt.vehiculo.marca'
    _description = 'Marca de Vehículo'
    _order = 'name'

    name = fields.Char(string='Marca', required=True)
    active = fields.Boolean(string='Activo', default=True)
    vehiculo_ids = fields.One2many('adt.vehiculo', 'marca_id', string='Vehículos')
    cantidad_vehiculos = fields.Integer(string='Cantidad de Vehículos', compute='_compute_cantidad')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Ya existe esta marca de vehículo.')
    ]

    @api.depends('vehiculo_ids')
    def _compute_cantidad(self):
        for record in self:
            record.cantidad_vehiculos = len(record.vehiculo_ids)


class AdtCreditoFinanciero(models.Model):
    _name = 'adt.credito.financiero'
    _description = 'Crédito Financiero del Vehículo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inicio desc'

    name = fields.Char(string='Número de Contrato', required=True, tracking=True)
    vehiculo_id = fields.Many2one('adt.vehiculo', string='Vehículo', required=True, ondelete='cascade')
    cliente_id = fields.Many2one(related='vehiculo_id.cliente_id', string='Cliente', store=True)

    # Información Financiera
    empresa_financiera = fields.Char(string='Entidad Financiera', required=True, tracking=True)
    monto_credito = fields.Monetary(string='Monto del Crédito', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)

    # Fechas
    fecha_inicio = fields.Date(string='Fecha de Inicio', required=True, tracking=True)
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento', required=True, tracking=True)

    # Estado
    estado = fields.Selection([
        ('al_dia', 'Al Día'),
        ('atrasado', 'Atrasado'),
        ('cancelado', 'Cancelado'),
        ('mora', 'En Mora')
    ], string='Estado de Pagos', default='al_dia', required=True, tracking=True)

    cuotas_pendientes = fields.Integer(string='Cuotas Pendientes', tracking=True)
    observaciones = fields.Text(string='Observaciones')

    active = fields.Boolean(string='Activo', default=True)

    @api.constrains('fecha_inicio', 'fecha_vencimiento')
    def _check_fechas(self):
        for record in self:
            if record.fecha_vencimiento < record.fecha_inicio:
                raise ValidationError(_('La fecha de vencimiento debe ser posterior a la fecha de inicio.'))
