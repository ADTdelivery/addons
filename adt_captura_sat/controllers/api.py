# -*- coding: utf-8 -*-
"""API para el agente de capturas SAT (contenedor Docker independiente).

    POST /api/capturas/sat/import   cuerpo JSON: el resultado de sat_capturas.py para una placa
                                    (más "metadata": {"ejecucion_id", "vehicle_id"}) o
                                    {"resultados": [...]} con varias. Respuesta JSON-RPC (HTTP 200):
                                    {"result": {"ok": bool, ...}}. Si ok es false, reintentar.
    GET  /api/capturas/sat/placas   placas de la flota a consultar

    Modo agente (POST JSON-RPC):
    /api/capturas/sat/ejecuciones/tomar            -> {"ejecucion": {id, name, placas} | null}
    /api/capturas/sat/ejecuciones/<id>/latido      {procesadas, total, placa} -> {"cancelar": bool}
    /api/capturas/sat/ejecuciones/<id>/finalizar   {error, cancelada, archivo, resultados: [...]}

Autenticación: cabecera `X-SAT-Token: <token>` (o `Authorization: Bearer <token>`).
Token en Ajustes > Técnico > Parámetros del sistema > adt_captura_sat.token.
"""
import hmac
import json

from odoo import SUPERUSER_ID, http
from odoo.http import Response, request

from odoo.addons.adt_papeletas.models.papeleta_sat_programa import _placas_de

from ..models.captura_sat import PARAM_TOKEN

NO_AUTORIZADO = {'ok': False, 'codigo': 401, 'error': 'token inválido'}


class CapturasSatAPI(http.Controller):

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

    @http.route('/api/capturas/sat/import', type='json', auth='none', methods=['POST'], csrf=False)
    def importar(self, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return NO_AUTORIZADO
        body = request.jsonrequest or {}
        consultas = body.get('resultados') if isinstance(body.get('resultados'), list) else [body]
        if not all(isinstance(c, dict) and c.get('placa') for c in consultas):
            return {'ok': False, 'codigo': 400, 'error': 'cada consulta debe tener "placa"'}
        Consulta = env['adt.captura.sat.consulta']
        detalle = []
        for datos in consultas:
            consulta = Consulta.registrar(datos)
            detalle.append({
                'placa': consulta.placa, 'consulta_id': consulta.id, 'estado': consulta.state,
                'resultado': consulta.resultado, 'vehiculo': consulta.vehicle_id.id or None,
                'nuevas': consulta.nuevas, 'levantadas': consulta.levantadas, 'error': consulta.error or None,
            })
        return {'ok': not any(d['estado'] == 'error' for d in detalle), 'consultas': detalle}

    @http.route('/api/capturas/sat/placas', type='http', auth='none', methods=['GET'], csrf=False)
    def placas(self, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return Response(json.dumps({'ok': False, 'error': 'token inválido'}), status=401,
                            content_type='application/json; charset=utf-8')
        placas = _placas_de(env['fleet.vehicle'].search([('license_plate', '!=', False)]))
        return Response(json.dumps({'ok': True, 'total': len(placas), 'placas': placas}, ensure_ascii=False),
                        content_type='application/json; charset=utf-8')

    # ------------------------------------------------------------ modo agente
    @http.route('/api/capturas/sat/ejecuciones/tomar', type='json', auth='none', methods=['POST'], csrf=False)
    def tomar(self, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return NO_AUTORIZADO
        return {'ok': True, 'ejecucion': env['adt.captura.sat.ejecucion']._tomar()}

    @http.route('/api/capturas/sat/ejecuciones/<int:ejecucion_id>/latido', type='json', auth='none',
                methods=['POST'], csrf=False)
    def latido(self, ejecucion_id, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return NO_AUTORIZADO
        ejecucion = env['adt.captura.sat.ejecucion'].browse(ejecucion_id).exists()
        if not ejecucion:
            return {'ok': True, 'cancelar': True}
        return dict(ejecucion._latido(request.jsonrequest or {}), ok=True)

    @http.route('/api/capturas/sat/ejecuciones/<int:ejecucion_id>/finalizar', type='json', auth='none',
                methods=['POST'], csrf=False)
    def finalizar(self, ejecucion_id, **kwargs):
        env = self._env()
        if not self._autorizado(env):
            return NO_AUTORIZADO
        ejecucion = env['adt.captura.sat.ejecucion'].browse(ejecucion_id).exists()
        if not ejecucion:
            return {'ok': True, 'estado': None}
        return {'ok': True, 'estado': ejecucion._finalizar(request.jsonrequest or {})}
