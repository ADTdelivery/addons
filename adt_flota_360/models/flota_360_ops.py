# -*- coding: utf-8 -*-
"""Flota 360: operaciones nativas de la vista (sin abrir formularios de Odoo).

* Formularios simplificados (papeleta, captura, orden de taller, vehículo,
  cliente, expediente): el servidor describe los campos y la vista JS los pinta.
  Todo se guarda con el ORM y los permisos del usuario, así que las reglas y
  validaciones de cada módulo siguen aplicando.
* Documentos: subir, revisar (aceptar / rechazar) y quitar las fotos del
  expediente y los archivos del vehículo.
* Crédito: simulación del cronograma (misma regla que
  adt.comercial.cuentas.generar_cuotas) y creación de la cuenta.
"""
import base64
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MAX_ARCHIVO_MB = 15
DIAS_PERIODO = {'semanal': 7, 'quincena': 15, 'mensual': 30}

# Catálogo de documentos del expediente, en el orden del formulario de adt_expedientes.
# (clave de estado, etiqueta, [(campo binario, lado)], condición)
#   clave -> estado_<clave> / obs_<clave> (None: el documento no se revisa)
#   condición -> cuándo aplica según el cliente (ver _aplica_documento)
EXPEDIENTE_GRUPOS = [
    ('identidad', 'Identidad', [
        ('foto_dni', 'DNI', [('foto_dni_frente', 'Anverso'), ('foto_dni_reverso', 'Reverso')], 'peruano'),
        ('foto_ce', 'Carnet de extranjería', [('foto_ce_frente', 'Anverso'), ('foto_ce_reverso', 'Reverso')], 'extranjero'),
        ('foto_pasaporte', 'Pasaporte (histórico)', [('foto_pasaporte_frente', 'Anverso'),
                                                    ('foto_pasaporte_reverso', 'Reverso')], 'cargado'),
        ('foto_licencia', 'Licencia de conducir', [('foto_licencia', '')], None),
    ]),
    ('solvencia', 'Ingresos y solvencia', [
        ('foto_recibo', 'Recibo de servicios', [('foto_recibo', '')], None),
        ('foto_sentinel', 'Sentinel', [('foto_sentinel_1', 'Score'), ('foto_sentinel_2', 'Deudas')], None),
        ('foto_ingresos', 'Ingresos (histórico)', [('foto_ingresos', '')], 'cargado'),
    ]),
    ('trabajo', 'Trabajo', [
        ('foto_moto', 'Foto en la moto', [('foto_moto', '')], 'mototaxista'),
        ('foto_soat', 'SOAT de su moto', [('foto_soat', '')], 'mototaxista'),
        ('foto_tarjeta', 'Tarjeta de propiedad de su moto', [('foto_tarjeta_propiedad_frente', 'Frente'),
                                                             ('foto_tarjeta_propiedad_reverso', 'Reverso')], 'mototaxista'),
        ('foto_lugar_trabajo', 'Lugar de trabajo', [('foto_lugar_trabajo', '')], 'no_mototaxista'),
        ('foto_lugar_negocio', 'Lugar del negocio', [('foto_lugar_negocio', '')], 'no_mototaxista'),
        ('foto_boletas', 'Boletas / contratos / recibos', [('foto_boletas', '')], 'no_mototaxista'),
        ('foto_estado_cuenta', 'Estado de cuenta', [('foto_estado_cuenta', '')], 'no_mototaxista'),
    ]),
    ('domicilio', 'Domicilio', [
        ('foto_ubicacion', 'Ubicación actual', [('foto_ubicacion_actual', '')], None),
        ('foto_fachada', 'Fachada del domicilio', [('foto_fachada_domicilio', '')], None),
        ('foto_contrato', 'Contrato de alquiler', [('foto_contrato_alquiler', '')], 'alquilada'),
        ('foto_vivienda', 'Vivienda (histórico)', [('foto_vivienda', '')], 'cargado'),
    ]),
    ('final', 'Fase final', [
        (None, 'Foto de entrega', [('foto_entrega', '')], None),
    ]),
    ('beneficiario', 'Beneficiario (opcional)', [
        ('foto_beneficiario', 'Documento del beneficiario', [('foto_beneficiario_documento', '')], 'opcional'),
    ]),
]

# Archivos del vehículo: campo binario -> (etiqueta, campo con el nombre del archivo, requerido).
VEHICULO_DOCUMENTOS = [
    ('soat_attachment', 'SOAT', 'soat_filename', True),
    ('tarjeta_propiedad_attachment', 'Tarjeta de propiedad', 'tarjeta_propiedad_filename', True),
    ('contrato_attachment', 'Contrato', 'contrato_filename', True),
    ('foto_entrega', 'Foto de entrega', 'foto_entrega_filename', True),
    ('chip_gnv_attachment', 'Chip GNV', 'chip_gnv_filename', False),
]

# Modelos que se pueden consultar desde los selectores de la vista.
OPCIONES_MODELOS = {
    'res.partner': [],
    'res.users': [('share', '=', False)],
    'fleet.vehicle.state': [],
    'adt.comercial.financiera': [],
}

TIPOS_CAMPO = {
    'char': 'char', 'text': 'text', 'html': 'text', 'date': 'date', 'datetime': 'datetime',
    'float': 'float', 'monetary': 'monetary', 'integer': 'integer', 'selection': 'selection',
    'many2one': 'many2one', 'boolean': 'boolean', 'binary': 'file', 'many2many': 'adjuntos',
}


class AdtFlota360Ops(models.AbstractModel):
    _inherit = 'adt.flota360'

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _vehiculo(self, vehicle_id):
        vehiculo = self.env['fleet.vehicle'].browse(int(vehicle_id)).exists()
        if not vehiculo:
            raise UserError(_('El vehículo ya no existe.'))
        vehiculo.check_access_rule('read')
        return vehiculo

    def _decodificar(self, datos):
        """Valida y normaliza un archivo enviado en base64 desde la vista."""
        if not datos:
            return False
        if ',' in datos[:100] and datos.startswith('data:'):
            datos = datos.split(',', 1)[1]
        try:
            crudo = base64.b64decode(datos, validate=True)
        except Exception:
            raise UserError(_('El archivo no se pudo leer. Vuelve a seleccionarlo.'))
        if len(crudo) > MAX_ARCHIVO_MB * 1024 * 1024:
            raise UserError(_('El archivo supera los %s MB permitidos.') % MAX_ARCHIVO_MB)
        return base64.b64encode(crudo)

    def _a_texto(self, campo, valor):
        if valor in (False, None):
            return False
        if campo.type == 'many2one':
            return [valor.id, valor.display_name] if valor else False
        if campo.type == 'date':
            return fields.Date.to_string(valor)
        if campo.type == 'datetime':
            return fields.Datetime.to_string(valor)
        if campo.type in ('binary', 'many2many'):
            return False
        return valor

    def _campo_spec(self, Model, nombre, **extra):
        """Describe un campo del modelo para la vista. None si el campo no existe."""
        campo = Model._fields.get(nombre)
        if not campo or campo.type not in TIPOS_CAMPO:
            return None
        spec = {
            'name': nombre,
            'label': campo.string,
            'type': TIPOS_CAMPO[campo.type],
            'required': bool(campo.required),
            'help': campo.help or '',
        }
        if campo.type == 'selection':
            spec['options'] = [list(o) for o in campo._description_selection(self.env)]
        elif campo.type == 'many2one':
            spec['model'] = campo.comodel_name
        spec.update(extra)
        return spec

    @api.model
    def opciones(self, modelo, termino='', limite=8):
        """Búsqueda para los selectores (many2one) de los formularios de la vista."""
        if modelo not in OPCIONES_MODELOS:
            raise AccessError(_('Modelo no permitido.'))
        Model = self.env[modelo]
        if not Model.check_access_rights('read', raise_exception=False):
            return []
        return [list(r) for r in Model.name_search(termino or '', OPCIONES_MODELOS[modelo], limit=limite)]

    # ------------------------------------------------------------------
    # Formularios
    # ------------------------------------------------------------------
    # Cada _form_<clave> devuelve:
    #   (registro o modelo, secciones [(titulo, [campos])], valores por defecto, fijos, título, ayuda)
    # `fijos` se escriben siempre (no los edita el usuario).

    def _form_papeleta(self, v, res_id, params):
        P = self._modelo('adt.papeleta', 'vehicle_id')
        if P is None:
            raise UserError(_('El módulo de papeletas no está disponible.'))
        rec = P.browse(res_id).exists() if res_id else P
        s = lambda n, **k: self._campo_spec(P, n, **k)
        secciones = [
            ('Papeleta', [s('name', label='N° de papeleta'), s('fecha_papeleta'), s('monto'), s('detalle', col=2)]),
            ('Prórroga', [s('tiene_prorroga'), s('dias_prorroga', visible=['tiene_prorroga']),
                          s('motivo_prorroga', col=2, visible=['tiene_prorroga'])]),
            ('Evidencias', [s('attachment_ids', label='Fotos o PDF de la papeleta', col=2)]),
        ]
        titulo = _('Editar papeleta %s') % rec.name if res_id else _('Registrar papeleta')
        return rec, secciones, {'fecha_papeleta': fields.Date.context_today(self)}, {'vehicle_id': v.id}, titulo, ''

    def _form_captura(self, v, res_id, params):
        C = self._modelo('adt.captura.record', 'cuenta_id')
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id')
        if C is None or Cuenta is None:
            raise UserError(_('El módulo de capturas no está disponible.'))
        cuentas = Cuenta.search([('vehiculo_id', '=', v.id), ('state', 'in', ('en_curso', 'aprobado'))], order='id desc')
        if not cuentas:
            raise UserError(_('Para registrar una captura el vehículo debe tener una cuenta en curso.'))
        s = lambda n, **k: self._campo_spec(C, n, **k)
        cuenta = s('cuenta_id', type='selection', options=[[c.id, c.display_name] for c in cuentas])
        secciones = [
            ('Captura', [cuenta, s('capture_type'), s('commitment_date', visible=['capture_type', 'compromiso']),
                         s('retention_reason'), s('intervention_fee'), s('notes', col=2)]),
            ('Evidencias', [s('evidencia_archivos', label='Fotos o videos de la captura', col=2)]),
        ]
        defaults = {'cuenta_id': cuentas[0].id, 'capture_type': 'inmediata', 'intervention_fee': 50.0}
        return C, secciones, defaults, {}, _('Registrar captura'), _(
            'El vehículo pasará al estado de captura correspondiente al guardar.')

    def _form_orden_taller(self, v, res_id, params):
        O = self._modelo('maintenance.work.order', 'vehicle_id', 'client_id')
        if O is None:
            raise UserError(_('El módulo de taller no está disponible.'))
        s = lambda n, **k: self._campo_spec(O, n, **k)
        secciones = [
            ('Ingreso', [s('client_id'), s('mechanic_id'), s('start_date'), s('mileage'),
                         s('entry_reason', col=2)]),
            ('Pago', [s('payer_type'), s('adt_contribution', visible=['payer_type', 'ambos'])]),
            ('Evidencia', [s('evidence_image', col=2)]),
        ]
        cliente = params.get('cliente_id') or v.driver_id.id
        defaults = {
            'client_id': cliente and [cliente, self.env['res.partner'].browse(cliente).display_name],
            'start_date': fields.Datetime.to_string(fields.Datetime.now()),
            'mileage': v.traccar_km_actual if 'traccar_km_actual' in v._fields else 0,
            'payer_type': 'cliente',
        }
        return O, secciones, defaults, {'vehicle_id': v.id}, _('Nueva orden de taller'), ''

    def _form_vehiculo(self, v, res_id, params):
        V = self.env['fleet.vehicle']
        s = lambda n, **k: self._campo_spec(V, n, **k)
        secciones = [
            ('Identificación', [s('license_plate'), s('vin_sn'), s('x_motor_sn'), s('model_year'), s('color'),
                                s('state_id')]),
            ('Entrega', [s('driver_id', label='Cliente / conductor'), s('fecha_entrega')]),
        ]
        return v, secciones, {}, {}, _('Editar vehículo'), ''

    def _form_cliente(self, v, res_id, params):
        P = self.env['res.partner']
        rec = P.browse(res_id).exists()
        if not rec:
            raise UserError(_('El cliente ya no existe.'))
        s = lambda n, **k: self._campo_spec(P, n, **k)
        secciones = [
            ('Datos personales', [s('name', required=True), s('vat', label='DNI / RUC'), s('nationality'),
                                  s('occupation')]),
            ('Contacto', [s('mobile'), s('phone'), s('email'), s('street', label='Dirección', col=2)]),
        ]
        return rec, secciones, {}, {}, _('Editar cliente'), ''

    def _form_expediente(self, v, res_id, params):
        E = self._modelo('adt.expediente', 'cliente_id')
        if E is None:
            raise UserError(_('El módulo de expedientes no está disponible.'))
        cliente = params.get('cliente_id')
        if not cliente:
            raise UserError(_('Asigna un cliente al vehículo antes de crear su expediente.'))
        s = lambda n, **k: self._campo_spec(E, n, **k)
        secciones = [
            ('Expediente', [s('asesora_id'), s('fecha'), s('vehiculo', col=2)]),
        ]
        defaults = {'asesora_id': [self.env.user.id, self.env.user.name], 'fecha': fields.Date.context_today(self)}
        return E, secciones, defaults, {'cliente_id': cliente}, _('Nuevo expediente'), _(
            'Después de crearlo podrás cargar los documentos del cliente desde esta misma pantalla.')

    def _form_expediente_datos(self, v, res_id, params):
        E = self._modelo('adt.expediente', 'cliente_id')
        rec = E.browse(res_id).exists() if E is not None and res_id else None
        if not rec:
            raise UserError(_('El expediente ya no existe.'))
        s = lambda n, **k: self._campo_spec(E, n, **k)
        ref = lambda i: [s('ref_%s_name' % i, label='Referencia %s' % i), s('ref_%s_phone' % i),
                         s('ref_%s_vinculo' % i)]
        mototaxista = rec.cliente_occupation_code == 'mototaxista' if 'cliente_occupation_code' in rec._fields else False
        trabajo = [s('ganancia_diaria_mensual'), s('tiempo_trabajando'), s('moto_empresa'), s('moto_propiedad')] \
            if mototaxista else [s('ganancia_diaria_mensual_no', label='Ganancia diaria / mensual'),
                                 s('tiempo_trabajando_no', label='¿Cuánto tiempo tiene trabajando?')]
        secciones = [
            ('Solicitud', [s('asesora_id'), s('fecha'), s('vehiculo', col=2)]),
            ('Domicilio', [s('direccion_cliente', label='Dirección', col=2), s('estado_direccion'),
                           s('obs_direccion', visible=['estado_direccion', 'rechazado']), s('tipo_vivienda'),
                           s('tiempo_viviendo'), s('propietario_contacto', visible=['tipo_vivienda', 'alquilada'])]),
            ('Trabajo', trabajo),
            ('Referencias', ref(1) + ref(2) + ref(3) + ref(4) +
             [s('estado_referencias'), s('obs_referencias', visible=['estado_referencias', 'rechazado'])]),
            ('Beneficiario (opcional)', [s('beneficiario_celular'), s('beneficiario_parentesco')]),
            ('Fase final', [s('placa'), s('chasis')]),
        ]
        return rec, secciones, {}, {}, _('Datos del expediente'), ''

    def _form_rechazo_documento(self, v, res_id, params):
        E = self._modelo('adt.expediente', 'cliente_id')
        rec = E.browse(res_id).exists() if E is not None and res_id else None
        clave = params.get('clave') or ''
        if not rec or 'obs_' + clave not in rec._fields:
            raise UserError(_('Documento no válido.'))
        spec = self._campo_spec(E, 'obs_' + clave, label='Motivo del rechazo', required=True, col=2)
        etiqueta = next((d[1] for _g, _t, docs in EXPEDIENTE_GRUPOS for d in docs if d[0] == clave), clave)
        return rec, [('', [spec])], {}, {'estado_' + clave: 'rechazado'}, _('Rechazar %s') % etiqueta, _(
            'El asesor verá este motivo para corregir el documento.')

    def _formulario(self, clave, vehicle_id, res_id, params):
        metodo = getattr(self, '_form_%s' % clave, None)
        if not metodo or not clave.replace('_', '').isalpha():
            raise UserError(_('Formulario no disponible.'))
        v = self._vehiculo(vehicle_id)
        rec, secciones, defaults, fijos, titulo, ayuda = metodo(v, res_id, params or {})
        secciones = [(t, [c for c in campos if c]) for t, campos in secciones]
        return v, rec, [(t, c) for t, c in secciones if c], defaults, fijos, titulo, ayuda

    @api.model
    def formulario(self, clave, vehicle_id, res_id=False, params=None):
        _v, rec, secciones, defaults, _fijos, titulo, ayuda = self._formulario(clave, vehicle_id, res_id, params)
        valores = dict(defaults)
        if rec and rec.id:
            for _t, campos in secciones:
                for c in campos:
                    if c['type'] in ('file', 'adjuntos'):
                        valores[c['name']] = bool(rec[c['name']])
                    else:
                        valor = self._a_texto(rec._fields[c['name']], rec[c['name']])
                        if c['type'] == 'selection' and c['name'] == 'cuenta_id' and valor:
                            valor = valor[0]
                        valores[c['name']] = valor
        return {
            'clave': clave,
            'res_id': rec.id if rec else False,
            'titulo': titulo,
            'ayuda': ayuda,
            'secciones': [{'titulo': t, 'campos': c} for t, c in secciones],
            'valores': valores,
        }

    @api.model
    def guardar(self, clave, vehicle_id, valores, res_id=False, params=None):
        _v, rec, secciones, _defaults, fijos, _titulo, _ayuda = self._formulario(clave, vehicle_id, res_id, params)
        Model = rec if rec is not None else None
        permitidos = {c['name']: c for _t, campos in secciones for c in campos}
        vals, adjuntos = {}, {}
        for nombre, valor in (valores or {}).items():
            spec = permitidos.get(nombre)
            if not spec:
                continue
            campo = Model._fields[nombre]
            if spec['type'] == 'adjuntos':
                adjuntos[nombre] = valor or []
                continue
            if spec['type'] == 'file':
                if isinstance(valor, dict) and valor.get('datos'):
                    vals[nombre] = self._decodificar(valor['datos'])
                elif valor is False:
                    vals[nombre] = False
                continue
            if valor in ('', None):
                valor = False
            if campo.type == 'many2one':
                valor = int(valor[0] if isinstance(valor, (list, tuple)) else valor) if valor else False
            elif campo.type == 'integer':
                valor = int(valor or 0)
            elif campo.type in ('float', 'monetary'):
                valor = float(valor or 0)
            elif campo.type == 'boolean':
                valor = bool(valor)
            # Las listas cerradas (incluidas las de registros, como la cuenta de una
            # captura) solo aceptan las opciones que se ofrecieron.
            if valor and spec.get('options') and str(valor) not in {str(o[0]) for o in spec['options']}:
                raise ValidationError(_('Valor no válido para %s.') % spec['label'])
            vals[nombre] = valor
        faltan = [c['label'] for c in permitidos.values()
                  if c['required'] and c['type'] not in ('adjuntos', 'file')
                  and not vals.get(c['name']) and not (rec and rec.id and c['name'] not in vals and rec[c['name']])]
        if faltan:
            raise ValidationError(_('Completa los campos obligatorios: %s.') % ', '.join(faltan))
        vals.update(fijos)
        if clave == 'captura':
            cuenta = self.env['adt.comercial.cuentas'].browse(vals.get('cuenta_id'))
            vals['partner_id'] = cuenta.partner_id.id
        if rec is not None and rec.id:
            rec.write(vals)
        else:
            rec = Model.create(vals)
        for nombre, archivos in adjuntos.items():
            nuevos = self._crear_adjuntos(rec, archivos)
            if nuevos:
                rec.write({nombre: [(4, a) for a in nuevos]})
        return {'id': rec.id, 'nombre': rec.display_name}

    def _crear_adjuntos(self, rec, archivos):
        ids = []
        for a in archivos:
            if not isinstance(a, dict) or not a.get('datos'):
                continue
            ids.append(self.env['ir.attachment'].create({
                'name': (a.get('nombre') or 'archivo')[:200],
                'datas': self._decodificar(a['datos']),
                'res_model': rec._name,
                'res_id': rec.id,
            }).id)
        return ids

    # ------------------------------------------------------------------
    # Documentos (expediente y vehículo)
    # ------------------------------------------------------------------

    def _campos_documento(self, modelo):
        if modelo == 'adt.expediente':
            return {f for _g, _t, docs in EXPEDIENTE_GRUPOS for d in docs for f, _l in d[2]}
        if modelo == 'fleet.vehicle':
            return {d[0] for d in VEHICULO_DOCUMENTOS}
        return set()

    def _registro_documento(self, modelo, res_id, campo):
        if campo not in self._campos_documento(modelo) or modelo not in self.env or campo not in self.env[modelo]._fields:
            raise AccessError(_('Documento no permitido.'))
        rec = self.env[modelo].browse(int(res_id)).exists()
        if not rec:
            raise UserError(_('El registro ya no existe.'))
        return rec

    @api.model
    def subir_documento(self, modelo, res_id, campo, nombre, datos):
        rec = self._registro_documento(modelo, res_id, campo)
        vals = {campo: self._decodificar(datos)}
        nombre_campo = next((d[2] for d in VEHICULO_DOCUMENTOS if d[0] == campo), None)
        if modelo == 'fleet.vehicle' and nombre_campo in rec._fields:
            vals[nombre_campo] = (nombre or '')[:200]
        rec.write(vals)
        return True

    @api.model
    def quitar_documento(self, modelo, res_id, campo):
        rec = self._registro_documento(modelo, res_id, campo)
        rec.write({campo: False})
        return True

    @api.model
    def revisar_documento(self, expediente_id, clave, estado):
        """Acepta un documento del expediente (el rechazo pasa por el formulario con motivo)."""
        rec = self.env['adt.expediente'].browse(int(expediente_id)).exists()
        if not rec or 'estado_' + (clave or '') not in rec._fields or estado != 'aceptado':
            raise UserError(_('Documento no válido.'))
        vals = {'estado_' + clave: 'aceptado'}
        if 'obs_' + clave in rec._fields:
            vals['obs_' + clave] = False
        rec.write(vals)
        return True

    def _adjuntos_por_campo(self, rec, campos):
        """{campo: attachment} de los binarios guardados como adjunto."""
        adjuntos = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', rec._name), ('res_id', '=', rec.id), ('res_field', 'in', list(campos))])
        return {a.res_field: a for a in adjuntos}

    def _archivo(self, rec, campo, adjunto, lado=''):
        """Datos de un archivo para la vista (vista previa y descarga)."""
        if not adjunto:
            return {'campo': campo, 'lado': lado, 'cargado': False}
        unico = (adjunto.checksum or '')[:8]
        base = '/web/content/%s/%s/%s' % (rec._name, rec.id, campo)
        es_imagen = (adjunto.mimetype or '').startswith('image/')
        return {
            'campo': campo, 'lado': lado, 'cargado': True,
            'imagen': es_imagen,
            'mimetype': adjunto.mimetype or '',
            'tamano': adjunto.file_size or 0,
            'fecha': fields.Datetime.to_string(adjunto.write_date or adjunto.create_date),
            'miniatura': '/web/image/%s/%s/%s/320x240?unique=%s' % (rec._name, rec.id, campo, unico) if es_imagen else '',
            'url': '%s?unique=%s' % (base, unico),
            'descarga': '%s?download=true&unique=%s' % (base, unico),
        }

    def _aplica_documento(self, e, condicion, cargado):
        nacionalidad = e.cliente_nationality_code if 'cliente_nationality_code' in e._fields else ''
        ocupacion = e.cliente_occupation_code if 'cliente_occupation_code' in e._fields else ''
        return {
            None: True,
            'opcional': True,
            'cargado': cargado,
            'peruano': not nacionalidad or nacionalidad == 'peruana' or cargado,
            'extranjero': (nacionalidad and nacionalidad != 'peruana') or cargado,
            'mototaxista': ocupacion == 'mototaxista' or cargado,
            'no_mototaxista': ocupacion != 'mototaxista' or cargado,
            'alquilada': ('tipo_vivienda' in e._fields and e.tipo_vivienda == 'alquilada') or cargado,
        }.get(condicion, True)

    def _documentos_expediente_grupos(self, e):
        """Documentos del expediente agrupados como en su formulario, con el estado de revisión."""
        campos = {f for _g, _t, docs in EXPEDIENTE_GRUPOS for d in docs for f, _l in d[2] if f in e._fields}
        adjuntos = self._adjuntos_por_campo(e, campos)
        grupos, requeridos, completos, rechazados = [], 0, 0, 0
        for gkey, gtitulo, docs in EXPEDIENTE_GRUPOS:
            items = []
            for clave, etiqueta, fotos, condicion in docs:
                fotos = [(f, l) for f, l in fotos if f in e._fields]
                if not fotos:
                    continue
                archivos = [self._archivo(e, f, adjuntos.get(f), l) for f, l in fotos]
                cargados = sum(1 for a in archivos if a['cargado'])
                if not self._aplica_documento(e, condicion, bool(cargados)):
                    continue
                revisable = bool(clave and 'estado_' + clave in e._fields)
                estado_rev = e['estado_' + clave] if revisable else False
                if not cargados:
                    estado = 'falta'
                elif cargados < len(archivos):
                    estado = 'incompleto'
                elif estado_rev == 'rechazado':
                    estado = 'rechazado'
                else:
                    estado = 'aceptado'
                obligatorio = condicion not in ('opcional', 'cargado')
                if obligatorio:
                    requeridos += 1
                    completos += estado == 'aceptado'
                rechazados += estado == 'rechazado'
                items.append({
                    'clave': clave or '', 'label': etiqueta, 'estado': estado, 'revisable': revisable and cargados > 0,
                    'obligatorio': obligatorio,
                    'obs': (e['obs_' + clave] or '') if clave and 'obs_' + clave in e._fields else '',
                    'archivos': archivos,
                    'historico': condicion == 'cargado',
                })
            if items:
                grupos.append({'key': gkey, 'titulo': gtitulo, 'documentos': items})
        return grupos, {'requeridos': requeridos, 'completos': completos, 'rechazados': rechazados}

    def _documentos_vehiculo(self, v):
        campos = [d for d in VEHICULO_DOCUMENTOS if d[0] in v._fields]
        if not campos:
            return []
        adjuntos = self._adjuntos_por_campo(v, [d[0] for d in campos])
        docs = []
        for campo, etiqueta, nombre_campo, requerido in campos:
            archivo = self._archivo(v, campo, adjuntos.get(campo))
            archivo['nombre'] = v[nombre_campo] if nombre_campo in v._fields and v[nombre_campo] else ''
            docs.append({
                'clave': campo, 'label': etiqueta, 'obligatorio': requerido,
                'estado': 'aceptado' if archivo['cargado'] else 'falta',
                'revisable': False, 'obs': '', 'archivos': [archivo],
            })
        return docs

    # ------------------------------------------------------------------
    # Crédito: cuenta y cronograma
    # ------------------------------------------------------------------

    def _simular(self, p):
        """Cuotas que generará adt.comercial.cuentas.generar_cuotas con estos datos.

        Replica esa regla tal cual (incluido el ajuste de la última cuota) para que
        la vista previa coincida con el cronograma real al aprobar la cuenta.
        """
        errores = []
        fraccionado = float(p.get('monto_fraccionado') or 0)
        gracia = float(p.get('cuota_gracia') or 0)
        qty = int(p.get('qty_cuotas') or 0)
        monto_cuota = float(p.get('monto_cuota') or 0) if p.get('modo') == 'monto' else 0.0
        dias = DIAS_PERIODO.get(p.get('periodicidad'))
        fecha_base = fields.Date.to_date(p.get('fecha_gracia')) if p.get('fecha_gracia') else None
        if fraccionado <= 0:
            errores.append(_('Indica el monto a financiar.'))
        if qty <= 0:
            errores.append(_('Indica el número de cuotas.'))
        if not dias:
            errores.append(_('Elige la periodicidad.'))
        if not fecha_base:
            errores.append(_('Indica la fecha de inicio del cronograma.'))
        if gracia >= fraccionado > 0:
            errores.append(_('La cuota 0 no puede ser mayor o igual al monto a financiar.'))
        if p.get('modo') == 'monto' and monto_cuota <= 0:
            errores.append(_('Indica el monto de la cuota.'))
        if errores:
            return {'cuotas': [], 'errores': errores}

        cuotas = []
        if gracia > 0:
            cuotas.append({'nombre': 'Cuota 0', 'fecha': fields.Date.to_string(fecha_base), 'monto': gracia})
        base = fraccionado - gracia
        if monto_cuota == 0:
            resto = base % qty
            monto = (base - resto) / qty if resto > 0 else base / qty
            montos = [monto] * qty
            montos[-1] += resto
        else:
            montos = [monto_cuota] * qty
            montos[-1] += base - qty * monto_cuota
        fecha = fecha_base
        for i, monto in enumerate(montos):
            fecha = fecha + timedelta(days=dias)
            cuotas.append({'nombre': 'Cuota %s' % (i + 1), 'fecha': fields.Date.to_string(fecha), 'monto': monto})

        avisos = []
        ultima = montos[-1]
        if ultima <= 0:
            errores.append(_('Con ese monto de cuota la última cuota queda en %.2f: reduce el número de cuotas.') % ultima)
        elif monto_cuota and abs(ultima - monto_cuota) > 0.01:
            avisos.append(_('La última cuota se ajusta a %.2f para cuadrar el monto financiado.') % ultima)
        return {
            'cuotas': cuotas,
            'errores': errores,
            'avisos': avisos,
            'total': sum(c['monto'] for c in cuotas),
            'cuota': montos[0],
            'ultima': fields.Date.to_string(fecha),
        }

    def _cuenta_borrador(self, v, cuenta_id):
        cuenta = self.env['adt.comercial.cuentas'].browse(int(cuenta_id)).exists()
        if not cuenta or cuenta.vehiculo_id != v:
            raise UserError(_('La cuenta no pertenece a este vehículo.'))
        if cuenta.state != 'borrador':
            raise UserError(_('Solo se puede editar el cronograma de una cuenta en borrador.'))
        return cuenta

    @api.model
    def cuenta_inicial(self, vehicle_id, cuenta_id=False):
        """Datos para el asistente de crédito (nueva cuenta o borrador existente)."""
        v = self._vehiculo(vehicle_id)
        Cuenta = self._modelo('adt.comercial.cuentas', 'vehiculo_id')
        if Cuenta is None:
            raise UserError(_('El módulo comercial no está disponible.'))
        hoy = fields.Date.context_today(self)
        financieras = self.env['adt.comercial.financiera'].search_read([], ['name'], order='name')
        valores = {
            'partner_id': v.driver_id and [v.driver_id.id, v.driver_id.display_name],
            'user_id': [self.env.user.id, self.env.user.name],
            'tipo_financiera_id': financieras[0]['id'] if len(financieras) == 1 else False,
            'periodicidad': 'quincena',
            'fecha_desembolso': fields.Date.to_string(hoy),
            'fecha_entrega': fields.Date.to_string(hoy),
            'fecha_gracia': fields.Date.to_string(hoy),
            'monto_total': 0.0, 'monto_inicial': 0.0, 'monto_fraccionado': 0.0, 'cuota_gracia': 0.0,
            'qty_cuotas': 24, 'monto_cuota': 0.0, 'modo': 'cuotas',
            'is_available_pay_mora': False,
        }
        if cuenta_id:
            c = self._cuenta_borrador(v, cuenta_id)
            for k in valores:
                if k in c._fields:
                    valores[k] = self._a_texto(c._fields[k], c[k])
            valores['tipo_financiera_id'] = c.tipo_financiera_id.id
            valores['modo'] = 'monto' if c.monto_cuota else 'cuotas'
        else:
            vigente = Cuenta.search([('vehiculo_id', '=', v.id), ('state', 'in', ('borrador', 'aprobado', 'en_curso'))], limit=1)
            if vigente:
                raise UserError(_('El vehículo ya tiene la cuenta %s (%s). Edítala en lugar de crear otra.')
                                % (vigente.display_name, self._etiqueta(vigente, 'state', vigente.state)))
        periodos = Cuenta._fields['periodicidad']._description_selection(self.env)
        return {
            'cuenta_id': cuenta_id or False,
            'valores': valores,
            'financieras': [[f['id'], f['name']] for f in financieras],
            'periodicidades': [list(p) for p in periodos],
            'vehiculo': ' '.join(filter(None, [v.license_plate, v.model_id.display_name])),
            'disponible': v.disponible if 'disponible' in v._fields else True,
            'simulacion': self._simular(valores),
        }

    @api.model
    def simular_cronograma(self, params):
        return self._simular(params or {})

    @api.model
    def guardar_cuenta(self, vehicle_id, params, aprobar=False, cuenta_id=False):
        v = self._vehiculo(vehicle_id)
        params = params or {}
        sim = self._simular(params)
        if sim['errores']:
            raise ValidationError('\n'.join(sim['errores']))
        partner = params.get('partner_id')
        partner = int(partner[0] if isinstance(partner, (list, tuple)) else partner) if partner else False
        if not partner:
            raise ValidationError(_('Elige el cliente de la cuenta.'))
        usuario = params.get('user_id')
        usuario = int(usuario[0] if isinstance(usuario, (list, tuple)) else usuario) if usuario else self.env.user.id
        modo_monto = params.get('modo') == 'monto'
        vals = {
            'partner_id': partner,
            'vehiculo_id': v.id,
            'user_id': usuario,
            'tipo_financiera_id': int(params['tipo_financiera_id']) if params.get('tipo_financiera_id') else False,
            'periodicidad': params.get('periodicidad'),
            'fecha_desembolso': params.get('fecha_desembolso') or False,
            'fecha_entrega': params.get('fecha_entrega') or False,
            'fecha_gracia': params.get('fecha_gracia'),
            'monto_total': float(params.get('monto_total') or 0),
            'monto_inicial': float(params.get('monto_inicial') or 0),
            'monto_fraccionado': float(params.get('monto_fraccionado') or 0),
            'cuota_gracia': float(params.get('cuota_gracia') or 0),
            'qty_cuotas': int(params.get('qty_cuotas') or 0),
            'monto_cuota': float(params.get('monto_cuota') or 0) if modo_monto else 0.0,
            'cuota_inicio_2': 0,
            'is_available_pay_mora': bool(params.get('is_available_pay_mora')),
        }
        Cuenta = self.env['adt.comercial.cuentas']
        vals = {k: val for k, val in vals.items() if k in Cuenta._fields}
        if cuenta_id:
            cuenta = self._cuenta_borrador(v, cuenta_id)
            # El cronograma se vuelve a generar con los nuevos datos al aprobar.
            if cuenta.cuota_ids:
                cuenta.cuota_ids.unlink()
            cuenta.write(vals)
        else:
            if Cuenta.search_count([('vehiculo_id', '=', v.id), ('state', 'in', ('borrador', 'aprobado', 'en_curso'))]):
                raise UserError(_('El vehículo ya tiene una cuenta vigente.'))
            if not v.driver_id and 'driver_id' in v._fields:
                v.write({'driver_id': partner})
            cuenta = Cuenta.create(vals)
        if aprobar:
            cuenta.aprobar_cuenta()
        return {'id': cuenta.id, 'referencia': cuenta.reference_no, 'estado': cuenta.state}
