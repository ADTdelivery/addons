# -*- coding: utf-8 -*-
{
    'name': 'ADT Capturas SAT',
    'summary': 'Alertas de órdenes de captura de vehículos del SAT Lima.',
    'description': """
        Integra el agente de capturas SAT (contenedor Docker independiente) con Odoo:

        * Programas de consulta (toda la flota, por financiera, por razón social, filtro, lista o las placas de un programa
          de papeletas) con ejecución automática o manual.
        * El agente toma las ejecuciones por /api/capturas/sat/ejecuciones/tomar, consulta
          cada placa y envía el resultado a /api/capturas/sat/import.
        * Cada orden de captura queda registrada por documento; cuando deja de figurar
          en el SAT se marca como levantada.
        * Alertas: estado del vehículo en Flota, aviso en su ficha, mensaje y actividad
          para el grupo «Recibir alertas de capturas SAT» y los responsables del programa.
    """,
    'author': 'ADT',
    'category': 'Fleet Management',
    'version': '15.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'fleet', 'adt_papeletas', 'adt_comercial', 'adt_fleet'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/captura_sat_data.xml',
        'views/captura_sat_views.xml',
        'views/captura_sat_programa_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
