# -*- coding: utf-8 -*-
from odoo import models, fields, api
import secrets
from datetime import datetime, timedelta


class AdtMobileToken(models.Model):
    _name = 'adt.mobile.token'
    _description = 'ADT Mobile API Token'

    name = fields.Char(string='Description')
    token = fields.Char(string='Token', required=True, index=True, copy=False)
    user_id = fields.Many2one('res.users', string='User', required=True)
    active = fields.Boolean(default=True)
    expiry = fields.Datetime(string='Expiry')

    @api.model
    def generate_token(self, user_id, days_valid=30, description=None):
        token = secrets.token_urlsafe(32)
        expiry_dt = datetime.utcnow() + timedelta(days=days_valid)
        # store as string in UTC
        expiry_str = fields.Datetime.to_string(expiry_dt)
        rec = self.create({
            'name': description or 'mobile token for %s' % user_id,
            'token': token,
            'user_id': user_id,
            'expiry': expiry_str,
            'active': True,
        })
        return rec

    @api.model
    def validate_token(self, token):
        if not token:
            return None
        rec = self.sudo().search([('token', '=', token), ('active', '=', True)], limit=1)
        if not rec:
            return None
        # compare expiry using odoo fields
        if rec.expiry:
            try:
                now = fields.Datetime.now()
                expiry_dt = fields.Datetime.from_string(rec.expiry)
                if expiry_dt and expiry_dt < now:
                    return None
            except Exception:
                # If parsing fails, be conservative and reject
                return None
        return rec
