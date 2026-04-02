import base64
import io
import re
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# ──────────────────────────────────────────────────────────────────────────────
# Excel writer (stdlib puro — no requiere openpyxl)
# ──────────────────────────────────────────────────────────────────────────────

def _build_xlsx_bytes(headers, rows):
    """
    Genera un archivo .xlsx mínimo usando zipfile + xml.etree (stdlib puro).
    headers: lista de strings (cabecera)
    rows:    lista de listas (filas de datos)
    Devuelve bytes del .xlsx.
    """
    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    # Compartir strings para reducir tamaño
    shared = []
    shared_map = {}

    def _si(text):
        key = str(text)
        if key not in shared_map:
            shared_map[key] = len(shared)
            shared.append(key)
        return shared_map[key]

    # Construir filas XML
    all_rows = [headers] + [list(r) for r in rows]
    row_xmls = []
    for r_idx, row in enumerate(all_rows, start=1):
        cells = []
        for c_idx, val in enumerate(row):
            col_letter = chr(ord('A') + c_idx)
            ref = '%s%d' % (col_letter, r_idx)
            if val is None:
                cells.append('<c r="%s" t="s"><v>%d</v></c>' % (ref, _si('')))
            elif isinstance(val, (int, float)):
                cells.append('<c r="%s"><v>%s</v></c>' % (ref, val))
            else:
                cells.append('<c r="%s" t="s"><v>%d</v></c>' % (ref, _si(str(val))))
        row_xmls.append('<row r="%d">%s</row>' % (r_idx, ''.join(cells)))

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="%s">'
        '<sheetData>%s</sheetData>'
        '</worksheet>'
    ) % (NS, ''.join(row_xmls))

    ss_items = ''.join('<si><t xml:space="preserve">%s</t></si>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;') for s in shared)
    ss_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="%s" count="%d" uniqueCount="%d">%s</sst>'
    ) % (NS, len(shared), len(shared), ss_items)

    wb_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Reporte" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )

    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        '</Relationships>'
    )

    pkg_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '</Types>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', pkg_rels)
        zf.writestr('xl/workbook.xml', wb_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        zf.writestr('xl/sharedStrings.xml', ss_xml)
    return buf.getvalue()


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

    # ── Modo de pago ──
    modo_pago = fields.Selection([
        ('exactas', 'Pagar cuotas exactas'),
        ('exceden', 'Pagar cuotas que exceden el valor'),
    ], string='Modo de pago', default='exceden', required=True,
       help=(
           "Exactas: solo registra cuotas donde el monto del Excel coincide exactamente con el saldo "
           "de la cuota en el sistema.\n"
           "Exceden: registra cuotas donde el monto del Excel >= saldo de la cuota (lógica actual con división)."
       ))

    result_message = fields.Text(string='Resultado', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Procesado'),
        ('error', 'Error'),
    ], default='draft', string='Estado')

    # ── Contadores resumen ──
    total_filas          = fields.Integer(string='Total filas', readonly=True)
    total_exitosos       = fields.Integer(string='Exitosos', readonly=True)
    total_errores        = fields.Integer(string='Errores', readonly=True)
    total_omitidos       = fields.Integer(string='Omitidos', readonly=True)
    total_no_registradas = fields.Integer(string='No registradas (monto diferente)', readonly=True)

    # ── Resultado visual HTML ──
    result_html = fields.Html(string='Resultado detallado', readonly=True, sanitize=False)

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

        Modos de pago:
          - 'exactas': solo registra si monto_excel == saldo_cuota exactamente.
            Las cuotas con montos distintos se recopilan y se reportan via Excel
            enviado al canal "general".
          - 'exceden': registra cuotas donde monto_excel >= saldo_cuota
            (comportamiento original, con división de cuotas).
        """
        self.ensure_one()
        if not self.archivo_excel:
            raise UserError(_('Por favor, seleccione un archivo Excel antes de importar.'))

        file_data = base64.b64decode(self.archivo_excel)
        filename = (self.nombre_archivo or '').lower()

        try:
            rows = self._read_rows(file_data, filename)
        except Exception as e:
            self.write({
                'state': 'error',
                'result_message': _('Error al leer el archivo: %s') % str(e),
                'result_html': '<div class="alert alert-danger"><i class="fa fa-times-circle"/> %s</div>' % str(e),
            })
            return self._reopen()

        # ── Estructuras de resultado ──
        filas_exitosas    = []  # {'fila': N, 'doc': '...', 'cuotas': '...', 'monto': X, 'op': '...'}
        filas_error       = []  # {'fila': N, 'doc': '...', 'msg': '...'}
        filas_no_reg      = []  # {'fila': N, 'cuota': '...', 'monto_sistema': X, 'monto_excel': Y, 'razon': '...'}
        omitidas = 0
        total_filas = len([r for r in rows if r and any(r)])

        modo = self.modo_pago or 'exceden'

        for idx, row in enumerate(rows, start=2):
            try:
                if not row or not any(row):
                    continue

                # ── Columnas: Fecha | Descripcion | Moneda | Monto | Numero Op ──
                fecha_raw   = row[0] if len(row) > 0 else None
                descripcion = str(row[1]).strip() if len(row) > 1 and row[1] else ''
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

                if monto < 0:
                    # ── Monto negativo → registrar como Egreso de Caja ──
                    try:
                        op_key = num_op or ('IMPORT-%d' % idx)
                        # Validar duplicado de número de operación en egresos
                        existing_egreso = self.env['adt.comercial.egreso.caja'].search(
                            [('numero_operacion', '=', op_key)], limit=1
                        )
                        if existing_egreso:
                            filas_error.append({
                                'fila': idx,
                                'doc': '— (Egreso)',
                                'msg': 'Número de operación "%s" ya registrado en Egresos de Caja '
                                       '(ref: %s)' % (op_key, existing_egreso.name or existing_egreso.id),
                            })
                            continue
                        self.env['adt.comercial.egreso.caja'].create({
                            'fecha': fecha_pago or date.today(),
                            'descripcion': descripcion or ('Fila %d' % idx),
                            'monto': abs(monto),
                            'numero_operacion': op_key,
                        })
                        filas_exitosas.append({
                            'fila': idx,
                            'doc': '— (Egreso)',
                            'cuotas': 'Registrado en Egresos de Caja',
                            'monto': abs(monto),
                            'op': op_key,
                        })
                    except Exception as e_egreso:
                        filas_error.append({
                            'fila': idx,
                            'doc': '—',
                            'msg': 'Error al registrar egreso: %s' % str(e_egreso),
                        })
                        _logger.exception('CuotasMasivas: error creando egreso en fila %d', idx)
                    continue

                if monto == 0:
                    filas_error.append({
                        'fila': idx,
                        'doc': '—',
                        'msg': 'Monto inválido (%s)' % monto_raw,
                    })
                    continue

                # ── Extracción ──
                tipo_doc, numero_doc = extract_info(descripcion)

                if tipo_doc == 'placa':
                    tipo_doc, numero_doc = resolve_placa_to_dni(self.env, numero_doc)

                if tipo_doc == 'unknown' or not numero_doc:
                    omitidas += 1
                    continue

                if tipo_doc == 'placa':
                    omitidas += 1
                    continue

                # ── Buscar cuota ──
                cuota, err_msg = self._find_cuota(numero_doc, fecha_pago)
                if err_msg:
                    filas_error.append({
                        'fila': idx,
                        'doc': 'DNI %s' % numero_doc,
                        'msg': err_msg,
                    })
                    continue

                saldo_cuota = cuota.saldo or 0.0

                # ══════════════════════════════════════════════════════════
                # MODO EXACTAS: solo registrar si monto coincide exactamente
                # ══════════════════════════════════════════════════════════
                if modo == 'exactas':
                    if round(monto, 2) != round(saldo_cuota, 2):
                        filas_no_reg.append({
                            'fila': idx,
                            'cuota': cuota.name or '—',
                            'doc': 'DNI %s' % numero_doc,
                            'monto_sistema': saldo_cuota,
                            'monto_excel': monto,
                            'razon': 'Monto no coincide: esperado S/%.2f, recibido S/%.2f' % (saldo_cuota, monto),
                        })
                        continue
                    # monto coincide → registrar una sola cuota (sin cascada)
                    cuotas_pagadas, excedente = self._registrar_pago_exacto(
                        cuota, monto, fecha_pago, num_op
                    )
                else:
                    # ══════════════════════════════════════════════════════
                    # MODO EXCEDEN: comportamiento original con cascada/división
                    # ══════════════════════════════════════════════════════
                    cuotas_pagadas, excedente = self._registrar_pago(
                        cuota, monto, fecha_pago, num_op
                    )

                detalle_cuotas = ', '.join(cuotas_pagadas) if cuotas_pagadas else '—'
                excedente_txt = ' | Excedente: S/ %.2f' % excedente if excedente > 0 else ''
                filas_exitosas.append({
                    'fila': idx,
                    'doc': 'DNI %s' % numero_doc,
                    'cuotas': detalle_cuotas + excedente_txt,
                    'monto': monto,
                    'op': num_op,
                })

            except Exception as e:
                filas_error.append({
                    'fila': idx,
                    'doc': '—',
                    'msg': str(e),
                })
                _logger.exception('CuotasMasivas: error en fila %d', idx)

        _logger.warning(modo == 'exactas' and 'CuotasMasivas: %d filas no registradas por monto diferente' % len(filas_no_reg) or '')
        # ── Enviar reporte de no-registradas al canal "general" (solo modo exactas) ──
        if modo == 'exactas' and filas_no_reg:
            try:
                self._enviar_reporte_no_registradas(filas_no_reg, filas_exitosas)
            except Exception as e:
                _logger.exception('CuotasMasivas: error enviando reporte al canal general: %s', e)

        # ── Construir HTML ──
        html = self._build_result_html(
            total_filas, filas_exitosas, filas_error, omitidas, filas_no_reg
        )

        # Texto plano para result_message (compatibilidad)
        lines = ['Pagos registrados: %d | Errores: %d | Omitidos: %d | No registradas: %d' % (
            len(filas_exitosas), len(filas_error), omitidas, len(filas_no_reg)
        )]
        self.write({
            'total_filas':          total_filas,
            'total_exitosos':       len(filas_exitosas),
            'total_errores':        len(filas_error),
            'total_omitidos':       omitidas,
            'total_no_registradas': len(filas_no_reg),
            'result_message':       '\n'.join(lines),
            'result_html':          html,
            'state': 'done' if not filas_error else 'error',
        })
        return self._reopen()

    # ──────────────────────────────────────────────────────────────────────────
    # Registrar pago exacto (modo exactas — sin cascada ni división)
    # ──────────────────────────────────────────────────────────────────────────

    def _registrar_pago_exacto(self, cuota, monto, fecha_pago, numero_operacion):
        """
        Registra el pago de UNA SOLA cuota cuando el monto coincide exactamente.
        No hay cascada ni división de cuotas.
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

        journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', cuota.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('No se encontró un diario de banco/caja para registrar el pago.'))

        mora, mora_dias = self._calcular_mora(cuota, fecha_pago, cuota.company_id.id)

        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'journal_id': journal.id,
            'cuota_id': cuota.id,
            'ref': numero_operacion,
            'amount': monto,
            'date': fecha_pago or date.today(),
            'partner_id': cuota.cuenta_id.partner_id.id,
            'mora': mora,
            'mora_dias': mora_dias,
            'mora_state': 'pending',
        })
        payment.action_post()
        cuota.write({'state': 'pagado'})

        label = '%s%s' % (cuota.name, ' [mora: %.2f]' % mora if mora > 0 else '')
        return [label], 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Enviar reporte de cuotas no registradas al canal "general"
    # ──────────────────────────────────────────────────────────────────────────

    def _enviar_reporte_no_registradas(self, filas_no_reg, filas_exitosas):
        """
        Genera un Excel con las cuotas no registradas y lo envía al canal 'general'
        de mail.channel con un mensaje resumen.
        """
        # ── 1. Generar Excel ──
        headers = [
            'Fila', 'Documento', 'N° Cuota',
            'Monto Esperado (Sistema)', 'Monto Recibido (Excel)',
            'Razón de Rechazo',
        ]
        rows_data = [
            [
                r['fila'],
                r.get('doc', '—'),
                r['cuota'],
                r['monto_sistema'],
                r['monto_excel'],
                r['razon'],
            ]
            for r in filas_no_reg
        ]
        xlsx_bytes = _build_xlsx_bytes(headers, rows_data)
        xlsx_b64 = base64.b64encode(xlsx_bytes).decode('utf-8')

        # ── 2. Buscar canal "general" ──
        canal = self.env['mail.channel'].sudo().search(
            [('name', 'ilike', 'general')], limit=1
        )
        if not canal:
            _logger.warning('CuotasMasivas: no se encontró canal "general" en mail.channel')
            return

        # ── 3. Calcular resumen ──
        total_exitosos = len(filas_exitosas)
        monto_exitoso  = sum(r.get('monto', 0.0) for r in filas_exitosas)
        total_no_reg   = len(filas_no_reg)
        monto_no_reg   = sum(r.get('monto_excel', 0.0) for r in filas_no_reg)

        fecha_hoy = date.today().strftime('%d/%m/%Y')
        body = (
            '<p><b>📊 Reporte de Importación Masiva de Cuotas — %s</b></p>'
            '<ul>'
            '<li>✅ Cuotas registradas exitosamente: <b>%d</b> (Total: S/ %.2f)</li>'
            '<li>❌ Cuotas NO registradas (monto no coincide): <b>%d</b> (Total: S/ %.2f)</li>'
            '</ul>'
            '<p>Se adjunta el archivo Excel con el detalle de las cuotas pendientes de regularizar.</p>'
        ) % (fecha_hoy, total_exitosos, monto_exitoso, total_no_reg, monto_no_reg)

        # ── 4. Enviar mensaje con adjunto al canal ──
        attachment = self.env['ir.attachment'].sudo().create({
            'name': 'cuotas_no_registradas_%s.xlsx' % date.today().strftime('%Y%m%d'),
            'datas': xlsx_b64,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': 'mail.channel',
            'res_id': canal.id,
        })

        canal.sudo().message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            attachment_ids=[attachment.id],
        )
        _logger.info(
            'CuotasMasivas: reporte de %d cuotas no registradas enviado al canal "%s"',
            total_no_reg, canal.name,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Builder HTML del resultado
    # ──────────────────────────────────────────────────────────────────────────

    def _build_result_html(self, total_filas, exitosas, errores, omitidas, no_reg=None):
        no_reg = no_reg or []
        total_procesadas = len(exitosas) + len(errores)
        pct = int(total_procesadas * 100 / total_filas) if total_filas else 100
        bar_color = '#28a745' if not errores else ('#ffc107' if exitosas else '#dc3545')

        # ── Barra de progreso ──
        barra = '''
        <div style="margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; font-size:13px; color:#6c757d; margin-bottom:4px;">
                <span><i class="fa fa-tasks"/> Filas procesadas: <strong>{procesadas} / {total}</strong></span>
                <span><strong>{pct}%</strong></span>
            </div>
            <div style="background:#e9ecef; border-radius:8px; height:14px; overflow:hidden;">
                <div style="width:{pct}%; background:{color}; height:100%; border-radius:8px;
                            transition:width 0.4s ease;"></div>
            </div>
        </div>
        '''.format(procesadas=total_procesadas, total=total_filas, pct=pct, color=bar_color)

        # ── Tarjetas resumen ──
        no_reg_card = ''
        if no_reg:
            no_reg_card = '''
            <div style="flex:1; min-width:120px; background:#e2d9f3; border:1px solid #c4aee9;
                        border-radius:8px; padding:14px; text-align:center;">
                <div style="font-size:28px; font-weight:bold; color:#4a235a;">{no_reg}</div>
                <div style="font-size:12px; color:#4a235a;"><i class="fa fa-exclamation-triangle"/> No registradas</div>
            </div>
            '''.format(no_reg=len(no_reg))

        resumen = '''
        <div style="display:flex; gap:12px; margin-bottom:20px; flex-wrap:wrap;">
            <div style="flex:1; min-width:120px; background:#d4edda; border:1px solid #c3e6cb;
                        border-radius:8px; padding:14px; text-align:center;">
                <div style="font-size:28px; font-weight:bold; color:#155724;">{exitosas}</div>
                <div style="font-size:12px; color:#155724;"><i class="fa fa-check-circle"/> Exitosos</div>
            </div>
            <div style="flex:1; min-width:120px; background:#f8d7da; border:1px solid #f5c6cb;
                        border-radius:8px; padding:14px; text-align:center;">
                <div style="font-size:28px; font-weight:bold; color:#721c24;">{errores}</div>
                <div style="font-size:12px; color:#721c24;"><i class="fa fa-times-circle"/> Errores</div>
            </div>
            <div style="flex:1; min-width:120px; background:#fff3cd; border:1px solid #ffeeba;
                        border-radius:8px; padding:14px; text-align:center;">
                <div style="font-size:28px; font-weight:bold; color:#856404;">{omitidas}</div>
                <div style="font-size:12px; color:#856404;"><i class="fa fa-minus-circle"/> Omitidos</div>
            </div>
            {no_reg_card}
            <div style="flex:1; min-width:120px; background:#d1ecf1; border:1px solid #bee5eb;
                        border-radius:8px; padding:14px; text-align:center;">
                <div style="font-size:28px; font-weight:bold; color:#0c5460;">{total}</div>
                <div style="font-size:12px; color:#0c5460;"><i class="fa fa-list"/> Total filas</div>
            </div>
        </div>
        '''.format(
            exitosas=len(exitosas), errores=len(errores),
            omitidas=omitidas, total=total_filas,
            no_reg_card=no_reg_card,
        )

        # ── Tabla de resultados (exitosas + errores) ──
        filas_html = ''

        # Exitosas
        for r in exitosas:
            filas_html += '''
            <tr style="background:#f8fff8;">
                <td style="padding:8px 10px; text-align:center;">
                    <span style="background:#28a745; color:#fff; border-radius:12px;
                                 padding:2px 8px; font-size:11px;">✅ Éxito</span>
                </td>
                <td style="padding:8px 10px; color:#6c757d; font-size:13px;">{fila}</td>
                <td style="padding:8px 10px; font-weight:500;">{doc}</td>
                <td style="padding:8px 10px; font-size:12px; color:#495057;">{cuotas}</td>
                <td style="padding:8px 10px; font-weight:600; color:#155724;">S/ {monto:.2f}</td>
                <td style="padding:8px 10px; font-size:12px; color:#6c757d;">{op}</td>
            </tr>
            '''.format(**r)

        # Errores
        for r in errores:
            filas_html += '''
            <tr style="background:#fff8f8;">
                <td style="padding:8px 10px; text-align:center;">
                    <span style="background:#dc3545; color:#fff; border-radius:12px;
                                 padding:2px 8px; font-size:11px;">❌ Error</span>
                </td>
                <td style="padding:8px 10px; color:#6c757d; font-size:13px;">{fila}</td>
                <td style="padding:8px 10px; font-weight:500;">{doc}</td>
                <td colspan="3" style="padding:8px 10px; font-size:12px; color:#721c24;">{msg}</td>
            </tr>
            '''.format(**r)

        if not filas_html:
            filas_html = '<tr><td colspan="6" style="text-align:center; padding:20px; color:#6c757d;">Sin resultados</td></tr>'

        tabla = '''
        <div style="border:1px solid #dee2e6; border-radius:8px; overflow:hidden;">
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
                <thead>
                    <tr style="background:#343a40; color:#fff;">
                        <th style="padding:10px; width:90px;">Estado</th>
                        <th style="padding:10px; width:60px;">Fila</th>
                        <th style="padding:10px;">Documento</th>
                        <th style="padding:10px;">Cuotas pagadas</th>
                        <th style="padding:10px; width:100px;">Monto</th>
                        <th style="padding:10px; width:120px;"># Operación</th>
                    </tr>
                </thead>
                <tbody>{filas}</tbody>
            </table>
        </div>
        '''.format(filas=filas_html)

        # ── Sección de cuotas NO registradas (solo modo exactas) ──
        tabla_no_reg = ''
        if no_reg:
            filas_nr = ''
            for r in no_reg:
                filas_nr += '''
                <tr style="background:#fdf0ff;">
                    <td style="padding:8px 10px; color:#6c757d; font-size:13px;">{fila}</td>
                    <td style="padding:8px 10px; font-weight:500;">{doc}</td>
                    <td style="padding:8px 10px; font-size:12px;">{cuota}</td>
                    <td style="padding:8px 10px; font-weight:600; color:#721c24;">S/ {monto_sistema:.2f}</td>
                    <td style="padding:8px 10px; font-weight:600; color:#856404;">S/ {monto_excel:.2f}</td>
                    <td style="padding:8px 10px; font-size:12px; color:#4a235a;">{razon}</td>
                </tr>
                '''.format(**r)

            tabla_no_reg = '''
            <h5 style="color:#4a235a; margin:20px 0 8px;">
                <i class="fa fa-exclamation-triangle"/> Cuotas no registradas (monto diferente) — Reporte enviado al canal "general"
            </h5>
            <div style="border:1px solid #c4aee9; border-radius:8px; overflow:hidden;">
                <table style="width:100%; border-collapse:collapse; font-size:13px;">
                    <thead>
                        <tr style="background:#6f42c1; color:#fff;">
                            <th style="padding:10px; width:60px;">Fila</th>
                            <th style="padding:10px;">Documento</th>
                            <th style="padding:10px;">N° Cuota</th>
                            <th style="padding:10px; width:130px;">Monto Sistema</th>
                            <th style="padding:10px; width:130px;">Monto Excel</th>
                            <th style="padding:10px;">Razón de Rechazo</th>
                        </tr>
                    </thead>
                    <tbody>{filas}</tbody>
                </table>
            </div>
            '''.format(filas=filas_nr)

        estado_badge = (
            '<span style="background:#28a745;color:#fff;padding:4px 12px;border-radius:20px;font-size:13px;">✅ Completado</span>'
            if not errores else
            '<span style="background:#ffc107;color:#212529;padding:4px 12px;border-radius:20px;font-size:13px;">⚠️ Completado con errores</span>'
        )

        return '''
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; padding:4px;">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                <h4 style="margin:0; color:#343a40;"><i class="fa fa-bar-chart"/> Resultado del procesamiento</h4>
                {badge}
            </div>
            {barra}
            {resumen}
            <h5 style="color:#343a40; margin:16px 0 8px;"><i class="fa fa-table"/> Detalle de registros</h5>
            {tabla}
            {tabla_no_reg}
        </div>
        '''.format(badge=estado_badge, barra=barra, resumen=resumen, tabla=tabla, tabla_no_reg=tabla_no_reg)

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
            'archivo_excel':       False,
            'nombre_archivo':      False,
            'result_message':      False,
            'result_html':         False,
            'total_filas':         0,
            'total_exitosos':      0,
            'total_errores':       0,
            'total_omitidos':      0,
            'total_no_registradas': 0,
            'state':               'draft',
        })
        return self._reopen()
