from odoo import http
from odoo.http import request
import requests
from datetime import date
from werkzeug.exceptions import NotFound

import logging

def validateField(data):
    if not data:
        return ""
    else:
        return data

def replaceRaw(data):
    for value in data[0]:
        data[0][value] = validateField(data[0][value])
    return data

class Cobranza(http.Controller):

    @http.route('/api/comercial/planpagos',type ='json' ,auth='none')
    def planpagos(self,db,login,password,client):
        request.session.authenticate(db, login, password)
        try:
            fleet_vehicle = request.env['fleet.vehicle'].search([['driver_id', '=', client['id']]]) \
                .read(['id',
                       'model_id',
                       'license_plate',
                       'driver_id',
                       'color',
                       'x_motor_sn',
                       'model_year',
                       ])

            fleet_vehicle = replaceRaw(fleet_vehicle)

            comercial_cuentas = request.env['adt.comercial.cuentas'].search([['partner_id', '=', client['id']]]) \
                .read(['id',
                       'fecha_cierre',
                       'user_id'
                       ])

            cuenta_id = comercial_cuentas[0]['id']
            comercial_cuotas = request.env['adt.comercial.cuotas'].search([['cuenta_id', '=', cuenta_id]]) \
                .read(['id',
                       'name', 'monto', 'saldo', 'fecha_cronograma', 'state'])

            data = {
                "fleet_vehicle" : fleet_vehicle[0],
                "comercial_cuentas" : comercial_cuentas[0],
                "comercial_cuotas" : comercial_cuotas
            }

            return data
        except:
            raise NotFound()

    @http.route('/detalle', type='json', auth='none')
    def get_nuevo(self, db, login, password, id):
        request.session.authenticate(db, login, password)
        contacto = request.env['res.partner'].search([['id', '=', id]])
        val = {
            'name': contacto.name,
            'direccion': contacto.street,
            'mobile': contacto.mobile,
        }
        vehicle_rec = request.env['fleet.vehicle'].search([['driver_id.id', '=', id]])
        fleet = []
        for vehicle in vehicle_rec:
            vals = {
                'modelo': vehicle.model_id.name,
                'matricula': vehicle.license_plate,
                'color': vehicle.color,
                'soat': vehicle.x_soat,
                'Licencia': vehicle.x_licencia_final,
                'tarjeta_propiedad': vehicle.x_fleet_tarjeta_propiedad,
                'chasis': vehicle.vin_sn,
                'numero_celular': vehicle.numero_celular,
                'puerto': vehicle.puerto,
                'detener_gps': vehicle.x_puerto_gps2,
                'reanudar_gps': vehicle.x_puerto_gps1,

            }
            fleet.append(vals)
        cuenta_rec = request.env['adt.comercial.cuentas'].search([['partner_id.id', '=', id]])
        estado2 = cuenta_rec[0].state

        captura_rec = request.env['adt.reporte.cobranza.captura'].search([['partner_id.id', '=', id]])
        dias = []
        data = []
        for captura in captura_rec:
            capturados = {
                'dias_retraso': captura.dias_retraso,
                'tipo_pago': captura.periodicidad,
                'state': estado2,
            }
        dias.append(capturados)
        # print(data)
        """vendedor_rec = request.env['adt.reporte.cobranza.pagos.pendientes'].search([['partner_id.id', '=', id]])
        valor2 = {
            'vendedor': vendedor_rec.user_id.name,
        }
        data.append(valor2)
        print(valor2)"""
        cuota_rec = request.env['adt.comercial.cuotas'].search([['cuenta_id.id', '=', cuenta_rec.id]])
        monto_total = 0
        for cuota in cuota_rec:
            cuota_det = {
                'cuota': cuota.name,
                'fecha_cronograma': cuota.fecha_cronograma,
                'estado': cuota.state,
                'monto': cuota.monto,
                'saldo': cuota.saldo,
            }
            data.append(cuota_det)
            if (cuota.state == 'retrasado'):
                monto_total += cuota.monto
        print(monto_total)

        final = {
            'contacto': val,
            'vehiculos': fleet,
            'dias': dias,
            'deudas': data,
        }
        return final

    @http.route('/captura', type='json', auth='none')
    def get_captura(self, db, login, password):
        request.session.authenticate(db, login, password)
        captura_rec = request.env['adt.reporte.cobranza.captura'].search([])
        data = []
        for captura in captura_rec:
            if captura.vehiculo_id.name:
                vals = {
                    'id': captura.id,
                    'deudor_id': captura.partner_id.id,
                    'deudor': captura.partner_id.name,
                    'moto': captura.vehiculo_id.name,
                    'dias_retraso': captura.dias_retraso,
                    'tipo_pago': captura.periodicidad,
                    'monto': captura.monto,
                }
                data.append(vals)
        newlista = []
        for x in data:
            if x not in newlista:
                newlista.append(x)
        print(newlista)
        capturas = {'status': 200, 'response': newlista, 'message': 'Success'}
        return capturas

    @http.route('/traccar', type='json', auth='none')
    def get_prueba(self, db, login, password):
        request.session.authenticate(db, login, password)
        captura_rec = request.env['adt.reporte.cobranza.captura'].search([])
        lista = []
        URL_TRACCAR = 'http://190.238.200.63:8082/api/devices'
        for captura in captura_rec:
            contacto = request.env['res.partner'].search([['id', '=', captura.partner_id.id]])
            data_deudores = {
                'name': contacto.name,
                'mobile': contacto.mobile,
            }
            vehicle_rec = request.env['fleet.vehicle'].search([['driver_id.id', '=', captura.partner_id.id]])
            a = ''
            b = ''
            for vehicle in vehicle_rec:
                a = vehicle.license_plate,
                b = vehicle.model_id.name,
                a = a[0]
                b = b[0]
            datos = {
                'name': data_deudores['name'],
                'uniqueId': a,
                'phone': data_deudores['mobile'],
                'model': b,
            }
            r = requests.get(URL_TRACCAR, json=datos, auth=('rapitash@gmail.com', 'Krishnna17$'))
            post = r.json()
            print(post)
            newlist = [x for x in post if x['contact'] == data_deudores['name'] and x['model'] == b]
            # print(newlist)
        lista.append(newlist)
        return post

    @http.route('/recuperar', type='json', auth='none')
    def get_recuperar(self, db, login, password, id):
        request.session.authenticate(db, login, password)
        captura_rec = request.env['adt.comercial.cuentas'].search([['partner_id.id', '=', id]])
        val = captura_rec['id']

        newlista = []
        for x in captura_rec:
            if x not in newlista:
                newlista.append(x)
        print(newlista)
        for cuenta in newlista:
            cuenta.write({'recuperado': True})
            cuenta.cancelar_cuenta()
        return (val)

    @http.route('/posicion', type='json', auth='none')
    def get_posicion(self, db, login, password, id):
        request.session.authenticate(db, login, password)
        URL_TRACCAR2 = 'http://190.238.200.63:8082/api/positions'
        s = requests.get(URL_TRACCAR2, json="", auth=('rapitash@gmail.com', 'Krishnna17$'))
        posicion = s.json()
        # print(posicion)
        lista = []
        # for pos in posicion:
        # print(pos['id'])
        # if str(pos['id']) == str(id):
        # print(pos['id'])
        newlist = [x for x in posicion if str(x['id']) == str(id)]
        print(newlist)
        return newlist

    @http.route('/filtro', type='json', auth='none')
    def get_filtro(self, db, login, password):
        request.session.authenticate(db, login, password)
        lista = []
        URL_TRACCAR = 'http://190.238.200.63:8082/api/devices'
        vehicle_rec = request.env['fleet.vehicle'].search([])
        a = ''
        b = ''
        for vehicle in vehicle_rec:
            a = vehicle.license_plate,
            b = vehicle.model_id.name,
            a = a[0]
            b = b[0]
            lista.append(a)
        r = requests.get(URL_TRACCAR, json="", auth=('rapitash@gmail.com', 'Krishnna17$'))
        post = r.json()
        gg = []
        for n in post:
            f = n['name'].split()
            for x in lista:
                if f[0] == x:
                    valores = {
                        'celular': n['phone'],
                        'identifier': n['uniqueId'],
                        'estado': n['status'],
                    }
                    gg.append(valores)
        print(gg)
        return gg

    @http.route('/placa', type='json', auth='public')
    def get_placa(self, db, login, password, id):
        request.session.authenticate(db, login, password)
        vehicle_rec = request.env['fleet.vehicle'].search([['license_plate', '=', id]])
        fleet = []
        for vehicle in vehicle_rec:
            vals = {
                'id': vehicle.id,
                'modelo': vehicle.model_id.name,
                'matricula': vehicle.license_plate,
                'conductor': vehicle.driver_id.name,
                'color': vehicle.color,
                'soat': vehicle.x_soat,
                'licencia': vehicle.x_licencia_final,
                'tarjeta_propiedad': vehicle.x_fleet_tarjeta_propiedad,
                'chasis': vehicle.vin_sn,
                'puerto': vehicle.puerto,
                'numero_celular': vehicle.numero_celular,
            }
            fleet.append(vals)
        contacto = request.env['res.partner'].search([['id', '=', vehicle_rec.driver_id.id]])
        val = {
            'name': contacto.name,
            'direccion': contacto.street,
            'mobile': contacto.mobile,
        }
        cuenta_rec = request.env['adt.comercial.cuentas'].search([['partner_id.id', '=', vehicle_rec.driver_id.id]])
        estado2 = cuenta_rec[0].state

        captura_rec = request.env['adt.reporte.cobranza.captura'].search(
            [['partner_id.id', '=', vehicle_rec.driver_id.id]])
        dias = []
        data = []
        for captura in captura_rec:
            capturados = {
                'dias_retraso': captura.dias_retraso,
                'tipo_pago': captura.periodicidad,
                'state': estado2,
            }
        dias.append(capturados)
        cuota_rec = request.env['adt.comercial.cuotas'].search([['cuenta_id.id', '=', cuenta_rec.id]])
        monto_total = 0
        for cuota in cuota_rec:
            cuota_det = {
                'cuota': cuota.name,
                'fecha_cronograma': cuota.fecha_cronograma,
                'estado': cuota.state,
                'monto': cuota.monto,
                'saldo': cuota.saldo,
            }
            data.append(cuota_det)
            if (cuota.state == 'retrasado'):
                monto_total += cuota.monto
        print(monto_total)
        final = {
            'contacto': val,
            'vehiculos': fleet,
            'dias': dias,
            'deudas': data,
        }
        return final

    @http.route('/buscar_placa', type='json', auth='public')
    def get_placa2(self, db, login, password, id):
        request.session.authenticate(db, login, password)
        vehicle_rec = request.env['fleet.vehicle'].search([['license_plate', '=', id]])
        fleet = []
        for vehicle in vehicle_rec:
            vals = {
                'id': vehicle.id,
                'modelo': vehicle.model_id.name,
                'matricula': vehicle.license_plate,
                'conductor': vehicle.driver_id.name,
                'color': vehicle.color,
                'soat': vehicle.x_soat,
                'licencia': vehicle.x_licencia_final,
                'tarjeta_propiedad': vehicle.x_fleet_tarjeta_propiedad,
                'chasis': vehicle.vin_sn,
                'puerto': vehicle.puerto,
                'numero_celular': vehicle.numero_celular,
            }
            fleet.append(vals)
        return fleet

    @http.route('/buscar_placa_total', type='json', auth='public')
    def get_placatotal(self, db, login, password, id):
        request.session.authenticate(db, login, password)

        # Get data fleet
        vehicle_rec = request.env['fleet.vehicle'].search([['license_plate', '=', id]])
        fleet = []
        for vehicle in vehicle_rec:
            data = {
                'id': vehicle.id,
                'modelo': vehicle.model_id.name,
                'matricula': vehicle.license_plate,
                'conductor': vehicle.driver_id.name,
                'color': vehicle.color,
                'soat': vehicle.x_soat,
                'licencia': vehicle.x_licencia_final,
                'tarjeta_propiedad': vehicle.x_fleet_tarjeta_propiedad,
                'chasis': vehicle.vin_sn,
                'puerto': vehicle.puerto,
                'numero_celular': vehicle.numero_celular,
            }
            fleet.append(data)

        # Get data Contact
        contact = request.env['res.partner'].search([['id', '=', vehicle_rec.driver_id.id]])
        val = {
            'name': contact.name,
            'direccion': contact.street,
            'mobile': contact.mobile,
        }

        # Get dataa ADT Comercial
        cuenta_rec = request.env['adt.comercial.cuentas'].search([['partner_id.id', '=', vehicle_rec.driver_id.id]])
        data = []

        cuota_rec = request.env['adt.comercial.cuotas'].search([['cuenta_id.id', '=', cuenta_rec.id]])
        monto_total = 0
        for cuota in cuota_rec:
            cuota_det = {
                'cuota': cuota.name,
                'fecha_cronograma': cuota.fecha_cronograma,
                'estado': cuota.state,
                'monto': cuota.monto,
                'saldo': cuota.saldo,
            }
            data.append(cuota_det)
            if (cuota.state == 'retrasado'):
                monto_total += cuota.monto
        print(monto_total)

        # Get data Traccar
        lista = []
        URL_TRACCAR = 'http://190.238.200.63:8082/api/devices'
        listVehicle = requests.get(URL_TRACCAR, json="", auth=('rapitash@gmail.com', 'Krishnna17$'))

        dataTraccar = {
            'groupId': '',
            'name': '',
            'status': '',
            'lastUpdate': ''
        }

        for vehicleTraccar in listVehicle.json():
            logging.info(" traccar : " + vehicleTraccar["name"])
            if vehicleTraccar != False:
                placa = vehicleTraccar["name"].split(" / ")[0].replace("-", "")
                if placa == id:
                    dataTraccar = {
                        'groupId': vehicleTraccar['groupId'],
                        'name': vehicleTraccar['name'],
                        'status': vehicleTraccar['status'],
                        'lastUpdate': vehicleTraccar['lastUpdate']
                    }

        final = {
            'contacto': val,
            'vehiculos': fleet,
            'deudas': data,
            'traccar': dataTraccar
        }
        return final

    @http.route('/api/fleetList', type='json', auth='public')
    def fleetList(self, db, login, password, id):
        request.session.authenticate(db, login, password)
        listVehicle = request.env['fleet.vehicle'].search([('license_plate', 'ilike', id)]).read([
            'id',
            'model_id',
            'license_plate',
            'driver_id',
        ])
        return listVehicle

    @http.route('/api/report', type='json', auth='public')
    def report1(self, db, login, password, id):
        request.session.authenticate(db, login, password)

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
