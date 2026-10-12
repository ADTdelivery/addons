# -*- coding: utf-8 -*-
{
    'name': 'ADT Dashboard de Flota',
    'version': '15.0.2.0.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Dashboard operativo de flota: stock, placas, flujo y alertas',
    'description': """
Dashboard de Flota
==================
* Indicadores: flota, con placa, stock disponible, listas para entregar, proceso completo.
* Combinaciones dueño × placa.
* Alertas operativas (cliente sin placa, trámites observados o sin iniciar, motos demoradas,
  stock envejecido, asignadas antes de estar listas, vehículos fuera del flujo).
* Flujo en curso por etapa y estado de placa, tiempos de ciclo (mediana y P85),
  ritmo semanal, antigüedad del stock y talleres de fibra.
* API JSON para la app de ventas: /api/stock/resumen, /api/stock/vehiculos,
  /api/stock/vehiculos/detalle.
    """,
    'author': 'CM Innovación',
    'depends': ['base', 'web', 'fleet', 'adt_tracking_moto', 'adt_tramite_placa'],
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
