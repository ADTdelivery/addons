from odoo import _, api, fields, models

import logging
_logger = logging.getLogger(__name__)


class ADTFleetVehicleV2(models.Model):
    _inherit = 'fleet.vehicle'

    cuenta_v2_ids = fields.One2many(
        'adt.comercial.cuentas.v2', 'vehiculo_id', string="Cuentas")

    # disponible = fields.Boolean(string='Disponible', compute="_compute_vehiculo_disponible", store=True)
    disponible2 = fields.Boolean(string='Disponible', default=True)

    # @api.depends('cuenta_ids')
    # def _compute_vehiculo_disponible(self):
    #     for record in self:
    #         if (len(record.cuenta_ids) == 0):
    #             _logger.info('ENTRA EN IF')
    #             record.disponible = True
    #         else:
    #             _logger.info('ENTRA EN ELSE')
    #             last_record = record.cuenta_ids.sorted(
    #                 key=lambda x: x.create_date, reverse=True)[0]
    #             _logger.info({'LAST REECORD': last_record})
    #             if (last_record.recuperado and last_record.state != 'pagado'):
    #                 _logger.info('ENTRA EN ELSE IF')
    #                 record.disponible = True
    #             elif last_record.state in ('pagado', 'aprobado', 'en_curso'):
    #                 _logger.info('ENTRA EN ELSE ELIF')
    #                 record.disponible = False
    #             else:
    #                 _logger.info('ENTRA EN ELSE ELSE')
    #                 record.disponible = False
