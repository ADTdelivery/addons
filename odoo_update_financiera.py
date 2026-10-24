#!/usr/bin/env python3
"""
Actualiza el campo "Tipo de Financiera" (tipo_financiera_id) de las cuentas
comerciales (adt.comercial.cuentas) en un Odoo remoto vía XML-RPC.

Credenciales por variables de entorno (o argumentos):
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD (contraseña o API key)

La financiera se indica por nombre o código (adt.comercial.financiera).

Ejemplos:
    # Ver financieras disponibles
    python3 odoo_update_financiera.py --listar

    # Por referencia de cuenta
    python3 odoo_update_financiera.py -F "Santander" --referencias CTA-0001 CTA-0002

    # Por chasis
    python3 odoo_update_financiera.py -F los_andes --chasis MD6M14LA6V4AA2336 --dry-run

    # Por placa
    python3 odoo_update_financiera.py -F SANT --placas ABC-123 XYZ-789 --dry-run

    # Por IDs
    python3 odoo_update_financiera.py -F "Santander" --ids 15 16

    # Quitar la financiera
    python3 odoo_update_financiera.py --quitar --ids 15

    # Masivo desde CSV (columnas: referencia o placa, y financiera)
    #   placa,financiera
    #   ABC-123,Santander
    #   XYZ-789,Mitsui
    python3 odoo_update_financiera.py --csv cambios.csv
"""
import argparse
import csv
import os
import sys
import xmlrpc.client

MODELO_CUENTA = "adt.comercial.cuentas"
MODELO_FINANCIERA = "adt.comercial.financiera"
CAMPO = "tipo_financiera_id"
CAMPO_PLACA = "moto_placa"
CAMPO_CHASIS = "moto_chasis"


def parse_args():
    p = argparse.ArgumentParser(description="Actualizar Tipo de Financiera en cuentas comerciales")
    p.add_argument("--url", default=os.getenv("http://52.15.86.160:8074"))
    p.add_argument("--db", default=os.getenv("odoov15"))
    p.add_argument("--user", default=os.getenv("odoov15@gmail.com"))
    p.add_argument("--password", default=os.getenv("odoov15@gmail.com"))

    p.add_argument("--listar", action="store_true", help="Lista las financieras y termina")
    fin = p.add_mutually_exclusive_group()
    fin.add_argument("-F", "--financiera", help="Nombre o código de la financiera")
    fin.add_argument("--quitar", action="store_true", help="Deja el campo vacío")

    target = p.add_mutually_exclusive_group()
    target.add_argument("--ids", type=int, nargs="+", help="IDs de cuentas")
    target.add_argument("--referencias", nargs="+", help="Valores de reference_no")
    target.add_argument("--placas", nargs="+", help="Valores de moto_placa")
    target.add_argument("--chasis", nargs="+", help="Números de chasis (VIN)")
    target.add_argument("--csv", help="CSV con columnas referencia|placa y financiera")

    p.add_argument("--dry-run", action="store_true", help="Muestra qué cambiaría sin escribir")
    p.add_argument("-y", "--yes", action="store_true", help="No pedir confirmación")
    args = p.parse_args()

    missing = [k for k in ("url", "db", "user", "password") if not getattr(args, k)]
    if missing:
        p.error("Faltan credenciales: " + ", ".join(missing))
    if not args.listar:
        if not (args.ids or args.referencias or args.placas or args.chasis or args.csv):
            p.error("Indica --ids, --referencias, --placas, --chasis o --csv")
        if not args.csv and not (args.financiera or args.quitar):
            p.error("Indica -F/--financiera o --quitar")
    return args


class Odoo:
    def __init__(self, url, db, user, password):
        url = url.rstrip("/")
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            sys.exit("Error: autenticación fallida.")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        self.db, self.password = db, password

    def call(self, model, method, *params, **kw):
        return self.models.execute_kw(self.db, self.uid, self.password, model, method, list(params), kw)


def cargar_financieras(odoo):
    """Devuelve {clave_normalizada: (id, nombre)} indexado por nombre y por código."""
    recs = odoo.call(MODELO_FINANCIERA, "search_read",
                     ["|", ("active", "=", True), ("active", "=", False)],
                     fields=["name", "code", "active"])
    idx = {}
    for r in recs:
        for clave in (r["name"], r["code"]):
            if clave:
                idx[clave.strip().upper()] = (r["id"], r["name"], r["active"])
    return recs, idx


def resolver_financiera(idx, texto):
    hit = idx.get(texto.strip().upper())
    if not hit:
        sys.exit(f"Error: no existe la financiera '{texto}'. Usa --listar para ver las disponibles.")
    fid, nombre, activa = hit
    if not activa:
        print(f"Aviso: la financiera '{nombre}' está archivada.")
    return fid, nombre


def leer_cuentas(odoo, domain):
    return odoo.call(MODELO_CUENTA, "search_read", domain,
                     fields=["reference_no", CAMPO_PLACA, CAMPO_CHASIS, CAMPO])


def plan_desde_args(odoo, args, idx):
    """Devuelve lista de (cuenta, financiera_id|False, financiera_nombre)."""
    if args.quitar:
        fid, fnombre = False, "(vacío)"
    else:
        fid, fnombre = resolver_financiera(idx, args.financiera)

    if args.ids:
        campo, valores = "id", args.ids
    elif args.referencias:
        campo, valores = "reference_no", args.referencias
    elif args.chasis:
        campo, valores = CAMPO_CHASIS, args.chasis
    else:
        campo, valores = CAMPO_PLACA, args.placas

    cuentas = leer_cuentas(odoo, [(campo, "in", valores)])
    encontrados = {c[campo] for c in cuentas}
    for v in valores:
        if v not in encontrados:
            print(f"Aviso: no se encontró cuenta con {campo} = {v}")
    return [(c, fid, fnombre) for c in cuentas]


def plan_desde_csv(odoo, ruta, idx):
    with open(ruta, newline="", encoding="utf-8-sig") as fh:
        filas = list(csv.DictReader(fh))
    if not filas:
        sys.exit("El CSV está vacío.")
    cols = {c.strip().lower(): c for c in filas[0].keys()}
    if "financiera" not in cols or not ({"referencia", "placa"} & cols.keys()):
        sys.exit("El CSV debe tener columnas 'financiera' y 'referencia' o 'placa'.")
    usa_ref = "referencia" in cols
    col_clave = cols["referencia" if usa_ref else "placa"]
    campo = "reference_no" if usa_ref else CAMPO_PLACA

    claves = [f[col_clave].strip() for f in filas if f[col_clave].strip()]
    por_clave = {}
    for c in leer_cuentas(odoo, [(campo, "in", claves)]):
        por_clave.setdefault(c[campo], []).append(c)

    plan = []
    for f in filas:
        clave = f[col_clave].strip()
        texto_fin = f[cols["financiera"]].strip()
        if not clave:
            continue
        cuentas = por_clave.get(clave)
        if not cuentas:
            print(f"Aviso: no se encontró cuenta con {campo} = {clave}")
            continue
        if texto_fin:
            fid, fnombre = resolver_financiera(idx, texto_fin)
        else:
            fid, fnombre = False, "(vacío)"
        plan.extend((c, fid, fnombre) for c in cuentas)
    return plan


def main():
    args = parse_args()
    odoo = Odoo(args.url, args.db, args.user, args.password)
    financieras, idx = cargar_financieras(odoo)

    if args.listar:
        print(f"{'ID':>4}  {'CÓDIGO':<12} NOMBRE")
        for r in financieras:
            estado = "" if r["active"] else "  (archivada)"
            print(f"{r['id']:>4}  {r['code'] or '':<12} {r['name']}{estado}")
        return

    plan = plan_desde_csv(odoo, args.csv, idx) if args.csv else plan_desde_args(odoo, args, idx)
    # Omitir las que ya tienen el valor correcto
    plan = [(c, fid, fn) for c, fid, fn in plan if (c[CAMPO] and c[CAMPO][0]) != fid]
    if not plan:
        print("Nada que actualizar.")
        return

    print(f"\n{len(plan)} cuenta(s) a actualizar:")
    for c, _fid, fnombre in plan[:100]:
        actual = c[CAMPO][1] if c[CAMPO] else "(vacío)"
        print(f"  [{c['id']}] {c['reference_no']} / {c[CAMPO_PLACA] or '-'}: {actual} → {fnombre}")
    if len(plan) > 100:
        print(f"  ... y {len(plan) - 100} más")

    if args.dry_run:
        print("\nDry-run: no se escribió nada.")
        return
    if not args.yes and input("\n¿Confirmar? [s/N]: ").strip().lower() not in ("s", "si", "sí", "y"):
        print("Cancelado.")
        return

    # Agrupar por financiera para hacer un write por grupo
    grupos = {}
    for c, fid, _fn in plan:
        grupos.setdefault(fid, []).append(c["id"])
    for fid, ids in grupos.items():
        odoo.call(MODELO_CUENTA, "write", ids, {CAMPO: fid})
    print(f"OK: {len(plan)} cuenta(s) actualizadas.")


if __name__ == "__main__":
    try:
        main()
    except xmlrpc.client.Fault as e:
        sys.exit(f"Error de Odoo: {e.faultString.strip().splitlines()[-1]}")
