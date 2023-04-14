# -*- coding: utf-8 -*-
import requests
from odoo import http
from odoo.http import request
from werkzeug.exceptions import NotFound


def validate(data):
    if not data:
        return ""
    else:
        return data


class ResPartnerAddons(http.Controller):
    @http.route('/api/ecommerce/category', type='json', auth='none')
    def category(self, db, login, password):
        request.session.authenticate(db, login, password)
        data = request.env['product.category'] \
            .search(
            [['id', '>', 0]]) \
            .read(['id', 'name'])
        try:
            for value in data[0]:
                data[0][value] = validate(data[0][value])
            return data
        except:
            raise NotFound()

    @http.route('/api/ecommerce/productbycategory', type='json', auth='none')
    def productbycategory(self, db, login, password, category):
        request.session.authenticate(db, login, password)
        products = request.env['product.template'] \
            .search(
            [['categ_id', '=', category['id']]]) \
            .read(['id', 'name', 'list_price'])

        return products

    @http.route('/api/ecommerce/createsale', type='json', auth='none')
    def createsale(self, db, login, password, order):
        request.session.authenticate(db, login, password)
        res_partner = http.request.env['res.partner'].search(
            [['vat', '=', order['document_client'] ]]) \
            .read(['id'])

        sale = http.request.env['sale.order'].sudo().create({
            'partner_id': res_partner[0]['id'],
        })

        for product in order['products']:
            http.request.env['sale.order.line'].sudo().create({
                'order_id': sale['id'],
                'product_id': product['product_id'],
                'price_unit': product['price_unit'],
                'product_uom_qty': product['product_uom_qty']
            })

        result = {
            'message' : 'Order was send successfully'
        }
        return result

    @http.route('/api/ecommerce/sales', type='json', auth='none')
    def sales(self, db, login, password, client):
        request.session.authenticate(db, login, password)

        res_partner = http.request.env['res.partner'].search(
            [['vat', '=', client['document_client'] ]]) \
            .read(['id'])

        sales = http.request.env['sale.order'].search([['partner_id','=',res_partner[0]['id']]]).\
            read(['id', 'partner_id'])

        result = []
        for sale in sales:
            sale_order_line = http.request.env['sale.order.line'].search([['order_id', '=', sale['id']]]). \
            read(['id', 'price_unit', 'product_id', 'product_uom_qty'])

            item = {
                'order': sale,
                'products': sale_order_line
            }
            result.append(item)

        return result
