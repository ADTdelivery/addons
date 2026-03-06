# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class ADTPapeleta(models.Model):
    _name = 'adt.papeleta'
    _description = 'Papeleta Vehicular'
    _order = 'fecha_papeleta desc'
    # enable chatter history
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Número de Papeleta', required=True)
    fecha_papeleta = fields.Date(string='Fecha de Papeleta', required=True)
    monto = fields.Monetary(string='Monto', required=True, currency_field='company_currency_id')
    detalle = fields.Text(string='Detalle')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True)
    fecha_inicio_cuotas = fields.Date(string='Fecha inicio cuotas', help='Fecha desde la cual se generarán las cuotas mensualmente cuando la papeleta sea fraccionada')

    # Evidencias (imágenes, PDFs) relacionadas a la papeleta
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='adt_papeleta_attachment_rel',
        column1='papeleta_id',
        column2='attachment_id',
        string='Evidencias (Fotos/PDFs)'
    )

    # Evidencias específicas del fraccionamiento/cuotas
    attachment_cuotas_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='adt_papeleta_cuotas_attachment_rel',
        column1='papeleta_id',
        column2='attachment_id',
        string='Evidencias Fraccionamiento (Fotos/PDFs)'
    )

    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado')
    ], string='Estado de papeleta', default='pendiente', tracking=True)

    fecha_captura = fields.Date(string='Fecha de Captura', compute='_compute_fecha_captura', store=True)

    tiene_prorroga = fields.Boolean(string='Tiene Prórroga')
    dias_prorroga = fields.Integer(string='Días de Prórroga')
    motivo_prorroga = fields.Text(string='Motivo de Prórroga')
    fecha_vencimiento_final = fields.Date(string='Fecha de Vencimiento Final', compute='_compute_fecha_vencimiento_final', store=True)

    company_currency_id = fields.Many2one('res.currency', string='Moneda', related='company_id.currency_id', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Indicador de proximidad
    proximo_a_vencerse = fields.Boolean(string='Próximo a vencerse', compute='_compute_proximo_a_vencerse', store=True)
    dias_para_captura = fields.Integer(string='Días para captura', compute='_compute_proximo_a_vencerse', store=True)
    texto_alerta = fields.Char(string='Texto Alerta', compute='_compute_proximo_a_vencerse', store=True)
    alert_badge = fields.Char(string='Badge Alerta', compute='_compute_proximo_a_vencerse', store=True)

    # Fraccionamiento
    cantidad_cuotas = fields.Integer(string='Cantidad de Cuotas')
    cuotas_ids = fields.One2many('adt.papeleta.cuota', 'papeleta_id', string='Cuotas', copy=True)
    fecha_pago = fields.Date(string='Fecha de Pago')
    show_fraccionamiento = fields.Boolean(string='Mostrar Fraccionamiento', compute='_compute_show_fraccionamiento')

    payment_method = fields.Selection([
            ('pago_completo', 'Pago Completo'),
            ('fraccionado', 'Fraccionado')
        ], string='Modalidad de pago', default='pago_completo', tracking=True)

    capturado = fields.Boolean(string='Capturado', default=False)
    recolocada = fields.Boolean(string='Recolocada', default=False)

    @api.depends('fecha_papeleta')
    def _compute_fecha_captura(self):
        for rec in self:
            rec.fecha_captura = False
            if rec.fecha_papeleta:
                rec.fecha_captura = fields.Date.add(rec.fecha_papeleta, days=30)

    @api.depends('fecha_captura', 'fecha_vencimiento_final', 'state')
    def _compute_proximo_a_vencerse(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.proximo_a_vencerse = False
            rec.dias_para_captura = 0
            rec.texto_alerta = False
            if rec.state != 'pendiente':
                continue
            if not rec.fecha_vencimiento_final:
                continue
            # compute difference in days: fecha_captura - today
            try:
                delta = (rec.fecha_vencimiento_final - today).days
            except Exception:
                delta = 0
            rec.dias_para_captura = delta
            # show alert starting 5 days before (delta <= 5). includes negative deltas for overdue
            if delta <= 5:
                rec.proximo_a_vencerse = True
                # build texto_alerta
                if delta > 1:
                    rec.texto_alerta = 'Vence en %s días' % delta
                elif delta == 1:
                    rec.texto_alerta = 'Vence en 1 día'
                elif delta == 0:
                    rec.texto_alerta = 'Vence hoy'
                else:
                    # overdue: delta < 0
                    dias_pasados = abs(delta)
                    if dias_pasados == 1:
                        rec.texto_alerta = 'Se pasó 1 día'
                    else:
                        rec.texto_alerta = 'Se pasó %s días' % dias_pasados
                # badge text is same as texto_alerta
                rec.alert_badge = rec.texto_alerta
            else:
                rec.proximo_a_vencerse = False
                rec.texto_alerta = False
                rec.alert_badge = False

    @api.depends('fecha_captura', 'tiene_prorroga', 'dias_prorroga', 'payment_method', 'cuotas_ids.state', 'cuotas_ids.due_date')
    def _compute_fecha_vencimiento_final(self):
        for rec in self:
            # Si la papeleta está fraccionada, fecha_vencimiento_final es la primera cuota pendiente
            if rec.payment_method == 'fraccionado' and rec.cuotas_ids:
                pendientes = rec.cuotas_ids.filtered(lambda c: c.state == 'pendiente')
                if pendientes:
                    # Ordenar por due_date y tomar la primera
                    siguientes = pendientes.sorted(key=lambda r: r.due_date or fields.Date.context_today(self))
                    rec.fecha_vencimiento_final = siguientes[0].due_date
                    continue
                else:
                    # Si no hay pendientes, tomar la última cuota (si existe) como vencimiento final
                    todas = rec.cuotas_ids.sorted(key=lambda r: r.due_date or fields.Date.context_today(self))
                    if todas:
                        rec.fecha_vencimiento_final = todas[-1].due_date
                        continue
            # Comportamiento por defecto (no fraccionado o sin cuotas)
            if rec.tiene_prorroga and rec.dias_prorroga and rec.fecha_captura:
                rec.fecha_vencimiento_final = fields.Date.add(rec.fecha_captura, days=rec.dias_prorroga)
            else:
                rec.fecha_vencimiento_final = rec.fecha_captura

    @api.constrains('name')
    def _check_unique_name(self):
        for rec in self:
            if self.search_count([('name', '=', rec.name)]) > 1:
                raise ValidationError('El número de papeleta debe ser único.')

    @api.constrains('vehicle_id')
    def _check_vehicle_active(self):
        for rec in self:
            if rec.vehicle_id and rec.vehicle_id.state_id and hasattr(rec.vehicle_id, 'active') and not rec.vehicle_id.active:
                # fleet.vehicle may not have 'active' field in some setups; check safely
                raise ValidationError('El vehículo debe estar activo en la flota.')

    def unlink(self):
        for rec in self:
            if rec.state == 'pagado':
                raise ValidationError('No se puede eliminar una papeleta en estado Pagado.')
        return super(ADTPapeleta, self).unlink()

    @api.onchange('cantidad_cuotas', 'state', 'monto')
    def _onchange_cantidad_o_estado(self):
        """No generar automáticamente las cuotas en el onchange.
        La generación será manual mediante el botón `Generar cuotas`.
        Aquí sólo podemos validar valores básicos si se desea.
        """
        for rec in self:
            # no auto-generate; just ensure cantidad_cuotas no es negativa
            if rec.cantidad_cuotas and rec.cantidad_cuotas < 0:
                raise ValidationError('La cantidad de cuotas debe ser un número positivo.')

    def _generate_cuotas_for(self, rec):
        """Genera cuotas para un registro individual `rec` según la lógica usada en el onchange.
        No hace nada si ya existen cuotas o si no está en modalidad fraccionado o cantidad_cuotas <= 0.
        """
        if rec.payment_method != 'fraccionado' or not rec.cantidad_cuotas:
            return
        if rec.cuotas_ids:
            return
        total = float(rec.monto or 0.0)
        n = int(rec.cantidad_cuotas or 0)
        if n <= 0:
            return
        base = total / n if n else 0.0
        # determine start date for cuotas
        if rec.fecha_inicio_cuotas:
            start_date = fields.Date.from_string(rec.fecha_inicio_cuotas)
        elif rec.fecha_papeleta:
            start_date = fields.Date.from_string(rec.fecha_papeleta)
        else:
            start_date = fields.Date.context_today(self)
        cuotas_vals = []
        for i in range(n):
            due = start_date + relativedelta(months=i)
            cuotas_vals.append((0, 0, {
                'name': 'Cuota %s' % (i + 1),
                'amount': base,
                'due_date': fields.Date.to_string(due),
            }))
        rec.cuotas_ids = cuotas_vals

    def action_generar_cuotas(self):
        """Botón que genera las cuotas manualmente tomando `cantidad_cuotas` y `fecha_inicio_cuotas`.
        Ahora borra las cuotas existentes (si las hay) y las recrea.
        """
        for rec in self:
            if rec.payment_method != 'fraccionado':
                raise UserError('La papeleta no está en modalidad "Fraccionado".')
            if not rec.cantidad_cuotas or int(rec.cantidad_cuotas) <= 0:
                raise UserError('Ingrese la cantidad de cuotas antes de generar.')

            # Si ya existen cuotas, eliminarlas antes de generar
            if rec.cuotas_ids:
                try:
                    count_old = len(rec.cuotas_ids)
                    rec.cuotas_ids.unlink()
                    _logger.info('adt.papeleta: eliminadas %s cuotas existentes para papeleta %s', count_old, rec.id)
                except Exception:
                    _logger.exception('adt.papeleta: fallo al eliminar cuotas existentes para papeleta %s', rec.id)
                    raise UserError('No se pudieron eliminar las cuotas existentes. Revise los logs.')

            # Generar nuevas cuotas
            try:
                rec._generate_cuotas_for(rec)
            except Exception:
                _logger.exception('Error generando cuotas manualmente para papeleta %s', rec.id)
                raise UserError('Ocurrió un error al generar las cuotas. Revise los logs.')

            # Informar en chatter cuántas se crearon
            try:
                created = len(rec.cuotas_ids)
                rec.message_post(body=_('Se generaron %s cuotas.') % (created,))
            except Exception:
                _logger.exception('Failed to post chatter message after generating cuotas for papeleta %s', rec.id)
        return True

    @api.depends('payment_method')
    def _compute_show_fraccionamiento(self):
        for rec in self:
            rec.show_fraccionamiento = rec.payment_method in ('fraccionado')

    def action_mark_pagado(self):
        """Marca la papeleta como pagada. Validaciones:
        - Si ya está en 'pagado' se ignora.
        - Si está en 'fraccionado' y existen cuotas pendientes, lanza error.
        - Si todo OK, setea state='pagado' y fecha_pago hoy.
        """
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state == 'pagado':
                continue
            if rec.state == 'fraccionado':
                pendientes = rec.cuotas_ids.filtered(lambda c: c.state == 'pendiente')
                if pendientes:
                    raise ValidationError('Existen cuotas pendientes. Marque las cuotas como pagadas antes de marcar la papeleta como pagada.')
            rec.write({
                'state': 'pagado',
                'fecha_pago': today,
            })
            # Post a short message to chatter
            try:
                rec.message_post(body=_('Papeleta marcada como <b>Pagado</b> por %s') % (self.env.user.display_name,))
            except Exception:
                _logger.exception('Failed to post chatter message for action_mark_pagado on papeleta %s', rec.id)
        return True

    def action_mark_capturar(self):
        """Marca la papeleta como capturada. Validaciones:
        - Si ya está en 'capturado' se ignora.
        - Si está en 'pagado' no se puede marcar como capturado.
        - Si todo OK, setea capturado=True.
        """
        for rec in self:
            if rec.capturado:
                continue
            if rec.state == 'pagado':
                raise ValidationError('No se puede marcar como capturada una papeleta que ya está pagada.')
            rec.capturado = True
            try:
                rec.message_post(body=_('Papeleta marcada como <b>Capturado</b> por %s') % (self.env.user.display_name,))
            except Exception:
                _logger.exception('Failed to post chatter message for action_mark_capturar on papeleta %s', rec.id)
        return True

    def action_unmark_capturar(self):
        """Quita la marca de captura en la papeleta (capturado=False).
        Si ya no está marcada, se ignora.
        Registra en chatter quién la removió.
        """
        for rec in self:
            if not rec.capturado:
                continue
            # permitir quitar la marca independientemente del estado de la papeleta
            rec.capturado = False
            try:
                rec.message_post(body=_('Marca de captura removida por %s') % (self.env.user.display_name,))
            except Exception:
                _logger.exception('Failed to post chatter message for action_unmark_capturar on papeleta %s', rec.id)
        return True

    @api.model
    def create(self, vals):
        rec = super(ADTPapeleta, self).create(vals)
        # No generar cuotas automáticamente al crear; la generación es manual mediante el botón
        try:
            rec.message_post(body=_('Papeleta creada por %s') % (self.env.user.display_name,))
        except Exception:
            _logger.exception('Failed to post chatter message on create for papeleta %s', rec.id)
        return rec

    def write(self, vals):
         # Prevent editing records that are already paid
         for rec in self:
             if rec.state == 'pagado':
                 raise UserError('No se puede modificar una papeleta que ya está en estado Pagado.')

         # capture previous values for keys to build a concise change log
         prevs = {}
         for rec in self:
             prev = {}
             for k in vals.keys():
                 try:
                     prev[k] = rec[k]
                 except Exception:
                     prev[k] = None
             prevs[rec.id] = prev

         res = super(ADTPapeleta, self).write(vals)

         # No generar cuotas automáticamente en write; la generación es manual mediante el botón

         # post changes into chatter
         for rec in self:
             prev = prevs.get(rec.id, {})
             changes = []

             def _repr_value(v):
                 # Safe string representation for comparison; handle recordsets without forcing singleton
                 try:
                     if hasattr(v, 'ids'):
                         return ', '.join([r.display_name for r in v])
                 except Exception:
                     pass
                 try:
                     return str(v)
                 except Exception:
                     return repr(v)

             for k, old in prev.items():
                 try:
                     new = getattr(rec, k, None)
                 except Exception:
                     new = None
                 old_repr = _repr_value(old)
                 new_repr = _repr_value(new)
                 if old_repr != new_repr:
                     changes.append('%s: %s -> %s' % (k, old_repr, new_repr))

             if changes:
                 try:
                     rec.message_post(body=_('Cambios: <br/>%s') % ('<br/>'.join(changes),))
                 except Exception:
                     _logger.exception('Failed to post chatter message on write for papeleta %s', rec.id)

         return res

    def action_eliminar_cuotas(self):
        """Eliminar todas las cuotas asociadas a la papeleta.
        Usable como botón separado si el usuario quiere borrar sin regenerar.
        """
        for rec in self:
            if not rec.cuotas_ids:
                raise UserError('No hay cuotas para eliminar.')
            try:
                count = len(rec.cuotas_ids)
                rec.cuotas_ids.unlink()
                _logger.info('adt.papeleta: eliminadas %s cuotas para papeleta %s', count, rec.id)
                try:
                    rec.message_post(body=_('Se eliminaron %s cuotas.') % (count,))
                except Exception:
                    _logger.exception('Failed to post chatter message after deleting cuotas for papeleta %s', rec.id)
            except Exception:
                _logger.exception('adt.papeleta: fallo al eliminar cuotas para papeleta %s', rec.id)
                raise UserError('No se pudieron eliminar las cuotas. Revise los logs.')
        return True

class ADTPapeletaCuota(models.Model):
    _name = 'adt.papeleta.cuota'
    _description = 'Cuota de Papeleta'
    _order = 'id'

    name = fields.Char(string='Cuota', required=True)
    papeleta_id = fields.Many2one('adt.papeleta', string='Papeleta', ondelete='cascade', required=True)
    due_date = fields.Date(string='Fecha de Cuota')
    amount = fields.Monetary(string='Monto', currency_field='company_currency_id')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado')
    ], string='Estado', default='pendiente')

    company_currency_id = fields.Many2one('res.currency', related='papeleta_id.company_currency_id', string='Moneda', readonly=True)

    @api.model
    def create(self, vals):
        # ensure default name if missing
        if not vals.get('name') and vals.get('papeleta_id'):
            papeleta = self.env['adt.papeleta'].browse(vals.get('papeleta_id'))
            count = self.search_count([('papeleta_id', '=', papeleta.id)]) + 1
            vals['name'] = 'Cuota %s' % count
        return super(ADTPapeletaCuota, self).create(vals)

    def action_mark_cuota_pagado(self):
        """Marca la(s) cuota(s) como pagada(s) y fuerza recarga de la vista cliente para que se actualicen decoraciones."""
        for rec in self:
            if rec.state == 'pagado':
                continue
            rec.state = 'pagado'
            try:
                rec.papeleta_id.message_post(body=_('Cuota %s marcada como pagada por %s') % (rec.name, self.env.user.display_name))
            except Exception:
                _logger.exception('Failed to post message when marking cuota pagada %s', rec.id)
        # return reload action for client to refresh view and show updated decorations
        return {'type': 'ir.actions.client', 'tag': 'reload'}
