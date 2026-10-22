from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)


class AdtExpediente(models.Model):
    _name = 'adt.expediente'
    _description = 'Expediente'
    _rec_name = 'cliente_id'

    # ======================
    # DATOS GENERALES
    # ======================

    state = fields.Selection([
        ('por_revisar', 'Por revisar'),
        ('incompleto_expediente', 'Incompleto - Expediente'),
        ('incompleto_fase_final', 'Incompleto - Fase Final'),
        ('completo', 'Completo'),
        ('aprobado_sin_desembolso', 'Aprobado sin desembolso'),
        ('rechazado', 'Rechazado'),
    ], compute='_compute_state', store=True, tracking=True)

    # Manual override field so UI buttons can set a persistent state that the compute respects.
    manual_state = fields.Selection([
        ('por_revisar', 'Por revisar'),
        ('incompleto_expediente', 'Incompleto - Expediente'),
        ('incompleto_fase_final', 'Incompleto - Fase Final'),
        ('completo', 'Completo'),
        ('aprobado_sin_desembolso', 'Aprobado sin desembolso'),
        ('rechazado', 'Rechazado'),
    ], string='Estado manual', help='Si se establece, este valor tendrá prioridad sobre el cálculo automático del estado.', copy=False)

    cliente_id = fields.Many2one('res.partner', string="Cliente", required=True)
    asesora_id = fields.Many2one('res.users', string="Asesora", required=True)
    fecha = fields.Date(default=fields.Date.today)

    # ======================
    # RECHAZO
    # ======================

    fecha_rechazo = fields.Date(readonly=True)
    motivo_rechazo = fields.Text(readonly=True)

    # ======================
    # REQUISITOS
    # ======================

    vehiculo = fields.Selection([
        ('moto_deluxe_200', 'Moto deluxe motor 200'),
        ('moto_duramax_225', 'Moto duramax motor 225'),
    ], string='Vehículo', help='Seleccionar la moto que va a financiar')

    cliente_nationality = fields.Char(string='Nacionalidad', compute='_compute_cliente_nationality', store=False, readonly=True)

    # Raw nationality code from partner (use this in attrs checks)
    cliente_nationality_code = fields.Char(string='Nacionalidad (code)', compute='_compute_cliente_nationality_code', store=False, readonly=True)

    @api.depends('cliente_id')
    def _compute_cliente_nationality_code(self):
        for rec in self:
            rec.cliente_nationality_code = getattr(rec.cliente_id, 'nationality', False) or ''

    @api.depends('cliente_id')
    def _compute_cliente_nationality(self):
        for rec in self:
            # Get the raw selection key from partner
            nat_key = getattr(rec.cliente_id, 'nationality', False) or False
            if not nat_key:
                rec.cliente_nationality = False
                continue
            # Try to resolve the selection label (display value)
            try:
                field = rec.cliente_id._fields.get('nationality')
                selection = field.selection if field else False
                if callable(selection):
                    selection = selection(rec.env)
                # selection is a list of tuples [(key,label), ...]
                rec.cliente_nationality = dict(selection).get(nat_key, nat_key)
            except Exception:
                # Fallback to the raw key if anything goes wrong
                rec.cliente_nationality = nat_key

    # Copy occupation from res.partner (display-only) like cliente_nationality
    cliente_occupation = fields.Char(string='Ocupación', compute='_compute_cliente_occupation', store=False, readonly=True)

    # Raw occupation code from partner (use this in attrs checks)
    cliente_occupation_code = fields.Char(string='Ocupación (code)', compute='_compute_cliente_occupation_code', store=False, readonly=True)

    @api.depends('cliente_id')
    def _compute_cliente_occupation(self):
        for rec in self:
            # use getattr to avoid errors if cliente_id is False or doesn't have occupation
            occ = getattr(rec.cliente_id, 'occupation', False)
            # occupation on partner is a selection; show the stored label if available
            if occ and rec.cliente_id._fields.get('occupation') and isinstance(rec.cliente_id._fields['occupation'], fields.Selection):
                # resolve selection to its label
                try:
                    # partner's display_name for selection can be fetched via _fields mapping
                    selection = rec.cliente_id._fields['occupation'].selection
                    # selection may be a callable too; handle both
                    if callable(selection):
                        selection = selection(rec.env)
                    # find label
                    label = dict(selection).get(occ, occ)
                except Exception:
                    label = occ
                rec.cliente_occupation = label or occ
            else:
                # fallback: try to read partner.occupation_display (if using compute) or raw value
                rec.cliente_occupation = occ or ''

    @api.depends('cliente_id')
    def _compute_cliente_occupation_code(self):
        for rec in self:
            rec.cliente_occupation_code = getattr(rec.cliente_id, 'occupation', False) or ''

    foto_vivienda = fields.Binary(attachment=True)
    estado_foto_vivienda = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_vivienda = fields.Text()

    foto_ingresos = fields.Binary(attachment=True)
    estado_foto_ingresos = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_ingresos = fields.Text()

    # Recibo de servicios (luz/agua) - two photos
    obs_foto_recibo = fields.Text(string='Observaciones Recibo')
    foto_recibo = fields.Binary(attachment=True, string='Recibo')
    estado_foto_recibo = fields.Selection([
             ('aceptado', 'Aceptado'),
             ('rechazado', 'Rechazado')
         ], default='aceptado')

    # ----------------------
    # Mototaxista specific fields (images, states, observations)
    # ----------------------
    foto_moto = fields.Binary(attachment=True, string='Foto en la moto')
    estado_foto_moto = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_moto = fields.Text()

    foto_soat = fields.Binary(attachment=True, string='SOAT')
    estado_foto_soat = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_soat = fields.Text()

    foto_tarjeta_propiedad_frente = fields.Binary(attachment=True, string='Tarjeta Propiedad - Frente')
    foto_tarjeta_propiedad_reverso = fields.Binary(attachment=True, string='Tarjeta Propiedad - Reverso')
    estado_foto_tarjeta = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_tarjeta = fields.Text()

    ganancia_diaria_mensual = fields.Char(string='Ganancia diaria / mensual')
    tiempo_trabajando = fields.Char(string='¿Cuánto tiempo tiene trabajando?')
    moto_empresa = fields.Char(string='Empresa asociada (si aplica)')
    moto_propiedad = fields.Selection([
        ('propia', 'Propia'),
        ('alquilada', 'Alquilada')
    ], string='Moto propia o alquilada')

    # ----------------------
    # Non-mototaxista fields
    # ----------------------
    foto_lugar_trabajo = fields.Binary(attachment=True, string='Lugar de trabajo')
    estado_foto_lugar_trabajo = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_lugar_trabajo = fields.Text()

    foto_lugar_negocio = fields.Binary(attachment=True, string='Lugar del negocio')
    estado_foto_lugar_negocio = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_lugar_negocio = fields.Text()

    foto_boletas = fields.Binary(attachment=True, string='Boletas / Contrato / Recibos')
    estado_foto_boletas = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_boletas = fields.Text()

    foto_estado_cuenta = fields.Binary(attachment=True, string='Estado de cuenta')
    estado_foto_estado_cuenta = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_estado_cuenta = fields.Text()

    ganancia_diaria_mensual_no = fields.Char(string='Ganancia diaria / mensual (no mototaxista)')
    tiempo_trabajando_no = fields.Char(string='¿Cuánto tiempo tiene trabajando? (no mototaxista)')

    # ----------------------
    # SENTINEL / SCORE
    # ----------------------
    # Two images: score image and deudas/services image (allow multiple by keeping two fields)
    foto_sentinel_1 = fields.Binary(attachment=True, string='Sentinel - Score')
    foto_sentinel_2 = fields.Binary(attachment=True, string='Sentinel - Deudas')
    estado_foto_sentinel = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_sentinel = fields.Text(string='Observaciones Sentinel')

    # ----------------------
    # Documento de identidad (nuevos campos)
    # ----------------------
    foto_dni_frente = fields.Binary(attachment=True)
    foto_dni_reverso = fields.Binary(attachment=True)
    estado_foto_dni = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
    ], default='aceptado')
    obs_foto_dni = fields.Text()

    # For foreign clients we need front/reverse for CE.
    # Pasaporte DESHABILITADO: los campos se conservan solo para el historial
    # (lectura); no se solicitan ni forman parte de ninguna validación.
    foto_ce_frente = fields.Binary(attachment=True)
    foto_ce_reverso = fields.Binary(attachment=True)
    estado_foto_ce = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
    ], default='aceptado')
    obs_foto_ce = fields.Text()
    foto_pasaporte_frente = fields.Binary(attachment=True)
    foto_pasaporte_reverso = fields.Binary(attachment=True)
    estado_foto_pasaporte = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
    ], default='aceptado')
    obs_foto_pasaporte = fields.Text()

    direccion_cliente = fields.Char()
    estado_direccion = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_direccion = fields.Text()


    foto_licencia = fields.Binary(attachment=True)
    estado_foto_licencia = fields.Selection([
                ('aceptado', 'Aceptado'),
                ('rechazado', 'Rechazado')
            ], default='aceptado')
    obs_foto_licencia = fields.Text()

    # ======================
    # UBICACIÓN Y FACHADA DEL DOMICILIO
    # ======================
    # Foto de ubicación en tiempo actual
    foto_ubicacion_actual = fields.Binary(attachment=True, string='Ubicación - Foto')
    estado_foto_ubicacion = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_ubicacion = fields.Text(string='Observaciones Ubicación')

    # Foto de fachada con el cliente en la puerta
    foto_fachada_domicilio = fields.Binary(attachment=True, string='Fachada domicilio - Foto')
    estado_foto_fachada = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_fachada = fields.Text(string='Observaciones Fachada')

    # Si vive alquilado: contrato (foto) o numero del dueño
    foto_contrato_alquiler = fields.Binary(attachment=True, string='Contrato alquiler - Foto')
    estado_foto_contrato = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_contrato = fields.Text(string='Observaciones Contrato')
    propietario_contacto = fields.Char(string='Número del dueño / contacto')

    # ¿Cuánto tiempo viven en ese lugar?
    tiempo_viviendo = fields.Char(string='¿Cuánto tiempo viven en ese lugar?')

    # La casa es alquilada / propia / familiar ?
    tipo_vivienda = fields.Selection([
        ('alquilada', 'Alquilada'),
        ('propia', 'Propia'),
        ('familiar', 'Familiar')
    ], string='Tipo de vivienda')

    # ======================
    # FASE FINAL
    # ======================

    foto_entrega = fields.Binary(attachment=True)
    placa = fields.Char()
    chasis = fields.Char()

    # ----------------------
    # REFERENCES (4) - ADDED FIELDS (non-destructive)
    # ----------------------
    # For each reference: name, phone, vínculo, two photos
    ref_1_name = fields.Char(string='Nombre')
    ref_1_phone = fields.Char(string='Teléfono')
    ref_1_vinculo = fields.Selection([
        ('familiar', 'Familiar'),
        ('amigo', 'Amigo'),
        ('colega', 'Colega'),
        ('otro', 'Otro'),
    ], string='Vínculo')


    ref_2_name = fields.Char(string='Nombre')
    ref_2_phone = fields.Char(string='Teléfono')
    ref_2_vinculo = fields.Selection([
        ('familiar', 'Familiar'),
        ('amigo', 'Amigo'),
        ('colega', 'Colega'),
        ('otro', 'Otro'),
    ], string='Vínculo')

    ref_3_name = fields.Char(string='Nombre')
    ref_3_phone = fields.Char(string='Teléfono')
    ref_3_vinculo = fields.Selection([
        ('familiar', 'Familiar'),
        ('amigo', 'Amigo'),
        ('colega', 'Colega'),
        ('otro', 'Otro'),
    ], string='Vínculo ')

    ref_4_name = fields.Char(string='Nombre')
    ref_4_phone = fields.Char(string=' Teléfono')
    ref_4_vinculo = fields.Selection([
        ('familiar', 'Familiar'),
        ('amigo', 'Amigo'),
        ('colega', 'Colega'),
        ('otro', 'Otro'),
    ], string='Vínculo')

    # Single state for the whole references section
    estado_referencias = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
    ], default='aceptado', string='Estado referencias')
    obs_referencias = fields.Text(string='Observaciones referencias')

    # ----------------------
    # BENEFICIARIO (opcional: no cuenta para el progreso ni el estado)
    # ----------------------
    foto_beneficiario_documento = fields.Binary(attachment=True, string='Documento del beneficiario - Foto')
    estado_foto_beneficiario = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_beneficiario = fields.Text(string='Observaciones beneficiario')
    beneficiario_celular = fields.Char(string='Celular del beneficiario')
    beneficiario_parentesco = fields.Selection([
        ('conyuge', 'Cónyuge'),
        ('conviviente', 'Conviviente'),
        ('hijo', 'Hijo(a)'),
        ('padre', 'Padre'),
        ('madre', 'Madre'),
        ('hermano', 'Hermano(a)'),
        ('abuelo', 'Abuelo(a)'),
        ('nieto', 'Nieto(a)'),
        ('tio', 'Tío(a)'),
        ('sobrino', 'Sobrino(a)'),
        ('primo', 'Primo(a)'),
        ('suegro', 'Suegro(a)'),
        ('cunado', 'Cuñado(a)'),
        ('yerno_nuera', 'Yerno / Nuera'),
        ('otro', 'Otro'),
    ], string='Parentesco del beneficiario')

    # ======================
    # EXPEDIENTE EN UN SOLO ARCHIVO
    # ======================
    # Alternativa a cargar cada foto: un PDF o Word con todo el expediente.
    # Mientras esté cargado y no rechazado, los requisitos del formulario se
    # consideran completos (ver `requisitos_cubiertos`). No cambia el estado:
    # el expediente sigue pasando por la revisión habitual.

    archivo_consolidado = fields.Binary(attachment=True, string='Expediente en un solo archivo',
                                        help='PDF o Word con todos los documentos del expediente.')
    archivo_consolidado_nombre = fields.Char(string='Nombre del archivo')
    estado_archivo_consolidado = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_archivo_consolidado = fields.Text(string='Observaciones del archivo')
    archivo_consolidado_fecha = fields.Datetime(string='Archivo cargado el', readonly=True, copy=False)
    archivo_consolidado_usuario_id = fields.Many2one('res.users', string='Archivo cargado por', readonly=True, copy=False)
    requisitos_cubiertos = fields.Boolean(
        string='Requisitos cubiertos por archivo', compute='_compute_requisitos_cubiertos', store=True,
        help='El expediente se cargó en un solo archivo aceptado: no se exige cada documento por separado.')

    # Firmas de los formatos admitidos (el contenido manda, no la extensión).
    FIRMAS_ARCHIVO_CONSOLIDADO = (
        (b'%PDF', 'PDF'),
        (b'PK\x03\x04', 'Word (.docx)'),
        (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'Word (.doc)'),
    )

    @api.depends('archivo_consolidado', 'estado_archivo_consolidado')
    def _compute_requisitos_cubiertos(self):
        for rec in self:
            rec.requisitos_cubiertos = bool(rec.archivo_consolidado) and rec.estado_archivo_consolidado != 'rechazado'

    @api.constrains('archivo_consolidado', 'archivo_consolidado_nombre')
    def _check_archivo_consolidado(self):
        for rec in self:
            datos = rec.with_context(bin_size=False).archivo_consolidado
            if not datos:
                continue
            cabecera = base64.b64decode(datos[:24])
            if not any(cabecera.startswith(firma) for firma, _n in self.FIRMAS_ARCHIVO_CONSOLIDADO):
                raise ValidationError('El expediente en un solo archivo debe ser PDF o Word (.doc / .docx).')
            nombre = (rec.archivo_consolidado_nombre or '').lower()
            # Un .docx es un ZIP: la extensión evita aceptar otros comprimidos.
            if cabecera.startswith(b'PK') and nombre and not nombre.endswith('.docx'):
                raise ValidationError('El archivo comprimido no es un documento Word (.docx).')

    def _marcar_archivo_consolidado(self, vals):
        if 'archivo_consolidado' not in vals:
            return vals
        vals = dict(vals)
        if vals['archivo_consolidado']:
            vals.update(archivo_consolidado_fecha=fields.Datetime.now(), archivo_consolidado_usuario_id=self.env.uid)
            # Un archivo nuevo vuelve a revisión: se limpia un rechazo anterior.
            vals.setdefault('estado_archivo_consolidado', 'aceptado')
            vals.setdefault('obs_archivo_consolidado', False)
        else:
            vals.update(archivo_consolidado_fecha=False, archivo_consolidado_usuario_id=False,
                        archivo_consolidado_nombre=False, estado_archivo_consolidado='aceptado',
                        obs_archivo_consolidado=False)
        return vals

    def _check_pdf_generable(self):
        """El PDF se arma con las fotos cargadas: no aplica si el expediente vino en un solo archivo."""
        cubiertos = self.filtered('requisitos_cubiertos')
        if cubiertos:
            raise UserError('El expediente de %s se cargó en un solo archivo (PDF o Word): descarga ese archivo '
                            'en lugar de generar el PDF.' % ', '.join(cubiertos.mapped('cliente_id.name')))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._marcar_archivo_consolidado(v) for v in vals_list])

    def write(self, vals):
        return super().write(self._marcar_archivo_consolidado(vals))

    # ======================
    # PUSH NOTIFICATIONS
    # ======================

    def _send_firebase_notification(self, title, body, action_type):
        """
        Envía notificación push al asesor/vendedor asociado al expediente.

        Args:
            title (str): Título de la notificación
            body (str): Mensaje de la notificación
            action_type (str): Tipo de acción (rechazado, incompleto, completo)
        """
        self.ensure_one()

        if not self.asesora_id:
            _logger.warning(f'Expediente {self.id} no tiene asesor asociado, no se envía notificación')
            return

        try:
            # Importar el servicio de notificaciones
            from ..services.notification_service import NotificationService

            notification_service = NotificationService(self.env)

            # Preparar datos adicionales
            data = {
                'expediente_id': self.id,
                'action': action_type,
                'timestamp': fields.Datetime.now().isoformat(),
                'cliente_id': self.cliente_id.id if self.cliente_id else None,
                'cliente_name': self.cliente_id.name if self.cliente_id else '',
            }

            # Enviar notificación al asesor/vendedor
            result = notification_service.send_to_user(
                user_id=self.asesora_id.id,
                title=title,
                body=body,
                data=data
            )

            if result.get('success'):
                _logger.info(
                    f'Notificación enviada para expediente {self.id}: '
                    f'{result.get("sent")} dispositivo(s)'
                )
            else:
                _logger.warning(
                    f'No se pudo enviar notificación para expediente {self.id}: '
                    f'{result.get("error")}'
                )

        except Exception as e:
            # No bloquear la operación si falla el envío de notificaciones
            _logger.error(
                f'Error enviando notificación para expediente {self.id}: {str(e)}',
                exc_info=True
            )

    # ======================
    # RECHAZAR CON WIZARD
    # ======================

    def action_rechazar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Rechazar expediente',
            'res_model': 'adt.expediente.rechazo.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_expediente_id': self.id
            }
        }

    # New actions to set manual_state so buttons can mark the expediente
    def action_mark_incompleto_expediente(self):
        self.write({'state': 'incompleto_expediente'})
        # Enviar notificación Firebase
        cliente_nombre = self.cliente_id.name or 'Cliente'
        self._send_firebase_notification(
            title='Expediente incompleto - Documentación',
            body=f'Hola {cliente_nombre}, tu expediente está incompleto. Por favor revisa los datos enviados.',
            action_type='incompleto_expediente_documentacion'
        )

    def action_mark_incompleto_fase_final(self):
        self.write({'state': 'incompleto_fase_final'})
        # Enviar notificación Firebase
        cliente_nombre = self.cliente_id.name or 'Cliente'
        self._send_firebase_notification(
            title='Expediente incompleto - Fase Final',
            body=f'Hola {cliente_nombre}, tu expediente está incompleto en la fase final. Por favor revisa la documentación.',
            action_type='incompleto_fase_final'
        )

    def action_mark_completo(self):
        self.write({'state': 'completo'})
        # Enviar notificación Firebase
        cliente_nombre = self.cliente_id.name or 'Cliente'
        self._send_firebase_notification(
            title='Expediente aprobado',
            body=f'¡Felicitaciones {cliente_nombre}! Tu expediente ha sido aprobado con éxito.',
            action_type='completo'
        )

    def action_mark_aprobado_sin_desembolso(self):
        self.write({'state': 'aprobado_sin_desembolso'})
        # Enviar notificación Firebase
        cliente_nombre = self.cliente_id.name or 'Cliente'
        self._send_firebase_notification(
            title='Expediente aprobado sin desembolso',
            body=f'Hola {cliente_nombre}, tu expediente ha sido aprobado sin desembolso.',
            action_type='aprobado_sin_desembolso'
        )

    # ======================
    # POPUPS DE FOTOS
    # ======================

    def _open_popup(self, view_xmlid, title):
        self.ensure_one()
        # If the record is not yet saved (no id), avoid opening a popup that could
        # trigger unwanted validations or create an empty record; notify the user
        # to save first. This prevents constraints from running while simply
        # viewing images on transient/unsaved records.
        if not self.id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Guardar expediente',
                    'message': 'Guarda el expediente antes de ver las fotos.',
                    'sticky': False,
                    'type': 'warning'
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'adt.expediente',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(view_xmlid).id,
            'target': 'new',
        }

    # Imágenes que se pueden editar (rotar / recortar). El pasaporte queda fuera: es solo histórico.
    def _campos_imagen_editables(self):
        return [nombre for nombre, campo in self._fields.items()
                if campo.type == 'binary' and nombre.startswith('foto_')
                and not nombre.startswith('foto_pasaporte_')]

    def action_editar_imagen(self):
        self.ensure_one()
        campo = self.env.context.get('campo_imagen')
        if campo not in self._campos_imagen_editables():
            raise UserError('La imagen indicada no se puede editar.')
        if not self[campo]:
            raise UserError('No hay imagen cargada para editar.')
        wizard = self.env['adt.expediente.imagen.wizard'].create({
            'expediente_id': self.id,
            'campo': campo,
            'campo_label': self._fields[campo].get_description(self.env)['string'],
            'imagen_original': self[campo],
        })
        return wizard._reabrir()

    def action_ver_foto_vivienda(self):
        return self._open_popup('adt_expedientes.view_foto_vivienda_popup', 'Foto vivienda')

    def action_ver_foto_ubicacion(self):
        return self._open_popup('adt_expedientes.view_foto_ubicacion_popup', 'Ubicación - Foto')

    def action_ver_foto_fachada(self):
        return self._open_popup('adt_expedientes.view_foto_fachada_popup', 'Fachada - Foto')

    def action_ver_foto_contrato(self):
        return self._open_popup('adt_expedientes.view_foto_contrato_popup', 'Contrato - Foto')

    def action_ver_foto_ingresos(self):
        return self._open_popup('adt_expedientes.view_foto_ingresos_popup', 'Fotos ingresos')

    def action_ver_foto_licencia(self):
        return self._open_popup('adt_expedientes.view_foto_licencia_popup', 'Foto licencia')

    def action_ver_foto_beneficiario(self):
        return self._open_popup('adt_expedientes.view_foto_beneficiario_popup', 'Documento del beneficiario')

    def action_ver_foto_entrega(self):
        return self._open_popup('adt_expedientes.view_foto_entrega_popup', 'Foto entrega')

    def action_ver_foto_recibo(self):
        return self._open_popup('adt_expedientes.view_foto_recibo_popup', 'Recibo')

    def action_ver_foto_sentinel_1(self):
        return self._open_popup('adt_expedientes.view_foto_sentinel_1_popup', 'Sentinel - Score')

    def action_ver_foto_sentinel_2(self):
        return self._open_popup('adt_expedientes.view_foto_sentinel_2_popup', 'Sentinel - Deudas')

    # Popup actions for mototaxista / non-mototaxista images
    def action_ver_foto_moto(self):
        return self._open_popup('adt_expedientes.view_foto_moto_popup', 'Foto en la moto')

    def action_ver_foto_soat(self):
        return self._open_popup('adt_expedientes.view_foto_soat_popup', 'SOAT')

    def action_ver_foto_tarjeta_frente(self):
        return self._open_popup('adt_expedientes.view_foto_tarjeta_frente_popup', 'Tarjeta - Frente')

    def action_ver_foto_tarjeta_reverso(self):
        return self._open_popup('adt_expedientes.view_foto_tarjeta_reverso_popup', 'Tarjeta - Reverso')

    def action_ver_foto_lugar_trabajo(self):
        return self._open_popup('adt_expedientes.view_foto_lugar_trabajo_popup', 'Lugar de trabajo')

    def action_ver_foto_lugar_negocio(self):
        return self._open_popup('adt_expedientes.view_foto_lugar_negocio_popup', 'Lugar del negocio')

    def action_ver_foto_boletas(self):
        return self._open_popup('adt_expedientes.view_foto_boletas_popup', 'Boletas / Contratos / Recibos')

    def action_ver_foto_estado_cuenta(self):
        return self._open_popup('adt_expedientes.view_foto_estado_cuenta_popup', 'Estado de cuenta')

    def action_ver_foto_sentinel(self):
        """Open a popup that shows both sentinel images together."""
        return self._open_popup('adt_expedientes.view_foto_sentinel_popup', 'Sentinel - Imágenes')

    # Document popups
    def action_ver_foto_dni_frente(self):
        return self._open_popup('adt_expedientes.view_foto_dni_frente_popup', 'DNI - Anverso')

    def action_ver_foto_dni_reverso(self):
        return self._open_popup('adt_expedientes.view_foto_dni_reverso_popup', 'DNI - Reverso')

    def action_ver_foto_ce_frente(self):
        return self._open_popup('adt_expedientes.view_foto_ce_frente_popup', 'CE - Anverso')

    def action_ver_foto_ce_reverso(self):
        return self._open_popup('adt_expedientes.view_foto_ce_reverso_popup', 'CE - Reverso')

    def action_ver_foto_pasaporte_frente(self):
        return self._open_popup('adt_expedientes.view_foto_pasaporte_frente_popup', 'Pasaporte - Anverso')

    def action_ver_foto_pasaporte_reverso(self):
        return self._open_popup('adt_expedientes.view_foto_pasaporte_reverso_popup', 'Pasaporte - Reverso')

    def action_open_expediente(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Expediente',
            'res_model': 'adt.expediente',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_print_expediente_pdf(self):
        """Generate a PDF document with expediente data and attached images."""
        self.ensure_one()
        self._check_pdf_generable()
        if not self.cliente_id:
            raise UserError('Debe seleccionar un cliente antes de generar el PDF.')

        has_main_image = any([
            self.foto_dni_frente,
            self.foto_ce_frente,
            self.foto_pasaporte_frente,
            self.foto_licencia,
            self.foto_recibo,
            self.foto_sentinel_1,
            self.foto_entrega,
        ])
        if not has_main_image:
            raise UserError('No hay imagenes cargadas para generar el PDF del expediente.')

        return self.env.ref('adt_expedientes.action_report_adt_expediente_pdf').report_action(self)

    # Helper for QWeb reports: return a data URI string for a Binary field name
    def get_data_uri(self, field_name):
        """Return a 'data:image/png;base64,...' string for the binary field specified by
        `field_name`. Returns an empty string when the field is falsy. This abstracts
        bytes/str handling away from QWeb templates (avoids calling .decode() in QWeb).
        """
        self.ensure_one()
        val = getattr(self, field_name, False)
        if not val:
            return ''
        # If it's bytes, try to decode; otherwise assume it's a base64 string
        try:
            if isinstance(val, (bytes, bytearray)):
                b64 = val.decode('utf-8')
            else:
                b64 = val
        except Exception:
            # As a last resort, base64-encode raw bytes
            try:
                import base64 as _b64
                b64 = _b64.b64encode(val).decode('utf-8')
            except Exception:
                return ''
        return 'data:image/png;base64,' + (b64 or '')

    # Backwards compatible alias (in case any template still references _get_data_uri)
    get_data_uri_safe = get_data_uri
    # Keep underscore-named alias because some templates still call doc._get_data_uri(...)
    _get_data_uri = get_data_uri

    # ======================
    # VALIDACIONES
    # ======================

    # NOTE: The original implementation of _compute_state is commented out below for temporary disabling / debugging.
    # If you want to re-enable the original logic restore the block and remove the no-op implementation that follows.
    #
    # @api.depends(
    #     'foto_vivienda', 'foto_ingresos', 'direccion_cliente', 'foto_licencia',
    #     'foto_entrega', 'placa', 'chasis',
    #     'estado_foto_vivienda', 'estado_foto_ingresos',
    #     'estado_direccion', 'estado_foto_licencia',
    #     'foto_dni_frente', 'foto_dni_reverso', 'estado_foto_dni',
    #     'foto_ce_frente', 'foto_ce_reverso', 'estado_foto_ce',
    #     'foto_pasaporte_frente', 'foto_pasaporte_reverso', 'estado_foto_pasaporte', 'cliente_id',
    #     'foto_recibo', 'estado_foto_recibo'
    # )
    # def _compute_state(self):
    #     """Compute the overall state and split previous single 'incompleto' into two precise values:
    #     - 'incompleto_expediente' when the expediente (requisitos) is incomplete but fase final may be complete
    #     - 'incompleto_fase_final' when requisitos are complete but the final phase is incomplete
    #     """
    #     for rec in self:
    #
    #         # Keep rejected untouched
    #         if rec.state == 'rechazado':
    #             continue
    #
    #         # New unsaved record
    #         if not rec.id:
    #             rec.state = 'por_revisar'
    #             continue
    #
    #         # Document validation depending on nationality
    #         doc_ok = True
    #         if rec.cliente_id:
    #             nat = getattr(rec.cliente_id, 'nationality', False)
    #             if nat == 'peruana':
    #                 doc_ok = bool(rec.foto_dni_frente and rec.foto_dni_reverso and rec.estado_foto_dni == 'aceptado')
    #             elif nat and nat != 'peruana':
    #                 ce_ok = bool(rec.foto_ce_frente and rec.foto_ce_reverso and rec.estado_foto_ce == 'aceptado')
    #                 pas_ok = bool(rec.foto_pasaporte_frente and rec.foto_pasaporte_reverso and rec.estado_foto_pasaporte == 'aceptado')
    #                 doc_ok = bool(ce_ok or pas_ok)
    #
    #         requisitos_ok = all([
    #             rec.foto_vivienda,
    #             rec.foto_ingresos,
    #             rec.direccion_cliente,
    #             rec.foto_licencia,
    #             rec.foto_recibo,
    #             doc_ok,
    #             rec.estado_foto_vivienda == 'aceptado',
    #             rec.estado_foto_ingresos == 'aceptado',
    #             rec.estado_direccion == 'aceptado',
    #             rec.estado_foto_licencia == 'aceptado',
    #             rec.estado_foto_recibo == 'aceptado',
    #         ])
    #
    #         fase_final_ok = all([
    #             rec.foto_entrega,
    #             rec.placa,
    #             rec.chasis,
    #         ])
    #
    #         # Determine precise incomplete state
    #         if requisitos_ok and fase_final_ok:
    #             rec.state = 'completo'
    #         elif requisitos_ok and not fase_final_ok:
    #             # expediente requirements satisfied, but final phase missing
    #             rec.state = 'incompleto_fase_final'
    #         elif fase_final_ok and not requisitos_ok:
    #             # final phase satisfied but expediente requirements missing
    #             rec.state = 'incompleto_expediente'
    #         else:
    #             rec.state = 'por_revisar'
    #
    #         # Respect manual_state if set; this allows buttons to control the state
    #         if rec.manual_state:
    #             rec.state = rec.manual_state

    @api.depends()  # keep a compute decorator to avoid Odoo warnings; no dependencies since this is a no-op
    def _compute_state(self):
        """Temporarily disabled compute. This no-op respects `manual_state` if it is set,
        otherwise leaves the stored `state` unchanged (so we don't overwrite values unintentionally).
        The original implementation is retained as a commented block above for reference.
        """
        for rec in self:
            if rec.manual_state:
                # If a manual override is present, ensure the stored state reflects it.
                rec.state = rec.manual_state
            else:
                # Do nothing: preserve existing stored `state` value.
                # Intentionally left blank to avoid recalculation while debugging.
                pass
"""
    @api.constrains('cliente_id', 'foto_dni_frente', 'foto_dni_reverso', 'foto_ce_frente', 'foto_ce_reverso')
    def _check_document_photos(self):
        for rec in self:
            if not rec.cliente_id:
                continue
            nat = getattr(rec.cliente_id, 'nationality', False)
            # treat any nationality that is not 'peruana' as foreign
            if nat == 'peruana':
                if not (rec.foto_dni_frente and rec.foto_dni_reverso):
                    raise ValidationError("Cliente peruano: debe subir ambas caras del DNI (anverso y reverso).")
                if rec.estado_foto_dni != 'aceptado':
                    raise ValidationError("El DNI debe estar en estado 'Aceptado'.")
            elif nat and nat != 'peruana':
                # require CE front+back, and it must be accepted (pasaporte ya no se acepta)
                if not (rec.foto_ce_frente and rec.foto_ce_reverso):
                    raise ValidationError("Cliente extranjero: debe subir Carnet de Extranjería (anverso/reverso) vigente.")
                if rec.estado_foto_ce != 'aceptado':
                    raise ValidationError("El Carnet de Extranjería debe estar en estado 'Aceptado'.")"""
