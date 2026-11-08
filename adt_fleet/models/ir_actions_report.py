# -*- coding: utf-8 -*-
"""Header/footer de los reportes ADT (Acta y Contrato) replicando el Word.

wkhtmltopdf dibuja header y footer como documentos HTML independientes,
dentro de las franjas definidas por margin_top / margin_bottom del
paperformat. Por eso:

* El paperformat usa margin_left/right = 0: así la franja del header/footer
  ocupa todo el ancho de la hoja y la imagen puede ir a sangre, igual que en
  Word. Los márgenes laterales del texto (25.4 mm) los pone el CSS del body.
* Las imágenes van en base64: wkhtmltopdf no necesita resolver URLs
  (web.base.url / report.url), que es lo que suele fallar en Docker.
* Las posiciones (mm) salen del XML del .docx (wp:anchor -> posOffset/extent).
"""
import base64
import os

from odoo import models
from odoo.tools import file_open

_IMG_DIR = 'adt_fleet/static/src/img'

# Geometría en mm tomada de context/*.docx (las dos plantillas comparten imágenes)
_HEADER = {'img': 'adt_header.png', 'left': -1.69, 'top': -0.2, 'width': 212.48, 'height': 19.37}
_FOOTER = {'img': 'adt_footer.png', 'left': -0.8, 'bottom': 0.15, 'width': 211.6, 'height': 18.28}

_REPORTS = {
    'adt_fleet.report_acta_vehicular',
    'adt_fleet.report_contrato_tvs',
}


def _b64(filename):
    with file_open(os.path.join(_IMG_DIR, filename), 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _band_html(spec, band_height, anchor):
    """HTML de una franja (header o footer) con la imagen posicionada en mm.

    :param band_height: alto de la franja en mm (= margin_top o margin_bottom).
    :param anchor: 'top' para el header, 'bottom' para el footer.
    """
    pos = '%s:%.2fmm;' % (anchor, spec[anchor])
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/><style>'
        'html,body{margin:0;padding:0;}'
        'body{position:relative;width:210mm;height:%.2fmm;overflow:hidden;}'
        'img{position:absolute;display:block;left:%.2fmm;%swidth:%.2fmm;height:%.2fmm;}'
        '</style></head><body><img src="data:image/png;base64,%s"/></body></html>'
    ) % (band_height, spec['left'], pos, spec['width'], spec['height'], _b64(spec['img']))


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _run_wkhtmltopdf(self, bodies, header=None, footer=None, **kwargs):
        if self.report_name in _REPORTS:
            pf = self.get_paperformat()
            header = _band_html(_HEADER, pf.margin_top, 'top')
            footer = _band_html(_FOOTER, pf.margin_bottom, 'bottom')
            # Sin div.article Odoo pasa el body como fragmento (sin doctype ->
            # quirks mode, donde las tablas no heredan fuente ni interlineado).
            bodies = [
                b if b.lstrip()[:9].lower() == '<!doctype'
                else '<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body>%s</body></html>' % b
                for b in bodies
            ]
        return super()._run_wkhtmltopdf(bodies, header=header, footer=footer, **kwargs)
