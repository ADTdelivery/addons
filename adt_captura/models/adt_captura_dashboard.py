# -*- coding: utf-8 -*-
from odoo import models, fields, tools

class AdtCapturaDashboard(models.Model):
    _name = "adt.captura.dashboard"
    _description = "Dashboard Captura"
    _auto = False

    capturas_activas = fields.Integer(string="Capturas Activas")
    monto_pendiente = fields.Float(string="Monto Pendiente - Intervención")
    clientes_mora = fields.Integer(string="Clientes en Mora")
    monto_vencido_total = fields.Float(string="Monto Vencido Total")

    compromiso_pago = fields.Integer(string="Compromisos de Pago")
    inmediata = fields.Integer(string="Capturas Inmediatas")
    compromisos_pago_vencidos = fields.Integer(string="Compromisos de Pago Vencidos")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Check if the adt_captura_mora view/table exists before referencing it
        self.env.cr.execute("SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = %s)", ('adt_captura_mora',))
        mora_exists = self.env.cr.fetchone()[0]

        if mora_exists:
            clientes_mora_sql = "(SELECT COUNT(*) FROM adt_captura_mora) AS clientes_mora,"
            monto_vencido_sql = "(SELECT COALESCE(SUM(monto_vencido), 0) FROM adt_captura_mora) AS monto_vencido_total"
        else:
            clientes_mora_sql = "0 AS clientes_mora,"
            monto_vencido_sql = "0 AS monto_vencido_total"

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    1 as id,

                    -- capturas activas
                    (SELECT COUNT(*)
                     FROM adt_captura_record
                     WHERE state = 'capturado') AS capturas_activas,

                     -- compromisos de pago
                    (SELECT COUNT(*)
                     FROM adt_captura_record
                     WHERE state = 'compromiso_pago') AS compromiso_pago,

                     -- compromiso de pago vencido
                    (SELECT COUNT(*)
                     FROM adt_captura_record
                     WHERE capture_type = 'compromiso' AND
                     commitment_date < CURRENT_DATE AND
                     payment_state = 'pendiente') AS compromisos_pago_vencidos,

                     -- capturas inmediata
                    (SELECT COUNT(*)
                     FROM adt_captura_record
                     WHERE state = 'inmediata') AS inmediata,

                    -- monto pendiente
                    (SELECT COALESCE(SUM(intervention_fee), 0)
                     FROM adt_captura_record
                     WHERE payment_state = 'pendiente') AS monto_pendiente,

                    -- clientes en mora
                    {clientes_mora_sql}

                    -- NUEVA METRICA: monto vencido total
                    {monto_vencido_sql}
            )
        """)
