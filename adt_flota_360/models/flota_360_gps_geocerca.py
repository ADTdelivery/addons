# -*- coding: utf-8 -*-
"""Geocercas del monitoreo GPS (Flota 360).

Se programan en Odoo (círculo o polígono dibujado en el mapa) y se publican en
Traccar para verlas también allí. La entrada/salida la detecta Odoo con cada
posición nueva (webhook de Traccar o sincronización), así no hace falta asignar
cada geocerca a cada dispositivo en Traccar. Las geocercas que ya existían en
Traccar se importan con las alertas apagadas.

Formato de Traccar (WKT con latitud primero):
    CIRCLE (lat lon, radio_m)
    POLYGON ((lat lon, lat lon, ..., lat lon))
"""
import json
import logging
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

RADIO_TIERRA_M = 6371000.0
_NUM = r'(-?\d+(?:\.\d+)?)'
_CIRCULO_RE = re.compile(r'^\s*CIRCLE\s*\(\s*%s\s+%s\s*,\s*%s\s*\)\s*$' % (_NUM, _NUM, _NUM), re.I)
_POLIGONO_RE = re.compile(r'^\s*POLYGON\s*\(\(\s*(.+?)\s*\)\)\s*$', re.I)


def distancia_m(lat1, lon1, lat2, lon2):
    """Distancia en metros entre dos coordenadas (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(a))


def punto_en_poligono(lat, lon, puntos):
    """Ray casting con la longitud como x y la latitud como y. puntos: [[lat, lon], ...]."""
    dentro = False
    n = len(puntos)
    j = n - 1
    for i in range(n):
        yi, xi = puntos[i]
        yj, xj = puntos[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            dentro = not dentro
        j = i
    return dentro


def wkt_a_geometria(area):
    """Área WKT de Traccar → dict(tipo, latitud, longitud, radio, puntos) o None si no se reconoce."""
    m = _CIRCULO_RE.match(area or '')
    if m:
        return {'tipo': 'circulo', 'latitud': float(m.group(1)), 'longitud': float(m.group(2)),
                'radio': float(m.group(3)), 'puntos': []}
    m = _POLIGONO_RE.match(area or '')
    if m:
        puntos = []
        for par in m.group(1).split(','):
            partes = par.split()
            if len(partes) >= 2:
                puntos.append([float(partes[0]), float(partes[1])])
        if len(puntos) > 3 and puntos[0] == puntos[-1]:
            puntos = puntos[:-1]
        if len(puntos) >= 3:
            lat = sum(p[0] for p in puntos) / len(puntos)
            lon = sum(p[1] for p in puntos) / len(puntos)
            return {'tipo': 'poligono', 'latitud': lat, 'longitud': lon, 'radio': 0.0, 'puntos': puntos}
    return None


def geometria_a_wkt(tipo, latitud, longitud, radio, puntos):
    if tipo == 'circulo':
        return 'CIRCLE (%s %s, %s)' % (latitud, longitud, round(radio or 0, 1))
    anillo = list(puntos) + [puntos[0]]
    return 'POLYGON ((%s))' % ', '.join('%s %s' % (p[0], p[1]) for p in anillo)


class AdtFlota360GpsGeocerca(models.Model):
    _name = 'adt.flota360.gps.geocerca'
    _description = 'Flota 360: geocerca del monitoreo GPS'
    _order = 'name'

    name = fields.Char('Nombre', required=True)
    active = fields.Boolean(default=True)
    descripcion = fields.Char('Descripción')
    color = fields.Char('Color', default='#d9480f')
    tipo = fields.Selection([('circulo', 'Círculo'), ('poligono', 'Polígono')], 'Forma', required=True,
                            default='circulo')
    latitud = fields.Float('Latitud del centro', digits=(10, 7))
    longitud = fields.Float('Longitud del centro', digits=(10, 7))
    radio = fields.Float('Radio (m)', default=200.0)
    puntos = fields.Text('Vértices (JSON [[lat, lon], ...])')
    alertar_entrada = fields.Boolean('Alertar al entrar', default=True)
    alertar_salida = fields.Boolean('Alertar al salir', default=True)
    alcance = fields.Selection([('todos', 'Todos los dispositivos'), ('seleccion', 'Solo los elegidos')],
                               'Aplica a', default='todos', required=True)
    dispositivo_ids = fields.Many2many('adt.flota360.gps.dispositivo', 'adt_flota360_gps_geocerca_disp_rel',
                                       'geocerca_id', 'dispositivo_id', 'Dispositivos')
    publicar_traccar = fields.Boolean('Publicar en Traccar', default=True)
    traccar_id = fields.Integer('ID en Traccar', index=True, copy=False)
    traccar_error = fields.Char('Error al publicar en Traccar', copy=False)

    @api.constrains('tipo', 'latitud', 'longitud', 'radio', 'puntos')
    def _check_geometria(self):
        for g in self:
            if g.tipo == 'circulo':
                if not (-90 <= g.latitud <= 90 and -180 <= g.longitud <= 180) or (not g.latitud and not g.longitud):
                    raise ValidationError(_('Marca el centro de la geocerca «%s» en el mapa.') % g.name)
                if not 10 <= (g.radio or 0) <= 100000:
                    raise ValidationError(_('El radio de «%s» debe estar entre 10 m y 100 km.') % g.name)
            elif len(g._puntos()) < 3:
                raise ValidationError(_('El polígono «%s» necesita al menos 3 puntos.') % g.name)

    def _puntos(self):
        self.ensure_one()
        try:
            puntos = json.loads(self.puntos or '[]')
        except ValueError:
            return []
        return [[float(p[0]), float(p[1])] for p in puntos if isinstance(p, (list, tuple)) and len(p) >= 2]

    def _geometria(self):
        """Datos planos para evaluar sin volver a leer el registro en cada posición."""
        self.ensure_one()
        return {'id': self.id, 'name': self.name, 'tipo': self.tipo, 'latitud': self.latitud,
                'longitud': self.longitud, 'radio': self.radio, 'puntos': self._puntos(),
                'entrada': self.alertar_entrada, 'salida': self.alertar_salida,
                'todos': self.alcance == 'todos', 'dispositivos': set(self.dispositivo_ids.ids)}

    @staticmethod
    def contiene(geo, lat, lon):
        if geo['tipo'] == 'circulo':
            return distancia_m(geo['latitud'], geo['longitud'], lat, lon) <= geo['radio']
        return punto_en_poligono(lat, lon, geo['puntos'])

    def _area_wkt(self):
        self.ensure_one()
        return geometria_a_wkt(self.tipo, self.latitud, self.longitud, self.radio, self._puntos())

    # --- Traccar ------------------------------------------------------

    def _publicar_traccar(self, traccar=None):
        """Crea o actualiza la geocerca en Traccar. Un fallo no impide guardarla en Odoo:
        queda en traccar_error para reintentar."""
        from .flota_360_gps import Traccar
        from odoo.exceptions import UserError
        for g in self:
            if not g.publicar_traccar:
                continue
            datos = {'name': g.name, 'description': g.descripcion or '', 'area': g._area_wkt(),
                     'attributes': {'color': g.color or '#d9480f'}}
            try:
                with (traccar or Traccar(self.env)) as t:
                    if g.traccar_id:
                        datos['id'] = g.traccar_id
                        t.enviar('PUT', '/api/geofences/%s' % g.traccar_id, datos)
                    else:
                        g.traccar_id = t.enviar('POST', '/api/geofences', datos).get('id') or 0
                g.traccar_error = False
            except UserError as exc:
                g.traccar_error = exc.args[0][:250]
                _logger.warning('[Flota 360][GPS] Geocerca %s no publicada en Traccar: %s', g.name, exc.args[0])

    def _quitar_traccar(self):
        from .flota_360_gps import Traccar
        from odoo.exceptions import UserError
        for g in self.filtered('traccar_id'):
            try:
                with Traccar(self.env) as t:
                    t.enviar('DELETE', '/api/geofences/%s' % g.traccar_id)
            except UserError as exc:
                _logger.warning('[Flota 360][GPS] Geocerca %s no se pudo quitar de Traccar: %s', g.name, exc.args[0])

    @api.model
    def _importar_traccar(self, geofences):
        """Geocercas de Traccar que Odoo aún no conoce: se crean con las alertas apagadas."""
        conocidas = set(self.with_context(active_test=False).search([('traccar_id', '!=', 0)]).mapped('traccar_id'))
        nuevas = 0
        for gf in geofences:
            if not gf.get('id') or gf['id'] in conocidas:
                continue
            geo = wkt_a_geometria(gf.get('area'))
            if not geo:
                continue
            self.create({
                'name': gf.get('name') or _('Geocerca %s') % gf['id'], 'descripcion': gf.get('description') or False,
                'tipo': geo['tipo'], 'latitud': geo['latitud'], 'longitud': geo['longitud'],
                'radio': geo['radio'] or 200.0, 'puntos': json.dumps(geo['puntos']) if geo['puntos'] else False,
                'color': (gf.get('attributes') or {}).get('color') or '#1c7ed6',
                'alertar_entrada': False, 'alertar_salida': False, 'traccar_id': gf['id'],
            })
            nuevas += 1
        return nuevas
