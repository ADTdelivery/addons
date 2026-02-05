# 🔄 INSTRUCCIONES PARA ACTUALIZAR EL MÓDULO ADT_SENTINEL

## Problema Solucionado
✅ El botón "Buscar" ahora funciona correctamente y muestra el campo para subir la imagen

## Cambios Realizados

### 1. Vista del Wizard Mejorada
- Campo de carga de imagen más visible con título "📎 Adjuntar Imagen del Reporte"
- Vista previa de la imagen con título "🖼️ Vista Previa"
- Mejor organización con grupos (groupbox) claramente identificados

### 2. Método de Búsqueda Optimizado
- Recarga explícita del wizard con la vista correcta
- Mejor gestión del contexto

## 🚀 CÓMO ACTUALIZAR (Elija UNA opción)

### OPCIÓN 1: Desde la Interfaz de Odoo (RECOMENDADO)

1. **Abra Odoo** en su navegador
2. Vaya al menú **Apps** (Aplicaciones)
3. **Quite el filtro "Apps"** (debe mostrar todos los módulos)
4. En el buscador, escriba: **adt_sentinel**
5. Haga clic en el botón **"Actualizar"** (⟳ icono de actualización)
6. **Confirme** la actualización
7. Espere a que termine el proceso
8. ✅ **¡Listo!** Pruebe el wizard nuevamente

### OPCIÓN 2: Reiniciar Odoo (si usa Docker)

```bash
# Navegue al directorio donde está docker-compose.yml
cd /ruta/de/tu/proyecto

# Reinicie los contenedores
docker-compose restart

# O si prefiere reconstruir:
docker-compose down
docker-compose up -d
```

### OPCIÓN 3: Reiniciar Odoo (instalación directa)

```bash
# Reiniciar el servicio de Odoo
sudo systemctl restart odoo

# Verificar el estado
sudo systemctl status odoo
```

### OPCIÓN 4: Actualizar desde línea de comandos

```bash
# Ejecutar Odoo con actualización del módulo
odoo-bin -c /etc/odoo/odoo.conf -d nombre_de_tu_base_de_datos -u adt_sentinel

# O si está usando docker:
docker exec -it nombre_contenedor odoo -u adt_sentinel -d nombre_bd --stop-after-init
```

## 🧪 CÓMO PROBAR

1. Vaya a **Sentinel > 🔍 Consultar DNI**
2. Ingrese un **DNI de 8 dígitos** (ejemplo: 12345678)
3. Haga clic en **"🔍 Buscar"**
4. Debería ver una de estas pantallas:

   **CASO A: Reporte Encontrado**
   - ✅ Mensaje de "Reporte Encontrado"
   - 📄 Vista previa de la imagen
   - 📊 Detalles del reporte
   - Botones: "Ver Reporte Completo" y "Ver Histórico"

   **CASO B: No Encontrado (Subir Imagen)**
   - 📸 Título "Subir Nuevo Reporte"
   - ℹ️ Mensaje informativo
   - ⚠️ Advertencia de costo (S/ 10.00)
   - **📎 Sección "Adjuntar Imagen del Reporte"** ← Aquí aparece el botón para subir
   - 📝 Campo de observaciones
   - 🖼️ Vista previa (aparece después de seleccionar la imagen)
   - Botón: "💾 Subir y Guardar (S/ 10.00)"

## 🐛 Si NO Aparece el Campo de Imagen

### Verificación 1: ¿Se actualizó correctamente?
```bash
# Buscar en los logs de Odoo
grep "adt_sentinel" /var/log/odoo/odoo.log | tail -20

# O en Docker:
docker logs nombre_contenedor | grep adt_sentinel | tail -20
```

### Verificación 2: Limpiar caché del navegador
1. Presione **Ctrl + Shift + R** (Windows/Linux)
2. O **Cmd + Shift + R** (Mac)
3. Cierre y abra el navegador

### Verificación 3: Modo desarrollador
1. Active el **modo desarrollador** en Odoo
2. Vaya a **Configuración > Técnico > Estructura de Base de Datos > Vistas**
3. Busque: **adt.sentinel.query.wizard.form.search**
4. Verifique que la vista tenga la fecha/hora de modificación reciente

### Verificación 4: Reinstalar el módulo (ÚLTIMO RECURSO)
```
1. Vaya a Apps
2. Busque "adt_sentinel"
3. Desinstale el módulo
4. Instale nuevamente
⚠️ CUIDADO: Esto eliminará los datos existentes
```

## 📞 SOPORTE

Si después de seguir todos los pasos aún no funciona:

1. Verifique los logs de Odoo para errores
2. Asegúrese de que el módulo se actualizó correctamente
3. Verifique que los archivos modificados estén en el servidor
4. Revise los permisos de los archivos (deben ser legibles por el usuario de Odoo)

## 📝 NOTA IMPORTANTE

Los cambios realizados son:
- ✅ **wizard/sentinel_query_wizard.py** - Método action_search mejorado
- ✅ **wizard/sentinel_query_wizard_views.xml** - Vista consolidada y mejorada

Ambos archivos deben estar presentes en:
`/Users/jhon.curi/Desktop/personal/odoo/addons/adt_sentinel/wizard/`
