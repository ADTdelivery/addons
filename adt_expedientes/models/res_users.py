# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """
    Extensión de res.users para invalidar tokens automáticamente
    cuando un usuario es desactivado o eliminado.

    CRÍTICO PARA SEGURIDAD:
    - Cuando un admin desactiva un usuario → tokens revocados INMEDIATAMENTE
    - Cuando un usuario es eliminado → tokens revocados antes de borrar
    - Próximo request del app → 401 Unauthorized → logout automático
    """
    _inherit = 'res.users'

    def write(self, vals):
        """
        Override write para detectar desactivación de usuarios
        y revocar automáticamente todos sus tokens activos.
        """
        # Detectar si se está desactivando el usuario
        if 'active' in vals and not vals['active']:
            # Revocar tokens ANTES de desactivar
            for user in self:
                _logger.info(f'🔒 User {user.login} (ID: {user.id}) being deactivated. Revoking all mobile tokens.')
                count = self.env['adt.mobile.token'].sudo().revoke_all_user_tokens(
                    user.id,
                    reason='user_disabled'
                )
                _logger.info(f'✅ Revoked {count} token(s) for user {user.login}')

        return super(ResUsers, self).write(vals)

    def unlink(self):
        """
        Override unlink para revocar tokens antes de eliminar usuario.
        """
        for user in self:
            _logger.info(f'🔒 User {user.login} (ID: {user.id}) being deleted. Revoking all mobile tokens.')
            count = self.env['adt.mobile.token'].sudo().revoke_all_user_tokens(
                user.id,
                reason='user_deleted'
            )
            _logger.info(f'✅ Revoked {count} token(s) for deleted user {user.login}')

        return super(ResUsers, self).unlink()

    def action_revoke_mobile_tokens(self):
        """
        Acción manual para revocar tokens desde la interfaz de Odoo.
        Puede ser llamada desde un botón en la vista de usuario.
        """
        self.ensure_one()
        count = self.env['adt.mobile.token'].sudo().revoke_all_user_tokens(
            self.id,
            reason='manual'
        )

        _logger.info(f'🔒 Manually revoked {count} token(s) for user {self.login}')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tokens Revocados',
                'message': f'Se revocaron {count} token(s) móvil(es) del usuario {self.name}.',
                'type': 'success',
                'sticky': False,
            }
        }
