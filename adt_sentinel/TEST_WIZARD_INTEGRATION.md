# 🧪 Pruebas de Integración - Wizard Sentinel

**Módulo:** adt_sentinel  
**Fecha:** 04 de febrero de 2026  
**Estado:** ✅ Listo para probar

---

## 📋 Pre-requisitos

1. **Módulo actualizado:**
   ```bash
   # Opción 1: Reiniciar Odoo (Docker)
   docker-compose restart web
   
   # Opción 2: Actualizar módulo específico
   docker exec -it <contenedor> odoo -u adt_sentinel -d <database>
   ```

2. **Permisos de usuario:**
   - Usuario debe tener permisos de lectura/escritura en `adt.sentinel.report`
   - Verificar en: Configuración > Usuarios y Compañías > Usuarios

---

## 🎯 Casos de Prueba

### ✅ Caso 1: Abrir el Wizard desde el Menú

**Pasos:**
1. Ir a **Sentinel > 🔍 Consultar DNI**
2. Se debe abrir un popup con el formulario del wizard
3. El campo "Número de Documento (DNI)" debe estar visible y editable
4. Estado inicial debe ser "search"

**Resultado Esperado:**
- ✅ El wizard se abre sin errores
- ✅ El formulario muestra el título "🔍 Consultar Reporte Sentinel"
- ✅ El botón "Buscar" está visible
- ✅ No hay mensajes de error en la consola

---

### ✅ Caso 2: Validación de DNI Vacío

**Pasos:**
1. Abrir el wizard
2. **NO** ingresar ningún DNI
3. Hacer clic en "🔍 Buscar"

**Resultado Esperado:**
- ❌ Error: "⚠️ DNI requerido - Debe ingresar el número de DNI antes de buscar."
- ✅ El wizard no se cierra
- ✅ El usuario puede corregir e intentar nuevamente

---

### ✅ Caso 3: Validación de Formato de DNI

**Datos de Prueba:**

| DNI Ingresado | Resultado Esperado | Mensaje |
|---------------|-------------------|---------|
| `12345` | ❌ Error | "DNI debe tener 8 dígitos" |
| `123456789` | ❌ Error | "DNI debe tener 8 dígitos" |
| `abcd1234` | ❌ Error | "DNI debe tener 8 dígitos numéricos" |
| `1234 5678` | ❌ Error | "DNI debe tener 8 dígitos numéricos" |
| `12345678` | ✅ Válido | Continúa con la búsqueda |

**Pasos:**
1. Abrir el wizard
2. Ingresar cada DNI de prueba
3. Hacer clic en "🔍 Buscar"

**Resultado Esperado:**
- ❌ Errores claros para formatos inválidos
- ✅ Búsqueda exitosa para formato válido

---

### ✅ Caso 4: DNI Sin Reporte Existente

**Pasos:**
1. Abrir el wizard
2. Ingresar un DNI válido que NO tenga reportes (ej: `99999999`)
3. Hacer clic en "🔍Buscar"

**Resultado Esperado:**
- ✅ El wizard cambia al estado "not_found"
- ✅ Se muestra el título "📸 Subir Nuevo Reporte"
- ✅ Se muestra el mensaje de costo (S/ 10.00)
- ✅ El campo DNI se muestra como readonly
- ✅ Aparece el campo para subir imagen
- ✅ Aparece el botón "💾 Subir y Guardar (S/ 10.00)"

---

### ✅ Caso 5: DNI Con Reporte Existente

**Prerequisito:** Debe existir al menos un reporte del mes actual

**Pasos:**
1. Abrir el wizard
2. Ingresar un DNI que SÍ tenga un reporte vigente
3. Hacer clic en "🔍 Buscar"

**Resultado Esperado:**
- ✅ El wizard cambia al estado "found"
- ✅ Se muestra el título "✅ Reporte Encontrado"
- ✅ Se muestra el mensaje de vigencia en verde
- ✅ Se muestra la imagen del reporte en la pestaña "📄 Vista Previa"
- ✅ Se muestra la información del reporte en la pestaña "📊 Detalles"
- ✅ Los botones "Ver Reporte Completo" y "Cerrar" están visibles

---

### ✅ Caso 6: Subir Nuevo Reporte

**Prerequisito:** Tener una imagen de prueba (PNG, JPG, o PDF)

**Pasos:**
1. Buscar un DNI sin reporte existente
2. En la pantalla "Subir Nuevo Reporte", hacer clic en "Cargar archivo"
3. Seleccionar una imagen válida
4. Opcionalmente agregar observaciones
5. Hacer clic en "💾 Subir y Guardar (S/ 10.00)"
6. Confirmar en el diálogo

**Resultado Esperado:**
- ✅ La imagen se carga correctamente
- ✅ Se muestra una vista previa de la imagen
- ✅ El wizard se cierra después de guardar
- ✅ Se crea un nuevo registro en "Sentinel > 📋 Todos los Reportes"
- ✅ El registro tiene:
  - DNI correcto
  - Fecha actual
  - Usuario actual
  - Estado "vigente"
  - Imagen adjunta

---

### ✅ Caso 7: Prevención de Duplicados

**Pasos:**
1. Subir un reporte para un DNI (siguiendo Caso 6)
2. Inmediatamente intentar buscar el mismo DNI nuevamente
3. Hacer clic en "🔍 Buscar"

**Resultado Esperado:**
- ✅ El sistema encuentra el reporte recién creado
- ✅ Se muestra en estado "found"
- ✅ NO permite subir otro reporte para el mismo DNI/mes

---

### ✅ Caso 8: Verificación de Logs

**Pasos:**
1. Realizar una búsqueda
2. Revisar los logs de Odoo

**Resultado Esperado (en logs):**
```
INFO adt_sentinel.wizard.sentinel_query_wizard: 🔍 Buscando DNI: 12345678
INFO adt_sentinel.wizard.sentinel_query_wizard: ✅ Reporte encontrado: ID=X, Fecha=2026-02-04
```
O:
```
INFO adt_sentinel.wizard.sentinel_query_wizard: 🔍 Buscando DNI: 99999999
INFO adt_sentinel.wizard.sentinel_query_wizard: ❌ No se encontró reporte vigente para DNI: 99999999
```

---

## 🐛 Checklist de Debugging

Si algo no funciona, verificar:

### 1. **El campo document_number llega vacío**
- [ ] ¿El botón tiene `force_save="1"`?
- [ ] ¿El wizard se crea con `action_open_sentinel_wizard()`?
- [ ] Revisar logs: ¿Qué valor llega a `action_search()`?

### 2. **El wizard no se abre**
- [ ] ¿El módulo se actualizó correctamente?
- [ ] ¿La acción `action_sentinel_query_wizard` es de tipo `ir.actions.server`?
- [ ] ¿Existe el método `action_open_sentinel_wizard()` en `sentinel.py`?

### 3. **Error al subir imagen**
- [ ] ¿El campo tiene `widget="binary"`?
- [ ] ¿El campo `report_image` es `required=True`?
- [ ] ¿El usuario tiene permisos de escritura?

### 4. **No se previenen duplicados**
- [ ] Verificar constraint `_check_unique_dni_per_month` en el modelo
- [ ] Revisar método `search_current_report()`

---

## 📊 Registro de Pruebas

| Caso | Fecha | Tester | Resultado | Notas |
|------|-------|--------|-----------|-------|
| Caso 1 | | | ⬜ Pendiente | |
| Caso 2 | | | ⬜ Pendiente | |
| Caso 3 | | | ⬜ Pendiente | |
| Caso 4 | | | ⬜ Pendiente | |
| Caso 5 | | | ⬜ Pendiente | |
| Caso 6 | | | ⬜ Pendiente | |
| Caso 7 | | | ⬜ Pendiente | |
| Caso 8 | | | ⬜ Pendiente | |

**Leyenda:**
- ✅ Aprobado
- ❌ Fallido
- ⚠️ Con observaciones
- ⬜ Pendiente

---

## 🔧 Comandos Útiles

### Ver logs en tiempo real (Docker)
```bash
docker-compose logs -f web
```

### Ver logs de un contenedor específico
```bash
docker logs -f <nombre_contenedor>
```

### Actualizar módulo desde línea de comandos
```bash
docker exec -it <contenedor> odoo -u adt_sentinel -d <database> --log-level=debug
```

### Limpiar caché de Odoo
```bash
# Detener Odoo
docker-compose stop web

# Limpiar archivos de sesión
docker-compose run --rm web rm -rf /var/lib/odoo/sessions/*

# Reiniciar
docker-compose start web
```

---

## 📞 Soporte

Si encuentras problemas:

1. **Revisar documentación:**
   - `WIZARD_FIX.md` - Detalles técnicos de la solución
   - `RESUMEN_CAMBIOS_WIZARD.md` - Resumen ejecutivo de cambios
   - `API.md` - Documentación de endpoints (si aplica)

2. **Ejecutar script de verificación:**
   ```bash
   bash verificar_wizard_fix.sh
   ```

3. **Revisar logs de Odoo** con nivel DEBUG

---

**Última actualización:** 04 de febrero de 2026  
**Versión:** 1.0  
**Estado:** ✅ Listo para Testing
