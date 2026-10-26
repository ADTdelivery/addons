# -*- coding: utf-8 -*-
{
    'name': 'ADT Ajustes de cronograma',
    'version': '15.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Acuerdos de cobranza: reprogramar cuotas, trasladar saldos, acordar mora, agregar cuotas y editar el cronograma',
    'description': """
Ajustes de cronograma
=====================
Los acuerdos que la cobranza hace con el cliente, como operaciones registradas y reversibles:

* Reprogramar una cuota (al final, después de otra cuota o en una fecha).
* Trasladar el saldo de una cuota a otra (la cuota queda pagada con lo abonado).
* Acordar o perdonar la mora, o cobrarla como cargo aparte.
* Agregar una cuota en cualquier punto, corriendo o no las siguientes.
* Editar o refinanciar el cronograma con montos libres, validando que el total cuadre.

Cada ajuste guarda quién lo hizo, el motivo y la foto de las cuotas antes del cambio;
el último ajuste de una cuenta se puede deshacer. Se usa desde Flota 360.
    """,
    'author': 'CM Innovación',
    'depends': ['adt_comercial', 'adt_flota_360'],
    'data': [
        'security/ir.model.access.csv',
        'views/ajuste_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_cobranza_ajustes/static/src/js/ajustes.js',
            'adt_cobranza_ajustes/static/src/scss/ajustes.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
