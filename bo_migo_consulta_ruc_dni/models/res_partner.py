# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.addons.bo_migo_consulta_ruc_dni.models.utils import request_migo_dni,request_migo_ruc
import requests
import json
from io import StringIO, BytesIO
import os
import logging
import re

_logger = logging.getLogger(__name__)

patron_ruc = re.compile("[12]\d{10}$")
patron_dni = re.compile("\d{8}$")


class ResPartner(models.Model):
    _inherit = "res.partner"

    estado_contribuyente = fields.Char(string='Estado del Contribuyente')
    msg_error = fields.Char(string="Error de consulta RUC DNI")
    ubigeo = fields.Char(string="Ubigeo")

    @api.onchange('l10n_latam_identification_type_id', 'vat')
    def vat_change(self):
        self.update_document()

    @api.model
    def _esrucvalido(self, vat_str):
        if patron_ruc.match(vat_str) :
            vat_arr = [int(c) for c in vat_str]
            arr = [5,4,3,2,7,6,5,4,3,2]
            s = sum([vat_arr[r]*arr[r] for r in range(0,10)])
            num_ver = (11-s%11)%10
            if vat_arr[10] != num_ver:
                return False
            return True
        else:
            return False

    def update_document(self):
        self.ensure_one()
        # self = self.with_context(check_flag=True)
        if not self.vat:
            return False
        if self.l10n_latam_identification_type_id.l10n_pe_vat_code == '1':
            # Valida DNI
            if self.vat:
                self.vat = self.vat.strip()
            if self.vat and len(self.vat) != 8:
                self.msg_error = 'El DNI debe tener 8 caracteres'
            else:
                # _logger.info(self.vat)
                response = request_migo_dni(self.vat)
                if "name" in response:
                    self.name = response.get("name")
                    # self.registration_name = nombre_entidad
                else:
                    self.name = " - "
                    # self.registration_name = " - "

        elif self.l10n_latam_identification_type_id.l10n_pe_vat_code == '6':
            # Valida RUC
            if self.vat and len(self.vat) != 11:
                self.msg_error = "El RUC debe tener 11 carácteres"
            if not self._esrucvalido(self.vat):
                self.msg_error = "El RUC no es Válido"
            else:
                _logger.info(self.vat)
                d = request_migo_ruc(self.vat)
                _logger.info(d)
                if not d:
                    self.name = " - "
                    return True
                if not d["success"]:
                    self.name = " - "
                    return True

                # _logger.info(d)
                ditrict_obj = self.env['l10n_pe.res.city.district']
                dist_id = ditrict_obj.search([('code', '=', d['ubigeo'])], limit=1)
                # _logger.info(dist_id)

                self.estado_contribuyente = d['estado_del_contribuyente']
                self.name = d['nombre_o_razon_social']
                # self.registration_name = d['nombre_o_razon_social']
                self.ubigeo = d["ubigeo"]
                self.street = d['direccion']
                # self.is_company = True
                self.company_type = "company"

                if dist_id:
                    self.l10n_pe_district = dist_id.id
                    self.city_id = dist_id.city_id.id
                    self.state_id = self.city_id.state_id.id
                    self.country_id = self.city_id.country_id.id