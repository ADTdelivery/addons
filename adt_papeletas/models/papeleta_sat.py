# -*- coding: utf-8 -*-
"""Espejo de las papeletas del SAT de Lima.

La sincronización (monitor en EC2 -> /api/papeletas/sat/import) mantiene al día
la papeleta interna (`adt.papeleta`) vinculada, sin intervención manual:

* papeleta nueva en el SAT -> se vincula por número o se crea la interna;
* cambian importe o fecha en el SAT -> se actualizan en la interna;
* deja de figurar en una consulta completa, o el SAT la muestra pagada ->
  la interna (y sus cuotas pendientes) pasa a pagada;
* vuelve a figurar después de eso -> actividad para revisarla (una papeleta
  pagada ya no se puede modificar).

Todo queda en el chatter de la papeleta interna.
"""
import base64
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

PARAM_TOKEN = 'adt_papeletas.sat_token'
PARAM_FECHA_INICIO = 'adt_papeletas.sat_fecha_inicio_auto'

# Estados de consulta del monitor
CON_PAPELETAS = 'con_papeletas'
SIN_PAPELETAS = 'sin_papeletas'

MIMETYPES = {
    b'%PDF-': 'application/pdf',
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'II*\x00': 'image/tiff',
    b'MM\x00*': 'image/tiff',
}
MAX_ARCHIVO = 10 * 1024 * 1024
# Una papeleta pendiente con más días que estos (desde la infracción) pasa a alerta.
DIAS_ALERTA = 7
# Estado del SAT que ya cuenta como pagado (texto libre del portal).
ESTADOS_PAGADOS = ('pagad', 'cancelad')
LIMA = timezone(timedelta(hours=-5))


def normalizar(texto):
    """Placa / número sin espacios, guiones ni símbolos, en mayúsculas."""
    return re.sub(r'[^A-Z0-9]', '', (texto or '').upper())


def _fecha(valor):
    """'15/03/2026' -> date. Devuelve False si no se reconoce."""
    valor = (valor or '').strip()[:10]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    return False


def _fecha_hora(valor):
    """ISO con zona ('2026-10-17T12:22:31-05:00') -> datetime UTC naive."""
    if not valor:
        return fields.Datetime.now()
    try:
        dt = datetime.fromisoformat(valor)
    except ValueError:
        return fields.Datetime.now()
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=LIMA)  # el monitor corre en hora de Lima
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _fecha_lima(utc_naive):
    """Datetime UTC naive (como se guarda) -> fecha en Lima."""
    return (utc_naive.replace(tzinfo=timezone.utc).astimezone(LIMA)).date()


def _numero(valor):
    if valor in (None, ''):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        limpio = re.sub(r'[^0-9.]', '', str(valor).replace(',', ''))
        try:
            return float(limpio) if limpio else None
        except ValueError:
            return None


class ADTPapeletaSat(models.Model):
    _name = 'adt.papeleta.sat'
    _description = 'Papeleta SAT Lima'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'vigente desc, fecha_infraccion desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='N° Papeleta / Código de pago', required=True, index=True, readonly=True)
    placa = fields.Char(string='Placa', index=True, readonly=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', index=True, tracking=True)
    papeleta_id = fields.Many2one('adt.papeleta', string='Papeleta interna', index=True,
                                  ondelete='set null', tracking=True,
                                  help='Papeleta del flujo interno (captura, cobranza) que corresponde a esta papeleta del SAT.')
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Moneda', readonly=True)

    # Datos que muestra el SAT
    reglamento = fields.Char(string='Reglamento', readonly=True)
    codigo_falta = fields.Char(string='Falta', readonly=True)
    fecha_infraccion = fields.Date(string='Fecha infracción / emisión', readonly=True)
    importe = fields.Monetary(string='Importe', readonly=True, tracking=True)
    gastos_costas = fields.Monetary(string='Gastos / Costas', readonly=True, tracking=True)
    descuento = fields.Monetary(string='Descuento', readonly=True)
    deuda = fields.Monetary(string='Deuda', readonly=True, tracking=True)
    estado_sat = fields.Char(string='Estado SAT', readonly=True, tracking=True)
    licencia_conducir = fields.Char(string='Licencia de conducir', readonly=True)
    tipo_documento = fields.Char(string='Tipo doc. identidad', readonly=True)
    numero_documento = fields.Char(string='N° doc. identidad', readonly=True)
    numero_compromiso_pago = fields.Char(string='N° compromiso de pago', readonly=True)
    flag_exc = fields.Char(string='bFlagExc', readonly=True)
    url_copia = fields.Char(string='URL copia SAT', readonly=True)
    estado_copia = fields.Char(string='Estado de la copia', readonly=True)
    error_copia = fields.Char(string='Error de la copia', readonly=True)
    datos_raw = fields.Text(string='Datos originales (JSON)', readonly=True)

    # Seguimiento entre consultas
    vigente = fields.Boolean(string='Figura en el SAT', default=True, readonly=True, tracking=True,
                             help='Falso cuando la papeleta dejó de aparecer en una consulta completa del SAT '
                                  '(pago, anulación o descargo: no confirma el pago).')
    primera_vez_visto = fields.Datetime(string='Primera vez vista', readonly=True)
    ultima_vez_visto = fields.Datetime(string='Última consulta', readonly=True)
    resuelta_en = fields.Datetime(string='Dejó de figurar', readonly=True)
    revision = fields.Selection([
        ('pendiente', 'Por revisar'),
        ('pagada', 'Pago confirmado'),
        ('anulada', 'Anulada / descargo'),
        ('otro', 'Otro'),
    ], string='Revisión', tracking=True,
        help='"Pago confirmado" cuando la papeleta interna se marcó pagada al dejar de figurar en el SAT; '
             '"Por revisar" si eso no fue posible.')
    importacion_id = fields.Many2one('adt.papeleta.sat.import', string='Última importación', readonly=True)

    # Estado de pago: nace pendiente y pasa a pagado cuando el SAT la muestra pagada o
    # deja de figurar en una consulta completa (mismo criterio que la sincronización).
    estado_pago = fields.Selection([
        ('pendiente', 'Pendiente de pago'),
        ('pagado', 'Pagado'),
    ], string='Estado de pago', compute='_compute_estado_pago', store=True, index=True, tracking=True)
    dias = fields.Integer(string='Días', compute='_compute_dias',
                          help='Días desde la infracción (o desde que se vio en el SAT, si no tiene fecha).')
    alerta_dias = fields.Boolean(string='Más de una semana', compute='_compute_dias',
                                 help='Pendiente de pago con más de %s días.' % DIAS_ALERTA)

    attachment_ids = fields.One2many('ir.attachment', 'res_id', string='Copias SAT',
                                     domain=[('res_model', '=', 'adt.papeleta.sat')])
    imagen = fields.Binary(string='Copia', compute='_compute_imagen')
    copias_count = fields.Integer(string='Copias', compute='_compute_imagen')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'La papeleta SAT ya existe.'),
    ]

    @api.depends('vigente', 'estado_sat')
    def _compute_estado_pago(self):
        for rec in self:
            pagada = any(c in (rec.estado_sat or '').lower() for c in ESTADOS_PAGADOS)
            rec.estado_pago = 'pagado' if pagada or not rec.vigente else 'pendiente'

    @api.depends('fecha_infraccion', 'primera_vez_visto', 'estado_pago')
    def _compute_dias(self):
        hoy = fields.Date.context_today(self)
        for rec in self:
            desde = rec.fecha_infraccion or (rec.primera_vez_visto and _fecha_lima(rec.primera_vez_visto))
            rec.dias = (hoy - desde).days if desde else 0
            rec.alerta_dias = rec.estado_pago == 'pendiente' and rec.dias > DIAS_ALERTA

    def _imagenes(self):
        self.ensure_one()
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name), ('res_id', '=', self.id),
        ], order='id desc')

    def _compute_imagen(self):
        for rec in self:
            adjuntos = rec._imagenes() if rec.id else self.env['ir.attachment']
            rec.copias_count = len(adjuntos)
            imagen = adjuntos.filtered(lambda a: (a.mimetype or '').startswith('image/'))[:1]
            rec.imagen = imagen.datas if imagen else False

    # ------------------------------------------------------------------ setup
    @api.model
    def _init_parametros(self):
        """Llamado desde data/: genera el token y la fecha de puesta en marcha una sola vez."""
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param(PARAM_TOKEN):
            icp.set_param(PARAM_TOKEN, secrets.token_urlsafe(32))
        if not icp.get_param(PARAM_FECHA_INICIO):
            icp.set_param(PARAM_FECHA_INICIO, fields.Date.to_string(fields.Date.context_today(self)))

    @api.model
    def _fecha_inicio_auto(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_FECHA_INICIO)
        return fields.Date.to_date(valor) if valor else False

    # ------------------------------------------------------------- búsquedas
    @api.model
    def _buscar_vehiculo(self, placa):
        if not placa:
            return self.env['fleet.vehicle']
        self.env['fleet.vehicle'].flush(['license_plate', 'active'])
        self.env.cr.execute("""
            SELECT id FROM fleet_vehicle
             WHERE regexp_replace(upper(coalesce(license_plate, '')), '[^A-Z0-9]', '', 'g') = %s
             ORDER BY active DESC, id DESC
             LIMIT 1
        """, (placa,))
        fila = self.env.cr.fetchone()
        return self.env['fleet.vehicle'].browse(fila[0]) if fila else self.env['fleet.vehicle']

    @api.model
    def _candidatas_internas(self, numero):
        """Hasta 2 papeletas internas con el mismo número (2 = ambiguo)."""
        if not numero:
            return self.env['adt.papeleta']
        self.env['adt.papeleta'].flush(['name'])
        clave = normalizar(numero)
        # Los números del SAT son dígitos; las papeletas manuales pueden tener
        # prefijos ("N° 15394818", "PAP-015394818"), así que se comparan solo dígitos.
        digitos = clave.lstrip('0') if clave.isdigit() else None
        self.env.cr.execute("""
            SELECT id FROM adt_papeleta
             WHERE regexp_replace(upper(coalesce(name, '')), '[^A-Z0-9]', '', 'g') = %s
                OR (%s IS NOT NULL
                    AND ltrim(regexp_replace(coalesce(name, ''), '[^0-9]', '', 'g'), '0') = %s)
             ORDER BY id
             LIMIT 2
        """, (clave, digitos, digitos))
        return self.env['adt.papeleta'].browse([f[0] for f in self.env.cr.fetchall()])

    @api.model
    def _buscar_papeleta_interna(self, numero):
        candidatas = self._candidatas_internas(numero)
        if len(candidatas) > 1:
            _logger.warning('Papeleta SAT %s coincide con varias papeletas internas; no se vincula.', numero)
            return self.env['adt.papeleta']
        return candidatas

    # --------------------------------------------------------- sincronización
    @api.model
    def _procesar_consulta(self, payload, importacion):
        """Aplica una consulta del monitor (una placa). Devuelve contadores."""
        placa = normalizar(payload.get('placa'))
        estado = payload.get('estado')
        consultado_en = _fecha_hora(payload.get('consultado_en'))
        papeletas = payload.get('papeletas') or []
        res = {'nuevas_sat': 0, 'actualizadas': 0, 'vinculadas': 0, 'creadas': 0, 'resueltas': 0,
               'pagadas': 0, 'internas_actualizadas': 0}

        vehiculo = self._buscar_vehiculo(placa)
        meta_vehicle = (payload.get('metadata') or {}).get('vehicle_id')
        if not vehiculo and meta_vehicle:
            vehiculo = self.env['fleet.vehicle'].browse(int(meta_vehicle)).exists()
        importacion.vehicle_id = vehiculo

        if estado not in (CON_PAPELETAS, SIN_PAPELETAS) and not papeletas:
            importacion.state = 'omitido'
            return res

        vistos = set()
        for datos in papeletas:
            numero = (datos.get('numero_papeleta') or '').strip()
            if not numero:
                continue
            vistos.add(numero)
            rec, nueva = self._upsert(numero, placa, vehiculo, datos, consultado_en, importacion)
            res['nuevas_sat' if nueva else 'actualizadas'] += 1
            accion = rec._vincular_o_crear()
            if accion:
                res[accion] += 1
            accion = rec._sincronizar_interna(consultado_en)
            if accion:
                res[accion] += 1

        # Solo una consulta completa permite decir que algo dejó de figurar.
        if estado in (CON_PAPELETAS, SIN_PAPELETAS) and placa:
            previas = self.search([
                ('placa', '=', placa), ('vigente', '=', True), ('name', 'not in', list(vistos)),
                '|', ('ultima_vez_visto', '=', False), ('ultima_vez_visto', '<', consultado_en),
            ])
            for rec in previas:
                res['resueltas'] += 1
                if rec._marcar_resuelta(consultado_en):
                    res['pagadas'] += 1
        return res

    @api.model
    def _upsert(self, numero, placa, vehiculo, datos, consultado_en, importacion):
        rec = self.search([('name', '=', numero)], limit=1)
        valores = {
            'placa': normalizar(datos.get('placa')) or placa,
            'reglamento': datos.get('reglamento') or False,
            'codigo_falta': datos.get('codigo_falta') or False,
            'fecha_infraccion': _fecha(datos.get('fecha_infraccion')),
            'importe': _numero(datos.get('importe_num', datos.get('importe'))) or 0.0,
            'gastos_costas': _numero(datos.get('gastos_costas_num', datos.get('gastos_costas'))) or 0.0,
            'descuento': _numero(datos.get('descuento_num', datos.get('descuento'))) or 0.0,
            'deuda': _numero(datos.get('deuda_num', datos.get('deuda'))) or 0.0,
            'estado_sat': datos.get('estado') or False,
            'licencia_conducir': datos.get('licencia_conducir') or False,
            'tipo_documento': datos.get('tipo_documento_identidad') or False,
            'numero_documento': datos.get('numero_documento_identidad') or False,
            'numero_compromiso_pago': datos.get('numero_compromiso_pago') or False,
            'flag_exc': (datos.get('raw') or {}).get('bflagexc') or False,
            'url_copia': datos.get('url_copia') or False,
            'estado_copia': datos.get('estado_copia') or False,
            'error_copia': datos.get('error_copia') or False,
            'datos_raw': json.dumps(datos.get('raw') or {}, ensure_ascii=False),
            'importacion_id': importacion.id,
        }
        if rec and ((rec.ultima_vez_visto and rec.ultima_vez_visto > consultado_en)
                    or (rec.resuelta_en and rec.resuelta_en >= consultado_en)):
            # Un reenvío antiguo no debe pisar datos más recientes.
            rec._guardar_archivos(datos.get('archivos') or [])
            return rec, False
        nueva = not rec
        valores.update({'vigente': True, 'ultima_vez_visto': consultado_en, 'resuelta_en': False})
        if vehiculo and (nueva or not rec.vehicle_id):
            valores['vehicle_id'] = vehiculo.id
        if nueva:
            valores.update({'name': numero, 'primera_vez_visto': consultado_en})
            rec = self.create(valores)
        else:
            reaparece = not rec.vigente
            pagada_por_sat = reaparece and rec.revision == 'pagada'
            if reaparece:
                valores['revision'] = False
            rec.write(valores)
            if reaparece:
                rec.message_post(body=_('La papeleta volvió a figurar en el SAT.'))
            if pagada_por_sat and rec.papeleta_id.state == 'pagado':
                rec._avisar_interna(
                    _('La papeleta %s volvió a figurar en el SAT (estado: %s, deuda %.2f) después de marcarse pagada '
                      'automáticamente. Verifique el pago.') % (rec.name, rec.estado_sat or '-', rec.deuda),
                    _('Papeleta pagada volvió a figurar en el SAT'))
        rec._guardar_archivos(datos.get('archivos') or [])
        return rec, nueva

    def _guardar_archivos(self, archivos):
        self.ensure_one()
        Adjunto = self.env['ir.attachment'].sudo()
        for archivo in archivos:
            try:
                contenido = base64.b64decode(archivo.get('datos') or '', validate=True)
            except (ValueError, TypeError):
                _logger.warning('Papeleta SAT %s: archivo con base64 inválido', self.name)
                continue
            if not contenido or len(contenido) > MAX_ARCHIVO:
                continue
            mimetype = next((m for firma, m in MIMETYPES.items() if contenido.startswith(firma)), None)
            if not mimetype:
                continue  # solo imágenes/PDF reconocibles
            checksum = hashlib.sha1(contenido).hexdigest()
            if Adjunto.search_count([('res_model', '=', self._name), ('res_id', '=', self.id),
                                     ('checksum', '=', checksum)]):
                continue
            nombre = re.sub(r'[^A-Za-z0-9_.-]', '_', archivo.get('nombre') or '') or checksum[:16]
            Adjunto.create({
                'name': 'SAT_%s_%s' % (self.name, nombre),
                'datas': base64.b64encode(contenido),
                'mimetype': mimetype,
                'res_model': self._name,
                'res_id': self.id,
            })

    def _vincular_o_crear(self):
        """Vincula con la papeleta interna del mismo número o, si corresponde, la crea.
        Devuelve 'vinculadas', 'creadas' o None."""
        self.ensure_one()
        if self.papeleta_id:
            return None
        existente = self._buscar_papeleta_interna(self.name)
        if existente:
            self.papeleta_id = existente
            existente.message_post(body=_(
                'Vinculada con la papeleta SAT %s (estado SAT: %s, importe %.2f, deuda %.2f).')
                % (self.name, self.estado_sat or '-', self.importe, self.deuda))
            return 'vinculadas'
        inicio = self._fecha_inicio_auto()
        if (self.vehicle_id and self.vigente and self.fecha_infraccion and inicio
                and self.fecha_infraccion >= inicio):
            try:
                with self.env.cr.savepoint():
                    self._crear_papeleta_interna()
                return 'creadas'
            except (UserError, ValidationError) as exc:
                self.message_post(body=_('No se pudo crear la papeleta interna: %s') % exc)
        return None

    def _crear_papeleta_interna(self):
        self.ensure_one()
        if self.papeleta_id:
            raise UserError(_('La papeleta SAT %s ya está vinculada.') % self.name)
        if not self.vehicle_id:
            raise UserError(_('Asigne un vehículo a la papeleta SAT %s antes de crear la interna.') % self.name)
        if not self.fecha_infraccion:
            raise UserError(_('La papeleta SAT %s no tiene fecha de infracción.') % self.name)
        if self._candidatas_internas(self.name):
            raise UserError(_('Ya existe una papeleta interna con el número %s; vincúlela.') % self.name)
        detalle = _('Importada del SAT Lima. Falta %s (%s). Estado SAT: %s. Licencia: %s.') % (
            self.codigo_falta or '-', self.reglamento or '-', self.estado_sat or '-', self.licencia_conducir or '-')
        papeleta = self.env['adt.papeleta'].create({
            'name': self.name,
            'fecha_papeleta': self.fecha_infraccion,
            'monto': self.importe,
            'vehicle_id': self.vehicle_id.id,
            'company_id': self.company_id.id or self.env.company.id,
            'detalle': detalle,
            'origen': 'sat',
            'attachment_ids': [(6, 0, self._imagenes().ids)],
        })
        self.papeleta_id = papeleta
        return papeleta

    def _sincronizar_interna(self, cuando):
        """Lleva a la papeleta interna lo que dice el SAT. Devuelve 'pagadas',
        'internas_actualizadas' o None."""
        self.ensure_one()
        papeleta = self.papeleta_id
        if not papeleta or papeleta.state == 'pagado' or not self.vigente:
            return None
        if self.ultima_vez_visto and self.ultima_vez_visto > cuando:
            return None  # reenvío antiguo
        consulta = _fecha_lima(cuando).strftime('%d/%m/%Y')
        if 'pagad' in (self.estado_sat or '').lower():
            return 'pagadas' if self._pagar_interna(cuando, _(
                'Marcada como <b>pagada</b> automáticamente: el SAT Lima la muestra como «%s» (consulta del %s).')
                % (self.estado_sat, consulta)) else None
        valores, cambios = {}, []
        if self.importe and abs((papeleta.monto or 0.0) - self.importe) > 0.009:
            valores['monto'] = self.importe
            cambios.append(_('monto %.2f → %.2f') % (papeleta.monto or 0.0, self.importe))
        if self.fecha_infraccion and papeleta.fecha_papeleta != self.fecha_infraccion:
            valores['fecha_papeleta'] = self.fecha_infraccion
            cambios.append(_('fecha %s → %s') % (papeleta.fecha_papeleta and papeleta.fecha_papeleta.strftime('%d/%m/%Y') or '-',
                                                 self.fecha_infraccion.strftime('%d/%m/%Y')))
        if not valores:
            return None
        try:
            with self.env.cr.savepoint():
                papeleta.with_context(sat_sync=True).write(valores)
        except (UserError, ValidationError) as exc:
            self.message_post(body=_('No se pudo actualizar la papeleta interna: %s') % exc)
            return None
        aviso = ''
        if 'monto' in valores and papeleta.cuotas_ids:
            if papeleta.cantidad_cuotas and all(c.state == 'pendiente' for c in papeleta.cuotas_ids):
                papeleta.cuotas_ids.unlink()
                sincronizada = papeleta.with_context(sat_sync=True)
                sincronizada._generate_cuotas_for(sincronizada)
                aviso = _(' Se regeneraron las %s cuotas con el nuevo monto.') % len(papeleta.cuotas_ids)
            else:
                aviso = _(' Tiene cuotas pagadas: revise las pendientes para que sumen el nuevo monto.')
        papeleta.message_post(body=_('Actualizada desde el SAT Lima (consulta del %s): %s.%s')
                              % (consulta, ', '.join(cambios), aviso))
        return 'internas_actualizadas'

    def _pagar_interna(self, cuando, motivo):
        """Marca pagada la papeleta interna y sus cuotas pendientes. True si lo logró."""
        self.ensure_one()
        papeleta = self.papeleta_id
        try:
            with self.env.cr.savepoint():
                papeleta.cuotas_ids.filtered(lambda c: c.state == 'pendiente').write({'state': 'pagado'})
                papeleta.with_context(sat_sync=True).write({'state': 'pagado', 'fecha_pago': _fecha_lima(cuando)})
        except (UserError, ValidationError) as exc:
            self.message_post(body=_('No se pudo marcar como pagada la papeleta interna: %s') % exc)
            return False
        papeleta.message_post(body=motivo)
        self.revision = 'pagada'
        return True

    def _marcar_resuelta(self, cuando):
        """Dejó de figurar en una consulta completa: se toma como pagada. True si
        se marcó pagada la papeleta interna."""
        self.ensure_one()
        self.write({'vigente': False, 'resuelta_en': cuando, 'revision': 'pendiente'})
        papeleta = self.papeleta_id
        if not papeleta or papeleta.state == 'pagado':
            if papeleta:
                self.revision = 'pagada'
            return False
        if self._pagar_interna(cuando, _(
                'Marcada como <b>pagada</b> automáticamente: ya no figura como pendiente en el SAT Lima '
                '(consulta del %s).') % _fecha_lima(cuando).strftime('%d/%m/%Y')):
            return True
        self._avisar_interna(_('La papeleta %s dejó de figurar en el SAT, pero no se pudo marcar como pagada. '
                               'Verifique si fue pagada, anulada o descargada.') % papeleta.name,
                             _('Verificar pago en SAT'))
        return False

    def _avisar_interna(self, texto, resumen):
        """Mensaje y actividad en la papeleta interna para quien la registró."""
        papeleta = self.papeleta_id
        papeleta.message_post(body=texto)
        usuario = papeleta.create_uid
        if not usuario or usuario.id == self.env.ref('base.user_root').id:
            # Creada por la sincronización: se avisa al administrador.
            usuario = self.env.ref('base.user_admin', raise_if_not_found=False)
        if usuario and usuario.active and not usuario.share:
            try:
                papeleta.activity_schedule('mail.mail_activity_data_todo', user_id=usuario.id,
                                           summary=resumen, note=texto)
            except Exception:
                _logger.exception('No se pudo programar la actividad para la papeleta %s', papeleta.id)

    # ----------------------------------------------------------------- botones
    def action_crear_papeleta_interna(self):
        for rec in self:
            rec._crear_papeleta_interna()
        if len(self) == 1:
            return self.action_abrir_papeleta_interna()
        return True

    def action_abrir_papeleta_interna(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Papeleta'),
            'res_model': 'adt.papeleta',
            'res_id': self.papeleta_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_vincular_automatico(self):
        """Reintenta vehículo + vínculo por número (útil tras corregir placas en flota)."""
        for rec in self:
            if not rec.vehicle_id:
                rec.vehicle_id = self._buscar_vehiculo(rec.placa)
            if not rec.papeleta_id:
                existente = self._buscar_papeleta_interna(rec.name)
                if existente:
                    rec.papeleta_id = existente
        return True

    def action_ver_copias(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Copias SAT'),
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,tree,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
        }


class ADTPapeletaSatImport(models.Model):
    _name = 'adt.papeleta.sat.import'
    _description = 'Importación de consulta SAT'
    _order = 'id desc'

    name = fields.Char(string='Referencia', required=True)
    corrida_id = fields.Char(string='Corrida', index=True)
    placa = fields.Char(string='Placa', index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo')
    consultado_en = fields.Datetime(string='Consultado en')
    estado_consulta = fields.Char(string='Resultado SAT')
    mensaje = fields.Char(string='Mensaje SAT')
    total_papeletas = fields.Integer(string='Papeletas')
    total_deuda = fields.Float(string='Deuda total SAT')
    nuevas_sat = fields.Integer(string='Nuevas SAT')
    actualizadas = fields.Integer(string='Actualizadas')
    vinculadas = fields.Integer(string='Vinculadas')
    creadas = fields.Integer(string='Papeletas internas creadas')
    resueltas = fields.Integer(string='Dejaron de figurar')
    pagadas = fields.Integer(string='Marcadas pagadas', help='Papeletas internas marcadas pagadas por esta consulta.')
    internas_actualizadas = fields.Integer(string='Internas actualizadas',
                                           help='Papeletas internas con importe o fecha actualizados desde el SAT.')
    state = fields.Selection([
        ('ok', 'Procesada'),
        ('omitido', 'Omitida (consulta fallida)'),
        ('error', 'Error'),
    ], string='Estado', default='ok', index=True)
    error = fields.Text(string='Error')
    payload = fields.Text(string='Payload (sin archivos)')
    ejecucion_id = fields.Many2one('adt.papeleta.sat.ejecucion', string='Ejecución', index=True,
                                   ondelete='set null', readonly=True)

    @api.model
    def _payload_sin_archivos(self, payload):
        copia = dict(payload)
        for clave in ('papeletas', 'nuevas', 'resueltas'):
            copia[clave] = [{k: v for k, v in p.items() if k != 'archivos'} for p in payload.get(clave) or []]
        return json.dumps(copia, ensure_ascii=False, indent=1)

    @api.model
    def registrar(self, payload):
        """Guarda la importación y aplica la consulta. Un error no deja cambios a medias."""
        placa = normalizar(payload.get('placa'))
        importacion = self.create({
            'name': '%s · %s' % (placa or '?', payload.get('consultado_en') or ''),
            'corrida_id': payload.get('corrida_id') or False,
            'placa': placa,
            'consultado_en': _fecha_hora(payload.get('consultado_en')),
            'estado_consulta': payload.get('estado'),
            'mensaje': (payload.get('mensaje') or '')[:250],
            'total_papeletas': payload.get('total_papeletas') or len(payload.get('papeletas') or []),
            'total_deuda': _numero(payload.get('total_deuda')) or 0.0,
            'payload': self._payload_sin_archivos(payload),
        })
        importacion._aplicar(payload)
        importacion._informar_ejecucion(payload)
        return importacion

    def _informar_ejecucion(self, payload):
        """Consultas lanzadas desde un programa/ejecución: actualiza su línea y el avance."""
        self.ensure_one()
        ejecucion_id = (payload.get('metadata') or {}).get('ejecucion_id')
        if not str(ejecucion_id or '').isdigit():
            return
        ejecucion = self.env['adt.papeleta.sat.ejecucion'].browse(int(ejecucion_id)).exists()
        if not ejecucion:
            return
        self.ejecucion_id = ejecucion
        try:
            with self.env.cr.savepoint():
                ejecucion._registrar_import(self, payload)
        except Exception:  # noqa: BLE001 - el informe nunca debe impedir guardar las papeletas
            _logger.exception('No se pudo actualizar la ejecución %s con %s', ejecucion_id, self.name)

    def _aplicar(self, payload):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                res = self.env['adt.papeleta.sat']._procesar_consulta(payload, self)
            self.write(dict(res, error=False, state=self.state if self.state == 'omitido' else 'ok'))
        except Exception as exc:  # noqa: BLE001 - se registra y se informa al monitor
            _logger.exception('Error importando consulta SAT %s', self.name)
            self.write({'state': 'error', 'error': '%s: %s' % (type(exc).__name__, exc)})

    def action_reprocesar(self):
        for rec in self:
            rec.state = 'ok'
            rec._aplicar(json.loads(rec.payload or '{}'))
        return True
