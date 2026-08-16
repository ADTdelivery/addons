# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .traccar_device_credential import AdtTraccarNotEligible
from ..services.traccar_client import TraccarClient, TraccarAPIError


class FleetVehicleTraccarDevice(models.Model):
    _inherit = 'fleet.vehicle'

    # Campo propio de este módulo (no se depende de fleet_addons.x_imei ni
    # de ningún otro módulo para esto — ver manifest). Mismo nombre que
    # históricamente se usó en el resto del código (fleet_addons,
    # referencias comentadas en adt_comercial) por continuidad, pero
    # definido y mantenido acá.
    x_imei = fields.Char(string='IMEI', help='IMEI del dispositivo GPS instalado en el vehículo.')

    traccar_credential_ids = fields.One2many(
        'adt.traccar.device.credential', 'vehicle_id', string='Credenciales Traccar')
    traccar_credential_active_id = fields.Many2one(
        'adt.traccar.device.credential', string='Credencial Traccar activa',
        compute='_compute_traccar_credential_active_id', store=False)
    traccar_credential_state = fields.Selection(
        related='traccar_credential_active_id.state', string='Estado Traccar', store=False)

    # ── Estado GPS (leído/actualizado vía la credencial activa) ─────────
    # Todos `related` a adt.traccar.device.credential — la data vive ahí
    # (ver ese modelo), acá solo se refleja para no obligar a navegar a otra
    # ficha. action_refresh_traccar_status() es el botón "Actualizar".
    gps_status = fields.Selection(related='traccar_credential_active_id.gps_status', string='Estado GPS')
    gps_last_update = fields.Datetime(
        related='traccar_credential_active_id.gps_last_update', string='Último reporte del GPS')
    gps_latitude = fields.Float(related='traccar_credential_active_id.gps_latitude', string='Latitud')
    gps_longitude = fields.Float(related='traccar_credential_active_id.gps_longitude', string='Longitud')
    gps_speed_kmh = fields.Float(
        related='traccar_credential_active_id.gps_speed_kmh', string='Velocidad (km/h)')
    gps_battery_level = fields.Float(
        related='traccar_credential_active_id.gps_battery_level', string='Batería (%)')
    gps_address = fields.Char(
        related='traccar_credential_active_id.gps_address', string='Dirección aproximada')
    gps_maps_url = fields.Char(related='traccar_credential_active_id.gps_maps_url', string='Ver en el mapa')
    gps_status_refreshed_at = fields.Datetime(
        related='traccar_credential_active_id.gps_status_refreshed_at', string='Actualizado en Odoo')

    @api.depends('traccar_credential_ids.state', 'traccar_credential_ids.active')
    def _compute_traccar_credential_active_id(self):
        for vehicle in self:
            vehicle.traccar_credential_active_id = vehicle.traccar_credential_ids.filtered(
                lambda c: c.state == 'activo')[:1]

    # ── Entrada (a): botón individual en el formulario ──────────────────
    def action_open_traccar_register_wizard(self):
        self.ensure_one()
        return {
            'name': _('Registrar / Sincronizar con Traccar'),
            'type': 'ir.actions.act_window',
            'res_model': 'adt.traccar.register.device.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_vehicle_id': self.id,
                'default_imei': self.x_imei,
            },
        }

    def action_refresh_traccar_status(self):
        """Botón "Actualizar" del formulario: pide a Traccar el estado en
        vivo del dispositivo (online/offline, posición, velocidad, batería)
        y lo guarda en los campos gps_* — ver adt.traccar.device.credential
        .action_refresh_gps_status()."""
        self.ensure_one()
        if not self.traccar_credential_active_id:
            raise UserError(_(
                'Este vehículo no tiene una credencial Traccar activa. '
                'Regístralo primero con el botón "Traccar".'
            ))
        self.traccar_credential_active_id.action_refresh_gps_status()
        return True

    def action_refresh_traccar_status_bulk(self):
        """Acción de lista: actualiza el estado GPS de todos los vehículos
        seleccionados que tengan credencial Traccar activa (mismo espíritu
        que action_sync_traccar_bulk, para poder revisar el estado de toda
        la flota de una sola vez)."""
        updated, skipped, errors = [], [], []
        for vehicle in self:
            label = vehicle.license_plate or vehicle.display_name or ('ID %s' % vehicle.id)
            if not vehicle.traccar_credential_active_id:
                skipped.append(_('%s: sin credencial Traccar activa') % label)
                continue
            try:
                vehicle.traccar_credential_active_id.action_refresh_gps_status()
                updated.append(label)
            except UserError as exc:
                errors.append('%s (%s)' % (label, exc))

        lines = []
        if updated:
            lines.append(_('Actualizados (%s): %s') % (len(updated), ', '.join(updated)))
        if skipped:
            lines.append(_('Omitidos (%s): %s') % (len(skipped), '; '.join(skipped)))
        if errors:
            lines.append(_('Con error (%s): %s') % (len(errors), '; '.join(errors)))
        message = '\n'.join(lines) or _('No había vehículos para actualizar.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Actualización de estado GPS'),
                'message': message,
                'sticky': bool(errors) or bool(skipped),
                'type': 'danger' if errors else ('warning' if skipped else 'success'),
            },
        }

    # ── Entrada (b): acción masiva desde la lista de vehículos ──────────
    def action_sync_traccar_bulk(self):
        """Sincroniza en Traccar todos los vehículos de `self` que
        califiquen (IMEI + cuenta activa + email de contacto). Pensada
        tanto para poner al día de una sola vez todos los vehículos que ya
        existían antes de instalar este módulo, como para lotes de
        vehículos nuevos más adelante — es exactamente la misma lógica que
        el botón individual (ver adt.traccar.device.credential.register_vehicle).

        Se autentica UNA sola vez contra Traccar y se reutiliza esa sesión
        para todos los vehículos del lote (en vez de loguearse de nuevo por
        cada uno) — importante cuando `self` es la flota completa (ver
        action_sync_traccar_all_fleet)."""
        Credential = self.env['adt.traccar.device.credential']

        try:
            client = TraccarClient.from_env(self.env)
            client.authenticate()
        except TraccarAPIError as exc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sincronización con Traccar'),
                    'message': _('No se pudo conectar con Traccar: %s') % exc,
                    'sticky': True,
                    'type': 'danger',
                },
            }

        synced, skipped, errors = [], [], []
        for vehicle in self:
            label = vehicle.license_plate or vehicle.display_name or ('ID %s' % vehicle.id)
            try:
                Credential.register_vehicle(vehicle, client=client)
                synced.append(label)
            except AdtTraccarNotEligible as exc:
                skipped.append('%s (%s)' % (label, exc))
            except UserError as exc:
                # Error real (API de Traccar, config faltante, etc.) — no
                # interrumpe el lote, se reporta y se sigue con el resto.
                errors.append('%s (%s)' % (label, exc))

        lines = []
        if synced:
            lines.append(_('Sincronizados (%s): %s') % (len(synced), ', '.join(synced)))
        if skipped:
            lines.append(_('Omitidos (%s): %s') % (len(skipped), '; '.join(skipped)))
        if errors:
            lines.append(_('Con error (%s): %s') % (len(errors), '; '.join(errors)))
        message = '\n'.join(lines) or _('No había vehículos para sincronizar.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronización con Traccar'),
                'message': message,
                'sticky': bool(errors) or bool(skipped),
                'type': 'danger' if errors else ('warning' if skipped else 'success'),
            },
        }

    def action_sync_traccar_all_fleet(self):
        """Acceso directo (menú, sin necesidad de seleccionar filas):
        sincroniza TODA la flota activa de una sola vez. Internamente es
        exactamente action_sync_traccar_bulk, solo que resuelve acá el
        recordset completo en vez de depender de una selección manual en
        la lista — pensado para "poner al día" toda la flota que ya
        existía antes de instalar este módulo con un solo click."""
        return self.search([]).action_sync_traccar_bulk()
