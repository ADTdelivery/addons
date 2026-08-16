# -*- coding: utf-8 -*-
{
    'name': 'ADT Traccar Device (Credenciales por vehículo)',
    'version': '15.0.1.0.0',
    'category': 'Operations/Fleet',
    'summary': 'Registra vehículos en Traccar (placa + IMEI) y crea credenciales individuales para la app',
    'description': '''
        ADT Traccar Device
        ===================

        Desde Odoo Flota permite:
          - Registrar/sincronizar un vehículo en Traccar identificándolo por
            placa (nombre del device) e IMEI (uniqueId), individualmente
            desde la ficha del vehículo o en lote desde la lista de Flota.
          - Solo se puede registrar un vehículo con una cuenta comercial
            activa en adt_comercial (state en_curso/aprobado).
          - Crea en Traccar un usuario Traccar individual **por vehículo**
            (no por cliente), reutilizando el email del contacto ya
            vinculado por Flota. Si un mismo cliente tiene más de un
            vehículo, el 2do/3er/... vehículo usa un email técnico derivado
            (juanv2@dominio, juanv3@dominio, ...) para que cada login
            Traccar quede acotado a un solo dispositivo.
          - La contraseña generada se guarda en texto plano en Odoo (campo
            restringido por grupo de seguridad) — decisión explícita para
            no depender de una clave de cifrado externa.
          - Expone un servicio REST (GET /v1/app/traccar-credentials,
            por Bearer token de mobile.token o directo por placa) que
            devuelve esas credenciales para que la app se conecte
            directamente al websocket de Traccar y reciba solo la
            ubicación de su propio dispositivo.
          - Botón "Actualizar" en la ficha del vehículo (y acción masiva
            desde la lista) para ver el estado GPS en vivo: en línea/
            desconectado, último reporte, velocidad, batería (si el
            dispositivo la reporta), latitud/longitud y link a Google Maps.
          - Mapa embebido en la misma ficha (pestaña "Traccar / GPS") que se
            actualiza solo cada 8 segundos mientras la ficha está abierta
            (polling contra el propio Odoo, que a su vez consulta a Traccar
            — no es un websocket directo navegador↔Traccar, ver plan).

        Ver plan-adt-traccar-device.md (raíz de addons/) para el detalle de
        diseño y las decisiones de arquitectura.
    ''',
    'author': 'ADT',
    # Autocontenido a propósito: NO depende de 'fleet_addons' (módulo en
    # desuso, con una vista rota — view_gps.xml — que rompe la instalación
    # de cualquiera que lo arrastre como dependencia). El campo x_imei que
    # antes vivía ahí ahora se define directamente en este módulo
    # (models/fleet_vehicle.py) — sin dependencias externas para eso.
    'depends': ['base', 'fleet', 'adt_traccar', 'adt_comercial', 'mail'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'wizard/traccar_register_device_wizard_views.xml',
        'views/traccar_device_credential_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adt_traccar_device/static/src/js/password_toggle_field.js',
            'adt_traccar_device/static/src/scss/password_toggle_field.scss',
            'adt_traccar_device/static/src/js/live_map_field.js',
            'adt_traccar_device/static/src/scss/live_map_field.scss',
            # OJO: Leaflet (leaflet.js/leaflet.css) NO va acá — se carga
            # perezosamente desde CDN solo cuando se abre la pestaña
            # "Traccar / GPS" de un vehículo (ver live_map_field.js,
            # ensureLeafletLoaded()), para no pesar en el resto del backend.
        ],
    },
    'installable': True,
    # True (no False) a propósito: con application=False Odoo intenta
    # renderizar 'description' como reStructuredText al instalar/actualizar
    # el módulo (ir_module.py::_get_desc), y el formato de texto libre de
    # arriba no es RST válido → rompía la instalación con
    # "docutils.utils.SystemMessage: Unexpected section title". Con
    # application=True ese renderizado se salta por completo. Mismo valor
    # que usan adt_traccar y adt_mantenimiento_preventivo.
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
