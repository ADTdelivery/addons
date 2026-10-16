# -*- coding: utf-8 -*-
"""Tokens de sesión de la app de gerencia.

Solo se guarda el hash (SHA-256) del token: si alguien lee la base no puede
usarlo. El token en claro se entrega una sola vez, al iniciar sesión.
"""
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

DIAS_VALIDEZ = 30
GRUPO = 'adt_gerencia_api.group_gerencia_api'


def _hash(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


class AdtGerenciaToken(models.Model):
    _name = 'adt.gerencia.token'
    _description = 'Token de la app de gerencia'
    _order = 'create_date desc'

    name = fields.Char(string='Dispositivo', readonly=True)
    user_id = fields.Many2one('res.users', string='Usuario', required=True, readonly=True,
                              ondelete='cascade', index=True)
    token_hash = fields.Char(required=True, readonly=True, index=True, copy=False)
    expira = fields.Datetime(string='Expira', required=True, readonly=True)
    revocado = fields.Boolean(string='Revocado', readonly=True, index=True)
    ultimo_uso = fields.Datetime(string='Último uso', readonly=True)
    ip = fields.Char(string='IP', readonly=True)
    app_version = fields.Char(string='Versión de la app', readonly=True)

    _sql_constraints = [('token_hash_unique', 'unique(token_hash)', 'Token duplicado.')]

    @api.model
    def emitir(self, user, dispositivo='', ip='', app_version=''):
        """Crea un token para el usuario y lo devuelve en claro (única vez)."""
        token = secrets.token_urlsafe(32)
        rec = self.sudo().create({
            'name': (dispositivo or _('Dispositivo sin nombre'))[:120],
            'user_id': user.id,
            'token_hash': _hash(token),
            'expira': fields.Datetime.now() + timedelta(days=DIAS_VALIDEZ),
            'ip': ip,
            'app_version': (app_version or '')[:40],
        })
        return token, rec

    @api.model
    def validar(self, token):
        """Usuario dueño del token si es válido, está vigente y sigue teniendo permiso; si no, None."""
        if not token:
            return None
        rec = self.sudo().search([('token_hash', '=', _hash(token)), ('revocado', '=', False)], limit=1)
        if not rec or rec.expira < fields.Datetime.now():
            return None
        user = rec.user_id
        # El permiso se revisa en cada llamada: si se le quita el grupo, el token deja de servir.
        if not user.active or not user.has_group(GRUPO):
            return None
        rec.write({'ultimo_uso': fields.Datetime.now()})
        return user

    @api.model
    def revocar(self, token):
        rec = self.sudo().search([('token_hash', '=', _hash(token))], limit=1)
        rec.write({'revocado': True})
        return bool(rec)

    def action_revocar(self):
        self.write({'revocado': True})

    @api.autovacuum
    def _gc_tokens(self):
        """Borra los tokens vencidos o revocados hace más de 30 días."""
        limite = fields.Datetime.now() - timedelta(days=30)
        self.sudo().search(['|', ('expira', '<', limite), '&', ('revocado', '=', True), ('write_date', '<', limite)]).unlink()
