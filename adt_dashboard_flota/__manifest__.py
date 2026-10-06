# -*- coding: utf-8 -*-
{
    'name': 'ADT Dashboard de Flota',
    'version': '15.0.1.1.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Dashboard gerencial de stock de motos (sin dueño) y placas listas',
    'description': """
Dashboard de Flota
==================
* Stock = vehículos activos de flota sin conductor/dueño asignado.
* Indicador de motos en stock con placa lista, en trámite y sin placa.
* Agrupaciones por modelo, año, color, estado de flota y estado de placa.
* Filtros cruzados dinámicos, mapa de calor modelo × año y detalle exportable.
* API JSON para la app de ventas: /api/stock/resumen, /api/stock/vehiculos,
  /api/stock/vehiculos/detalle.
    """,
    'author': 'CM Innovación',
    'depends': ['base', 'web', 'fleet'],
    'data': [
        'views/fleet_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_dashboard_flota/static/src/scss/fleet_dashboard.scss',
            'adt_dashboard_flota/static/src/js/fleet_dashboard.js',
        ],
        'web.assets_qweb': [
            'adt_dashboard_flota/static/src/xml/fleet_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
