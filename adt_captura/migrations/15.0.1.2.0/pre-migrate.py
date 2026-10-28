# -*- coding: utf-8 -*-
"""La captura deja de usar la papeleta interna (adt.papeleta): las liberaciones por
pago total o fraccionado de la papeleta pasan a "Pago de las papeletas SAT"."""


def migrate(cr, version):
    cr.execute("""
        UPDATE adt_captura_record
           SET liberacion_tipo = 'pago_papeleta_sat'
         WHERE liberacion_tipo IN ('pago_papeleta_total', 'pago_fraccionado')
    """)
