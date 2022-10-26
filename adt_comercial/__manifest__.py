{
    'name': 'ADT Comercial',
    'version': '15.0.1.0.0',
    'author': 'Bigodoo',
    'maintainer': 'Bigodoo',
    'depends': [
        'base','sale', 'account', 'fleet','sms','mail'
    ],
    'data': [
        'data/sequences.xml',
        'data/recuperacion_data.xml',
        'data/action_view_sms.xml',
        'security/res_groups.xml',
        'views/view_comercial_socios.xml',
        'views/view_comercial_cuentas.xml',
        'views/view_comercial_payments.xml',
        'views/view_comercial_registrar_mora.xml',
        'views/view_comercial_registrar_observacion.xml',
        'views/view_comercial_refinanciamiento.xml',
        'views/view_cobranzas_pagos.xml',
        'views/view_cobranzas_capturas.xml',
        'views/view_cobranzas_config.xml',
        'views/view_vehiculo.xml',
        'views/view_warning_message.xml',
        'reports/external_layout_cronograma.xml',
        # 'reports/paperformat.xml',
        'reports/report.xml',
        'reports/reporte_cronograma_cuenta.xml'
    ],
    # 'assets': {
    #     'web.report_assets_common': [
    #         '/adt_comercial/static/src/scss/style.scss',
    #     ],
    # },
}
