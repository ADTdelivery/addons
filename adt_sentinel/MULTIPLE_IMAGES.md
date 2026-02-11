# Múltiples Imágenes en Reportes Sentinel

## 📋 Resumen

Se ha implementado soporte para **múltiples imágenes** en los reportes Sentinel, reemplazando la limitación anterior de una sola imagen por reporte.

## ✨ Nuevas Características

### 1. Modelo `adt.sentinel.report.image`
- **Relación:** One2Many con `adt.sentinel.report`
- **Campos:**
  - `image`: Imagen binaria (attachment=True)
  - `image_filename`: Nombre del archivo
  - `description`: Descripción opcional de la imagen
  - `sequence`: Orden de visualización (editable con drag & drop)

### 2. Campos Actualizados en `adt.sentinel.report`
- **Nuevo:** `image_ids` (One2many) - Múltiples imágenes
- **Nuevo:** `image_count` (Integer, computed) - Contador de imágenes
- **Deprecado:** `report_image` (Binary) - Mantenido por compatibilidad

### 3. Nuevas Funcionalidades

#### Método `action_view_images()`
Abre una ventana con todas las imágenes asociadas al reporte:
```python
def action_view_images(self):
    """Abre la vista de imágenes asociadas al reporte."""
    self.ensure_one()
    return {
        'name': f'Imágenes - DNI {self.document_number}',
        'type': 'ir.actions.act_window',
        'res_model': 'adt.sentinel.report.image',
        'view_mode': 'tree,form',
        'domain': [('report_id', '=', self.id)],
        'context': {
            'default_report_id': self.id,
            'create': True,
        },
    }
```

## 🖼️ Vista Actualizada

### Formulario del Reporte
- **Botón estadístico:** Muestra el contador de imágenes
- **Vista Kanban:** Muestra todas las imágenes con miniaturas
- **Edición inline:** Agregar/editar múltiples imágenes directamente
- **Tab Legacy:** El campo antiguo `report_image` solo se muestra si tiene valor

### Características de la Vista
- 📸 Vista previa en miniatura
- 🔢 Orden personalizable (drag & drop)
- 📝 Descripción por imagen
- 📁 Nombre de archivo
- 🖱️ Click para ampliar

## 🔄 Migración

### Datos Existentes
El campo `report_image` se mantiene para **compatibilidad hacia atrás**:
- Los reportes antiguos seguirán mostrando su imagen en el tab "Imagen Legacy"
- Nuevos reportes deben usar `image_ids`

### Proceso de Actualización
1. Actualizar el módulo: `Aplicaciones → adt_sentinel → Actualizar`
2. Los reportes existentes mantienen su imagen original
3. Se puede agregar nuevas imágenes usando el campo `image_ids`

## 📝 Uso

### Desde Python
```python
# Crear reporte con múltiples imágenes
report = env['adt.sentinel.report'].create({
    'document_number': '12345678',
    'query_date': fields.Date.today(),
    'query_user_id': env.user.id,
    'image_ids': [
        (0, 0, {
            'image': base64_image_1,
            'image_filename': 'sentinel_page1.png',
            'description': 'Página 1',
            'sequence': 10,
        }),
        (0, 0, {
            'image': base64_image_2,
            'image_filename': 'sentinel_page2.png',
            'description': 'Página 2',
            'sequence': 20,
        }),
    ]
})

# Agregar imagen a reporte existente
report.image_ids.create({
    'image': base64_image,
    'image_filename': 'additional.png',
    'description': 'Detalle adicional',
})

# Contar imágenes
total_images = report.image_count
```

### Desde la UI
1. Abrir un reporte Sentinel
2. Ir al tab "🖼️ Imágenes del Reporte"
3. Hacer clic en "Agregar una línea"
4. Subir imagen, agregar descripción
5. Arrastrar para reordenar

## 🔐 Seguridad

Permisos configurados:
- `access_sentinel_report_image_user`: Usuarios normales (CRUD completo)
- `access_sentinel_report_image_manager`: Administradores (CRUD completo)

## 🧪 Testing

```python
# Test: Crear reporte con múltiples imágenes
report = self.env['adt.sentinel.report'].create({
    'document_number': '12345678',
    'query_date': fields.Date.today(),
    'query_user_id': self.env.user.id,
})

# Agregar 3 imágenes
for i in range(3):
    report.image_ids.create({
        'image': b'fake_image_data',
        'image_filename': f'test_{i}.png',
        'description': f'Test image {i}',
    })

# Verificar contador
self.assertEqual(report.image_count, 3)

# Verificar action
action = report.action_view_images()
self.assertEqual(action['res_model'], 'adt.sentinel.report.image')
self.assertEqual(action['domain'], [('report_id', '=', report.id)])
```

## ⚡ Rendimiento

- Las imágenes se almacenan como **attachments** (filestore)
- No impacta el rendimiento de la base de datos
- Carga bajo demanda en la UI

## 🎯 Casos de Uso

1. **Reportes multipágina:** Sentinel puede tener varias páginas
2. **Documentos adicionales:** Agregar anexos relacionados
3. **Histórico visual:** Múltiples capturas de pantalla
4. **Comparaciones:** Reportes de diferentes fechas

---

**Versión:** 1.0.0  
**Fecha:** 2026-02-11  
**Estado:** ✅ Implementado
