from odoo import api, fields, models


class ADTComercialCuotasPendientes(models.Model):
    _name = 'adt.comercial.cuotas.pendientes'
    _description = 'ADT Cuotas pendientes por validar'
    _order = 'create_date desc, id desc'

    cuota_id = fields.Many2one('adt.comercial.cuotas', string='Cuota', required=True, ondelete='cascade', index=True)
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', compute='_compute_snapshot_fields', store=True)
    placa = fields.Char(string='Placa', compute='_compute_snapshot_fields', store=True)
    numero_documento = fields.Char(string='Numero de documento', compute='_compute_snapshot_fields', store=True)
    monto_cuota = fields.Float(string='Monto de cuota', required=True)
    numero_operacion_cuota = fields.Char(string='Nro operacion cuota')
    monto_mora = fields.Float(string='Monto de mora', default=0.0)
    numero_operacion_mora = fields.Char(string='Nro operacion mora')
    comprobante_line_ids = fields.One2many(
        'adt.comercial.cuotas.pendientes.comprobante',
        'pendiente_id',
        string='Comprobantes'
    )
    comprobante_count = fields.Integer(string='Cantidad comprobantes', compute='_compute_comprobante_count', store=True)
    fecha = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now)
    comentario = fields.Text(string='Comentario')
    estado = fields.Selection(
        [
            ('PENDIENTE_VALIDAR', 'PENDIENTE_VALIDAR'),
            ('VALIDADO', 'VALIDADO'),
        ],
        string='Estado',
        default='PENDIENTE_VALIDAR',
        required=True,
        index=True,
    )

    @api.depends('cuota_id', 'cuota_id.cuenta_id', 'cuota_id.cuenta_id.partner_id', 'cuota_id.cuenta_id.vehiculo_id')
    def _compute_snapshot_fields(self):
        for rec in self:
            cuenta = rec.cuota_id.cuenta_id
            rec.cuenta_id = cuenta.id if cuenta else False
            rec.placa = cuenta.vehiculo_id.license_plate if cuenta and cuenta.vehiculo_id else False
            rec.numero_documento = cuenta.partner_id.vat if cuenta and cuenta.partner_id else False

    @api.depends('comprobante_line_ids')
    def _compute_comprobante_count(self):
        for rec in self:
            rec.comprobante_count = len(rec.comprobante_line_ids)

    def _sync_cuota_pendiente_validar(self, cuotas=None):
        cuotas = cuotas or self.mapped('cuota_id')
        for cuota in cuotas:
            lines = cuota.cuota_pendiente_ids
            if not lines:
                new_state = 'SIN_REGISTRO'
            elif any(line.estado == 'VALIDADO' for line in lines):
                new_state = 'VALIDADO'
            else:
                new_state = 'PENDIENTE_VALIDAR'
            cuota.sudo().write({'pendiente_validar': new_state})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_cuota_pendiente_validar()
        return records

    def write(self, vals):
        cuotas_before = self.mapped('cuota_id')
        res = super().write(vals)
        self._sync_cuota_pendiente_validar(cuotas_before | self.mapped('cuota_id'))
        return res

    def unlink(self):
        cuotas_before = self.mapped('cuota_id')
        res = super().unlink()
        (self.env['adt.comercial.cuotas.pendientes'].browse())._sync_cuota_pendiente_validar(cuotas_before)
        return res


class ADTComercialCuotasPendientesComprobante(models.Model):
    _name = 'adt.comercial.cuotas.pendientes.comprobante'
    _description = 'Comprobante de cuota pendiente'
    _order = 'id asc'

    pendiente_id = fields.Many2one(
        'adt.comercial.cuotas.pendientes',
        string='Pendiente',
        required=True,
        ondelete='cascade',
        index=True,
    )
    numero_operacion = fields.Char(string='Numero operacion', required=True, index=True)
    image = fields.Binary(string='Imagen comprobante', attachment=True)

