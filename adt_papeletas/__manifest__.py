# -*- coding: utf-8 -*-
{
    'name': "ADT Papeletas",
    'summary': "Gestión de papeletas vehiculares.",
    'description': """
        Módulo para gestionar papeletas vehiculares, incluyendo registro, seguimiento y control de vencimientos.
        Integra las consultas del SAT Lima (monitor en EC2) mediante /api/papeletas/sat/import.
        Programas de consulta (por financiera, filtro o lista) con ejecución nocturna o manual
        y el informe de cada ejecución.
    """,
    'author': "Your Company",
    'website': "http://www.yourcompany.com",
    'category': 'Fleet Management',
    'version': '1.5',
    'depends': ['base', 'mail', 'fleet'],
    'data': [
        'security/ir.model.access.csv',
        'views/adt_papeleta_form_view.xml',
        'views/adt_papeleta_fleet_inherit_view.xml',
        'views/adt_papeleta_sat_views.xml',
        'views/adt_papeleta_sat_programa_views.xml',
        'data/adt_papeleta_sat_data.xml',
        'data/adt_papeleta_sat_estado_cuenta_data.xml',
        'data/adt_papeleta_sat_programa_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_papeletas/static/src/js/adt_papeleta_badge.js',
            'adt_papeletas/static/src/css/adt_papeleta_badge.css',
        ],
    },
    'demo': [
        # Demo data files
    ],
}
