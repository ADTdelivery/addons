{
    'name': 'ADT Simulador de Financiamiento',
    'version': '15.0.1.0.0',
    'category': 'Sales',
    'summary': 'Simulador de cuotas (mensual, semanal y diaria) por vehículo financiable',
    'description': """
Simulador de cuotas TVS
=======================
* Productos financiables con importe a financiar y TEA configurables.
* Cálculo de C/Mensual, C/Semanal y C/Diaria (sistema francés).
* Asistente "Simular cuota" y registro de simulaciones.
* API JSON para la app.
    """,
    'author': 'CM Innovación',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/financing_vehicle_data.xml',
        'views/financing_vehicle_views.xml',
        'views/financing_simulation_views.xml',
        'wizard/financing_simulation_wizard_views.xml',
        'report/financing_simulation_report.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
