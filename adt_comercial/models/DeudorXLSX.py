from odoo import models, fields
import logging
from odoo.http import request
from datetime import date

log = logging.getLogger(__name__)


class Deudor(models.Model):
    #_inherit = "adt.reporte.cobranza.pagos.pendientes"
    _inherit = "adt.comercial.cuentas"

    def btn_generar_reporte(self):
        report_obj = self.env.ref("adt_comercial.reporte_deudor")
        return report_obj.report_action([], {})


class DeudorXLSX(models.AbstractModel):
    _name = "report.adt_comercial.clientes_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte de Cliente en XLSX"

    def generate_xlsx_report(self, workbook, data, deudores):

        list_deudores = self.generate_new_list(deudores)
        sheet = workbook.add_worksheet("Data")
        bold = workbook.add_format({"bold": True})


        sheet.write(0, 1, "Referencia")
        sheet.write(0, 2, "Socio")
        sheet.write(0, 3, "DNI o CE")
        sheet.write(0, 4, "Marca y Modelo")
        sheet.write(0, 5, "Analista de credito")
        sheet.write(0, 6, "Cobrador")
        sheet.write(0, 7, "Tipo de cuenta")
        sheet.write(0, 8, "Monto de cuota")
        sheet.write(0, 9, "Fecha de desembolso")
        sheet.write(0, 10, "Monto de deuda total")
        sheet.write(0, 11, "Dias de atraso")
        sheet.write(0, 12, "# de cuotas pagadas")
        sheet.write(0, 13, "# de cuotas pendientes")
        sheet.write(0, 14, "# de cuotas retrasadas")
        sheet.write(0, 15, "Cuota actual")
        sheet.write(0, 16, "# total cuotas")

        row = 1

        for deudor in list_deudores:
            # dict --> tuple
            # #valores
            sheet.write(row, 1, deudor.get('reference_no'))
            sheet.write(row, 2, deudor.get('partner_id')[1])
            sheet.write(row, 3, deudor.get('vat'))  # DNI o CE
            sheet.write(row, 4, deudor.get('vehiculo_id')[1])
            sheet.write(row, 5, deudor.get('user_id')[1])
            sheet.write(row, 6, "")
            sheet.write(row, 7, deudor.get('periodicidad'))
            sheet.write(row, 8, deudor.get('monto_cuota'))

            if type(deudor.get('fecha_desembolso')) != bool:
                sheet.write(row, 9, deudor.get('fecha_desembolso').strftime("%d/%m/%Y"))
            else:
                sheet.write(row, 9, deudor.get(''))

            sheet.write(row, 10, deudor.get('amount_cuota_retrasadas'))
            sheet.write(row, 11, deudor.get('dias_retraso'))
            sheet.write(row, 12, deudor.get('cuotas_pagadas'))
            sheet.write(row, 13, deudor.get('cuotas_pendientes'))
            sheet.write(row, 14, deudor.get('cuotas_retrasadas'))
            sheet.write(row, 15, deudor.get('cuota_actual'))
            sheet.write(row, 16, deudor.get('total_cuotas'))

            row += 1


    def generate_new_list(self,cuentas):

        list = []

        for item in cuentas:
            print(item.id)
            data = request.env['adt.comercial.cuentas'].search(
                [('state', '!=', 'cancelado'),('id','=',item.id)], order="id asc").read([
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

            list = list + data

            print(data)
            #print(type(data))
            #list.append(data)

        last_list = []

        print(type(list))

        for item in list:
            #print(type(item))
            cuotas_general = request.env['adt.comercial.cuotas'].search(
                [('cuenta_id', '=', item['id'])]).read([
                'fecha_cronograma', 'state', 'name', 'monto'])

            """item['dias_retraso'] = self.quantity_dias_atraso2(cuotas_general)
            item['cuotas_pagadas'] = self.count_cuotas_pagadas(cuotas_general)
            item['cuotas_pendientes'] = self.count_cuotas_pendientes(cuotas_general)
            item['cuotas_retrasadas'] = self.count_cuotas_retrasadas(cuotas_general)
            item['cuota_actual'] = self.current_date(cuotas_general)
            item['amount_cuota_retrasadas'] = self.amount_cuotas_retrasadas(cuotas_general)
            item['vat'] = self.find_identity_document(item['partner_id'][0])
            item['total_cuotas'] = self.total_cuotas(cuotas_general)
            
            
            
             'reference_no',  # Referencia
            'partner_id',  # Nombre del socio
            # DNI o CE
            'vehiculo_id',  # Marca de moto y modelo
            'user_id',  # Analista de credito
            # Cobrador
            'periodicidad',  # Tipo de cuenta
            'monto_cuota',  # Monto de cuota
            'fecha_desembolso',  # Fecha de desembolsolox
            'monto_fraccionado',  # Monto de deuda total
            
            """
            if item['reference_no'] == 'CC00158' or item['reference_no'] == 'CC00165' or item['reference_no'] == 'CC00166' or item['reference_no'] == 'CC00167':
                logging.info(str(item))

            new_item = {
                'reference_no' : item['reference_no'],
                'partner_id' : item['partner_id'],
                'vehiculo_id' : item['vehiculo_id'],
                'user_id' : item['user_id'],
                'periodicidad' : item['periodicidad'],
                'monto_cuota' : item['monto_cuota'],
                'fecha_desembolso' : item['fecha_desembolso'],
                'monto_fraccionado' : item['monto_fraccionado'],
                'dias_retraso' : self.quantity_dias_atraso2(cuotas_general),
                'cuotas_pagadas' : self.count_cuotas_pagadas(cuotas_general),
                'cuotas_pendientes' : self.count_cuotas_pendientes(cuotas_general),
                'cuotas_retrasadas' : self.count_cuotas_retrasadas(cuotas_general),
                'cuota_actual' : self.current_date(cuotas_general),
                'amount_cuota_retrasadas' : self.amount_cuotas_retrasadas(cuotas_general),
                'vat' : self.find_identity_document(item['partner_id'][0]),
                'total_cuotas' : self.total_cuotas(cuotas_general)
            }

            last_list.append(new_item)

        return last_list

    def find_identity_document(self, partner_id):
        dni = request.env['res.partner'].search(
            [('id', '=', partner_id)]).read(['vat'])

        try:
            document = dni[0].get('vat')
        except:
            document = ""

        return document

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

    def quantity_dias_atraso2(self, item):
        index = 0
        amount_last = 0
        for data in item:
            if data['state'].strip() == 'retrasado':
                try:
                    # extract amount_day
                    # print('resta : ' + str(item[index + 1]['fecha_cronograma']) + ' - ' + str(data['fecha_cronograma']))
                    amount = item[index + 1]['fecha_cronograma'] - data['fecha_cronograma']
                    amount_last += int(str(amount).split(' ')[0])
                except:
                    amount = date.today() - data['fecha_cronograma']
                    amount_last += int(str(amount).split(' ')[0])

            index += 1

        return amount_last

    def count_cuotas_pagadas(self, list):
        quanty = 0
        for cuota in list:
            if cuota['state'].strip() == 'pagado':
                quanty = quanty + 1
        return quanty

    def count_cuotas_pendientes(self, list):
        quanty = 0
        for cuota in list:
            if cuota['state'].strip() == 'pendiente':
                quanty = quanty + 1
        return quanty

    def count_cuotas_retrasadas(self, list):
        quanty = 0
        for cuota in list:
            if cuota['state'].strip() == 'retrasado':
                quanty = quanty + 1
        return quanty

    def amount_cuotas_retrasadas(self, list):
        quanty = 0.0
        for cuota in list:
            if cuota['state'].strip() == 'retrasado':
                quanty = quanty + cuota['monto']
        return quanty

    def current_date(self, list):
        retrasado = True
        index = 0
        index_retrasado = 0

        try:
            while retrasado:
                if list[index]['state'] == 'pendiente':
                    retrasado = False
                    index_retrasado = index

                index += 1

            current_cuota = list[index_retrasado - 1]['name']
        except:
            current_cuota = ""

        return current_cuota

    def total_cuotas(self, list):
        return len(list)
