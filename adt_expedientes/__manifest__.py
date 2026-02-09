{
    'name': 'ADT Expedientes',
    'version': '15.0.4.0.0',
    'category': 'Operations/Security',
    'summary': 'Gestión de expedientes con sistema de seguridad móvil y notificaciones push',
    'description': '''
        ADT Expedientes - Sistema de Seguridad Móvil + Push Notifications
        ==================================================================

        Características de Seguridad:
        - Token-based authentication con SHA256 hashing
        - Device binding (un token por dispositivo)
        - Validación automática en cada request
        - Revocación automática al desactivar usuarios
        - Auditoría completa de accesos (logs)
        - Rate limiting anti-abuse
        - Detección de actividad sospechosa

        Notificaciones Push:
        - Notificaciones automáticas en cambios de estado de expedientes
        - Soporte multi-dispositivo por usuario
        - Gestión de tokens FCM
        - Compatible con Android, iOS y Web

        API RESTful + Sentinel Integration:
        - Endpoints para gestión de tokens FCM
        - Integración con módulo adt_sentinel
        - API móvil segura para consultas Sentinel
    ''',
    'author': 'ADT',
    'website': 'https://www.adt.com',
    'depends': ['base', 'mail', 'adt_sentinel'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/notification_config.xml',
        'views/expediente_views.xml',
        'views/expediente_rechazo_wizard.xml',
        'views/res_partner_views.xml',
        'views/expediente_references_inherit.xml',
        'views/fcm_device_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
