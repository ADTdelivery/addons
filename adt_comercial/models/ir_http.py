# -*- coding: utf-8 -*-
"""
IrHttp override to fix mobile API requests that send Content-Type: application/json
against endpoints declared type='http'.

Mobile apps (Android/iOS) often send Content-Type: application/json on every
request regardless of HTTP method — GET included, and POST even against endpoints
that don't expect a JSON-RPC envelope. Odoo 15 decides HttpRequest vs. JsonRequest
purely from that header, *before* it knows which route matched:
  - GET/HEAD with that header → JsonRequest tries to parse an empty body →
    "Invalid JSON data: ''" → 400.
  - POST with that header against a route declared `type='http'` → Odoo builds a
    JsonRequest, then at dispatch time finds the route wants HttpRequest → 400
    "Function declared as capable of handling request of type 'http' but called
    with a request of type 'json'".

Fix: force the WSGI environ CONTENT_TYPE to '' so Odoo routes these through
HttpRequest instead — safe because every `type='http'` controller in
adt_comercial parses the JSON body itself from the raw bytes
(`request.httprequest.data`), it never relies on Odoo's own JSON-RPC parsing.

Only a handful of /v1/* POST endpoints are genuinely `type='json'` (JSON-RPC) —
those are excluded so this override doesn't break THEM the other way around.
Keep `_JSON_RPC_POST_PATHS` in sync with `controllers/mobile_api.py` if a new
`type='json'` POST route is added there.
"""
import logging
from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

_MOBILE_API_PREFIX = '/v1/'

# POST routes under /v1/* that are deliberately type='json' (JSON-RPC) — do NOT
# strip their Content-Type, they need to stay JsonRequest.
_JSON_RPC_POST_PATHS = {
    '/v1/auth/login',
    '/v1/auth/logout',
    '/v1/promotions',
    '/v1/maintenance/record',
}


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _dispatch(cls):
        """
        Before normal dispatch, strip Content-Type from requests targeting the
        mobile API (/v1/*) that would otherwise be misrouted to JsonRequest:
        all GET/HEAD, and any POST except the explicit JSON-RPC exceptions above.
        """
        httprequest = request.httprequest
        is_mobile_api = httprequest.path.startswith(_MOBILE_API_PREFIX)
        has_json_content_type = bool(
            httprequest.content_type and 'application/json' in httprequest.content_type)

        should_strip = is_mobile_api and has_json_content_type and (
            httprequest.method in ('GET', 'HEAD')
            or (httprequest.method == 'POST' and httprequest.path not in _JSON_RPC_POST_PATHS)
        )

        if should_strip:
            # Patch the WSGI environ in-place — this is safe because the
            # environ dict is request-scoped and never shared across threads.
            httprequest.environ['CONTENT_TYPE'] = ''
            # Werkzeug caches content_type; clear it so the patched value is used.
            if 'content_type' in httprequest.__dict__:
                del httprequest.__dict__['content_type']

        return super()._dispatch()
