# -*- coding: utf-8 -*-
"""
Regla de Mantenimiento Preventivo (ej. Cambio de aceite, Cambio de frenos)
y sus Umbrales de kilometraje.

Ver propuesta-mantenimiento-preventivo-traccar.md, secciones 2.2 y 4.

Aquí es donde se configura, por cada tipo de mantenimiento:
    - cuántos DÍAS dura la campaña de notificaciones (dias_notificacion)
    - cuántas NOTIFICACIONES se envían por día (notificaciones_por_dia)
    - la secuencia de kilometrajes que la disparan (umbral_ids)

Decisión de negocio confirmada (sección 2.2): los umbrales NO son un
intervalo fijo. Son una lista ordenada y extensible ("umbral_ids") propia de
cada regla: el primer cambio de aceite puede ser a los 600km, el segundo a
los 1000km, el tercero a los 2000km, etc. Esta lista se amplía/edita en
cualquier momento desde este mismo formulario, sin tocar código.
"""
from urllib.parse import quote

from odoo import api, fields, models
from odoo.exceptions import ValidationError

HORAS_DISPONIBLES = ['%02d:%02d' % (h, m) for h in range(24) for m in (0, 30)]

MENSAJE_TEMPLATE_DEFAULT = (
    'Tu vehículo {placa} alcanzó {km_actual} km. '
    'Es momento de realizar el mantenimiento: {regla}.'
)


class AdtMantenimientoRegla(models.Model):
    _name = 'adt.mantenimiento.regla'
    _description = 'Regla de Mantenimiento Preventivo (por kilometraje)'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True, help='Ej: Cambio de aceite')
    code = fields.Char(
        string='Código interno',
        help='Identificador técnico opcional, ej: cambio_aceite. No se usa para '
             'la lógica de negocio, solo como referencia.',
    )
    sequence = fields.Integer(string='Secuencia', default=10)

    dias_notificacion = fields.Integer(
        string='Días de campaña', required=True, default=3,
        help='Cantidad de días que durará la campaña de notificaciones una vez '
             'disparada la regla (se copia a cada campaña al crearse; cambiar '
             'este valor no afecta campañas ya en curso).',
    )
    notificaciones_por_dia = fields.Integer(
        string='Notificaciones por día', required=True, default=3,
        help='Cantidad de notificaciones push que se enviarán cada día mientras '
             'la campaña esté activa (se copia a cada campaña al crearse).',
    )
    horario_ids = fields.Many2many(
        'adt.mantenimiento.horario.slot',
        'adt_mantenimiento_regla_horario_rel', 'regla_id', 'horario_slot_id',
        string='Horarios sugeridos',
        help='Selecciona las horas del día en que se enviarán las notificaciones '
             '(ej: 09:00, 14:00, 19:00). Si eliges menos horas que '
             '"Notificaciones por día", el resto se reparte uniformemente dentro '
             'de la ventana horaria por defecto (Ajustes → Mantenimiento '
             'Preventivo). Si no eliges ninguna, se reparten todas.',
    )
    mensaje_template = fields.Text(
        string='Plantilla de mensaje', required=True,
        default=MENSAJE_TEMPLATE_DEFAULT,
        help='Variables disponibles: {placa}, {km_actual}, {regla}.',
    )
    active = fields.Boolean(string='Activa', default=True)

    umbral_ids = fields.One2many(
        'adt.mantenimiento.umbral', 'regla_id', string='Umbrales de kilometraje',
    )
    umbral_count = fields.Integer(compute='_compute_umbral_count', string='N° Umbrales')

    # ─────────────────────────────────────────────────────────────
    # Oferta / Promoción asociada a esta regla (opcional)
    # ─────────────────────────────────────────────────────────────
    es_oferta = fields.Boolean(
        string='¿Es una oferta?', default=False,
        help='Actívalo para asociar una oferta/promoción comercial a esta '
             'regla (ej. descuento en el cambio de aceite), que se puede '
             'mostrar junto con la notificación de mantenimiento.',
    )
    oferta_titulo = fields.Char(string='Título de la oferta')
    oferta_descripcion = fields.Text(string='Descripción de la oferta')

    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company,
    )
    oferta_moneda_id = fields.Many2one(
        'res.currency', string='Moneda', related='company_id.currency_id', readonly=True,
    )
    oferta_precio = fields.Monetary(
        string='Precio (opcional)', currency_field='oferta_moneda_id',
        help='Déjalo en 0 si la oferta no tiene un precio fijo que mostrar.',
    )

    oferta_dias_duracion = fields.Integer(
        string='Duración de la oferta (días)',
        help='Cantidad de días que dura vigente esta oferta desde que se '
             'muestra al cliente.',
    )

    oferta_wsp_numero = fields.Char(
        string='WhatsApp (número)',
        help='Número de WhatsApp de contacto para esta oferta, en formato '
             'internacional sin +, ej: 51999111222.',
    )
    oferta_wsp_mensaje = fields.Char(
        string='Mensaje predefinido de WhatsApp',
        help='Texto que se precarga en WhatsApp al tocar el link. Si se deja '
             'vacío, se arma automáticamente con el título de la oferta.',
    )
    oferta_wsp_link = fields.Char(
        string='Link de WhatsApp', compute='_compute_oferta_wsp_link', store=True,
        help='Generado automáticamente a partir del número y el mensaje.',
    )

    imagen_ids = fields.One2many(
        'adt.mantenimiento.oferta.imagen', 'regla_id', string='Imágenes de la oferta',
    )

    @api.depends('umbral_ids')
    def _compute_umbral_count(self):
        for rec in self:
            rec.umbral_count = len(rec.umbral_ids)

    @api.depends('oferta_wsp_numero', 'oferta_wsp_mensaje', 'oferta_titulo', 'name')
    def _compute_oferta_wsp_link(self):
        for rec in self:
            digits = ''.join(ch for ch in (rec.oferta_wsp_numero or '') if ch.isdigit())
            if not digits:
                rec.oferta_wsp_link = False
                continue
            mensaje = rec.oferta_wsp_mensaje or (
                'Hola, quiero más información sobre la oferta: %s' % (rec.oferta_titulo or rec.name)
            )
            rec.oferta_wsp_link = 'https://wa.me/%s?text=%s' % (digits, quote(mensaje))

    @api.constrains('dias_notificacion')
    def _check_dias_notificacion(self):
        for rec in self:
            if rec.dias_notificacion <= 0:
                raise ValidationError('Los días de campaña deben ser mayores a 0.')

    @api.constrains('notificaciones_por_dia')
    def _check_notificaciones_por_dia(self):
        for rec in self:
            if rec.notificaciones_por_dia <= 0:
                raise ValidationError('Las notificaciones por día deben ser mayores a 0.')

    @api.constrains('es_oferta', 'oferta_titulo')
    def _check_oferta_titulo(self):
        for rec in self:
            if rec.es_oferta and not rec.oferta_titulo:
                raise ValidationError(
                    'Si "¿Es una oferta?" está activo, debes ingresar un título para la oferta.'
                )

    @api.constrains('oferta_wsp_numero')
    def _check_oferta_wsp_numero(self):
        for rec in self:
            if not rec.oferta_wsp_numero:
                continue
            digits = ''.join(ch for ch in rec.oferta_wsp_numero if ch.isdigit())
            if len(digits) < 8 or len(digits) > 15:
                raise ValidationError(
                    'El número de WhatsApp debe tener entre 8 y 15 dígitos (sin espacios ni símbolos).'
                )

    def _get_horarios_list(self):
        """Devuelve la lista de horarios elegidos, ordenada (['09:00','14:00',...])."""
        self.ensure_one()
        return self.horario_ids.sorted('hora').mapped('name')

    def _get_oferta_imagen_urls(self):
        """
        URLs públicas (servidas por adt_mantenimiento_preventivo/controllers/
        mobile_api.py: get_oferta_imagen) para las imágenes de la oferta de
        esta regla, ordenadas por secuencia. Requiere `web.base.url`
        configurado (Ajustes → Técnico → Parámetros del sistema).
        """
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        return [
            '%s/v1/mantenimiento-preventivo/imagen/%d' % (base_url, imagen.id)
            for imagen in self.imagen_ids.sorted('sequence')
        ]

    def build_mensaje(self, placa, km_actual):
        """Renderiza mensaje_template con las variables disponibles."""
        self.ensure_one()
        km_str = '%.0f' % km_actual if km_actual is not None else '-'
        template = self.mensaje_template or MENSAJE_TEMPLATE_DEFAULT
        try:
            return template.format(placa=placa or '-', km_actual=km_str, regla=self.name)
        except (KeyError, IndexError):
            # Plantilla mal formada (variable inexistente): se cae a la
            # plantilla por defecto para no romper el envío.
            return MENSAJE_TEMPLATE_DEFAULT.format(placa=placa or '-', km_actual=km_str, regla=self.name)


class AdtMantenimientoUmbral(models.Model):
    _name = 'adt.mantenimiento.umbral'
    _description = 'Umbral de kilometraje de una Regla de Mantenimiento'
    _order = 'regla_id, orden'

    regla_id = fields.Many2one(
        'adt.mantenimiento.regla', string='Regla', required=True, ondelete='cascade',
        index=True,
    )
    orden = fields.Integer(
        string='Orden', required=True,
        help='Posición en la secuencia (1, 2, 3...). El motor de reglas siempre '
             'busca "el siguiente umbral no disparado todavía" según este orden, '
             'no asume una progresión aritmética.',
    )
    km_umbral = fields.Float(string='Km umbral', required=True, digits=(10, 1))
    activo = fields.Boolean(
        string='Activo', default=True,
        help='Permite desactivar un umbral puntual sin borrar el histórico.',
    )

    _sql_constraints = [
        ('umbral_regla_orden_uniq', 'unique(regla_id, orden)',
         'Ya existe un umbral con ese orden para esta regla.'),
    ]

    @api.constrains('km_umbral')
    def _check_km_umbral(self):
        for rec in self:
            if rec.km_umbral <= 0:
                raise ValidationError('El kilometraje umbral debe ser mayor a 0.')
