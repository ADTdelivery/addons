# -*- coding: utf-8 -*-
{
    'name': 'ADT Flota 360',
    'version': '15.0.1.4.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Vista unificada del vehículo: buscador por placa, cliente o documento y estado de todos los módulos',
    'description': """
Flota 360
=========
Una sola pantalla para encontrar un vehículo (placa, chasis, motor, nombre,
DNI/RUC o teléfono del cliente) y ver de un vistazo su estado en cada módulo:

* Cuentas y cuotas (adt_comercial)
* Papeletas (adt_papeletas)
* GPS / Traccar (adt_traccar_device, adt_mantenimiento_preventivo)
* Trámite de placa y tracking de entrega (adt_tramite_placa, adt_tracking_moto)
* Capturas (adt_captura)
* Taller (maintenance_workshop)
* Expediente del cliente y sus documentos (adt_expedientes)

Cada módulo es opcional: si no está instalado, su sección no se muestra.
La ficha del vehículo se abre a pantalla completa con un menú por áreas
(cliente, crédito y cobranza, vehículo) y el recorrido del vehículo desde el
expediente hasta la cobranza. Las operaciones frecuentes son nativas de la
vista: registrar papeletas, capturas y órdenes de taller, editar vehículo y
cliente, crear expedientes, subir y revisar documentos, y crear la cuenta con
su cronograma. Los pagos de cuota, mora y varias cuotas usan popups JavaScript nativos,
con las validaciones y el registro contable de ADT Comercial.
    """,
    'author': 'CM Innovación',
    'depends': ['base', 'web', 'fleet', 'adt_comercial'],
    'data': [
        'security/cartera_security.xml',
        'security/ir.model.access.csv',
        'views/flota_360_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_flota_360/static/src/scss/flota_360.scss',
            'adt_flota_360/static/src/js/flota_360.js',
            'adt_flota_360/static/src/js/pagos.js',
            'adt_flota_360/static/src/scss/pagos.scss',
            'adt_flota_360/static/src/js/carteras.js',
            'adt_flota_360/static/src/scss/carteras.scss',
            'adt_flota_360/static/src/js/cobranza_rentabilidad.js',
            'adt_flota_360/static/src/scss/cobranza_rentabilidad.scss',
            'adt_flota_360/static/src/js/flota_360_indicadores.js',
            'adt_flota_360/static/src/scss/flota_360_indicadores.scss',
        ],
        'web.assets_qweb': [
            'adt_flota_360/static/src/xml/flota_360.xml',
            'adt_flota_360/static/src/xml/cobranza_rentabilidad.xml',
            'adt_flota_360/static/src/xml/flota_360_indicadores.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
