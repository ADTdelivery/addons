# 🔒 TEST DE SEGURIDAD - ENDPOINTS PROTEGIDOS

## Cambios Aplicados

Se eliminó el **fallback de autenticación por sesión** en el método `_authenticate_request()`.

Ahora **TODOS** los endpoints móviles requieren obligatoriamente un token Bearer válido en el header `Authorization`.

---

## 🧪 Pruebas desde Postman

### ❌ TEST 1: SIN TOKEN (Debe Fallar)

**Endpoint:** `POST /adt_expedientes/mobile/expediente/summary_by_asesora`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
    "jsonrpc": "2.0",
    "params": {
        "asesora_id": 1
    }
}
```

**Respuesta Esperada (401 Unauthorized):**
```json
{
    "jsonrpc": "2.0",
    "id": null,
    "result": {
        "success": false,
        "error": "Authentication required - Token missing",
        "code": 401,
        "message": "No se proporcionó token de autenticación. Por favor inicia sesión."
    }
}
```

---

### ✅ TEST 2: CON TOKEN VÁLIDO (Debe Funcionar)

**Paso 1: Obtener Token**

`POST /adt_expedientes/mobile/token/create`

**Body:**
```json
{
    "jsonrpc": "2.0",
    "params": {
        "db": "tu_base_datos",
        "login": "admin",
        "password": "admin",
        "device_info": {
            "device_id": "test-postman-123",
            "device_name": "Postman Test",
            "device_os": "Postman",
            "app_version": "1.0.0"
        }
    }
}
```

**Respuesta:**
```json
{
    "jsonrpc": "2.0",
    "id": null,
    "result": {
        "success": true,
        "data": {
            "token": "abc123...xyz789",
            "expiry": "2026-03-06 10:00:00",
            "user": {
                "id": 2,
                "name": "Admin"
            }
        }
    }
}
```

**Paso 2: Usar el Token**

`POST /adt_expedientes/mobile/expediente/summary_by_asesora`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer abc123...xyz789
```

**Body:**
```json
{
    "jsonrpc": "2.0",
    "params": {
        "asesora_id": 2
    }
}
```

**Respuesta Esperada (200 OK):**
```json
{
    "jsonrpc": "2.0",
    "id": null,
    "result": {
        "success": true,
        "data": [...]
    }
}
```

---

### ❌ TEST 3: CON TOKEN INVÁLIDO (Debe Fallar)

**Headers:**
```
Content-Type: application/json
Authorization: Bearer token_falso_12345
```

**Respuesta Esperada (401 Unauthorized):**
```json
{
    "jsonrpc": "2.0",
    "id": null,
    "result": {
        "success": false,
        "error": "Invalid or expired token",
        "code": 401,
        "message": "Tu sesión ha expirado o tu cuenta fue desactivada. Por favor inicia sesión nuevamente."
    }
}
```

---

### ❌ TEST 4: CON USUARIO DESACTIVADO (Debe Fallar)

1. Desactiva el usuario desde Odoo (Settings → Users → Desactivar)
2. Intenta usar el token del usuario desactivado

**Respuesta Esperada (403 Forbidden):**
```json
{
    "jsonrpc": "2.0",
    "id": null,
    "result": {
        "success": false,
        "error": "User account disabled",
        "code": 403,
        "message": "Tu cuenta ha sido desactivada. Contacta al administrador."
    }
}
```

---

## 📋 Endpoints Protegidos

Todos estos endpoints ahora requieren token obligatoriamente:

1. ✅ `/adt_expedientes/mobile/partner/find_by_dni`
2. ✅ `/adt_expedientes/mobile/partner/create`
3. ✅ `/adt_expedientes/mobile/partner/update`
4. ✅ `/adt_expedientes/mobile/partner/search_by_dni`
5. ✅ `/adt_expedientes/mobile/partner/card`
6. ✅ `/adt_expedientes/mobile/expediente/create`
7. ✅ `/adt_expedientes/mobile/expediente/update`
8. ✅ `/adt_expedientes/mobile/expediente/get`
9. ✅ `/adt_expedientes/mobile/expediente/upload_image`
10. ✅ `/adt_expedientes/mobile/expediente/set_doc_state`
11. ✅ `/adt_expedientes/mobile/expediente/finalize`
12. ✅ `/adt_expedientes/mobile/expediente/progress`
13. ✅ `/adt_expedientes/mobile/expedientes/by_asesora`
14. ✅ **`/adt_expedientes/mobile/expediente/summary_by_asesora`** ← Confirmado protegido

---

## 🔓 Endpoints Públicos (Sin Token)

Solo estos dos endpoints NO requieren token:

1. `/adt_expedientes/mobile/token/create` - Login (crear token)
2. `/adt_expedientes/mobile/token/revoke` - Logout (revocar token)

---

## ⚠️ Importante

Después de aplicar este cambio:

1. **Reinicia el servicio de Odoo**
2. Limpia las cookies del navegador si estabas probando desde ahí
3. Usa **siempre** el header `Authorization: Bearer <token>` en Postman
4. Si tienes tokens antiguos, créalos nuevamente con `/token/create`

---

## 🛡️ Seguridad Garantizada

Con este cambio:

✅ **NO** se puede acceder sin token  
✅ **NO** se puede usar cookies de sesión  
✅ **NO** se puede usar tokens expirados  
✅ **NO** se puede usar tokens de usuarios desactivados  
✅ **SÍ** se valida el token en cada request  
✅ **SÍ** se registra cada acceso en auditoría  

---

**Fecha de aplicación:** 4 de febrero de 2026
**Archivo modificado:** `/controllers/mobile_api.py`
**Método modificado:** `_authenticate_request()` (líneas 50-96)
