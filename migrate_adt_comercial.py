"""
=============================================================================
SCRIPT DE MIGRACIÓN: adt.comercial.cuentas + adt.comercial.cuotas
=============================================================================
Migra datos del módulo ADT Comercial entre dos instancias de Odoo 15 via XMLRPC.

Flujo:
  1. Leer placas de fleet.vehicle del NUEVO Odoo (8074/odoo1)
  2. Buscar cada placa en el ANTIGUO Odoo (8070/odoo2)
  3. Si existe → buscar adt.comercial.cuentas vinculadas al vehículo
  4. Si tiene cuentas → crear la cuenta en el nuevo Odoo con nuevo reference_no
  5. Copiar las cuotas (adt.comercial.cuotas) tal cual, sin regenerar cronograma
  6. Copiar pagos (account.payment) de las cuotas pagadas/a_cuenta

Ejecución:
  Modo dry-run (solo loguea, no crea nada):
      python migrate_adt_comercial.py --dry-run

  Ejecución real:
      python migrate_adt_comercial.py

Requisitos:
  pip install xmlrpc (incluido en Python stdlib)
=============================================================================
"""

import xmlrpc.client
import argparse
import logging
import sys
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE CONEXIÓN
# ─────────────────────────────────────────────

NUEVO_ODOO = {
    "url":      "http://52.15.86.160:8074",
    "db":       "odoov15",
    "username": "odoov15@gmail.com",
    "password": "odoov15@gmail.com",
}

ANTIGUO_ODOO = {
    "url":       "http://52.15.86.160:8070",
    "db":       "odoo",
    "username": "rapitash@gmail.com",
    "password": "Sofka2024",
}

# Nombre del journal a usar para los account.payment migrados.
# El script buscará uno de tipo 'bank' o 'cash'. Si quieres forzar un nombre
# específico, escríbelo aquí. Si lo dejas en None, tomará el primero disponible.
JOURNAL_NAME_NUEVO = None  # Ejemplo: "Banco BCP"  o None para automático

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONEXIÓN XMLRPC
# ─────────────────────────────────────────────

def conectar(cfg: dict) -> tuple:
    """Retorna (uid, models_proxy) para un Odoo dado."""
    common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common")
    uid = common.authenticate(cfg["db"], cfg["username"], cfg["password"], {})
    if not uid:
        raise ConnectionError(
            f"No se pudo autenticar en {cfg['url']} con usuario {cfg['username']}"
        )
    models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object")
    log.info("Conectado a %s  (uid=%s)", cfg["url"], uid)
    return uid, models


def call(models, cfg: dict, uid: int, model: str, method: str, *args, **kwargs):
    """Wrapper genérico para llamadas XMLRPC."""
    return models.execute_kw(cfg["db"], uid, cfg["password"], model, method, list(args), kwargs)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def fmt_date(val) -> Optional[str]:
    """Normaliza un valor de fecha a string 'YYYY-MM-DD' o None."""
    if not val or val is False:
        return None
    if isinstance(val, str):
        return val[:10]  # recorta datetime si viene con hora
    return str(val)


def safe_str(val) -> Optional[str]:
    return val if isinstance(val, str) else None


def safe_float(val) -> float:
    return float(val) if val else 0.0


def safe_int(val) -> int:
    return int(val) if val else 0


def m2o_id(val) -> Optional[int]:
    """Extrae el id de un campo Many2one que puede venir como [id, name] o False."""
    if not val or val is False:
        return None
    if isinstance(val, (list, tuple)):
        return val[0]
    return int(val)


# ─────────────────────────────────────────────
# RESOLUCIÓN DEL JOURNAL EN NUEVO ODOO
# ─────────────────────────────────────────────

def resolver_journal(models_n, uid_n: int) -> int:
    """
    Busca el journal a usar para los pagos en el nuevo Odoo.
    Prioridad:
      1. El que coincida con JOURNAL_NAME_NUEVO (si está definido)
      2. El primero de tipo 'bank'
      3. El primero de tipo 'cash'
    """
    domain = [("type", "in", ["bank", "cash"])]
    if JOURNAL_NAME_NUEVO:
        domain.append(("name", "=", JOURNAL_NAME_NUEVO))

    journals = call(models_n, NUEVO_ODOO, uid_n, "account.journal", "search_read",
                    domain, fields=["id", "name", "type"], limit=5)

    if not journals:
        raise RuntimeError(
            "No se encontró ningún journal de tipo 'bank' o 'cash' en el nuevo Odoo. "
            "Crea uno o configura JOURNAL_NAME_NUEVO."
        )

    if JOURNAL_NAME_NUEVO and journals:
        j = journals[0]
    else:
        # Preferir bank sobre cash
        bank = [j for j in journals if j["type"] == "bank"]
        j = bank[0] if bank else journals[0]

    log.info("Journal seleccionado para pagos: [%s] %s (%s)", j["id"], j["name"], j["type"])
    return j["id"]


# ─────────────────────────────────────────────
# PASO 1: LEER PLACAS DEL NUEVO ODOO
# ─────────────────────────────────────────────

def obtener_vehiculos_nuevo(models_n, uid_n: int) -> list[dict]:
    vehiculos = call(
        models_n, NUEVO_ODOO, uid_n,
        "fleet.vehicle", "search_read",
        [("license_plate", "!=", False)],
        fields=["id", "license_plate", "name", "driver_id"],
    )
    log.info("Vehículos encontrados en nuevo Odoo: %d", len(vehiculos))
    return vehiculos


# ─────────────────────────────────────────────
# PASO 2: BUSCAR PLACA EN ANTIGUO ODOO
# ─────────────────────────────────────────────

def buscar_vehiculo_antiguo(models_a, uid_a: int, placa: str) -> Optional[dict]:
    resultados = call(
        models_a, ANTIGUO_ODOO, uid_a,
        "fleet.vehicle", "search_read",
        [("license_plate", "=", placa)],
        fields=["id", "license_plate", "name"],
        limit=1,
    )
    return resultados[0] if resultados else None


# ─────────────────────────────────────────────
# INTROSPECCIÓN DE CAMPOS (compatibilidad entre versiones)
# ─────────────────────────────────────────────

_fields_cache = {}  # model -> set(field_names)


def campos_existentes(models, cfg: dict, uid: int, model: str) -> set:
    """Retorna el conjunto de campos disponibles en un modelo del Odoo dado."""
    cache_key = f"{cfg['url']}:{model}"
    if cache_key not in _fields_cache:
        raw = call(models, cfg, uid, model, "fields_get", [], attributes=["string"])
        _fields_cache[cache_key] = set(raw.keys())
        log.debug("Campos disponibles en %s.%s: %d", cfg["url"], model, len(_fields_cache[cache_key]))
    return _fields_cache[cache_key]


def filtrar_campos(models, cfg: dict, uid: int, model: str, deseados: list) -> list:
    """Filtra la lista de campos deseados a solo los que existen en el modelo."""
    existentes = campos_existentes(models, cfg, uid, model)
    disponibles = [f for f in deseados if f in existentes]
    faltantes = [f for f in deseados if f not in existentes]
    if faltantes:
        log.warning("Campos no encontrados en %s (%s): %s", model, cfg["url"], faltantes)
    return disponibles


# ─────────────────────────────────────────────
# PASO 3: BUSCAR CUENTAS EN ANTIGUO ODOO
# ─────────────────────────────────────────────

# Campos deseados — se filtrará automáticamente contra los que existan en el antiguo Odoo
CUENTAS_FIELDS_DESEADOS = [
    "id", "reference_no", "state", "state_view",
    "partner_id", "user_id",
    "fecha_desembolso", "fecha_entrega", "fecha_cierre",
    "periodicidad",
    "monto_total", "monto_inicial", "monto_fraccionado",
    "cuota_gracia", "fecha_gracia",
    "qty_cuotas", "monto_cuota",
    "vehiculo_id",
    "moto_tarjeta", "gps_chip", "gps_activo", "soat_activo",
    "recuperado", "message",
    "asesor", "tipo_financiera",
    "cuota_inicio_1", "cuota_fin_1", "monto_1",
    "cuota_inicio_2", "cuota_fin_2", "monto_2",
    "is_available_pay_mora", "captura_prioridad",
    "cuota_ids",
]

CUOTAS_FIELDS_DESEADOS = [
    "id", "name", "monto", "saldo",
    "fecha_cronograma", "fecha_compromiso",
    "state", "type", "periodicidad",
    "real_date", "numero_operacion", "x_asesora",
    "mora_total", "mora_pendiente", "mora_estado_texto",
    "mora_operacion", "mora_dias",
    "payment_ids",
    "parent_id",
    "es_subcuota",
]

PAYMENT_FIELDS_DESEADOS = [
    "id", "amount", "date", "ref",
    "payment_type", "journal_id",
    "partner_id", "state",
    "mora", "mora_state", "mora_operacion", "mora_dias", "mora_payment_date",
]


def buscar_cuentas_antiguo(models_a, uid_a: int, vehicle_id: int) -> list[dict]:
    campos = filtrar_campos(models_a, ANTIGUO_ODOO, uid_a,
                            "adt.comercial.cuentas", CUENTAS_FIELDS_DESEADOS)
    return call(
        models_a, ANTIGUO_ODOO, uid_a,
        "adt.comercial.cuentas", "search_read",
        [("vehiculo_id", "=", vehicle_id)],
        fields=campos,
    )


# ─────────────────────────────────────────────
# PASO 4: BUSCAR CUOTAS EN ANTIGUO ODOO
# ─────────────────────────────────────────────

def buscar_cuotas_antiguo(models_a, uid_a: int, cuenta_id: int) -> list[dict]:
    campos = filtrar_campos(models_a, ANTIGUO_ODOO, uid_a,
                            "adt.comercial.cuotas", CUOTAS_FIELDS_DESEADOS)
    return call(
        models_a, ANTIGUO_ODOO, uid_a,
        "adt.comercial.cuotas", "search_read",
        [("cuenta_id", "=", cuenta_id)],
        fields=campos,
        order="id asc",
    )


# ─────────────────────────────────────────────
# PASO 5: BUSCAR PAGOS EN ANTIGUO ODOO
# ─────────────────────────────────────────────

def buscar_pagos_cuota(models_a, uid_a: int, cuota_id: int) -> list[dict]:
    campos = filtrar_campos(models_a, ANTIGUO_ODOO, uid_a,
                            "account.payment", PAYMENT_FIELDS_DESEADOS)
    return call(
        models_a, ANTIGUO_ODOO, uid_a,
        "account.payment", "search_read",
        [("cuota_id", "=", cuota_id)],
        fields=campos,
        order="id asc",
    )


# ─────────────────────────────────────────────
# PASO 6: CREAR CUENTA EN NUEVO ODOO
# ─────────────────────────────────────────────

def buscar_partner_nuevo(models_n, uid_n: int, partner_id_antiguo: int) -> Optional[int]:
    """
    Intenta localizar el mismo partner en el nuevo Odoo por su ID.
    Si los IDs no coinciden entre instancias, ajusta esta función para
    buscar por email, vat, o nombre.
    """
    res = call(
        models_n, NUEVO_ODOO, uid_n,
        "res.partner", "search_read",
        [("id", "=", partner_id_antiguo)],
        fields=["id", "name"],
        limit=1,
    )
    return res[0]["id"] if res else None


def buscar_user_nuevo(models_n, uid_n: int, user_id_antiguo: int) -> Optional[int]:
    """Localiza el usuario en nuevo Odoo por ID."""
    res = call(
        models_n, NUEVO_ODOO, uid_n,
        "res.users", "search_read",
        [("id", "=", user_id_antiguo)],
        fields=["id", "name"],
        limit=1,
    )
    return res[0]["id"] if res else None


def crear_cuenta_nuevo(models_n, uid_n: int, cuenta: dict, nuevo_vehicle_id: int,
                       driver_id_nuevo: Optional[int], dry_run: bool) -> Optional[int]:
    """Crea la cuenta en el nuevo Odoo. Retorna el nuevo ID o None en dry-run.

    driver_id_nuevo: ID del driver_id del vehículo en el NUEVO Odoo (res.partner).
                     Se usa como partner_id de la cuenta.
    """

    user_id = m2o_id(cuenta.get("user_id"))
    nuevo_user_id = buscar_user_nuevo(models_n, uid_n, user_id) if user_id else None

    nuevo_partner_id = driver_id_nuevo
    if not nuevo_partner_id:
        log.warning(
            "  ⚠ El vehículo nuevo_id=%s no tiene driver_id asignado. "
            "partner_id de la cuenta quedará en blanco.", nuevo_vehicle_id
        )

    # Generar reference_no ANTES de crear para que name_get() nunca encuentre False.
    # El módulo concatena reference_no + partner.name en name_get(), si es False truena.
    state_antiguo = cuenta.get("state") or "borrador"
    if state_antiguo in ("en_curso", "pagado", "cancelado", "aprobado"):
        nuevo_ref = call(
            models_n, NUEVO_ODOO, uid_n,
            "ir.sequence", "next_by_code", "comercial.cuentas"
        )
    else:
        nuevo_ref = "Nuevo"

    vals = {
        "reference_no":    nuevo_ref,
        "state":           state_antiguo,
        "state_view":      cuenta.get("state_view") or "new",

        "partner_id":      nuevo_partner_id,
        "user_id":         nuevo_user_id,

        "fecha_desembolso": fmt_date(cuenta.get("fecha_desembolso")),
        "fecha_entrega":    fmt_date(cuenta.get("fecha_entrega")),
        "fecha_cierre":     safe_int(cuenta.get("fecha_cierre")),

        "periodicidad":     cuenta.get("periodicidad") or "quincena",

        "monto_total":       safe_float(cuenta.get("monto_total")),
        "monto_inicial":     safe_float(cuenta.get("monto_inicial")),
        "monto_fraccionado": safe_float(cuenta.get("monto_fraccionado")),
        "cuota_gracia":      safe_float(cuenta.get("cuota_gracia")),
        "fecha_gracia":      fmt_date(cuenta.get("fecha_gracia")),

        "qty_cuotas":   safe_int(cuenta.get("qty_cuotas")),
        "monto_cuota":  safe_float(cuenta.get("monto_cuota")),

        "vehiculo_id":  nuevo_vehicle_id,

        "moto_tarjeta": safe_str(cuenta.get("moto_tarjeta")),
        "gps_chip":     safe_str(cuenta.get("gps_chip")),
        "gps_activo":   bool(cuenta.get("gps_activo")),
        "soat_activo":  bool(cuenta.get("soat_activo")),

        "recuperado":   bool(cuenta.get("recuperado")),
        "message":      safe_str(cuenta.get("message")),

        "asesor":          safe_str(cuenta.get("asesor")),
        "tipo_financiera": safe_str(cuenta.get("tipo_financiera")),

        "cuota_inicio_1": safe_int(cuenta.get("cuota_inicio_1")),
        "cuota_fin_1":    safe_int(cuenta.get("cuota_fin_1")),
        "monto_1":        safe_float(cuenta.get("monto_1")),
        "cuota_inicio_2": safe_int(cuenta.get("cuota_inicio_2")),
        "cuota_fin_2":    safe_int(cuenta.get("cuota_fin_2")),
        "monto_2":        safe_float(cuenta.get("monto_2")),

        "is_available_pay_mora": bool(cuenta.get("is_available_pay_mora")),
        "captura_prioridad":     safe_str(cuenta.get("captura_prioridad")),
    }

    # Limpiar Nones y Falses vacíos en campos de fecha
    vals = {k: v for k, v in vals.items() if v is not None}

    if dry_run:
        log.info("  [DRY-RUN] Crearía cuenta (antiguo id=%s) state=%s driver/partner=%s vehicle=%s",
                 cuenta["id"], vals.get("state"), driver_id_nuevo, nuevo_vehicle_id)
        return None

    nuevo_id = call(models_n, NUEVO_ODOO, uid_n, "adt.comercial.cuentas", "create", vals)

    log.info("    reference_no asignado al crear: %s", nuevo_ref)

    # Marcar vehículo como no disponible si la cuenta está activa
    if vals["state"] in ("en_curso", "aprobado"):
        call(models_n, NUEVO_ODOO, uid_n,
             "fleet.vehicle", "write",
             [nuevo_vehicle_id], {"disponible": False})

    log.info("  ✓ Cuenta creada en nuevo Odoo id=%s (antiguo id=%s) ref=%s state=%s",
             nuevo_id, cuenta["id"], vals.get("reference_no", "pendiente"), vals["state"])
    return nuevo_id


# ─────────────────────────────────────────────
# PASO 7: CREAR CUOTAS EN NUEVO ODOO
# ─────────────────────────────────────────────

def crear_cuota_nuevo(models_n, uid_n: int, cuota: dict, nueva_cuenta_id: int,
                      dry_run: bool) -> Optional[int]:
    """Crea una cuota en el nuevo Odoo vinculada a la nueva cuenta."""

    vals = {
        "cuenta_id":         nueva_cuenta_id,
        "name":              safe_str(cuota.get("name")) or "Cuota",
        "monto":             safe_float(cuota.get("monto")),
        "saldo":             safe_float(cuota.get("saldo")),
        "fecha_cronograma":  fmt_date(cuota.get("fecha_cronograma")),
        "fecha_compromiso":  fmt_date(cuota.get("fecha_compromiso")),
        "type":              cuota.get("type") or "cuota",
        "periodicidad":      safe_str(cuota.get("periodicidad")),
        "real_date":         safe_str(cuota.get("real_date")),
        "numero_operacion":  safe_str(cuota.get("numero_operacion")),
        "x_asesora":         safe_str(cuota.get("x_asesora")),
        # mora — campos calculados, pero los guardamos directamente
        "mora_pendiente":     safe_float(cuota.get("mora_pendiente")),
        "mora_estado_texto":  safe_str(cuota.get("mora_estado_texto")),
        "mora_operacion":     safe_str(cuota.get("mora_operacion")),
        "mora_dias":          safe_int(cuota.get("mora_dias")),
    }

    # Limpiar nulos
    vals = {k: v for k, v in vals.items() if v is not None}

    if dry_run:
        log.info("    [DRY-RUN] Crearía cuota '%s' monto=%.2f state=%s pagos=%d",
                 vals.get("name"), vals.get("monto", 0),
                 cuota.get("state"), len(cuota.get("payment_ids") or []))
        return None

    nueva_cuota_id = call(
        models_n, NUEVO_ODOO, uid_n,
        "adt.comercial.cuotas", "create", vals
    )

    # El state se calcula (computed), pero si venía pagado/a_cuenta se reflejará
    # automáticamente cuando se creen los pagos. Sin embargo, para cuotas
    # 'anulada' (canceladas sin pago) lo escribimos directamente.
    estado_antiguo = cuota.get("state")
    if estado_antiguo == "anulada":
        call(models_n, NUEVO_ODOO, uid_n,
             "adt.comercial.cuotas", "write",
             [nueva_cuota_id], {"state": "anulada"})

    log.info("    ✓ Cuota '%s' creada id=%s state_antiguo=%s",
             vals.get("name"), nueva_cuota_id, estado_antiguo)
    return nueva_cuota_id


# ─────────────────────────────────────────────
# PASO 8: CREAR PAGOS EN NUEVO ODOO
# ─────────────────────────────────────────────

def crear_pagos_cuota(models_n, uid_n: int, pagos: list[dict],
                      nueva_cuota_id: int, nuevo_partner_id: Optional[int],
                      journal_id: int, dry_run: bool):
    """Crea los account.payment de una cuota en el nuevo Odoo."""

    for pago in pagos:
        # Solo migrar pagos que estaban posted (confirmados)
        if pago.get("state") not in ("posted", "done", False, None):
            # Pagos draft o cancelados no se migran
            log.info("      Skip pago id=%s state=%s (no confirmado)", pago["id"], pago.get("state"))
            continue

        vals = {
            "payment_type":    pago.get("payment_type") or "inbound",
            "journal_id":      journal_id,
            "cuota_id":        nueva_cuota_id,
            "partner_id":      nuevo_partner_id,
            "ref":             safe_str(pago.get("ref")),
            "amount":          safe_float(pago.get("amount")),
            "date":            fmt_date(pago.get("date")),
            "mora":            safe_float(pago.get("mora")),
            "mora_state":      pago.get("mora_state") or "pending",
            "mora_operacion":  safe_str(pago.get("mora_operacion")),
            "mora_dias":       safe_int(pago.get("mora_dias")),
            "mora_payment_date": fmt_date(pago.get("mora_payment_date")),
        }

        vals = {k: v for k, v in vals.items() if v is not None}

        if dry_run:
            log.info("      [DRY-RUN] Crearía pago amount=%.2f date=%s ref=%s mora=%.2f",
                     vals.get("amount", 0), vals.get("date"), vals.get("ref"), vals.get("mora", 0))
            continue

        try:
            nuevo_pago_id = call(
                models_n, NUEVO_ODOO, uid_n,
                "account.payment", "create", vals
            )
            # Confirmar (post) el pago
            call(models_n, NUEVO_ODOO, uid_n,
                 "account.payment", "action_post", [nuevo_pago_id])
            log.info("      ✓ Pago creado y confirmado id=%s amount=%.2f",
                     nuevo_pago_id, vals.get("amount", 0))
        except Exception as e:
            log.error("      ✗ Error creando pago antiguo id=%s: %s", pago["id"], e)


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def migrar(dry_run: bool = False, limite: int = 0, placas_filtro: list = None):
    mode = "DRY-RUN (sin cambios)" if dry_run else "EJECUCIÓN REAL"
    placas_filtro = [p.strip().upper() for p in (placas_filtro or []) if p.strip()]
    log.info("=" * 60)
    log.info("MIGRACIÓN ADT COMERCIAL — Modo: %s", mode)
    if placas_filtro:
        log.info("Filtro de placas activo: %s", placas_filtro)
    log.info("=" * 60)

    # Conectar a ambos Odoos
    uid_n, models_n = conectar(NUEVO_ODOO)
    uid_a, models_a = conectar(ANTIGUO_ODOO)

    # Resolver journal una sola vez
    journal_id = resolver_journal(models_n, uid_n) if not dry_run else 0

    # Contadores
    stats = {
        "vehiculos_procesados": 0,
        "vehiculos_sin_placa_en_antiguo": 0,
        "vehiculos_sin_cuentas": 0,
        "cuentas_migradas": 0,
        "cuentas_error": 0,
        "cuotas_migradas": 0,
        "pagos_migrados": 0,
    }

    # PASO 1 — Leer placas del NUEVO Odoo
    vehiculos_nuevo = obtener_vehiculos_nuevo(models_n, uid_n)
    total_disponibles = len(vehiculos_nuevo)

    # Filtrar por placas específicas si se indicaron
    if placas_filtro:
        vehiculos_nuevo = [
            v for v in vehiculos_nuevo
            if (v.get("license_plate") or "").strip().upper() in placas_filtro
        ]
        placas_encontradas = {(v.get("license_plate") or "").strip().upper() for v in vehiculos_nuevo}
        placas_no_encontradas = set(placas_filtro) - placas_encontradas
        log.info("Filtro de placas: %d encontradas en nuevo Odoo de %d solicitadas",
                 len(vehiculos_nuevo), len(placas_filtro))
        if placas_no_encontradas:
            log.warning("  Placas NO encontradas en nuevo Odoo: %s", sorted(placas_no_encontradas))
    elif limite > 0:
        vehiculos_nuevo = vehiculos_nuevo[:limite]
        log.info("Límite aplicado: %d de %d vehículos disponibles", limite, total_disponibles)
    else:
        log.info("Sin límite: procesando todos los %d vehículos disponibles", total_disponibles)

    for veh_nuevo in vehiculos_nuevo:
        placa = (veh_nuevo.get("license_plate") or "").strip().upper()
        if not placa:
            continue

        stats["vehiculos_procesados"] += 1
        log.info("─" * 50)
        log.info("Procesando placa: %s (nuevo_id=%s)", placa, veh_nuevo["id"])

        # PASO 2 — Buscar en antiguo Odoo
        veh_antiguo = buscar_vehiculo_antiguo(models_a, uid_a, placa)
        if not veh_antiguo:
            log.info("  Placa %s no encontrada en antiguo Odoo — skip", placa)
            stats["vehiculos_sin_placa_en_antiguo"] += 1
            continue

        log.info("  Placa encontrada en antiguo Odoo id=%s", veh_antiguo["id"])

        # PASO 3 — Buscar cuentas en antiguo Odoo
        cuentas = buscar_cuentas_antiguo(models_a, uid_a, veh_antiguo["id"])
        if not cuentas:
            log.info("  Sin cuentas adt.comercial.cuentas para este vehículo — skip")
            stats["vehiculos_sin_cuentas"] += 1
            continue

        log.info("  Cuentas encontradas: %d", len(cuentas))

        for cuenta in cuentas:
            log.info("  Procesando cuenta antiguo_id=%s state=%s ref=%s",
                     cuenta["id"], cuenta.get("state"), cuenta.get("reference_no"))
            try:
                # PASO 4 — Crear cuenta en nuevo Odoo
                # Usar driver_id del vehículo en el nuevo Odoo como partner_id de la cuenta
                driver_id_nuevo = m2o_id(veh_nuevo.get("driver_id"))
                if not driver_id_nuevo:
                    log.warning(
                        "  ⚠ Vehículo placa=%s (nuevo_id=%s) no tiene driver_id. "
                        "La cuenta se creará sin partner_id.", placa, veh_nuevo["id"]
                    )
                nueva_cuenta_id = crear_cuenta_nuevo(
                    models_n, uid_n, cuenta, veh_nuevo["id"], driver_id_nuevo, dry_run
                )

                if not dry_run and not nueva_cuenta_id:
                    log.error("  ✗ No se pudo crear la cuenta antiguo_id=%s", cuenta["id"])
                    stats["cuentas_error"] += 1
                    continue

                if not dry_run:
                    stats["cuentas_migradas"] += 1

                # PASO 5 — Migrar cuotas
                cuotas_antiguas = buscar_cuotas_antiguo(models_a, uid_a, cuenta["id"])
                log.info("  Cuotas a migrar: %d", len(cuotas_antiguas))

                # Resolver partner_id para los pagos: usar driver_id del vehículo nuevo
                partner_id_para_pagos = driver_id_nuevo if not dry_run else None

                for cuota in cuotas_antiguas:
                    # PASO 5a — Crear cuota
                    nueva_cuota_id = crear_cuota_nuevo(
                        models_n, uid_n, cuota,
                        nueva_cuenta_id or 0,
                        dry_run
                    )

                    if not dry_run:
                        stats["cuotas_migradas"] += 1

                    # PASO 6 — Migrar pagos si los hay
                    payment_ids = cuota.get("payment_ids") or []
                    if payment_ids:
                        pagos = buscar_pagos_cuota(models_a, uid_a, cuota["id"])
                        if pagos:
                            crear_pagos_cuota(
                                models_n, uid_n, pagos,
                                nueva_cuota_id or 0,
                                partner_id_para_pagos,
                                journal_id,
                                dry_run
                            )
                            if not dry_run:
                                stats["pagos_migrados"] += len(pagos)

            except Exception as e:
                log.exception("  ✗ Error procesando cuenta antiguo_id=%s: %s", cuenta["id"], e)
                stats["cuentas_error"] += 1

    # Resumen final
    log.info("")
    log.info("=" * 60)
    log.info("RESUMEN DE MIGRACIÓN (%s)", mode)
    log.info("=" * 60)
    for k, v in stats.items():
        log.info("  %-40s %d", k.replace("_", " ").capitalize() + ":", v)
    log.info("=" * 60)

    if dry_run:
        log.info("Ningún dato fue modificado. Ejecuta sin --dry-run para aplicar.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migración ADT Comercial entre instancias Odoo",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simula la migración sin crear ni modificar nada en el nuevo Odoo"
    )
    parser.add_argument(
        "--limite", type=int, default=0, metavar="N",
        help=(
            "Cantidad de vehículos a procesar:\n"
            "  --limite 1      → procesa solo 1 vehículo\n"
            "  --limite 10     → procesa los primeros 10 vehículos\n"
            "  --limite 0      → procesa TODOS (valor por defecto)\n"
            "  (omitir)        → procesa TODOS"
        )
    )
    parser.add_argument(
        "--placas", nargs="+", metavar="PLACA", default=None,
        help=(
            "Lista de placas específicas a migrar (ignora --limite si se usa):\n"
            "  --placas 0334BD 8613YC 5391BD\n"
            "  --placas 6363ID 9836ED"
        )
    )
    args = parser.parse_args()
    migrar(dry_run=args.dry_run, limite=args.limite, placas_filtro=args.placas)