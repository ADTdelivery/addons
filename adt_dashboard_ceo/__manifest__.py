# -*- coding: utf-8 -*-
{
    'name': 'ADT Dashboard Ejecutivo',
    'version': '15.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Estado de la compañía para el CEO: ventas, cobranza, financieras, clientes, expedientes y flota',
    'description': """
Dashboard Ejecutivo
===================
Vista global para la toma de decisiones. Reúne en una sola pantalla los indicadores clave de
Comercial (ventas, cobranza, financieras, clientes), Expedientes y Flota, con alertas
automáticas y acceso directo al dashboard de cada área. Usa los mismos cálculos que cada
dashboard, por lo que los números siempre coinciden.
    """,
    'author': 'CM Innovación',
    'depends': ['web', 'adt_comercial', 'adt_expedientes', 'adt_dashboard_flota'],
    'data': [
        'views/ceo_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_dashboard_ceo/static/src/scss/ceo_dashboard.scss',
            'adt_dashboard_ceo/static/src/js/ceo_dashboard.js',
        ],
        'web.assets_qweb': [
            'adt_dashboard_ceo/static/src/xml/ceo_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
