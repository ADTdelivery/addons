# -*- coding: utf-8 -*-
import math

# Mismo criterio que adt_dashboard_flota para no depender de ese módulo.
PLATE_PLACEHOLDERS = {
    'S/P', 'SP', 'S/N', 'SN', 'SIN PLACA', 'EN TRAMITE', 'EN TRÁMITE',
    'TRAMITE', 'TRÁMITE', 'PENDIENTE', 'NULL', 'NONE', 'N/A', 'NA', '-', '--',
}


def plate_is_ready(plate):
    """Una placa está lista si tiene un valor real (no placeholder) con al menos un dígito."""
    value = (plate or '').strip().upper()
    if not value or value in PLATE_PLACEHOLDERS:
        return False
    return any(ch.isdigit() for ch in value)


def percentil(valores, p):
    """Percentil por rango más cercano (sin interpolar)."""
    if not valores:
        return None
    orden = sorted(valores)
    return orden[max(0, math.ceil(p / 100 * len(orden)) - 1)]


# Umbral de demora cuando la etapa no tiene SLA: P85 de los casos cerrados recientes.
VENTANA_HISTORIA_DIAS = 90
MIN_MUESTRAS_HISTORIA = 5

CODIGOS_ETAPA = [
    ('recojo', 'Recojo en distribuidor'),
    ('almacen', 'Almacén de la empresa'),
    ('fibra', 'En fibra'),
    ('listo', 'Listo para asignar'),
]
ORDEN_ETAPA = {'recojo': 1, 'almacen': 2, 'fibra': 3, 'listo': 4}
FECHA_POR_ETAPA = {
    'recojo': 'fecha_recojo',
    'almacen': 'fecha_ingreso_almacen',
    'fibra': 'fecha_envio_fibra',
    'listo': 'fecha_listo',
}

# Mismos estados que adt.tramite.placa.
ESTADOS_PLACA = [
    ('pendiente', 'Pendiente'),
    ('en_tramite', 'En trámite'),
    ('observado', 'Observado'),
    ('finalizado', 'Finalizado'),
]

ESTADOS_GLOBAL = [
    ('en_proceso', 'En proceso'),
    ('listo_asignar', 'Listo para asignar'),
    ('asignado_sin_placa', 'Asignado sin placa'),
    ('asignado_con_placa', 'Asignado con placa'),
    ('entregado', 'Entregado'),
]
