# -*- coding: utf-8 -*-
{
    'name': 'ADT Mantenimiento Preventivo (Traccar)',
    'version': '15.0.1.0.0',
    'category': 'Operations/Fleet',
    'summary': 'Alertas de mantenimiento preventivo por kilometraje (Traccar) vía notificaciones push',
    'description': '''
        ADT Mantenimiento Preventivo
        ============================

        Implementación de la propuesta "propuesta-mantenimiento-preventivo-traccar.md":

        - Lee diariamente el kilometraje acumulado de cada vehículo desde Traccar
          (match por placa contra el nombre del dispositivo).
        - Evalúa ese kilometraje contra reglas de mantenimiento configurables
          (aceite, frenos, etc.), cada una con su propia secuencia de umbrales
          de kilometraje (no un intervalo fijo).
        - Por cada regla se puede configurar cuántos DÍAS dura la campaña de
          notificaciones y cuántas NOTIFICACIONES se envían por día.
        - Genera campañas de notificación y las envía por push (Firebase),
          reutilizando el mismo servicio HTTP y el modelo mobile.fcm.device
          del módulo ADT Comercial.
        - El cliente a notificar se resuelve así: placa (Traccar) → vehículo
          (Flota) → contrato comercial vigente → cliente (res.partner) →
          dispositivos FCM de ese cliente.
        - Alerta en el chatter del vehículo cuando este deja de reportar GPS
          por N días (configurable).
    ''',
    'author': 'ADT',
    'depends': ['base', 'fleet', 'mail', 'adt_comercial', 'adt_traccar'],
    'data': [
        'security/ir.model.access.csv',
        'data/mantenimiento_horario_slot_data.xml',
        'data/mantenimiento_regla_data.xml',
        'data/origen_atencion_data.xml',
        'data/ir_cron_data.xml',
        'views/horario_slot_views.xml',
        'views/mantenimiento_regla_views.xml',
        'views/vehicle_rule_state_views.xml',
        'views/campana_views.xml',
        'views/vehicle_report_status_views.xml',
        'views/orden_atencion_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/res_config_settings_views.xml',
        'views/test_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
