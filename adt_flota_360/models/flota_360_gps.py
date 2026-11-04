# -*- coding: utf-8 -*-
"""Monitoreo GPS (vista 7 de Flota 360, acción JS: adt_flota_360_gps).

Cada dispositivo de Traccar queda registrado en `adt.flota360.gps.dispositivo`,
esté o no relacionado con un vehículo de Odoo: así se «escuchan» todos y se
sabe cuáles dejan de reportar aunque su placa no exista en la flota.

Tiempo real, en tres capas:
1. Webhook: Traccar reenvía a Odoo cada evento (desconexión, conexión, alarma) y,
   si se activa, cada posición (ver controllers/flota_360_gps_webhook.py). Se
   procesa al instante.
2. Sincronización: el cron lee Traccar cada minuto (/api/devices y /api/positions)
   como respaldo y para los umbrales por tiempo («sin reportar» no es un evento
   de Traccar: se deduce de los minutos sin datos).
3. Bus de Odoo: cada evento de alerta se envía al momento a los usuarios
   (bus.bus, canal del partner); el servicio JS adt_flota_360_gps_alertas lo
   muestra como notificación del navegador y dentro de Odoo.

Relación con Odoo, por placa: el nombre del dispositivo suele traer texto pegado
a la placa («XYAZ12 - nuevo», «ABC-123 (repuesto)»). Se prueban, en orden, el IMEI
(si el vehículo lo tiene), la placa exacta, la placa sin las palabras de ruido
configurables, fragmentos con forma de placa y, por último, una placa de Odoo
contenida en el nombre. Si varias placas coinciden no se relaciona («ambiguo»).
Una relación hecha a mano nunca la cambia la sincronización. Los dispositivos sin
vehículo pueden crearlo en Odoo (a pedido o automáticamente).

Geocercas: ver flota_360_gps_geocerca.py. La entrada/salida se evalúa con cada
posición nueva.
"""
import json
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .flota_360 import placa_valida
from .flota_360_gps_geocerca import AdtFlota360GpsGeocerca, distancia_m

_logger = logging.getLogger(__name__)

LOG = '[Flota 360][GPS]'
TRACCAR_TIMEOUT = 25  # segundos
GRUPO_USUARIO = 'fleet.fleet_group_user'
GRUPO_MANAGER = 'fleet.fleet_group_manager'
BUS_TIPO = 'adt_flota_360.gps'

PARAM = 'adt_flota_360.gps_%s'
MINUTOS_DEMORA = 20       # desde aquí el reporte está demorado
MINUTOS_SIN_REPORTE = 60  # desde aquí el vehículo «no reporta» y se alerta
# Texto que suele ir pegado a la placa en el nombre del dispositivo de Traccar.
PALABRAS_RUIDO = (
    'NUEVO NUEVA NEW VIEJO VIEJA OLD ANTIGUO ANTIGUA ANTERIOR ACTUAL PRUEBA PRUEBAS TEST DEMO '
    'GPS TRACKER EQUIPO MOTO MOTOS AUTO CARRO VEHICULO REPUESTO CAMBIO CAMBIADO BAJA RETIRADO '
    'RETIRADA COPIA BIS TEMP TEMPORAL REINSTALADO INSTALADO OK PLACA SINPLACA'
)
DIAS_EVENTOS = 60  # se conserva el historial de eventos de los últimos N días
MAX_ALERTAS = 50
MAX_DIAS_RECORRIDO = 7
MAX_PUNTOS_RECORRIDO = 3000
NUDO_KMH = 1.852
WEBHOOK_ACTIVO_MIN = 15  # sin llamadas del webhook en este tiempo: se considera inactivo

ESTADOS = [
    ('reportando', 'Reportando'),
    ('demorado', 'Reporte demorado'),
    ('sin_reporte', 'Sin reportar'),
    ('nunca', 'Nunca reportó'),
    ('deshabilitado', 'Deshabilitado'),
]
NIVEL_ESTADO = {'reportando': 'ok', 'demorado': 'atencion', 'sin_reporte': 'critico', 'nunca': 'critico',
                'deshabilitado': 'neutral'}
REPORTA = ('reportando', 'demorado')
NO_REPORTA = ('sin_reporte', 'nunca')
METODOS = [
    ('imei', 'IMEI del vehículo'),
    ('exacta', 'Placa exacta'),
    ('limpieza', 'Placa sin texto extra'),
    ('patron', 'Placa dentro del nombre'),
    ('contenida', 'Placa de Odoo contenida en el nombre'),
    ('manual', 'Relacionado a mano'),
    ('creado', 'Vehículo creado desde Traccar'),
    ('ambiguo', 'Varias placas coinciden'),
    ('sin_vinculo', 'Sin vehículo en Odoo'),
]
TIPOS_EVENTO = [
    ('sin_reporte', 'Dejó de reportar'),
    ('volvio', 'Volvió a reportar'),
    ('desconectado', 'Se desconectó de Traccar'),
    ('alarma', 'Alarma del equipo'),
    ('geocerca_entrada', 'Entró a una geocerca'),
    ('geocerca_salida', 'Salió de una geocerca'),
    ('nuevo', 'Nuevo en Traccar'),
    ('creado', 'Vehículo creado en Odoo'),
    ('deshabilitado', 'Deshabilitado en Traccar'),
    ('eliminado', 'Eliminado de Traccar'),
]
# Eventos que pueden avisar al usuario (se eligen en la configuración).
ALERTABLES = ('sin_reporte', 'volvio', 'desconectado', 'alarma', 'geocerca_entrada', 'geocerca_salida')
NIVEL_EVENTO = {'sin_reporte': 'critico', 'alarma': 'critico', 'desconectado': 'atencion',
                'geocerca_entrada': 'info', 'geocerca_salida': 'atencion', 'volvio': 'ok'}

# Alarmas de Traccar (atributo «alarm» de la posición o del evento).
ALARMAS = {
    'sos': 'Botón de pánico (SOS)',
    'powercut': 'Corte de energía: el GPS perdió la alimentación del vehículo (posible desconexión)',
    'poweroff': 'El equipo GPS fue apagado',
    'removing': 'Alarma de retiro del equipo',
    'tampering': 'Alarma de manipulación del equipo',
    'jamming': 'Posible inhibidor de señal (jammer)',
    'gpsantennacut': 'Antena GPS desconectada',
    'lowpower': 'Alimentación del vehículo baja',
    'lowbattery': 'Batería interna del GPS baja',
    'overspeed': 'Exceso de velocidad',
    'accident': 'Posible accidente',
    'movement': 'Movimiento no autorizado',
    'vibration': 'Vibración',
}
ALARMAS_DEFECTO = 'sos powercut poweroff removing tampering jamming gpsantennacut accident movement'
SIN_COMUNICACION = 'Sin comunicación: revisar chip (saldo o datos), cobertura o si el equipo fue retirado'


# ----------------------------------------------------------------------
# Conexión con Traccar
# ----------------------------------------------------------------------

class Traccar(object):
    """Sesión con la API de Traccar como el administrador de Ajustes → Traccar
    (adt_traccar.url / .email / .password). Uso: `with Traccar(env) as t: t.leer(...)`.
    Se puede anidar: el `with` interno reutiliza la sesión abierta."""

    def __init__(self, env):
        ICP = env['ir.config_parameter'].sudo()
        self.url = (ICP.get_param('adt_traccar.url') or '').rstrip('/')
        self._email = ICP.get_param('adt_traccar.email') or ''
        self._password = ICP.get_param('adt_traccar.password') or ''
        self.sesion = None
        self._nivel = 0

    def __enter__(self):
        self._nivel += 1
        if self.sesion:
            return self
        if not self.url or not self._email or not self._password:
            self._nivel -= 1
            raise UserError(_('Traccar no está configurado: completa URL, email y password en Ajustes → Traccar.'))
        self.sesion = requests.Session()
        try:
            resp = self.sesion.post('%s/api/session' % self.url, data={'email': self._email, 'password': self._password},
                                    timeout=TRACCAR_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            self._cerrar()
            raise UserError(_('No se pudo conectar con Traccar: %s') % exc)
        if resp.status_code != 200:
            self._cerrar()
            raise UserError(_('Traccar rechazó el inicio de sesión (HTTP %s).') % resp.status_code)
        return self

    def __exit__(self, *exc):
        self._nivel -= 1
        if self._nivel <= 0:
            self._cerrar()
        return False

    def _cerrar(self):
        if self.sesion:
            self.sesion.close()
        self.sesion = None
        self._nivel = 0

    def leer(self, ruta, params=None, obligatorio=True):
        try:
            r = self.sesion.get(self.url + ruta, params=params, headers={'Accept': 'application/json'},
                                timeout=TRACCAR_TIMEOUT)
            if r.status_code != 200:
                if obligatorio:
                    raise UserError(_('Traccar devolvió HTTP %s en %s.') % (r.status_code, ruta))
                return []
            return r.json()
        except requests.exceptions.RequestException as exc:
            raise UserError(_('No se pudo conectar con Traccar: %s') % exc)
        except ValueError:
            raise UserError(_('Traccar devolvió una respuesta que no es JSON en %s.') % ruta)

    def leer_lista(self, ruta, params=None, obligatorio=True):
        datos = self.leer(ruta, params, obligatorio)
        return datos if isinstance(datos, list) else []

    def enviar(self, metodo, ruta, datos=None):
        try:
            r = self.sesion.request(metodo, self.url + ruta, json=datos, timeout=TRACCAR_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise UserError(_('No se pudo conectar con Traccar: %s') % exc)
        if r.status_code not in (200, 201, 204):
            raise UserError(_('Traccar devolvió HTTP %s en %s %s: %.200s') % (r.status_code, metodo, ruta, r.text))
        try:
            return r.json() if r.text else {}
        except ValueError:
            return {}


def iso_traccar(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


# ----------------------------------------------------------------------
# Placas: limpieza y relación con los vehículos de Odoo
# ----------------------------------------------------------------------

def _sin_acentos(texto):
    return unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii')


def tokens_placa(texto):
    """Bloques de letras/números en mayúscula: «abc-123 Nuevo» → ['ABC', '123', 'NUEVO']."""
    return re.findall(r'[A-Z0-9]+', _sin_acentos(texto).upper())


def palabras_ruido(texto):
    return {p for p in tokens_placa(texto) if p}


def _quitar_ruido_pegado(token, ruido):
    """«XYAZ12NUEVO» → «XYAZ12»: quita palabras de ruido pegadas al inicio o al final,
    siempre que queden al menos 5 caracteres (lo mínimo de una placa)."""
    cambiado = True
    while cambiado:
        cambiado = False
        for palabra in sorted(ruido, key=len, reverse=True):
            if len(palabra) < 3 or len(token) - len(palabra) < 5:
                continue
            if token.endswith(palabra):
                token, cambiado = token[:-len(palabra)], True
                break
            if token.startswith(palabra):
                token, cambiado = token[len(palabra):], True
                break
    return token


def con_forma_de_placa(clave):
    return bool(clave) and 5 <= len(clave) <= 7 and bool(re.search(r'\d', clave)) and bool(re.search(r'[A-Z]', clave))


def claves_placa(texto, ruido):
    """Claves con las que se puede reconocer la placa escrita en `texto`, de la más fiel
    a la más permisiva: [(método, clave)].

    «XYAZ12 - nuevo» → [('exacta', 'XYAZ12NUEVO'), ('limpieza', 'XYAZ12')]
    «Moto 1234-AB juan» → [..., ('limpieza', '1234ABJUAN'), ('patron', '1234AB'), ...]
    """
    tokens = tokens_placa(texto)
    res, vistas = [], set()

    def agregar(metodo, clave):
        if len(clave) >= 4 and clave not in vistas:
            vistas.add(clave)
            res.append((metodo, clave))

    agregar('exacta', ''.join(tokens))
    limpios = [t for t in (_quitar_ruido_pegado(t, ruido) for t in tokens if t not in ruido) if t]
    agregar('limpieza', ''.join(limpios))
    # Fragmentos con forma de placa: 1 a 3 bloques seguidos, de 5 a 7 caracteres con letras y números.
    for i in range(len(limpios)):
        for j in range(i + 1, min(i + 3, len(limpios)) + 1):
            clave = ''.join(limpios[i:j])
            if con_forma_de_placa(clave):
                agregar('patron', clave)
    return res


class IndicePlacas(object):
    """Vehículos de Odoo indexados por sus claves de placa (y por IMEI) para relacionar
    cada dispositivo de Traccar en una sola pasada."""

    def __init__(self, vehiculos, ruido):
        """vehiculos: iterable de (id, placa, imei)."""
        self.ruido = ruido
        self.por_clave = {}
        self.por_imei = {}
        self.placas = {}
        for vid, placa, imei in vehiculos:
            self.agregar(vid, placa, imei)

    def agregar(self, vid, placa, imei=None):
        if imei and imei.strip():
            self.por_imei.setdefault(imei.strip(), set()).add(vid)
        if not placa_valida(placa):
            return
        self.placas[vid] = placa
        for metodo, clave in claves_placa(placa, self.ruido):
            if metodo in ('exacta', 'limpieza'):
                self.por_clave.setdefault(clave, set()).add(vid)

    def _nota(self, vids):
        return 'Coinciden: %s' % ', '.join(sorted(self.placas.get(v, str(v)) for v in vids))

    def buscar(self, nombre, imei=None):
        """→ (vehicle_id o False, método, clave, nota)."""
        vids = self.por_imei.get((imei or '').strip()) if imei else None
        if vids and len(vids) == 1:
            return next(iter(vids)), 'imei', (imei or '').strip(), ''

        claves = claves_placa(nombre, self.ruido)
        for metodo, clave in claves:
            vids = self.por_clave.get(clave)
            if not vids:
                continue
            if len(vids) == 1:
                return next(iter(vids)), metodo, clave, ''
            return False, 'ambiguo', clave, self._nota(vids)

        # Una placa de Odoo escrita dentro del nombre (con texto pegado que no es ruido conocido).
        textos = [c for m, c in claves if m in ('exacta', 'limpieza')]
        mejor, encontrados = 0, set()
        for clave, vids in self.por_clave.items():
            if len(clave) < 5 or len(clave) < mejor or not any(clave in t for t in textos):
                continue
            if len(clave) > mejor:
                mejor, encontrados = len(clave), set()
            encontrados |= vids
        if len(encontrados) == 1:
            vid = next(iter(encontrados))
            return vid, 'contenida', next(c for c, v in self.por_clave.items() if vid in v and len(c) == mejor), ''
        if encontrados:
            return False, 'ambiguo', '', self._nota(encontrados)
        limpia = next((c for m, c in claves if m == 'patron'), None) or next((c for m, c in claves if m == 'limpieza'), '')
        return False, 'sin_vinculo', limpia, ''


# ----------------------------------------------------------------------
# Estado del dispositivo y motivo
# ----------------------------------------------------------------------

def fecha_traccar(valor):
    """ISO 8601 de Traccar → datetime naive en UTC (o None)."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _numero(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def alarmas_de(texto):
    return [a.strip().lower() for a in str(texto or '').split(',') if a.strip()]


def hechos_posicion(pos):
    """Lo que la última posición dice sobre una caída, del más al menos determinante."""
    if not pos:
        return []
    attrs = pos.get('attributes') or {}
    hechos = []
    for alarma in alarmas_de(attrs.get('alarm')):
        texto = ALARMAS.get(alarma)
        if texto and texto not in hechos and alarma not in ('overspeed', 'vibration', 'movement'):
            hechos.append(texto)
    voltaje = _numero(attrs.get('power'))
    if voltaje is not None:
        if voltaje < 1:
            hechos.append('Sin alimentación del vehículo en el último reporte (0 V)')
        elif voltaje < 11.5:
            hechos.append('Voltaje del vehículo bajo en el último reporte (%.1f V)' % voltaje)
    bateria = _numero(attrs.get('batteryLevel'))
    interna = _numero(attrs.get('battery'))
    if bateria is not None and bateria < 20:
        hechos.append('Batería interna del GPS baja (%.0f %%)' % bateria)
    elif bateria is None and interna is not None and 0 < interna < 3.5:
        hechos.append('Batería interna del GPS baja (%.2f V)' % interna)
    if pos.get('valid') is False or pos.get('outdated'):
        hechos.append('Sin señal GPS en el último reporte (antena obstruida o vehículo bajo techo)')
    if attrs.get('ignition') is False:
        hechos.append('Vehículo apagado en el último reporte (algunos equipos dejan de transmitir con el motor apagado)')
    return hechos


def diagnosticar(device, pos, ahora, min_demora=MINUTOS_DEMORA, min_sin=MINUTOS_SIN_REPORTE):
    """→ dict(estado, ultimo, minutos, motivo, detalle) de un dispositivo de Traccar."""
    pos = pos or {}
    fechas = [f for f in (fecha_traccar(device.get('lastUpdate')), fecha_traccar(pos.get('serverTime'))) if f]
    ultimo = max(fechas) if fechas else None
    minutos = max(0, int((ahora - ultimo).total_seconds() // 60)) if ultimo else None
    hechos = hechos_posicion(pos)
    detalle = list(hechos)

    if device.get('disabled'):
        estado, motivo = 'deshabilitado', 'Deshabilitado en Traccar: no se monitorea'
    elif not ultimo:
        estado = 'nunca'
        motivo = 'Nunca envió datos: revisar instalación, IMEI registrado y configuración del servidor en el equipo'
    elif minutos < min_demora:
        estado = 'reportando'
        motivo = 'Comunica, pero sin señal GPS válida' if (pos.get('valid') is False or pos.get('outdated')) else 'Reportando'
    elif minutos < min_sin:
        estado = 'demorado'
        motivo = 'Reporte demorado' + (': ' + hechos[0][0].lower() + hechos[0][1:] if hechos else '')
    else:
        estado = 'sin_reporte'
        motivo = hechos[0] if hechos else SIN_COMUNICACION
        if hechos:
            detalle.append(SIN_COMUNICACION)
    if device.get('status'):
        detalle.append('Estado de la conexión en Traccar: %s' % {
            'online': 'en línea', 'offline': 'desconectado', 'unknown': 'desconocido'}.get(device['status'], device['status']))
    return {'estado': estado, 'ultimo': ultimo, 'minutos': minutos, 'motivo': motivo, 'detalle': detalle}


def valores_posicion(pos):
    """Campos del dispositivo que salen de la última posición."""
    if not pos:
        return {}
    attrs = pos.get('attributes') or {}
    ignicion = attrs.get('ignition')
    return {
        'latitud': pos.get('latitude') or 0.0,
        'longitud': pos.get('longitude') or 0.0,
        'velocidad_kmh': round((pos.get('speed') or 0.0) * NUDO_KMH, 1),
        'direccion': pos.get('address') or False,
        'ignicion': 'on' if ignicion is True else ('off' if ignicion is False else False),
        'bateria': _numero(attrs.get('batteryLevel')) or 0.0,
        'voltaje': _numero(attrs.get('power')) or 0.0,
        'alarma': attrs.get('alarm') or False,
        'posicion_valida': bool(pos.get('valid')) and not pos.get('outdated'),
        'satelites': int(_numero(attrs.get('sat')) or 0),
        'km_total': round((_numero(attrs.get('totalDistance')) or 0.0) / 1000.0, 1),
        'protocolo': pos.get('protocol') or False,
        'ultima_posicion': fecha_traccar(pos.get('fixTime')) or False,
        'atributos': json.dumps(attrs, sort_keys=True, ensure_ascii=False) if attrs else False,
    }


def evaluar_geocercas(estado_json, disp_id, lat, lon, valida, geos):
    """Estado de las geocercas de un dispositivo tras una posición nueva.

    estado_json guarda {"evaluadas": [ids], "dentro": [ids]}: una geocerca que el
    dispositivo nunca evaluó solo se inicializa (sin evento), así crear una geocerca
    o un dispositivo nuevo no dispara una ola de alertas.
    → (nuevo estado_json, [(geo, 'entrada'|'salida')])."""
    try:
        estado = json.loads(estado_json or '{}')
    except ValueError:
        estado = {}
    evaluadas, dentro = set(estado.get('evaluadas') or []), set(estado.get('dentro') or [])
    if not valida or (not lat and not lon):
        return estado_json or False, []
    transiciones = []
    vigentes = set()
    for geo in geos:
        if not geo['todos'] and disp_id not in geo['dispositivos']:
            continue
        vigentes.add(geo['id'])
        esta = AdtFlota360GpsGeocerca.contiene(geo, lat, lon)
        if geo['id'] in evaluadas:
            if esta and geo['id'] not in dentro:
                transiciones.append((geo, 'entrada'))
            elif not esta and geo['id'] in dentro:
                transiciones.append((geo, 'salida'))
        evaluadas.add(geo['id'])
        if esta:
            dentro.add(geo['id'])
        else:
            dentro.discard(geo['id'])
    nuevo = {'evaluadas': sorted(evaluadas & vigentes), 'dentro': sorted(dentro & vigentes)}
    return json.dumps(nuevo), transiciones


def _tiempo(minutos):
    if minutos is None:
        return ''
    if minutos < 60:
        return '%s min' % minutos
    if minutos < 60 * 48:
        h, m = divmod(minutos, 60)
        return '%s h %s min' % (h, m) if m else '%s h' % h
    return '%s días' % (minutos // (60 * 24))


# ----------------------------------------------------------------------
# Modelos
# ----------------------------------------------------------------------

class AdtFlota360GpsDispositivo(models.Model):
    _name = 'adt.flota360.gps.dispositivo'
    _description = 'Flota 360: dispositivo GPS de Traccar monitoreado'
    _order = 'name'

    name = fields.Char('Nombre en Traccar', required=True, index=True)
    traccar_id = fields.Integer('ID en Traccar', required=True, index=True)
    imei = fields.Char('IMEI (uniqueId)', index=True)
    active = fields.Boolean(default=True, help='Se archiva cuando el dispositivo ya no existe en Traccar.')

    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehículo', ondelete='set null', index=True)
    placa_detectada = fields.Char('Placa detectada', help='Placa limpia que se usó para buscar el vehículo.')
    vinculo_metodo = fields.Selection(METODOS, 'Relación', default='sin_vinculo')
    vinculo_manual = fields.Boolean(
        'Relación manual', help='La relación (o la falta de ella) se fijó a mano: la sincronización no la cambia.')
    vinculo_nota = fields.Char('Nota de la relación')

    estado = fields.Selection(ESTADOS, 'Estado', default='nunca', index=True)
    estado_desde = fields.Datetime('En este estado desde')
    motivo = fields.Char('Motivo')
    motivo_detalle = fields.Text('Diagnóstico')
    ultimo_reporte = fields.Datetime('Último reporte')
    sincronizado = fields.Datetime('Sincronizado')

    traccar_status = fields.Selection(
        [('online', 'En línea'), ('offline', 'Desconectado'), ('unknown', 'Desconocido')], 'Conexión en Traccar')
    deshabilitado = fields.Boolean('Deshabilitado en Traccar')
    grupo = fields.Char('Grupo en Traccar')
    telefono = fields.Char('Teléfono / chip')
    modelo_equipo = fields.Char('Modelo del equipo')
    contacto = fields.Char('Contacto')
    categoria = fields.Char('Categoría')

    ultima_posicion = fields.Datetime('Fecha de la última posición')
    latitud = fields.Float('Latitud', digits=(10, 6))
    longitud = fields.Float('Longitud', digits=(10, 6))
    velocidad_kmh = fields.Float('Velocidad (km/h)')
    direccion = fields.Char('Dirección')
    ignicion = fields.Selection([('on', 'Encendido'), ('off', 'Apagado')], 'Ignición')
    bateria = fields.Float('Batería interna (%)')
    voltaje = fields.Float('Voltaje del vehículo (V)')
    alarma = fields.Char('Última alarma')
    posicion_valida = fields.Boolean('Posición GPS válida')
    satelites = fields.Integer('Satélites')
    km_total = fields.Float('Km (odómetro Traccar)')
    protocolo = fields.Char('Protocolo')
    atributos = fields.Text('Atributos de la última posición (JSON)')
    geocercas_estado = fields.Text('Geocercas (estado interno)')

    evento_ids = fields.One2many('adt.flota360.gps.evento', 'dispositivo_id', 'Eventos')

    _sql_constraints = [
        ('traccar_id_uniq', 'unique(traccar_id)', 'El dispositivo de Traccar ya está registrado.'),
    ]

    # --- Configuración -------------------------------------------------

    @api.model
    def _config(self):
        ICP = self.env['ir.config_parameter'].sudo()

        def entero(clave, defecto):
            try:
                return max(1, int(ICP.get_param(PARAM % clave) or defecto))
            except ValueError:
                return defecto

        def texto(clave, defecto):
            valor = ICP.get_param(PARAM % clave)
            return defecto if valor is None or valor is False else valor

        demora = entero('minutos_demora', MINUTOS_DEMORA)
        sin = max(entero('minutos_sin_reporte', MINUTOS_SIN_REPORTE), demora + 1)
        alertas = [a for a in texto('alertas', ' '.join(ALERTABLES)).split() if a in ALERTABLES]
        destinatarios = [int(u) for u in texto('destinatarios', '').split() if u.isdigit()]
        try:
            modelo_id = int(ICP.get_param(PARAM % 'modelo_id') or 0)
        except ValueError:
            modelo_id = 0
        return {
            'minutos_demora': demora, 'minutos_sin_reporte': sin,
            'palabras_ruido': texto('palabras_ruido', PALABRAS_RUIDO),
            'alertas': alertas,
            'alarmas': alarmas_de(texto('alarmas', ALARMAS_DEFECTO).replace(' ', ',')),
            'destinatarios': destinatarios,
            'crear_vehiculos': texto('crear_vehiculos', '0') == '1',
            'modelo_id': modelo_id,
        }

    # --- Sincronización completa (cron cada minuto) --------------------

    @api.model
    def _indice_placas(self, ruido):
        Vehicle = self.env['fleet.vehicle'].sudo()
        campos = ['license_plate'] + (['x_imei'] if 'x_imei' in Vehicle._fields else [])
        filas = Vehicle.search_read([], campos)
        return IndicePlacas(((f['id'], f['license_plate'], f.get('x_imei')) for f in filas), palabras_ruido(ruido))

    @api.model
    def _geocercas_activas(self):
        return [g._geometria() for g in self.env['adt.flota360.gps.geocerca'].sudo().search([])]

    @api.model
    def _cambios(self, rec, vals):
        """Solo los valores que cambian (evita escribir miles de filas en cada pasada)."""
        res = {}
        for campo, valor in vals.items():
            actual = rec[campo]
            if rec._fields[campo].type == 'many2one':
                actual = actual.id
            elif rec._fields[campo].type == 'float':
                actual = round(actual or 0.0, 6)
                valor = round(valor or 0.0, 6)
            if (actual or False) != (valor or False):
                res[campo] = valor
        return res

    @api.model
    def _contexto(self, ruido=None):
        """Lo que se precalcula una vez por pasada (índice de placas, geocercas, configuración)."""
        cfg = self._config()
        return {'cfg': cfg, 'indice': self._indice_placas(ruido or cfg['palabras_ruido']),
                'geocercas': self._geocercas_activas(), 'grupos': {}}

    def _aplicar(self, device, pos, ahora, ctx, alarma_evento=None):
        """Aplica a `self` (o crea, si `self` está vacío) lo que Traccar informa de un
        dispositivo. Lo usan la sincronización, el webhook y la vista en vivo.
        → (registro, [valores de eventos])."""
        cfg = ctx['cfg']
        diag = diagnosticar(device, pos, ahora, cfg['minutos_demora'], cfg['minutos_sin_reporte'])
        tid = device['id']
        vals = {
            'name': (device.get('name') or '').strip() or device.get('uniqueId') or str(tid),
            'traccar_id': tid,
            'imei': device.get('uniqueId') or False,
            'active': True,
            'estado': diag['estado'],
            'motivo': diag['motivo'],
            'motivo_detalle': '\n'.join(diag['detalle']) or False,
            'ultimo_reporte': diag['ultimo'] or False,
            'traccar_status': device.get('status') if device.get('status') in ('online', 'offline', 'unknown') else False,
            'deshabilitado': bool(device.get('disabled')),
            'telefono': device.get('phone') or False,
            'modelo_equipo': device.get('model') or False,
            'contacto': device.get('contact') or False,
            'categoria': device.get('category') or False,
        }
        if 'groupId' in device and ctx['grupos']:
            vals['grupo'] = ctx['grupos'].get(device.get('groupId')) or False
        vals.update(valores_posicion(pos))
        rec = self
        if not rec or not rec.vinculo_manual:
            vid, metodo, clave, nota = ctx['indice'].buscar(vals['name'], vals['imei'])
            if rec and rec.vinculo_metodo == 'creado' and rec.vehicle_id and not vid:
                vid, metodo = rec.vehicle_id.id, 'creado'  # el vehículo creado desde Traccar se conserva
            vals.update(vehicle_id=vid or False, vinculo_metodo=metodo, placa_detectada=clave or False,
                        vinculo_nota=nota or False)

        eventos = []
        if pos and pos.get('latitude') is not None:
            estado_geo, transiciones = evaluar_geocercas(
                rec.geocercas_estado if rec else False, rec.id if rec else 0, pos.get('latitude'),
                pos.get('longitude'), bool(pos.get('valid')) and not pos.get('outdated'), ctx['geocercas'])
            vals['geocercas_estado'] = estado_geo
        else:
            transiciones = []

        if not rec:
            vals.update(estado_desde=ahora, sincronizado=ahora)
            rec = self.create(vals)
            eventos.append(rec._evento_vals('nuevo', ahora))
            return rec, eventos

        anterior, status_anterior = rec.estado, rec.traccar_status
        cambios = self._cambios(rec, vals)
        vehicle_id = vals.get('vehicle_id', rec.vehicle_id.id)
        if 'estado' in cambios:
            cambios['estado_desde'] = ahora
            tipo = rec._tipo_evento(anterior, vals['estado'])
            if tipo:
                eventos.append(rec._evento_vals(tipo, ahora, vals['estado'], vals['motivo'], anterior,
                                                vehicle_id=vehicle_id))
        # Desconexión inmediata: Traccar la marca al cortarse la conexión, antes de cumplirse el umbral.
        if (status_anterior == 'online' and vals['traccar_status'] in ('offline', 'unknown')
                and not any(e['tipo'] == 'sin_reporte' for e in eventos) and vals['estado'] != 'deshabilitado'):
            eventos.append(rec._evento_vals('desconectado', ahora, vals['estado'], vals['motivo'], vehicle_id=vehicle_id))
        for geo, sentido in transiciones:
            if geo['entrada' if sentido == 'entrada' else 'salida']:
                eventos.append(rec._evento_vals('geocerca_' + sentido, ahora, vals['estado'], geo['name'],
                                                vehicle_id=vehicle_id, geocerca=geo))
        if alarma_evento and alarma_evento in cfg['alarmas']:
            eventos.append(rec._evento_vals('alarma', ahora, vals['estado'], ALARMAS.get(alarma_evento, alarma_evento),
                                            vehicle_id=vehicle_id, alarma=alarma_evento))
        cambios['sincronizado'] = ahora
        rec.write(cambios)
        return rec, eventos

    @api.model
    def sincronizar(self):
        """Lee Traccar y actualiza el registro de dispositivos, su relación con Odoo, su
        estado, las geocercas y los eventos. Si Traccar no responde, no cambia nada."""
        self = self.sudo()
        cr = self.env.cr
        cr.execute("SELECT pg_try_advisory_xact_lock(hashtext('adt_flota360_gps_sync'))")
        if not cr.fetchone()[0]:
            return {'ok': False, 'error': _('Ya hay una sincronización en curso; intenta en unos segundos.')}
        ICP = self.env['ir.config_parameter']
        ahora = fields.Datetime.now()
        try:
            devices, positions, groups, geofences = self._traccar_datos()
        except UserError as exc:
            ICP.set_param(PARAM % 'ultimo_error', '%s|%s' % (fields.Datetime.to_string(ahora), exc.args[0]))
            _logger.warning('%s %s', LOG, exc.args[0])
            return {'ok': False, 'error': exc.args[0]}

        if geofences:
            self.env['adt.flota360.gps.geocerca']._importar_traccar(geofences)
        ctx = self._contexto()
        ctx['grupos'] = {g.get('id'): g.get('name') for g in groups} or {None: False}
        pos_por_device = {p.get('deviceId'): p for p in positions if p.get('deviceId')}
        existentes = {d.traccar_id: d for d in self.with_context(active_test=False).search([])}
        resumen = {'ok': True, 'total': 0, 'nuevos': 0, 'actualizados': 0, 'eliminados': 0, 'eventos': 0, 'creados': 0}
        eventos, vistos = [], set()

        for device in devices:
            tid = device.get('id')
            if not tid or tid in vistos:
                continue
            vistos.add(tid)
            resumen['total'] += 1
            rec = existentes.get(tid, self.browse())
            if not rec:
                resumen['nuevos'] += 1
            rec, nuevos = rec._aplicar(device, pos_por_device.get(tid), ahora, ctx)
            eventos += nuevos

        for tid, rec in existentes.items():
            if tid not in vistos and rec.active:
                eventos.append(rec._evento_vals('eliminado', ahora))
                rec.write({'active': False, 'sincronizado': ahora})
                resumen['eliminados'] += 1

        if ctx['cfg']['crear_vehiculos'] and ctx['cfg']['modelo_id']:
            pendientes = self.search([('vehicle_id', '=', False), ('vinculo_manual', '=', False),
                                      ('vinculo_metodo', '=', 'sin_vinculo')])
            creados, nuevos = pendientes._crear_vehiculos(ctx['cfg']['modelo_id'], ahora)
            resumen['creados'] = len(creados)
            eventos += nuevos

        resumen['eventos'] = len(eventos)
        self.env['adt.flota360.gps.evento']._registrar(eventos)
        ICP.set_param(PARAM % 'ultima_sync', fields.Datetime.to_string(ahora))
        ICP.set_param(PARAM % 'ultimo_error', '')
        _logger.info('%s Sincronizados %s dispositivos (%s nuevos, %s eliminados, %s eventos, %s vehículos creados).',
                     LOG, resumen['total'], resumen['nuevos'], resumen['eliminados'], resumen['eventos'],
                     resumen['creados'])
        return resumen

    @api.model
    def _traccar_datos(self):
        """(dispositivos, posiciones, grupos, geocercas) leídos de Traccar."""
        with Traccar(self.env) as t:
            return (t.leer_lista('/api/devices'), t.leer_lista('/api/positions'),
                    t.leer_lista('/api/groups', obligatorio=False), t.leer_lista('/api/geofences', obligatorio=False))

    # --- Tiempo real (webhook de Traccar) ------------------------------

    @api.model
    def procesar_webhook(self, datos):
        """Evento o posición reenviados por Traccar (event.forward / forward con JSON):
        {"event": {...}, "device": {...}, "position": {...}} o {"position": {...}, "device": {...}}."""
        self = self.sudo()
        evento = datos.get('event') or {}
        device = dict(datos.get('device') or {})
        pos = datos.get('position') or None
        tid = device.get('id') or evento.get('deviceId') or (pos or {}).get('deviceId')
        if not tid:
            return {'ok': False, 'error': 'sin deviceId'}
        ahora = fields.Datetime.now()
        rec = self.with_context(active_test=False).search([('traccar_id', '=', tid)], limit=1)
        if rec and not device.get('lastUpdate'):
            # Payload solo con posición: se completa con lo que ya se sabe del dispositivo.
            device.update({k: v for k, v in {
                'id': tid, 'name': device.get('name') or rec.name, 'uniqueId': device.get('uniqueId') or rec.imei,
                'status': device.get('status') or rec.traccar_status, 'disabled': rec.deshabilitado,
                'lastUpdate': (pos or {}).get('serverTime') or (
                    rec.ultimo_reporte and iso_traccar(rec.ultimo_reporte)),
            }.items() if k not in device or device.get(k) is None})
        device.setdefault('id', tid)
        if not rec and not device.get('name'):
            return {'ok': False, 'error': 'dispositivo desconocido sin datos'}
        alarma = None
        if evento.get('type') == 'alarm':
            alarma = (alarmas_de((evento.get('attributes') or {}).get('alarm')) or [None])[0]
        ctx = self._contexto()
        rec, eventos = rec._aplicar(device, pos, ahora, ctx, alarma_evento=alarma)
        self.env['adt.flota360.gps.evento']._registrar(eventos)
        ICP = self.env['ir.config_parameter']
        ultimo = fields.Datetime.from_string(ICP.get_param(PARAM % 'webhook_ultimo') or '1970-01-01 00:00:00')
        if ahora - ultimo > timedelta(seconds=60):
            ICP.set_param(PARAM % 'webhook_ultimo', fields.Datetime.to_string(ahora))
        return {'ok': True, 'eventos': len(eventos)}

    # --- Eventos -------------------------------------------------------

    def _tipo_evento(self, anterior, nuevo):
        if nuevo == 'sin_reporte' and anterior in REPORTA:
            return 'sin_reporte'
        if nuevo in REPORTA and anterior in NO_REPORTA:
            return 'volvio'
        if nuevo == 'deshabilitado':
            return 'deshabilitado'
        return None

    def _evento_vals(self, tipo, ahora, estado=None, motivo=None, anterior=None, vehicle_id=None, geocerca=None,
                     alarma=None):
        self.ensure_one()
        vehiculo = self.env['fleet.vehicle'].browse(vehicle_id) if vehicle_id else self.vehicle_id
        estado = estado or self.estado
        motivo = motivo or self.motivo
        nombre = vehiculo.license_plate or self.name
        mensajes = {
            'sin_reporte': '%s dejó de reportar. %s' % (nombre, motivo or ''),
            'volvio': ('%s reportó por primera vez' if anterior == 'nunca' else '%s volvió a reportar') % nombre,
            'desconectado': '%s se desconectó de Traccar' % nombre,
            'alarma': '%s: %s' % (nombre, motivo or alarma or ''),
            'geocerca_entrada': '%s entró a %s' % (nombre, geocerca['name'] if geocerca else ''),
            'geocerca_salida': '%s salió de %s' % (nombre, geocerca['name'] if geocerca else ''),
            'nuevo': 'Nuevo dispositivo en Traccar: %s' % self.name,
            'creado': 'Se creó el vehículo %s en Odoo desde Traccar' % nombre,
            'deshabilitado': '%s fue deshabilitado en Traccar' % self.name,
            'eliminado': '%s ya no existe en Traccar' % self.name,
        }
        return {'dispositivo_id': self.id, 'vehicle_id': vehiculo.id or False, 'tipo': tipo, 'fecha': ahora,
                'estado': estado, 'motivo': motivo or False, 'mensaje': mensajes[tipo].strip(),
                'geocerca_id': geocerca['id'] if geocerca else False, 'alarma': alarma or False}

    # --- Vehículos que faltan en Odoo ----------------------------------

    def _crear_vehiculos(self, modelo_id, ahora=None):
        """Crea en Odoo el vehículo de cada dispositivo sin vehículo cuya placa leída tenga
        forma de placa. Dos dispositivos con la misma placa comparten el vehículo.
        → (vehículos creados, [valores de eventos])."""
        ahora = ahora or fields.Datetime.now()
        Vehicle = self.env['fleet.vehicle'].sudo()
        modelo = self.env['fleet.vehicle.model'].sudo().browse(modelo_id).exists()
        if not modelo:
            raise ValidationError(_('Elige en la configuración el modelo con el que se crean los vehículos.'))
        indice = self._indice_placas(self._config()['palabras_ruido'])
        creados, eventos, por_placa = Vehicle, [], {}
        for d in self.filtered(lambda r: not r.vehicle_id):
            placa = d.placa_detectada
            if not con_forma_de_placa(placa):
                continue
            vid = por_placa.get(placa)
            if not vid:
                existente = indice.buscar(placa)
                if existente[0]:
                    vid = existente[0]
                elif existente[1] == 'ambiguo':
                    continue
                else:
                    vals = {'model_id': modelo.id, 'license_plate': placa}
                    if 'x_imei' in Vehicle._fields and d.imei:
                        vals['x_imei'] = d.imei
                    vehiculo = Vehicle.create(vals)
                    creados |= vehiculo
                    indice.agregar(vehiculo.id, placa, d.imei)
                    vid = vehiculo.id
                por_placa[placa] = vid
            d.write({'vehicle_id': vid, 'vinculo_metodo': 'creado', 'vinculo_manual': False,
                     'vinculo_nota': _('Creado desde Traccar el %s') % fields.Date.to_string(ahora.date())})
            eventos.append(d._evento_vals('creado', ahora, vehicle_id=vid))
        return creados, eventos

    # --- Mantenimiento -------------------------------------------------

    @api.model
    def _cron_sincronizar(self):
        self.sincronizar()
        limite = fields.Datetime.now() - timedelta(days=DIAS_EVENTOS)
        self.env['adt.flota360.gps.evento'].sudo().search([('fecha', '<', limite)]).unlink()

    def rematch(self):
        """Vuelve a la relación automática y la recalcula al momento."""
        indice = self._indice_placas(self._config()['palabras_ruido'])
        for rec in self:
            vid, metodo, clave, nota = indice.buscar(rec.name, rec.imei)
            if rec.vinculo_metodo == 'creado' and rec.vehicle_id and not vid:
                continue
            rec.write({'vinculo_manual': False, 'vehicle_id': vid or False, 'vinculo_metodo': metodo,
                       'placa_detectada': clave or False, 'vinculo_nota': nota or False})


class AdtFlota360GpsEvento(models.Model):
    _name = 'adt.flota360.gps.evento'
    _description = 'Flota 360: cambio de estado de un dispositivo GPS'
    _order = 'id desc'

    dispositivo_id = fields.Many2one('adt.flota360.gps.dispositivo', 'Dispositivo', required=True,
                                     ondelete='cascade', index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehículo', ondelete='set null')
    tipo = fields.Selection(TIPOS_EVENTO, 'Evento', required=True, index=True)
    fecha = fields.Datetime('Fecha', required=True, default=fields.Datetime.now, index=True)
    estado = fields.Selection(ESTADOS, 'Estado')
    motivo = fields.Char('Motivo')
    mensaje = fields.Char('Mensaje')
    geocerca_id = fields.Many2one('adt.flota360.gps.geocerca', 'Geocerca', ondelete='set null')
    alarma = fields.Char('Alarma')

    @api.model
    def _registrar(self, valores):
        """Crea los eventos y envía al momento (bus de Odoo) los que son alertas activas."""
        if not valores:
            return self.browse()
        eventos = self.sudo().create(valores)
        eventos._publicar()
        return eventos

    def _destinatarios(self, cfg):
        grupo = self.env.ref(GRUPO_USUARIO, raise_if_not_found=False)
        usuarios = grupo.sudo().users.filtered(lambda u: u.active and not u.share) if grupo else self.env['res.users']
        if cfg['destinatarios']:
            usuarios = usuarios.filtered(lambda u: u.id in cfg['destinatarios'])
        return usuarios

    def _alerta_dict(self, info=None):
        self.ensure_one()
        v = (info or {}).get(self.vehicle_id.id, {})
        return {
            'id': self.id, 'tipo': self.tipo, 'tipo_label': dict(TIPOS_EVENTO).get(self.tipo),
            'nivel': NIVEL_EVENTO.get(self.tipo, 'info'), 'mensaje': self.mensaje or '', 'motivo': self.motivo or '',
            'dispositivo_id': self.dispositivo_id.id, 'nombre': self.dispositivo_id.name,
            'placa': v.get('placa') or self.vehicle_id.license_plate or self.dispositivo_id.name,
            'cliente': v.get('cliente', ''), 'fecha': fields.Datetime.to_string(self.fecha),
            'geocerca': self.geocerca_id.name or '',
        }

    def _publicar(self):
        cfg = self.env['adt.flota360.gps.dispositivo']._config()
        alertas = self.filtered(lambda e: e.tipo in cfg['alertas'])
        if not alertas:
            return
        usuarios = self._destinatarios(cfg)
        if not usuarios:
            return
        info = self.env['adt.flota360']._gps_vehiculos({e.vehicle_id.id for e in alertas if e.vehicle_id})
        payload = {'eventos': [e._alerta_dict(info) for e in alertas.sorted('id')]}
        self.env['bus.bus'].sudo()._sendmany([(u.partner_id, BUS_TIPO, payload) for u in usuarios])


# ----------------------------------------------------------------------
# API de la vista (adt.flota360)
# ----------------------------------------------------------------------

class AdtFlota360Gps(models.AbstractModel):
    _inherit = 'adt.flota360'

    def _gps_check(self, grupo=GRUPO_USUARIO):
        if not self.env.user.has_group(grupo):
            raise AccessError(_('No tienes acceso al monitoreo GPS.'))
        return self.env['adt.flota360.gps.dispositivo'].sudo()

    def _gps_dispositivo(self, dispositivo_id):
        Disp = self._gps_check()
        d = Disp.with_context(active_test=False).browse(int(dispositivo_id)).exists()
        if not d:
            raise ValidationError(_('El dispositivo ya no existe.'))
        return d

    def _gps_webhook_url(self):
        ICP = self.env['ir.config_parameter'].sudo()
        token = ICP.get_param(PARAM % 'webhook_token')
        if not token:
            token = secrets.token_urlsafe(24)
            ICP.set_param(PARAM % 'webhook_token', token)
        base = (ICP.get_param('web.base.url') or '').rstrip('/')
        return '%s/adt_flota_360/gps/traccar/%s' % (base, token)

    def _gps_meta(self):
        ICP = self.env['ir.config_parameter'].sudo()
        error = ICP.get_param(PARAM % 'ultimo_error') or ''
        fecha_error, _sep, texto_error = error.partition('|')
        cron = self.env.ref('adt_flota_360.cron_gps_monitor', raise_if_not_found=False)
        cron = cron.sudo() if cron else cron
        cfg = self.env['adt.flota360.gps.dispositivo']._config()
        webhook_ultimo = ICP.get_param(PARAM % 'webhook_ultimo') or False
        activo = bool(webhook_ultimo) and fields.Datetime.now() - fields.Datetime.from_string(webhook_ultimo) < timedelta(
            minutes=WEBHOOK_ACTIVO_MIN)
        manager = self.env.user.has_group(GRUPO_MANAGER)
        modelo = self.env['fleet.vehicle.model'].sudo().browse(cfg['modelo_id']).exists()
        cfg.update({
            'ultima_sync': ICP.get_param(PARAM % 'ultima_sync') or False,
            'error': texto_error or False,
            'error_fecha': fecha_error if texto_error else False,
            'frecuencia': cron.interval_number if cron and cron.interval_type == 'minutes' else False,
            'cron_activo': bool(cron and cron.active),
            'manager': manager,
            'traccar_url': (ICP.get_param('adt_traccar.url') or '').rstrip('/') or False,
            'webhook_ultimo': webhook_ultimo,
            'tiempo_real': activo,
            'modelo_nombre': modelo.display_name if modelo else '',
            'tipos_alerta': [{'id': t, 'label': dict(TIPOS_EVENTO)[t]} for t in ALERTABLES],
            'tipos_alarma': [{'id': k, 'label': v} for k, v in ALARMAS.items()],
            'soy_destinatario': not cfg['destinatarios'] or self.env.user.id in cfg['destinatarios'],
        })
        if manager:
            cfg['webhook_url'] = self._gps_webhook_url()
        return cfg

    def _gps_vehiculos(self, vehicle_ids):
        """{vehicle_id: {placa, vehiculo, cliente, telefono}} en una sola lectura."""
        Vehicle = self.env['fleet.vehicle'].sudo()
        campos = [c for c in ('license_plate', 'model_id', 'driver_id', 'vin_sn') if c in Vehicle._fields]
        filas = Vehicle.browse([v for v in vehicle_ids if v]).read(campos)
        socios = {s['id']: s for s in self.env['res.partner'].sudo().browse(
            list({f['driver_id'][0] for f in filas if f.get('driver_id')})).read(['mobile', 'phone'])}
        res = {}
        for f in filas:
            socio = socios.get(self._id(f.get('driver_id'))) or {}
            res[f['id']] = {
                'placa': f.get('license_plate') or '',
                'vehiculo': self._m2o(f.get('model_id')),
                'cliente': self._m2o(f.get('driver_id')),
                'telefono': socio.get('mobile') or socio.get('phone') or '',
                'chasis': f.get('vin_sn') or '',
            }
        return res

    def _gps_dentro(self, estado_json):
        try:
            return (json.loads(estado_json or '{}').get('dentro')) or []
        except ValueError:
            return []

    def _gps_geocercas_lista(self, dentro_por_geo=None):
        res = []
        for g in self.env['adt.flota360.gps.geocerca'].sudo().search([]):
            res.append({
                'id': g.id, 'name': g.name, 'descripcion': g.descripcion or '', 'color': g.color or '#d9480f',
                'tipo': g.tipo, 'lat': g.latitud, 'lon': g.longitud, 'radio': g.radio, 'puntos': g._puntos(),
                'entrada': g.alertar_entrada, 'salida': g.alertar_salida, 'alcance': g.alcance,
                'dispositivos': g.dispositivo_ids.ids, 'publicar': g.publicar_traccar, 'traccar_id': g.traccar_id,
                'traccar_error': g.traccar_error or '', 'dentro': (dentro_por_geo or {}).get(g.id, 0),
            })
        return res

    @api.model
    def gps_tablero(self):
        """Todos los dispositivos monitoreados (la vista filtra y ordena en el navegador)."""
        Disp = self._gps_check()
        campos = ['name', 'imei', 'vehicle_id', 'placa_detectada', 'vinculo_metodo', 'vinculo_manual', 'vinculo_nota',
                  'estado', 'estado_desde', 'motivo', 'ultimo_reporte', 'traccar_status', 'grupo', 'latitud',
                  'longitud', 'velocidad_kmh', 'ignicion', 'bateria', 'voltaje', 'posicion_valida', 'direccion',
                  'geocercas_estado']
        filas = Disp.search_read([], campos, order='name')
        info = self._gps_vehiculos({self._id(f['vehicle_id']) for f in filas if f['vehicle_id']})
        metodos = dict(METODOS)
        a_texto = fields.Datetime.to_string
        conteo_vehiculo, dentro_por_geo = {}, {}
        for f in filas:
            if f['vehicle_id']:
                conteo_vehiculo[f['vehicle_id'][0]] = conteo_vehiculo.get(f['vehicle_id'][0], 0) + 1
        items = []
        for f in filas:
            vid = self._id(f['vehicle_id'])
            v = info.get(vid, {})
            dentro = self._gps_dentro(f['geocercas_estado'])
            for g in dentro:
                dentro_por_geo[g] = dentro_por_geo.get(g, 0) + 1
            items.append({
                'id': f['id'], 'nombre': f['name'], 'imei': f['imei'] or '',
                'estado': f['estado'], 'nivel': NIVEL_ESTADO.get(f['estado'], 'neutral'),
                'motivo': f['motivo'] or '',
                'sin_gps': f['estado'] == 'reportando' and not f['posicion_valida'],
                'ultimo': a_texto(f['ultimo_reporte']) if f['ultimo_reporte'] else False,
                'desde': a_texto(f['estado_desde']) if f['estado_desde'] else False,
                'conexion': f['traccar_status'] or '',
                'grupo': f['grupo'] or '',
                'vehicle_id': vid, 'placa': v.get('placa', ''), 'vehiculo': v.get('vehiculo', ''),
                'cliente': v.get('cliente', ''), 'telefono': v.get('telefono', ''),
                'otros_dispositivos': conteo_vehiculo.get(vid, 1) - 1 if vid else 0,
                'placa_detectada': f['placa_detectada'] or '',
                'metodo': f['vinculo_metodo'] or 'sin_vinculo',
                'metodo_label': metodos.get(f['vinculo_metodo'] or 'sin_vinculo', ''),
                'puede_crear': not vid and (f['vinculo_metodo'] or 'sin_vinculo') == 'sin_vinculo'
                and con_forma_de_placa(f['placa_detectada']),
                'manual': f['vinculo_manual'], 'nota': f['vinculo_nota'] or '',
                'lat': f['latitud'], 'lon': f['longitud'], 'velocidad': f['velocidad_kmh'],
                'ignicion': f['ignicion'] or '', 'bateria': f['bateria'], 'voltaje': f['voltaje'],
                'direccion': f['direccion'] or '', 'geocercas': dentro,
            })
        return {'items': items, 'meta': self._gps_meta(), 'odoo_sin_gps': self._gps_odoo_sin_gps(conteo_vehiculo),
                'geocercas': self._gps_geocercas_lista(dentro_por_geo)}

    def _gps_odoo_sin_gps(self, con_dispositivo):
        """Vehículos de Odoo con placa (y cliente) que no tienen ningún dispositivo en Traccar."""
        Vehicle = self.env['fleet.vehicle'].sudo()
        dominio = [('id', 'not in', list(con_dispositivo))]
        if 'driver_id' in Vehicle._fields:
            dominio.append(('driver_id', '!=', False))
        ids = [f['id'] for f in Vehicle.search_read(dominio, ['license_plate']) if placa_valida(f['license_plate'])]
        return {'n': len(ids), 'ids': ids}

    @api.model
    def gps_dispositivo(self, dispositivo_id):
        d = self._gps_dispositivo(dispositivo_id)
        Disp = d.browse()
        a_texto = lambda f: fields.Datetime.to_string(f) if f else False
        v = self._gps_vehiculos([d.vehicle_id.id]).get(d.vehicle_id.id, {}) if d.vehicle_id else {}
        otros = Disp.search([('vehicle_id', '=', d.vehicle_id.id), ('id', '!=', d.id)]) if d.vehicle_id else Disp
        try:
            atributos = json.loads(d.atributos) if d.atributos else {}
        except ValueError:
            atributos = {}
        geos = self.env['adt.flota360.gps.geocerca'].sudo().browse(self._gps_dentro(d.geocercas_estado)).exists()
        return {
            'id': d.id, 'nombre': d.name, 'imei': d.imei or '', 'traccar_id': d.traccar_id, 'activo': d.active,
            'estado': d.estado, 'estado_label': dict(ESTADOS).get(d.estado, ''), 'nivel': NIVEL_ESTADO.get(d.estado),
            'desde': a_texto(d.estado_desde), 'motivo': d.motivo or '',
            'detalle': [l for l in (d.motivo_detalle or '').split('\n') if l],
            'ultimo': a_texto(d.ultimo_reporte), 'ultima_posicion': a_texto(d.ultima_posicion),
            'sincronizado': a_texto(d.sincronizado),
            'conexion': dict(d._fields['traccar_status']._description_selection(self.env)).get(d.traccar_status, ''),
            'grupo': d.grupo or '', 'telefono_chip': d.telefono or '', 'modelo_equipo': d.modelo_equipo or '',
            'contacto': d.contacto or '', 'categoria': d.categoria or '', 'protocolo': d.protocolo or '',
            'lat': d.latitud, 'lon': d.longitud, 'velocidad': d.velocidad_kmh, 'direccion': d.direccion or '',
            'ignicion': d.ignicion or '', 'bateria': d.bateria, 'voltaje': d.voltaje, 'alarma': d.alarma or '',
            'posicion_valida': d.posicion_valida, 'satelites': d.satelites, 'km_total': d.km_total,
            'atributos': atributos,
            'vehicle_id': d.vehicle_id.id or False, 'vehiculo': v,
            'metodo': d.vinculo_metodo or 'sin_vinculo', 'metodo_label': dict(METODOS).get(d.vinculo_metodo or 'sin_vinculo'),
            'manual': d.vinculo_manual, 'nota': d.vinculo_nota or '', 'placa_detectada': d.placa_detectada or '',
            'puede_crear': not d.vehicle_id and d.vinculo_metodo == 'sin_vinculo' and con_forma_de_placa(d.placa_detectada),
            'otros': [{'id': o.id, 'nombre': o.name, 'estado': o.estado, 'nivel': NIVEL_ESTADO.get(o.estado)} for o in otros],
            'geocercas': [{'id': g.id, 'name': g.name, 'color': g.color} for g in geos],
            'eventos': [{
                'id': e.id, 'tipo': e.tipo, 'tipo_label': dict(TIPOS_EVENTO).get(e.tipo), 'fecha': a_texto(e.fecha),
                'mensaje': e.mensaje or '', 'nivel': NIVEL_EVENTO.get(e.tipo, 'neutral'),
            } for e in d.evento_ids[:50]],
            'traccar_url': (self.env['ir.config_parameter'].sudo().get_param('adt_traccar.url') or '').rstrip('/') or False,
        }

    @api.model
    def gps_sincronizar(self):
        Disp = self._gps_check()
        res = Disp.sincronizar()
        if not res.get('ok'):
            raise UserError(res.get('error') or _('No se pudo sincronizar con Traccar.'))
        return res

    # --- En vivo y recorrido ------------------------------------------

    @api.model
    def gps_en_vivo(self, dispositivo_id):
        """Posición actual leída directamente de Traccar (la vista la pide cada pocos
        segundos). De paso actualiza el registro y dispara los eventos que correspondan."""
        d = self._gps_dispositivo(dispositivo_id)
        with Traccar(self.env) as t:
            devices = t.leer_lista('/api/devices', {'id': d.traccar_id})
            posiciones = t.leer_lista('/api/positions', {'deviceId': d.traccar_id}, obligatorio=False)
        if not devices:
            raise ValidationError(_('Traccar ya no tiene este dispositivo.'))
        pos = posiciones[-1] if posiciones else None
        Disp = d.browse()
        ctx = Disp._contexto()
        d, eventos = d._aplicar(devices[0], pos, fields.Datetime.now(), ctx)
        self.env['adt.flota360.gps.evento']._registrar(eventos)
        return {
            'estado': d.estado, 'estado_label': dict(ESTADOS).get(d.estado), 'nivel': NIVEL_ESTADO.get(d.estado),
            'motivo': d.motivo or '', 'conexion': d.traccar_status or '',
            'ultimo': fields.Datetime.to_string(d.ultimo_reporte) if d.ultimo_reporte else False,
            'fix': fields.Datetime.to_string(d.ultima_posicion) if d.ultima_posicion else False,
            'lat': d.latitud, 'lon': d.longitud, 'velocidad': d.velocidad_kmh, 'curso': (pos or {}).get('course') or 0,
            'direccion': d.direccion or '', 'ignicion': d.ignicion or '', 'bateria': d.bateria, 'voltaje': d.voltaje,
            'valida': d.posicion_valida,
        }

    @api.model
    def gps_recorrido(self, dispositivo_id, desde, hasta):
        """Recorrido, viajes y paradas de Traccar entre dos fechas (UTC 'YYYY-MM-DD HH:MM:SS')."""
        d = self._gps_dispositivo(dispositivo_id)
        inicio, fin = fields.Datetime.to_datetime(desde), fields.Datetime.to_datetime(hasta)
        if not inicio or not fin or fin <= inicio:
            raise ValidationError(_('El rango de fechas no es válido.'))
        if fin - inicio > timedelta(days=MAX_DIAS_RECORRIDO):
            raise ValidationError(_('Elige un rango de hasta %s días.') % MAX_DIAS_RECORRIDO)
        params = {'deviceId': d.traccar_id, 'from': iso_traccar(inicio), 'to': iso_traccar(fin)}
        with Traccar(self.env) as t:
            ruta = t.leer_lista('/api/reports/route', params)
            paradas = t.leer_lista('/api/reports/stops', params, obligatorio=False)
            viajes = t.leer_lista('/api/reports/trips', params, obligatorio=False)
        validas = [p for p in ruta if p.get('latitude') or p.get('longitude')]
        paso = max(1, -(-len(validas) // MAX_PUNTOS_RECORRIDO))
        muestra = validas[::paso]
        if validas and muestra[-1] is not validas[-1]:
            muestra.append(validas[-1])
        a_texto = lambda v: fields.Datetime.to_string(fecha_traccar(v)) if fecha_traccar(v) else False
        distancia = sum((v.get('distance') or 0.0) for v in viajes) / 1000.0
        if not distancia and len(validas) > 1:
            distancia = sum(distancia_m(a['latitude'], a['longitude'], b['latitude'], b['longitude'])
                            for a, b in zip(validas, validas[1:])) / 1000.0
        eventos = self.env['adt.flota360.gps.evento'].sudo().search(
            [('dispositivo_id', '=', d.id), ('fecha', '>=', inicio), ('fecha', '<=', fin)], limit=200)
        return {
            'puntos': [[round(p['latitude'], 6), round(p['longitude'], 6), a_texto(p.get('fixTime')),
                        round((p.get('speed') or 0.0) * NUDO_KMH), (p.get('attributes') or {}).get('ignition')]
                       for p in muestra],
            'total_puntos': len(validas),
            'paradas': [{
                'lat': s.get('latitude'), 'lon': s.get('longitude'), 'desde': a_texto(s.get('startTime')),
                'hasta': a_texto(s.get('endTime')), 'minutos': int((s.get('duration') or 0) // 60000),
                'direccion': s.get('address') or '',
            } for s in paradas],
            'resumen': {
                'distancia_km': round(distancia, 1),
                'vel_max': round(max([(p.get('speed') or 0.0) for p in validas] or [0]) * NUDO_KMH),
                'minutos_movimiento': int(sum((v.get('duration') or 0) for v in viajes) // 60000),
                'viajes': len(viajes), 'paradas': len(paradas),
            },
            'eventos': [{'fecha': fields.Datetime.to_string(e.fecha), 'tipo_label': dict(TIPOS_EVENTO).get(e.tipo),
                         'mensaje': e.mensaje or '', 'nivel': NIVEL_EVENTO.get(e.tipo, 'neutral')} for e in eventos],
        }

    # --- Relación y vehículos ------------------------------------------

    @api.model
    def gps_buscar_vehiculos(self, texto):
        Disp = self._gps_check()
        texto = (texto or '').strip()
        if len(texto) < 2:
            return []
        Vehicle = self.env['fleet.vehicle'].sudo()
        compacto = re.sub(r'[^0-9A-Za-z]', '', texto).upper()
        ids = set()
        if compacto:
            self.env.cr.execute("""
                SELECT id FROM fleet_vehicle
                 WHERE active AND upper(regexp_replace(coalesce(license_plate, ''), '[^A-Za-z0-9]', '', 'g')) LIKE %s
                 LIMIT 15""", ['%' + compacto + '%'])
            ids.update(r[0] for r in self.env.cr.fetchall())
        dominio = ['|', ('vin_sn', 'ilike', texto), ('license_plate', 'ilike', texto)]
        if 'driver_id' in Vehicle._fields:
            dominio = ['|'] + dominio + [('driver_id.name', 'ilike', texto)]
        ids.update(Vehicle.search(dominio, limit=15).ids)
        ids = list(ids)[:20]
        info = self._gps_vehiculos(ids)
        usados = {}
        for f in Disp.search_read([('vehicle_id', 'in', ids)], ['vehicle_id']):
            usados[f['vehicle_id'][0]] = usados.get(f['vehicle_id'][0], 0) + 1
        return sorted([dict(info[i], id=i, dispositivos=usados.get(i, 0)) for i in ids if i in info],
                      key=lambda r: r['placa'])

    @api.model
    def gps_vincular(self, dispositivo_id, vehicle_id):
        d = self._gps_dispositivo(dispositivo_id)
        vehiculo = self.env['fleet.vehicle'].sudo().browse(int(vehicle_id)).exists() if vehicle_id else None
        if vehicle_id and not vehiculo:
            raise ValidationError(_('El vehículo ya no existe.'))
        d.write({'vehicle_id': vehiculo.id if vehiculo else False, 'vinculo_manual': True,
                 'vinculo_metodo': 'manual' if vehiculo else 'sin_vinculo',
                 'vinculo_nota': _('Relacionado por %s') % self.env.user.name if vehiculo
                 else _('Sin vehículo, fijado por %s') % self.env.user.name})
        return self.gps_dispositivo(d.id)

    @api.model
    def gps_vinculo_automatico(self, dispositivo_id):
        d = self._gps_dispositivo(dispositivo_id)
        d.rematch()
        return self.gps_dispositivo(d.id)

    @api.model
    def gps_crear_vehiculos(self, dispositivo_ids):
        """Crea en Odoo los vehículos de los dispositivos elegidos que no tienen vehículo."""
        Disp = self._gps_check(GRUPO_MANAGER)
        cfg = Disp._config()
        if not cfg['modelo_id']:
            raise ValidationError(_('Primero elige en Configuración el modelo con el que se crean los vehículos.'))
        disp = Disp.browse([int(i) for i in dispositivo_ids or []]).exists()
        creados, eventos = disp._crear_vehiculos(cfg['modelo_id'])
        self.env['adt.flota360.gps.evento']._registrar(eventos)
        omitidos = len(disp.filtered(lambda d: not d.vehicle_id))
        return {'creados': len(creados), 'relacionados': len(eventos), 'omitidos': omitidos}

    # --- Geocercas -----------------------------------------------------

    @api.model
    def gps_geocerca_guardar(self, geocerca_id, valores):
        self._gps_check(GRUPO_MANAGER)
        Geo = self.env['adt.flota360.gps.geocerca'].sudo()
        v = valores or {}
        nombre = (v.get('name') or '').strip()
        if not nombre:
            raise ValidationError(_('Ponle un nombre a la geocerca.'))
        tipo = v.get('tipo') if v.get('tipo') in ('circulo', 'poligono') else 'circulo'
        puntos = [[float(p[0]), float(p[1])] for p in (v.get('puntos') or [])] if tipo == 'poligono' else []
        datos = {
            'name': nombre, 'descripcion': v.get('descripcion') or False, 'color': v.get('color') or '#d9480f',
            'tipo': tipo, 'radio': float(v.get('radio') or 0),
            'latitud': float(v.get('lat') or 0), 'longitud': float(v.get('lon') or 0),
            'puntos': json.dumps(puntos) if puntos else False,
            'alertar_entrada': bool(v.get('entrada')), 'alertar_salida': bool(v.get('salida')),
            'alcance': 'seleccion' if v.get('alcance') == 'seleccion' else 'todos',
            'dispositivo_ids': [(6, 0, [int(i) for i in v.get('dispositivos') or []])],
            'publicar_traccar': bool(v.get('publicar', True)),
        }
        if tipo == 'poligono' and puntos:
            datos['latitud'] = sum(p[0] for p in puntos) / len(puntos)
            datos['longitud'] = sum(p[1] for p in puntos) / len(puntos)
        if geocerca_id:
            geo = Geo.browse(int(geocerca_id)).exists()
            if not geo:
                raise ValidationError(_('La geocerca ya no existe.'))
            geo.write(datos)
        else:
            geo = Geo.create(datos)
        geo._publicar_traccar()
        return {'id': geo.id, 'traccar_error': geo.traccar_error or ''}

    @api.model
    def gps_geocerca_eliminar(self, geocerca_id):
        self._gps_check(GRUPO_MANAGER)
        geo = self.env['adt.flota360.gps.geocerca'].sudo().browse(int(geocerca_id)).exists()
        if geo:
            geo._quitar_traccar()
            geo.unlink()
        return True

    # --- Configuración y alertas --------------------------------------

    @api.model
    def gps_config(self):
        self._gps_check()
        meta = self._gps_meta()
        if meta['manager']:
            grupo = self.env.ref(GRUPO_USUARIO)
            meta['usuarios'] = [{'id': u.id, 'name': u.name} for u in grupo.sudo().users.filtered(
                lambda u: u.active and not u.share).sorted('name')]
            meta['modelos'] = [{'id': m['id'], 'name': m['display_name']} for m in self.env['fleet.vehicle.model'].sudo()
                               .search_read([], ['display_name'], order='name', limit=500)]
        return meta

    @api.model
    def gps_config_guardar(self, valores):
        self._gps_check(GRUPO_MANAGER)
        valores = valores or {}
        try:
            demora = int(valores.get('minutos_demora'))
            sin = int(valores.get('minutos_sin_reporte'))
            frecuencia = int(valores.get('frecuencia') or 0)
        except (TypeError, ValueError):
            raise ValidationError(_('Los minutos deben ser números enteros.'))
        if demora < 1 or sin <= demora:
            raise ValidationError(_('«Sin reportar» debe ser mayor que «demorado», y ambos de al menos 1 minuto.'))
        if frecuencia and not 1 <= frecuencia <= 60:
            raise ValidationError(_('La frecuencia de sincronización debe estar entre 1 y 60 minutos.'))
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(PARAM % 'minutos_demora', str(demora))
        ICP.set_param(PARAM % 'minutos_sin_reporte', str(sin))
        ruido_anterior = self.env['adt.flota360.gps.dispositivo']._config()['palabras_ruido']
        if 'palabras_ruido' in valores:
            ICP.set_param(PARAM % 'palabras_ruido', ' '.join(sorted(palabras_ruido(valores['palabras_ruido']))))
        if 'alertas' in valores:
            ICP.set_param(PARAM % 'alertas', ' '.join(a for a in valores['alertas'] or [] if a in ALERTABLES))
        if 'alarmas' in valores:
            ICP.set_param(PARAM % 'alarmas', ' '.join(a for a in valores['alarmas'] or [] if a in ALARMAS))
        if 'destinatarios' in valores:
            ICP.set_param(PARAM % 'destinatarios', ' '.join(str(int(u)) for u in valores['destinatarios'] or []))
        if 'crear_vehiculos' in valores:
            ICP.set_param(PARAM % 'crear_vehiculos', '1' if valores['crear_vehiculos'] else '0')
        if 'modelo_id' in valores:
            ICP.set_param(PARAM % 'modelo_id', str(int(valores['modelo_id'] or 0)))
        cfg = self.env['adt.flota360.gps.dispositivo']._config()
        if cfg['crear_vehiculos'] and not cfg['modelo_id']:
            raise ValidationError(_('Para crear vehículos automáticamente elige el modelo con el que se crean.'))
        cron = self.env.ref('adt_flota_360.cron_gps_monitor', raise_if_not_found=False)
        if cron and frecuencia:
            cron.sudo().write({'interval_number': frecuencia, 'interval_type': 'minutes'})
        if cfg['palabras_ruido'] != ruido_anterior:
            Disp = self.env['adt.flota360.gps.dispositivo'].sudo()
            Disp.search([('vinculo_manual', '=', False)]).rematch()
        return self.gps_config()

    @api.model
    def gps_regenerar_webhook(self):
        self._gps_check(GRUPO_MANAGER)
        self.env['ir.config_parameter'].sudo().set_param(PARAM % 'webhook_token', secrets.token_urlsafe(24))
        return self.gps_config()

    @api.model
    def gps_probar_notificacion(self):
        """Envía por el bus de Odoo una alerta de prueba solo al usuario actual: valida que
        las notificaciones llegan al instante a este navegador."""
        self._gps_check()
        ahora = fields.Datetime.to_string(fields.Datetime.now())
        self.env['bus.bus'].sudo()._sendone(self.env.user.partner_id, BUS_TIPO, {'prueba': True, 'eventos': [{
            'id': 0, 'tipo': 'prueba', 'tipo_label': 'Prueba', 'nivel': 'critico', 'placa': 'PRUEBA',
            'mensaje': 'Alerta de prueba enviada a las %s' % ahora, 'motivo': 'Si ves esto, las alertas en tiempo real llegan a este navegador.',
            'cliente': '', 'dispositivo_id': False, 'fecha': ahora, 'geocerca': '',
        }]})
        return True

    @api.model
    def gps_alertas(self, desde_id=None):
        """Respaldo del bus para el servicio de notificaciones: eventos de alerta posteriores
        a `desde_id`. Sin `desde_id` solo devuelve el último id (no se notifica el pasado)."""
        if not self.env.user.has_group(GRUPO_USUARIO):
            return {'activo': False}
        cfg = self.env['adt.flota360.gps.dispositivo']._config()
        Evento = self.env['adt.flota360.gps.evento'].sudo()
        ultimo = Evento.search([], limit=1).id or 0
        res = {'activo': True, 'ultimo_id': ultimo, 'eventos': []}
        if not desde_id or (cfg['destinatarios'] and self.env.user.id not in cfg['destinatarios']):
            return res
        eventos = Evento.search([('id', '>', int(desde_id)), ('tipo', 'in', cfg['alertas'])], limit=MAX_ALERTAS)
        info = self._gps_vehiculos({e.vehicle_id.id for e in eventos if e.vehicle_id})
        res['eventos'] = [e._alerta_dict(info) for e in eventos.sorted('id')]
        return res

    # --- Integración con la ficha de Flota 360 ------------------------

    def _gps_monitor_por_vehiculo(self, ids):
        """{vehicle_id: dispositivo} del monitoreo, priorizando el que reportó más reciente."""
        if not self.env.user.has_group(GRUPO_USUARIO):
            return {}
        Disp = self.env['adt.flota360.gps.dispositivo'].sudo()
        res = {}
        minimo = datetime.min
        for d in Disp.search([('vehicle_id', 'in', list(ids))]).sorted(lambda r: r.ultimo_reporte or minimo, reverse=True):
            res.setdefault(d.vehicle_id.id, d)
        return res

    def _lote_gps(self, ids):
        """El chip «GPS» y el filtro «GPS sin señal» del buscador usan el monitoreo cuando
        existe (se actualiza cada minuto para toda la flota)."""
        res = super()._lote_gps(ids)
        if not self.env['adt.flota360.gps.dispositivo'].sudo().search([], limit=1):
            return res
        res = dict(res or {})
        for vid, d in self._gps_monitor_por_vehiculo(ids).items():
            res[vid] = {'vehicle_id': (vid, d.vehicle_id.display_name),
                        'gps_status': 'online' if d.estado in REPORTA else 'offline',
                        'gps_last_update': d.ultimo_reporte}
        return res

    def _seccion_gps(self, v, hoy):
        sec = super()._seccion_gps(v, hoy)
        d = self._gps_monitor_por_vehiculo([v.id]).get(v.id)
        if not d:
            return sec
        nivel = NIVEL_ESTADO.get(d.estado, 'neutral')
        if d.estado == 'reportando' and not d.posicion_valida:
            nivel = 'atencion'
        tiempo = _tiempo(int((fields.Datetime.now() - d.ultimo_reporte).total_seconds() // 60)) if d.ultimo_reporte else ''
        texto = dict(ESTADOS).get(d.estado)
        if d.estado in ('sin_reporte', 'demorado') and tiempo:
            texto = '%s hace %s' % (texto, tiempo)
        ver = {'tipo': 'cliente', 'tag': 'adt_flota_360_gps', 'params': {'dispositivo_id': d.id},
               'label': 'Ver en monitoreo GPS', 'icon': 'fa-heartbeat', 'primary': d.estado in NO_REPORTA}
        if not sec or sec.get('vacio'):
            acciones = [ver]
            if d.latitud or d.longitud:
                acciones.append({'tipo': 'url', 'url': 'https://www.google.com/maps?q=%s,%s' % (d.latitud, d.longitud),
                                 'label': 'Ver en mapa', 'icon': 'fa-map'})
            acciones += [a for a in (sec or {}).get('acciones', [])]
            return {
                'key': 'gps', 'titulo': 'GPS / Traccar', 'icon': 'fa-map-marker',
                'frase': {'nivel': nivel, 'texto': texto, 'detalle': d.motivo or ''},
                'gps': {
                    'status': 'online' if d.estado in REPORTA else 'offline', 'estado': texto,
                    'ultimo': fields.Datetime.to_string(d.ultimo_reporte) if d.ultimo_reporte else False,
                    'refrescado': fields.Datetime.to_string(d.sincronizado) if d.sincronizado else False,
                    'direccion': d.direccion or '', 'lat': d.latitud, 'lon': d.longitud,
                },
                'kpis': [
                    {'label': 'Velocidad', 'texto': '%.0f km/h' % (d.velocidad_kmh or 0)},
                    {'label': 'Batería', 'texto': '%.0f %%' % d.bateria if d.bateria else '—'},
                    {'label': 'Km', 'texto': '{:,.0f}'.format(d.km_total) if d.km_total else '—'},
                    {'label': 'IMEI', 'texto': d.imei or '—'},
                ],
                'acciones': acciones,
            }
        sec['frase'] = {'nivel': nivel, 'texto': texto, 'detalle': d.motivo or ''}
        sec.setdefault('acciones', []).insert(0, ver)
        return sec
