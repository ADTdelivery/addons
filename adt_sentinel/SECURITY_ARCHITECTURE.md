# ARQUITECTURA DE SEGURIDAD - ADT SENTINEL

## 🔒 Principios de Diseño

El módulo Sentinel implementa múltiples capas de seguridad para garantizar la integridad de los datos y prevenir uso indebido.

---

## 🛡️ Capas de Protección

### 1. Validación de Entrada (Frontend)

**Ubicación:** `wizard/sentinel_query_wizard.py`

```python
@api.constrains('document_number')
def _check_document_number_format(self):
    """Valida formato del DNI antes de buscar."""
    if not re.match(r'^\d{8}$', dni):
        raise ValidationError(...)
```

**Validaciones:**
- DNI debe ser exactamente 8 dígitos
- Solo caracteres numéricos
- Sin espacios ni caracteres especiales

---

### 2. Constraint de Base de Datos (DB Level)

**Ubicación:** `models/sentinel.py`

```python
_sql_constraints = [
    ('unique_document_month',
     'unique(document_number, query_month, query_year)',
     'Ya existe un reporte vigente...')
]
```

**Garantías:**
- Imposible crear dos reportes para mismo DNI en mismo mes
- Protección incluso si se accede directamente a la BD
- Constraint a nivel PostgreSQL

---

### 3. Validación de Duplicados (Application Level)

**Ubicación:** `wizard/sentinel_query_wizard.py` → `action_upload_report()`

```python
# Doble verificación antes de crear
existing = self.env['adt.sentinel.report'].search_current_report(
    self.document_number
)
if existing:
    raise UserError('Reporte duplicado detectado...')
```

**Previene:**
- Race conditions
- Consultas concurrentes
- Errores de timing

---

### 4. Campos Protegidos (Write Protection)

**Ubicación:** `models/sentinel.py` → `write()`

```python
protected_fields = {
    'document_number', 'report_image', 'image_filename',
    'query_date', 'query_user_id'
}

if any(field in vals for field in protected_fields):
    raise UserError('No se pueden modificar...')
```

**Campos inmutables:**
- DNI del cliente
- Imagen del reporte
- Fecha de consulta
- Usuario que consultó

**Campo editable:**
- `notes` (observaciones)

---

### 5. Eliminación Prohibida (Delete Protection)

**Ubicación:** `models/sentinel.py` → `unlink()`

```python
def unlink(self):
    raise UserError(
        'Los reportes Sentinel NO pueden eliminarse.'
    )
```

**Razones:**
- Trazabilidad completa
- Auditoría
- Cumplimiento legal
- Histórico permanente

---

## 🔐 Control de Acceso (ACL)

### Archivo: `security/ir.model.access.csv`

```csv
access_sentinel_report_user,adt.sentinel.report.user,model_adt_sentinel_report,base.group_user,1,1,1,0
```

**Permisos por grupo:**

| Grupo | Leer | Escribir | Crear | Eliminar |
|-------|------|----------|-------|----------|
| Users | ✅ | ✅* | ✅ | ❌ |
| System | ✅ | ✅* | ✅ | ❌ |

\* Solo campo `notes`

---

## 🕵️ Trazabilidad

### Información Registrada

Cada reporte almacena:

```python
{
    'document_number': '12345678',        # Quién fue consultado
    'query_user_id': res.users(5),        # Quién consultó
    'query_date': '2026-02-04',           # Cuándo consultó
    'query_month': 2,                     # Mes de vigencia
    'query_year': 2026,                   # Año de vigencia
    'state': 'vigente',                   # Estado actual
}
```

### Auditoría Automática

- **Log de creación:** `create_date`, `create_uid`
- **Log de modificación:** `write_date`, `write_uid`
- **Chatter:** Integración con mail tracking
- **Histórico:** Búsqueda por `get_report_history(dni)`

---

## 🚨 Manejo de Errores

### Errores de Usuario (UserError)

1. **Formato DNI inválido**
   ```
   ⚠️ El número de documento debe tener exactamente 8 dígitos.
   ```

2. **Imagen requerida**
   ```
   ⚠️ Debe adjuntar la imagen del reporte Sentinel
   ```

3. **Duplicado detectado**
   ```
   ⚠️ Ya existe un reporte vigente para este DNI
   ```

4. **Modificación prohibida**
   ```
   🚫 No se pueden modificar los datos del reporte
   ```

5. **Eliminación prohibida**
   ```
   🚫 Los reportes NO pueden eliminarse
   ```

### Errores de Sistema (ValidationError)

1. **Constraint violado**
   ```
   IntegrityError: duplicate key value violates unique constraint
   ```
   - Capturado y convertido a mensaje amigable

---

## 🔍 Búsqueda Segura

### Método: `search_current_report()`

```python
@api.model
def search_current_report(self, document_number):
    return self.search([
        ('document_number', '=', document_number),
        ('is_current_month', '=', True)
    ], limit=1)
```

**Características:**
- Solo busca reportes vigentes
- Usa campo computed `is_current_month`
- Límite de 1 resultado (optimización)
- No permite wildcards

---

## 🧪 Testing de Seguridad

### Casos de Prueba Obligatorios

#### Test 1: Constraint de Unicidad
```python
# Intentar crear 2 reportes para mismo DNI/mes
report1 = create({'document_number': '12345678', ...})  # OK
report2 = create({'document_number': '12345678', ...})  # ERROR
# Esperado: IntegrityError
```

#### Test 2: Modificación de Campos Protegidos
```python
report.write({'document_number': '87654321'})  # ERROR
# Esperado: UserError
```

#### Test 3: Eliminación
```python
report.unlink()  # ERROR
# Esperado: UserError
```

#### Test 4: Acceso Concurrente
```python
# 2 usuarios crean reporte simultáneamente
with transaction1:
    create_report('12345678')  # OK
with transaction2:
    create_report('12345678')  # ERROR (constraint)
```

---

## 🔄 Vigencia Automática

### Recálculo de Estado

```python
@api.depends('query_month', 'query_year')
def _compute_state(self):
    today = fields.Date.context_today(self)
    for record in self:
        if record.query_month == today.month and record.query_year == today.year:
            record.state = 'vigente'
        else:
            record.state = 'vencido'
```

**Características:**
- Se ejecuta automáticamente
- No requiere cron jobs
- Basado en fecha del contexto
- Stored en BD para performance

---

## 📊 Métricas de Seguridad

### KPIs de Control

1. **Duplicados prevenidos:** 
   - Contador de intentos bloqueados
   - Ahorro calculado: intentos × S/ 10

2. **Modificaciones rechazadas:**
   - Log de intentos de edición
   - Usuarios que intentaron modificar

3. **Intentos de eliminación:**
   - Registro de quién intentó eliminar
   - Fecha y hora del intento

---

## 🎯 Mejores Prácticas

### Para Desarrolladores

1. **Nunca deshabilitar constraints**
   - Son la última línea de defensa
   
2. **Validar en múltiples capas**
   - Frontend (wizard)
   - Backend (model)
   - Base de datos (constraint)

3. **Usar campos computed stored**
   - Performance en búsquedas
   - Consistencia de datos

4. **Implementar trazabilidad completa**
   - Quién, cuándo, qué

### Para Usuarios

1. **Siempre buscar antes de consultar**
   - Usa el wizard oficial
   
2. **No intentar modificar registros**
   - Solo campo `notes` es editable
   
3. **Reportar intentos de duplicado**
   - Puede indicar capacitación necesaria

---

## 🚀 Actualizaciones Futuras

### Mejoras de Seguridad Planificadas

1. **Rate limiting**
   - Máximo N consultas por usuario por día
   
2. **Alertas automáticas**
   - Notificar supervisor si múltiples intentos de duplicado
   
3. **Exportación encriptada**
   - Reportes exportados con password
   
4. **Auditoría avanzada**
   - Dashboard de uso y violaciones

---

## 📞 Contacto

Para reportar vulnerabilidades de seguridad:
- **Email:** security@adt.com
- **Prioridad:** Alta
- **Confidencialidad:** Garantizada

---

**Última actualización:** 04/02/2026  
**Revisión:** v1.0.0
