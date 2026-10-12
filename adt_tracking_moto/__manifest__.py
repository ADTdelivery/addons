# -*- coding: utf-8 -*-
{
    'name': 'ADT Tracking de Motos',
    'version': '15.0.1.2.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Seguimiento de cada moto desde el recojo en el distribuidor hasta la entrega al cliente',
    'description': """
Tracking de motos
=================
* Toda moto que se crea en flota sin placa y sin dueño (p. ej. desde la factura)
  entra automáticamente al tracking.
* Flujo logístico de 4 etapas fijas (nombre editable): recojo en distribuidor,
  almacén de la empresa, fibra (en un taller configurable) y listo para asignar.
* Flujo de placa en paralelo, sincronizado con el trámite de adt_tramite_placa.
* Historial con tiempos por etapa y reporte de tiempos.
    """,
    'author': 'CM Innovación',
    'depends': [
        'fleet',
        'mail',
        'account',
        'adt_tramite_placa',
        'adt_facturacion_v1',
        'adt_fleet',
    ],
    'data': [
        'security/tracking_groups.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/tracking_etapa_data.xml',
        'data/tracking_taller_data.xml',
        'wizard/enviar_fibra_wizard_views.xml',
        'wizard/sincronizar_wizard_views.xml',
        'views/tracking_views.xml',
        'views/tracking_log_views.xml',
        'views/tracking_etapa_views.xml',
        'views/tracking_taller_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/fleet_vehicle_operacion_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_tracking_moto/static/src/scss/kanban.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
