# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class AdtProximaRevision(models.Model):
    _name = 'adt.proxima.revision'
    _description = 'Próxima Revisión Programada'
    _order = 'fecha_proxima'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden Origen', required=True, ondelete='cascade')
    vehiculo_id = fields.Many2one('adt.vehiculo', string='Vehículo', required=True)
    cliente_id = fields.Many2one('res.partner', string='Cliente', required=True)

    # Tipo de Revisión
    tipo_revision = fields.Selection([
        ('preventivo', 'Mantenimiento Preventivo'),
        ('inspeccion', 'Inspección General'),
        ('cambio_aceite', 'Cambio de Aceite'),
        ('revision_frenos', 'Revisión de Frenos'),
        ('otro', 'Otro')
    ], string='Tipo de Revisión', required=True, default='preventivo')

    # Programación por Fecha
    fecha_proxima = fields.Date(string='Fecha Sugerida', required=True)
    fecha_limite = fields.Date(string='Fecha Límite', compute='_compute_fecha_limite', store=True)
    dias_restantes = fields.Integer(string='Días Restantes', compute='_compute_dias_restantes')

    # Programación por Kilometraje
    kilometraje_actual = fields.Float(string='Kilometraje Actual', required=True)
    kilometraje_proximo = fields.Float(string='Kilometraje Próxima Revisión', required=True)
    km_restantes = fields.Float(string='Km Restantes', compute='_compute_km_restantes')
    porcentaje_completado = fields.Float(string='% Completado', compute='_compute_porcentaje')

    # Lo que ocurra primero
    criterio_alcanzado = fields.Selection([
        ('fecha', 'Fecha'),
        ('kilometraje', 'Kilometraje'),
        ('ninguno', 'Ninguno')
    ], string='Criterio Alcanzado', compute='_compute_criterio_alcanzado')

    # Trabajos Sugeridos
    trabajos_sugeridos = fields.Text(string='Trabajos Sugeridos',
                                      help='Lista de trabajos recomendados para esta revisión')

    # Recordatorios
    recordatorio_enviado_7dias = fields.Boolean(string='Recordatorio 7 días', default=False)
    recordatorio_enviado_3dias = fields.Boolean(string='Recordatorio 3 días', default=False)
    recordatorio_enviado_1dia = fields.Boolean(string='Recordatorio 1 día', default=False)
    fecha_ultimo_recordatorio = fields.Date(string='Último Recordatorio')

    # Estado
    state = fields.Selection([
        ('programado', 'Programado'),
        ('proximo', 'Próximo (< 15 días)'),
        ('urgente', 'Urgente (< 7 días)'),
        ('vencido', 'Vencido'),
        ('completado', 'Completado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', compute='_compute_state', store=True, tracking=True)

    # Cumplimiento
    fecha_cumplimiento = fields.Date(string='Fecha de Cumplimiento')
    orden_cumplimiento_id = fields.Many2one('adt.orden.mantenimiento', string='Orden de Cumplimiento')

    # Observaciones
    observaciones = fields.Text(string='Observaciones')
    notas_internas = fields.Text(string='Notas Internas')

    @api.depends('orden_id.name', 'tipo_revision')
    def _compute_name(self):
        for record in self:
            if record.orden_id:
                record.name = f"REV-{record.orden_id.name}"
            else:
                record.name = 'Nueva Revisión'

    @api.depends('fecha_proxima')
    def _compute_fecha_limite(self):
        for record in self:
            if record.fecha_proxima:
                # 15 días de tolerancia después de la fecha sugerida
                record.fecha_limite = record.fecha_proxima + timedelta(days=15)
            else:
                record.fecha_limite = False

    @api.depends('fecha_proxima')
    def _compute_dias_restantes(self):
        today = fields.Date.today()
        for record in self:
            if record.fecha_proxima:
                delta = record.fecha_proxima - today
                record.dias_restantes = delta.days
            else:
                record.dias_restantes = 0

    @api.depends('vehiculo_id.kilometraje', 'kilometraje_proximo')
    def _compute_km_restantes(self):
        for record in self:
            if record.vehiculo_id and record.kilometraje_proximo:
                km_actual = record.vehiculo_id.kilometraje or record.kilometraje_actual
                record.km_restantes = record.kilometraje_proximo - km_actual
            else:
                record.km_restantes = 0

    @api.depends('vehiculo_id.kilometraje', 'kilometraje_actual', 'kilometraje_proximo')
    def _compute_porcentaje(self):
        for record in self:
            if record.kilometraje_proximo and record.kilometraje_actual:
                km_actual = record.vehiculo_id.kilometraje or record.kilometraje_actual
                km_recorrido = km_actual - record.kilometraje_actual
                km_total = record.kilometraje_proximo - record.kilometraje_actual
                if km_total > 0:
                    record.porcentaje_completado = min((km_recorrido / km_total) * 100, 100)
                else:
                    record.porcentaje_completado = 0
            else:
                record.porcentaje_completado = 0

    @api.depends('dias_restantes', 'km_restantes', 'fecha_cumplimiento')
    def _compute_state(self):
        for record in self:
            if record.fecha_cumplimiento:
                record.state = 'completado'
            elif record.dias_restantes < 0 and record.km_restantes < 0:
                record.state = 'vencido'
            elif record.dias_restantes <= 7 or record.km_restantes <= 500:
                record.state = 'urgente'
            elif record.dias_restantes <= 15 or record.km_restantes <= 1000:
                record.state = 'proximo'
            else:
                record.state = 'programado'

    @api.depends('dias_restantes', 'km_restantes')
    def _compute_criterio_alcanzado(self):
        for record in self:
            if record.dias_restantes <= 0:
                record.criterio_alcanzado = 'fecha'
            elif record.km_restantes <= 0:
                record.criterio_alcanzado = 'kilometraje'
            else:
                record.criterio_alcanzado = 'ninguno'

    @api.model
    def create(self, vals):
        """Calcular automáticamente fecha y kilometraje si no se proporcionan"""
        if vals.get('orden_id'):
            orden = self.env['adt.orden.mantenimiento'].browse(vals['orden_id'])

            # Calcular fecha próxima (3 meses por defecto)
            if not vals.get('fecha_proxima'):
                vals['fecha_proxima'] = fields.Date.today() + timedelta(days=90)

            # Calcular kilometraje próximo
            if not vals.get('kilometraje_proximo') and orden.kilometraje:
                # 5000 km para motocicleta, 3000 para mototaxi
                intervalo = 3000 if orden.vehiculo_id.tipo == 'mototaxi' else 5000
                vals['kilometraje_proximo'] = orden.kilometraje + intervalo

            # Trabajos sugeridos automáticos
            if not vals.get('trabajos_sugeridos'):
                vals['trabajos_sugeridos'] = '''• Cambio de aceite y filtro
• Revisión de frenos
• Inspección de llantas
• Verificación de sistema eléctrico
• Ajuste general'''

        return super(AdtProximaRevision, self).create(vals)

    def action_enviar_recordatorio(self):
        """Enviar recordatorio al cliente"""
        self.ensure_one()

        # Preparar mensaje
        mensaje = f"""
Estimado/a {self.cliente_id.name},

Le recordamos que su vehículo {self.vehiculo_id.name} tiene una revisión programada.

Fecha sugerida: {self.fecha_proxima.strftime('%d/%m/%Y')}
Kilometraje actual: {self.vehiculo_id.kilometraje:.0f} km
Próxima revisión: {self.kilometraje_proximo:.0f} km

Trabajos sugeridos:
{self.trabajos_sugeridos}

Por favor, contacte con nosotros para agendar su cita.

Saludos,
{self.env.company.name}
        """

        # Enviar correo
        if self.cliente_id.email:
            mail_values = {
                'subject': f'Recordatorio de Mantenimiento - {self.vehiculo_id.placa}',
                'body_html': mensaje.replace('\n', '<br/>'),
                'email_to': self.cliente_id.email,
            }
            self.env['mail.mail'].create(mail_values).send()

        # Registrar recordatorio
        self.fecha_ultimo_recordatorio = fields.Date.today()

        # Marcar según días
        if self.dias_restantes <= 1:
            self.recordatorio_enviado_1dia = True
        elif self.dias_restantes <= 3:
            self.recordatorio_enviado_3dias = True
        elif self.dias_restantes <= 7:
            self.recordatorio_enviado_7dias = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recordatorio Enviado'),
                'message': _('Recordatorio enviado a %s') % self.cliente_id.name,
                'type': 'success',
            }
        }

    @api.model
    def cron_enviar_recordatorios_automaticos(self):
        """Cron para enviar recordatorios automáticos"""
        # Recordatorio 7 días antes
        revisiones_7dias = self.search([
            ('state', '=', 'proximo'),
            ('dias_restantes', '<=', 7),
            ('dias_restantes', '>', 3),
            ('recordatorio_enviado_7dias', '=', False)
        ])
        for revision in revisiones_7dias:
            revision.action_enviar_recordatorio()

        # Recordatorio 3 días antes
        revisiones_3dias = self.search([
            ('state', '=', 'urgente'),
            ('dias_restantes', '<=', 3),
            ('dias_restantes', '>', 1),
            ('recordatorio_enviado_3dias', '=', False)
        ])
        for revision in revisiones_3dias:
            revision.action_enviar_recordatorio()

        # Recordatorio 1 día antes
        revisiones_1dia = self.search([
            ('state', '=', 'urgente'),
            ('dias_restantes', '<=', 1),
            ('recordatorio_enviado_1dia', '=', False)
        ])
        for revision in revisiones_1dia:
            revision.action_enviar_recordatorio()

    def action_completar(self):
        """Marcar revisión como completada"""
        self.ensure_one()
        if not self.orden_cumplimiento_id:
            raise ValidationError(_('Debe asociar una orden de mantenimiento de cumplimiento.'))

        self.fecha_cumplimiento = fields.Date.today()
        self.state = 'completado'

    def action_cancelar(self):
        """Cancelar revisión programada"""
        self.ensure_one()
        self.state = 'cancelado'

    def action_crear_orden(self):
        """Crear orden de mantenimiento desde revisión"""
        self.ensure_one()

        orden = self.env['adt.orden.mantenimiento'].create({
            'cliente_id': self.cliente_id.id,
            'vehiculo_id': self.vehiculo_id.id,
            'tipo_servicio': 'preventivo',
            'kilometraje': self.vehiculo_id.kilometraje,
            'observaciones': f'Revisión programada: {self.trabajos_sugeridos}'
        })

        self.orden_cumplimiento_id = orden.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.orden.mantenimiento',
            'res_id': orden.id,
            'view_mode': 'form',
            'target': 'current',
        }
