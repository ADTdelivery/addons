{
    'name': 'ADT Expedientes',
    'version': '15.0.2.0.0',
    'category': 'Operations',
    'summary': 'Gestión de expedientes (formulario único estilo desktop)',
    'author': 'ADT',
    'depends': ['base', 'mail'],
    'data': [
        'views/report_expediente.xml',
        'security/ir.model.access.csv',
        'views/expediente_views.xml',
        'views/expediente_rechazo_wizard.xml',
        'views/res_partner_views.xml',
        'views/expediente_references_inherit.xml'
    ],
    'application': True,
}
