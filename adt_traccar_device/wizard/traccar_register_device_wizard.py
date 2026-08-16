# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TraccarRegisterDeviceWizard(models.TransientModel):
    _name = 'adt.traccar.register.device.wizard'
    _description = 'Registrar / Sincronizar vehículo con Traccar'

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True, readonly=True)
    plate = fields.Char(string='Placa', related='vehicle_id.license_plate', readonly=True)
    imei = fields.Char(string='IMEI', required=True,
                        help='Se prellena desde el IMEI cargado en el vehículo; editable si hace falta corregirlo.')

    partner_id = fields.Many2one(
        'res.partner', string='Cliente', compute='_compute_partner_id', readonly=True)
    partner_email = fields.Char(
        string='Email del cliente', related='partner_id.email', readonly=True)

    existing_credential_id = fields.Many2one(
        'adt.traccar.device.credential', string='Credencial activa actual',
        compute='_compute_existing_credential_id', readonly=True)
    traccar_email_preview = fields.Char(
        string='Email Traccar que se usará', readonly=True,
        compute='_compute_traccar_email_preview',
        help='Si el cliente ya tiene otro vehículo registrado, se usará un email técnico '
             'derivado (ej. juanv2@dominio) para que este vehículo tenga su propio login.')

    @api.depends('vehicle_id')
    def _compute_partner_id(self):
        Cuenta = self.env['adt.comercial.cuentas']
        for wiz in self:
            partner = wiz.vehicle_id.driver_id
            if not partner:
                cuenta = Cuenta.search(
                    [('vehiculo_id', '=', wiz.vehicle_id.id), ('state', 'in', ('en_curso', 'aprobado'))],
                    limit=1, order='id desc')
                partner = cuenta.partner_id
            wiz.partner_id = partner

    @api.depends('vehicle_id')
    def _compute_existing_credential_id(self):
        Credential = self.env['adt.traccar.device.credential']
        for wiz in self:
            wiz.existing_credential_id = Credential.search(
                [('vehicle_id', '=', wiz.vehicle_id.id), ('state', '=', 'activo')], limit=1)

    @api.depends('partner_id', 'partner_id.email')
    def _compute_traccar_email_preview(self):
        Credential = self.env['adt.traccar.device.credential']
        for wiz in self:
            if wiz.partner_id and wiz.partner_id.email:
                sequence = Credential._next_email_sequence(wiz.partner_id)
                wiz.traccar_email_preview = Credential._compute_traccar_email(wiz.partner_id, sequence)
            else:
                wiz.traccar_email_preview = False

    def action_confirm(self):
        self.ensure_one()
        if not self.imei:
            raise UserError(_('Ingrese el IMEI del dispositivo.'))

        # Si el IMEI cambió (o el vehículo no lo tenía cargado), se guarda
        # de vuelta en el vehículo (x_imei, definido en este mismo módulo)
        # para que quede como fuente de verdad.
        if self.imei != self.vehicle_id.x_imei:
            self.vehicle_id.x_imei = self.imei

        credential = self.env['adt.traccar.device.credential'].register_vehicle(
            self.vehicle_id, imei=self.imei)

        return {
            'name': _('Credencial Traccar'),
            'type': 'ir.actions.act_window',
            'res_model': 'adt.traccar.device.credential',
            'view_mode': 'form',
            'res_id': credential.id,
            'target': 'current',
        }
