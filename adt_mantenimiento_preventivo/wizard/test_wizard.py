# -*- coding: utf-8 -*-
"""
Wizard de simulación: permite probar todo el flujo de mantenimiento
preventivo (motor de reglas + envío de notificación) sin depender de un
servidor Traccar real ni de un dispositivo FCM real.

Crea (o reutiliza) un vehículo, un cliente y un dispositivo FCM de prueba,
dispara el motor de reglas con el kilometraje que se indique, y opcionalmente
fuerza un envío de notificación inmediato (ignorando el horario programado)
para validar la entrega punta a punta.
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PLACA_PRUEBA_DEFAULT = 'PRUEBA-001'
NOMBRE_PARTNER_PRUEBA = 'Cliente de Prueba (Mantenimiento Preventivo)'
NOMBRE_MODELO_PRUEBA = 'PRUEBA (Mantenimiento Preventivo)'
NOMBRE_MARCA_PRUEBA = 'PRUEBA'
DEVICE_ID_PRUEBA = 'PRUEBA-DEVICE'


class AdtMantenimientoTestWizard(models.TransientModel):
    _name = 'adt.mantenimiento.test.wizard'
    _description = 'Simular Escenario de Prueba de Mantenimiento Preventivo'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo de prueba',
        help='Déjalo vacío para crear uno nuevo con la placa de abajo (o reutilizar '
             'uno ya creado por una simulación anterior con la misma placa).',
    )
    placa_prueba = fields.Char(string='Placa de prueba', default=PLACA_PRUEBA_DEFAULT)
    partner_id = fields.Many2one(
        'res.partner', string='Cliente de prueba',
        help='Déjalo vacío para crear/reutilizar un cliente de prueba genérico.',
    )

    regla_id = fields.Many2one(
        'adt.mantenimiento.regla', string='Regla a simular', required=True,
        default=lambda self: self._default_regla_id(),
    )

    usar_traccar_real = fields.Boolean(
        string='Consultar Traccar real (en vez de simular el km)',
        help='Requiere seleccionar arriba un vehículo EXISTENTE cuya placa '
             'coincida exactamente con el nombre de un dispositivo en Traccar. '
             'Se autentica contra Traccar, busca el dispositivo por placa, lee '
             'su kilometraje real (attributes.totalDistance) y con ESE valor '
             'se evalúa la regla elegida — igual que el Job A real, pero para '
             'un solo vehículo y de forma inmediata.',
    )
    km_simulado = fields.Float(
        string='Kilometraje simulado', required=True,
        default=lambda self: self._default_km_simulado(),
        help='Se evalúa solo contra la regla elegida (no contra todas las reglas '
             'activas), para que la simulación sea predecible. Se ignora si '
             '"Consultar Traccar real" está activo.',
    )

    fcm_token = fields.Char(
        string='Token FCM real (opcional)',
        help='Pon el token de tu celular para recibir el push de prueba de verdad. '
             'Si lo dejas vacío, se usa un token ficticio (no llega nada al celular, '
             'pero puedes revisar el resultado en la bitácora).',
    )
    log_only = fields.Boolean(
        string='Modo prueba (no llamar al endpoint real)', default=True,
        help='Si está activo, el envío solo queda registrado en el log y la '
             'bitácora; no se hace la llamada HTTP real al servicio de push.',
    )
    forzar_envio_inmediato = fields.Boolean(
        string='Forzar un envío de prueba inmediato', default=True,
        help='Si la simulación dispara una campaña nueva, envía de inmediato una '
             'notificación de esa campaña, ignorando el horario configurado.',
    )

    @api.model
    def _default_regla_id(self):
        return self.env['adt.mantenimiento.regla'].search([('active', '=', True)], limit=1)

    @api.model
    def _default_km_simulado(self):
        regla = self._default_regla_id()
        primer_umbral = regla.umbral_ids.sorted('orden')[:1]
        return (primer_umbral.km_umbral + 50) if primer_umbral else 650.0

    @api.onchange('regla_id')
    def _onchange_regla_id(self):
        for rec in self:
            if not rec.regla_id:
                continue
            primer_umbral = rec.regla_id.umbral_ids.sorted('orden')[:1]
            if primer_umbral:
                rec.km_simulado = primer_umbral.km_umbral + 50

    # ─────────────────────────────────────────────────────────────
    # Simular
    # ─────────────────────────────────────────────────────────────
    def action_simular(self):
        self.ensure_one()
        if self.usar_traccar_real and not self.vehicle_id:
            raise UserError(
                'Para probar contra Traccar real, selecciona arriba un vehículo '
                'EXISTENTE cuya placa coincida con el nombre de un dispositivo en '
                'Traccar (no se puede autogenerar uno de prueba para este caso).'
            )

        vehicle = self._get_or_create_vehicle()
        partner = self._get_or_create_partner()
        if vehicle.driver_id != partner:
            vehicle.driver_id = partner.id
        device = self._get_or_create_fcm_device(partner)

        if self.usar_traccar_real:
            km_actual = self._leer_km_real_de_traccar(vehicle)
            origen_km = 'Traccar real'
        else:
            km_actual = self.km_simulado
            vehicle.traccar_km_actual = km_actual
            origen_km = 'simulado manualmente'

        Campana = self.env['adt.mantenimiento.campana'].sudo()
        campanas_antes = Campana.search([
            ('vehicle_id', '=', vehicle.id), ('regla_id', '=', self.regla_id.id),
        ])

        Motor = self.env['adt.mantenimiento.motor.reglas']
        campanas_creadas = Motor._evaluar_regla_para_vehiculo(vehicle, self.regla_id, km_actual)

        campana_nueva = Campana.search([
            ('vehicle_id', '=', vehicle.id), ('regla_id', '=', self.regla_id.id),
            ('id', 'not in', campanas_antes.ids),
        ], order='id desc', limit=1)

        resumen = [
            'Vehículo: %s (id=%s)' % (vehicle.license_plate, vehicle.id),
            'Cliente: %s' % partner.display_name,
            'Dispositivo FCM: %s (token %s)' % (
                device.device_id, 'real' if (self.fcm_token or '').strip() else 'ficticio',
            ),
            'Km (%s): %.0f' % (origen_km, km_actual),
            'Regla evaluada: %s' % self.regla_id.name,
            'Campañas nuevas creadas: %d' % campanas_creadas,
        ]

        if campana_nueva and self.forzar_envio_inmediato:
            enviado = campana_nueva._enviar_una_notificacion(log_only=self.log_only)
            ultimo_log = campana_nueva.log_ids.sorted('fecha_hora', reverse=True)[:1]
            detalle = ultimo_log.detalle if ultimo_log else ''
            resumen.append(
                'Envío de prueba inmediato: %s (%s)' % ('OK' if enviado else 'FALLÓ', detalle)
            )
        elif self.forzar_envio_inmediato:
            resumen.append(
                'No se forzó envío: no se creó ninguna campaña nueva con ese km '
                '(puede que ya existiera o que el km no alcance el siguiente umbral).'
            )

        vehicle.message_post(
            subject='Simulación de mantenimiento preventivo',
            body='<br/>'.join(resumen),
        )
        _logger.info('[ADT Mantenimiento][Simulación] %s', ' | '.join(resumen))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Resultado de la simulación',
            'res_model': 'fleet.vehicle',
            'view_mode': 'form',
            'res_id': vehicle.id,
            'target': 'current',
        }

    def _leer_km_real_de_traccar(self, vehicle):
        """
        Réplica, para UN solo vehículo, del paso de lectura del Job A real
        (ver models/cron_service.py): autentica contra Traccar, busca el
        dispositivo por placa y lee su kilometraje real. De paso actualiza
        también el estado de reporte GPS (sección 4.1), para poder probar
        ese caso en la misma corrida.
        """
        self.ensure_one()
        log_prefix = '[ADT Mantenimiento][Simulación][Traccar]'
        placa = (vehicle.license_plate or '').strip().upper()
        _logger.info(
            '%s Iniciando consulta real a Traccar. vehículo id=%s placa=%s',
            log_prefix, vehicle.id, placa or '(sin placa)',
        )
        if not placa:
            _logger.error('%s El vehículo id=%s no tiene placa configurada.', log_prefix, vehicle.id)
            raise UserError('El vehículo no tiene placa configurada; no se puede buscar en Traccar.')

        Client = self.env['adt.mantenimiento.traccar.client']
        try:
            _logger.info('%s Paso 1/4: leyendo configuración de Traccar (Ajustes → Traccar).', log_prefix)
            cfg = Client._get_config()
            _logger.info('%s Paso 2/4: autenticando contra %s.', log_prefix, cfg['url'])
            jsessionid = Client._authenticate(cfg)
            _logger.info('%s Paso 3/4: buscando placa "%s" entre los dispositivos de Traccar.', log_prefix, placa)
            devices_by_plate = Client._get_devices_by_plate(cfg, jsessionid)
        except (ValueError, RuntimeError) as exc:
            _logger.error('%s Falló antes de llegar a leer la posición: %s', log_prefix, exc)
            raise UserError('No se pudo conectar con Traccar: %s' % exc)

        device = devices_by_plate.get(placa)
        if not device:
            _logger.error(
                '%s Placa "%s" NO encontrada en Traccar. Placas disponibles: %s',
                log_prefix, placa, ', '.join(sorted(devices_by_plate.keys())) or '(ninguna)',
            )
            raise UserError(
                'No se encontró en Traccar ningún dispositivo con nombre igual a la '
                'placa "%s". Verifica que el nombre del dispositivo en Traccar '
                'coincida exactamente con la placa del vehículo.' % placa
            )
        _logger.info(
            '%s Placa "%s" encontrada: device_id=%s status=%s lastUpdate=%s',
            log_prefix, placa, device.get('id'), device.get('status'), device.get('lastUpdate'),
        )

        _logger.info('%s Paso 4/4: leyendo kilometraje (última posición) del dispositivo.', log_prefix)
        km_actual, ultima_fecha_reporte = Client.get_km_and_last_report(cfg, jsessionid, device)
        if km_actual is None:
            _logger.error(
                '%s El dispositivo "%s" no devolvió kilometraje utilizable. Revisa los '
                'logs "[ADT Mantenimiento][Traccar]" de arriba para ver la posición cruda.',
                log_prefix, placa,
            )
            raise UserError(
                'Traccar no devolvió kilometraje (attributes.totalDistance) para el '
                'dispositivo "%s". Puede que no tenga posiciones registradas todavía.' % placa
            )

        _logger.info(
            '%s ÉXITO: placa=%s km_actual=%.1f última_fecha_reporte=%s',
            log_prefix, placa, km_actual, ultima_fecha_reporte,
        )

        vehicle.write({
            'traccar_device_id': device.get('id'),
            'traccar_km_actual': km_actual,
            'traccar_ultima_sincronizacion': fields.Datetime.now(),
        })

        Motor = self.env['adt.mantenimiento.motor.reglas']
        Motor._evaluar_reporte_gps(vehicle, ultima_fecha_reporte)

        return km_actual

    def _get_or_create_vehicle(self):
        self.ensure_one()
        if self.vehicle_id:
            return self.vehicle_id
        Vehicle = self.env['fleet.vehicle'].sudo()
        placa = (self.placa_prueba or PLACA_PRUEBA_DEFAULT).strip().upper()
        vehicle = Vehicle.search([('license_plate', '=', placa)], limit=1)
        if vehicle:
            return vehicle
        model = self._get_or_create_modelo_prueba()
        return Vehicle.create({'model_id': model.id, 'license_plate': placa})

    def _get_or_create_modelo_prueba(self):
        Model = self.env['fleet.vehicle.model'].sudo()
        model = Model.search([('name', '=', NOMBRE_MODELO_PRUEBA)], limit=1)
        if model:
            return model
        Brand = self.env['fleet.vehicle.model.brand'].sudo()
        brand = Brand.search([('name', '=', NOMBRE_MARCA_PRUEBA)], limit=1)
        if not brand:
            brand = Brand.create({'name': NOMBRE_MARCA_PRUEBA})
        return Model.create({'name': NOMBRE_MODELO_PRUEBA, 'brand_id': brand.id})

    def _get_or_create_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('name', '=', NOMBRE_PARTNER_PRUEBA)], limit=1)
        if partner:
            return partner
        return Partner.create({'name': NOMBRE_PARTNER_PRUEBA})

    def _get_or_create_fcm_device(self, partner):
        self.ensure_one()
        FCM = self.env['mobile.fcm.device'].sudo()
        device = FCM.search([
            ('partner_id', '=', partner.id), ('device_id', '=', DEVICE_ID_PRUEBA),
        ], limit=1)
        token = (self.fcm_token or '').strip() or ('TEST-TOKEN-%s' % partner.id)
        if device:
            device.write({'fcm_token': token, 'active': True})
            return device
        return FCM.create({
            'partner_id': partner.id,
            'fcm_token': token,
            'platform': 'android',
            'device_id': DEVICE_ID_PRUEBA,
            'device_name': 'Dispositivo de Prueba (Mantenimiento Preventivo)',
        })

    # ─────────────────────────────────────────────────────────────
    # Limpieza
    # ─────────────────────────────────────────────────────────────
    def action_limpiar_datos_prueba(self):
        """
        Elimina todos los vehículos con placa 'PRUEBA-%' (y en cascada sus
        campañas, estados de regla y estado de reporte GPS) y los clientes
        'Cliente de Prueba%' junto con sus dispositivos FCM.
        """
        Vehicle = self.env['fleet.vehicle'].sudo()
        vehicles = Vehicle.search([('license_plate', 'like', 'PRUEBA-%')])
        eliminados, no_eliminados = 0, 0
        for vehicle in vehicles:
            try:
                with self.env.cr.savepoint():
                    vehicle.unlink()
                eliminados += 1
            except Exception as exc:
                no_eliminados += 1
                _logger.warning(
                    '[ADT Mantenimiento][Simulación] No se pudo eliminar vehículo %s: %s',
                    vehicle.id, exc,
                )

        Partner = self.env['res.partner'].sudo()
        partners = Partner.search([('name', 'like', NOMBRE_PARTNER_PRUEBA + '%')])
        self.env['mobile.fcm.device'].sudo().search([('partner_id', 'in', partners.ids)]).unlink()
        partners_eliminados = 0
        for partner in partners:
            try:
                with self.env.cr.savepoint():
                    partner.unlink()
                partners_eliminados += 1
            except Exception as exc:
                _logger.warning(
                    '[ADT Mantenimiento][Simulación] No se pudo eliminar cliente de prueba %s: %s',
                    partner.id, exc,
                )

        mensaje = '%d vehículo(s) y %d cliente(s) de prueba eliminados.' % (eliminados, partners_eliminados)
        if no_eliminados:
            mensaje += ' %d vehículo(s) no se pudieron eliminar (tienen otros registros vinculados).' % no_eliminados

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Limpieza de datos de prueba',
                'message': mensaje,
                'type': 'success',
                'sticky': True,
            },
        }
