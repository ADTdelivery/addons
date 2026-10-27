# -*- coding: utf-8 -*-
"""Programas SAT: financiera_codigo (una) -> financiera_ids (varias).

adt_papeletas ya quitó el campo, pero la columna sigue en la tabla.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'adt_papeleta_sat_programa' AND column_name = 'financiera_codigo'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        INSERT INTO adt_papeleta_sat_programa_financiera_rel (programa_id, financiera_id)
        SELECT p.id, f.id
          FROM adt_papeleta_sat_programa p
          JOIN adt_comercial_financiera f ON f.code = p.financiera_codigo
        ON CONFLICT DO NOTHING
    """)
