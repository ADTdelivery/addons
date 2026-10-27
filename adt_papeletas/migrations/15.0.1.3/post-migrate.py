# -*- coding: utf-8 -*-
"""solo_cuentas_vigentes (bool) -> estado_cuenta_ids (aprobado + en curso).

Sin marcar equivalía a no filtrar por estado, que ahora es dejar la lista vacía.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'adt_papeleta_sat_programa' AND column_name = 'solo_cuentas_vigentes'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        INSERT INTO adt_papeleta_sat_programa_estado_rel (programa_id, estado_id)
        SELECT p.id, e.id
          FROM adt_papeleta_sat_programa p
          JOIN adt_papeleta_sat_estado_cuenta e ON e.code IN ('aprobado', 'en_curso')
         WHERE p.solo_cuentas_vigentes
        ON CONFLICT DO NOTHING
    """)
