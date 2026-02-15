# -*- coding: utf-8 -*-
{
    'name': 'ADT Mantenimiento Mecánico',
    'version': '1.0.0',
    'author': 'Bigodoo',
    'maintainer': 'Bigodoo',
    'category': 'Fleet',
    'summary': 'Gestión Completa de Mantenimiento Mecánico para Motocicletas y Mototaxis',
    'description': """
        Sistema integral de gestión de órdenes de mantenimiento mecánico.

        Características principales:
        - Gestión completa de órdenes de mantenimiento
        - Control de vehículos, clientes y créditos
        - Inspección detallada y diagnóstico
        - Control de fluidos y repuestos
        - Gestión de mecánicos y mano de obra
        - Control de calidad pre-entrega
        - Facturación y costos integrados
        - Programación de mantenimientos futuros
        - Sistema de autorizaciones y firmas digitales
    """,
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'product',
        'stock',
        'account',
    ],
    'data': [
        # Security
        'security/security_groups.xml',
        'security/ir.model.access.csv',

        # Data
        'data/sequence.xml',
        'data/vehicle_data.xml',

        # Views - Orden de carga importante
        'views/adt_vehiculo_views.xml',
        'views/adt_cliente_views.xml',
        'views/adt_mecanico_views.xml',
        'views/adt_orden_mantenimiento_views.xml',

        # Menús
        'views/menu_views.xml',
    ],
    'demo': [],
    'assets': {
        'web.assets_backend': [
            'adt_mantenimiento_mecanico/static/src/css/styles.css',
            'adt_mantenimiento_mecanico/static/src/js/widgets.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
