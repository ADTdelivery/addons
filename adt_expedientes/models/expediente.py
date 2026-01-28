from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class AdtExpediente(models.Model):
    _name = 'adt.expediente'
    _description = 'Expediente'
    _rec_name = 'cliente_id'

    # ======================
    # DATOS GENERALES
    # ======================

    state = fields.Selection([
        ('por_revisar', 'Por revisar'),
        ('incompleto', 'Incompleto'),
        ('completo', 'Completo'),
        ('rechazado', 'Rechazado'),
    ], compute='_compute_state', store=True, tracking=True)

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

    @api.depends('cliente_id')
    def _compute_cliente_nationality(self):
        for rec in self:
            rec.cliente_nationality = getattr(rec.cliente_id, 'nationality', False) or False

    # Copy occupation from res.partner (display-only) like cliente_nationality
    cliente_occupation = fields.Char(string='Ocupación', compute='_compute_cliente_occupation', store=False, readonly=True)

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

    # ----------------------
    # Recibo de servicios (luz/agua) - two photos
    # ----------------------
    foto_recibo = fields.Binary(attachment=True, string='Recibo')
    estado_foto_recibo = fields.Selection([
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado')
    ], default='aceptado')
    obs_foto_recibo = fields.Text(string='Observaciones Recibo')

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

    # For foreign clients we need front/reverse for CE and passport
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
    # FASE FINAL
    # ======================

    foto_entrega = fields.Binary(attachment=True)
    placa = fields.Char()
    chasis = fields.Char()

    # ======================
    # ESTADO AUTOMÁTICO
    # ======================

    @api.depends(
        'foto_vivienda', 'foto_ingresos', 'direccion_cliente', 'foto_licencia',
        'foto_entrega', 'placa', 'chasis',
        'estado_foto_vivienda', 'estado_foto_ingresos',
        'estado_direccion', 'estado_foto_licencia',
        'foto_dni_frente', 'foto_dni_reverso', 'estado_foto_dni',
        'foto_ce_frente', 'foto_ce_reverso', 'estado_foto_ce',
        'foto_pasaporte_frente', 'foto_pasaporte_reverso', 'estado_foto_pasaporte', 'cliente_id',
        'foto_recibo', 'estado_foto_recibo'
    )
    def _compute_state(self):
        for rec in self:

            # Mantener rechazado
            if rec.state == 'rechazado':
                continue

            # Registro nuevo
            if not rec.id:
                rec.state = 'por_revisar'
                continue

            # Documento de identidad valid depending on nationality
            doc_ok = True
            if rec.cliente_id:
                nat = getattr(rec.cliente_id, 'nationality', False)
                if nat == 'peruana':
                    doc_ok = bool(rec.foto_dni_frente and rec.foto_dni_reverso and rec.estado_foto_dni == 'aceptado')
                elif nat == 'extranjera':
                    # require both front and reverse for CE and passport
                    ce_ok = bool(rec.foto_ce_frente and rec.foto_ce_reverso and rec.estado_foto_ce == 'aceptado')
                    pas_ok = bool(rec.foto_pasaporte_frente and rec.foto_pasaporte_reverso and rec.estado_foto_pasaporte == 'aceptado')
                    doc_ok = bool(ce_ok or pas_ok)

            requisitos_ok = all([
                rec.foto_vivienda,
                rec.foto_ingresos,
                rec.direccion_cliente,
                rec.foto_licencia,
                rec.foto_recibo,
                doc_ok,
                rec.estado_foto_vivienda == 'aceptado',
                rec.estado_foto_ingresos == 'aceptado',
                rec.estado_direccion == 'aceptado',
                rec.estado_foto_licencia == 'aceptado',
                rec.estado_foto_recibo == 'aceptado',
            ])

            fase_final_ok = all([
                rec.foto_entrega,
                rec.placa,
                rec.chasis,
            ])

            if requisitos_ok and fase_final_ok:
                rec.state = 'completo'
            elif requisitos_ok or fase_final_ok:
                rec.state = 'incompleto'
            else:
                rec.state = 'por_revisar'

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

    # ======================
    # POPUPS DE FOTOS
    # ======================

    def _open_popup(self, view_xmlid, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'adt.expediente',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(view_xmlid).id,
            'target': 'new',
        }

    def action_ver_foto_vivienda(self):
        return self._open_popup('adt_expedientes.view_foto_vivienda_popup', 'Foto vivienda')

    def action_ver_foto_ingresos(self):
        return self._open_popup('adt_expedientes.view_foto_ingresos_popup', 'Fotos ingresos')

    def action_ver_foto_licencia(self):
        return self._open_popup('adt_expedientes.view_foto_licencia_popup', 'Foto licencia')

    def action_ver_foto_entrega(self):
        return self._open_popup('adt_expedientes.view_foto_entrega_popup', 'Foto entrega')

    def action_ver_foto_recibo(self):
        return self._open_popup('adt_expedientes.view_foto_recibo_popup', 'Recibo')

    def action_ver_foto_sentinel_1(self):
        return self._open_popup('adt_expedientes.view_foto_sentinel_1_popup', 'Sentinel - Score')

    def action_ver_foto_sentinel_2(self):
        return self._open_popup('adt_expedientes.view_foto_sentinel_2_popup', 'Sentinel - Deudas')

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

    # ======================
    # VALIDACIONES
    # ======================

    @api.constrains('cliente_id', 'foto_dni_frente', 'foto_dni_reverso', 'foto_ce_frente', 'foto_ce_reverso', 'foto_pasaporte_frente', 'foto_pasaporte_reverso')
    def _check_document_photos(self):
        for rec in self:
            if not rec.cliente_id:
                continue
            nat = getattr(rec.cliente_id, 'nationality', False)
            if nat == 'peruana':
                if not (rec.foto_dni_frente and rec.foto_dni_reverso):
                    raise ValidationError("Cliente peruano: debe subir ambas caras del DNI (anverso y reverso).")
                if rec.estado_foto_dni != 'aceptado':
                    raise ValidationError("El DNI debe estar en estado 'Aceptado'.")
            elif nat == 'extranjera':
                # require CE front+back OR passport front+back, and the provided doc must be accepted
                ce_present = bool(rec.foto_ce_frente and rec.foto_ce_reverso)
                pas_present = bool(rec.foto_pasaporte_frente and rec.foto_pasaporte_reverso)
                if not (ce_present or pas_present):
                    raise ValidationError("Cliente extranjero: debe subir Carnet de Extranjería (anverso/reverso) o Pasaporte (anverso/reverso) vigentes.")
                if ce_present and rec.estado_foto_ce != 'aceptado':
                    raise ValidationError("El Carnet de Extranjería debe estar en estado 'Aceptado'.")
                if pas_present and rec.estado_foto_pasaporte != 'aceptado':
                    raise ValidationError("El Pasaporte debe estar en estado 'Aceptado'.")
