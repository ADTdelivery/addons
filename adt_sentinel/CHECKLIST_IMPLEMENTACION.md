# ✅ CHECKLIST DE IMPLEMENTACIÓN - Wizard Sentinel

**Fecha de inicio:** _______________  
**Completado por:** _______________  
**Base de datos:** _______________

---

## 📋 FASE 1: Verificación Pre-Actualización

- [ ] Los archivos modificados existen:
  - [ ] `models/sentinel.py`
  - [ ] `views/sentinel_menu.xml`
  - [ ] `wizard/sentinel_query_wizard.py`
  - [ ] `wizard/sentinel_query_wizard_views.xml`

- [ ] Scripts creados:
  - [ ] `actualizar_modulo.sh`
  - [ ] `verificar_wizard_fix.sh`

- [ ] Documentación creada:
  - [ ] `RESUMEN_CAMBIOS_WIZARD.md`
  - [ ] `WIZARD_FIX.md`
  - [ ] `TEST_WIZARD_INTEGRATION.md`
  - [ ] `GUIA_ACTUALIZACION.md`
  - [ ] `QUICK_START.txt`

---

## 🚀 FASE 2: Actualización del Módulo

- [ ] **Paso 1:** Hacer backup de la base de datos
  ```bash
  # Comando usado:
  # __________________________________________________
  ```

- [ ] **Paso 2:** Elegir método de actualización
  - [ ] Método 1: Script automático
  - [ ] Método 2: Docker manual
  - [ ] Método 3: Interfaz web

- [ ] **Paso 3:** Ejecutar actualización
  ```bash
  # Comando usado:
  # __________________________________________________
  
  # Resultado:
  # [ ] ✅ Éxito
  # [ ] ❌ Error (describir): ____________________
  ```

- [ ] **Paso 4:** Reiniciar servicio web
  ```bash
  # Comando usado:
  # __________________________________________________
  ```

- [ ] **Paso 5:** Verificar logs (no debe haber errores)
  ```bash
  # Comando usado:
  # docker-compose logs web | tail -50
  
  # ¿Hay errores?
  # [ ] No
  # [ ] Sí (describir): ____________________
  ```

---

## 🔍 FASE 3: Verificación Automática

- [ ] Ejecutar script de verificación:
  ```bash
  cd /Users/jhon.curi/Desktop/personal/odoo/addons/adt_sentinel
  chmod +x verificar_wizard_fix.sh
  ./verificar_wizard_fix.sh
  ```

- [ ] Resultado de verificación:
  - [ ] ✅ Método action_open_sentinel_wizard() encontrado
  - [ ] ✅ Acción de servidor configurada
  - [ ] ✅ force_save="1" aplicado al botón
  - [ ] ✅ Acción XML antigua eliminada correctamente
  - [ ] ✅ VERIFICACIÓN EXITOSA

---

## 🧪 FASE 4: Pruebas Funcionales

### Test 1: Apertura del Wizard
- [ ] Ir a: **Sentinel > 🔍 Consultar DNI**
- [ ] El wizard se abre correctamente
- [ ] El campo DNI está visible y editable
- [ ] El título es "🔍 Consultar Reporte Sentinel"
- [ ] El botón "Buscar" está visible

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 2: Validación de DNI Vacío
- [ ] Dejar el campo DNI vacío
- [ ] Hacer clic en "🔍 Buscar"
- [ ] Aparece error: "⚠️ DNI requerido"
- [ ] El wizard no se cierra
- [ ] Puedo intentar nuevamente

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 3: Validación de Formato

**DNI: "12345" (5 dígitos)**
- [ ] Ingresar DNI
- [ ] Hacer clic en "🔍 Buscar"
- [ ] Aparece error: "⚠️ Formato de DNI inválido"

**DNI: "123456789" (9 dígitos)**
- [ ] Ingresar DNI
- [ ] Hacer clic en "🔍 Buscar"
- [ ] Aparece error: "⚠️ Formato de DNI inválido"

**DNI: "abcd1234" (con letras)**
- [ ] Ingresar DNI
- [ ] Hacer clic en "🔍 Buscar"
- [ ] Aparece error: "⚠️ Formato de DNI inválido"

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 4: Búsqueda - DNI Sin Reporte

**DNI de prueba:** 99999999

- [ ] Ingresar DNI
- [ ] Hacer clic en "🔍 Buscar"
- [ ] El wizard cambia a estado "not_found"
- [ ] Aparece título: "📸 Subir Nuevo Reporte"
- [ ] Aparece mensaje de costo (S/ 10.00)
- [ ] El campo DNI está readonly
- [ ] Aparece campo para subir imagen
- [ ] Aparece botón "💾 Subir y Guardar"

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 5: Búsqueda - DNI Con Reporte

**DNI de prueba:** ________________ (debe tener reporte vigente)

- [ ] Ingresar DNI
- [ ] Hacer clic en "🔍 Buscar"
- [ ] El wizard cambia a estado "found"
- [ ] Aparece título: "✅ Reporte Encontrado"
- [ ] Aparece mensaje de vigencia en verde
- [ ] Se muestra la imagen del reporte
- [ ] Se muestran los detalles del reporte
- [ ] Botones "Ver Reporte Completo" y "Cerrar" visibles

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 6: Subir Nuevo Reporte

**Prerequisito:** Imagen de prueba disponible

- [ ] Buscar DNI sin reporte (99999999)
- [ ] En pantalla "Subir Nuevo Reporte"
- [ ] Hacer clic en "Cargar archivo"
- [ ] Seleccionar imagen válida
- [ ] La imagen se carga correctamente
- [ ] Se muestra vista previa de la imagen
- [ ] Agregar observaciones (opcional): ________________
- [ ] Hacer clic en "💾 Subir y Guardar"
- [ ] Confirmar en el diálogo
- [ ] El wizard se cierra
- [ ] Ir a: **Sentinel > 📋 Todos los Reportes**
- [ ] El nuevo reporte aparece en la lista
- [ ] Verificar datos del reporte:
  - [ ] DNI correcto
  - [ ] Fecha actual
  - [ ] Usuario actual
  - [ ] Estado "vigente"
  - [ ] Imagen adjunta

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 7: Prevención de Duplicados

- [ ] Intentar buscar el DNI del Test 6 nuevamente
- [ ] Hacer clic en "🔍 Buscar"
- [ ] El sistema encuentra el reporte recién creado
- [ ] NO permite subir otro reporte

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

### Test 8: Verificación de Logs

- [ ] Abrir logs en tiempo real:
  ```bash
  docker-compose logs -f web
  ```

- [ ] Hacer una búsqueda de DNI
- [ ] Los logs muestran:
  - [ ] "🔍 Buscando DNI: XXXXXXXX"
  - [ ] "✅ Reporte encontrado: ID=X, Fecha=..."
  - [ ] O: "❌ No se encontró reporte vigente..."

**Resultado:** [ ] ✅ APROBADO  [ ] ❌ FALLIDO

---

## 📊 RESUMEN DE RESULTADOS

**Total de Tests:** 8

| Test | Resultado |
|------|-----------|
| Test 1: Apertura | [ ] ✅  [ ] ❌ |
| Test 2: Validación Vacío | [ ] ✅  [ ] ❌ |
| Test 3: Validación Formato | [ ] ✅  [ ] ❌ |
| Test 4: DNI Sin Reporte | [ ] ✅  [ ] ❌ |
| Test 5: DNI Con Reporte | [ ] ✅  [ ] ❌ |
| Test 6: Subir Reporte | [ ] ✅  [ ] ❌ |
| Test 7: Duplicados | [ ] ✅  [ ] ❌ |
| Test 8: Logs | [ ] ✅  [ ] ❌ |

**Tests Aprobados:** ____ / 8  
**Tests Fallidos:** ____ / 8

---

## ✅ FASE 5: Validación Final

- [ ] Todos los tests pasaron (8/8)
- [ ] No hay errores en los logs
- [ ] El módulo está funcionando en producción
- [ ] La documentación está completa
- [ ] El equipo está informado de los cambios

---

## 📝 NOTAS Y OBSERVACIONES

```
Fecha: _______________

Observaciones:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

Problemas encontrados:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

Soluciones aplicadas:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
```

---

## 🎉 APROBACIÓN FINAL

- [ ] **Implementación completa y funcional**
- [ ] **Documentación revisada y archivada**
- [ ] **Equipo notificado**

**Firmado por:** _______________________  
**Fecha:** _______________________  
**Hora:** _______________________

---

**Estado Final:** 

[ ] ✅ **APROBADO** - Listo para producción  
[ ] ⚠️ **CON OBSERVACIONES** - Requiere ajustes menores  
[ ] ❌ **NO APROBADO** - Requiere revisión completa

---

*Documento generado por GitHub Copilot - 04 de febrero de 2026*
