from odoo import http
from odoo.http import request
import requests


class Cobranza(http.Controller):
    @http.route('/detalle', type='json', auth='none')
    def get_nuevo(self, db, login, password,id):
        request.session.authenticate(db, login, password)
        contacto = request.env['res.partner'].search([['id', '=',id]])
        val = {
            'name': contacto.name,
            'direccion': contacto.street,
            'mobile': contacto.mobile,
        }
        #print(val)
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
            #print(fleet)
        cuenta_rec = request.env['adt.comercial.cuentas'].search([['partner_id.id', '=', id]])
        estado2=cuenta_rec[0].state

        captura_rec = request.env['adt.reporte.cobranza.captura'].search([['partner_id.id', '=', id]])
        dias=[]
        data = []
        for captura in captura_rec:
            capturados = {
                'dias_retraso': captura.dias_retraso,
                'tipo_pago': captura.periodicidad,
                'state':estado2,
            }
        dias.append(capturados)
        #print(data)
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
            if (cuota.state== 'retrasado'):
                monto_total += cuota.monto
        print(monto_total)

        final = {
            'contacto': val,
            'vehiculos': fleet,
            'dias':dias,
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
        URL_TRACCAR = 'http://190.232.26.249:8082/api/devices'
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
            #print(newlist)
        lista.append(newlist)
        return post

    @http.route('/recuperar', type='json', auth='none')
    def get_recuperar(self, db, login, password,id):
        request.session.authenticate(db, login, password)
        captura_rec = request.env['adt.comercial.cuentas'].search([['partner_id.id', '=', id]])
        val= captura_rec['id']

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
    def get_posicion(self, db, login, password,id):
        request.session.authenticate(db, login, password)
        URL_TRACCAR2 = 'http://190.232.26.249:8082/api/positions'
        s = requests.get(URL_TRACCAR2, json="", auth=('rapitash@gmail.com', 'Krishnna17$'))
        posicion = s.json()
        #print(posicion)
        lista =[]
        #for pos in posicion:
            #print(pos['id'])
            #if str(pos['id']) == str(id):
                #print(pos['id'])
        newlist = [x for x in posicion if str(x['id']) == str(id)]
        print(newlist)
        return newlist

    @http.route('/filtro', type='json', auth='none')
    def get_filtro(self, db, login, password):
        request.session.authenticate(db, login, password)
        lista = []
        URL_TRACCAR = 'http://190.232.26.249:8082/api/devices'
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
        gg=[]
        for n in post:
            f = n['name'].split()
            for x in lista:
                if f[0]==x:
                    valores={
                        'celular':n['phone'],
                        'identifier':n['uniqueId'],
                        'estado':n['status'],
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
                'puerto':vehicle.puerto,
                'numero_celular':vehicle.numero_celular,
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

        captura_rec = request.env['adt.reporte.cobranza.captura'].search([['partner_id.id', '=', vehicle_rec.driver_id.id]])
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
        final = {
            'contacto': val,
            'vehiculos': fleet,
            'deudas': data,
        }
        return final