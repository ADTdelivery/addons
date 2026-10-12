# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ESTADOS_TRAMITE = [
    ('pendiente', 'Pendiente'),
    ('en_tramite', 'En trámite'),
    ('observado', 'Observado'),
    ('finalizado', 'Finalizado'),
    ('historial', 'Historial'),
]
# Con placa: el historial es un finalizado archivado de la vista diaria.
ESTADOS_CON_PLACA = ('finalizado', 'historial')

PARAM_DIAS_FINALIZADO = 'adt_tramite_placa.dias_finalizado'
DIAS_FINALIZADO_DEFECTO = 7

# Mismo criterio que adt_dashboard_flota.
PLATE_PLACEHOLDERS = {
    'S/P', 'SP', 'S/N', 'SN', 'SIN PLACA', 'EN TRAMITE', 'EN TRÁMITE',
    'TRAMITE', 'TRÁMITE', 'PENDIENTE', 'NULL', 'NONE', 'N/A', 'NA', '-', '--',
}


def plate_is_ready(plate):
    """Una placa está lista si tiene un valor real (no placeholder) con al menos un dígito."""
    value = (plate or '').strip().upper()
    if not value or value in PLATE_PLACEHOLDERS:
        return False
    return any(ch.isdigit() for ch in value)


class AdtTramitePlaca(models.Model):
    _name = 'adt.tramite.placa'
    _description = 'Trámite de placa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Referencia', readonly=True, copy=False, default='Nuevo')
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Moto', required=True, ondelete='restrict', index=True, tracking=True,
    )
    factura_id = fields.Many2one(related='vehicle_id.x_id_facturacion', string='Factura', store=True)
    proveedor_id = fields.Many2one(related='factura_id.partner_id', string='Proveedor', store=True)
    modelo_id = fields.Many2one(related='vehicle_id.model_id', string='Modelo', store=True)
    chasis = fields.Char(related='vehicle_id.vin_sn', string='Chasis')
    motor = fields.Char(related='vehicle_id.x_motor_sn', string='Motor')

    state = fields.Selection(
        ESTADOS_TRAMITE, string='Estado', default='pendiente', required=True, readonly=True,
        tracking=True, group_expand='_read_group_state',
    )
    fecha_inicio = fields.Datetime(string='Inicio del trámite', readonly=True)
    fecha_ultima_observacion = fields.Datetime(string='Última observación', readonly=True)
    fecha_fin = fields.Datetime(string='Fin del trámite', readonly=True)
    fecha_historial = fields.Datetime(string='Pasó a historial', readonly=True)
    motivo_observacion = fields.Text(string='Motivo de la observación', readonly=True, tracking=True)
    cant_observaciones = fields.Integer(string='Observaciones', readonly=True)
    dias_tramite = fields.Float(string='Días de trámite', compute='_compute_dias_tramite', digits=(16, 1))
    dias_sin_iniciar = fields.Float(string='Días sin iniciar', compute='_compute_dias_tramite', digits=(16, 1))

    num_placa = fields.Char(string='N° Placa', tracking=True)
    tarjeta_propiedad = fields.Binary(string='Tarjeta de propiedad', attachment=True)
    tarjeta_propiedad_filename = fields.Char(string='Nombre archivo tarjeta')
    notas = fields.Text(string='Notas')

    _sql_constraints = [
        ('vehicle_unique', 'unique(vehicle_id)', 'La moto ya tiene un trámite de placa.'),
    ]

    @api.model
    def _read_group_state(self, states, domain, order):
        return [key for key, _label in ESTADOS_TRAMITE]

    @api.depends('fecha_inicio', 'fecha_fin', 'state')
    def _compute_dias_tramite(self):
        ahora = fields.Datetime.now()
        for rec in self:
            if rec.fecha_inicio:
                rec.dias_tramite = ((rec.fecha_fin or ahora) - rec.fecha_inicio).total_seconds() / 86400
            else:
                rec.dias_tramite = 0
            if rec.state == 'pendiente' and rec.create_date:
                rec.dias_sin_iniciar = max(0.0, (ahora - rec.create_date).total_seconds() / 86400)
            else:
                rec.dias_sin_iniciar = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('adt.tramite.placa') or 'Nuevo'
        return super().create(vals_list)

    # ── Transiciones ────────────────────────────────────────────────────────

    def _validar_estado(self, permitidos, accion):
        for rec in self:
            if rec.state not in permitidos:
                raise UserError(_('No se puede %(accion)s el trámite %(ref)s porque está «%(estado)s».',
                                  accion=accion, ref=rec.name,
                                  estado=dict(ESTADOS_TRAMITE)[rec.state]))

    def action_iniciar(self):
        self._validar_estado(['pendiente'], _('iniciar'))
        self.write({'state': 'en_tramite', 'fecha_inicio': fields.Datetime.now()})

    def action_observar(self):
        self._validar_estado(['en_tramite'], _('observar'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Observar trámite'),
            'res_model': 'adt.tramite.placa.observar.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tramite_id': self.id},
        }

    def _observar(self, motivo):
        self._validar_estado(['en_tramite'], _('observar'))
        for rec in self:
            rec.write({
                'state': 'observado',
                'motivo_observacion': motivo,
                'fecha_ultima_observacion': fields.Datetime.now(),
                'cant_observaciones': rec.cant_observaciones + 1,
            })

    def action_levantar_observacion(self):
        self._validar_estado(['observado'], _('levantar la observación de'))
        self.write({'state': 'en_tramite'})

    def action_finalizar(self):
        self._validar_estado(['en_tramite'], _('finalizar'))
        for rec in self:
            if not plate_is_ready(rec.num_placa):
                raise UserError(_('Ingrese el N° de placa antes de finalizar el trámite %s.') % rec.name)
            rec.write({
                'state': 'finalizado',
                'num_placa': rec.num_placa.strip().upper(),
                'fecha_fin': fields.Datetime.now(),
            })
            rec._pasar_datos_vehiculo()

    def action_reabrir(self):
        self._validar_estado(list(ESTADOS_CON_PLACA), _('reabrir'))
        self.write({'state': 'en_tramite', 'fecha_fin': False, 'fecha_historial': False})

    # ── Historial ───────────────────────────────────────────────────────────

    @api.model
    def _dias_finalizado(self):
        """Días que un trámite permanece en Finalizado antes de pasar a Historial (configurable)."""
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_DIAS_FINALIZADO, DIAS_FINALIZADO_DEFECTO)
        try:
            return max(0, int(valor))
        except (TypeError, ValueError):
            return DIAS_FINALIZADO_DEFECTO

    @api.model
    def _cron_pasar_a_historial(self):
        limite = fields.Datetime.now() - timedelta(days=self._dias_finalizado())
        tramites = self.search([('state', '=', 'finalizado'), ('fecha_fin', '<=', limite)])
        tramites.write({'state': 'historial', 'fecha_historial': fields.Datetime.now()})
        return tramites

    def _pasar_datos_vehiculo(self):
        for rec in self:
            vals = {'license_plate': rec.num_placa}
            # tarjeta_propiedad_attachment lo agrega adt_fleet / fleet_addons, si están instalados.
            if rec.tarjeta_propiedad and 'tarjeta_propiedad_attachment' in rec.vehicle_id._fields:
                vals['tarjeta_propiedad_attachment'] = rec.tarjeta_propiedad
            rec.vehicle_id.sudo().write(vals)
