# ADT Sentinel - API Documentation

## Métodos Públicos del Modelo

### `adt.sentinel.report`

#### `search_current_report(document_number)`

Busca un reporte vigente para el DNI especificado.

**Parámetros:**
- `document_number` (str): DNI de 8 dígitos

**Retorna:**
- `recordset`: Reporte vigente o recordset vacío

**Ejemplo:**
```python
report = self.env['adt.sentinel.report'].search_current_report('12345678')
if report:
    print(f"Reporte encontrado: {report.query_date}")
else:
    print("No existe reporte vigente")
```

---

#### `get_report_history(document_number)`

Obtiene el histórico completo de reportes para un DNI.

**Parámetros:**
- `document_number` (str): DNI a buscar

**Retorna:**
- `recordset`: Todos los reportes ordenados por fecha descendente

**Ejemplo:**
```python
history = self.env['adt.sentinel.report'].get_report_history('12345678')
for report in history:
    print(f"{report.query_date} - {report.state}")
```

---

#### `action_view_image()`

Abre el reporte en vista de formulario.

**Retorna:**
- `dict`: Action para abrir formulario

**Ejemplo:**
```python
report = self.env['adt.sentinel.report'].browse(1)
return report.action_view_image()
```

---

#### `action_view_history()`

Muestra el histórico completo del DNI.

**Retorna:**
- `dict`: Action para abrir lista de reportes

---

## Métodos del Wizard

### `adt.sentinel.query.wizard`

#### `action_search()`

Busca reporte vigente por DNI.

**Retorna:**
- `dict`: Action para recargar wizard con resultado

---

#### `action_upload_report()`

Sube nuevo reporte después de validaciones.

**Retorna:**
- `dict`: Action para abrir reporte creado

**Excepciones:**
- `UserError`: Si falta imagen o existe duplicado

---

## Campos Computados

### `query_month`
- **Tipo:** Integer
- **Stored:** True
- **Depends:** query_date
- **Descripción:** Mes de vigencia (1-12)

### `query_year`
- **Tipo:** Integer
- **Stored:** True
- **Depends:** query_date
- **Descripción:** Año de vigencia

### `state`
- **Tipo:** Selection
- **Stored:** True
- **Depends:** query_month, query_year
- **Valores:** 'vigente' | 'vencido'
- **Descripción:** Estado calculado automáticamente

### `is_current_month`
- **Tipo:** Boolean
- **Searchable:** True
- **Depends:** query_month, query_year
- **Descripción:** True si pertenece al mes actual

---

## Constraints

### SQL Constraints

```python
_sql_constraints = [
    ('unique_document_month',
     'unique(document_number, query_month, query_year)',
     'Ya existe un reporte vigente para este DNI')
]
```

### Python Constraints

```python
@api.constrains('document_number')
def _check_document_number(self):
    # DNI debe ser exactamente 8 dígitos numéricos
```

---

## Integraciones

### Con `res.users`

Campo: `query_user_id` (Many2one)
- Relación con usuarios de Odoo
- Readonly después de creación
- Usado para trazabilidad

### Con `mail.thread`

Herencia: No (pero compatible con chatter)
- Campos: message_follower_ids, message_ids
- Permite seguimiento y mensajes

---

## Búsquedas Optimizadas

### Índices Creados

```sql
CREATE INDEX ON adt_sentinel_report (document_number);
CREATE INDEX ON adt_sentinel_report (query_date);
CREATE INDEX ON adt_sentinel_report (query_month, query_year);
```

### Búsqueda Recomendada

```python
# CORRECTO (usa índices)
reports = self.env['adt.sentinel.report'].search([
    ('document_number', '=', dni),
    ('is_current_month', '=', True)
])

# INCORRECTO (lento)
reports = self.env['adt.sentinel.report'].search([
    ('query_date', '>=', start_of_month),
    ('query_date', '<=', end_of_month)
])
```

---

## Permisos

### Reglas de Acceso

```csv
# Usuarios normales
perm_read=1, perm_write=1, perm_create=1, perm_unlink=0

# Administradores
perm_read=1, perm_write=1, perm_create=1, perm_unlink=0
```

**Nota:** Nadie puede eliminar (método unlink() bloqueado)

---

## Ejemplos de Uso

### Crear reporte manualmente (no recomendado)

```python
# Mejor usar el wizard, pero si es necesario:
report = self.env['adt.sentinel.report'].create({
    'document_number': '12345678',
    'report_image': image_base64,
    'query_date': fields.Date.today(),
    # query_user_id se asigna automáticamente
})
```

### Buscar reportes vigentes

```python
vigentes = self.env['adt.sentinel.report'].search([
    ('state', '=', 'vigente')
])
```

### Obtener reportes del usuario actual

```python
mis_reportes = self.env['adt.sentinel.report'].search([
    ('query_user_id', '=', self.env.user.id)
])
```

### Contar consultas del mes

```python
count = self.env['adt.sentinel.report'].search_count([
    ('is_current_month', '=', True)
])
print(f"Consultas este mes: {count}")
```

---

## Webhooks / API Externa

Para integración externa, crear controller:

```python
from odoo import http
from odoo.http import request

class SentinelAPI(http.Controller):
    
    @http.route('/api/sentinel/check/<dni>', type='json', auth='user')
    def check_dni(self, dni):
        report = request.env['adt.sentinel.report'].search_current_report(dni)
        if report:
            return {
                'exists': True,
                'date': report.query_date.isoformat(),
                'user': report.query_user_id.name,
                'state': report.state
            }
        return {'exists': False}
```

---

## Eventos y Triggers

### Al crear reporte

```python
@api.model_create_multi
def create(self, vals_list):
    # Custom logic here
    records = super().create(vals_list)
    # Post-create actions
    return records
```

### Al cambiar mes (automático)

Los campos computed se recalculan automáticamente al acceder a los registros.

---

## Migraciones

### Actualizar módulo

```bash
# Actualizar código
./odoo-bin -c odoo.conf -u adt_sentinel

# Forzar actualización
./odoo-bin -c odoo.conf -u adt_sentinel --stop-after-init
```

---

## Debugging

### Activar logs

```python
import logging
_logger = logging.getLogger(__name__)

_logger.info("Buscando DNI: %s", dni)
_logger.warning("Reporte duplicado detectado")
_logger.error("Error al crear reporte: %s", str(e))
```

### Ver queries SQL

```bash
# En odoo.conf
log_level = debug_sql
```

---

**Versión:** 1.0.0  
**Última actualización:** 04/02/2026
