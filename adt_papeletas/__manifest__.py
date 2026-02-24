# -*- coding: utf-8 -*-
{
    'name': "ADT Papeletas",
    'summary': "Gestión de papeletas vehiculares.",
    'description': """
        Módulo para gestionar papeletas vehiculares, incluyendo registro, seguimiento y control de vencimientos.
    """,
    'author': "Your Company",
    'website': "http://www.yourcompany.com",
    'category': 'Fleet Management',
    'version': '1.0',
    'depends': ['base', 'fleet'],
    'data': [
        'security/ir.model.access.csv',
        'views/adt_papeleta_form_view.xml',
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
