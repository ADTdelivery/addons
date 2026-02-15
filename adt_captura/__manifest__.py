# -*- coding: utf-8 -*-
{
    'name': 'ADT Captura',
    'version': '1.1.3',
    'category': 'Custom',
    'summary': 'Gestión de Capturas de Vehículos en Mora',
    'description': """
        Módulo para gestionar el proceso completo de captura de vehículos:
        - Identificación de clientes en mora
        - Registro de capturas con evidencia
        - Gestión de pagos de intervención
        - Control de liberación y retención
        - Historial y trazabilidad completa
    """,
    'author': 'ADT',
    'depends': ['base', 'web', 'fleet', 'adt_comercial'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/adt_captura_record_views.xml',
        'views/adt_captura_mora_views.xml',
        'views/wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
