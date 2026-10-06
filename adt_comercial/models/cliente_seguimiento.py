from odoo import fields, models

CLASIFICACION_MANUAL = [
    ('apto', 'Apto para un nuevo préstamo'),
    ('evaluar', 'Evaluar antes de prestar'),
    ('no_prestar', 'No prestar'),
]
ESTADO_SEGUIMIENTO = [
    ('por_contactar', 'Por contactar'),
    ('contactado', 'Contactado'),
    ('interesado', 'Interesado'),
    ('no_interesado', 'No interesado'),
    ('nuevo_prestamo', 'Nuevo préstamo otorgado'),
]


class AdtClienteSeguimiento(models.Model):
    """Seguimiento comercial de un cliente para un futuro préstamo (uno por cliente).

    La clasificación automática (puntaje y segmento) se calcula en el Dashboard de Clientes;
    aquí se guarda lo que decide el equipo: contacto, próxima llamada y, si corresponde,
    una clasificación manual que tiene prioridad (por ejemplo, marcar a un cliente conflictivo).
    """
    _name = 'adt.cliente.seguimiento'
    _description = 'Seguimiento de clientes para nuevo préstamo'
    _inherit = ['mail.thread']
    _rec_name = 'partner_id'
    _order = 'proximo_contacto asc, id desc'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, ondelete='cascade', index=True)
    clasificacion_manual = fields.Selection(
        CLASIFICACION_MANUAL, string='Clasificación manual', tracking=True,
        help='Si se completa, reemplaza la clasificación automática del dashboard. '
             '"No prestar" siempre tiene prioridad.')
    motivo_manual = fields.Char(string='Motivo de la clasificación', tracking=True)
    estado = fields.Selection(
        ESTADO_SEGUIMIENTO, string='Estado del seguimiento', default='por_contactar', required=True, tracking=True)
    proximo_contacto = fields.Date(string='Próximo contacto', tracking=True)
    notas = fields.Text(string='Notas')
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, tracking=True)

    _sql_constraints = [
        ('partner_unico', 'unique(partner_id)', 'El cliente ya tiene un registro de seguimiento.'),
    ]
