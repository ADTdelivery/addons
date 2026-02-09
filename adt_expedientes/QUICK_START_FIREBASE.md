# 🚀 Quick Start - Firebase Push Notifications

## ⚡ Configuración Rápida (5 minutos)

### 1️⃣ Instalar dependencias

```bash
pip3 install google-auth requests
```

### 2️⃣ Obtener credenciales de Firebase

1. Ir a [Firebase Console](https://console.firebase.google.com/)
2. Seleccionar proyecto
3. ⚙️ **Configuración** > **Cuentas de servicio**
4. Click **"Generar nueva clave privada"**
5. Descargar `firebase-adminsdk-xxx.json`

### 3️⃣ Subir archivo al servidor

```bash
# Copiar al servidor
scp firebase-adminsdk-xxx.json user@servidor:/opt/odoo/config/

# Dar permisos
chmod 600 /opt/odoo/config/firebase-adminsdk-xxx.json
chown odoo:odoo /opt/odoo/config/firebase-adminsdk-xxx.json
```

### 4️⃣ Configurar Odoo

**Opción A: Por interfaz**
1. Ir a **Configuración > Técnico > Parámetros del Sistema**
2. Crear:
   - `firebase.service_account_path` = `/opt/odoo/config/firebase-adminsdk-xxx.json`
   - `firebase.project_id` = `tu-proyecto-id`

**Opción B: Por SQL**
```sql
INSERT INTO ir_config_parameter (key, value) VALUES 
    ('firebase.service_account_path', '/opt/odoo/config/firebase-adminsdk-xxx.json'),
    ('firebase.project_id', 'tu-proyecto-12345');
```

### 5️⃣ Actualizar módulo

```bash
./odoo-bin -u adt_expedientes -d tu_base_datos
```

---

## 📱 Uso desde App Móvil

### Paso 1: Login y obtener token

```javascript
POST /adt_expedientes/mobile/token/create

{
  "db": "nombre_bd",
  "login": "usuario",
  "password": "contraseña"
}

Response: { "success": true, "data": { "token": "abc123..." } }
```

### Paso 2: Registrar token FCM

```javascript
POST /adt/mobile/fcm/register
Headers: Authorization: Bearer abc123...

{
  "fcm_token": "dXYz789...",
  "platform": "android"
}
```

### Paso 3: Recibir notificaciones push

La app recibirá automáticamente notificaciones cuando:
- ✅ Se rechace un expediente
- ✅ Se marque como incompleto
- ✅ Se marque como completo

---

## 🧪 Test Rápido

### Verificar configuración

```bash
# Ver parámetros
psql tu_bd -c "SELECT key, value FROM ir_config_parameter WHERE key LIKE 'firebase%';"
```

### Probar registro de dispositivo

```bash
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "test123", "platform": "android"}'
```

### Ver dispositivos registrados

Odoo UI: **Configuración > Dispositivos FCM**

---

## 🔍 Verificar que funciona

1. Ir a un expediente en Odoo
2. Presionar botón **"Marcar Completo"**
3. Ver logs:
   ```bash
   tail -f /var/log/odoo/odoo.log | grep FCM
   ```
4. Deberías ver:
   ```
   INFO: Notificación FCM enviada para expediente X: 1 dispositivo(s)
   ```

---

## 📊 Endpoints Disponibles

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/adt/mobile/fcm/register` | POST | Registrar token FCM |
| `/adt/mobile/fcm/unregister` | POST | Desactivar token |
| `/adt/mobile/fcm/devices` | POST | Listar dispositivos |
| `/api/sentinel/report/get` | POST | Consultar reporte Sentinel |
| `/api/sentinel/report/create` | POST | Crear reporte Sentinel |

Todos requieren: `Authorization: Bearer TOKEN`

---

## ❌ Troubleshooting Express

| Error | Solución |
|-------|----------|
| `No module named 'google.auth'` | `pip3 install google-auth` |
| `FileNotFoundError` | Verificar ruta en `firebase.service_account_path` |
| `No se encontró la configuración` | Crear parámetros del sistema |
| No llegan notificaciones | Verificar que el cliente tenga usuario asociado |

---

## 📚 Documentación completa

Ver: `FIREBASE_IMPLEMENTATION.md`

---

**✅ ¡Listo para usar!**
