# -*- coding: utf-8 -*-
"""
Parser del PDF "PLAN DE PAGOS" (formato fijo de la cooperativa).

No depende de Odoo: se puede usar desde el modelo o por línea de comandos:

    python3 plan_pagos_parser.py "21 URIBURU CHUCHON JOSE DANIEL.pdf"

Estrategia para garantizar precisión
====================================
1. Extracción por coordenadas (pdfminer): cada fragmento de texto trae su
   posición (x, y). Agrupamos por fila (misma y) y ordenamos por x, así el
   texto conserva el layout del PDF aunque tenga dos columnas de cabecera.
2. Anclas fijas: las etiquetas (SOCIO, MONTO CRÉDITO, PLAZO...) siempre son
   las mismas, así que el valor de cada clave es "lo que sigue a su etiqueta
   hasta la siguiente etiqueta conocida".
3. Doble motor: la tabla de cuotas se extrae también con PyPDF2 (motor
   independiente) y ambos resultados deben coincidir (consenso).
4. Validación matemática (el documento es un cronograma financiero, así que
   sus números deben cumplir identidades exactas):
     - Suma por fila:  capital + interés + desgravamen + ... + otros = total
     - Suma por columna = fila "Total" del PDF
     - Interés con TEA:  interés_i = saldo_{i-1} · ((1 + TEA)^(días_i/360) − 1)
     - Desgravamen:      desgrav_i = tasa · saldo_i  (tasa mensual inferida por
                         mínimos cuadrados y luego verificada fila por fila)
     - Plazo en días = último vencimiento − fecha de desembolso
     - Cuotas consecutivas y vencimientos mensuales
     - DNI de 8 dígitos
   Si un número se lee mal (un dígito cambiado, columna corrida) alguna de
   estas identidades falla y el documento queda "observado".
"""
import io
import json
import re
import sys
from datetime import date, datetime

# --------------------------------------------------------------------------
# Constantes del formato
# --------------------------------------------------------------------------

# Etiqueta en el PDF -> clave en el JSON
HEADER_LABELS = [
    ('NRO. SOLICITUD', 'nro_solicitud'),
    ('NRO. EXPEDIENTE', 'nro_expediente'),
    ('AGENCIA', 'agencia'),
    ('SOCIO', 'socio'),
    ('MONTO CRÉDITO', 'monto_credito'),
    ('FECHA DESEMB.', 'fecha_desembolso'),
    ('PLAZO', 'plazo_dias'),
    ('FREC. CUOTA', 'frecuencia_cuota'),
    ('TASA INTERÉS ANUAL', 'tasa_interes_anual'),
    ('PRODUCTO', 'producto'),
    ('TIPO DE CRÉDITO', 'tipo_credito'),
    ('TIPO DE COBRO', 'tipo_cobro'),
    ('ANALISTA', 'analista'),
]

# Campos de cabecera que pueden faltar en el PDF: se usa este valor por defecto
# en lugar de rechazar el documento.
HEADER_DEFAULTS = {
    'nro_solicitud': '0',
}

# Columnas numéricas de la tabla de cuotas, en el orden del PDF
CUOTA_COLUMNS = [
    'capital', 'interes', 'seguro_desgravamen', 'comision_operativa',
    'interes_vencido', 'interes_moratorio', 'interes_compensatorio',
    'aporte', 'otros', 'total',
]

NUM = r'-?[\d,]+\.\d{2}'
DATE = r'\d{1,2}/\d{2}/\d{4}'
CUOTA_RE = re.compile(
    r'(?P<fecha>%s)\s+(?P<nro>\d{1,3})\s+(?P<nums>(?:%s\s+){9}%s)\s+(?P<estado>[A-Za-zÁÉÍÓÚÑáéíóúñ]+(?: [A-Za-zÁÉÍÓÚÑáéíóúñ]+)*?)'
    r'(?=\s+%s|\s+Total\b|\s*$)'
    % (DATE, NUM, NUM, DATE)
)
TOTAL_RE = re.compile(r'\bTotal\s+(?P<nums>(?:%s\s+){9}%s)' % (NUM, NUM))

# Tolerancias (en soles)
TOL_ROW = 0.02          # redondeo de céntimos al sumar una fila
TOL_COLUMN = 0.05       # suma de columna vs fila Total
TOL_FORMULA = 0.02      # interés / desgravamen recalculados vs PDF


class PlanPagosParseError(Exception):
    pass


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _to_float(value):
    return float(value.replace(',', ''))


def _to_date(value):
    return datetime.strptime(value.strip(), '%d/%m/%Y').date()


def _add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, d.day)


# --------------------------------------------------------------------------
# 1) PDF -> texto
# --------------------------------------------------------------------------

def extract_text_layout(pdf_bytes, y_tolerance=3.0):
    """Texto con el layout del PDF usando coordenadas de pdfminer.

    Fragmentos con la misma 'y' (± y_tolerance) forman una fila; dentro de la
    fila se ordenan por 'x' y se separan con doble espacio (límite de columna).
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextContainer, LTTextLine

    pages_text = []
    for page in extract_pages(io.BytesIO(pdf_bytes), laparams=LAParams()):
        segments = []
        for element in page:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if isinstance(line, LTTextLine):
                    text = line.get_text().strip()
                    if text:
                        segments.append((line.y1, line.x0, text))

        rows = []
        for y, x, text in sorted(segments, key=lambda s: (-s[0], s[1])):
            if rows and abs(rows[-1]['y'] - y) <= y_tolerance:
                rows[-1]['items'].append((x, text))
            else:
                rows.append({'y': y, 'items': [(x, text)]})

        lines = ['  '.join(t for _, t in sorted(r['items'])) for r in rows]
        pages_text.append('\n'.join(lines))
    return '\n\f\n'.join(pages_text)


def extract_text_pypdf2(pdf_bytes):
    """Motor secundario e independiente (flujo de tokens, sin layout)."""
    try:
        import PyPDF2
    except ImportError:
        return None
    reader = PyPDF2.PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    return '\n'.join(reader.getPage(i).extractText() for i in range(reader.getNumPages()))


# --------------------------------------------------------------------------
# 2) texto -> clave/valor
# --------------------------------------------------------------------------

def _parse_header(text):
    # Sólo la parte anterior a la tabla, aplanada en una línea
    head = text.split('CUOTAS A PAGAR')[0]
    head = re.sub(r'\s+', ' ', head.replace('PLAN DE PAGOS', ' '))

    # Las etiquetas más largas primero para que "TIPO DE CRÉDITO" no se
    # confunda con otra etiqueta que sea prefijo
    labels = sorted((l for l, _ in HEADER_LABELS), key=len, reverse=True)
    label_re = re.compile(r'(%s)\s*:?' % '|'.join(re.escape(l) for l in labels))

    raw = {}
    matches = list(label_re.finditer(head))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(head)
        value = head[m.end():end].strip().lstrip(':').strip()
        raw.setdefault(m.group(1), value)

    header = {key: raw.get(label) for label, key in HEADER_LABELS}
    for key, default in HEADER_DEFAULTS.items():
        if not header.get(key):
            header[key] = default

    missing = [k for _, k in HEADER_LABELS if not header.get(k)]
    if missing:
        raise PlanPagosParseError('No se encontraron los campos: %s' % ', '.join(missing))

    # Normalización de tipos
    socio = header.pop('socio')
    nombre, _, codigo = socio.partition('//')
    header['socio'] = nombre.strip()
    header['codigo_socio'] = codigo.strip()
    header['monto_credito'] = _to_float(re.search(NUM, header['monto_credito']).group())
    header['moneda'] = 'PEN'
    header['plazo_dias'] = int(re.search(r'\d+', header['plazo_dias']).group())
    header['tasa_interes_anual'] = float(re.search(r'[\d.]+', header['tasa_interes_anual']).group())
    header['fecha_desembolso'] = _to_date(header['fecha_desembolso']).isoformat()
    return header


def _parse_cuotas(text):
    flat = re.sub(r'\s+', ' ', text)
    cuotas = []
    for m in CUOTA_RE.finditer(flat):
        nums = [_to_float(n) for n in m.group('nums').split()]
        row = {
            'nro_cuota': int(m.group('nro')),
            'fecha_vencimiento': _to_date(m.group('fecha')).isoformat(),
        }
        row.update(dict(zip(CUOTA_COLUMNS, nums)))
        row['estado'] = m.group('estado')
        cuotas.append(row)

    totales = None
    m = TOTAL_RE.search(flat)
    if m:
        totales = dict(zip(CUOTA_COLUMNS, [_to_float(n) for n in m.group('nums').split()]))
    return cuotas, totales


def _parse_footer(text):
    footer = dict.fromkeys(['dni', 'oficina', 'usuario_emisor', 'fecha_sistema', 'fecha_maquina'])
    m = re.search(r'DNI\s+NRO\.\s*(\d+)', text)
    if m:
        footer['dni'] = m.group(1)
    m = re.search(r'Oficina:\s*(.+?)\s+Usuario:', text)
    if m:
        footer['oficina'] = m.group(1).strip()
    m = re.search(r'Usuario:\s*(.+?)\s+Fecha Sistema:', text)
    if m:
        footer['usuario_emisor'] = m.group(1).strip()
    m = re.search(r'Fecha Sistema:\s*(%s)' % DATE, text)
    if m:
        footer['fecha_sistema'] = _to_date(m.group(1)).isoformat()
    m = re.search(r'(%s)\s+(\d{2}:\d{2}:\d{2})' % DATE, text.split('Fecha Maquina')[-1])
    if m:
        footer['fecha_maquina'] = '%sT%s' % (_to_date(m.group(1)).isoformat(), m.group(2))
    return footer


# --------------------------------------------------------------------------
# 3) Validaciones matemáticas
# --------------------------------------------------------------------------

def _check(checks, code, ok, detail):
    checks.append({'regla': code, 'ok': bool(ok), 'detalle': detail})


def desgravamen_rate(cuotas):
    """Tasa mensual de desgravamen estimada por mínimos cuadrados
    (Σ desgrav / Σ saldo), redondeada a 4 decimales en porcentaje."""
    saldo = sum(c['capital'] for c in cuotas)
    total_saldo = total_des = 0.0
    for c in cuotas:
        saldo -= c['capital']
        total_saldo += saldo
        total_des += c['seguro_desgravamen']
    return round(total_des / total_saldo, 6) if total_saldo else 0.0


def validate(data, secondary_cuotas=None):
    checks = []
    cuotas = data['cuotas']
    totales = data.get('totales')
    header = data['cabecera']

    _check(checks, 'cuotas_encontradas', cuotas, '%d cuotas leídas' % len(cuotas))
    if not cuotas:
        return checks

    # Suma por fila
    bad_rows = []
    for c in cuotas:
        s = round(sum(c[k] for k in CUOTA_COLUMNS[:-1]), 2)
        if abs(s - c['total']) > TOL_ROW:
            bad_rows.append('cuota %d: suma %.2f ≠ total %.2f' % (c['nro_cuota'], s, c['total']))
    _check(checks, 'suma_por_fila', not bad_rows,
           '; '.join(bad_rows) or 'Todas las filas cuadran (capital+interés+...+otros = total)')

    # Suma por columna
    if totales:
        bad_cols = []
        for k in CUOTA_COLUMNS:
            s = round(sum(c[k] for c in cuotas), 2)
            if abs(s - totales[k]) > TOL_COLUMN:
                bad_cols.append('%s: suma %.2f ≠ %.2f' % (k, s, totales[k]))
        _check(checks, 'suma_por_columna', not bad_cols,
               '; '.join(bad_cols) or 'Todas las columnas cuadran con la fila Total')
    else:
        _check(checks, 'suma_por_columna', False, 'No se encontró la fila Total')

    # Correlatividad y periodicidad mensual
    nros = [c['nro_cuota'] for c in cuotas]
    _check(checks, 'cuotas_consecutivas', nros == list(range(nros[0], nros[0] + len(nros))),
           'Cuotas %d a %d' % (nros[0], nros[-1]))
    fechas = [date.fromisoformat(c['fecha_vencimiento']) for c in cuotas]
    expected = [_add_months(fechas[0], i) for i in range(len(fechas))]
    _check(checks, 'vencimientos_mensuales', fechas == expected,
           'Vencimientos cada mes el día %d' % fechas[0].day)

    # Plazo = último vencimiento − desembolso
    desembolso = date.fromisoformat(header['fecha_desembolso'])
    dias = (fechas[-1] - desembolso).days
    _check(checks, 'plazo_dias', dias == header['plazo_dias'],
           '%s − %s = %d días (PDF: %d)' % (fechas[-1], desembolso, dias, header['plazo_dias']))

    # Interés con TEA sobre saldo (sistema francés, año comercial de 360 días)
    tea = header['tasa_interes_anual'] / 100.0
    saldo = round(sum(c['capital'] for c in cuotas), 2)
    previo = desembolso if nros[0] == 1 else _add_months(fechas[0], -1)
    bad_int, saldos = [], []
    for c, f in zip(cuotas, fechas):
        d = (f - previo).days
        teorico = saldo * ((1 + tea) ** (d / 360.0) - 1)
        if abs(teorico - c['interes']) > TOL_FORMULA:
            bad_int.append('cuota %d: %.2f vs teórico %.2f' % (c['nro_cuota'], c['interes'], teorico))
        saldo = round(saldo - c['capital'], 2)
        saldos.append(saldo)
        previo = f
    _check(checks, 'interes_vs_tea', not bad_int,
           '; '.join(bad_int) or 'Interés de cada cuota coincide con saldo·((1+TEA)^(días/360)−1)')

    # Seguro de desgravamen = tasa fija sobre el saldo luego de pagar la cuota
    tasa = desgravamen_rate(cuotas)
    bad_des = ['cuota %d: %.2f vs teórico %.2f' % (c['nro_cuota'], c['seguro_desgravamen'], s * tasa)
               for c, s in zip(cuotas, saldos)
               if abs(s * tasa - c['seguro_desgravamen']) > TOL_FORMULA]
    _check(checks, 'desgravamen_vs_saldo', not bad_des,
           '; '.join(bad_des) or 'Desgravamen = %.4f %% del saldo en todas las cuotas' % (tasa * 100))

    # Capital
    pendiente = round(sum(c['capital'] for c in cuotas), 2)
    _check(checks, 'capital_no_excede_monto', pendiente <= header['monto_credito'] + TOL_COLUMN,
           'Capital pendiente %.2f de %.2f' % (pendiente, header['monto_credito']))

    # DNI
    dni = data.get('pie', {}).get('dni', '')
    _check(checks, 'dni_valido', re.fullmatch(r'\d{8}', dni or ''), 'DNI: %s' % (dni or 'no encontrado'))

    # Consenso entre motores de extracción
    if secondary_cuotas is not None:
        diffs = [c['nro_cuota'] for c, s in zip(cuotas, secondary_cuotas) if c != s]
        same = len(cuotas) == len(secondary_cuotas) and not diffs
        _check(checks, 'consenso_motores', same,
               'pdfminer y PyPDF2 coinciden en %d cuotas' % len(cuotas) if same else
               'Diferencias: %d vs %d filas, cuotas %s' % (len(cuotas), len(secondary_cuotas), diffs))
    return checks


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------

def parse_text(text):
    cuotas, totales = _parse_cuotas(text)
    return {
        'documento': 'PLAN DE PAGOS',
        'cabecera': _parse_header(text),
        'cuotas': cuotas,
        'totales': totales,
        'pie': _parse_footer(text),
    }


def parse_pdf(pdf_bytes):
    """Devuelve (texto, data) donde data incluye 'resumen' y 'validacion'."""
    text = extract_text_layout(pdf_bytes)
    data = parse_text(text)

    secondary = None
    alt_text = extract_text_pypdf2(pdf_bytes)
    if alt_text:
        secondary, _ = _parse_cuotas(alt_text)

    cuotas = data['cuotas']
    data['resumen'] = None
    if cuotas:
        capital_pendiente = round(sum(c['capital'] for c in cuotas), 2)
        data['resumen'] = {
            'cuotas_pendientes': len(cuotas),
            'primera_cuota': cuotas[0]['nro_cuota'],
            'ultima_cuota': cuotas[-1]['nro_cuota'],
            'capital_pendiente': capital_pendiente,
            'capital_amortizado': round(data['cabecera']['monto_credito'] - capital_pendiente, 2),
            'monto_cuota_referencial': cuotas[0]['total'],
            'tasa_desgravamen_mensual': round(desgravamen_rate(cuotas) * 100, 4),
            'proximo_vencimiento': cuotas[0]['fecha_vencimiento'],
        }

    checks = validate(data, secondary)
    passed = sum(1 for c in checks if c['ok'])
    data['validacion'] = {
        'estado': 'valido' if passed == len(checks) else 'observado',
        'confianza': round(100.0 * passed / len(checks), 1),
        'reglas': checks,
    }
    return text, data


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Uso: python3 plan_pagos_parser.py archivo.pdf [--text]')
    with open(sys.argv[1], 'rb') as fh:
        txt, result = parse_pdf(fh.read())
    if '--text' in sys.argv:
        print(txt)
        print('\n' + '=' * 80 + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
