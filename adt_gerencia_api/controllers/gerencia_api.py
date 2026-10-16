# -*- coding: utf-8 -*-
"""API de la app de gerencia (v1). Ver API.md.

Autenticación: POST /api/gerencia/v1/auth/login devuelve un token; el resto de
endpoints exige el header  Authorization: Bearer <token>.  Solo pueden entrar los
usuarios del grupo "Acceso a la app de gerencia" y el permiso se revisa en cada
llamada.

Respuestas:
  éxito  {"ok": true,  "data": ..., "meta": {...}}
  error  {"ok": false, "error": {"codigo": "...", "mensaje": "..."}}
"""
import json
import logging

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import Response, request

from ..models.gerencia_token import GRUPO

_logger = logging.getLogger(__name__)

PREFIJO = '/api/gerencia/v1'


def _respuesta(cuerpo, estado=200):
    return Response(json.dumps(cuerpo, ensure_ascii=False, default=str), status=estado,
                    content_type='application/json; charset=utf-8')


def _ok(data, meta=None):
    cuerpo = {'ok': True, 'data': data}
    if meta:
        cuerpo['meta'] = meta
    return _respuesta(cuerpo)


def _error(estado, codigo, mensaje):
    return _respuesta({'ok': False, 'error': {'codigo': codigo, 'mensaje': mensaje}}, estado)


def _cuerpo_json():
    try:
        return json.loads(request.httprequest.get_data(as_text=True) or '{}')
    except ValueError:
        return None


def _token():
    auth = request.httprequest.headers.get('Authorization', '')
    return auth[7:].strip() if auth.startswith('Bearer ') else ''


def _entero(valor, nombre):
    if valor in (None, ''):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError('El parámetro "%s" debe ser un número.' % nombre)


def protegido(funcion):
    """Valida el token y el grupo; pasa el usuario al endpoint y convierte errores en JSON."""
    def envoltura(self, **kwargs):
        bearer = _token()
        user = request.env['adt.gerencia.token'].sudo().validar(bearer) if bearer else None
        # La app seller reutiliza /web/session/authenticate; no necesita otro login.
        # Si se envió Bearer, un token inválido no se sustituye por la cookie.
        if not bearer and request.session.uid:
            session_user = request.env['res.users'].sudo().browse(request.session.uid).exists()
            # Revalida la sesión para detectar usuarios inactivos/cambios de contraseña.
            from odoo.service import security
            if (session_user and session_user.active and security.check_session(request.session, request.env)
                    and session_user._is_internal() and session_user.has_group(GRUPO)):
                user = session_user
        if not user:
            return _error(401, 'NO_AUTORIZADO', 'Sesión inválida, vencida o sin permiso para la app de gerencia.')
        try:
            return funcion(self, user, **kwargs)
        except ValueError as e:
            return _error(400, 'PARAMETRO_INVALIDO', str(e))
        except Exception:
            _logger.exception('API gerencia: error en %s', request.httprequest.path)
            return _error(500, 'ERROR_INTERNO', 'No se pudieron calcular los indicadores. Intenta nuevamente.')
    envoltura.__name__ = funcion.__name__
    envoltura.__doc__ = funcion.__doc__
    return envoltura


class GerenciaApi(http.Controller):

    def _indicadores(self, user):
        return request.env['adt.gerencia.indicadores'].with_user(user)

    # ------------------------------------------------------------------ sesión

    @http.route(PREFIJO + '/auth/login', type='http', auth='none', methods=['POST'], csrf=False)
    def login(self, **_kw):
        """{"login": "...", "password": "...", "dispositivo": "iPhone de ...", "app_version": "1.0.0"}"""
        datos = _cuerpo_json()
        if datos is None:
            return _error(400, 'JSON_INVALIDO', 'El cuerpo debe ser JSON.')
        login, password = (datos.get('login') or '').strip(), datos.get('password') or ''
        if not login or not password:
            return _error(400, 'DATOS_INCOMPLETOS', 'Envía login y password.')
        try:
            uid = request.env['res.users'].sudo()._login(request.db, login, password, {'interactive': False})
        except AccessDenied:
            return _error(401, 'CREDENCIALES_INVALIDAS', 'Usuario o contraseña incorrectos.')
        user = request.env['res.users'].sudo().browse(uid)
        if not user.has_group(GRUPO):
            return _error(403, 'SIN_PERMISO', 'Tu usuario no tiene acceso a la app de gerencia.')
        token, rec = request.env['adt.gerencia.token'].sudo().emitir(
            user, dispositivo=datos.get('dispositivo'), ip=request.httprequest.remote_addr,
            app_version=datos.get('app_version'))
        return _ok({
            'token': token,
            'tipo': 'Bearer',
            'expira': rec.expira,
            'usuario': {'id': user.id, 'nombre': user.name, 'login': user.login},
        })

    @http.route(PREFIJO + '/auth/logout', type='http', auth='none', methods=['POST'], csrf=False)
    def logout(self, **_kw):
        request.env['adt.gerencia.token'].sudo().revocar(_token())
        return _ok({'cerrada': True})

    @http.route(PREFIJO + '/me', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def me(self, user, **_kw):
        return _ok({'id': user.id, 'nombre': user.name, 'login': user.login,
                    'empresa': user.company_id.name})

    # ------------------------------------------------------------------ datos

    @http.route(PREFIJO + '/dashboard', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def dashboard(self, user, financiera_id=None, **_kw):
        """Todos los indicadores. ?financiera_id=<id> (0 = sin financiera) filtra los montos."""
        return _ok(self._indicadores(user).dashboard(financiera_id=_entero(financiera_id, 'financiera_id')))

    @http.route(PREFIJO + '/resumen', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def resumen(self, user, financiera_id=None, **_kw):
        """Resumen de gerencia por secciones, cada indicador seccionado por financiera."""
        return _ok(self._indicadores(user).resumen(financiera_id=_entero(financiera_id, 'financiera_id')))

    @http.route(PREFIJO + '/resumen/<string:clave>', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def resumen_detalle(self, user, clave, financiera_id=None, filtro=None, buscar=None, pagina=1, por_pagina=20, **_kw):
        """Detalle de un indicador del resumen: las filas que forman su valor."""
        data, meta = self._indicadores(user).resumen_detalle(
            clave, financiera_id=_entero(financiera_id, 'financiera_id'), filtro=filtro or None, buscar=buscar,
            pagina=_entero(pagina, 'pagina') or 1, por_pagina=_entero(por_pagina, 'por_pagina') or 20)
        return _ok(data, meta)

    @http.route(PREFIJO + '/deudores', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def deudores(self, user, financiera_id=None, tramo=None, estado=None, buscar=None, orden='vencido',
                 pagina=1, por_pagina=20, **_kw):
        items, meta = self._indicadores(user).deudores(
            financiera_id=_entero(financiera_id, 'financiera_id'), tramo=tramo, estado=estado, buscar=buscar,
            orden=orden, pagina=_entero(pagina, 'pagina') or 1, por_pagina=_entero(por_pagina, 'por_pagina') or 20)
        return _ok(items, meta)

    @http.route(PREFIJO + '/candidatos', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def candidatos(self, user, financiera_id=None, segmento='apto', buscar=None, pagina=1, por_pagina=20, **_kw):
        items, meta = self._indicadores(user).candidatos(
            financiera_id=_entero(financiera_id, 'financiera_id'), segmento=segmento or None, buscar=buscar,
            pagina=_entero(pagina, 'pagina') or 1, por_pagina=_entero(por_pagina, 'por_pagina') or 20)
        return _ok(items, meta)

    @http.route(PREFIJO + '/traspasos', type='http', auth='none', methods=['GET'], csrf=False)
    @protegido
    def traspasos(self, user, financiera_id=None, etapa=None, buscar=None, pagina=1, por_pagina=20, **_kw):
        items, meta = self._indicadores(user).traspasos(
            financiera_id=_entero(financiera_id, 'financiera_id'), etapa=etapa, buscar=buscar,
            pagina=_entero(pagina, 'pagina') or 1, por_pagina=_entero(por_pagina, 'por_pagina') or 20)
        return _ok(items, meta)
