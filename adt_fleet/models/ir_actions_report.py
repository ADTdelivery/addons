# -*- coding: utf-8 -*-
import os
import base64
from odoo import models

_MODULE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IMG_PATH = os.path.join(_MODULE_PATH, 'static', 'src', 'img')

_REPORT_NAME = 'adt_fleet.report_acta_vehicular'


def _b64(filename):
    with open(os.path.join(_IMG_PATH, filename), 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _html_header():
    b64 = _b64('header.png')
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        '<style>*{margin:0;padding:0;box-sizing:border-box;}'
        'body{margin:0;padding:0;width:100%;}'
        'img{width:100%;display:block;}</style></head>'
        '<body><img src="data:image/png;base64,' + b64 + '"/></body></html>'
    )


def _html_footer():
    b64 = _b64('footer.png')
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        '<style>*{margin:0;padding:0;box-sizing:border-box;}'
        'body{margin:0;padding:0;width:100%;}'
        'img{width:100%;display:block;}</style></head>'
        '<body><img src="data:image/png;base64,' + b64 + '"/></body></html>'
    )


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _run_wkhtmltopdf(self, bodies, header=None, footer=None, **kwargs):
        if self.report_name == _REPORT_NAME:
            header = _html_header()
            footer = _html_footer()
        return super()._run_wkhtmltopdf(bodies, header=header, footer=footer, **kwargs)
