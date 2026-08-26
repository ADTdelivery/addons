# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from ..services.traccar_client import TraccarClient, TraccarAPIError


class TraccarRegisterDeviceWizard(models.TransientModel):
    _name = 'adt.traccar.register.device.wizard'
    _description = 'Registrar / Sincronizar vehículo con Traccar'

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', required=True, readonly=True)
    plate = fields.Char(string='Placa', related='vehicle_id.license_plate', readonly=True)
    # Editable acá (no related-readonly): se prellena desde el vehículo y,
    # si se cambia, se guarda de vuelta en fleet.vehicle al confirmar (ver
    # action_confirm) — mismo patrón que ya se usaba con el IMEI antes de
    # que este pasara a resolverse solo desde Traccar.
    traccar_solo_gps = fields.Boolean(
        string='Solo servicio GPS (sin cuenta comercial)',
        help='Marcar cuando el cliente solo contrató el servicio de GPS, sin una cuenta '
             'comercial asociada a este vehículo. Mientras esté marcada, la sincronización no '
             'exige una cuenta comercial activa — alcanza con la placa y un conductor con '
             'email asignado. Se guarda en el vehículo al confirmar.')

    # Ya no se pide el IMEI a mano: se muestra acá solo como previsualización
    # de lo que register_vehicle() va a resolver al confirmar (buscando en
    # Traccar el dispositivo cuyo nombre corresponda a la placa — ver
    # TraccarClient.find_device_by_plate). Si Traccar todavía no tiene ese
    # dispositivo, imei_preview queda vacío y se explica en imei_warning.
    imei_preview = fields.Char(
        string='IMEI detectado en Traccar', readonly=True, compute='_compute_imei_preview',
        help='Se obtiene automáticamente de Traccar: se busca el dispositivo cuyo nombre '
             'contenga la placa (tolera guiones, espacios u otro texto agregado en el '
             'nombre, ej. "ABC-123", "ABC123 Prueba"). Ya no hace falta escribirlo a mano.')
    imei_warning = fields.Char(string='Aviso', readonly=True, compute='_compute_imei_preview')

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

    @api.depends('plate')
    def _compute_imei_preview(self):
        for wiz in self:
            wiz.imei_preview = False
            wiz.imei_warning = False
            if not wiz.plate:
                wiz.imei_warning = _('El vehículo no tiene placa cargada.')
                continue
            try:
                client = TraccarClient.from_env(self.env)
                client.authenticate()
                device = client.find_device_by_plate(wiz.plate)
            except TraccarAPIError as exc:
                wiz.imei_warning = str(exc)
                continue
            if not device:
                wiz.imei_warning = _(
                    'No se encontró en Traccar ningún dispositivo para la placa "%s".'
                ) % wiz.plate
                continue
            imei = (device.get('uniqueId') or '').strip()
            if not imei:
                wiz.imei_warning = _(
                    'El dispositivo "%s" en Traccar no tiene IMEI configurado.'
                ) % (device.get('name') or '')
                continue
            wiz.imei_preview = imei

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
        # Si se tocó la casilla en el wizard, se guarda de vuelta en el
        # vehículo (fuente de verdad) antes de sincronizar.
        if self.traccar_solo_gps != self.vehicle_id.traccar_solo_gps:
            self.vehicle_id.traccar_solo_gps = self.traccar_solo_gps

        # register_vehicle busca el dispositivo en Traccar por placa y saca
        # el IMEI de ahí (ver adt.traccar.device.credential.register_vehicle);
        # si no lo encuentra, levanta un UserError legible acá mismo.
        credential = self.env['adt.traccar.device.credential'].register_vehicle(self.vehicle_id)

        return {
            'name': _('Credencial Traccar'),
            'type': 'ir.actions.act_window',
            'res_model': 'adt.traccar.device.credential',
            'view_mode': 'form',
            'res_id': credential.id,
            'target': 'current',
        }
