# INSTRUCCIONES PARA VER EL MÓDULO ADT_CAPTURA

## PROBLEMA IDENTIFICADO
El módulo está instalado pero el menú no aparece. Esto puede deberse a:
1. El web_icon apuntaba a una imagen inexistente (ya corregido)
2. El módulo necesita ser actualizado después de los cambios
3. Los permisos del usuario no están configurados

## SOLUCIÓN PASO A PASO

### PASO 1: Actualizar el Módulo
1. Ir a: **Apps**
2. Activar **modo desarrollador** (si no está activado):
   - Configuración → Activar modo desarrollador
   - O agregar `?debug=1` en la URL
3. Quitar el filtro "Apps" en la búsqueda
4. Buscar: **"ADT Captura"** o **"adt_captura"**
5. Click en el módulo
6. Click en botón **"Actualizar"** (⟳ Upgrade)
7. Esperar a que termine la actualización

### PASO 2: Refrescar la Página
1. Presionar **F5** o **Ctrl+R** (Cmd+R en Mac)
2. O cerrar y volver a abrir el navegador

### PASO 3: Verificar el Menú
El menú debe aparecer como:
```
📱 Gestión de Capturas
   └─ Operaciones
      ├─ Clientes en Mora
      ├─ Capturas Activas
      └─ Historial
```

### PASO 4: Asignar Permisos (Si no ves el menú)
1. Ir a: **Configuración → Usuarios y Compañías → Usuarios**
2. Seleccionar tu usuario
3. Pestaña: **Derechos de acceso**
4. Buscar sección "Captura" o desplazarse hasta encontrar:
   - ☐ Capturador
   - ☐ Supervisor de Captura
   - ☐ Administrador de Captura
5. Marcar al menos: **☑ Capturador**
6. Guardar
7. **Cerrar sesión y volver a entrar**

## VERIFICACIÓN ALTERNATIVA

### Método 1: Buscar directamente
1. En el buscador de menú (arriba), escribir: **"Clientes en Mora"**
2. Si aparece, el módulo está instalado correctamente
3. Si no aparece, ir al Paso 4 (permisos)

### Método 2: Verificar en Apps
1. **Apps** → Buscar "adt_captura"
2. Debe aparecer con estado: **✓ Instalado**
3. Si dice "Instalado" pero no ves el menú → Problema de permisos

### Método 3: Acceso directo por URL
1. En la barra de direcciones, agregar al final de la URL:
   ```
   /web#action=adt_captura.action_adt_captura_mora
   ```
2. Si carga la vista "Clientes en Mora" → El módulo funciona
3. Si da error → Problema de instalación

## PROBLEMAS COMUNES

### A) El menú no aparece
**Causa**: Falta de permisos
**Solución**: Seguir PASO 4

### B) Error al actualizar
**Causa**: Algún campo o dependencia falta
**Solución**: Compartir el error completo

### C) Aparece pero está vacío "Clientes en Mora"
**Causa**: Es normal si no hay clientes con mora
**Solución**: Verificar que existan cuentas con cuotas vencidas en adt_comercial

### D) No aparece en Apps
**Causa**: El módulo no está en el path de Odoo
**Solución**: Verificar que la carpeta esté en addons/

## COMANDOS ÚTILES (Si tienes acceso al servidor)

### Actualizar desde línea de comandos:
```bash
# Navegar a la carpeta de Odoo
cd /ruta/a/odoo

# Actualizar el módulo
./odoo-bin -u adt_captura -d nombre_base_datos

# O reiniciar Odoo
sudo systemctl restart odoo
```

## VERIFICACIÓN FINAL

Después de completar los pasos, debes poder:
- ✅ Ver el menú "Gestión de Capturas"
- ✅ Acceder a "Clientes en Mora"
- ✅ Acceder a "Capturas Activas"
- ✅ Acceder a "Historial"

## SI NADA FUNCIONA

1. Compartir captura de pantalla de:
   - Apps mostrando el estado del módulo
   - La vista de permisos del usuario
   - Cualquier mensaje de error

2. Verificar logs de Odoo:
   ```bash
   tail -f /var/log/odoo/odoo-server.log
   ```

3. Verificar que adt_comercial esté instalado:
   - El módulo depende de adt_comercial
   - Sin él, no funcionará correctamente

---

**CAMBIO REALIZADO**: Se eliminó la referencia al web_icon inexistente en menu.xml
**ACCIÓN REQUERIDA**: Actualizar el módulo en Odoo (Apps → adt_captura → Actualizar)
