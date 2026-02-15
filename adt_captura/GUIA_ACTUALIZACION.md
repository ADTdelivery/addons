# 🚀 GUÍA RÁPIDA DE ACTUALIZACIÓN

## ✅ MÓDULO ADT_CAPTURA v1.1

---

## 📦 ¿QUÉ SE ACTUALIZÓ?

**8 mejoras implementadas:**
1. ✅ Eliminado "Condicional"
2. ✅ Eliminado "Estado Mora"
3. ✅ Agregado "# Cuotas Vencidas"
4. ✅ Pago desacoplado de liberación
5. ✅ Alerta de deuda anterior
6. ✅ Popups se cierran solos
7. ✅ Vistas separadas por tipo
8. ✅ Preview de imágenes

**Versión:** 1.0 → 1.1

---

## 🎯 CÓMO ACTUALIZAR (3 PASOS)

### PASO 1: Modo Desarrollador
```
Configuración → Activar el modo de desarrollador
O agregar ?debug=1 en la URL
```

### PASO 2: Actualizar Módulo
```
1. Apps
2. Quitar filtro "Apps" de la búsqueda
3. Buscar: "adt_captura"
4. Click en el módulo
5. Click botón "Actualizar" (⟳)
6. Esperar 10-30 segundos
7. ✓ Listo!
```

### PASO 3: Refrescar Navegador
```
Presionar F5 o Ctrl+R
```

---

## ✅ VERIFICACIÓN (2 MINUTOS)

Después de actualizar, verifica:

### 1. Menú
```
¿El menú tiene 4 opciones?
✓ Clientes en Mora
✓ Capturas Inmediatas
✓ Compromisos de Pago
✓ Historial
```

### 2. Crear Captura
```
¿Al crear captura solo hay 2 tipos?
✓ Inmediata
✓ Compromiso de Pago
(Condicional ya NO aparece)
```

### 3. Campos en Form
```
¿El formulario muestra estos campos?
✓ Días de Mora
✓ # Cuotas Vencidas (NUEVO)
✓ Tipo Cartera
(Estado Mora ya NO aparece)
```

### 4. Alerta de Deuda
```
¿Si el cliente tiene deuda anterior se ve alerta?
✓ Banner amarillo con ⚠️
✓ Muestra monto total
✓ Botón "Ver Capturas Anteriores"
```

### 5. Registrar Pago
```
¿El popup se cierra solo después de guardar?
✓ Sí
```

### 6. Liberar sin Pago
```
¿Se puede liberar aunque no haya pagado?
✓ Sí (agrega nota: "Pago aún pendiente")
```

### 7. Preview de Imágenes
```
¿Las imágenes se ven en miniatura?
✓ Sí, en la pestaña Evidencia
```

---

## ⚠️ PROBLEMAS COMUNES

### No veo el menú después de actualizar
**Solución:**
1. F5 para refrescar
2. Cerrar sesión y volver a entrar
3. Verificar permisos de usuario

### Error al actualizar
**Solución:**
1. Leer el mensaje de error completo
2. Si dice "estado_mora" → Es normal, se está eliminando
3. La actualización lo maneja automáticamente

### Capturas viejas con "Condicional"
**Solución:**
- Las capturas existentes siguen funcionando
- Solo las nuevas no tendrán esa opción

---

## 📊 ANTES vs DESPUÉS

| Característica | v1.0 | v1.1 |
|----------------|------|------|
| Tipos captura | 3 | 2 ✅ |
| Menús | 3 | 4 ✅ |
| Estado mora | Sí | No ✅ |
| # Cuotas | No | Sí ✅ |
| Alerta deuda | No | Sí ✅ |
| Popup cierre | Manual | Auto ✅ |
| Preview img | No | Sí ✅ |
| Liberar sin pago | No | Sí ✅ |

---

## 📁 DOCUMENTACIÓN DISPONIBLE

- `RESUMEN_EJECUTIVO.md` → Resumen de 1 página
- `CAMBIOS_IMPLEMENTADOS.md` → Detalle completo
- `ANTES_VS_DESPUES.md` → Comparación visual
- `COMO_VER_EL_MODULO.md` → Troubleshooting
- `README.md` → Manual de usuario

---

## 🎉 ¡ACTUALIZACIÓN EXITOSA!

Si llegaste hasta aquí y todas las verificaciones están en ✓:

**¡FELICITACIONES! El módulo está actualizado correctamente.**

Puedes empezar a usar las nuevas funcionalidades inmediatamente.

---

## 📞 ¿NECESITAS AYUDA?

Si algo no funciona:
1. Revisar logs de Odoo
2. Consultar `CAMBIOS_IMPLEMENTADOS.md`
3. Verificar permisos de usuario
4. Contactar soporte técnico

---

**Versión:** 1.1  
**Fecha:** 15 de Febrero de 2026  
**Estado:** ✅ LISTO PARA PRODUCCIÓN
