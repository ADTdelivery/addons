# ⚙️ Configuración Dinámica de URL de Notificaciones

## ✅ Implementado

Ahora puedes configurar la URL del servicio de notificaciones de forma dinámica sin modificar código.

## 🎯 Configuración

### Opción 1: Desde la UI de Odoo (Recomendado)

1. **Ir a Configuración**
   - Menú: `Configuración` → `Técnico` → `Parámetros del Sistema`

2. **Buscar o crear el parámetro:**
   - **Clave:** `notification.service.url`
   - **Valor:** `http://192.168.100.5:8030/send`

3. **Guardar**

### Opción 2: Desde SQL

```sql
-- Actualizar si existe
UPDATE ir_config_parameter 
SET value = 'http://192.168.100.5:8030/send' 
WHERE key = 'notification.service.url';

-- O insertar si no existe
INSERT INTO ir_config_parameter (key, value, create_date, create_uid, write_date, write_uid)
VALUES ('notification.service.url', 'http://192.168.100.5:8030/send', NOW(), 1, NOW(), 1)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
```

### Opción 3: Desde Python (Shell de Odoo)

```python
# Acceder a shell de Odoo
./odoo-bin shell -d tu_bd

# Establecer la URL
env['ir.config_parameter'].sudo().set_param(
    'notification.service.url', 
    'http://192.168.100.5:8030/send'
)
```

## 📝 Ejemplos de URLs

### Desarrollo Local
```
http://localhost:8030/send
```

### Red Local (LAN)
```
http://192.168.100.5:8030/send
```

### Servidor Remoto
```
http://notificaciones.tudominio.com:8030/send
```

### Con Puerto Diferente
```
http://192.168.1.100:9000/api/push
```

### HTTPS
```
https://api.notificaciones.com/send
```

## 🔍 Verificar Configuración Actual

### Desde UI
1. Ir a: `Configuración` → `Técnico` → `Parámetros del Sistema`
2. Buscar: `notification.service.url`

### Desde SQL
```sql
SELECT key, value 
FROM ir_config_parameter 
WHERE key = 'notification.service.url';
```

### Desde Python (Shell)
```python
url = env['ir.config_parameter'].sudo().get_param('notification.service.url')
print(f'URL actual: {url}')
```

## 🔄 Cambiar URL Sin Reiniciar

**¡No necesitas reiniciar Odoo!** El cambio se aplica inmediatamente:

1. Cambiar el valor en `Parámetros del Sistema`
2. Guardar
3. La próxima notificación usará la nueva URL

## 🧪 Probar Nueva URL

```python
# En shell de Odoo
from addons.adt_expedientes.services.notification_service import NotificationService

service = NotificationService(env)
print(f'URL configurada: {service.notification_url}')

# Probar envío
result = service.send_notification(
    token='test_token',
    title='Test',
    body='Probando nueva URL',
    data={'test': True}
)
print(result)
```

## 📋 Valores por Defecto

Si no configuras el parámetro, se usa el valor por defecto:
```
http://localhost:8030/send
```

Este valor se establece automáticamente al instalar/actualizar el módulo mediante el archivo:
```
data/notification_config.xml
```

## 🚀 Instalación/Actualización

```bash
# Actualizar módulo para aplicar la configuración
./odoo-bin -u adt_expedientes -d tu_bd
```

Después de actualizar, verifica que el parámetro existe:
```sql
SELECT * FROM ir_config_parameter WHERE key = 'notification.service.url';
```

## 🎯 Casos de Uso

### Desarrollo
```
notification.service.url = http://localhost:8030/send
```

### QA/Testing
```
notification.service.url = http://192.168.100.5:8030/send
```

### Producción
```
notification.service.url = https://push.tudominio.com/api/send
```

## 🔒 Seguridad

- El parámetro solo puede ser modificado por usuarios con permisos de administrador
- Se almacena en la base de datos
- No está hardcodeado en el código
- Puede ser diferente por cada base de datos

## 📊 Múltiples Entornos

Si tienes múltiples bases de datos, puedes configurar URLs diferentes:

```bash
# Base de datos de desarrollo
./odoo-bin shell -d dev_db
>>> env['ir.config_parameter'].sudo().set_param('notification.service.url', 'http://localhost:8030/send')

# Base de datos de producción
./odoo-bin shell -d prod_db
>>> env['ir.config_parameter'].sudo().set_param('notification.service.url', 'https://push.prod.com/send')
```

## ✅ Ventajas

- ✅ **Sin modificar código** - Solo cambia configuración
- ✅ **Sin reiniciar Odoo** - Aplica inmediatamente
- ✅ **Por base de datos** - Diferentes URLs por entorno
- ✅ **UI amigable** - Editable desde interfaz
- ✅ **Backup incluido** - Se respalda con la BD

## 🆘 Troubleshooting

### No puedo ver el parámetro en la UI

**Solución:**
1. Actualizar el módulo: `./odoo-bin -u adt_expedientes -d tu_bd`
2. Verificar que eres administrador
3. Habilitar modo desarrollador: `Configuración` → `Activar modo de desarrollador`

### La URL no cambia

**Solución:**
1. Verificar que el parámetro existe:
   ```sql
   SELECT * FROM ir_config_parameter WHERE key = 'notification.service.url';
   ```
2. Limpiar cache de Python (reiniciar Odoo)
3. Verificar logs de Odoo para ver qué URL está usando

### Error al conectar al servicio

**Solución:**
1. Verificar que el servicio está corriendo:
   ```bash
   curl http://192.168.100.5:8030/send
   ```
2. Verificar firewall y puertos
3. Ver logs de Odoo: `tail -f /var/log/odoo/odoo.log | grep -i notification`

---

## 📝 Resumen Rápido

```bash
# 1. Actualizar módulo
./odoo-bin -u adt_expedientes -d tu_bd

# 2. Ir a UI de Odoo
# Configuración → Técnico → Parámetros del Sistema

# 3. Editar/Crear:
# Clave: notification.service.url
# Valor: http://192.168.100.5:8030/send

# 4. ¡Listo! No reiniciar necesario
```

---

**✅ Ahora puedes cambiar la URL del servicio de notificaciones sin tocar código!**
