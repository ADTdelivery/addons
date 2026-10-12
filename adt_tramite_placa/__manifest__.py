# -*- coding: utf-8 -*-
{
    'name': 'ADT Trámite de Placa',
    'version': '15.0.1.0.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Seguimiento simple del trámite de placa de cada moto facturada',
    'description': """
Trámite de placa
================
* Al crear un vehículo desde la factura se crea su trámite de placa en estado Pendiente.
* Estados: Pendiente → En trámite (inicio manual) → Observado ⇄ En trámite → Finalizado → Historial.
* Los finalizados pasan solos a Historial tras N días (configurable, 7 por defecto).
* Al finalizar, el número de placa y la tarjeta de propiedad pasan al vehículo.
    """,
    'author': 'CM Innovación',
    'depends': ['fleet', 'mail', 'adt_facturacion_v1'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'wizard/observar_wizard_views.xml',
        'wizard/config_wizard_views.xml',
        'views/tramite_placa_views.xml',
        'views/fleet_vehicle_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_tramite_placa/static/src/scss/kanban.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
