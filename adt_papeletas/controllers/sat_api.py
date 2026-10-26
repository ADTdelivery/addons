# -*- coding: utf-8 -*-
"""API del monitor de papeletas SAT (EC2).

    POST /api/papeletas/sat/import   cuerpo JSON: una consulta por placa (payload del webhook)
                                     o el resumen completo {"resultados": [...]}.
                                     Odoo responde JSON-RPC (HTTP 200): {"result": {"ok": bool, ...}}.
                                     Si ok es false, el cliente debe reintentar.
    GET  /api/papeletas/sat/placas   placas de la flota a consultar

    Modo agente (programas y ejecuciones creados en Odoo), todos POST JSON-RPC:
    /api/papeletas/sat/ejecuciones/tomar            -> {"ejecucion": {id, name, placas} | null}
    /api/papeletas/sat/ejecuciones/<id>/latido      {procesadas, total, placa} -> {"cancelar": bool}
    /api/papeletas/sat/ejecuciones/<id>/finalizar   {error, cancelada, archivo, resultados: [...]}

Autenticación: cabecera `X-SAT-Token: <token>` (o `Authorization: Bearer <token>`).
El token está en Ajustes > Técnico > Parámetros del sistema > adt_papeletas.sat_token.
"""
import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import Response, request

from ..models.papeleta_sat import PARAM_TOKEN
from ..models.papeleta_sat_programa import _placas_de

_logger = logging.getLogger(__name__)


def _json(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False, default=str), status=status,
                    content_type='application/json; charset=utf-8')


class PapeletasSatAPI(http.Controller):

    def _env(self):
        return request.env(user=SUPERUSER_ID)

    def _autorizado(self, env):
        esperado = env['ir.config_parameter'].get_param(PARAM_TOKEN) or ''
        cabeceras = request.httprequest.headers
        recibido = cabeceras.get('X-SAT-Token') or ''
        auth = cabeceras.get('Authorization') or ''
        if not recibido and auth.lower().startswith('bearer '):
            recibido = auth[7:].strip()
        return bool(esperado) and hmac.compare_digest(recibido.encode(), esperado.encode())

    # type='json': Odoo 15 enruta todo POST application/json como JSON-RPC.
    @http.route('/api/papeletas/sat/import', type='json', auth='none', methods=['POST'], csrf=False)
    def importar(self, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return {'ok': False, 'codigo': 401, 'error': 'token inválido'}
        body = request.jsonrequest or {}
        consultas = body.get('resultados') if isinstance(body.get('resultados'), list) else [body]
        if not all(isinstance(c, dict) and c.get('placa') for c in consultas):
            return {'ok': False, 'codigo': 400, 'error': 'cada consulta debe tener "placa"'}

        Import = env['adt.papeleta.sat.import']
        detalle = []
        for consulta in consultas:
            imp = Import.registrar(consulta)
            detalle.append({
                'placa': imp.placa, 'importacion_id': imp.id, 'estado': imp.state,
                'vehiculo': imp.vehicle_id.id or None, 'nuevas_sat': imp.nuevas_sat,
                'vinculadas': imp.vinculadas, 'creadas': imp.creadas,
                'resueltas': imp.resueltas, 'error': imp.error or None,
            })
        # Con errores, ok=false para que el monitor reintente; la bitácora queda guardada igual.
        return {'ok': not any(d['estado'] == 'error' for d in detalle), 'consultas': detalle}

    @http.route('/api/papeletas/sat/placas', type='http', auth='none', methods=['GET'], csrf=False)
    def placas(self, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return _json({'ok': False, 'error': 'token inválido'}, 401)
        # Mismo criterio que la importación: con placas repetidas gana el vehículo más reciente.
        placas = _placas_de(env['fleet.vehicle'].search([('license_plate', '!=', False)]))
        return _json({'ok': True, 'total': len(placas), 'placas': placas})

    # ------------------------------------------------------------ modo agente
    @http.route('/api/papeletas/sat/ejecuciones/tomar', type='json', auth='none', methods=['POST'], csrf=False)
    def tomar(self, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return {'ok': False, 'codigo': 401, 'error': 'token inválido'}
        return {'ok': True, 'ejecucion': env['adt.papeleta.sat.ejecucion']._tomar()}

    def _ejecucion(self, env, ejecucion_id):
        return env['adt.papeleta.sat.ejecucion'].browse(ejecucion_id).exists()

    @http.route('/api/papeletas/sat/ejecuciones/<int:ejecucion_id>/latido', type='json', auth='none',
                methods=['POST'], csrf=False)
    def latido(self, ejecucion_id, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return {'ok': False, 'codigo': 401, 'error': 'token inválido'}
        ejecucion = self._ejecucion(env, ejecucion_id)
        if not ejecucion:
            # Borrada en Odoo: que el agente se detenga.
            return {'ok': True, 'cancelar': True}
        return dict(ejecucion._latido(request.jsonrequest or {}), ok=True)

    @http.route('/api/papeletas/sat/ejecuciones/<int:ejecucion_id>/finalizar', type='json', auth='none',
                methods=['POST'], csrf=False)
    def finalizar(self, ejecucion_id, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return {'ok': False, 'codigo': 401, 'error': 'token inválido'}
        ejecucion = self._ejecucion(env, ejecucion_id)
        if not ejecucion:
            return {'ok': True, 'estado': None}
        return {'ok': True, 'estado': ejecucion._finalizar(request.jsonrequest or {})}
