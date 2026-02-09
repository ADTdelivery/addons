from odoo import models, fields


class AdtExpedienteRechazoWizard(models.TransientModel):
    _name = 'adt.expediente.rechazo.wizard'
    _description = 'Rechazo de expediente'

    expediente_id = fields.Many2one('adt.expediente', required=True)
    fecha_rechazo = fields.Date(default=fields.Date.today, required=True)
    motivo_rechazo = fields.Text(required=True)

    def action_confirmar(self):
        self.expediente_id.write({
            'state': 'rechazado',
            'fecha_rechazo': self.fecha_rechazo,
            'motivo_rechazo': self.motivo_rechazo,
        })

        # Enviar notificación Firebase
        self.expediente_id._send_firebase_notification(
            title='Expediente rechazado',
            body=f'Tu expediente ha sido rechazado. Motivo: {self.motivo_rechazo[:100]}',
            action_type='rechazado'
        )
