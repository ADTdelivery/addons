# 🚨 PROBLEMA CRÍTICO: TransientModel no guarda automáticamente

## El Problema Real

Los modelos `TransientModel` (wizards) en Odoo **NO guardan automáticamente** los campos cuando el usuario escribe en el formulario. El valor solo existe en la interfaz web hasta que se ejecuta un `write()` o `create()`.

Cuando se hace clic en un botón `type="object"`, Odoo **NO guarda automáticamente** los cambios pendientes del formulario antes de ejecutar el método.

## ¿Por qué no funcionan las soluciones anteriores?

1. **`force_save="1"`** - No existe en Odoo estándar
2. **`self.document_number`** - Está vacío porque no se ha guardado
3. **Query SQL directa** - La tabla puede no tener el registro o está vacío
4. **`self.env.cr.commit()`** - Peligroso en wizards, puede causar inconsistencias

## ✅ SOLUCIÓN DEFINITIVA

Hay **3 opciones reales** que funcionan:

---

### OPCIÓN 1: Pasar el DNI como parámetro en el contexto (RECOMENDADO)

Cambiar el botón para que ejecute JavaScript que capture el valor y lo pase al método:

**wizard/sentinel_query_wizard_views.xml:**
```xml
<button name="action_search_with_dni"
        string="🔍 Buscar"
        type="object"
        class="btn-primary"
        context="{'dni_from_form': document_number}"
        attrs="{'invisible': [('state', '!=', 'search')]}"/>
```

**wizard/sentinel_query_wizard.py:**
```python
def action_search_with_dni(self):
    self.ensure_one()
    
    # Leer del contexto
    dni = self._context.get('dni_from_form', '').strip()
    
    if not dni:
        raise exceptions.UserError('⚠️ DNI requerido')
    
    # ... resto del código
```

**PROBLEMA:** El contexto no captura el valor del campo directamente.

---

### OPCIÓN 2: Usar dos pasos con botón de guardado

Agregar un botón que primero guarde:

**wizard/sentinel_query_wizard_views.xml:**
```xml
<button name="action_save_and_search"
        string="🔍 Buscar"
        type="object"
        class="btn-primary"
        attrs="{'invisible': [('state', '!=', 'search')]}"/>
```

**wizard/sentinel_query_wizard.py:**
```python
def action_save_and_search(self):
    self.ensure_one()
    
    # Primero guardar explícitamente
    self.write({'document_number': self.document_number})
    
    # Luego buscar
    return self.action_search()

def action_search(self):
    self.ensure_one()
    dni = (self.document_number or '').strip()
    # ... resto del código
```

**PROBLEMA:** `self.document_number` sigue vacío antes del `write()`.

---

### OPCIÓN 3: Dividir en dos wizards (LA QUE FUNCIONA) ⭐

**Primera Vista: Solo captura DNI**
- Campo DNI con `required="1"`
- Botón "Continuar" que guarda y abre segunda vista

**Segunda Vista: Muestra resultados**
- Recibe DNI como parámetro
- Muestra si existe o permite subir

#### Implementación:

**Paso 1:** Modificar el wizard para tener dos métodos:

```python
class SentinelQueryWizard(models.TransientModel):
    _name = 'adt.sentinel.query.wizard'
    
    document_number = fields.Char(required=True)
    state = fields.Selection([
        ('input', 'Ingreso DNI'),
        ('result', 'Resultado'),
    ], default='input')
    
    def action_continue(self):
        """Guarda el DNI y busca"""
        self.ensure_one()
        
        # Validar formato
        dni = (self.document_number or '').strip()
        if not re.match(r'^\d{8}$', dni):
            raise exceptions.UserError('DNI inválido')
        
        # Guardar el DNI
        self.write({'document_number': dni})
        
        # Buscar reporte
        report = self.env['adt.sentinel.report'].search_current_report(dni)
        
        if report:
            self.write({
                'state': 'result',
                'found_report_id': report.id,
            })
        else:
            self.write({'state': 'result'})
        
        # Reabrir wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adt.sentinel.query.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
```

**Paso 2:** Dos vistas en el XML:

```xml
<form>
    <!-- VISTA 1: Ingreso DNI -->
    <div attrs="{'invisible': [('state', '!=', 'input')]}">
        <group>
            <field name="document_number" required="1"/>
        </group>
        <footer>
            <button name="action_continue" string="Continuar" type="object"/>
        </footer>
    </div>
    
    <!-- VISTA 2: Resultado -->
    <div attrs="{'invisible': [('state', '!=', 'result')]}">
        <!-- Mostrar resultado -->
    </div>
</form>
```

---

## 🎯 MI RECOMENDACIÓN

**USA LA OPCIÓN 3** - Es la única que garantiza que el valor se guarde correctamente.

El flujo sería:
1. Usuario abre wizard → Ve campo DNI
2. Usuario ingresa DNI → Hace clic en "Continuar"
3. El método `action_continue()` valida, guarda con `write()`, y busca
4. El wizard se reabre mostrando el resultado

## 📝 Archivo para modificar

Solo necesitas modificar:
- `wizard/sentinel_query_wizard.py` - Agregar método `action_continue()`
- `wizard/sentinel_query_wizard_views.xml` - Cambiar `action_search` por `action_continue`

---

¿Quieres que implemente la OPCIÓN 3?
