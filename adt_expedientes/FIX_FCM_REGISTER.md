# 🔧 Fix: Endpoint FCM Register

## ✅ Problema Resuelto

El endpoint `/adt/mobile/fcm/register` es un endpoint JSON-RPC de Odoo que acepta parámetros JSON directamente en el body.

## 📝 Cambios Realizados

### 1. Extracción correcta de parámetros
- El endpoint ahora extrae parámetros correctamente de `kwargs`
- Acepta tanto `fcm_token` como `token`
- Platform tiene valor por defecto `android`

## 🚀 Cómo Enviar el Request

### ⚠️ IMPORTANTE: Formato JSON-RPC

El endpoint usa `type='json'` de Odoo, que significa que espera **JSON directo en el body**, no JSON-RPC wrapped.

### ✅ Formato Correcto

**Ejemplo mínimo:**
```bash
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AUTH" \
  -d '{
    "token": "dXYz123abc..."
  }'
```

**Ejemplo completo:**
```bash
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AUTH" \
  -d '{
    "fcm_token": "dXYz123abc...",
    "platform": "android",
    "device_info": {
      "device_id": "uuid-123",
      "device_name": "Samsung S21",
      "device_os": "Android 12",
      "app_version": "1.0.0"
    }
  }'
```

## 💻 Desde Código

### Flutter/Dart
```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

Future<void> registerFCMToken(String authToken, String fcmToken) async {
  final response = await http.post(
    Uri.parse('http://localhost:8069/adt/mobile/fcm/register'),
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $authToken',
    },
    body: jsonEncode({
      'token': fcmToken,  // ✅ Funciona
      'platform': 'android',
    }),
  );

  final result = jsonDecode(response.body);
  print(result['result']); // Acceder al resultado
}
```

### JavaScript/React Native
```javascript
async function registerFCMToken(authToken, fcmToken) {
  const response = await fetch('http://localhost:8069/adt/mobile/fcm/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      token: fcmToken,  // ✅ Funciona
      platform: 'android',
    }),
  });

  const data = await response.json();
  console.log(data.result); // Acceder al resultado
}
```

### Python
```python
import requests

def register_fcm_token(auth_token, fcm_token):
    url = 'http://localhost:8069/adt/mobile/fcm/register'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {auth_token}',
    }
    payload = {
        'token': fcm_token,  # ✅ Funciona
        'platform': 'android',
    }
    
    response = requests.post(url, json=payload, headers=headers)
    result = response.json()
    print(result['result'])  # Acceder al resultado
```

## ✅ Respuestas

### Success
```json
{
  "jsonrpc": "2.0",
  "id": null,
  "result": {
    "success": true,
    "message": "Token FCM registrado correctamente",
    "device_id": 15,
    "device_name": "Samsung S21"
  }
}
```

### Error: Sin token
```json
{
  "jsonrpc": "2.0",
  "id": null,
  "result": {
    "success": false,
    "error": "Missing fcm_token",
    "message": "El token FCM es requerido."
  }
}
```

### Error: Sin autenticación
```json
{
  "jsonrpc": "2.0",
  "id": null,
  "result": {
    "success": false,
    "error": "Authentication required",
    "message": "No se proporcionó token de autenticación."
  }
}
```

## 📋 Parámetros Aceptados

El endpoint acepta los parámetros directamente en el JSON del body:

| Parámetro | Alternativa | Tipo | Requerido | Default | Descripción |
|-----------|-------------|------|-----------|---------|-------------|
| `fcm_token` | `token` | string | ✅ Sí | - | Token FCM del dispositivo |
| `platform` | - | string | ❌ No | `android` | `android`, `ios` o `web` |
| `device_info` | - | object | ❌ No | `{}` | Info del dispositivo |

### Opciones de envío del token:

**Opción 1:** (Recomendado)
```json
{ "fcm_token": "tu_token" }
```

**Opción 2:** (También funciona)
```json
{ "token": "tu_token" }
```

## 🔐 Headers Requeridos

```
Content-Type: application/json
Authorization: Bearer TU_TOKEN_DE_AUTENTICACION
```

## 📝 Nota Importante

La respuesta viene envuelta en JSON-RPC, por lo que debes acceder al resultado así:

```javascript
// ✅ Correcto
const success = response.data.result.success;

// ❌ Incorrecto
const success = response.data.success;
```

## ✅ Listo para usar

El endpoint ahora extrae correctamente los parámetros del JSON que envías en el body.
