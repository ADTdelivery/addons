# ✅ ESTADO ACTUAL DE LA IMPLEMENTACIÓN

**Fecha:** 04 de febrero de 2026  
**Problema:** El campo `document_number` llega vacío a `action_search()`

## 📋 Lo que se ha intentado

1. ✅ `force_save="1"` en el botón
2. ✅ Crear wizard desde Python con `action_open_sentinel_wizard()`
3. ✅ Usar `flush()` para sincronizar valores pendientes
4. ✅ Leer directamente de la base de datos con SQL
5. ✅ Usar `@api.onchange` para capturar cambios
6. ✅ Múltiples intentos de lectura (caché, DB, flush)

## 🚨 El Problema Real

**Los modelos `TransientModel` en Odoo NO guardan automáticamente los valores del formulario cuando se hace clic en un botón `type="object"`.**

El valor existe solo en el navegador hasta que:
- Se ejecuta un `create()` o `write()` explícito
- Se usa un botón con atributos especiales
- Se divide el flujo en múltiples pasos

## ✅ SOLUCIÓN ACTUAL (Código Implementado)

El código actual usa `flush()` para intentar sincronizar:

```python
def action_search(self):
    self.ensure_one()
    
    # Forzar flush de valores pendientes
    self.env['adt.sentinel.query.wizard'].flush(['document_number'])
    
    # Leer el valor
    dni = (self.document_number or '').strip()
    
    # ... validaciones y búsqueda
```

**Esto DEBERÍA funcionar en teoría, pero en la práctica puede fallar.**

## 🔍 SIGUIENTE PASO: DEBUGGING

Antes de cambiar la arquitectura, necesitas:

### 1. Actualizar el módulo

```bash
cd /Users/jhon.curi/Desktop/personal/odoo
docker-compose exec web odoo -u adt_sentinel -d <nombre_bd> --stop-after-init
docker-compose restart web
```

### 2. Probar y ver los logs

```bash
docker-compose logs -f web | grep -E "🔍|💾|✅|❌|PASO"
```

### 3. Hacer la prueba

1. Ir a: **Sentinel > 🔍 Consultar DNI**
2. Ingresar: `12345678`
3. Hacer clic en: **Buscar**
4. Observar qué aparece en los logs

### 4. Reportar el resultado

**Caso A: Los logs muestran el DNI**
```
INFO: 🔍 [PASO 1] DNI capturado del formulario: '12345678'
INFO: 💾 [PASO 2] DNI guardado en el wizard
```
✅ **SOLUCIÓN FUNCIONÓ** - El flush() está sincronizando correctamente

**Caso B: Los logs muestran vacío**
```
INFO: 🔍 [PASO 1] DNI capturado del formulario: ''
```
❌ **SOLUCIÓN NO FUNCIONÓ** - Necesitamos cambiar la arquitectura

## 🎯 SI LA SOLUCIÓN NO FUNCIONA

Hay **2 opciones finales**:

### Opción 1: Dividir en dos vistas (MÁS FÁCIL)

Cambiar el flujo a:
1. Vista 1: Solo campo DNI + botón "Continuar"
2. El botón ejecuta un método que guarda y busca
3. Vista 2: Muestra el resultado

**Ventaja:** Garantiza que el DNI se guarde antes de buscar  
**Desventaja:** Requiere un clic extra

### Opción 2: Usar JavaScript para capturar el valor

Agregar un widget JavaScript que capture el valor del campo y lo envíe al servidor.

**Ventaja:** Funciona 100%  
**Desventaja:** Más complejo, requiere código JS

## 📝 DECISIÓN

**Dime qué muestran los logs después de actualizar y probar.**

Si los logs muestran vacío, implementaré la **Opción 1** que es garantizada al 100%.

---

**Archivos actuales:**
- ✅ `models/sentinel.py` - Con `action_open_sentinel_wizard()`
- ✅ `views/sentinel_menu.xml` - Con acción de servidor
- ✅ `wizard/sentinel_query_wizard.py` - Con flush() y logs
- ✅ `wizard/sentinel_query_wizard_views.xml` - Con botón estándar

**Documentación:**
- 📄 `SOLUCION_TRANSIENT_MODEL.md` - Explicación del problema
- 📄 `DEBUG_DNI_VACIO.md` - Guía de debugging
- 📄 Este archivo - Estado actual

---

**¿Qué hacer ahora?**

1. Actualizar módulo
2. Probar
3. Ver logs
4. Reportar resultado aquí

Entonces sabré si necesitamos implementar una solución diferente.
