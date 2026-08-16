# -*- coding: utf-8 -*-
"""
Credenciales Traccar individuales por vehículo.

Ver plan-adt-traccar-device.md (raíz de addons/) para el diseño completo.

Resumen del criterio de negocio implementado aquí:
  - Un vehículo solo puede registrarse en Traccar si tiene una cuenta
    comercial activa en adt_comercial (state en_curso/aprobado) — mismo
    criterio que adt_fleet._get_cuenta_for_report().
  - Se crea SIEMPRE un usuario Traccar nuevo por vehículo (nunca se
    comparte un mismo usuario Traccar entre dos vehículos), para que el
    permiso quede acotado a un solo dispositivo por login.
  - El email de login Traccar se deriva del email real del contacto: el
    primer vehículo del cliente usa el email tal cual; el 2do/3er/...
    vehículo del mismo cliente agrega un sufijo "v{n}" al local-part
    (juan@gmail.com → juanv2@gmail.com → juanv3@gmail.com...).
  - El password se genera al azar y se guarda en texto plano en
    `traccar_password` (decisión explícita del cliente: sin cifrado ni
    variable de entorno adicional, para simplificar el deploy). El campo
    está restringido por el grupo adt_traccar_device.group_traccar_credentials_admin
    en las vistas — no cualquier usuario interno lo ve.
"""
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.traccar_client import TraccarClient, TraccarAPIError, parse_traccar_datetime

_logger = logging.getLogger(__name__)

ACTIVE_CUENTA_STATES = ('en_curso', 'aprobado')


class AdtTraccarNotEligible(UserError):
    """Se lanza cuando el vehículo simplemente no califica todavía para
    registrarse en Traccar (falta IMEI / cuenta activa / email de
    contacto). Se distingue de un UserError genérico (error real de la API
    de Traccar) para que la acción masiva pueda reportarlo como "omitido"
    en vez de "con error" — ver fleet_vehicle.action_sync_traccar_bulk."""
    pass


class AdtTraccarDeviceCredential(models.Model):
    _name = 'adt.traccar.device.credential'
    _description = 'Credenciales Traccar por vehículo'
    _order = 'create_date desc'
    _rec_name = 'plate'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo', required=True, index=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, index=True)
    cuenta_id = fields.Many2one(
        'adt.comercial.cuentas', string='Cuenta comercial',
        help='Cuenta activa que habilitó el registro (auditoría).')

    plate = fields.Char(string='Placa', required=True)
    imei = fields.Char(string='IMEI', required=True)

    traccar_device_id = fields.Integer(string='ID dispositivo (Traccar)', required=True)
    traccar_user_id = fields.Integer(string='ID usuario (Traccar)', required=True)

    partner_email_base = fields.Char(
        string='Email de contacto (base)',
        groups='adt_traccar_device.group_traccar_credentials_admin',
        help='Email de res.partner usado como base para derivar el email técnico.')
    email_sequence = fields.Integer(
        string='Secuencia de email', required=True, default=1,
        help='1 = email real del contacto. 2, 3... = variantes juanv2@, juanv3@... '
             'para que cada vehículo del mismo cliente tenga su propio login Traccar.')
    traccar_email = fields.Char(
        string='Email Traccar (login)', required=True,
        groups='adt_traccar_device.group_traccar_credentials_admin')
    traccar_password = fields.Char(
        string='Password Traccar',
        groups='adt_traccar_device.group_traccar_credentials_admin',
        help='Password en texto plano (decisión explícita: sin cifrado, para simplificar '
             'el deploy). Solo visible para el grupo "Traccar: Ver credenciales". En pantalla '
             'se muestra ofuscado con un botón de "ojo" para revelarlo (widget '
             'adt_password_toggle, ver static/src/js/).')

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('activo', 'Activo'),
        ('error', 'Error'),
        ('revocado', 'Revocado'),
    ], string='Estado', default='borrador', required=True, index=True)
    last_error = fields.Text(string='Último error')
    active = fields.Boolean(default=True)

    # ── Estado GPS (snapshot, se llena con action_refresh_gps_status) ─────
    # No se auto-actualiza solo: hace falta apretar "Actualizar" (desde acá
    # o desde el botón espejo en fleet.vehicle) para pedirle el dato fresco
    # a Traccar. gps_last_update es el reloj del DISPOSITIVO (cuándo reportó
    # por última vez); gps_status_refreshed_at es el reloj de ODOO (cuándo
    # se hizo el último click en "Actualizar") — son cosas distintas.
    gps_status = fields.Selection([
        ('online', 'En línea'),
        ('offline', 'Desconectado'),
        ('unknown', 'Desconocido'),
    ], string='Estado GPS', help='Tal como lo reporta Traccar (device.status).')
    gps_last_update = fields.Datetime(
        string='Último reporte del dispositivo',
        help='Cuándo el dispositivo GPS reportó por última vez a Traccar (device.lastUpdate).')
    gps_latitude = fields.Float(string='Latitud', digits=(10, 6))
    gps_longitude = fields.Float(string='Longitud', digits=(10, 6))
    gps_speed_kmh = fields.Float(
        string='Velocidad (km/h)', digits=(10, 1),
        help='Traccar reporta la velocidad en nudos; ya convertida a km/h acá (×1.852).')
    gps_battery_level = fields.Float(
        string='Batería (%)', digits=(5, 1),
        help='Solo disponible si el dispositivo lo reporta (attributes.batteryLevel). '
             '0 puede significar "no reportado", no necesariamente batería agotada.')
    gps_address = fields.Char(
        string='Dirección aproximada',
        help='Geocodificación inversa hecha por el propio servidor Traccar, si está configurada '
             'ahí. Puede venir vacía.')
    gps_maps_url = fields.Char(string='Ver en el mapa', compute='_compute_gps_maps_url')
    gps_status_refreshed_at = fields.Datetime(
        string='Actualizado en Odoo',
        help='Cuándo se apretó "Actualizar" por última vez en Odoo (no es lo mismo que '
             'gps_last_update, que es el reloj del dispositivo).')

    @api.depends('gps_latitude', 'gps_longitude')
    def _compute_gps_maps_url(self):
        for rec in self:
            if rec.gps_latitude or rec.gps_longitude:
                rec.gps_maps_url = 'https://www.google.com/maps?q=%s,%s' % (
                    rec.gps_latitude, rec.gps_longitude)
            else:
                rec.gps_maps_url = False

    _sql_constraints = [
        ('traccar_email_uniq', 'unique(traccar_email)',
         'Ya existe una credencial Traccar registrada con ese email técnico.'),
    ]

    @api.constrains('vehicle_id', 'state', 'active')
    def _check_single_active_credential_per_vehicle(self):
        for rec in self:
            if rec.state != 'activo' or not rec.active:
                continue
            other_active = self.search([
                ('vehicle_id', '=', rec.vehicle_id.id),
                ('state', '=', 'activo'),
                ('active', '=', True),
                ('id', '!=', rec.id),
            ], limit=1)
            if other_active:
                raise UserError(_(
                    'El vehículo "%s" ya tiene una credencial Traccar activa (%s). '
                    'Revóquela antes de activar otra.'
                ) % (rec.vehicle_id.display_name, other_active.traccar_email))

    # ── Helpers de email técnico ─────────────────────────────────────────
    @staticmethod
    def _split_email(email):
        if not email or '@' not in email:
            return None, None
        local, domain = email.split('@', 1)
        return local, domain

    def _compute_traccar_email(self, partner, sequence):
        local, domain = self._split_email(partner.email)
        if not local:
            return False
        if sequence <= 1:
            return partner.email
        return '%sv%s@%s' % (local, sequence, domain)

    def _next_email_sequence(self, partner):
        """Cuenta también credenciales inactivas/revocadas para no reciclar
        nunca un sufijo que Traccar ya haya conocido (ver plan, sección 3.1)."""
        count = self.with_context(active_test=False).search_count([
            ('partner_id', '=', partner.id),
        ])
        return count + 1

    # ── Resolución de cuenta activa / cliente ───────────────────────────
    def _get_active_cuenta(self, vehicle):
        """Mismo criterio que adt_fleet._get_cuenta_for_report(): prioriza
        en_curso, luego aprobado. A diferencia de ese helper, aquí NO se
        hace fallback a "cualquier cuenta" — si no hay una activa, no se
        puede registrar en Traccar."""
        Cuenta = self.env['adt.comercial.cuentas'].sudo()
        return (
            Cuenta.search([('vehiculo_id', '=', vehicle.id), ('state', '=', 'en_curso')],
                           limit=1, order='id desc')
            or Cuenta.search([('vehiculo_id', '=', vehicle.id), ('state', '=', 'aprobado')],
                              limit=1, order='id desc')
        )

    # ── Orquestador principal ────────────────────────────────────────────
    @api.model
    def register_vehicle(self, vehicle, imei=None, client=None):
        """Registra/sincroniza `vehicle` en Traccar. Idempotente por IMEI:

          - Si el vehículo NO tiene credencial activa todavía, o la tiene
            pero para OTRO IMEI (cambió el dispositivo físico): crea (o
            reutiliza) el device en Traccar por IMEI, crea un usuario
            Traccar NUEVO y exclusivo de este vehículo, le asigna permiso
            solo sobre su device, y persiste las credenciales.
            Si había una credencial activa previa, se revoca.
          - Si el vehículo YA tiene una credencial activa para el MISMO
            IMEI: no se crea ningún usuario/password nuevo — se devuelve
            la credencial existente tal cual (solo se renombra el device
            en Traccar si cambió la placa). Esto es lo que permite correr
            la sincronización masiva repetidas veces sobre toda la flota
            sin generar usuarios Traccar huérfanos en cada corrida.

        Devuelve siempre el registro adt.traccar.device.credential vigente
        (state='activo') para este vehículo.

        Usado tanto por el botón individual del formulario de fleet.vehicle
        como por la acción masiva de la vista de lista — es el único punto
        de entrada, no hay lógica distinta para vehículos nuevos vs.
        existentes (ver plan, sección 4.1).

        `client`: instancia de TraccarClient YA AUTENTICADA, opcional. Si no
        se pasa, se crea y autentica una recién cuando hace falta hablar con
        Traccar (después de las validaciones de elegibilidad, que son
        locales y no deberían gastar una llamada a Traccar si el vehículo
        ni siquiera califica). Si se pasa (ver fleet_vehicle.
        action_sync_traccar_bulk / action_sync_traccar_all_fleet), se
        reutiliza tal cual — así una sincronización masiva de N vehículos
        hace UN solo login contra Traccar en vez de N.
        """
        vehicle.ensure_one()

        plate = (vehicle.license_plate or '').strip()
        if not plate:
            raise AdtTraccarNotEligible(_('El vehículo no tiene placa.'))

        imei = (imei or vehicle.x_imei or '').strip()
        if not imei:
            raise AdtTraccarNotEligible(_(
                'El vehículo "%s" no tiene IMEI. Complételo antes de registrar en Traccar.'
            ) % plate)

        cuenta = self._get_active_cuenta(vehicle)
        if not cuenta:
            raise AdtTraccarNotEligible(_(
                'El vehículo "%s" no tiene una cuenta comercial activa (en curso o aprobada). '
                'No se puede registrar en Traccar.'
            ) % plate)

        partner = vehicle.driver_id or cuenta.partner_id
        if not partner:
            raise AdtTraccarNotEligible(_(
                'El vehículo "%s" no tiene cliente/conductor asignado.'
            ) % plate)
        if not partner.email:
            raise AdtTraccarNotEligible(_(
                'El cliente "%s" no tiene email registrado en Contactos. '
                'Complételo antes de continuar.'
            ) % partner.name)

        # ── Idempotencia: si el vehículo ya tiene una credencial activa
        # para ESTE MISMO IMEI (mismo dispositivo físico), no se crea un
        # usuario/password Traccar nuevo — se devuelve la credencial
        # existente tal cual (a lo sumo se renombra el device si cambió la
        # placa). Esto es lo que hace segura la sincronización masiva: se
        # puede correr sobre toda la flota las veces que sea sin generar
        # usuarios Traccar huérfanos en cada corrida. Un usuario/password
        # nuevo solo se emite cuando el IMEI cambió (device físico distinto)
        # o cuando no había ninguna credencial activa todavía.
        existing = self.search([
            ('vehicle_id', '=', vehicle.id), ('state', '=', 'activo'),
        ], limit=1)
        if existing and existing.imei == imei:
            update_vals = {}
            if existing.plate != plate:
                try:
                    if client is None:
                        client = TraccarClient.from_env(self.env)
                        client.authenticate()
                    client.update_device_name(existing.traccar_device_id, plate, imei)
                except TraccarAPIError as exc:
                    _logger.error(
                        '[adt_traccar_device] Error renombrando device %s en Traccar (vehicle=%s): %s',
                        existing.traccar_device_id, vehicle.id, exc,
                    )
                    raise UserError(str(exc))
                update_vals['plate'] = plate
            if existing.cuenta_id.id != cuenta.id:
                update_vals['cuenta_id'] = cuenta.id
            if update_vals:
                existing.write(update_vals)
            return existing

        sequence = self._next_email_sequence(partner)
        traccar_email = self._compute_traccar_email(partner, sequence)

        try:
            if client is None:
                client = TraccarClient.from_env(self.env)
                client.authenticate()
            device, _created = client.get_or_create_device(plate, imei)
            traccar_device_id = device['id']

            # Anti-colisión: si por algún motivo ese email técnico ya existe
            # en Traccar (ej. credencial borrada manualmente sin borrar el
            # usuario en Traccar), se incrementa la secuencia hasta hallar
            # una libre.
            while client.find_user_by_email(traccar_email):
                sequence += 1
                traccar_email = self._compute_traccar_email(partner, sequence)

            password_plain = secrets.token_urlsafe(12)
            traccar_user = client.create_user(partner.name, traccar_email, password_plain)
            client.add_permission(traccar_user['id'], traccar_device_id)
        except TraccarAPIError as exc:
            _logger.error(
                '[adt_traccar_device] Error registrando vehículo %s (placa=%s) en Traccar: %s',
                vehicle.id, plate, exc,
            )
            raise UserError(str(exc))

        # Si llegamos hasta acá con 'existing' seteado, es porque el IMEI
        # cambió (device físico distinto) — se revoca la credencial vieja;
        # nunca conviven dos activas para el mismo vehículo (ver
        # _check_single_active_credential_per_vehicle). Si 'existing' está
        # vacío, es simplemente el primer registro de este vehículo.
        if existing:
            existing.write({'state': 'revocado', 'active': False})

        return self.create({
            'vehicle_id': vehicle.id,
            'partner_id': partner.id,
            'cuenta_id': cuenta.id,
            'plate': plate,
            'imei': imei,
            'traccar_device_id': traccar_device_id,
            'traccar_user_id': traccar_user['id'],
            'partner_email_base': partner.email,
            'email_sequence': sequence,
            'traccar_email': traccar_email,
            'traccar_password': password_plain,
            'state': 'activo',
            'last_error': False,
        })

    # ── Acciones ─────────────────────────────────────────────────────────
    def get_plain_password(self):
        """Devuelve el password en texto plano (así se guarda). Solo debe
        llamarse desde el controller REST autenticado (4.3 del plan) o
        desde una acción explícita de "ver password" con permisos."""
        self.ensure_one()
        return self.traccar_password

    def action_regenerate_password(self):
        self.ensure_one()
        if self.state != 'activo':
            raise UserError(_('Solo se puede regenerar el password de una credencial activa.'))

        client = TraccarClient.from_env(self.env)
        new_password = secrets.token_urlsafe(12)
        try:
            client.authenticate()
            client.update_user_password(
                self.traccar_user_id, self.partner_id.name, self.traccar_email, new_password)
        except TraccarAPIError as exc:
            _logger.error(
                '[adt_traccar_device] Error regenerando password (credential=%s): %s', self.id, exc)
            raise UserError(str(exc))

        self.write({'traccar_password': new_password})
        return True

    def action_revoke(self):
        self.write({'state': 'revocado', 'active': False})

    def action_refresh_gps_status(self):
        """Consulta a Traccar en vivo el estado actual del dispositivo
        (online/offline, última posición, velocidad, batería si la
        reporta) y lo guarda en los campos gps_*. Es la acción detrás del
        botón "Actualizar" — no hay refresco automático/cron, es manual a
        propósito (así no se generan llamadas a Traccar de fondo sin que
        nadie las esté mirando)."""
        self.ensure_one()
        if self.state != 'activo':
            raise UserError(_('Solo se puede actualizar el estado de una credencial activa.'))

        client = TraccarClient.from_env(self.env)
        try:
            client.authenticate()
            device = client.get_device_by_id(self.traccar_device_id)
        except TraccarAPIError as exc:
            _logger.error(
                '[adt_traccar_device] Error consultando estado (credential=%s): %s', self.id, exc)
            raise UserError(str(exc))

        vals = {
            'gps_status': device.get('status') or 'unknown',
            'gps_last_update': parse_traccar_datetime(device.get('lastUpdate')),
            'gps_status_refreshed_at': fields.Datetime.now(),
        }

        position_id = device.get('positionId')
        if position_id:
            try:
                position = client.get_position(position_id)
            except TraccarAPIError as exc:
                # El device sí respondió — no tirar todo el refresco abajo
                # por un error puntual en /api/positions, solo se deja sin
                # actualizar la parte de posición/velocidad/batería.
                _logger.warning(
                    '[adt_traccar_device] No se pudo leer la posición %s (credential=%s): %s',
                    position_id, self.id, exc)
                position = None
            if position:
                attrs = position.get('attributes') or {}
                speed_knots = position.get('speed') or 0.0
                vals.update({
                    'gps_latitude': position.get('latitude') or 0.0,
                    'gps_longitude': position.get('longitude') or 0.0,
                    'gps_speed_kmh': speed_knots * 1.852,  # Traccar reporta velocidad en nudos
                    'gps_battery_level': attrs.get('batteryLevel') or 0.0,
                    'gps_address': position.get('address') or False,
                })

        self.write(vals)
        return True
