# -*- coding: utf-8 -*-
{
    'name': 'ADT API Gerencia',
    'version': '15.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'API para la app móvil de gerencia: cartera, cobranza, vehículos, candidatos a préstamo y traspasos',
    'description': """
API Gerencia
============
API REST de solo lectura para la app móvil de la gerencia. Solo los usuarios del
grupo "Acceso a la app de gerencia" pueden iniciar sesión y leer los datos.

Los indicadores se calculan con la misma lógica de los reportes de Odoo
(Cartera y financieras, Reporte de Cobranzas y Dashboard de Clientes), así que
los números coinciden con lo que ve el equipo.

Ver API.md para el detalle de los endpoints.
    """,
    'author': 'CM Innovación',
    'depends': ['base', 'fleet', 'adt_comercial'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/gerencia_token_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
