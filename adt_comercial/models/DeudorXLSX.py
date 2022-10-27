from odoo import models, fields
import logging
from odoo.http import request
from datetime import date

log = logging.getLogger(__name__)


class Deudor(models.Model):
    _inherit = "adt.reporte.cobranza.pagos.pendientes"

    def btn_generar_reporte(self):
        report_obj = self.env.ref("adt_comercial.reporte_deudor")
        return report_obj.report_action([], {})


class DeudorXLSX(models.AbstractModel):
    _name = "report.adt_comercial.clientes_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte de Cliente en XLSX"

    def generate_xlsx_report(self, workbook, data, deudores):
        list_deudores = self.generate_new_list()
        sheet = workbook.add_worksheet("Data")
        bold = workbook.add_format({"bold": True})

        sheet.write(0,1,"Referencia")
        sheet.write(0,2,"Socio")
        sheet.write(0,3,"DNI o CE")
        sheet.write(0,4,"Marca y Modelo")
        sheet.write(0,5,"Analista de credito")
        sheet.write(0,6,"Cobrador")
        sheet.write(0,7,"Tipo de cuenta")
        sheet.write(0,8,"Monto de cuota")
        sheet.write(0,9,"Fecha de desembolso")
        sheet.write(0,10,"Monto de deuda total")
        sheet.write(0,11,"Dias de atraso")
        sheet.write(0,12,"Numero de cuotas pagadas")
        sheet.write(0,13,"Numero de cuotas pendientes")
        sheet.write(0,14,"Numero de cuotas viegentes")

        row = 1

        for deudor in list_deudores:
            #dict --> tuple
            # #valores
            sheet.write(row,1,deudor.get('reference_no'))
            sheet.write(row,2,deudor.get('partner_id')[1])
            sheet.write(row,3,"") # DNI o CE
            sheet.write(row,4,deudor.get('vehiculo_id')[1])
            sheet.write(row,5,deudor.get('user_id')[1])

            sheet.write(row,6,deudor.get('user_id')[1])

            sheet.write(row,7,deudor.get('periodicidad'))
            sheet.write(row,8,deudor.get('monto_cuota'))
            sheet.write(row,9,deudor.get('fecha_desembolso').strftime("%m/%d/%Y"))
            sheet.write(row,10,deudor.get('monto_fraccionado'))
            sheet.write(row,11,deudor.get('dias_retraso'))
            sheet.write(row,12,deudor.get('cuotas_pagadas'))
            sheet.write(row,13,deudor.get('cuotas_pendientes'))
            sheet.write(row,14,deudor.get('cuotas_retrasadas'))
            row +=1

    def generate_new_list(self):
        list = request.env['adt.comercial.cuentas'].search(
            [('state', '!=', 'cancelado')]).read([
            'reference_no',  # Referencia
            'partner_id',  # Nombre del socio
            # DNI o CE
            'vehiculo_id',  # Marca de moto y modelo
            'user_id',  # Analista de credito
            # Cobrador
            'periodicidad',  # Tipo de cuenta
            'monto_cuota',  # Monto de cuota
            'fecha_desembolso',  # Fecha de desembolso
            'monto_fraccionado',  # Monto de deuda total
            # Dias de atraso
            # Numero de cuotas pagadas
            # Numero de cuotas pendientes
            # Numero de cuota vigente
        ])

        print(type(list))

        for item in list:
            cuotas_general = request.env['adt.comercial.cuotas'].search(
                [('cuenta_id', '=', item['id'])]).read([
                'fecha_cronograma', 'state'
            ])

            quanty_pagadas = self.count_cuotas_pagadas(cuotas_general)
            quanty_pendientes = self.count_cuotas_pendientes(cuotas_general)
            quanty_retrasadas = self.count_cuotas_retrasadas(cuotas_general)
            quantity_dias_atraso = self.quantity_dias_atraso(item)

            item['dias_retraso'] = quantity_dias_atraso
            item['cuotas_pagadas'] = quanty_pagadas
            item['cuotas_pendientes'] = quanty_pendientes
            item['cuotas_retrasadas'] = quanty_retrasadas

            print(str(item))

        return list

    def quantity_dias_atraso(self, item):
        cuotas = request.env['adt.comercial.cuotas'].search(
            [('state', '=', 'retrasado'), ('cuenta_id', '=', item['id'])]).read([
            'fecha_cronograma'
        ])

        try:
            amount_day1 = cuotas[len(cuotas) - 1]['fecha_cronograma'] - cuotas[0]['fecha_cronograma']
            amount_day2 = date.today() - cuotas[len(cuotas) - 1]['fecha_cronograma']

            total = int(str(amount_day1).split(' ')[0]) + int(str(amount_day2).split(' ')[0])
        except:

            total = 0

        return total

    def count_cuotas_pagadas(self, list):
        quanty = 0
        for cuota in list:
            if cuota['state'] == 'pagado':
                quanty = quanty + 1
        return quanty

    def count_cuotas_pendientes(self, list):
        quanty = 0
        for cuota in list:
            if cuota['state'] == 'pendiente':
                quanty = quanty + 1
        return quanty

    def count_cuotas_retrasadas(self, list):
        quanty = 0
        for cuota in list:
            if cuota['state'] == 'retrasado':
                quanty = quanty + 1
        return quanty
