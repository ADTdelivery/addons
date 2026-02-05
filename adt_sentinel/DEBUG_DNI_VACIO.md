# 🐛 GUÍA DE DEBUGGING - Problema del DNI Vacío

## Síntomas

Cuando haces clic en "Buscar", el método `action_search()` recibe `self.document_number` vacío o `None`, aunque el usuario ingresó un valor en el formulario.

## Cómo Debuggear

### 1. Activar Logs Detallados

Actualiza el módulo con logs activos:

```bash
docker-compose restart web
docker-compose logs -f web | grep "🔍\|💾\|✅\|❌"
```

### 2. Probar y Observar Logs

1. Abrir wizard
2. Ingresar DNI: `12345678`
3. Hacer clic en "Buscar"
4. Observar los logs:

```
INFO adt_sentinel.wizard: 🔍 [PASO 1] DNI capturado del formulario: '12345678'
INFO adt_sentinel.wizard: 💾 [PASO 2] DNI guardado en el wizard
INFO adt_sentinel.wizard: ✅ [PASO 3] Reporte encontrado: ID=1, Fecha=2026-02-04
```

O si el DNI está vacío:

```
INFO adt_sentinel.wizard: 🔍 [PASO 1] DNI capturado del formulario: ''
```

### 3. Investigar la Tabla

Si el DNI está vacío en el log, verifica la tabla directamente:

```sql
-- Conectar a PostgreSQL
docker-compose exec db psql -U odoo

-- Ver registros del wizard
SELECT id, document_number, state, create_date 
FROM adt_sentinel_query_wizard 
ORDER BY id DESC 
LIMIT 5;
```

### 4. Verificar el Flujo de Creación

Agrega un log en `action_open_sentinel_wizard`:

```python
def action_open_sentinel_wizard(self):
    wizard = self.env['adt.sentinel.query.wizard'].create({
        'state': 'search',
    })
    
    _logger.info("🆕 Wizard creado: ID=%s, document_number='%s'", 
                 wizard.id, wizard.document_number)
    
    return {
        'type': 'ir.actions.act_window',
        ...
    }
```

## Posibles Causas y Soluciones

### Causa 1: El flush() no funciona

**Síntoma:** El log muestra `''` en el PASO 1

**Solución:** Cambiar a enfoque de dos pasos

```python
def action_search(self):
    self.ensure_one()
    
    # Forzar guardado primero
    if hasattr(self, '_cache'):
        # Leer de la caché interna de Odoo
        cached_values = self._cache.get(self.id, {})
        dni = cached_values.get('document_number', '')
        _logger.info("📦 DNI de caché: '%s'", dni)
    
    if not dni:
        dni = (self.document_number or '').strip()
    
    # ... resto
```

### Causa 2: El wizard se crea sin el campo

**Síntoma:** La tabla no tiene el campo `document_number`

**Solución:** Recrear el wizard

```python
def action_open_sentinel_wizard(self):
    wizard = self.env['adt.sentinel.query.wizard'].create({
        'state': 'search',
        'document_number': '',  # Inicializar explícitamente
    })
```

### Causa 3: El campo no se sincroniza desde el formulario

**Síntoma:** El valor existe en el navegador pero no en el servidor

**Solución:** Usar JavaScript para capturar y enviar el valor

Agregar en `sentinel_query_wizard_views.xml`:

```xml
<field name="document_number" 
       on_change="1"
       force_save="1"/>
```

### Causa 4: Problema con TransientModel

**Síntoma:** Ninguna de las soluciones anteriores funciona

**Solución DEFINITIVA:** Cambiar la arquitectura

```python
# Opción A: Usar un campo Many2one al modelo principal
document_number_id = fields.Many2one('res.partner', 'Cliente')

# Opción B: Dos wizards separados
# Wizard 1: Solo captura DNI
# Wizard 2: Muestra resultado

# Opción C: Pasar DNI por contexto desde el menú
```

## 🎯 Prueba Rápida

Agrega este método temporal para testing:

```python
def test_dni_capture(self):
    """Método de prueba para verificar captura de DNI"""
    _logger.info("=" * 50)
    _logger.info("TEST: Captura de DNI")
    _logger.info("self.id = %s", self.id)
    _logger.info("self.document_number = '%s'", self.document_number)
    _logger.info("self._cache = %s", self._cache if hasattr(self, '_cache') else 'N/A')
    
    # Leer directamente de DB
    self.env.cr.execute("SELECT document_number FROM adt_sentinel_query_wizard WHERE id = %s", (self.id,))
    result = self.env.cr.fetchone()
    _logger.info("DB value = '%s'", result[0] if result else 'NULL')
    _logger.info("=" * 50)
    
    return True
```

Llámalo desde un botón temporal:

```xml
<button name="test_dni_capture" string="🧪 Test" type="object"/>
```

## 📝 Reporte de Resultados

Después de probar, completa esto:

```
FECHA: _______________
USUARIO: _______________

1. ¿Qué muestra el log del PASO 1?
   DNI capturado: _______________________

2. ¿Qué hay en la base de datos?
   SELECT document_number: _______________________

3. ¿El test_dni_capture funciona?
   [ ] Sí  [ ] No

4. Observaciones:
   _____________________________________________
   _____________________________________________
```

---

**Siguiente paso:** Según los resultados, aplicar la solución correspondiente.
