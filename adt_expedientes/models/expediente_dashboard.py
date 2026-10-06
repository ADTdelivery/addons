from odoo import api, fields, models

# Documentos que se revisan en el expediente: campo de estado -> nombre para mostrar.
DOCUMENTOS = {
    'estado_foto_dni': 'DNI',
    'estado_foto_ce': 'Carné de extranjería',
    'estado_foto_pasaporte': 'Pasaporte',
    'estado_foto_licencia': 'Licencia',
    'estado_foto_vivienda': 'Foto de vivienda',
    'estado_direccion': 'Dirección',
    'estado_foto_ubicacion': 'Ubicación',
    'estado_foto_fachada': 'Fachada del domicilio',
    'estado_foto_contrato': 'Contrato de alquiler',
    'estado_foto_recibo': 'Recibo de servicios',
    'estado_foto_ingresos': 'Sustento de ingresos',
    'estado_foto_boletas': 'Boletas / contratos',
    'estado_foto_estado_cuenta': 'Estado de cuenta',
    'estado_foto_lugar_trabajo': 'Lugar de trabajo',
    'estado_foto_lugar_negocio': 'Lugar del negocio',
    'estado_foto_moto': 'Foto en la moto',
    'estado_foto_soat': 'SOAT',
    'estado_foto_tarjeta': 'Tarjeta de propiedad',
    'estado_foto_sentinel': 'Sentinel',
    'estado_referencias': 'Referencias',
}

# Etapas del flujo, en orden. "grupo" resume el estado para los indicadores.
ETAPAS = [
    ('por_revisar', 'en_proceso'),
    ('incompleto_expediente', 'en_proceso'),
    ('incompleto_fase_final', 'en_proceso'),
    ('aprobado_sin_desembolso', 'aprobado'),
    ('completo', 'aprobado'),
    ('rechazado', 'rechazado'),
]


class AdtExpedienteDashboard(models.AbstractModel):
    """Datos del Dashboard de Expedientes (JS: adt_expedientes_dashboard)."""
    _name = 'adt.expediente.dashboard'
    _description = 'Dashboard de expedientes'

    @api.model
    def get_dashboard_data(self):
        Expediente = self.env['adt.expediente']
        campos_doc = [f for f in DOCUMENTOS if f in Expediente._fields]
        registros = Expediente.search_read(
            [], ['state', 'cliente_id', 'asesora_id', 'fecha', 'create_date', 'fecha_rechazo', 'motivo_rechazo',
                 'vehiculo'] + campos_doc, order='fecha desc, id desc')
        estados = dict(Expediente._fields['state']._description_selection(self.env))
        vehiculos = dict(Expediente._fields['vehiculo']._description_selection(self.env)) if 'vehiculo' in Expediente._fields else {}

        expedientes = []
        for r in registros:
            fecha = r['fecha'] or (r['create_date'] and r['create_date'].date())
            expedientes.append({
                'id': r['id'],
                'cliente': r['cliente_id'][1] if r['cliente_id'] else '',
                'asesora_id': r['asesora_id'][0] if r['asesora_id'] else 0,
                'asesora': r['asesora_id'][1] if r['asesora_id'] else 'Sin asesora',
                'estado': r['state'] or 'por_revisar',
                'fecha': fields.Date.to_string(fecha) if fecha else None,
                'fecha_rechazo': fields.Date.to_string(r['fecha_rechazo']) if r['fecha_rechazo'] else None,
                'motivo_rechazo': (r['motivo_rechazo'] or '').strip(),
                'vehiculo': vehiculos.get(r['vehiculo'], 'Sin vehículo'),
                'observados': [DOCUMENTOS[f] for f in campos_doc if r[f] == 'rechazado'],
            })
        return {
            'hoy': fields.Date.to_string(fields.Date.context_today(self)),
            'estados': [{'key': k, 'label': estados.get(k, k), 'grupo': g} for k, g in ETAPAS],
            'expedientes': expedientes,
        }
