# 🚀 PASOS RÁPIDOS PARA ACTUALIZAR

## ⚡ PROBLEMAS RESUELTOS

✅ **Problema 1**: El botón "Buscar" no hacía nada
✅ **Problema 2**: No aparecía el campo para subir imagen  
✅ **Problema 3**: Error "mandatory field is not set"

## ⚡ OPCIÓN MÁS RÁPIDA (Desde Odoo)

### Paso 1: Abrir Apps
- Inicia sesión en Odoo
- Haz clic en el menú **"Apps"**

### Paso 2: Buscar el módulo
- Quita el filtro "Apps" (para ver todos los módulos)
- En el buscador, escribe: **adt_sentinel**

### Paso 3: Actualizar
- Haz clic en el botón **"Actualizar"** (icono ⟳)
- Confirma cuando pregunte
- Espera a que termine (puede tardar 10-30 segundos)

### Paso 4: Limpiar caché
- Presiona **Ctrl + Shift + R** en tu navegador
- O cierra y abre el navegador completamente

### Paso 5: Probar
- Ve a **Sentinel > 🔍 Consultar DNI**
- Ingresa un DNI de 8 dígitos
- Haz clic en **"🔍 Buscar"**

---

## ✅ ¿QUÉ DEBERÍAS VER?

### Si el DNI NO tiene reporte del mes:
```
┌─────────────────────────────────────┐
│ 📸 Subir Nuevo Reporte             │
├─────────────────────────────────────┤
│                                     │
│ [Mensaje informativo]               │
│ [Advertencia de costo S/ 10.00]    │
│                                     │
│ 📋 Información del Reporte          │
│ DNI: 12345678                       │
│ Observaciones: [______]             │
│                                     │
│ 📎 Adjuntar Imagen del Reporte ⭐   │
│ [📁 Seleccionar Archivo]            │  ← AQUÍ ESTÁ!
│                                     │
│ 🖼️ Vista Previa                    │
│ (aparece después de seleccionar)    │
│                                     │
│ [💾 Subir y Guardar] [Cancelar]    │
└─────────────────────────────────────┘
```

### Si el DNI YA tiene reporte del mes:
```
┌─────────────────────────────────────┐
│ ✅ Reporte Encontrado               │
├─────────────────────────────────────┤
│                                     │
│ [Información del reporte]           │
│ [Vista previa de la imagen]         │
│                                     │
│ [Ver Reporte] [Ver Histórico]      │
└─────────────────────────────────────┘
```

---

## 🐛 SOLUCIÓN DE PROBLEMAS

### ❌ No veo el campo para subir imagen

**Causa 1: No actualizaste el módulo**
- Ve a Apps → Buscar "adt_sentinel" → Actualizar

**Causa 2: Caché del navegador**
- Presiona Ctrl+Shift+R (Windows/Linux)
- Presiona Cmd+Shift+R (Mac)

**Causa 3: El DNI ya tiene reporte vigente**
- Intenta con un DNI diferente
- Verifica que no exista reporte del mes actual

**Causa 4: Error en actualización**
- Revisa logs: /var/log/odoo/odoo.log
- O en Docker: `docker logs nombre_contenedor`

### ❌ El botón "Buscar" no hace nada

**Solución:**
1. Asegúrate de ingresar exactamente 8 dígitos
2. Limpia el caché del navegador
3. Actualiza el módulo en Apps

---

## 📂 ARCHIVOS MODIFICADOS

Los siguientes archivos fueron actualizados:

1. **wizard/sentinel_query_wizard.py**
   - Método `action_search` mejorado
   - Recarga explícita del wizard

2. **wizard/sentinel_query_wizard_views.xml**
   - Vista única consolidada
   - Campo de imagen claramente visible
   - Secciones condicionales por estado

---

## 🎯 LO IMPORTANTE

**ANTES** del cambio:
- ❌ Click en "Buscar" → No pasaba nada
- ❌ O no aparecía el campo de imagen

**DESPUÉS** del cambio:
- ✅ Click en "Buscar" → Se actualiza la pantalla
- ✅ Aparece claramente "📎 Adjuntar Imagen del Reporte"
- ✅ Botón visible para seleccionar archivo
- ✅ Vista previa de la imagen después de seleccionar

---

## 📞 ¿NECESITAS MÁS AYUDA?

Si después de seguir todos los pasos aún no funciona:

1. Verifica en modo desarrollador:
   - Activa modo desarrollador en Odoo
   - Ve a Configuración > Técnico > Vistas
   - Busca: "adt.sentinel.query.wizard.form.search"
   - Verifica que tenga fecha/hora reciente

2. Revisa los logs:
   ```bash
   # Log estándar
   tail -f /var/log/odoo/odoo.log
   
   # O con Docker
   docker logs -f nombre_contenedor
   ```

3. Reinicia Odoo (último recurso):
   ```bash
   # Con systemd
   sudo systemctl restart odoo
   
   # Con Docker
   docker-compose restart
   ```

---

**¡Listo! Ahora actualiza el módulo y prueba. El campo de imagen debería aparecer claramente.**
