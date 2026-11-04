# -*- coding: utf-8 -*-
{
    'name': 'ADT Flota 360',
    'version': '15.0.1.10.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Vista unificada del vehículo: buscador por placa, cliente o documento y estado de todos los módulos',
    'description': """
Flota 360
=========
Una sola pantalla para encontrar un vehículo (placa, chasis, motor, nombre,
DNI/RUC o teléfono del cliente) y ver de un vistazo su estado en cada módulo:

* Cuentas y cuotas (adt_comercial)
* Papeletas del SAT Lima: estado de pago y días (adt_papeletas)
* GPS / Traccar (adt_traccar_device, adt_mantenimiento_preventivo)
* Trámite de placa y tracking de entrega (adt_tramite_placa, adt_tracking_moto)
* Capturas (adt_captura), con una vista paso a paso: posibles capturas (cuotas
  vencidas o papeletas SAT pendientes), captura, cobro de la intervención,
  liberación o disolución y recolocación
* Tracking de motos (adt_tracking_moto) en una sola vista: indicadores por etapa
  (Gambeta, Base, Fibra por taller, Base con fibra), tablero donde cada tarjeta
  avanza la logística e inicia el trámite de placa, detalle con los dos flujos
  y configuración (etapas, talleres de fibra, parámetros de placa) en un drawer
* Taller (maintenance_workshop)
* Monitoreo GPS: todos los dispositivos de Traccar (con o sin vehículo en Odoo,
  relacionados por placa aunque el nombre traiga texto extra), cuáles reportan y
  cuáles no y por qué, con alertas en tiempo real (webhook de Traccar + bus de
  Odoo) cuando un vehículo deja de reportar, se desconecta, lanza una alarma o
  entra/sale de una geocerca; ubicación en vivo, recorrido por fechas y geocercas
  programables publicadas en Traccar
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
    'depends': ['base', 'web', 'bus', 'fleet', 'adt_comercial'],
    'data': [
        'security/cartera_security.xml',
        'security/ir.model.access.csv',
        'views/flota_360_views.xml',
        'views/flota_360_gps_views.xml',
        'data/flota_360_gps_cron.xml',
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
            'adt_flota_360/static/src/js/flota_360_capturas.js',
            'adt_flota_360/static/src/scss/flota_360_capturas.scss',
            'adt_flota_360/static/src/js/flota_360_tracking.js',
            'adt_flota_360/static/src/scss/flota_360_tracking.scss',
            'adt_flota_360/static/src/js/flota_360_carga_pdf.js',
            'adt_flota_360/static/src/scss/flota_360_carga_pdf.scss',
            'adt_flota_360/static/src/js/flota_360_gps_mapa.js',
            'adt_flota_360/static/src/js/flota_360_gps.js',
            'adt_flota_360/static/src/js/flota_360_gps_alertas.js',
            'adt_flota_360/static/src/scss/flota_360_gps.scss',
        ],
        'web.assets_qweb': [
            'adt_flota_360/static/src/xml/flota_360.xml',
            'adt_flota_360/static/src/xml/cobranza_rentabilidad.xml',
            'adt_flota_360/static/src/xml/flota_360_indicadores.xml',
            'adt_flota_360/static/src/xml/flota_360_capturas.xml',
            'adt_flota_360/static/src/xml/flota_360_carga_pdf.xml',
            'adt_flota_360/static/src/xml/flota_360_gps.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
