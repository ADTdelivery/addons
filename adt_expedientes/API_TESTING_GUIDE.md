# 🧪 API Testing Guide - Firebase + Sentinel

## 📋 Colección Postman

### Variables de entorno

Crear un environment con:

```json
{
  "base_url": "http://localhost:8069",
  "db": "tu_base_datos",
  "login": "usuario_test",
  "password": "contraseña",
  "auth_token": "",
  "fcm_token": "test_fcm_token_123"
}
```

---

## 🔐 1. Autenticación

### 1.1 Crear Token de Autenticación

**POST** `{{base_url}}/adt_expedientes/mobile/token/create`

**Headers:**
```
Content-Type: application/json
```

**Body (raw JSON):**
```json
{
  "db": "{{db}}",
  "login": "{{login}}",
  "password": "{{password}}",
  "device_info": {
    "device_id": "test-device-uuid-123",
    "device_name": "Postman Test Device",
    "device_os": "Postman Runner",
    "app_version": "1.0.0"
  },
  "days_valid": 30
}
```

**Response esperado:**
```json
{
  "success": true,
  "data": {
    "token": "a1b2c3d4e5f6...",
    "user_id": 8,
    "user_name": "Test User",
    "expires_at": "2026-03-10T10:30:00"
  }
}
```

**Tests (Postman):**
```javascript
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

pm.test("Response has success", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.success).to.eql(true);
});

pm.test("Token received", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.data.token).to.exist;
    pm.environment.set("auth_token", jsonData.data.token);
});
```

---

## 🔔 2. FCM - Gestión de Tokens

### 2.1 Registrar Token FCM

**POST** `{{base_url}}/adt/mobile/fcm/register`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer {{auth_token}}
```

**Body:**
```json
{
  "fcm_token": "{{fcm_token}}",
  "platform": "android",
  "device_info": {
    "device_id": "test-uuid-456",
    "device_name": "Samsung Galaxy S21",
    "device_os": "Android 12",
    "app_version": "1.0.0"
  }
}
```

**Response esperado:**
```json
{
  "success": true,
  "message": "Token FCM registrado correctamente",
  "device_id": 15,
  "device_name": "Samsung Galaxy S21"
}
```

**Tests:**
```javascript
pm.test("FCM token registered", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.success).to.eql(true);
    pm.expect(jsonData.device_id).to.exist;
});
```

---

### 2.2 Listar Dispositivos FCM

**POST** `{{base_url}}/adt/mobile/fcm/devices`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer {{auth_token}}
```

**Body:**
```json
{}
```

**Response esperado:**
```json
{
  "success": true,
  "devices": [
    {
      "id": 1,
      "device_name": "Samsung Galaxy S21",
      "platform": "android",
      "device_os": "Android 12",
      "active": true,
      "last_seen": "2026-02-08T10:30:00",
      "notification_count": 5,
      "app_version": "1.0.0"
    }
  ]
}
```

---

### 2.3 Desactivar Token FCM

**POST** `{{base_url}}/adt/mobile/fcm/unregister`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer {{auth_token}}
```

**Body:**
```json
{
  "fcm_token": "{{fcm_token}}"
}
```

**Response esperado:**
```json
{
  "success": true,
  "message": "Token FCM desactivado correctamente"
}
```

---

## 🛡️ 3. Sentinel API

### 3.1 Consultar Reporte Vigente

**POST** `{{base_url}}/api/sentinel/report/get`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer {{auth_token}}
```

**Body:**
```json
{
  "document_number": "12345678"
}
```

**Response (existe):**
```json
{
  "success": true,
  "data": {
    "id": 15,
    "document_number": "12345678",
    "query_date": "2026-02-05",
    "query_user": "María Torres",
    "state": "vigente",
    "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
    "image_filename": "sentinel_12345678.jpg"
  }
}
```

**Response (no existe):**
```json
{
  "success": true,
  "data": null
}
```

**Tests:**
```javascript
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

pm.test("Response structure valid", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.success).to.eql(true);
    pm.expect(jsonData.data).to.exist;
});
```

---

### 3.2 Crear Nuevo Reporte Sentinel

**POST** `{{base_url}}/api/sentinel/report/create`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer {{auth_token}}
```

**Body:**
```json
{
  "document_number": "87654321",
  "image_base64": "/9j/4AAQSkZJRgABAQAAAQABAAD...",
  "image_filename": "sentinel_87654321.png",
  "query_user_id": 8,
  "query_date": "2026-02-08",
  "notes": "Consulta de prueba desde Postman"
}
```

**Response OK:**
```json
{
  "success": true,
  "message": "Reporte Sentinel registrado correctamente",
  "record_id": 16
}
```

**Response Error (ya existe):**
```json
{
  "success": false,
  "error": "existing_current_month",
  "message": "Ya existe un reporte vigente este mes",
  "data": {
    "id": 15,
    "query_date": "2026-02-05",
    "query_user": "María Torres"
  }
}
```

**Tests:**
```javascript
pm.test("Report created or already exists", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.success).to.exist;
    
    if (jsonData.success) {
        pm.expect(jsonData.record_id).to.exist;
    } else {
        pm.expect(jsonData.error).to.eql("existing_current_month");
    }
});
```

---

## 🔄 4. Flujo Completo de Prueba

### Secuencia de Prueba End-to-End

```
1. Login (crear token de autenticación)
   ↓
2. Registrar token FCM
   ↓
3. Listar dispositivos (verificar registro)
   ↓
4. Consultar reporte Sentinel (DNI sin reporte)
   ↓
5. Crear reporte Sentinel
   ↓
6. Consultar reporte Sentinel (verificar que existe)
   ↓
7. [Desde Odoo UI] Cambiar estado de expediente
   ↓
8. [App móvil] Recibir notificación push
```

---

## 🧪 5. Tests Automatizados

### Collection Tests (ejecutar antes de cada request)

**Pre-request Script:**
```javascript
// Verificar que tenemos token
if (!pm.environment.get("auth_token")) {
    console.log("No auth token found. Run login first.");
}
```

**Tests globales:**
```javascript
pm.test("Response time is less than 2000ms", function () {
    pm.expect(pm.response.responseTime).to.be.below(2000);
});

pm.test("Content-Type is application/json", function () {
    pm.response.to.have.header("Content-Type", /application\/json/);
});
```

---

## 🔍 6. Validación de Errores

### 6.1 Sin autenticación

**Request sin header Authorization**

**Response esperado:**
```json
{
  "success": false,
  "error": "Authentication required",
  "message": "No se proporcionó token de autenticación."
}
```

---

### 6.2 Token expirado

**Request con token inválido/expirado**

**Response esperado:**
```json
{
  "success": false,
  "error": "Invalid or expired token",
  "message": "Tu sesión ha expirado. Por favor inicia sesión nuevamente."
}
```

---

### 6.3 DNI inválido (Sentinel)

**Body con DNI mal formado:**
```json
{
  "document_number": "123"
}
```

**Response esperado:**
```json
{
  "success": false,
  "error": "document_number must be 8 digits"
}
```

---

## 📊 7. Newman (CLI Testing)

### Instalar Newman

```bash
npm install -g newman
```

### Exportar colección Postman

1. En Postman: Click **⋯** > **Export**
2. Guardar como `firebase_api_tests.postman_collection.json`

### Ejecutar tests

```bash
# Ejecutar colección completa
newman run firebase_api_tests.postman_collection.json \
  --environment production.postman_environment.json \
  --reporters cli,html \
  --reporter-html-export report.html

# Ejecutar solo una carpeta
newman run firebase_api_tests.postman_collection.json \
  --folder "FCM Tests"

# Con delay entre requests
newman run firebase_api_tests.postman_collection.json \
  --delay-request 500
```

---

## 🎯 8. Casos de Prueba Críticos

### Checklist de Testing

- [ ] ✅ Login exitoso genera token válido
- [ ] ✅ Login con credenciales incorrectas falla
- [ ] ✅ Registrar token FCM con token válido
- [ ] ✅ Registrar token FCM sin autenticación falla
- [ ] ✅ Listar dispositivos muestra dispositivos registrados
- [ ] ✅ Desactivar token FCM funciona correctamente
- [ ] ✅ Consultar reporte Sentinel inexistente retorna null
- [ ] ✅ Crear reporte Sentinel con imagen base64
- [ ] ✅ Crear reporte duplicado (mismo mes) falla
- [ ] ✅ Consultar reporte Sentinel existente retorna datos
- [ ] ✅ Validación de DNI (8 dígitos) funciona
- [ ] ✅ Tokens expirados son rechazados
- [ ] ✅ Usuario desactivado no puede usar token

---

## 📱 9. Test desde App Móvil (Flutter/React Native)

### Flutter Example

```dart
// 1. Login
final response = await http.post(
  Uri.parse('$baseUrl/adt_expedientes/mobile/token/create'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({
    'db': 'mi_bd',
    'login': 'usuario',
    'password': 'pass',
  }),
);

final authToken = jsonDecode(response.body)['data']['token'];

// 2. Registrar FCM Token
final fcmToken = await FirebaseMessaging.instance.getToken();

await http.post(
  Uri.parse('$baseUrl/adt/mobile/fcm/register'),
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer $authToken',
  },
  body: jsonEncode({
    'fcm_token': fcmToken,
    'platform': 'android',
  }),
);

// 3. Escuchar notificaciones
FirebaseMessaging.onMessage.listen((RemoteMessage message) {
  print('Notificación recibida: ${message.notification?.title}');
  print('Data: ${message.data}');
  
  // Navegar al expediente
  if (message.data['expediente_id'] != null) {
    Navigator.push(/* ... */);
  }
});
```

---

## 🐛 10. Debug Tips

### Ver logs en tiempo real

```bash
# Odoo logs
tail -f /var/log/odoo/odoo.log | grep -E "(FCM|Firebase|Sentinel)"

# Filtrar solo errores
tail -f /var/log/odoo/odoo.log | grep -E "ERROR.*FCM"

# Filtrar solo notificaciones enviadas
tail -f /var/log/odoo/odoo.log | grep "Notificación FCM enviada"
```

### Ver requests en Odoo

```bash
# Activar modo debug en odoo.conf
log_level = debug
log_handler = odoo.http.rpc.request:DEBUG
```

### Verificar tokens en BD

```sql
-- Ver tokens FCM activos
SELECT 
    u.login,
    f.device_name,
    f.platform,
    f.notification_count,
    f.last_seen
FROM adt_fcm_device f
JOIN res_users u ON f.user_id = u.id
WHERE f.active = true;

-- Ver estadísticas
SELECT 
    platform,
    COUNT(*) as total,
    SUM(notification_count) as notificaciones
FROM adt_fcm_device
WHERE active = true
GROUP BY platform;
```

---

**✅ Colección completa de tests lista para usar!**
