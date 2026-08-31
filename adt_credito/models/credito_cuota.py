from odoo import _, api, fields, models


class CreditoCuota(models.Model):
    _name = 'credito.cuota'
    _description = 'Cuota de un contrato de crédito'
    _order = 'contrato_id, numero_cuota'

    name = fields.Char(string="Cuota", compute='_compute_name', store=True)

    contrato_id = fields.Many2one('credito.contrato', string="Contrato", required=True, ondelete='cascade')
    partner_id = fields.Many2one(related='contrato_id.partner_id', store=True, string="Cliente")
    company_id = fields.Many2one(related='contrato_id.company_id', store=True, string="Compañía")
    currency_id = fields.Many2one(related='contrato_id.currency_id')

    numero_cuota = fields.Integer(string="# Cuota")
    fecha_vencimiento = fields.Date(string="Fecha de vencimiento")
    monto = fields.Monetary(string="Monto de cuota")
    monto_pagado = fields.Monetary(string="Monto pagado", compute='_compute_pagos', store=True)
    saldo = fields.Monetary(string="Saldo", compute='_compute_pagos', store=True)

    pago_ids = fields.One2many('credito.pago', 'cuota_id', string="Pagos")

    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('parcial', 'Pago parcial'),
        ('pagada', 'Pagada'),
        ('vencida', 'Vencida'),
        ('condonada', 'Condonada'),
    ], string="Estado", default='pendiente', compute='_compute_estado', store=True)

    dias_mora = fields.Integer(string="Días de mora", compute='_compute_mora', store=True)
    mora_manual = fields.Boolean(
        string="Editar mora manualmente", default=False,
        help="Activa esta opción para definir manualmente el monto de mora de esta cuota.",
    )
    mora_manual_monto = fields.Monetary(string="Mora manual")
    mora_monto = fields.Monetary(string="Mora", compute='_compute_mora', store=True)
    mora_pagada = fields.Monetary(string="Mora pagada", compute='_compute_mora_pagada', store=True)
    mora_pendiente = fields.Monetary(string="Mora pendiente", compute='_compute_mora_pagada', store=True)

    @api.depends('contrato_id.name', 'numero_cuota', 'fecha_vencimiento')
    def _compute_name(self):
        for rec in self:
            rec.name = '%s - Cuota %s%s' % (
                rec.contrato_id.name or _('Nuevo'),
                rec.numero_cuota,
                (' (%s)' % rec.fecha_vencimiento) if rec.fecha_vencimiento else '',
            )

    @api.depends('pago_ids.monto', 'pago_ids.tipo', 'monto')
    def _compute_pagos(self):
        for rec in self:
            pagos_cuota = rec.pago_ids.filtered(lambda p: p.tipo == 'cuota')
            rec.monto_pagado = sum(pagos_cuota.mapped('monto'))
            rec.saldo = max(rec.monto - rec.monto_pagado, 0.0)

    @api.depends('pago_ids.monto', 'pago_ids.tipo', 'mora_monto')
    def _compute_mora_pagada(self):
        for rec in self:
            pagos_mora = rec.pago_ids.filtered(lambda p: p.tipo == 'mora')
            rec.mora_pagada = sum(pagos_mora.mapped('monto'))
            rec.mora_pendiente = max(rec.mora_monto - rec.mora_pagada, 0.0)

    @api.depends('monto_pagado', 'monto', 'fecha_vencimiento')
    def _compute_estado(self):
        hoy = fields.Date.context_today(self)
        for rec in self:
            if rec.estado == 'condonada':
                continue
            if rec.monto > 0 and rec.monto_pagado >= rec.monto:
                rec.estado = 'pagada'
            elif rec.monto_pagado > 0:
                rec.estado = 'parcial'
            elif rec.fecha_vencimiento and rec.fecha_vencimiento < hoy:
                rec.estado = 'vencida'
            else:
                rec.estado = 'pendiente'

    @api.depends('fecha_vencimiento', 'estado', 'mora_manual', 'mora_manual_monto')
    def _compute_mora(self):
        hoy = fields.Date.context_today(self)
        for rec in self:
            if rec.mora_manual:
                rec.mora_monto = rec.mora_manual_monto
                rec.dias_mora = (
                    (hoy - rec.fecha_vencimiento).days
                    if rec.fecha_vencimiento and hoy > rec.fecha_vencimiento else 0
                )
                continue
            if rec.estado not in ('vencida', 'parcial') or not rec.fecha_vencimiento:
                rec.dias_mora = 0
                rec.mora_monto = 0.0
                continue
            company = rec.company_id or rec.env.company
            dias = (hoy - rec.fecha_vencimiento).days - (company.credito_mora_dias_gracia or 0)
            dias = max(dias, 0)
            rec.dias_mora = dias
            if not dias:
                rec.mora_monto = 0.0
                continue
            if company.credito_mora_tipo == 'porcentual':
                monto = rec.monto * (company.credito_mora_valor / 100.0) * dias
            else:
                monto = company.credito_mora_valor * dias
            if company.credito_mora_tope:
                monto = min(monto, company.credito_mora_tope)
            rec.mora_monto = monto

    def action_pagar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registrar pago'),
            'res_model': 'credito.registrar.pago',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contrato_id': self.contrato_id.id, 'default_cuota_id': self.id},
        }

    @api.model
    def _cron_actualizar_mora(self):
        """Recalcula estado y mora de las cuotas vivas, y ajusta el estado del contrato.

        Se ejecuta a diario vía ir.cron: los campos dependen de la fecha de hoy, así que
        no se recalculan solos con el paso del tiempo sin este barrido explícito.
        """
        cuotas = self.search([('estado', 'not in', ('pagada', 'condonada'))])
        cuotas._compute_estado()
        cuotas._compute_mora()
        cuotas._compute_mora_pagada()
        for contrato in cuotas.mapped('contrato_id'):
            if contrato.estado not in ('activo', 'en_mora'):
                continue
            if contrato.saldo_pendiente <= 0:
                contrato.estado = 'pagado'
            elif contrato.cuotas_vencidas:
                contrato.estado = 'en_mora'
            else:
                contrato.estado = 'activo'
