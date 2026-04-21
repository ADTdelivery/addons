# -*- coding: utf-8 -*-
"""
IrHttp override to fix mobile API GET requests that send Content-Type: application/json.

Mobile apps (Android/iOS) often send Content-Type: application/json on every
request regardless of HTTP method.  Odoo 15 dispatches based on Content-Type:
when it sees 'application/json' it routes to JsonRequest, which tries to parse
the body — but GET requests have no body → "Invalid JSON data: ''" → 400.

Fix: for GET/HEAD requests on /v1/* paths, force the WSGI environ
CONTENT_TYPE to '' so Odoo routes them through HttpRequest instead.
"""
import logging
from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

_MOBILE_API_PREFIX = '/v1/'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _dispatch(cls):
        """
        Before normal dispatch, strip Content-Type from GET/HEAD requests
        that target the mobile API (/v1/*) so Odoo does not try to parse
        an empty body as JSON.
        """
        httprequest = request.httprequest
        if (
            httprequest.method in ('GET', 'HEAD')
            and httprequest.path.startswith(_MOBILE_API_PREFIX)
            and httprequest.content_type
            and 'application/json' in httprequest.content_type
        ):
            # Patch the WSGI environ in-place — this is safe because the
            # environ dict is request-scoped and never shared across threads.
            httprequest.environ['CONTENT_TYPE'] = ''
            # Werkzeug caches content_type; clear it so the patched value is used.
            if 'content_type' in httprequest.__dict__:
                del httprequest.__dict__['content_type']

        return super()._dispatch()
