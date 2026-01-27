from odoo import models, fields, api
from odoo.exceptions import UserError


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
        'estado_direccion', 'estado_foto_licencia'
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

            requisitos_ok = all([
                rec.foto_vivienda,
                rec.foto_ingresos,
                rec.direccion_cliente,
                rec.foto_licencia,
                rec.estado_foto_vivienda == 'aceptado',
                rec.estado_foto_ingresos == 'aceptado',
                rec.estado_direccion == 'aceptado',
                rec.estado_foto_licencia == 'aceptado',
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




