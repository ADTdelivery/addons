# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class AdtTvsPuntoAutorizado(models.Model):
    _name = 'adt.tvs.punto_autorizado'
    _description = 'Punto Autorizado'

    name = fields.Char(string='Nombre', required=True)
    direccion = fields.Char(string='Dirección')


class AdtTvsMantenimiento(models.Model):
    _name = 'adt.tvs.mantenimiento'
    _description = 'ADT TVS Mantenimiento'
    _rec_name = 'name'

    name = fields.Char(string='Número', required=True, copy=False, readonly=True, default=lambda self: _('New'))

    punto_autorizado_id = fields.Many2one('adt.tvs.punto_autorizado', string='Punto Autorizado')

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True)
    motivo_ingreso = fields.Char(string='Motivo de ingreso')

    date_inicio_revision = fields.Datetime(string='Fecha inicio revisión', required=True, default=fields.Datetime.now)
    date_fin_revision = fields.Datetime(string='Fecha fin revisión')
    days_in_taller = fields.Integer(string='Días en taller', compute='_compute_days_in_taller', store=True)

    # Use explicit relation table so the many2many_binary widget works properly
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='adt_tvs_mantenimiento_attachment_rel',
        column1='mantenimiento_id',
        column2='attachment_id',
        string='Archivos'
    )

    state = fields.Selection([
        ('in_progress', 'En taller'),
        ('done', 'Revisión finalizada')
    ], string='Estado', default='in_progress', required=True)

    active = fields.Boolean(default=True)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Moneda', readonly=True)

    tiene_garantia = fields.Boolean(string='¿Tiene garantía?', default=False)
    gasto_mantenimiento = fields.Monetary(string='Gasto de Mantenimiento', currency_field='company_currency_id', default=0.0)

    @api.model
    def create(self, vals):
        # ensure new records are created with a name and start in 'in_progress'
        if vals.get('name', _('New')) == _('New') or not vals.get('name'):
            seq = self.env['ir.sequence'].next_by_code('adt.tvs.mantenimiento')
            vals['name'] = seq or vals.get('name', _('New'))
        if not vals.get('state'):
            vals['state'] = 'in_progress'
        return super(AdtTvsMantenimiento, self).create(vals)

    @api.depends('date_inicio_revision', 'date_fin_revision')
    def _compute_days_in_taller(self):
        for rec in self:
            if not rec.date_inicio_revision:
                rec.days_in_taller = 0
                continue
            # use end date if set, otherwise now
            end_dt = rec.date_fin_revision or fields.Datetime.now()
            try:
                start = fields.Datetime.from_string(rec.date_inicio_revision)
                end = fields.Datetime.from_string(end_dt)
            except Exception:
                # fallback to zero
                rec.days_in_taller = 0
                continue
            delta = end - start
            # ensure non-negative
            rec.days_in_taller = max(0, delta.days)

    def action_ingresar_taller(self):
        for rec in self:
            if not rec.date_inicio_revision:
                raise UserError(_('La fecha de inicio de revisión es obligatoria para ingresar al taller.'))
            rec.state = 'in_progress'

    def action_finalizar_revision(self):
        for rec in self:
            if not rec.date_fin_revision:
                raise UserError(_('Debe registrar la fecha de fin de revisión antes de finalizar.'))
            # Ensure date_fin >= date_inicio
            if rec.date_inicio_revision and rec.date_fin_revision:
                start = fields.Datetime.from_string(rec.date_inicio_revision)
                end = fields.Datetime.from_string(rec.date_fin_revision)
                if end < start:
                    raise ValidationError(_('La fecha fin no puede ser anterior a la fecha de inicio.'))
            rec.state = 'done'

    @api.constrains('state', 'date_fin_revision')
    def _check_finalized_has_date(self):
        for rec in self:
            if rec.state == 'done' and not rec.date_fin_revision:
                raise ValidationError(_('No se puede marcar como finalizado sin una fecha de fin.'))

    def write(self, vals):
        # prevent editing finalized records
        if any(r.state == 'done' for r in self):
            # allow only modifications that don't change content? For simplicity, block all
            raise UserError(_('No se puede modificar un registro que ya fue finalizado.'))
        return super(AdtTvsMantenimiento, self).write(vals)

    def unlink(self):
        if any(r.state == 'done' for r in self):
            raise UserError(_('No se puede eliminar un registro que ya fue finalizado.'))
        return super(AdtTvsMantenimiento, self).unlink()


class AdtTvsVehicleMaintenanceRecord(models.Model):
    _name = 'adt.tvs.vehicle_maintenance_record'
    _description = 'Registro de Mantenimiento por Kilometraje (TVS)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        ('vehicle_maintenance_unique', 'unique(vehicle_id)', 'Ya existe un registro de mantenimiento para este vehículo.'),
    ]

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True, tracking=True)
    conductor_id = fields.Many2one('res.partner', string='Conductor / Cliente', readonly=False)
    conductor_document = fields.Char(string='Documento')
    chassis = fields.Char(string='Chasis')
    motor = fields.Char(string='Motor')
    placa = fields.Char(string='Placa')

    estado_mantenimiento = fields.Selection([
        ('tvs', 'TVS'),
        ('terceros', 'Terceros')
    ], string='Responsable del Mantenimiento', default='tvs', tracking=True)
    motivo_terceros = fields.Text(string='Motivo (Terceros)')

    line_ids = fields.One2many('adt.tvs.vehicle_maintenance_line', 'record_id', string='Plan de Mantenimiento', copy=True)

    active = fields.Boolean(default=True)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id_fill(self):
        for rec in self:
            rec.conductor_id = False
            rec.conductor_document = False
            rec.chassis = False
            rec.motor = False
            rec.placa = False
            if not rec.vehicle_id:
                continue
            vehicle = rec.vehicle_id
            # Try to get driver/partner info
            driver = False
            driver_field = vehicle._fields.get('driver_id')
            if driver_field:
                try:
                    driver = getattr(vehicle, 'driver_id')
                except Exception:
                    driver = False
            # fallbacks
            if not driver and getattr(vehicle, 'partner_id', False):
                driver = vehicle.partner_id
            if not driver and getattr(vehicle, 'owner_id', False):
                driver = vehicle.owner_id
            if driver:
                if hasattr(driver, 'partner_id') and getattr(driver, 'partner_id'):
                    partner = driver.partner_id
                else:
                    partner = driver
                rec.conductor_id = partner.id
                # try to get document number from partner.vat or ref
                try:
                    rec.conductor_document = partner.vat or partner.ref or ''
                except Exception:
                    rec.conductor_document = ''
            # vehicle fields: chassis/vin, engine, license_plate
            # try common field names safely
            vin = False
            for attr in ('vin_sn', 'chassis_number', 'vin', 'serial_no'):
                if getattr(vehicle, attr, False):
                    vin = getattr(vehicle, attr)
                    break
            rec.chassis = vin or ''
            engine = False
            for attr in ('engine_number', 'motor_number', 'motor'):
                if getattr(vehicle, attr, False):
                    engine = getattr(vehicle, attr)
                    break
            rec.motor = engine or ''
            rec.placa = getattr(vehicle, 'license_plate', '') or getattr(vehicle, 'plate', '') or ''

            # Auto-generate default plan of km if there are no lines yet
            try:
                if not rec.line_ids:
                    rec._generate_default_plan()
            except Exception:
                # don't break onchange on error, but log in server logs if needed
                _logger = getattr(self, '_logger', None)
                if _logger:
                    _logger.exception('Failed to auto-generate default km plan for vehicle %s', getattr(vehicle, 'id', False))

    @api.model
    def create(self, vals):
        # Prevent creating a second maintenance record for the same vehicle
        if vals.get('vehicle_id'):
            exists = self.search([('vehicle_id', '=', vals.get('vehicle_id'))], limit=1)
            if exists:
                raise ValidationError('Ya existe un registro de mantenimiento para este vehículo.')
        if vals.get('name', _('New')) == _('New'):
            seq = self.env['ir.sequence'].next_by_code('adt.tvs.vehicle_maintenance_record')
            vals['name'] = seq or _('New')
        rec = super(AdtTvsVehicleMaintenanceRecord, self).create(vals)
        # auto-generate plan if no lines
        if not rec.line_ids:
            rec._generate_default_plan()
        return rec

    def _generate_default_plan(self):
        kms = [750,1500,2500,3000,6000,9000,12000,15000,18000,21000,24000]
        lines = []
        for k in kms:
            lines.append((0,0,{
                'km_objetivo': k,
                'realizado': False,
            }))
        self.line_ids = lines
        return True

    @api.constrains('estado_mantenimiento','motivo_terceros')
    def _check_motivo_terceros(self):
        for rec in self:
            if rec.estado_mantenimiento == 'terceros' and not rec.motivo_terceros:
                raise ValidationError('El motivo para terceros es obligatorio cuando el estado es Terceros.')


class AdtTvsVehicleMaintenanceLine(models.Model):
    _name = 'adt.tvs.vehicle_maintenance_line'
    _description = 'Línea de Mantenimiento por Km (TVS)'

    record_id = fields.Many2one('adt.tvs.vehicle_maintenance_record', string='Registro', ondelete='cascade')
    km_objetivo = fields.Integer(string='KM Objetivo', required=True)
    realizado = fields.Boolean(string='Realizado', default=False)
    attachment_ids = fields.Many2many('ir.attachment', 'adt_tvs_maintenance_line_attachment_rel', 'line_id', 'attachment_id', string='Orden de Trabajo')
    fecha_inicio = fields.Date(string='Fecha Inicio')
    fecha_fin = fields.Date(string='Fecha Fin')

    @api.constrains('realizado','attachment_ids','fecha_inicio','fecha_fin')
    def _check_realizado_requirements(self):
        for rec in self:
            if rec.realizado:
                if not rec.attachment_ids or not rec.fecha_inicio or not rec.fecha_fin:
                    raise ValidationError('Si marcado como realizado, debe ingresar Orden de Trabajo, Fecha Inicio y Fecha Fin.')

    def action_open_in_modal(self):
        """Open this maintenance line in a modal form view."""
        self.ensure_one()
        view = self.env.ref('adt_tvs_mantenimiento.view_adt_tvs_vehicle_maintenance_line_form', False)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Línea de Mantenimiento'),
            'res_model': 'adt.tvs.vehicle_maintenance_line',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')] if view else None,
            'target': 'new',
        }


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    maintenance_record_ids = fields.One2many('adt.tvs.vehicle_maintenance_record', 'vehicle_id', string='Mantenimientos por KM')
    # Expose adt.tvs.mantenimiento records related to this vehicle
    mantenimiento_ids = fields.One2many('adt.tvs.mantenimiento', 'vehicle_id', string='Mantenimientos ADT')
