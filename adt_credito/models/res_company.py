from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    credito_mora_tipo = fields.Selection(
        [('fijo', 'Monto fijo por día'),
         ('porcentual', 'Porcentaje diario sobre la cuota')],
        string="Tipo de mora",
        default='fijo',
    )
    credito_mora_valor = fields.Float(
        string="Valor de mora",
        default=0.0,
        help="Monto fijo cobrado por cada día de atraso, o porcentaje diario sobre el "
             "monto de la cuota, según el tipo elegido.",
    )
    credito_mora_dias_gracia = fields.Integer(
        string="Días de gracia",
        default=0,
        help="Días de atraso tolerados antes de empezar a calcular mora.",
    )
    credito_mora_tope = fields.Float(
        string="Tope máximo de mora por cuota",
        default=0.0,
        help="0 = sin tope.",
    )
