{
    'name': 'ADT Crédito',
    'version': '15.0.1.0.0',
    'author': 'Bigodoo',
    'maintainer': 'Bigodoo',
    'summary': 'Venta de productos a crédito en cuotas fijas: cronograma, mora y refinanciamiento',
    'category': 'Sales',
    'depends': ['base', 'product', 'sale', 'mail'],
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/product_data.xml',
        'data/cron_mora.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        # Los wizards deben cargarse antes de las vistas de contrato/cuota: esas vistas
        # referencian las acciones de estos wizards en sus botones (%(adt_credito.action_...)d).
        'views/credito_refinanciamiento_views.xml',
        'views/credito_registrar_mora_views.xml',
        'views/credito_registrar_pago_views.xml',
        'views/credito_contrato_views.xml',
        'views/credito_cuota_views.xml',
        'views/credito_pago_views.xml',
        # El dashboard debe cargar antes que menu.xml: el menú referencia su acción.
        'views/dashboard_credito.xml',
        'views/menu.xml',
        'reports/report_cronograma.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_credito/static/src/scss/style.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
