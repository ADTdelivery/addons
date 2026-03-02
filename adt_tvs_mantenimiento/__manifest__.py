# -*- coding: utf-8 -*-
{
    'name': 'ADT TVS Mantenimiento',
    'version': '1.0.0',
    'summary': 'Module skeleton for TVS maintenance processes',
    'description': 'Manage vehicle entry, review and closure of maintenance with traceability and attachments.',
    'category': 'Tools',
    'author': 'Your Company',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'fleet'],
    'data': [
        'security/ir.model.access.csv',
        'data/adt_tvs_mantenimiento_sequences.xml',
        'views/adt_tvs_mantenimiento_menu.xml',
        'views/adt_tvs_mantenimiento_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
