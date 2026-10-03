from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _
from odoo.exceptions import ValidationError

DIAS_MES = 30
DIAS_SEMANA = 7
CARGO_DIARIO_DEFECTO = 5.0


def validar_parametros(importe_financiar, cuota_inicial, tea, plazo_meses, cargo_diario=0.0):
    """Devuelve un mensaje de error, o None si los parámetros son válidos."""
    if not tea or tea <= 0:
        return _('La TEA debe ser mayor que cero (se guarda en decimal, ej. 26.82% = 0.2682).')
    if not plazo_meses or plazo_meses <= 0 or int(plazo_meses) != plazo_meses:
        return _('El plazo debe ser un número entero positivo de meses.')
    if cuota_inicial < 0:
        return _('La cuota inicial no puede ser negativa.')
    if importe_financiar - cuota_inicial <= 0:
        return _('La cuota inicial debe ser menor que el importe a financiar.')
    if (cargo_diario or 0.0) < 0:
        return _('El cargo diario no puede ser negativo.')
    return None


def calcular_cuotas(importe_financiar, cuota_inicial, tea, plazo_meses, cargo_diario=0.0):
    """Cadena de fórmulas del simulador (sin redondeos intermedios).

    F4  = F2 - F3                    capital
    E9  = (1 + TEA)^(1/12) - 1       interés mensual (im)
    I9  = im * (1 + im)^plazo        factor A
    K9  = (1 + im)^plazo - 1         factor B
    K10 = F4 * I9 / K9               cuota mensual (sin cargo)
    K12 = K10 / 30                   cuota diaria (sin cargo)

    A la cuota diaria se le suma el `cargo_diario` (monto fijo por cada día) y
    las demás cuotas se derivan de ella con las mismas equivalencias:

    cuota diaria  = K12 + cargo
    cuota semanal = cuota diaria * 7
    cuota mensual = K10 + cargo * 30
    total del crédito  = cuota mensual * plazo
    total cargo diario = cargo * plazo * 30
    total de intereses = K10 * plazo - F4   (no incluye el cargo diario)
    """
    error = validar_parametros(importe_financiar, cuota_inicial, tea, plazo_meses, cargo_diario)
    if error:
        raise ValidationError(error)

    plazo = int(plazo_meses)
    capital = importe_financiar - cuota_inicial
    interes_mensual = (1 + tea) ** (1 / 12) - 1
    factor_a = interes_mensual * (1 + interes_mensual) ** plazo
    factor_b = (1 + interes_mensual) ** plazo - 1
    cargo = cargo_diario or 0.0
    cuota_mensual_base = capital * factor_a / factor_b
    cuota_mensual = cuota_mensual_base + cargo * DIAS_MES
    cuota_diaria = cuota_mensual_base / DIAS_MES + cargo
    cuota_semanal = cuota_diaria * DIAS_SEMANA
    total_credito = cuota_mensual * plazo
    total_cargo_diario = cargo * plazo * DIAS_MES
    return {
        'capital': capital,
        'interes_mensual': interes_mensual,
        'cuota_mensual': cuota_mensual,
        'cuota_semanal': cuota_semanal,
        'cuota_diaria': cuota_diaria,
        'total_credito': total_credito,
        'total_cargo_diario': total_cargo_diario,
        'total_intereses': total_credito - total_cargo_diario - capital,
    }


FRECUENCIAS = ('mensual', 'semanal', 'diaria')


def generar_cronograma(fecha_inicio, frecuencia, plazo_meses, cuota_mensual, total_credito):
    """Cronograma simple a partir del resultado del simulador.

    Usa las mismas equivalencias de la hoja (mes = 30 días, semana = 7 días):
    * mensual: `plazo` cuotas de C/Mensual.
    * semanal: cuotas de C/Semanal cada 7 días (`plazo*30/7`, redondeado hacia arriba).
    * diaria:  `plazo*30` cuotas de C/Diaria, una por día.

    La cuota k vence `k` periodos después de la fecha de inicio. La última cuota se
    ajusta para que la suma sea exactamente el total del crédito (redondeado a
    centavos). El saldo es lo que falta pagar del total del crédito.
    """
    plazo = int(plazo_meses)
    dias = plazo * DIAS_MES
    if frecuencia == 'mensual':
        cantidad, monto = plazo, cuota_mensual
    elif frecuencia == 'semanal':
        cantidad, monto = -(-dias // DIAS_SEMANA), cuota_mensual / DIAS_MES * DIAS_SEMANA
    elif frecuencia == 'diaria':
        cantidad, monto = dias, cuota_mensual / DIAS_MES
    else:
        raise ValidationError(_('Frecuencia no válida: %s') % frecuencia)

    monto_c = round(monto * 100)
    total_c = round(total_credito * 100)
    filas, pagado = [], 0
    for k in range(1, cantidad + 1):
        cuota_c = monto_c if k < cantidad else total_c - pagado
        pagado += cuota_c
        if frecuencia == 'mensual':
            fecha = fecha_inicio + relativedelta(months=k)
        elif frecuencia == 'semanal':
            fecha = fecha_inicio + timedelta(days=DIAS_SEMANA * k)
        else:
            fecha = fecha_inicio + timedelta(days=k)
        filas.append({
            'numero': k,
            'fecha': fecha,
            'cuota': cuota_c / 100,
            'saldo': (total_c - pagado) / 100,
        })
    return filas
