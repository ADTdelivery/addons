# ✅ Installation Verification Checklist

## 📋 Pre-Installation

- [ ] Odoo 15.0+ instalado
- [ ] Módulo `adt_sentinel` instalado y funcional
- [ ] Acceso SSH al servidor
- [ ] Cuenta de Firebase configurada

---

## 🔧 Installation Steps

### 1. Dependencias Python

```bash
cd /Users/jhon.curi/Desktop/personal/odoo/addons/adt_expedientes
pip3 install -r requirements.txt
```

**Verificar:**
```bash
python3 -c "import google.auth; print('✓ google-auth OK')"
python3 -c "import requests; print('✓ requests OK')"
```

- [ ] google-auth instalado
- [ ] requests instalado

---

### 2. Archivos Creados

Verificar que existen los siguientes archivos:

**Modelos:**
- [ ] `models/fcm_device.py`
- [ ] `models/__init__.py` (actualizado con fcm_device)

**Services:**
- [ ] `services/__init__.py`
- [ ] `services/firebase_service.py`

**Controllers:**
- [ ] `controllers/fcm_controller.py`
- [ ] `controllers/mobile_sentinel_api.py` (ya existía)
- [ ] `controllers/__init__.py` (actualizado)

**Views:**
- [ ] `views/fcm_device_views.xml`

**Security:**
- [ ] `security/ir.model.access.csv` (actualizado con adt.fcm.device)

**Wizard:**
- [ ] `wizard/expediente_rechazo_wizard.py` (actualizado con notificación)

**Manifest:**
- [ ] `__manifest__.py` (actualizado con nueva versión y dependencias)

**Documentación:**
- [ ] `FIREBASE_IMPLEMENTATION.md`
- [ ] `QUICK_START_FIREBASE.md`
- [ ] `API_TESTING_GUIDE.md`
- [ ] `README_FIREBASE.md`
- [ ] `requirements.txt`

---

### 3. Verificar Sintaxis Python

```bash
cd models
python3 -m py_compile fcm_device.py
python3 -m py_compile expediente.py

cd ../services
python3 -m py_compile firebase_service.py

cd ../controllers
python3 -m py_compile fcm_controller.py
```

- [ ] Sin errores de sintaxis en modelos
- [ ] Sin errores de sintaxis en servicios
- [ ] Sin errores de sintaxis en controllers

---

### 4. Firebase Configuration

**Obtener Service Account:**
- [ ] Acceder a [Firebase Console](https://console.firebase.google.com/)
- [ ] Ir a Configuración > Cuentas de servicio
- [ ] Descargar JSON de clave privada
- [ ] Archivo guardado como: `firebase-adminsdk-xxx.json`

**Subir al servidor:**
```bash
# Copiar archivo
scp firebase-adminsdk-xxx.json user@servidor:/opt/odoo/config/

# SSH al servidor
ssh user@servidor

# Dar permisos
sudo chown odoo:odoo /opt/odoo/config/firebase-adminsdk-xxx.json
sudo chmod 600 /opt/odoo/config/firebase-adminsdk-xxx.json

# Verificar
ls -la /opt/odoo/config/firebase-adminsdk-xxx.json
```

- [ ] Archivo JSON subido
- [ ] Permisos correctos (600)
- [ ] Owner correcto (odoo:odoo)

---

### 5. Actualizar Módulo en Odoo

```bash
# Opción 1: Línea de comandos
./odoo-bin -u adt_expedientes -d nombre_bd --stop-after-init

# Opción 2: Desde UI
# Aplicaciones > adt_expedientes > Actualizar
```

- [ ] Módulo actualizado sin errores
- [ ] Logs sin errores críticos

---

### 6. Configurar Parámetros del Sistema

**Método 1: UI**

1. Ir a: **Configuración > Técnico > Parámetros del Sistema**
2. Crear parámetro:
   - Clave: `firebase.service_account_path`
   - Valor: `/opt/odoo/config/firebase-adminsdk-xxx.json`
3. Crear parámetro:
   - Clave: `firebase.project_id`
   - Valor: `tu-proyecto-id` (ej: `adt-expedientes-12345`)

**Método 2: SQL**

```sql
INSERT INTO ir_config_parameter (key, value, create_date, create_uid, write_date, write_uid)
VALUES 
    ('firebase.service_account_path', '/opt/odoo/config/firebase-adminsdk-xxx.json', NOW(), 1, NOW(), 1),
    ('firebase.project_id', 'tu-proyecto-id', NOW(), 1, NOW(), 1)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
```

**Verificar:**
```sql
SELECT key, value FROM ir_config_parameter WHERE key LIKE 'firebase%';
```

- [ ] `firebase.service_account_path` configurado
- [ ] `firebase.project_id` configurado
- [ ] Valores correctos

---

### 7. Verificar Base de Datos

**Tablas creadas:**
```sql
-- Verificar que la tabla existe
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'adt_fcm_device'
);
```

**Estructura de la tabla:**
```sql
\d adt_fcm_device
```

- [ ] Tabla `adt_fcm_device` creada
- [ ] Columnas correctas (user_id, token, platform, etc.)

---

### 8. Verificar Access Rights

```sql
SELECT * FROM ir_model_access WHERE model_id IN (
    SELECT id FROM ir_model WHERE model = 'adt.fcm.device'
);
```

- [ ] Access rights para `adt.fcm.device` configurados

---

### 9. Verificar Views

```sql
SELECT name, model FROM ir_ui_view WHERE model = 'adt.fcm.device';
```

Debe mostrar:
- `adt.fcm.device.tree`
- `adt.fcm.device.form`
- `adt.fcm.device.search`

- [ ] Views de FCM device creadas

---

### 10. Verificar Menú

**UI:**
1. Ir a **Configuración**
2. Buscar menú **"Dispositivos FCM"**

**SQL:**
```sql
SELECT name FROM ir_ui_menu WHERE name LIKE '%FCM%';
```

- [ ] Menú "Dispositivos FCM" visible

---

## 🧪 Functional Testing

### Test 1: Registrar Token FCM (API)

```bash
# 1. Obtener token de autenticación
TOKEN=$(curl -s -X POST http://localhost:8069/adt_expedientes/mobile/token/create \
  -H "Content-Type: application/json" \
  -d '{
    "db": "tu_bd",
    "login": "admin",
    "password": "admin"
  }' | jq -r '.data.token')

echo "Token: $TOKEN"

# 2. Registrar token FCM
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "fcm_token": "test_token_verification_123",
    "platform": "android",
    "device_info": {
      "device_name": "Test Device",
      "device_os": "Test OS"
    }
  }'
```

**Resultado esperado:**
```json
{
  "success": true,
  "message": "Token FCM registrado correctamente",
  "device_id": 1
}
```

- [ ] API responde correctamente
- [ ] Token registrado exitosamente
- [ ] device_id retornado

---

### Test 2: Verificar en UI

1. Ir a **Configuración > Dispositivos FCM**
2. Verificar que aparece el dispositivo registrado

- [ ] Dispositivo visible en lista
- [ ] Información correcta (usuario, platform, etc.)

---

### Test 3: Notificación Push (Simulación)

1. Crear un expediente de prueba
2. Asignar cliente con usuario
3. Registrar token FCM para ese usuario
4. Cambiar estado del expediente (ej: "Marcar Completo")

**Verificar logs:**
```bash
tail -n 50 /var/log/odoo/odoo.log | grep -i fcm
```

**Resultado esperado:**
```
INFO: Notificación FCM enviada para expediente X: 1 dispositivo(s)
```

- [ ] Notificación enviada sin errores
- [ ] Log registrado correctamente

---

### Test 4: Sentinel API

```bash
# Consultar reporte
curl -X POST http://localhost:8069/api/sentinel/report/get \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_number": "12345678"}'
```

- [ ] API Sentinel responde
- [ ] Autenticación funciona

---

## 🔍 Troubleshooting

### Si hay errores al actualizar el módulo

**Ver logs:**
```bash
tail -n 100 /var/log/odoo/odoo.log
```

**Errores comunes:**

1. **ImportError: No module named 'google.auth'**
   ```bash
   pip3 install google-auth
   ```

2. **Table already exists**
   - Normal si actualizando, ignorar

3. **Access rights missing**
   - Verificar `security/ir.model.access.csv`
   - Actualizar módulo nuevamente

---

### Si Firebase no envía notificaciones

1. **Verificar configuración:**
   ```sql
   SELECT * FROM ir_config_parameter WHERE key LIKE 'firebase%';
   ```

2. **Verificar archivo JSON:**
   ```bash
   ls -la /opt/odoo/config/firebase-adminsdk-*.json
   cat /opt/odoo/config/firebase-adminsdk-*.json | python3 -m json.tool
   ```

3. **Verificar logs en detalle:**
   ```bash
   tail -f /var/log/odoo/odoo.log | grep -E "(Firebase|FCM|ERROR)"
   ```

4. **Test manual desde Python:**
   ```python
   from google.oauth2 import service_account
   
   creds = service_account.Credentials.from_service_account_file(
       '/opt/odoo/config/firebase-adminsdk-xxx.json',
       scopes=['https://www.googleapis.com/auth/firebase.messaging']
   )
   
   print("✓ Credenciales válidas")
   ```

---

## ✅ Final Verification

**Checklist completo:**

- [ ] ✅ Dependencias instaladas
- [ ] ✅ Archivos creados
- [ ] ✅ Sintaxis Python correcta
- [ ] ✅ Firebase configurado
- [ ] ✅ Módulo actualizado
- [ ] ✅ Parámetros configurados
- [ ] ✅ Base de datos OK
- [ ] ✅ Access rights OK
- [ ] ✅ Views creadas
- [ ] ✅ Menú visible
- [ ] ✅ API FCM funciona
- [ ] ✅ UI dispositivos funciona
- [ ] ✅ Notificaciones funcionan
- [ ] ✅ Sentinel API funciona

---

## 📊 Post-Installation

### Monitoreo

```sql
-- Ver estadísticas
SELECT 
    COUNT(*) as total_devices,
    COUNT(CASE WHEN active THEN 1 END) as active_devices,
    SUM(notification_count) as total_notifications
FROM adt_fcm_device;

-- Ver por plataforma
SELECT 
    platform,
    COUNT(*) as devices,
    SUM(notification_count) as notifications
FROM adt_fcm_device
WHERE active = true
GROUP BY platform;
```

---

## 🎉 Success!

Si todos los checks están ✅, el sistema está:

**✨ COMPLETAMENTE INSTALADO Y FUNCIONAL ✨**

Puedes proceder a:
1. Integrar con la app móvil
2. Configurar Firebase en la app
3. Probar notificaciones end-to-end

---

**Documentación adicional:**
- [FIREBASE_IMPLEMENTATION.md](FIREBASE_IMPLEMENTATION.md) - Documentación técnica completa
- [QUICK_START_FIREBASE.md](QUICK_START_FIREBASE.md) - Guía rápida de configuración
- [API_TESTING_GUIDE.md](API_TESTING_GUIDE.md) - Guía de testing con Postman

**¿Problemas?** Revisa la sección de Troubleshooting en cada documento.
