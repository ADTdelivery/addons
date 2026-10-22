# -*- coding: utf-8 -*-
from odoo import models


class AdtComercialCuentas(models.Model):
    """El titular del vehículo sigue al crédito: se asigna al crearlo o aprobarlo (Flota 360),
    se libera al anularlo o recuperarlo y vuelve si la cuenta se restablece."""
    _inherit = 'adt.comercial.cuentas'

    def cancelar_cuenta(self):
        # recuperar_vehiculo también pasa por aquí.
        res = super().cancelar_cuenta()
        self.env['adt.flota360']._liberar_titular(self)
        return res

    def restablecer_vehiculo(self):
        res = super().restablecer_vehiculo()
        self.env['adt.flota360']._reasignar_titular(self)
        return res
