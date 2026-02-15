# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AdtControlCalidad(models.Model):
    _name = 'adt.control.calidad'
    _description = 'Control de Calidad Pre-Entrega'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Control de Calidad', compute='_compute_name', store=True)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')

    # Responsable
    inspector_id = fields.Many2one('res.users', string='Inspector de Calidad',
                                    default=lambda self: self.env.user, required=True, tracking=True)
    fecha_control = fields.Datetime(string='Fecha de Control', default=fields.Datetime.now)

    # Checklist Obligatorio (5 verificaciones críticas)
    item_encendido = fields.Selection([
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado')
    ], string='1. Encendido Correcto', required=True, tracking=True)
    obs_encendido = fields.Text(string='Observaciones Encendido')

    item_frenos = fields.Selection([
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado')
    ], string='2. Frenos Funcionales', required=True, tracking=True)
    obs_frenos = fields.Text(string='Observaciones Frenos')

    item_luces = fields.Selection([
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado')
    ], string='3. Luces Operativas', required=True, tracking=True)
    obs_luces = fields.Text(string='Observaciones Luces')

    item_fugas = fields.Selection([
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado')
    ], string='4. Sin Fugas de Fluidos', required=True, tracking=True)
    obs_fugas = fields.Text(string='Observaciones Fugas')

    item_prueba_manejo = fields.Selection([
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado')
    ], string='5. Prueba de Manejo', required=True, tracking=True)
    km_prueba = fields.Float(string='Kilómetros de Prueba', help='Kilómetros recorridos en prueba')
    obs_prueba_manejo = fields.Text(string='Observaciones Prueba de Manejo')

    # Verificaciones Adicionales
    verificaciones_adicionales = fields.Text(string='Verificaciones Adicionales')

    # Evidencia Fotográfica
    fotos_evidencia = fields.Many2many('ir.attachment', string='Fotos de Evidencia')

    # Resultado
    aprobado = fields.Boolean(string='Control de Calidad Aprobado', compute='_compute_aprobado',
                               store=True, tracking=True)
    motivo_rechazo = fields.Text(string='Motivo de Rechazo')

    # Retrabajo
    es_segunda_revision = fields.Boolean(string='Es Segunda Revisión', default=False)
    control_previo_id = fields.Many2one('adt.control.calidad', string='Control Previo')

    # Tiempo
    tiempo_control = fields.Float(string='Tiempo de Control (min)', help='Tiempo empleado en minutos')

    # Firma
    firma_inspector = fields.Binary(string='Firma del Inspector', attachment=True)
    fecha_firma = fields.Datetime(string='Fecha de Firma')

    # Observaciones
    observaciones_generales = fields.Text(string='Observaciones Generales')

    @api.depends('orden_id.name')
    def _compute_name(self):
        for record in self:
            if record.orden_id:
                suffix = ' (2da Rev.)' if record.es_segunda_revision else ''
                record.name = f"CC-{record.orden_id.name}{suffix}"
            else:
                record.name = 'Nuevo Control'

    @api.depends('item_encendido', 'item_frenos', 'item_luces', 'item_fugas', 'item_prueba_manejo')
    def _compute_aprobado(self):
        for record in self:
            # Todos los ítems deben estar aprobados
            record.aprobado = all([
                record.item_encendido == 'aprobado',
                record.item_frenos == 'aprobado',
                record.item_luces == 'aprobado',
                record.item_fugas == 'aprobado',
                record.item_prueba_manejo == 'aprobado'
            ])

    @api.constrains('km_prueba')
    def _check_km_prueba(self):
        """Validar que se registren kilómetros de prueba"""
        for record in self:
            if record.item_prueba_manejo == 'aprobado' and not record.km_prueba:
                raise ValidationError(_('Debe registrar los kilómetros recorridos en la prueba de manejo.'))

    def action_aprobar(self):
        """Aprobar control de calidad"""
        self.ensure_one()
        if not all([self.item_encendido, self.item_frenos, self.item_luces,
                    self.item_fugas, self.item_prueba_manejo]):
            raise UserError(_('Debe completar todos los ítems del checklist.'))

        if not self.aprobado:
            raise UserError(_('No se puede aprobar. Existen ítems rechazados.'))

        if not self.firma_inspector:
            raise UserError(_('Se requiere la firma digital del inspector.'))

        self.fecha_firma = fields.Datetime.now()
        self.orden_id.action_completar()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Control de Calidad Aprobado'),
                'message': _('La orden está lista para facturación.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_rechazar(self):
        """Rechazar control de calidad"""
        self.ensure_one()
        if not self.motivo_rechazo:
            raise UserError(_('Debe especificar el motivo del rechazo.'))

        # Devolver orden a estado "En Proceso"
        self.orden_id.state = 'in_progress'

        # Notificar al mecánico responsable
        if self.orden_id.trabajo_ids:
            for trabajo in self.orden_id.trabajo_ids:
                if trabajo.mecanico_id and trabajo.mecanico_id.user_id:
                    self.orden_id.message_post(
                        body=f"Control de Calidad Rechazado. Motivo: {self.motivo_rechazo}",
                        partner_ids=[trabajo.mecanico_id.user_id.partner_id.id]
                    )

        # Crear nuevo control para segunda revisión
        new_control = self.create({
            'orden_id': self.orden_id.id,
            'es_segunda_revision': True,
            'control_previo_id': self.id
        })
        self.orden_id.control_calidad_id = new_control.id

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Control de Calidad Rechazado'),
                'message': _('La orden ha sido devuelta para correcciones.'),
                'type': 'warning',
                'sticky': True,
            }
        }

    def action_solicitar_firma(self):
        """Abrir modal para firma digital"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.control.calidad',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'solicitar_firma': True}
        }
