from odoo import _, api, fields, models


class AdtComercialFinanciera(models.Model):
    _name = "adt.comercial.financiera"
    _description = "Tipo de Financiera"
    _order = "name"

    name = fields.Char(string="Nombre", required=True, tracking=True)
    code = fields.Char(string="Codigo", required=True, copy=False)
    active = fields.Boolean(default=True)
    menu_id = fields.Many2one("ir.ui.menu", string="Menu", readonly=True, copy=False)
    action_id = fields.Many2one("ir.actions.act_window", string="Accion", readonly=True, copy=False)

    _sql_constraints = [
        ("adt_comercial_financiera_code_uniq", "unique(code)", "El codigo de financiera ya existe."),
        ("adt_comercial_financiera_name_uniq", "unique(name)", "El nombre de financiera ya existe."),
    ]

    def _get_cuentas_parent_menu(self):
        return self.env.ref("adt_comercial.adt_comercial_menu_cuentas", raise_if_not_found=False)

    def _sync_cuentas_menu(self):
        parent_menu = self._get_cuentas_parent_menu()
        if not parent_menu:
            return

        for rec in self:
            action_vals = {
                "name": _("Cuentas - %s") % rec.name,
                "res_model": "adt.comercial.cuentas",
                "view_mode": "tree,form",
                "domain": [("tipo_financiera_id", "=", rec.id)],
                "context": {"search_default_tipo_financiera_id": rec.id},
            }
            action = rec.action_id.sudo()
            if action:
                action.write(action_vals)
            else:
                action = self.env["ir.actions.act_window"].sudo().create(action_vals)

            menu_vals = {
                "name": rec.name,
                "parent_id": parent_menu.id,
                "action": "ir.actions.act_window,%s" % action.id,
                "sequence": 20,
                "active": rec.active,
            }
            menu = rec.menu_id.sudo()
            if menu:
                menu.write(menu_vals)
            else:
                menu = self.env["ir.ui.menu"].sudo().create(menu_vals)

            rec.sudo().write({"menu_id": menu.id, "action_id": action.id})

    @api.model
    def _sync_all_cuentas_menus(self):
        self.sudo().search([])._sync_cuentas_menu()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_cuentas_menu()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("name", "active")):
            self._sync_cuentas_menu()
        return res

    def unlink(self):
        actions = self.mapped("action_id").sudo()
        menus = self.mapped("menu_id").sudo()
        res = super().unlink()
        menus.unlink()
        actions.unlink()
        return res

