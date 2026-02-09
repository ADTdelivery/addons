# ✅ FCM Controller Actualizado - Usando Patrón de mobile_api.py

## 🔧 Cambios Realizados

He modificado `fcm_controller.py` para usar **exactamente el mismo patrón** de extracción de JSON que `mobile_api.py`.

### 📝 Patrón Aplicado

```python
# Extraer parámetros del JSON request (mismo patrón que mobile_api.py)
payload = {}
if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
    payload.update(request.jsonrequest)

fcm_token = fcm_token or token or payload.get('fcm_token') or payload.get('token')
platform = platform or payload.get('platform', 'android')
device_info = device_info or payload.get('device_info', {})
```

### ✅ Endpoints Actualizados

1. **`/adt/mobile/fcm/register`** - Ahora usa `request.jsonrequest`
2. **`/adt/mobile/fcm/unregister`** - Ahora usa `request.jsonrequest`

## 🚀 Cómo Usar

### Request Example

```bash
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN" \
  -d '{
    "token": "tu_fcm_token_aqui",
    "platform": "android"
  }'
```

### Desde Flutter/Dart

```dart
final response = await http.post(
  Uri.parse('$baseUrl/adt/mobile/fcm/register'),
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer $authToken',
  },
  body: jsonEncode({
    'token': fcmToken,
    'platform': 'android',
  }),
);

final data = jsonDecode(response.body);
print(data['result']['success']); // true
```

### Desde JavaScript

```javascript
const response = await fetch(`${baseUrl}/adt/mobile/fcm/register`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${authToken}`,
  },
  body: JSON.stringify({
    token: fcmToken,
    platform: 'android',
  }),
});

const data = await response.json();
console.log(data.result.success); // true
```

## ✅ Respuesta Esperada

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

## 📋 Parámetros Aceptados

| Parámetro | Alternativas | Tipo | Requerido | Default |
|-----------|--------------|------|-----------|---------|
| `fcm_token` | `token` | string | ✅ Sí | - |
| `platform` | - | string | ❌ No | `android` |
| `device_info` | - | object | ❌ No | `{}` |

## 🔍 Diferencia con Versión Anterior

### ❌ ANTES (No funcionaba)
```python
fcm_token = fcm_token or kwargs.get('fcm_token')
```

### ✅ AHORA (Funciona igual que mobile_api.py)
```python
payload = {}
if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
    payload.update(request.jsonrequest)

fcm_token = fcm_token or token or payload.get('fcm_token') or payload.get('token')
```

## 🎯 Consistencia con mobile_api.py

Ahora `fcm_controller.py` usa **exactamente el mismo patrón** que `mobile_api.py`:
- ✅ Extrae de `request.jsonrequest`
- ✅ Verifica con `hasattr` e `isinstance`
- ✅ Usa `payload.update()` para copiar el diccionario
- ✅ Fallback a parámetros de función
- ✅ Mismo estilo y estructura

## 📦 Instalación

```bash
# Actualizar el módulo
./odoo-bin -u adt_expedientes -d tu_bd

# O desde Odoo UI: Apps > ADT Expedientes > Actualizar
```

## ✅ Verificación

```bash
# Test rápido
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token":"test123"}'

# Respuesta esperada:
# {
#   "jsonrpc": "2.0",
#   "id": null,
#   "result": {
#     "success": true,
#     "message": "Token FCM registrado correctamente",
#     "device_id": 1
#   }
# }
```

---

**✅ Ahora `fcm_controller.py` usa el mismo patrón probado de `mobile_api.py`!**
