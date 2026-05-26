# -*- coding: utf-8 -*-
from odoo import models, api


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _build_wkhtmltopdf_args(self, paperformat_id, landscape,
                                 specific_paperformat_args=None,
                                 set_viewport_size=False):
        command_args = super()._build_wkhtmltopdf_args(
            paperformat_id, landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size,
        )
        if '--encoding' not in command_args:
            command_args.extend(['--encoding', 'utf-8'])
        return command_args
