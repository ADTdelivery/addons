# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools

import logging

from .adt_captura_record import SOURCE_TYPES

_logger = logging.getLogger(__name__)

# Filtro de la lista de posibles capturas (Ajustes > Capturas). Las cuotas vencidas del
# cronograma solo ponen la cuenta en captura si superan ambos límites; las papeletas SAT
# pendientes entran siempre. Parámetro ausente o inválido = 0 (sin límite).
PARAM_DIAS_MORA = 'adt_captura.cronograma_dias_mora_mayor_a'
PARAM_CUOTAS_VENCIDAS = 'adt_captura.cronograma_cuotas_vencidas_mayor_a'


class ADTCapturaMora(models.Model):
    """Vista SQL para identificar clientes en mora que requieren captura"""
    _name = 'adt.captura.mora'
    _description = 'Clientes en Mora - Para Captura'
    _auto = False
    _rec_name = 'partner_id'
    _order = 'dias_mora desc, fecha_cronograma asc'

    # Datos principales
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string='Cuenta', readonly=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo', readonly=True)
    reference_no = fields.Char(string='N° Cuenta', readonly=True)

    # Información de mora
    dias_mora = fields.Integer(string='Días de Mora', readonly=True)
    tipo_cartera = fields.Selection([
        ('quincena', 'Qorilazo'),
        ('mensual', 'Los Andes'),
    ], string='Tipo de Cartera', readonly=True)

    # Información de cuotas
    fecha_cronograma = fields.Date(string='Fecha Vencimiento', readonly=True)
    monto_vencido = fields.Float(string='Monto Vencido', readonly=True)
    numero_cuotas_vencidas = fields.Integer(string='# Cuotas Vencidas', readonly=True)

    # Papeletas del SAT Lima pendientes de pago (adt.papeleta.sat)
    papeletas_sat = fields.Integer(string='Papeletas SAT pendientes', readonly=True)
    deuda_sat = fields.Float(string='Deuda SAT', readonly=True)
    fecha_papeleta_sat = fields.Date(string='Papeleta SAT más antigua', readonly=True)
    papeleta_sat_id = fields.Many2one('adt.papeleta.sat', string='Papeleta SAT', readonly=True)

    # Información GPS
    gps_chip = fields.Char(string='GPS Chip', readonly=True)
    gps_activo = fields.Boolean(string='GPS Activo', readonly=True)

    # Contacto
    phone = fields.Char(string='Teléfono', readonly=True)
    mobile = fields.Char(string='Celular', readonly=True)
    vat = fields.Char(string='DNI/CE', readonly=True)

    # Asesor
    user_id = fields.Many2one('res.users', string='Asesor', readonly=True)

    # Estado captura
    captura_existente = fields.Boolean(string='Tiene Captura', readonly=True)

    # Mantenimiento TVS
    en_mantenimiento_tvs = fields.Boolean(string='En Mantenimiento TVS', readonly=True)
    dias_en_mantenimiento_tvs = fields.Integer(string='Días en Mantenimiento TVS', readonly=True)

    # Prioridad de captura (editable en cuenta)
    captura_prioridad = fields.Selection([
        ('', ''),
        ('normal', 'Normal'),
        ('urgente', 'Urgente')
    ], string='Prioridad de Captura', readonly=False, related='cuenta_id.captura_prioridad', store=False)

    # Origen: cuotas vencidas del cronograma, papeletas SAT pendientes o ambos
    source_type = fields.Selection(SOURCE_TYPES, string='Origen', readonly=True)

    @api.model
    def _filtro_captura(self):
        """Límites vigentes del filtro, leídos igual que en la vista SQL."""
        icp = self.env['ir.config_parameter'].sudo()
        res = {}
        for clave, param in (('dias_mora_mayor_a', PARAM_DIAS_MORA),
                             ('cuotas_vencidas_mayor_a', PARAM_CUOTAS_VENCIDAS)):
            valor = (icp.get_param(param) or '').strip()
            res[clave] = int(valor) if valor.isdigit() else 0
        return res

    def init(self):
        """Posibles capturas: cuentas con cuotas vencidas del cronograma que superan el filtro
        configurado (días de mora y cantidad de cuotas, ver _filtro_captura) o con papeletas
        del SAT Lima pendientes de pago. Una papeleta SAT solo cuenta para la cuenta vigente
        (aprobada o en curso) del vehículo y si la infracción es posterior al desembolso,
        para no cargarle al cliente las de un titular anterior. El filtro se lee de
        ir_config_parameter en cada consulta: cambiarlo no requiere actualizar el módulo."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW {table} AS (
                WITH cfg AS (
                    SELECT
                        COALESCE((SELECT CASE WHEN TRIM(p.value) ~ '^[0-9]+$' THEN TRIM(p.value)::int END
                                  FROM ir_config_parameter p WHERE p.key = '{param_dias}'), 0) AS dias_mora_mayor_a,
                        COALESCE((SELECT CASE WHEN TRIM(p.value) ~ '^[0-9]+$' THEN TRIM(p.value)::int END
                                  FROM ir_config_parameter p WHERE p.key = '{param_cuotas}'), 0) AS cuotas_vencidas_mayor_a
                ),
                cuotas AS (
                    SELECT
                        cuota.cuenta_id,
                        MIN(cuota.fecha_cronograma) AS fecha_cronograma,
                        COALESCE(SUM(cuota.saldo), 0) AS monto_vencido,
                        COUNT(cuota.id) AS numero_cuotas_vencidas
                    FROM adt_comercial_cuotas cuota
                    WHERE cuota.type = 'cuota'
                      AND cuota.state IN ('pendiente', 'retrasado')
                      AND cuota.fecha_cronograma < CURRENT_DATE
                    GROUP BY cuota.cuenta_id
                )
                SELECT
                    cuenta.id,
                    cuenta.partner_id,
                    cuenta.id AS cuenta_id,
                    cuenta.vehiculo_id AS vehicle_id,
                    cuenta.reference_no,
                    COALESCE(CURRENT_DATE - cu.fecha_cronograma, 0) AS dias_mora,
                    cuenta.periodicidad AS tipo_cartera,
                    cu.fecha_cronograma,
                    COALESCE(cu.monto_vencido, 0) AS monto_vencido,
                    COALESCE(cu.numero_cuotas_vencidas, 0) AS numero_cuotas_vencidas,

                    COALESCE(sat.n, 0) AS papeletas_sat,
                    COALESCE(sat.deuda, 0) AS deuda_sat,
                    sat.fecha AS fecha_papeleta_sat,
                    sat.primera AS papeleta_sat_id,

                    cuenta.gps_chip,
                    cuenta.gps_activo,
                    partner.phone,
                    partner.mobile,
                    partner.vat,
                    cuenta.user_id,

                    EXISTS (
                        SELECT 1 FROM adt_captura_record r
                        WHERE r.cuenta_id = cuenta.id
                          AND r.state IN ('capturado', 'disolucion_contrato')
                    ) AS captura_existente,

                    EXISTS (
                        SELECT 1 FROM adt_tvs_mantenimiento tvs
                        WHERE tvs.vehicle_id = cuenta.vehiculo_id
                          AND tvs.state = 'in_progress'
                          AND tvs.active = true
                    ) AS en_mantenimiento_tvs,
                    COALESCE((
                        SELECT tvs.days_in_taller FROM adt_tvs_mantenimiento tvs
                        WHERE tvs.vehicle_id = cuenta.vehiculo_id
                          AND tvs.state = 'in_progress'
                          AND tvs.active = true
                        ORDER BY tvs.date_inicio_revision DESC
                        LIMIT 1
                    ), 0) AS dias_en_mantenimiento_tvs,

                    CASE
                        WHEN f.cronograma_ok AND sat.n > 0 THEN 'ambos'
                        WHEN f.cronograma_ok THEN 'mora'
                        ELSE 'papeleta'
                    END AS source_type

                FROM adt_comercial_cuentas cuenta
                CROSS JOIN cfg
                LEFT JOIN cuotas cu ON cu.cuenta_id = cuenta.id
                LEFT JOIN LATERAL (
                    SELECT COALESCE(CURRENT_DATE - cu.fecha_cronograma > cfg.dias_mora_mayor_a
                                    AND cu.numero_cuotas_vencidas > cfg.cuotas_vencidas_mayor_a,
                                    false) AS cronograma_ok
                ) f ON true
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS n,
                        SUM(s.deuda) AS deuda,
                        MIN(COALESCE(s.fecha_infraccion, s.primera_vez_visto::date)) AS fecha,
                        (ARRAY_AGG(s.id ORDER BY COALESCE(s.fecha_infraccion, s.primera_vez_visto::date) ASC NULLS LAST, s.id))[1] AS primera
                    FROM adt_papeleta_sat s
                    WHERE s.vehicle_id = cuenta.vehiculo_id
                      AND s.estado_pago = 'pendiente'
                      AND cuenta.state IN ('aprobado', 'en_curso')
                      AND (cuenta.fecha_desembolso IS NULL OR s.fecha_infraccion IS NULL
                           OR s.fecha_infraccion >= cuenta.fecha_desembolso)
                ) sat ON true
                LEFT JOIN res_partner partner ON partner.id = cuenta.partner_id
                WHERE cuenta.state != 'cancelado'
                  AND (f.cronograma_ok OR sat.n > 0)
            )
        '''.format(table=self._table, param_dias=PARAM_DIAS_MORA, param_cuotas=PARAM_CUOTAS_VENCIDAS))

    def action_iniciar_captura(self):
        """Abre el formulario para registrar una nueva captura"""
        self.ensure_one()

        # Verificar si ya existe una captura activa
        captura_existente = self.env['adt.captura.record'].search([
            ('cuenta_id', '=', self.cuenta_id.id),
            ('state', '=', 'capturado')
        ], limit=1)

        if captura_existente:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Aviso',
                    'message': 'Ya existe una captura activa para esta cuenta.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        return {
            'name': 'Nueva Captura',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.captura.record',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_cuenta_id': self.cuenta_id.id,
                'default_intervention_fee': 50.0,
                'default_source_type': self.source_type,
            },
            'target': 'current',
        }

    def action_ver_detalle(self):
        """Abre el detalle de la cuenta"""
        self.ensure_one()

        return {
            'name': f'Cuenta {self.reference_no}',
            'type': 'ir.actions.act_window',
            'res_model': 'adt.comercial.cuentas',
            'view_mode': 'form',
            'res_id': self.cuenta_id.id,
        }

    def action_set_prioridad_urgente(self):
        """Set the related cuenta's prioridad to 'urgente'"""
        self.ensure_one()
        if self.cuenta_id:
            self.cuenta_id.captura_prioridad = 'urgente'

    def action_set_prioridad_normal(self):
        """Set the related cuenta's prioridad to 'normal'"""
        self.ensure_one()
        if self.cuenta_id:
            self.cuenta_id.captura_prioridad = 'normal'
