{
    'name': 'ADT Expedientes',
    'version': '15.0.3.0.0',
    'category': 'Operations/Security',
    'summary': 'Gestión de expedientes con sistema de seguridad móvil de nivel producción',
    'description': '''
        ADT Expedientes - Sistema de Seguridad Móvil
        =============================================

        Características de Seguridad:
        - Token-based authentication con SHA256 hashing
        - Device binding (un token por dispositivo)
        - Validación automática en cada request
        - Revocación automática al desactivar usuarios
        - Auditoría completa de accesos (logs)
        - Rate limiting anti-abuse
        - Detección de actividad sospechosa

        API RESTful para aplicaciones móviles con máxima seguridad.
    ''',
    'author': 'ADT',
    'website': 'https://www.adt.com',
    'depends': ['base', 'mail', 'adt_sentinel'],
    'data': [
        'security/ir.model.access.csv',
        'views/expediente_views.xml',
        'views/expediente_rechazo_wizard.xml',
        'views/res_partner_views.xml',
        'views/expediente_references_inherit.xml',
        'views/report_expediente.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
