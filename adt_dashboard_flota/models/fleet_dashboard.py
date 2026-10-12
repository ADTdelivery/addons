# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Valores que se suelen cargar en license_plate cuando la placa aún no existe.
PLATE_PLACEHOLDERS = {
    'S/P', 'SP', 'S/N', 'SN', 'SIN PLACA', 'EN TRAMITE', 'EN TRÁMITE',
    'TRAMITE', 'TRÁMITE', 'PENDIENTE', 'NULL', 'NONE', 'N/A', 'NA', '-', '--',
}

PLATE_STATUS_LABELS = {
    'lista': 'Placa lista',
    'tramite': 'En trámite',
    'sin_placa': 'Sin placa',
}


def plate_is_ready(plate):
    """Una placa está lista si tiene un valor real (no placeholder) con al menos un dígito."""
    value = (plate or '').strip().upper()
    if not value or value in PLATE_PLACEHOLDERS:
        return False
    return any(ch.isdigit() for ch in value)


def normalize_label(value, default):
    value = ' '.join(str(value or '').split()).upper()
    return value or default


class AdtFleetDashboard(models.AbstractModel):
    _name = 'adt.fleet.dashboard'
    _description = 'Dashboard de Flota (stock y placas)'

    @api.model
    def _get_plate_procedures(self, vehicle_ids):
        """Trámite de placa por vehículo (adt_tramite_placa)."""
        Tramite = self.env['adt.tramite.placa']
        if not Tramite.check_access_rights('read', raise_exception=False):
            return {}
        state_labels = dict(Tramite._fields['state']._description_selection(self.env))
        result = {}
        for rec in Tramite.search_read([('vehicle_id', 'in', vehicle_ids)], ['vehicle_id', 'state', 'num_placa']):
            result[rec['vehicle_id'][0]] = {
                'state': rec['state'],
                'state_label': state_labels.get(rec['state'], ''),
                'num_plate': rec['num_placa'],
            }
        return result

    @api.model
    def _compute_plate_status(self, plate, procedure):
        if plate_is_ready(plate):
            return 'lista'
        if procedure:
            if procedure['state'] in ('finalizado', 'historial') and plate_is_ready(procedure['num_plate']):
                return 'lista'
            if procedure['state'] in ('en_tramite', 'observado'):
                return 'tramite'
        return 'sin_placa'

    @api.model
    def _vehicle_rows(self, domain=None):
        """Vehículos activos con estado de placa calculado (base del dashboard y de la API)."""
        Vehicle = self.env['fleet.vehicle']
        vehicle_fields = Vehicle._fields
        read_fields = [
            'name', 'license_plate', 'vin_sn', 'model_id', 'brand_id', 'model_year',
            'color', 'state_id', 'driver_id', 'vehicle_type', 'acquisition_date',
        ]
        # Respaldo con datos de facturación (adt_facturacion_v1) cuando el vehículo no tiene año/color/motor.
        optional = [f for f in ('x_facturacion_ano_modelo', 'x_facturacion_color', 'x_motor_sn',
                                'x_facturacion_motor') if f in vehicle_fields]
        read_fields += optional

        rows = Vehicle.search_read(domain or [], read_fields, order='id')
        procedures = self._get_plate_procedures([r['id'] for r in rows])
        type_labels = dict(Vehicle.fields_get(['vehicle_type'])['vehicle_type'].get('selection') or [])
        state_sequences = {
            s.id: s.sequence for s in self.env['fleet.vehicle.state'].search([])
        }

        vehicles = []
        for r in rows:
            procedure = procedures.get(r['id'])
            year = r['model_year'] or r.get('x_facturacion_ano_modelo') or ''
            color = r['color'] or r.get('x_facturacion_color') or ''
            plate = (r['license_plate'] or '').strip()
            if not plate_is_ready(plate) and procedure and plate_is_ready(procedure['num_plate']) \
                    and procedure['state'] in ('finalizado', 'historial'):
                plate = procedure['num_plate'].strip()
            status = self._compute_plate_status(r['license_plate'], procedure)
            vehicles.append({
                'id': r['id'],
                'name': r['name'] or '',
                'plate': plate if status == 'lista' else (r['license_plate'] or '').strip(),
                'plate_status': status,
                'vin': r['vin_sn'] or '',
                'motor': r.get('x_motor_sn') or r.get('x_facturacion_motor') or '',
                'brand': r['brand_id'][1] if r['brand_id'] else 'SIN MARCA',
                'model': r['model_id'][1] if r['model_id'] else 'SIN MODELO',
                'model_id': r['model_id'][0] if r['model_id'] else False,
                'year': normalize_label(year, 'SIN AÑO'),
                'color': normalize_label(color, 'SIN COLOR'),
                'state': r['state_id'][1] if r['state_id'] else 'Sin estado',
                'state_seq': state_sequences.get(r['state_id'][0], 999) if r['state_id'] else 999,
                'vehicle_type': r['vehicle_type'] or '',
                'vehicle_type_label': type_labels.get(r['vehicle_type'], 'Sin tipo'),
                'has_owner': bool(r['driver_id']),
                'owner': r['driver_id'][1] if r['driver_id'] else '',
                'procedure_state': procedure['state_label'] if procedure else '',
                'acquisition_date': fields.Date.to_string(r['acquisition_date']) if r['acquisition_date'] else '',
            })
        return vehicles

    @api.model
    def get_dashboard_data(self):
        return {
            'vehicles': self._vehicle_rows(),
            'plate_status_labels': PLATE_STATUS_LABELS,
            'has_plate_procedures': True,
            'generated_at': fields.Datetime.to_string(fields.Datetime.now()),
        }
