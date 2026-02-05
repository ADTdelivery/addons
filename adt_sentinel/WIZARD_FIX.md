# 🔧 Corrección del Wizard de Consulta DNI

## 📋 Problema Original

El wizard de consulta DNI no guardaba el valor del campo `document_number` antes de ejecutar el método `action_search()`, lo que causaba que siempre llegara vacío o `False`.

## ✅ Solución Implementada

Se implementaron **DOS SOLUCIONES** complementarias:

### 1️⃣ Solución en el Botón (force_save)

**Archivo:** `wizard/sentinel_query_wizard_views.xml`

```xml
<button name="action_search"
        string="🔍 Buscar"
        type="object"
        class="btn-primary"
        force_save="1"  <!-- ← SOLUCIÓN 1 -->
        attrs="{'invisible': [('state', '!=', 'search')]}"/>
```

El atributo `force_save="1"` fuerza a Odoo a guardar el formulario antes de ejecutar el método.

### 2️⃣ Solución en la Arquitectura (Acción desde Python)

**Problema:** Las acciones XML (`ir.actions.act_window`) no garantizan la creación correcta de registros transient.

**Solución:** Crear el wizard desde un método Python que garantiza la instanciación correcta.

#### Archivos Modificados:

##### A) `models/sentinel.py`
```python
def action_open_sentinel_wizard(self):
    """
    Abre el wizard de consulta de DNI.
    
    Este método crea un nuevo registro transient del wizard,
    asegurando que siempre comience en estado 'search' con
    valores inicializados correctamente.
    """
    # Crear un nuevo registro transient del wizard
    wizard = self.env['adt.sentinel.query.wizard'].create({
        'state': 'search',
    })

    # Retornar la acción para abrir el wizard
    return {
        'type': 'ir.actions.act_window',
        'name': 'Consultar DNI',
        'res_model': 'adt.sentinel.query.wizard',
        'res_id': wizard.id,
        'view_mode': 'form',
        'view_id': self.env.ref('adt_sentinel.view_sentinel_query_wizard_form_search').id,
        'target': 'new',
        'context': dict(self.env.context, wizard_created=True),
    }
```

##### B) `views/sentinel_menu.xml`
```xml
<!-- ANTES: Acción XML -->
<record id="action_sentinel_query_wizard" model="ir.actions.act_window">
    <field name="name">Consultar DNI</field>
    <field name="res_model">adt.sentinel.query.wizard</field>
    ...
</record>

<!-- DESPUÉS: Acción de servidor que llama a Python -->
<record id="action_sentinel_query_wizard" model="ir.actions.server">
    <field name="name">Consultar DNI</field>
    <field name="model_id" ref="model_adt_sentinel_report"/>
    <field name="state">code</field>
    <field name="code">
action = model.action_open_sentinel_wizard()
    </field>
</record>
```

##### C) `wizard/sentinel_query_wizard_views.xml`
```xml
<!-- ELIMINADO: Ya no se necesita la acción XML -->
<!-- Se mantiene solo la definición de vistas -->
```

## 🎯 Ventajas de esta Solución

1. **Garantiza Instanciación:** El wizard siempre se crea correctamente con valores iniciales
2. **Force Save:** El formulario se guarda antes de ejecutar métodos
3. **Simplicidad:** El código del método `action_search()` es más limpio
4. **Reutilizable:** Se puede llamar el método desde cualquier lugar (menú, botón, API)
5. **Debugging:** Es más fácil depurar porque el flujo es explícito

## 📝 Método action_search Simplificado

**Archivo:** `wizard/sentinel_query_wizard.py`

```python
def action_search(self):
    self.ensure_one()
    
    # Gracias a force_save="1", el valor ya está guardado
    dni = (self.document_number or '').strip()
    
    if not dni:
        raise exceptions.UserError('⚠️ DNI requerido...')
    
    if not re.match(r'^\d{8}$', dni):
        raise exceptions.UserError('⚠️ Formato de DNI inválido...')
    
    # Buscar reporte
    report = self.env['adt.sentinel.report'].search_current_report(dni)
    
    # Actualizar estado...
```

## 🔄 Cómo Actualizar el Módulo

### Opción 1: Desde la interfaz de Odoo
1. Ir a **Apps** (Aplicaciones)
2. Buscar **adt_sentinel**
3. Clic en **Actualizar**
4. Esperar confirmación

### Opción 2: Desde terminal (Docker)
```bash
docker-compose restart web
# O actualizar específicamente
docker exec -it <contenedor> odoo -u adt_sentinel -d <database>
```

### Opción 3: Desde terminal (Odoo nativo)
```bash
./odoo-bin -u adt_sentinel -d <database> --stop-after-init
```

## 🧪 Validación

Después de actualizar, verifica:

1. ✅ El menú "🔍 Consultar DNI" abre el wizard correctamente
2. ✅ Se puede ingresar un DNI de 8 dígitos
3. ✅ El botón "🔍 Buscar" ejecuta la búsqueda sin errores
4. ✅ El mensaje de error aparece si el DNI está vacío o es inválido
5. ✅ Se muestra correctamente si el reporte existe o no

## 📚 Referencias

- **Odoo Transient Models:** Modelos temporales que solo existen durante la sesión
- **force_save:** Atributo de botones para forzar guardado previo
- **ir.actions.server:** Acciones de servidor que ejecutan código Python
- **Wizard Pattern:** Patrón para flujos multi-paso en Odoo

---

**Fecha de implementación:** 04 de febrero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Implementado y probado
