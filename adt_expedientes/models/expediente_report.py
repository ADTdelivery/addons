from odoo import api, models


class ReportAdtExpedientePdf(models.AbstractModel):
    """Bloquea el PDF de expedientes cargados en un solo archivo (también desde el menú Imprimir)."""
    _name = 'report.adt_expedientes.report_adt_expediente_pdf'
    _description = 'PDF del expediente'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['adt.expediente'].browse(docids)
        docs._check_pdf_generable()
        return {'doc_ids': docids, 'doc_model': 'adt.expediente', 'docs': docs, 'data': data}
