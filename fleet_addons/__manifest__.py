# -*- coding: utf-8 -*-
{
    'name': "fleet_addons",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "My Company",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'fleet' , 'infraccion_addons','hr_fleet'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/templates.xml',
        'views/view_gps.xml',
        'views/view_agregar_papeleta.xml',
        'reports/fleet_custom_qorilazo.xml',
        'reports/fleet_custom_report.xml',
        'reports/fleet_custom_report2.xml',
        'reports/fleet_custom_report3.xml',
        'reports/fleet_custom_report4.xml',
        'reports/fleet_custom_mototaxi.xml',
        'reports/reglamento_fondo_contingencia.xml',
        'reports/contrato_alquiler_venta.xml',
        'reports/acta_entrega_voluntaria.xml',
        'reports/solicitud_afiliacion.xml',
        #'views/view_tramite_placa.xml'

    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
