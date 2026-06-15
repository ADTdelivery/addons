# -*- coding: utf-8 -*-
import os
import base64
from odoo import models

_MODULE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IMG_PATH = os.path.join(_MODULE_PATH, 'static', 'src', 'img')

_REPORT_ACTA      = 'adt_fleet.report_acta_vehicular'
_REPORT_CONTRATO  = 'adt_fleet.report_contrato_tvs'


def _b64(filename):
    with open(os.path.join(_IMG_PATH, filename), 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _make_html(img_filename):
    b64 = _b64(img_filename)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        '<style>*{margin:0;padding:0;box-sizing:border-box;}'
        'body{margin:0;padding:0;width:100%;}'
        'img{width:100%;display:block;}</style></head>'
        '<body><img src="data:image/png;base64,' + b64 + '"/></body></html>'
    )


_CONFIGS = {
    _REPORT_ACTA:     ('header.png',    'footer.png'),
    _REPORT_CONTRATO: ('header_v2.png', 'footer_v2.png'),
}


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _run_wkhtmltopdf(self, bodies, header=None, footer=None, **kwargs):
        cfg = _CONFIGS.get(self.report_name)
        if cfg:
            header = _make_html(cfg[0])
            footer = _make_html(cfg[1])
        return super()._run_wkhtmltopdf(bodies, header=header, footer=footer, **kwargs)
