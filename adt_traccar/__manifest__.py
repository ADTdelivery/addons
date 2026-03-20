{
    'name': 'ADT Traccar',
    'version': '15.0.1.0.0',
    'category': 'Operations/Fleet',
    'summary': 'Integración con Traccar GPS para gestión de vehículos',
    'description': '''
        ADT Traccar - Integración GPS con Traccar
        ==========================================

        Características:
        - Integración con plataforma GPS Traccar
        - Seguimiento en tiempo real de vehículos
        - Sincronización de dispositivos GPS con flota
        - Historial de posiciones y recorridos
        - Alertas y eventos de dispositivos GPS
    ''',
    'author': 'ADT',
    'depends': ['base', 'fleet', 'base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/adt_traccar_views.xml',
        'views/adt_traccar_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
