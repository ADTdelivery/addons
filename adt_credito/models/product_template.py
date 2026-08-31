import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# (código, xmlid del menú padre, modelo a listar, campo de dominio hacia el producto)
# El campo de dominio usa 'in' contra los ids de las variantes (product.product) del
# template, porque credito.contrato.product_id apunta a product.product, no a
# product.template — no siempre coinciden en id aunque el producto no tenga variantes.
CREDITO_MENU_SECTIONS = [
    ('contrato', 'adt_credito.menu_credito_contratos', 'credito.contrato', 'product_id'),
    ('cobranza', 'adt_credito.menu_credito_cobranza', 'credito.cuota', 'contrato_id.product_id'),
    ('pago', 'adt_credito.menu_credito_pagos', 'credito.pago', 'contrato_id.product_id'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    es_financiable = fields.Boolean(
        string="Disponible a crédito",
        default=False,
        help="Permite vender este producto mediante un contrato de crédito en cuotas fijas.",
    )
    credito_enganche_minimo_pct = fields.Float(
        string="Enganche mínimo (%)",
        default=0.0,
        help="Porcentaje mínimo del precio de venta que el cliente debe pagar como "
             "enganche/inicial al originar un contrato de crédito con este producto.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        products._sync_credito_menus()
        return products

    def write(self, vals):
        res = super().write(vals)
        if {'es_financiable', 'name', 'active'} & set(vals):
            self._sync_credito_menus()
        return res

    def unlink(self):
        self._remove_credito_menus()
        return super().unlink()

    def _sync_credito_menus(self):
        """Crea/actualiza (o retira) el submenú por producto en Contratos, Cobranza y
        Pagos, para que cada producto financiable tenga su propia pestaña — así los
        contratos de productos distintos (GPS, Llantas, ...) no se mezclan en una sola
        lista."""
        for product in self:
            if product.es_financiable and product.active:
                for code, parent_xmlid, res_model, domain_field in CREDITO_MENU_SECTIONS:
                    product._ensure_credito_menu(code, parent_xmlid, res_model, domain_field)
            else:
                product._remove_credito_menus()

    def _ensure_credito_menu(self, code, parent_xmlid, res_model, domain_field):
        self.ensure_one()
        parent_menu = self.env.ref(parent_xmlid, raise_if_not_found=False)
        if not parent_menu:
            # El menú padre todavía no existe (p.ej. se está instalando el módulo y
            # views/menu.xml no cargó aún) — no hay nada donde colgar el submenú todavía.
            return

        variant_ids = self.product_variant_ids.ids or [0]
        domain = repr([(domain_field, 'in', variant_ids)])

        action_xmlid = 'credito_action_%s_producto_%d' % (code, self.id)
        action = self._get_or_create_xmlid_record('ir.actions.act_window', action_xmlid, {
            'name': self.display_name,
            'res_model': res_model,
            'view_mode': 'tree,form',
            'domain': domain,
        })

        menu_xmlid = 'credito_menu_%s_producto_%d' % (code, self.id)
        self._get_or_create_xmlid_record('ir.ui.menu', menu_xmlid, {
            'name': self.display_name,
            'parent_id': parent_menu.id,
            'action': 'ir.actions.act_window,%d' % action.id,
        })

    def _get_or_create_xmlid_record(self, model_name, xmlid_name, vals):
        """Crea (o actualiza si ya existe) un registro identificado por un external id
        estable ('adt_credito.<xmlid_name>'), sin depender de la API interna de carga de
        datos XML — solo search/create/write, para no atarse a una firma privada que
        puede cambiar entre versiones de Odoo."""
        IrModelData = self.env['ir.model.data'].sudo()
        Model = self.env[model_name].sudo()

        data = IrModelData.search([
            ('module', '=', 'adt_credito'),
            ('name', '=', xmlid_name),
            ('model', '=', model_name),
        ], limit=1)
        if data and data.res_id:
            record = Model.browse(data.res_id)
            if record.exists():
                record.write(vals)
                return record

        record = Model.create(vals)
        if data:
            data.write({'res_id': record.id})
        else:
            IrModelData.create({
                'name': xmlid_name,
                'module': 'adt_credito',
                'model': model_name,
                'res_id': record.id,
                'noupdate': True,
            })
        return record

    def _remove_credito_menus(self):
        IrModelData = self.env['ir.model.data'].sudo()
        for product in self:
            for code, _parent_xmlid, _res_model, _domain_field in CREDITO_MENU_SECTIONS:
                # El menú se elimina primero para no dejar, ni por un instante, un
                # menuitem apuntando a una acción ya borrada.
                for model_name, prefix in (
                    ('ir.ui.menu', 'credito_menu_'),
                    ('ir.actions.act_window', 'credito_action_'),
                ):
                    xmlid_name = '%s%s_producto_%d' % (prefix, code, product.id)
                    data = IrModelData.search([
                        ('module', '=', 'adt_credito'),
                        ('name', '=', xmlid_name),
                        ('model', '=', model_name),
                    ], limit=1)
                    if data and data.res_id:
                        record = self.env[model_name].sudo().browse(data.res_id)
                        if record.exists():
                            record.unlink()
                    if data:
                        data.unlink()
