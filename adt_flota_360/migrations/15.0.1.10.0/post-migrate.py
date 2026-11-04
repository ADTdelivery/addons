# -*- coding: utf-8 -*-
"""Monitoreo GPS en tiempo real: el cron de respaldo pasa de 2 a 1 minuto (el registro
del cron es noupdate, así que el XML no lo cambia en instalaciones existentes)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_cron SET interval_number = 1
         WHERE interval_type = 'minutes' AND interval_number = 2
           AND id IN (SELECT res_id FROM ir_model_data
                       WHERE module = 'adt_flota_360' AND name = 'cron_gps_monitor' AND model = 'ir.cron')
    """)
