{
    'name': 'ADT Plan de Pagos PDF',
    'version': '15.0.1.0.0',
    'summary': 'Convierte el PDF "Plan de Pagos" a texto y JSON con validación matemática',
    'description': """
        Lee el PDF de Plan de Pagos (formato fijo), lo convierte a texto
        respetando el layout y lo estructura en JSON clave/valor.

        Cada lectura se valida con identidades financieras (sumas por fila y
        columna, interés por TEA, desgravamen sobre saldo, plazo en días) y con
        un segundo motor de extracción (PyPDF2) para asegurar la precisión.
    """,
    'category': 'Accounting',
    'author': 'ADT',
    'depends': ['base'],
    'external_dependencies': {'python': ['pdfminer']},
    'data': [
        'security/ir.model.access.csv',
        'views/plan_pagos_pdf_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
