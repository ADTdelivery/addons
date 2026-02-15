# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AdtAutorizacion(models.Model):
    _name = 'adt.autorizacion'
    _description = 'Autorización del Cliente'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_autorizacion desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')
    cliente_id = fields.Many2one('res.partner', string='Cliente', required=True)

    # Tipo de Autorización
    tipo = fields.Selection([
        ('cotizacion', 'Autorización de Cotización'),
        ('trabajo_adicional', 'Trabajo Adicional'),
        ('cambio_repuesto', 'Cambio de Tipo de Repuesto'),
        ('aumento_costo', 'Aumento de Costo'),
        ('condiciones_generales', 'Condiciones Generales'),
        ('entrega_limitaciones', 'Entrega con Limitaciones')
    ], string='Tipo de Autorización', required=True, default='cotizacion', tracking=True)

    # Detalles
    descripcion = fields.Text(string='Descripción', required=True)
    trabajos_autorizados = fields.Many2many('adt.trabajo', string='Trabajos Autorizados')
    trabajos_rechazados = fields.Many2many('adt.trabajo', 'adt_autorizacion_trabajo_rechazado_rel',
                                            string='Trabajos Rechazados')

    # Montos
    monto_original = fields.Monetary(string='Monto Original', currency_field='currency_id')
    monto_final = fields.Monetary(string='Monto Final', currency_field='currency_id', tracking=True)
    diferencia = fields.Monetary(string='Diferencia', compute='_compute_diferencia', store=True, currency_field='currency_id')
    porcentaje_aumento = fields.Float(string='% Aumento', compute='_compute_porcentaje_aumento', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('pendiente', 'Pendiente de Firma'),
        ('autorizado', 'Autorizado'),
        ('rechazado', 'Rechazado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True)

    # Firma y Autorización
    firma_cliente = fields.Binary(string='Firma del Cliente', attachment=True)
    fecha_autorizacion = fields.Datetime(string='Fecha de Autorización', tracking=True)
    metodo_autorizacion = fields.Selection([
        ('presencial', 'Presencial'),
        ('telefono', 'Por Teléfono'),
        ('email', 'Por Email'),
        ('whatsapp', 'Por WhatsApp')
    ], string='Método de Autorización')

    # Documento Adjunto
    documento_firmado = fields.Binary(string='Documento Firmado', attachment=True)
    documento_filename = fields.Char(string='Nombre Archivo')

    # Observaciones
    observaciones_cliente = fields.Text(string='Observaciones del Cliente')
    observaciones_internas = fields.Text(string='Observaciones Internas')
    motivo_rechazo = fields.Text(string='Motivo de Rechazo')

    # Re-autorización
    es_reautorizacion = fields.Boolean(string='Es Re-autorización', default=False)
    autorizacion_previa_id = fields.Many2one('adt.autorizacion', string='Autorización Previa')

    # Control
    responsable_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user)

    @api.depends('orden_id.name', 'tipo')
    def _compute_name(self):
        for record in self:
            if record.orden_id:
                tipos_cortos = {
                    'cotizacion': 'COTIZ',
                    'trabajo_adicional': 'TRAB-AD',
                    'cambio_repuesto': 'REP',
                    'aumento_costo': 'AUMENTO',
                    'condiciones_generales': 'COND',
                    'entrega_limitaciones': 'ENT-LIM'
                }
                tipo_corto = tipos_cortos.get(record.tipo, 'AUT')
                record.name = f"{tipo_corto}-{record.orden_id.name}"
            else:
                record.name = 'Nueva Autorización'

    @api.depends('monto_original', 'monto_final')
    def _compute_diferencia(self):
        for record in self:
            record.diferencia = record.monto_final - record.monto_original

    @api.depends('monto_original', 'diferencia')
    def _compute_porcentaje_aumento(self):
        for record in self:
            if record.monto_original and record.monto_original > 0:
                record.porcentaje_aumento = (record.diferencia / record.monto_original) * 100
            else:
                record.porcentaje_aumento = 0

    @api.constrains('monto_final', 'monto_original')
    def _check_aumento_significativo(self):
        """Validar aumentos significativos de costo"""
        for record in self:
            if record.tipo == 'aumento_costo' and record.porcentaje_aumento > 10:
                # Si aumenta más del 10%, requiere autorización especial
                if not record.firma_cliente and record.state == 'autorizado':
                    raise ValidationError(
                        _('Un aumento de costo mayor al 10% requiere firma del cliente.')
                    )

    def action_solicitar_autorizacion(self):
        """Enviar solicitud de autorización al cliente"""
        self.ensure_one()
        self.state = 'pendiente'

        # Preparar mensaje
        mensaje = f"""
Estimado/a {self.cliente_id.name},

Requerimos su autorización para lo siguiente:

Orden: {self.orden_id.name}
Tipo: {dict(self._fields['tipo'].selection).get(self.tipo)}

Detalles:
{self.descripcion}

Monto: {self.monto_final:.2f} {self.currency_id.symbol}

Por favor, confirme su autorización.

Saludos,
{self.env.company.name}
        """

        # Crear actividad
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary='Pendiente Autorización de Cliente',
            note=self.descripcion,
            user_id=self.responsable_id.id
        )

        # Enviar email si tiene
        if self.cliente_id.email:
            self.message_post(
                body=mensaje,
                subject=f'Autorización Requerida - {self.orden_id.name}',
                partner_ids=[self.cliente_id.id]
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Solicitud Enviada'),
                'message': _('Solicitud de autorización enviada a %s') % self.cliente_id.name,
                'type': 'info',
            }
        }

    def action_autorizar(self):
        """Autorizar"""
        self.ensure_one()

        if not self.firma_cliente:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'adt.autorizacion',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'solicitar_firma': True}
            }

        self.state = 'autorizado'
        self.fecha_autorizacion = fields.Datetime.now()

        # Actualizar trabajos autorizados
        for trabajo in self.trabajos_autorizados:
            trabajo.autorizado = True

        # Actualizar orden si es autorización de cotización
        if self.tipo == 'cotizacion':
            self.orden_id.autorizado = True
            self.orden_id.fecha_autorizacion = self.fecha_autorizacion
            self.orden_id.firma_cliente = self.firma_cliente

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Autorizado'),
                'message': _('Autorización registrada exitosamente'),
                'type': 'success',
            }
        }

    def action_rechazar(self):
        """Rechazar autorización"""
        self.ensure_one()

        if not self.motivo_rechazo:
            raise UserError(_('Debe especificar el motivo del rechazo.'))

        self.state = 'rechazado'

        # Actualizar trabajos rechazados
        for trabajo in self.trabajos_rechazados:
            trabajo.autorizado = False
            trabajo.motivo_rechazo = self.motivo_rechazo

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rechazado'),
                'message': _('Autorización rechazada'),
                'type': 'warning',
            }
        }

    def action_generar_documento(self):
        """Generar documento de autorización en PDF"""
        self.ensure_one()
        return self.env.ref('adt_mantenimiento_mecanico.action_report_autorizacion').report_action(self)


class AdtCondicionesGenerales(models.Model):
    _name = 'adt.condiciones.generales'
    _description = 'Condiciones Generales del Servicio'
    _order = 'sequence'

    sequence = fields.Integer(string='Secuencia', default=10)
    name = fields.Char(string='Título', required=True)
    codigo = fields.Char(string='Código')
    descripcion = fields.Text(string='Descripción', required=True)
    categoria = fields.Selection([
        ('responsabilidad', 'Responsabilidad'),
        ('garantia', 'Garantía'),
        ('pago', 'Condiciones de Pago'),
        ('entrega', 'Condiciones de Entrega'),
        ('general', 'General')
    ], string='Categoría', default='general')

    es_obligatorio = fields.Boolean(string='Aceptación Obligatoria', default=True,
                                     help='Si es obligatorio, el cliente debe aceptarlo explícitamente')

    active = fields.Boolean(string='Activo', default=True)
    fecha_vigencia = fields.Date(string='Vigente Desde', default=fields.Date.today)

    # Texto Legal
    texto_legal = fields.Html(string='Texto Legal Completo')


class AdtAceptacionCondiciones(models.Model):
    _name = 'adt.aceptacion.condiciones'
    _description = 'Aceptación de Condiciones'

    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')
    condicion_id = fields.Many2one('adt.condiciones.generales', string='Condición', required=True)
    cliente_id = fields.Many2one('res.partner', string='Cliente', required=True)

    aceptado = fields.Boolean(string='Aceptado', default=False, tracking=True)
    fecha_aceptacion = fields.Datetime(string='Fecha de Aceptación')
    firma_cliente = fields.Binary(string='Firma', attachment=True)

    # Método de aceptación
    metodo = fields.Selection([
        ('presencial', 'Presencial'),
        ('digital', 'Digital'),
        ('verbal', 'Verbal (Registrado)')
    ], string='Método de Aceptación')

    observaciones = fields.Text(string='Observaciones')
