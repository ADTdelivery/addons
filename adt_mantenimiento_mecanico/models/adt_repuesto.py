# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AdtOrdenRepuesto(models.Model):
    _name = 'adt.orden.repuesto'
    _description = 'Repuesto en Orden de Mantenimiento'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Secuencia', default=10)
    orden_id = fields.Many2one('adt.orden.mantenimiento', string='Orden', required=True, ondelete='cascade')
    trabajo_id = fields.Many2one('adt.trabajo', string='Trabajo Asociado')

    # Producto/Repuesto
    product_id = fields.Many2one('product.product', string='Repuesto', required=True,
                                  domain="[('type', 'in', ['product', 'consu'])]")
    descripcion = fields.Char(string='Descripción', related='product_id.name', readonly=True)
    codigo = fields.Char(string='Código', related='product_id.default_code', readonly=True)

    # Tipo
    tipo_repuesto = fields.Selection([
        ('original', 'Original'),
        ('alternativo_premium', 'Alternativo Premium'),
        ('alternativo_estandar', 'Alternativo Estándar'),
        ('generico', 'Genérico')
    ], string='Tipo', required=True, default='original')

    # Cantidad y Stock
    cantidad = fields.Float(string='Cantidad', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', related='product_id.uom_id')
    stock_disponible = fields.Float(string='Stock Disponible', related='product_id.qty_available')
    stock_reservado = fields.Float(string='Reservado', default=0.0)

    # Precios
    precio_unitario = fields.Monetary(string='Precio Unitario', required=True, currency_field='currency_id')
    descuento = fields.Float(string='Descuento %', default=0.0)
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Control de Inventario
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('reserved', 'Reservado'),
        ('used', 'Usado'),
        ('returned', 'Devuelto'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)

    # Trazabilidad
    lote_id = fields.Many2one('stock.production.lot', string='Lote/Serie')
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento')
    proveedor_id = fields.Many2one('res.partner', string='Proveedor', domain="[('supplier_rank', '>', 0)]")

    # Garantía
    tiene_garantia = fields.Boolean(string='Tiene Garantía', default=True)
    meses_garantia = fields.Integer(string='Meses de Garantía', default=6)

    # Autorización
    autorizado = fields.Boolean(string='Autorizado por Cliente', default=False)
    motivo_rechazo = fields.Text(string='Motivo de Rechazo')

    # Observaciones
    observaciones = fields.Text(string='Observaciones')

    @api.depends('cantidad', 'precio_unitario', 'descuento')
    def _compute_subtotal(self):
        for record in self:
            subtotal_bruto = record.cantidad * record.precio_unitario
            descuento_monto = subtotal_bruto * (record.descuento / 100)
            record.subtotal = subtotal_bruto - descuento_monto

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.precio_unitario = self.product_id.list_price

            # Verificar stock
            if self.product_id.qty_available <= 0:
                return {
                    'warning': {
                        'title': _('Sin Stock'),
                        'message': _('Este repuesto no tiene stock disponible. ¿Desea generar solicitud de compra?')
                    }
                }

    @api.constrains('cantidad', 'stock_disponible')
    def _check_stock(self):
        for record in self:
            if record.state == 'reserved':
                if record.cantidad > record.stock_disponible:
                    raise ValidationError(
                        _('No hay suficiente stock de "%s". Disponible: %s, Solicitado: %s') %
                        (record.product_id.name, record.stock_disponible, record.cantidad)
                    )

    def action_reservar(self):
        """Reservar repuesto en inventario"""
        self.ensure_one()
        if self.cantidad > self.stock_disponible:
            raise UserError(_('Stock insuficiente para reservar.'))

        self.state = 'reserved'
        self.stock_reservado = self.cantidad

        # Aquí iría integración con stock.move para reserva real
        # stock_move = self.env['stock.move'].create({...})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Repuesto Reservado'),
                'message': _('%s unidades de %s reservadas') % (self.cantidad, self.product_id.name),
                'type': 'success',
            }
        }

    def action_liberar(self):
        """Liberar reserva de repuesto"""
        self.ensure_one()
        self.state = 'cancelled'
        self.stock_reservado = 0.0

    def action_usar(self):
        """Marcar como usado y descontar de inventario"""
        self.ensure_one()
        if self.state != 'reserved':
            raise UserError(_('El repuesto debe estar reservado primero.'))

        self.state = 'used'
        # Aquí iría la lógica de descuento real de inventario

    def action_solicitar_compra(self):
        """Generar solicitud de compra"""
        self.ensure_one()
        # Aquí iría la creación de purchase.order o purchase.requisition
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Compra'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.proveedor_id.id if self.proveedor_id else False,
                'default_order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_qty': self.cantidad,
                    'price_unit': self.precio_unitario,
                })]
            },
            'target': 'current',
        }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    es_repuesto_taller = fields.Boolean(string='Es Repuesto de Taller', default=False)
    categoria_repuesto = fields.Selection([
        ('motor', 'Motor'),
        ('frenos', 'Frenos'),
        ('suspension', 'Suspensión'),
        ('electrico', 'Sistema Eléctrico'),
        ('transmision', 'Transmisión'),
        ('carroceria', 'Carrocería'),
        ('accesorios', 'Accesorios'),
        ('fluidos', 'Fluidos y Lubricantes'),
        ('filtros', 'Filtros'),
        ('llantas', 'Llantas')
    ], string='Categoría de Repuesto')

    # Compatibilidad
    marca_vehiculo_ids = fields.Many2many('adt.vehiculo.marca', string='Marcas Compatibles')

    # Inventario
    punto_reorden = fields.Float(string='Punto de Reorden', default=5.0)
    alerta_stock_bajo = fields.Boolean(string='Alerta Stock Bajo', compute='_compute_alerta_stock')

    @api.depends('qty_available', 'punto_reorden')
    def _compute_alerta_stock(self):
        for record in self:
            record.alerta_stock_bajo = (record.qty_available <= record.punto_reorden)
