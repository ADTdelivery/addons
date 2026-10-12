# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Estados de placa de procedure_plate -> estados de adt_tramite_placa."""
    for viejo, nuevo in (('tramitado', 'finalizado'), ('rechazado', 'observado')):
        cr.execute("UPDATE adt_moto_tracking SET estado_placa = %s WHERE estado_placa = %s", (nuevo, viejo))
        cr.execute("UPDATE adt_moto_tracking_log SET codigo_hasta = %s WHERE flujo = 'placa' AND codigo_hasta = %s",
                   (nuevo, viejo))
