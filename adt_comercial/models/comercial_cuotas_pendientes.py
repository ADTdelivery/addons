from odoo import fields, models


class ADTComercialCuotasPendientes(models.Model):
    _name = 'adt.comercial.cuotas.pendientes'
    _description = 'ADT Cuotas pendientes por validar'
    _order = 'create_date desc, id desc'

    cuota_id = fields.Many2one('adt.comercial.cuotas', string='Cuota', required=True, ondelete='cascade', index=True)
    monto_cuota = fields.Float(string='Monto de cuota', required=True)
    numero_operacion_cuota = fields.Char(string='Nro operacion cuota', required=True)
    monto_mora = fields.Float(string='Monto de mora', default=0.0)
    numero_operacion_mora = fields.Char(string='Nro operacion mora')
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

