# -*- coding: utf-8 -*-
"""
Job A — Lector de kilometraje y motor de reglas.

Ver propuesta-mantenimiento-preventivo-traccar.md, secciones 3 y 4.

Corre una vez al día (cron nocturno, ver data/ir_cron_data.xml):
    1. Para cada vehículo activo con placa, hace match contra Traccar
       (nombre de dispositivo == placa) y lee su kilometraje acumulado.
    2. Evalúa cada regla de mantenimiento activa contra ese kilometraje
       usando VehicleRuleState (motor de umbrales, sección 4).
    3. Si corresponde, crea una NotificationCampaign (sección 2.4).
    4. De paso, evalúa si el vehículo dejó de reportar GPS (sección 4.1).

Este job NO envía notificaciones (eso lo hace el Job B, ver
notification_campaign.py: cron_enviar_notificaciones_campanas).
"""
import logging
from datetime import timezone

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

DIAS_SIN_REPORTE_DEFAULT = 3


class AdtMantenimientoMotorReglas(models.AbstractModel):
    _name = 'adt.mantenimiento.motor.reglas'
    _description = 'Motor de Reglas de Mantenimiento Preventivo (Job A)'

    @api.model
    def cron_leer_kilometraje_y_evaluar_reglas(self):
        Vehicle = self.env['fleet.vehicle'].sudo()
        vehicles = Vehicle.search([('active', '=', True), ('license_plate', '!=', False)])
        _logger.info(
            '[ADT Mantenimiento] Job A: iniciando. %d vehículo(s) activo(s) con placa a evaluar.',
            len(vehicles),
        )

        Client = self.env['adt.mantenimiento.traccar.client']
        try:
            cfg = Client._get_config()
            jsessionid = Client._authenticate(cfg)
            devices_by_plate = Client._get_devices_by_plate(cfg, jsessionid)
        except (ValueError, RuntimeError) as exc:
            _logger.error('[ADT Mantenimiento] Job A ABORTADO (no se pudo conectar a Traccar): %s', exc)
            return {'procesados': 0, 'campanas_creadas': 0, 'error': str(exc)}

        campanas_creadas = 0
        procesados = 0
        sin_match = []

        for vehicle in vehicles:
            placa = (vehicle.license_plate or '').strip().upper()
            device = devices_by_plate.get(placa)
            if not device:
                sin_match.append(placa)
                continue

            procesados += 1
            try:
                # savepoint por vehículo: si algo falla procesando este
                # vehículo (red, dato corrupto), no debe tumbar el resto del
                # cron ni dejar la transacción abortada para los siguientes.
                with self.env.cr.savepoint():
                    km_actual, ultima_fecha_reporte = Client.get_km_and_last_report(cfg, jsessionid, device)

                    vals = {
                        'traccar_device_id': device.get('id'),
                        'traccar_ultima_sincronizacion': fields.Datetime.now(),
                    }
                    if km_actual is not None:
                        vals['traccar_km_actual'] = km_actual
                    vehicle.write(vals)

                    self._evaluar_reporte_gps(vehicle, ultima_fecha_reporte)

                    if km_actual is not None:
                        creadas = self._evaluar_reglas_vehiculo(vehicle, km_actual)
                        campanas_creadas += creadas
                        _logger.info(
                            '[ADT Mantenimiento] Job A: placa=%s km_actual=%.1f → %d campaña(s) nueva(s).',
                            placa, km_actual, creadas,
                        )
                    else:
                        _logger.warning(
                            '[ADT Mantenimiento] Job A: placa=%s SIN kilometraje utilizable, '
                            'no se evaluó ninguna regla (ver logs "[ADT Mantenimiento][Traccar]" arriba).',
                            placa,
                        )
            except Exception as exc:
                _logger.exception(
                    '[ADT Mantenimiento] Job A: error procesando placa=%s (device_id=%s): %s',
                    placa, device.get('id'), exc,
                )

        if sin_match:
            _logger.warning(
                '[ADT Mantenimiento] Job A: %d vehículo(s) sin match en Traccar (placa no encontrada '
                'como nombre de dispositivo): %s',
                len(sin_match), ', '.join(sin_match),
            )

        _logger.info(
            '[ADT Mantenimiento] Job A finalizado. Vehículos con match en Traccar=%d | Sin match=%d | '
            'Campañas nuevas=%d',
            procesados, len(sin_match), campanas_creadas,
        )
        return {'procesados': procesados, 'campanas_creadas': campanas_creadas}

    # ─────────────────────────────────────────────────────────────
    # Motor de reglas (sección 4)
    # ─────────────────────────────────────────────────────────────
    def _evaluar_reglas_vehiculo(self, vehicle, km_actual):
        reglas = self.env['adt.mantenimiento.regla'].sudo().search([('active', '=', True)])
        return sum(self._evaluar_regla_para_vehiculo(vehicle, regla, km_actual) for regla in reglas)

    def _evaluar_regla_para_vehiculo(self, vehicle, regla, km_actual):
        """
        Evalúa UNA regla contra el km_actual de UN vehículo. Aislado del resto
        de reglas para poder reutilizarse tanto desde el Job A (todas las
        reglas activas) como desde el wizard de simulación (una sola regla
        elegida a mano).

        Regla de negocio: km_actual cae en el "bucket" delimitado por dos
        umbrales consecutivos (ej. 500km < km_actual < 1000km), y se dispara
        UNA sola campaña para el umbral inferior de ese bucket (el más alto
        que km_actual ya alcanzó), no una por cada umbral intermedio que se
        haya saltado. Ej: con umbrales [500, 1000, 2000, 3000] y
        km_actual=1500 se dispara solo el umbral de 1000 (no también el de
        500); con km_actual=2500 se dispara solo el de 2000.

        Los umbrales intermedios saltados quedan marcados como "pasados"
        (ultimo_umbral_orden avanza directo al umbral disparado) sin generar
        una notificación individual para ellos.
        """
        RuleState = self.env['adt.mantenimiento.vehicle.rule.state'].sudo()
        Campana = self.env['adt.mantenimiento.campana'].sudo()
        state = RuleState._get_or_create(vehicle.id, regla.id)

        pendientes = regla.umbral_ids.filtered(
            lambda u: u.activo and u.orden > state.ultimo_umbral_orden
        ).sorted('orden')
        alcanzados = pendientes.filtered(lambda u: km_actual >= u.km_umbral)
        if not alcanzados:
            # Todavía no llega al siguiente umbral pendiente, o no hay más
            # umbrales configurados por ahora (queda a la espera).
            return 0

        umbral_a_disparar = alcanzados[-1]  # el más alto ya alcanzado

        Campana.create({
            'vehicle_id': vehicle.id,
            'regla_id': regla.id,
            'umbral_id': umbral_a_disparar.id,
            'km_al_disparo': km_actual,
            'dias_totales': regla.dias_notificacion,
            'notificaciones_por_dia': regla.notificaciones_por_dia,
        })

        state.write({
            'ultimo_umbral_orden': umbral_a_disparar.orden,
            'estado': 'campana_activa',
            'fecha_disparo': fields.Datetime.now(),
        })

        return 1

    # ─────────────────────────────────────────────────────────────
    # Alerta de vehículo sin reporte (sección 4.1)
    # ─────────────────────────────────────────────────────────────
    def _evaluar_reporte_gps(self, vehicle, ultima_fecha_reporte):
        Status = self.env['adt.mantenimiento.vehicle.report.status'].sudo()
        status = Status._get_or_create(vehicle.id)

        if ultima_fecha_reporte:
            # Traccar puede devolver la fecha con tzinfo; Odoo Datetime la
            # necesita naive en UTC.
            if ultima_fecha_reporte.tzinfo is not None:
                ultima_fecha_reporte = ultima_fecha_reporte.astimezone(timezone.utc).replace(tzinfo=None)
            status.ultima_fecha_reporte = ultima_fecha_reporte

        dias_umbral = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'adt_mantenimiento.dias_sin_reporte', DIAS_SIN_REPORTE_DEFAULT
            )
        )

        if status.dias_sin_reportar >= dias_umbral and not status.alerta_sin_reporte_enviada:
            vehicle.message_post(
                body=(
                    '⚠️ El vehículo %s lleva %s día(s) sin reportar posición GPS.'
                    % (vehicle.license_plate, status.dias_sin_reportar)
                ),
                subject='Alerta GPS: vehículo sin reportar',
            )
            status.alerta_sin_reporte_enviada = True
        elif status.dias_sin_reportar < dias_umbral and status.alerta_sin_reporte_enviada:
            status.alerta_sin_reporte_enviada = False
