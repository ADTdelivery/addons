from odoo import models,fields,api
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
_logger = logging.getLogger(__name__)

def request_migo_dni(dni):
    ICPSudo = request.env["ir.config_parameter"].sudo()
    api_migo_endpoint = ICPSudo.get_param("api.migo.endpoint", default="")
    api_migo_token = ICPSudo.get_param("api.migo.token", default="")
    url = api_migo_endpoint+ ('' if api_migo_endpoint[-1] == '/' else '/') + "dni"
    
    try:
        headers = {
            'Content-Type': 'application/json'
        }
        data = {
            "token": api_migo_token,
            "dni": dni
        }
        res = requests.request(
            "POST", url, headers=headers, data=json.dumps(data),timeout=3)
        res = res.json()
        _logger.info(res)
        if res.get("success", False):
            return {"name":res.get("nombre", False)}
        return {}
    except Exception as e:
        return {}

def request_migo_ruc( ruc):
    errors = []
    ICPSudo = request.env["ir.config_parameter"].sudo()
    api_migo_endpoint = ICPSudo.get_param("api.migo.endpoint", default="")
    api_migo_token = ICPSudo.get_param("api.migo.token", default="")
    url = api_migo_endpoint+ ('' if api_migo_endpoint[-1] == '/' else '/') + "ruc"
    
    _logger.info([api_migo_endpoint,api_migo_token])
    if not api_migo_endpoint:
        errors.append("Debe configurar el end-point del API")
    if not api_migo_token:
        errors.append("Debe configurar el token del API")
    if len(errors) > 0:
        raise UserError("\n".join(errors))
    else:
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            data = {
                "token": api_migo_token,
                "ruc": ruc
            }
            res = requests.request("POST", url, headers=headers, data=json.dumps(data),timeout=3)
            res = res.json()
            _logger.info(res)
            if res.get("success", False):
                return res
            return {}
        except Exception as e:
            _logger.info(e)
            return {}