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
        self.updateDataAccount()
        list_deudores = self.generate_new_list(deudores)
        sheet = workbook.add_worksheet("Data")
        bold = workbook.add_format({"bold": True})


        sheet.write(0, 1, "Referencia")
        sheet.write(0, 2, "Socio")
        sheet.write(0, 3, "DNI o CE")
        sheet.write(0, 4, "Marca y Modelo")
        sheet.write(0, 5, "Analista de credito")
        sheet.write(0, 6, "Vendedor")
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

        sheet.write(0, 17, "Telefono")
        sheet.write(0, 18, "Celular")

        row = 1

        for deudor in list_deudores:
            # dict --> tuple
            # #valores
            sheet.write(row, 1, deudor.get('reference_no'))
            sheet.write(row, 2, deudor.get('partner_id'))
            sheet.write(row, 3, deudor.get('vat'))  # DNI o CE
            sheet.write(row, 4, deudor.get('vehiculo_id')[1])
            sheet.write(row, 4, deudor.get('vehiculo_id')[1])

            sheet.write(row, 5, self.findAsesor(deudor.get('asesor')))

            sheet.write(row, 6, deudor.get('user_id')[1])
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

            sheet.write(row, 17, deudor.get('phone'))
            sheet.write(row, 18, deudor.get('mobile'))


            row += 1


    def generate_new_list(self,cuentas):

        list = []

        for item in cuentas:
            data = request.env['adt.comercial.cuentas'].search(
                [('state', '!=', 'cancelado'),('id','=',item.id)], order="id asc").read([
                'reference_no',  # Referencia
                'partner_id',  # Nombre del socio
                # DNI o CE
                'vehiculo_id',  # Marca de moto y modelo
                'asesor',  # Analista de credito
                'user_id',# Cobrador
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



        last_list = []

        for item in list:

            cuotas_general = request.env['adt.comercial.cuotas'].search(
                [('cuenta_id', '=', item['id'])]).read([
                'fecha_cronograma', 'state', 'name', 'monto'])

            res_partner = request.env['res.partner'].search(
                [('id', '=', item['partner_id'][0])]).read([
                'name', 'apellido_paterno', 'apellido_materno' , 'phone' ,'mobile'  ])

            #print(str(res_partner))
            #print(str(self.valuePartner(res_partner)))

            new_item = {
                'reference_no' : item['reference_no'],
                #'partner_id' : item['partner_id'],
                'partner_id': self.valuePartner(res_partner) ,
                'phone' : self.valuePartnerPhone(res_partner),
                'mobile' : self.valuePartnerMobile(res_partner),
                'vehiculo_id' : item['vehiculo_id'],
                'user_id' : item['user_id'],
                'asesor' : item['asesor'],
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



    def findAsesor(self,index):

        asesor = ''
        if index == '1':
            asesor = 'Rogers Héctor Vizarreta Puchuri'
        if index == '2':
            asesor = 'Luis Bullón Aponte'
        if index == '3':
            asesor = 'Jaico Cervera Luna'

        data = asesor
        return asesor

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

            #current_cuota = list[index_retrasado - 1]['name']
            current_cuota = "Cuota "+str(index_retrasado+1)
        except:
            current_cuota = ""

        #self.current_cuota = "Cuota "+str(index_retrasado)
        return current_cuota

    def total_cuotas(self, list):
        return len(list)

    def validateString(self,data):
        if type(data) == bool:
            return ""
        else:
            return data

    def valuePartner(self,data):
        nombre= ""

        if len(data) > 0:
            nombre = data[0]['name'] + self.validateString(data[0]['apellido_paterno']) + self.validateString(data[0]['apellido_materno'])
        else:
            nombre = "sin valor"

        return nombre

    def valuePartnerPhone(self,data):
        if len(data) > 0:
            phone = data[0]['phone']
        else:
            phone = "-"

        return phone

    def valuePartnerMobile(self,data):
        if len(data) > 0:
            phone = data[0]['mobile']
        else:
            phone = "-"

        return phone

    def updateDataAccount(self):
        cuotas_general = request.env['adt.comercial.cuotas'].search(
            [('id', '>', 0)]).read(['id','fecha_cronograma', 'state', 'name', 'monto'])

        for cuota in cuotas_general:
            account_payment = request.env['account.payment'].search([('cuota_id', '=', cuota.get('id'))]).read([
                'move_id',
            ])
            print(account_payment)
            if len(account_payment) > 0:
                account_move = request.env['account.move'].search(
                    [('id', '=', account_payment[0]['move_id'][0])]).read([
                    'date',
                    'ref'
                ])
                cuota['real_date'] = str(account_move[0]['date'])
                cuota['numero_operacion'] = str(account_move[0]['ref'])

            else:
                cuota['real_date'] = ""
                cuota['numero_operacion'] = ""