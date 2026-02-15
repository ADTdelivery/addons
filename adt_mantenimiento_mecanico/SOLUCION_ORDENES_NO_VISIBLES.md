# 🔧 SOLUCIÓN: No se pueden ver las órdenes creadas

## ✅ PROBLEMA IDENTIFICADO Y RESUELTO

**Causa**: Los usuarios normales no tenían permisos de lectura sobre las órdenes de mantenimiento.

**Solución aplicada**: Agregado permiso de lectura para el grupo `group_taller_usuario`.

---

## 📝 CAMBIOS REALIZADOS

### Archivo modificado: `security/ir.model.access.csv`

**Línea agregada:**
```csv
access_adt_orden_mantenimiento_usuario,adt.orden.mantenimiento.usuario,model_adt_orden_mantenimiento,group_taller_usuario,1,0,0,0
```

Esto permite que todos los usuarios del taller puedan **leer** las órdenes (aunque no editarlas ni crearlas).

---

## 🚀 PASOS PARA APLICAR LA SOLUCIÓN

### Opción 1: Desde línea de comandos (Recomendado)

```bash
# Actualizar el módulo
./odoo-bin -u adt_mantenimiento_mecanico -d nombre_de_tu_base_de_datos --stop-after-init

# Reiniciar Odoo
sudo systemctl restart odoo
```

### Opción 2: Desde la interfaz de Odoo

1. Ve a **Aplicaciones** (Apps)
2. Elimina el filtro "Aplicaciones" de la búsqueda
3. Busca **"ADT Mantenimiento Mecánico"**
4. Click en **"Actualizar"** (botón con icono de refresh)
5. Espera a que termine la actualización

---

## 👥 VERIFICAR PERMISOS DE USUARIO

Después de actualizar, verifica que tu usuario tenga el grupo correcto:

1. Ve a **Configuración → Usuarios y Compañías → Usuarios**
2. Abre tu usuario
3. Ve a la pestaña **"Control de acceso"**
4. En la sección **"Taller Mecánico"**, asegúrate de tener al menos uno de estos roles:
   - ✅ **Usuario del Taller** (para solo lectura)
   - ✅ **Asesor de Servicio** (para crear/editar órdenes)
   - ✅ **Mecánico** (para trabajar en órdenes)
   - ✅ **Supervisor del Taller** (para supervisión completa)
   - ✅ **Administrador del Taller** (acceso total)

---

## 🎯 ESTRUCTURA DE PERMISOS

### Usuario del Taller (Básico)
- ✅ **Leer** órdenes, vehículos, mecánicos
- ❌ No puede crear ni modificar

### Mecánico
- ✅ **Leer y Escribir** trabajos asignados
- ✅ **Crear** inspecciones y diagnósticos
- ❌ No puede crear órdenes nuevas

### Asesor de Servicio
- ✅ **Leer, Crear y Modificar** órdenes
- ✅ **Crear** vehículos y clientes
- ❌ No puede eliminar

### Supervisor / Administrador
- ✅ **Acceso completo** (CRUD) a todos los registros
- ✅ Puede eliminar registros

---

## 🔍 CÓMO VERIFICAR QUE FUNCIONA

1. **Actualiza el módulo** según los pasos anteriores
2. **Recarga la página** del navegador (F5 o Ctrl+R)
3. Ve al menú **"Taller Mecánico → Órdenes → Órdenes de Mantenimiento"**
4. Deberías ver todas las órdenes creadas

Si después de actualizar sigues sin ver las órdenes:

### Solución adicional:

```bash
# Limpiar caché y actualizar
./odoo-bin -u adt_mantenimiento_mecanico -d nombre_db --stop-after-init

# Si usas Docker:
docker-compose restart
```

---

## 📊 RESUMEN DE PERMISOS ACTUALIZADOS

| Grupo | Órdenes | Vehículos | Mecánicos | Clientes |
|-------|---------|-----------|-----------|----------|
| Usuario | ✅ Leer | ✅ Leer | ✅ Leer | ✅ Leer |
| Mecánico | ✅ Leer/Escribir | ✅ Leer | ✅ Leer | ✅ Leer |
| Asesor | ✅ CRUD* | ✅ CRUD* | ✅ Leer | ✅ CRUD* |
| Manager | ✅ CRUD | ✅ CRUD | ✅ CRUD | ✅ CRUD |

*CRUD = Create, Read, Update (sin Delete)

---

## ✅ PROBLEMA RESUELTO

Los cambios ya están aplicados en el código. Solo necesitas **actualizar el módulo** en tu instancia de Odoo.

**Fecha de corrección**: Febrero 13, 2026  
**Archivo modificado**: `security/ir.model.access.csv`  
**Líneas añadidas**: 1  

---

## 💡 NOTA IMPORTANTE

Si en el futuro quieres que ciertos usuarios NO vean ciertas órdenes, puedes agregar **Record Rules** en el archivo `security/security_groups.xml` para filtrar por:
- Asesor asignado
- Sucursal
- Estado de la orden
- Etc.

Por ahora, todos los usuarios autenticados con el grupo "Taller Mecánico" podrán ver todas las órdenes.
