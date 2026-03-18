# -*- coding: utf-8 -*-
{
    'name': "ADT Facturación V1",
    'summary': "Campos adicionales en facturas para vehículos/motos",
    'description': """
        Módulo que agrega campos adicionales al modelo account.move (facturas):
        - Chasis
        - Modelo (fleet.vehicle.model)
        - Motor
        - Año del modelo
        - Color
        - DUA
        - Adjuntar factura (PDF)
    """,
    'author': "ADT",
    'website': "https://www.adt.com",
    'category': 'Accounting',
    'version': '15.0.1.0.0',
    'depends': ['base', 'account', 'fleet'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
