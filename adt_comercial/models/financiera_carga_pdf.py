import base64
import logging
import threading
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.plan_pagos_parser import PlanPagosParseError, parse_pdf

_logger = logging.getLogger(__name__)

# Estados de la cuenta del cliente -> situación de su deuda con ADT.
# Igual que Flota 360: cancelado = cuenta anulada (o moto recuperada), pagado = terminó de pagar.
DEUDA_POR_ESTADO = {
    'borrador': 'activa', 'aprobado': 'activa', 'en_curso': 'activa',
    'pagado': 'cancelada',
    'cancelado': 'anulada',
}
# Si el cliente tiene varias cuentas, el plan va a la moto de la cuenta más relevante.
PRIORIDAD_DEUDA = ('activa', 'cancelada', 'anulada')

LINEAS_POR_COMMIT = 10      # el cron confirma cada 10 PDFs: un fallo no pierde lo ya cargado
SEGUNDOS_POR_CRON = 90      # por debajo de limit_time_real (120 s por defecto); luego se reprograma
LINEAS_PROCESAR_AHORA = 15  # "Procesar ahora" dentro de la petición web, sin esperar al cron
MAX_PDFS_POR_LOTE = 500


class ADTFinancieraCargaPdf(models.Model):
    """Carga masiva de PDFs "Plan de Pagos" de la financiera.

    Cada PDF se lee, se busca al cliente por el DNI del PDF, se identifica si su deuda
    (cuenta) está activa, cancelada o anulada y el plan se guarda en la moto de esa cuenta
    (campos cf_* de fleet.vehicle y su cronograma), igual que al subirlo uno por uno.
    El trabajo lo hace un cron por tandas para soportar cientos de PDFs sin timeouts.
    """
    _name = 'adt.financiera.carga.pdf'
    _description = 'Carga masiva de planes de pago de la financiera'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(string="Lote", required=True, copy=False, readonly=True,
                       default=lambda self: _('Nuevo'))
    state = fields.Selection(
        [('borrador', 'Borrador'), ('procesando', 'Procesando'), ('terminado', 'Terminado')],
        string="Estado", default='borrador', required=True, tracking=True, copy=False)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'adt_financiera_carga_pdf_attachment_rel', 'carga_id', 'attachment_id',
        string="PDFs", copy=False)
    reemplazar = fields.Boolean(
        string="Reemplazar planes ya cargados", default=True,
        help="Si la moto ya tiene un plan de pagos, se reemplaza por el del PDF. "
             "Si se desmarca, esos PDFs quedan como «Omitido».")
    linea_ids = fields.One2many('adt.financiera.carga.pdf.linea', 'carga_id', string="Resultado", copy=False)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    total = fields.Integer(compute='_compute_totales', string="PDFs")
    total_pendiente = fields.Integer(compute='_compute_totales', string="Pendientes")
    total_cargado = fields.Integer(compute='_compute_totales', string="Cargados")
    total_sin_cliente = fields.Integer(compute='_compute_totales', string="Sin cliente")
    total_revisar = fields.Integer(compute='_compute_totales', string="A revisar")
    total_omitido = fields.Integer(compute='_compute_totales', string="Omitidos")
    total_error = fields.Integer(compute='_compute_totales', string="Con error")
    total_activa = fields.Integer(compute='_compute_totales', string="Deuda activa")
    total_cancelada = fields.Integer(compute='_compute_totales', string="Deuda cancelada")
    total_anulada = fields.Integer(compute='_compute_totales', string="Deuda anulada")
    progreso = fields.Float(compute='_compute_totales', string="Avance (%)")

    @api.depends('linea_ids.state', 'linea_ids.situacion_deuda')
    def _compute_totales(self):
        Linea = self.env['adt.financiera.carga.pdf.linea']
        por_estado, por_deuda = {}, {}
        if self.ids:
            for g in Linea.read_group([('carga_id', 'in', self.ids)], ['carga_id', 'state'],
                                      ['carga_id', 'state'], lazy=False):
                por_estado[(g['carga_id'][0], g['state'])] = g['__count']
            for g in Linea.read_group([('carga_id', 'in', self.ids)], ['carga_id', 'situacion_deuda'],
                                      ['carga_id', 'situacion_deuda'], lazy=False):
                por_deuda[(g['carga_id'][0], g['situacion_deuda'])] = g['__count']
        for rec in self:
            def n(estado):
                return por_estado.get((rec.id, estado), 0)
            rec.total = sum(v for (cid, _e), v in por_estado.items() if cid == rec.id)
            rec.total_pendiente = n('pendiente')
            rec.total_cargado = n('cargado')
            rec.total_sin_cliente = n('sin_cliente')
            rec.total_revisar = n('revisar')
            rec.total_omitido = n('omitido')
            rec.total_error = n('error')
            rec.total_activa = por_deuda.get((rec.id, 'activa'), 0)
            rec.total_cancelada = por_deuda.get((rec.id, 'cancelada'), 0)
            rec.total_anulada = por_deuda.get((rec.id, 'anulada'), 0)
            rec.progreso = 100.0 * (rec.total - rec.total_pendiente) / rec.total if rec.total else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = _('Carga PDF %s') % fields.Datetime.to_string(fields.Datetime.now())
        return super().create(vals_list)

    # ------------------------------------------------------------------ acciones

    def action_procesar(self):
        """Crea una línea por PDF y deja el lote en cola para el cron."""
        for rec in self:
            pdfs = rec.attachment_ids.filtered(lambda a: (a.name or '').lower().endswith('.pdf')
                                               or a.mimetype == 'application/pdf')
            if not pdfs and not rec.linea_ids:
                raise UserError(_("Sube al menos un PDF del plan de pagos."))
            if len(pdfs) > MAX_PDFS_POR_LOTE:
                raise UserError(_("Máximo %s PDFs por lote (subiste %s).") % (MAX_PDFS_POR_LOTE, len(pdfs)))
            ya = rec.linea_ids.mapped('attachment_id')
            vistos = {a.checksum for a in ya if a.checksum}
            nuevas = []
            for att in pdfs - ya:
                repetido = att.checksum and att.checksum in vistos
                vistos.add(att.checksum)
                nuevas.append({
                    'carga_id': rec.id, 'attachment_id': att.id, 'nombre_archivo': att.name,
                    'state': 'omitido' if repetido else 'pendiente',
                    'mensaje': _("El mismo PDF está repetido en el lote.") if repetido else False,
                })
            self.env['adt.financiera.carga.pdf.linea'].create(nuevas)
            rec.state = 'procesando'
        self._disparar_cron()
        return True

    def action_procesar_ahora(self):
        """Procesa una tanda en la misma petición (útil si los crons están apagados)."""
        if any(r.state == 'borrador' for r in self):
            self.filtered(lambda r: r.state == 'borrador').action_procesar()
        self._procesar_lineas(self.linea_ids.filtered(lambda l: l.state == 'pendiente')[:LINEAS_PROCESAR_AHORA],
                              commit=False)
        self._cerrar_terminados()
        return True

    def action_reintentar(self):
        lineas = self.linea_ids.filtered(lambda l: l.state in ('error', 'sin_cliente', 'revisar'))
        if not lineas:
            raise UserError(_("No hay PDFs con error, sin cliente o por revisar."))
        lineas.write({'state': 'pendiente', 'mensaje': False})
        self.write({'state': 'procesando'})
        self._disparar_cron()
        return True

    def action_ver_lineas(self):
        self.ensure_one()
        estado = self.env.context.get('estado_linea')
        dominio = [('carga_id', '=', self.id)] + ([('state', '=', estado)] if estado else [])
        return {
            'type': 'ir.actions.act_window', 'name': self.name,
            'res_model': 'adt.financiera.carga.pdf.linea', 'view_mode': 'tree,form', 'domain': dominio,
        }

    # ------------------------------------------------------------------ cron

    def _disparar_cron(self):
        cron = self.env.ref('adt_comercial.ir_cron_carga_pdf_financiera', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_procesar(self):
        inicio = time.time()
        Linea = self.env['adt.financiera.carga.pdf.linea']
        while time.time() - inicio < SEGUNDOS_POR_CRON:
            tanda = Linea.search([('state', '=', 'pendiente'), ('carga_id.state', '=', 'procesando')],
                                 order='carga_id, id', limit=LINEAS_POR_COMMIT)
            if not tanda:
                break
            tanda.mapped('carga_id')._procesar_lineas(tanda, commit=True)
        self.search([('state', '=', 'procesando')])._cerrar_terminados()
        if Linea.search_count([('state', '=', 'pendiente'), ('carga_id.state', '=', 'procesando')]):
            self._disparar_cron()

    def _cerrar_terminados(self):
        for rec in self.filtered(lambda r: r.state == 'procesando'):
            if not rec.linea_ids.filtered(lambda l: l.state == 'pendiente'):
                rec.state = 'terminado'
                rec.message_post(body=_(
                    "Carga terminada: %(c)s cargados, %(s)s sin cliente, %(r)s por revisar, "
                    "%(o)s omitidos, %(e)s con error.") % {
                        'c': rec.total_cargado, 's': rec.total_sin_cliente, 'r': rec.total_revisar,
                        'o': rec.total_omitido, 'e': rec.total_error})

    def _procesar_lineas(self, lineas, commit):
        en_test = getattr(threading.current_thread(), 'testing', False)
        for linea in lineas:
            try:
                with self.env.cr.savepoint():
                    linea._procesar()
            except Exception as e:
                # Lo que el PDF dejó a medias se deshizo con el savepoint; la línea queda con el error.
                self.env['base'].invalidate_cache()
                _logger.exception("Carga masiva financiera: error con %s", linea.nombre_archivo)
                linea.write({'state': 'error', 'mensaje': str(e)[:500]})
        if commit and not en_test:
            self.env.cr.commit()


class ADTFinancieraCargaPdfLinea(models.Model):
    _name = 'adt.financiera.carga.pdf.linea'
    _description = 'PDF de una carga masiva de la financiera'
    _order = 'carga_id, id'
    _rec_name = 'nombre_archivo'

    carga_id = fields.Many2one('adt.financiera.carga.pdf', string="Lote", required=True,
                               ondelete='cascade', index=True)
    attachment_id = fields.Many2one('ir.attachment', string="PDF", ondelete='set null')
    nombre_archivo = fields.Char(string="Archivo")
    state = fields.Selection(
        [('pendiente', 'Pendiente'), ('cargado', 'Cargado'), ('sin_cliente', 'Sin cliente'),
         ('revisar', 'Revisar'), ('omitido', 'Omitido'), ('error', 'Error')],
        string="Resultado", default='pendiente', required=True, index=True)
    mensaje = fields.Text(string="Detalle")

    # Lo leído del PDF
    dni = fields.Char(string="DNI (PDF)")
    socio_pdf = fields.Char(string="Socio (PDF)")
    monto_credito = fields.Float(string="Monto crédito")
    cuotas_pdf = fields.Integer(string="Cuotas en el PDF")
    cf_estado = fields.Selection([('valido', 'Válido'), ('observado', 'Observado')], string="Lectura")
    confianza = fields.Float(string="Confianza (%)", digits=(16, 1))

    # Lo encontrado en ADT
    partner_id = fields.Many2one('res.partner', string="Cliente")
    cuenta_id = fields.Many2one('adt.comercial.cuentas', string="Cuenta")
    cuenta_state = fields.Selection(related='cuenta_id.state', string="Estado de la cuenta")
    vehiculo_id = fields.Many2one('fleet.vehicle', string="Moto")
    situacion_deuda = fields.Selection(
        [('activa', 'Deuda activa'), ('cancelada', 'Deuda cancelada'), ('anulada', 'Deuda anulada'),
         ('sin_deuda', 'Sin deuda')],
        string="Deuda del cliente", index=True)

    # Reasignación manual: se elige otro cliente/cuenta y el plan reemplaza al de esa moto.
    partner_manual_id = fields.Many2one('res.partner', string="Otro cliente")
    cuenta_manual_id = fields.Many2one(
        'adt.comercial.cuentas', string="Cuenta del otro cliente",
        domain="[('partner_id', '=', partner_manual_id), ('vehiculo_id', '!=', False)]")

    @api.onchange('partner_manual_id')
    def _onchange_partner_manual_id(self):
        cuenta, _situacion = self._cuenta_del_cliente(self.partner_manual_id) if self.partner_manual_id \
            else (self.env['adt.comercial.cuentas'], False)
        self.cuenta_manual_id = cuenta

    def action_cargar_otro_cliente(self):
        """Carga el PDF en la moto de la cuenta elegida, reemplazando el plan que tenga."""
        for rec in self:
            cuenta = rec.cuenta_manual_id
            if not cuenta and rec.partner_manual_id:
                cuenta, _situacion = rec._cuenta_del_cliente(rec.partner_manual_id)
            if not cuenta:
                raise UserError(_("Elige el cliente y la cuenta (con moto) donde cargar «%s».")
                                % rec.nombre_archivo)
            anterior = rec.vehiculo_id if rec.state == 'cargado' else self.env['fleet.vehicle']
            rec._procesar(cuenta=cuenta)
            # El PDF estaba cargado en otra moto (cliente equivocado): esa moto se queda sin plan.
            if anterior and anterior != rec.vehiculo_id and anterior.cf_pdf_nombre == rec.nombre_archivo:
                anterior.write({'cf_pdf': False})
                rec.mensaje = '%s\n%s' % (rec.mensaje, _("Se quitó el plan de la moto anterior %s.")
                                          % anterior.display_name)
            rec.write({'partner_manual_id': False, 'cuenta_manual_id': False})
        self.mapped('carga_id')._cerrar_terminados()
        return True

    def _procesar(self, cuenta=None):
        """Lee el PDF, identifica al cliente y su deuda, y guarda el plan en la moto.

        Con `cuenta` (elegida a mano) no se busca por DNI: el plan va a la moto de esa cuenta
        y reemplaza el que tenga, sin las restricciones de la carga automática."""
        self.ensure_one()
        att = self.attachment_id
        if not att:
            return self.write({'state': 'error', 'mensaje': _("El PDF ya no existe.")})
        pdf = att.raw or (att.datas and base64.b64decode(att.datas))
        try:
            _texto, data = parse_pdf(pdf)
        except PlanPagosParseError as e:
            return self.write({'state': 'error', 'mensaje': _("No tiene el formato de Plan de Pagos: %s") % e})

        cab, pie = data['cabecera'], data['pie']
        dni = (pie.get('dni') or '').strip()
        vals = {
            'dni': dni, 'socio_pdf': cab.get('socio'), 'monto_credito': cab.get('monto_credito'),
            'cuotas_pdf': len(data['cuotas']), 'cf_estado': data['validacion']['estado'],
            'confianza': data['validacion']['confianza'],
            'partner_id': False, 'cuenta_id': False, 'vehiculo_id': False, 'situacion_deuda': False,
        }
        manual = bool(cuenta)
        if manual:
            situacion = DEUDA_POR_ESTADO.get(cuenta.state, 'activa')
        else:
            if not dni:
                return self.write(dict(vals, state='sin_cliente', mensaje=_("El PDF no trae DNI.")))
            partners = self._buscar_clientes(dni)
            if not partners:
                return self.write(dict(vals, state='sin_cliente',
                                       mensaje=_("No existe un cliente con DNI %s.") % dni))
            vals['partner_id'] = partners[:1].id
            cuenta, situacion = self._cuenta_del_cliente(partners)
            if not cuenta:
                return self.write(dict(vals, state='sin_cliente', situacion_deuda='sin_deuda', mensaje=_(
                    "El cliente %s no tiene cuentas (deuda) con moto.") % partners[:1].name))
        vals.update(partner_id=cuenta.partner_id.id, cuenta_id=cuenta.id, situacion_deuda=situacion)
        vehiculo = cuenta.vehiculo_id
        vals['vehiculo_id'] = vehiculo.id
        etiqueta = dict(self._fields['situacion_deuda'].selection)[situacion]

        mismo_lote = self.search([('carga_id', '=', self.carga_id.id), ('id', '!=', self.id),
                                  ('vehiculo_id', '=', vehiculo.id), ('state', '=', 'cargado')])
        if manual:
            # Lo elegido a mano manda: el otro PDF del lote que había llegado a esta moto queda reemplazado.
            mismo_lote.write({'state': 'omitido', 'mensaje': _(
                "Reemplazado por %s (asignado a mano).") % self.nombre_archivo})
        else:
            # Una cuenta cancelada/anulada puede ser de una moto que ya se entregó a otro cliente.
            if situacion != 'activa':
                otra = vehiculo.cuenta_ids.filtered(
                    lambda c: DEUDA_POR_ESTADO.get(c.state) == 'activa' and c.partner_id not in partners)
                if otra:
                    return self.write(dict(vals, state='revisar', mensaje=_(
                        "La deuda del cliente está %s, pero la moto %s ahora tiene la cuenta activa %s de %s. "
                        "No se cargó: usa «Cargar en otro cliente» para decidir.") % (
                            etiqueta.lower(), vehiculo.display_name, otra[:1].reference_no or otra[:1].id,
                            otra[:1].partner_id.name)))
            if mismo_lote:
                return self.write(dict(vals, state='omitido', mensaje=_(
                    "La moto ya recibió otro plan en este lote (%s).") % mismo_lote[:1].nombre_archivo))
            if vehiculo.cf_pdf and not self.carga_id.reemplazar:
                return self.write(dict(vals, state='omitido', mensaje=_(
                    "La moto ya tenía un plan de pagos (%s).") % (vehiculo.cf_pdf_nombre or '')))

        reemplaza = vehiculo.cf_pdf_nombre
        # Se guarda el PDF sin volver a leerlo (ya se leyó) y se aplican los datos al modelo de financiera.
        vehiculo.with_context(cf_sin_leer=True).write({
            'cf_pdf': base64.b64encode(pdf), 'cf_pdf_nombre': (self.nombre_archivo or '')[:200]})
        vehiculo._cf_validar_cliente(data)
        vehiculo._cf_aplicar(data)
        vals['cf_estado'] = data['validacion']['estado']
        vals['confianza'] = data['validacion']['confianza']
        mensaje = _("Plan cargado en %s (cuenta %s, deuda %s)%s.") % (
            vehiculo.display_name, cuenta.reference_no or cuenta.id, etiqueta.lower(),
            _(", asignado a mano") if manual else '')
        if reemplaza:
            mensaje += ' ' + _("Reemplazó al plan anterior (%s).") % reemplaza
        return self.write(dict(vals, state='cargado', mensaje=mensaje))

    @api.model
    def _buscar_clientes(self, dni):
        Partner = self.env['res.partner'].with_context(active_test=False)
        return Partner.search([('vat', '=', dni)]) or Partner.search([('vat', 'ilike', dni)])

    @api.model
    def _cuenta_del_cliente(self, partners):
        """(cuenta, situación): la cuenta con moto más relevante del cliente — activa, luego
        cancelada (pagada), luego anulada; dentro de cada grupo la más reciente."""
        cuentas = self.env['adt.comercial.cuentas'].search(
            [('partner_id', 'in', partners.ids), ('vehiculo_id', '!=', False)],
            order='fecha_desembolso desc, id desc')
        for situacion in PRIORIDAD_DEUDA:
            cuenta = cuentas.filtered(lambda c: DEUDA_POR_ESTADO.get(c.state) == situacion)[:1]
            if cuenta:
                return cuenta, situacion
        return self.env['adt.comercial.cuentas'], False

    def action_abrir_moto(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'fleet.vehicle',
                'res_id': self.vehiculo_id.id, 'view_mode': 'form'}
