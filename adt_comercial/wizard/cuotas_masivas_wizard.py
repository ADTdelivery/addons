import base64
import io
import re
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def extract_info(descripcion):
    """
    Analiza el campo descripcion y devuelve (tipo_doc, numero_doc).

    Reglas (en orden de prioridad):
      1. PLACA  →  texto tras "PLACA"  →  tipo='placa'
      2. DNI explícito  →  8 dígitos seguidos de "DNI"  →  tipo='dni'
      3. DNI al final  →  últimos 8 dígitos del string  →  tipo='dni'
      4. Resto  →  tipo='unknown', numero_doc=None
    """
    if not descripcion:
        return 'unknown', None

    text = str(descripcion).strip().upper()

    # Regla 1: PLACA
    placa_match = re.search(r'PLACA([A-Z0-9]+)', text)
    if placa_match:
        return 'placa', placa_match.group(1)

    # Regla 2: DNI explícito  (8 dígitos + "DNI")
    dni_explicit = re.search(r'(\d{8})DNI', text)
    if dni_explicit:
        return 'dni', dni_explicit.group(1)

    # Regla 3: últimos 8 dígitos al final
    trailing_digits = re.search(r'(\d{8})\D*$', text)
    if trailing_digits:
        return 'dni', trailing_digits.group(1)

    return 'unknown', None


def resolve_placa_to_dni(env, placa):
    """
    Dado una placa, busca en fleet.vehicle y devuelve el VAT del conductor.
    Retorna (tipo_doc, numero_doc).

    Si no se puede resolver devuelve ('placa', placa) para mantener el original.
    """
    try:
        vehicle = env['fleet.vehicle'].search(
            [('license_plate', '=ilike', placa)], limit=1
        )
        if not vehicle:
            _logger.warning('resolve_placa_to_dni: vehículo con placa "%s" no encontrado', placa)
            return 'placa', placa

        driver = vehicle.driver_id
        if not driver:
            _logger.warning('resolve_placa_to_dni: vehículo %s no tiene driver_id', vehicle.id)
            return 'placa', placa

        # Usar document_number (adt_clientes_extension) con fallback a vat
        doc = (getattr(driver, 'document_number', None) or driver.vat or '').strip()
        if not doc:
            _logger.warning(
                'resolve_placa_to_dni: driver %s (veh %s) no tiene document_number ni vat',
                driver.id, vehicle.id,
            )
            return 'placa', placa

        return 'dni', doc

    except Exception as e:
        _logger.exception('resolve_placa_to_dni: error inesperado para placa "%s": %s', placa, e)
        return 'placa', placa


def parse_fecha(valor):
    """Intenta parsear varios formatos de fecha y devuelve un objeto date o None."""
    if not valor:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.date() if isinstance(valor, datetime) else valor
    s = str(valor).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Wizard
# ──────────────────────────────────────────────────────────────────────────────

class CuotasMasivasWizard(models.TransientModel):
    _name = 'adt.comercial.cuotas.masivas.wizard'
    _description = 'Importación masiva de cuotas desde Excel'

    archivo_excel = fields.Binary(
        string='Archivo Excel',
        required=True,
        attachment=False,
    )
    nombre_archivo = fields.Char(string='Nombre del archivo')

    result_message = fields.Text(string='Resultado', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Procesado'),
        ('error', 'Error'),
    ], default='draft', string='Estado')

    # ──────────────────────────────────────────────────────────────────────────
    # Leer Excel
    # ──────────────────────────────────────────────────────────────────────────

    def _read_rows(self, file_data, filename):
        """
        Lee el Excel sin librerías externas:
          - .xlsx → parse manual con zipfile + xml.etree (stdlib puro)
          - .xls  → xlrd (ya incluido en Odoo 15)
          - .csv  → csv stdlib

        Devuelve lista de filas a partir de la fila 2 (omite encabezado).
        Cada fila es una lista: [fecha, descripcion, moneda, monto, numero_operacion]
        """
        fname = (filename or '').lower()

        if fname.endswith('.xlsx'):
            return self._read_xlsx_stdlib(file_data)
        elif fname.endswith('.csv'):
            return self._read_csv(file_data)
        else:
            return self._read_xls(file_data)

    # ── .xlsx con stdlib puro ──────────────────────────────────────────────────

    def _read_xlsx_stdlib(self, file_data):
        """
        Parsea un .xlsx usando únicamente zipfile + xml.etree (Python stdlib).
        Un .xlsx es un ZIP que contiene:
          - xl/sharedStrings.xml  → tabla de strings compartidos
          - xl/worksheets/sheet1.xml → celdas
        """
        NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

        try:
            zf = zipfile.ZipFile(io.BytesIO(file_data))
        except zipfile.BadZipFile:
            raise UserError(_('El archivo no es un .xlsx válido (no es un ZIP).'))

        # 1) Shared strings
        shared_strings = []
        if 'xl/sharedStrings.xml' in zf.namelist():
            ss_tree = ET.parse(zf.open('xl/sharedStrings.xml'))
            for si in ss_tree.getroot().findall('.//{%s}si' % NS):
                parts = si.findall('.//{%s}t' % NS)
                shared_strings.append(''.join(p.text or '' for p in parts))

        # 2) Primera hoja
        sheet_name = None
        for name in zf.namelist():
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                sheet_name = name
                break
        if not sheet_name:
            raise UserError(_('No se encontró ninguna hoja en el archivo .xlsx'))

        sheet_tree = ET.parse(zf.open(sheet_name))
        root = sheet_tree.getroot()

        rows_raw = []
        for row_el in root.findall('.//{%s}row' % NS):
            row_idx = int(row_el.attrib.get('r', 0))
            if row_idx < 2:          # saltar encabezado
                continue

            cells = {}
            for cell in row_el.findall('{%s}c' % NS):
                col_ref = re.sub(r'\d', '', cell.attrib.get('r', ''))
                col_num = self._col_letter_to_index(col_ref)
                t = cell.attrib.get('t', '')
                v_el = cell.find('{%s}v' % NS)
                raw_val = v_el.text if v_el is not None else None

                if raw_val is None:
                    cells[col_num] = None
                elif t == 's':
                    # shared string
                    cells[col_num] = shared_strings[int(raw_val)]
                elif t == 'b':
                    cells[col_num] = raw_val == '1'
                else:
                    # número o fecha (Excel guarda fechas como número de días desde 1900-01-01)
                    cells[col_num] = raw_val

            if not cells:
                continue

            max_col = max(cells.keys())
            row = [cells.get(i) for i in range(max_col + 1)]
            rows_raw.append(row)

        zf.close()

        # Convertir números de fecha Excel a objetos date en col 0
        result = []
        for row in rows_raw:
            if row:
                row[0] = self._maybe_excel_date(row[0])
            result.append(row)
        return result

    @staticmethod
    def _col_letter_to_index(letters):
        """Convierte 'A'→0, 'B'→1, 'Z'→25, 'AA'→26, etc."""
        idx = 0
        for ch in letters.upper():
            idx = idx * 26 + (ord(ch) - ord('A') + 1)
        return idx - 1

    @staticmethod
    def _maybe_excel_date(value):
        """
        Si value es un string numérico que representa una fecha Excel
        (número de días desde 1899-12-30), lo convierte a date.
        Si no, lo devuelve tal cual.
        """
        if value is None:
            return None
        try:
            n = float(value)
            # Excel epoch: 1899-12-30
            if 1 < n < 100000:
                return date(1899, 12, 30) + timedelta(days=int(n))
        except (ValueError, TypeError):
            pass
        return value

    # ── .xls con xlrd (incluido en Odoo 15) ──────────────────────────────────

    def _read_xls(self, file_data):
        try:
            import xlrd
        except ImportError:
            raise UserError(_(
                'No se encontró xlrd. Exporta el archivo como .xlsx o .csv e inténtalo de nuevo.'
            ))
        wb = xlrd.open_workbook(file_contents=file_data)
        ws = wb.sheet_by_index(0)
        rows = []
        for i in range(1, ws.nrows):
            row = list(ws.row_values(i))
            # xlrd devuelve fechas como float también; convertir col 0
            if row:
                try:
                    n = float(row[0])
                    if 1 < n < 100000:
                        tup = xlrd.xldate_as_tuple(n, wb.datemode)
                        row[0] = date(tup[0], tup[1], tup[2])
                except (ValueError, TypeError):
                    pass
            rows.append(row)
        return rows

    # ── .csv stdlib ───────────────────────────────────────────────────────────

    def _read_csv(self, file_data):
        import csv
        text = file_data.decode('utf-8-sig', errors='replace')
        reader = csv.reader(io.StringIO(text))
        rows = []
        for i, row in enumerate(reader):
            if i == 0:
                continue  # encabezado
            rows.append(row)
        return rows

    # ──────────────────────────────────────────────────────────────────────────
    # Buscar cuota a pagar
    # ──────────────────────────────────────────────────────────────────────────

    def _find_cuota(self, dni, fecha_pago):
        """
        Busca la cuota MÁS ANTIGUA pendiente/retrasada para el partner con DNI=dni.

        La fecha del Excel representa la FECHA DE PAGO, no un criterio de búsqueda.
        Siempre se paga la cuota más antigua (menor fecha_cronograma) que esté
        en estado pendiente, retrasado o a_cuenta — de forma consecutiva.
        """
        # Buscar por document_number (adt_clientes_extension) con fallback a vat
        partners = self.env['res.partner'].search([('document_number', '=', dni)])
        if not partners:
            partners = self.env['res.partner'].search([('vat', '=', dni)])
        if not partners:
            return None, 'No se encontró cliente con DNI "%s"' % dni

        cuentas = self.env['adt.comercial.cuentas'].search([
            ('partner_id', 'in', partners.ids),
            ('state', 'in', ('en_curso', 'aprobado')),
        ])
        if not cuentas:
            return None, 'No hay cuentas activas para DNI "%s"' % dni

        # Cuota más antigua por jerarquía (padre primero, luego hijos, luego siguiente padre)
        cuota = self.env['adt.comercial.cuotas'].search([
            ('cuenta_id', 'in', cuentas.ids),
            ('state', 'in', ('retrasado', 'pendiente', 'a_cuenta')),
        ], order='parent_sort_id asc, id asc', limit=1)

        if not cuota:
            return None, 'No hay cuotas pendientes para DNI "%s"' % dni

        return cuota, None

    # ──────────────────────────────────────────────────────────────────────────
    # Calcular mora (misma lógica que ADTComercialRegisterPayment._compute_mora)
    # ──────────────────────────────────────────────────────────────────────────

    def _calcular_mora(self, cuota, fecha_pago, company_id):
        """
        Calcula mora y días de mora para una cuota dado la fecha de pago.
        Retorna (mora, mora_dias).
        """
        if not (fecha_pago and cuota.fecha_cronograma):
            return 0.0, 0

        diff_days = (fecha_pago - cuota.fecha_cronograma).days
        if diff_days <= 0:
            return 0.0, 0

        default_factor = float(
            self.env['ir.config_parameter'].sudo()
                .get_param('adt_comercial.mora_factor', 2)
        )

        factors = self.env['adt.cobranza.config.factor'].sudo().search(
            [('company_id', '=', company_id)],
            order='id asc',
            limit=2,
        )

        # Contar cuotas de la cuenta que ya tienen mora registrada
        previous_mora_count = len(
            cuota.cuenta_id.cuota_ids.filtered(lambda c: c.mora_total > 0.0)
        )

        if not factors:
            factor = default_factor
        else:
            index = min(previous_mora_count, len(factors) - 1)
            factor = float(factors[index].factor_mora)

        mora = round(diff_days * factor, 2)
        return mora, diff_days

    # ──────────────────────────────────────────────────────────────────────────
    # Registrar pago en la cuota
    # ──────────────────────────────────────────────────────────────────────────

    def _registrar_pago(self, cuota_inicial, monto, fecha_pago, numero_operacion):
        """
        Registra el pago en cascada:
          1. Paga la cuota más antigua con el monto disponible.
          2. Si el monto cubre la cuota completa y sobra excedente,
             continúa con la siguiente cuota más antigua.
          3. Si el monto no alcanza para cubrir la cuota completa,
             se paga lo que hay y el restante se crea como subcuota.
          4. Un único número de operación cubre todas las cuotas pagadas.
          5. La mora se calcula automáticamente por cada cuota según su
             fecha_cronograma vs fecha_pago.
        """
        # Verificar duplicado de número de operación
        existing = self.env['account.payment'].search(
            [('ref', '=', numero_operacion)], limit=1
        )
        if existing:
            raise UserError(
                _('Número de operación "%s" ya registrado en la cuenta "%s"') % (
                    numero_operacion,
                    existing.cuota_id.cuenta_id.display_name if existing.cuota_id else '?',
                )
            )

        # Obtener journal por defecto
        journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', cuota_inicial.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('No se encontró un diario de banco/caja para registrar el pago.'))

        cuenta = cuota_inicial.cuenta_id
        company_id = cuota_inicial.company_id.id
        excedente = monto
        cuotas_pagadas = []

        # Obtener todas las cuotas pendientes ordenadas por jerarquía:
        # parent_sort_id agrupa padre e hijos juntos, id mantiene el orden de creación
        # Esto garantiza: Cuota 7 → Cuota 7-1 → Cuota 8 → Cuota 8-1 → ...
        cuotas_pendientes = self.env['adt.comercial.cuotas'].search([
            ('cuenta_id', '=', cuenta.id),
            ('state', 'in', ('retrasado', 'pendiente', 'a_cuenta')),
        ], order='parent_sort_id asc, id asc')

        for cuota in cuotas_pendientes:
            if excedente <= 0:
                break

            saldo_cuota = cuota.saldo or 0.0
            if saldo_cuota <= 0:
                continue

            # Calcular mora automáticamente para esta cuota
            mora, mora_dias = self._calcular_mora(cuota, fecha_pago, company_id)

            if excedente >= saldo_cuota:
                # ── Pago completo de esta cuota ──
                monto_pago = saldo_cuota
                excedente = round(excedente - saldo_cuota, 2)

                payment = self.env['account.payment'].create({
                    'payment_type': 'inbound',
                    'journal_id': journal.id,
                    'cuota_id': cuota.id,
                    'ref': numero_operacion,
                    'amount': monto_pago,
                    'date': fecha_pago or date.today(),
                    'partner_id': cuenta.partner_id.id,
                    'mora': mora,
                    'mora_dias': mora_dias,
                    'mora_state': 'pending',
                })
                payment.action_post()
                cuota.write({'state': 'pagado'})
                cuotas_pagadas.append(
                    '%s%s' % (cuota.name, ' [mora: %.2f]' % mora if mora > 0 else '')
                )

            else:
                # ── Pago parcial: excedente < saldo_cuota ──
                monto_pago = excedente
                excedente = 0.0

                payment = self.env['account.payment'].create({
                    'payment_type': 'inbound',
                    'journal_id': journal.id,
                    'cuota_id': cuota.id,
                    'ref': numero_operacion,
                    'amount': monto_pago,
                    'date': fecha_pago or date.today(),
                    'partner_id': cuenta.partner_id.id,
                    'mora': mora,
                    'mora_dias': mora_dias,
                    'mora_state': 'pending',
                })
                payment.action_post()

                # Crear subcuota con el restante
                restante = round(saldo_cuota - monto_pago, 2)
                cuota.write({'monto': monto_pago})

                parent = cuota.parent_id or cuota
                num_sub = len(parent.child_ids) + 1
                self.env['adt.comercial.cuotas'].create({
                    'name': '%s-%d' % (parent.name, num_sub),
                    'cuenta_id': cuenta.id,
                    'monto': restante,
                    'fecha_cronograma': fecha_pago or date.today(),
                    'periodicidad': cuota.periodicidad,
                    'parent_id': parent.id,
                    'type': 'cuota',
                })
                cuotas_pagadas.append(
                    '%s (parcial%s)' % (cuota.name, ', mora: %.2f' % mora if mora > 0 else '')
                )

        return cuotas_pagadas, excedente

    # ──────────────────────────────────────────────────────────────────────────
    # Acción principal
    # ──────────────────────────────────────────────────────────────────────────

    def action_importar(self):
        """
        Procesa el Excel bancario con formato:
          Fecha | Descripcion | Moneda | Monto | Numero de Operacion
        """
        self.ensure_one()
        if not self.archivo_excel:
            raise UserError(_('Por favor, seleccione un archivo Excel antes de importar.'))

        file_data = base64.b64decode(self.archivo_excel)
        filename = (self.nombre_archivo or '').lower()

        try:
            rows = self._read_rows(file_data, filename)
        except Exception as e:
            self.state = 'error'
            self.result_message = _('Error al leer el archivo: %s') % str(e)
            return self._reopen()

        procesadas = 0
        omitidas = 0
        errores = []
        detalles = []

        for idx, row in enumerate(rows, start=2):
            try:
                if not row or not any(row):
                    continue

                # ── Columnas: Fecha | Descripcion | Moneda | Monto | Numero Op ──
                fecha_raw   = row[0] if len(row) > 0 else None
                descripcion = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                # moneda       = row[2]  (no se usa en la lógica)
                monto_raw   = row[3] if len(row) > 3 else None
                num_op      = str(row[4]).strip() if len(row) > 4 and row[4] else ''

                # Parsear fecha y monto
                fecha_pago = parse_fecha(fecha_raw)
                try:
                    monto = float(str(monto_raw).replace(',', '.')) if monto_raw else 0.0
                except (ValueError, TypeError):
                    monto = 0.0

                if not descripcion:
                    omitidas += 1
                    continue
                if monto <= 0:
                    errores.append(_('Fila %d: monto inválido (%s), se omite.') % (idx, monto_raw))
                    continue

                # ── Extracción ──
                tipo_doc, numero_doc = extract_info(descripcion)

                if tipo_doc == 'placa':
                    tipo_doc, numero_doc = resolve_placa_to_dni(self.env, numero_doc)

                # Solo procesar filas que tengan DNI o PLACA resoluble
                if tipo_doc == 'unknown' or not numero_doc:
                    omitidas += 1
                    continue

                # Si después de resolver la placa sigue siendo 'placa' (no se encontró DNI)
                if tipo_doc == 'placa':
                    omitidas += 1
                    continue

                # ── Buscar cuota ──
                cuota, err_msg = self._find_cuota(numero_doc, fecha_pago)
                if err_msg:
                    errores.append(_('Fila %d [DNI %s]: %s') % (idx, numero_doc, err_msg))
                    continue

                # ── Registrar pago en cascada ──
                cuotas_pagadas, excedente = self._registrar_pago(cuota, monto, fecha_pago, num_op)

                procesadas += 1
                detalle_cuotas = ', '.join(cuotas_pagadas) if cuotas_pagadas else '—'
                excedente_txt = ' | Excedente sin aplicar: %.2f' % excedente if excedente > 0 else ''
                detalles.append(
                    '  ✓ Fila %d | DNI %s | Cuotas: [%s] | Monto %.2f | Op %s%s' % (
                        idx, numero_doc, detalle_cuotas, monto, num_op, excedente_txt
                    )
                )

            except Exception as e:
                errores.append(_('Fila %d: Error — %s') % (idx, str(e)))
                _logger.exception('CuotasMasivas: error en fila %d', idx)

        # ── Resultado ──
        lines = ['✅ Pagos registrados: %d' % procesadas]
        if omitidas:
            lines.append('⏭ Filas sin DNI/placa reconocible omitidas: %d' % omitidas)
        if detalles:
            lines.append('\nDetalle:')
            lines.extend(detalles)
        if errores:
            lines.append('\n⚠️ Errores (%d):' % len(errores))
            lines.extend(errores)

        self.result_message = '\n'.join(lines)
        self.state = 'done' if procesadas > 0 and not errores else ('error' if errores else 'done')
        return self._reopen()

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers de navegación
    # ──────────────────────────────────────────────────────────────────────────

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset(self):
        """Reinicia el wizard para importar otro archivo."""
        self.ensure_one()
        self.write({
            'archivo_excel': False,
            'nombre_archivo': False,
            'result_message': False,
            'state': 'draft',
        })
        return self._reopen()
