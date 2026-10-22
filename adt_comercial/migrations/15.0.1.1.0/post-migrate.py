"""El plan de pagos de la financiera pasa de la cuenta al vehículo.

Antes el PDF y su cronograma se guardaban en cada cuenta (adt.comercial.cuentas). Ahora son del
vehículo (fleet.vehicle) y las cuentas los muestran desde él. Esta migración, sin borrar datos:

1. Por cada vehículo elige la cuenta cuyo plan se conserva: la que tiene el PDF, el cronograma
   leído con más cuotas y, a igualdad, la más reciente.
2. Copia sus campos cf_* al vehículo (las columnas viejas de la cuenta quedan en la base).
3. Mueve el PDF (adjunto) y las filas del cronograma de esa cuenta al vehículo. Los planes de
   las otras cuentas del mismo vehículo quedan como estaban (adjuntos y filas sin vehículo).
4. Deja los datos de la financiera (fin_*) en una sola cuenta del vehículo, para que el
   dashboard y los reportes no cuenten dos veces la misma deuda con la financiera.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Columnas que se copian de la cuenta al vehículo (mismo nombre en ambas tablas).
CAMPOS = [
    'cf_pdf_nombre', 'cf_nro_solicitud', 'cf_nro_expediente', 'cf_agencia', 'cf_socio',
    'cf_codigo_socio', 'cf_dni', 'cf_monto_credito', 'cf_fecha_desembolso', 'cf_plazo_dias',
    'cf_frecuencia_cuota', 'cf_tasa_interes_anual', 'cf_producto', 'cf_tipo_credito', 'cf_tipo_cobro',
    'cf_analista', 'cf_oficina', 'cf_usuario_emisor', 'cf_fecha_sistema', 'cf_fecha_emision',
    'cf_cuotas_pendientes', 'cf_primera_cuota', 'cf_ultima_cuota', 'cf_capital_pendiente',
    'cf_capital_amortizado', 'cf_monto_cuota', 'cf_total_pdf', 'cf_tasa_desgravamen',
    'cf_proximo_vencimiento', 'cf_estado', 'cf_confianza', 'cf_validacion_html', 'cf_json',
]


def _columnas(cr, tabla):
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (tabla,))
    return {r[0] for r in cr.fetchall()}


def migrate(cr, version):
    if not version:
        return
    en_cuenta = _columnas(cr, 'adt_comercial_cuentas')
    en_vehiculo = _columnas(cr, 'fleet_vehicle')
    if 'cf_estado' not in en_cuenta:
        _logger.info("Plan de la financiera: no hay columnas cf_* en las cuentas, nada que migrar.")
        return
    campos = [c for c in CAMPOS if c in en_cuenta and c in en_vehiculo]

    # Cuentas con plan: PDF adjunto o cronograma leído.
    cr.execute("""
        SELECT c.id, c.vehiculo_id,
               (SELECT a.id FROM ir_attachment a
                 WHERE a.res_model = 'adt.comercial.cuentas' AND a.res_field = 'cf_pdf' AND a.res_id = c.id
                 ORDER BY a.id DESC LIMIT 1) AS adjunto,
               (SELECT count(*) FROM adt_comercial_cuentas_cronograma_fin f WHERE f.cuenta_id = c.id) AS filas
          FROM adt_comercial_cuentas c
         WHERE c.vehiculo_id IS NOT NULL
           AND (c.cf_estado IS NOT NULL
                OR EXISTS (SELECT 1 FROM adt_comercial_cuentas_cronograma_fin f WHERE f.cuenta_id = c.id)
                OR EXISTS (SELECT 1 FROM ir_attachment a WHERE a.res_model = 'adt.comercial.cuentas'
                           AND a.res_field = 'cf_pdf' AND a.res_id = c.id))
    """)
    por_vehiculo = {}
    for cuenta_id, vehiculo_id, adjunto, filas in cr.fetchall():
        por_vehiculo.setdefault(vehiculo_id, []).append((bool(adjunto), filas, cuenta_id, adjunto))

    migrados = []
    for vehiculo_id, candidatas in por_vehiculo.items():
        # Un vehículo que ya tiene su plan (p. ej. migración repetida) no se toca.
        cr.execute("SELECT 1 FROM adt_comercial_cuentas_cronograma_fin WHERE vehicle_id = %s LIMIT 1", (vehiculo_id,))
        if cr.fetchone():
            continue
        con_pdf, filas, cuenta_id, adjunto = max(candidatas)
        if len(candidatas) > 1:
            _logger.info("Plan de la financiera: el vehículo %s tenía plan en las cuentas %s; se conserva el de la cuenta %s.",
                         vehiculo_id, sorted(c[2] for c in candidatas), cuenta_id)
        if campos:
            cr.execute("UPDATE fleet_vehicle v SET %s FROM adt_comercial_cuentas c WHERE c.id = %%s AND v.id = %%s"
                       % ', '.join('%s = c.%s' % (f, f) for f in campos), (cuenta_id, vehiculo_id))
        if adjunto:
            cr.execute("""UPDATE ir_attachment SET res_model = 'fleet.vehicle', res_id = %s
                           WHERE id = %s""", (vehiculo_id, adjunto))
        # cuenta_id se vacía: si la cuenta se borra, el plan del vehículo no debe borrarse con ella.
        cr.execute("""UPDATE adt_comercial_cuentas_cronograma_fin SET vehicle_id = %s, cuenta_id = NULL
                       WHERE cuenta_id = %s""", (vehiculo_id, cuenta_id))
        # Las cuentas del vehículo cuyos fin_* vinieron de un PDF quedan marcadas: la sincronización
        # deja esos datos solo en la cuenta que corresponde.
        cr.execute("""UPDATE adt_comercial_cuentas SET fin_desde_vehiculo = TRUE
                       WHERE vehiculo_id = %s AND cf_estado IS NOT NULL""", (vehiculo_id,))
        migrados.append(vehiculo_id)

    if migrados:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env['fleet.vehicle'].browse(migrados)._cf_sincronizar_cuenta()
    _logger.info("Plan de la financiera: %s vehículos migrados.", len(migrados))
