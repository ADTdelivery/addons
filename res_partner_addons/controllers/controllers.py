#-*- coding: utf-8 -*-
import requests
from odoo import http
from odoo.http import request
from werkzeug.exceptions import NotFound


def validate(data):
    if not data:
        return ""
    else:
        return data


class ResPartnerAddons(http.Controller):
    @http.route('/api/respartner/client', type='json', auth='none')
    def authenticate(self, db,login,password,credential):
        request.session.authenticate(db,login,password)
        data = request.env['res.partner']\
            .search(
            [['vat','=', credential['number_document'] ]])\
            .read(['id','name','street','l10n_latam_identification_type_id',
                   'phone','mobile'])
        try:
            for value in data[0]:
                data[0][value] = validate(data[0][value])
            return data
        except:
            raise NotFound()

    @http.route('/api/respartner/register', type='json', auth='none')
    def register(self, db,login,password,register):
        request.session.authenticate(db,login,password)
        data = request.env['res.partner'].sudo().create({

        })
        try:
            for value in data[0]:
                data[0][value] = validate(data[0][value])
            return data
        except:
            raise NotFound()





