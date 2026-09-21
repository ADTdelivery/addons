from odoo import fields, models


class AdtComercialFinancieraReporte(models.Model):
    """Un menú del Reporte Financiera por cada financiera (igual que en Cuentas)."""
    _inherit = "adt.comercial.financiera"

    reporte_menu_id = fields.Many2one("ir.ui.menu", string="Menu de reporte", readonly=True, copy=False)
    reporte_action_id = fields.Many2one(
        "ir.actions.act_window", string="Accion de reporte", readonly=True, copy=False)

    def _sync_cuentas_menu(self):
        res = super()._sync_cuentas_menu()
        self._sync_reporte_menu()
        return res

    def _sync_reporte_menu(self):
        parent_menu = self.env.ref(
            "adt_comercial.adt_comercial_menu_reporte_financiera", raise_if_not_found=False)
        vistas = [
            ("tree", "adt_comercial.adt_comercial_cuentas_reporte_financiera_tree"),
            ("pivot", "adt_comercial.adt_comercial_cuentas_reporte_financiera_pivot"),
            ("graph", "adt_comercial.adt_comercial_cuentas_reporte_financiera_graph"),
            ("form", "adt_comercial.adt_comercial_cuentas_form"),
        ]
        search_view = self.env.ref(
            "adt_comercial.adt_comercial_cuentas_reporte_financiera_search", raise_if_not_found=False)
        grupo = self.env.ref(
            "adt_comercial.group_access_adt_comercial_gerencia", raise_if_not_found=False)
        if not parent_menu or not search_view:
            return

        for rec in self:
            action_vals = {
                "name": "Reporte - %s" % rec.name,
                "res_model": "adt.comercial.cuentas",
                "view_mode": "tree,pivot,graph,form",
                "domain": str([("tipo_financiera_id", "=", rec.id), ("fin_monto_total", ">", 0)]),
                "search_view_id": search_view.id,
            }
            action = rec.reporte_action_id.sudo()
            if action:
                action.write(action_vals)
            else:
                action_vals["view_ids"] = [
                    (0, 0, {"sequence": i, "view_mode": modo, "view_id": self.env.ref(xmlid).id})
                    for i, (modo, xmlid) in enumerate(vistas, start=1)]
                action = self.env["ir.actions.act_window"].sudo().create(action_vals)

            menu_vals = {
                "name": rec.name,
                "parent_id": parent_menu.id,
                "action": "ir.actions.act_window,%s" % action.id,
                "sequence": 20,
                "active": rec.active,
                "groups_id": [(6, 0, grupo.ids)] if grupo else False,
            }
            menu = rec.reporte_menu_id.sudo()
            if menu:
                menu.write(menu_vals)
            else:
                menu = self.env["ir.ui.menu"].sudo().create(menu_vals)

            rec.sudo().write({"reporte_menu_id": menu.id, "reporte_action_id": action.id})

    def unlink(self):
        actions = self.mapped("reporte_action_id").sudo()
        menus = self.mapped("reporte_menu_id").sudo()
        res = super().unlink()
        menus.unlink()
        actions.unlink()
        return res
