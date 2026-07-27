# -*- coding: utf-8 -*-
"""
Catálogo de horarios seleccionables para las notificaciones de mantenimiento.

En vez de escribir manualmente "09:00,14:00,19:00", el usuario elige estas
horas desde un selector de tags (ver adt.mantenimiento.regla.horario_ids).
Se precargan cada 30 minutos (00:00 a 23:30, ver data/); si se necesita
mayor granularidad (ej. 09:15) se puede agregar un registro nuevo desde
Configuración sin tocar código.
"""
from odoo import fields, models


class AdtMantenimientoHorarioSlot(models.Model):
    _name = 'adt.mantenimiento.horario.slot'
    _description = 'Horario seleccionable para notificaciones de mantenimiento'
    _order = 'hora'

    name = fields.Char(string='Hora', required=True, help='Formato HH:MM, ej: 09:00')
    hora = fields.Float(
        string='Hora (decimal)', required=True,
        help='Usada para ordenar el selector, ej: 9.5 equivale a 09:30.',
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('horario_slot_name_uniq', 'unique(name)', 'Ya existe un horario con ese valor.'),
    ]
