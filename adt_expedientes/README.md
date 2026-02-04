# ADT Expedientes - Sistema de Seguridad Móvil 🔐

## Arquitectura de Seguridad de Nivel Producción

Sistema completo de autenticación y autorización para APIs móviles con:

- ✅ **Tokens SHA256 hasheados** (nunca en texto claro)
- ✅ **Device binding** (un token por dispositivo)
- ✅ **Validación automática** en cada request
- ✅ **Revocación automática** al desactivar usuarios
- ✅ **Auditoría completa** de accesos
- ✅ **Rate limiting** anti-abuse
- ✅ **HTTP 401/403** estándar

---

## 🚀 Quick Start

### 1. Generar Token (Login desde App)

```bash
POST /adt_expedientes/mobile/token/create
Content-Type: application/json

{
  "db": "produccion",
  "login": "usuario@empresa.com",
  "password": "password123",
  "device_info": {
    "device_id": "550e8400-e29b-41d4-a716-446655440000",
    "device_name": "iPhone 13 Pro",
    "device_os": "iOS 15.1",
    "app_version": "1.0.0"
  },
  "days_valid": 30
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "token": "XYZABC...64_caracteres...XYZ",
    "expiry": "2026-03-05 10:30:00",
    "user": {"id": 5, "name": "Juan Pérez"}
  }
}
```

### 2. Usar Token en Requests

```bash
GET /adt_expedientes/mobile/expediente/by_asesora
Authorization: Bearer XYZABC...token...XYZ
```

### 3. Logout (Revocar Token)

```bash
POST /adt_expedientes/mobile/token/revoke
Authorization: Bearer XYZABC...token...XYZ
```

---

## 🔒 Características de Seguridad

### Validación Automática

En **CADA request**, el backend valida:
1. Token válido y activo
2. Token no expirado
3. Usuario activo en Odoo
4. Rate limiting (máx 100 req/min)

Si cualquier check falla → **401 Unauthorized**

### Revocación Automática

Los tokens se invalidan INMEDIATAMENTE cuando:
- ✅ Usuario es desactivado (`user.active = False`)
- ✅ Usuario es eliminado del sistema
- ✅ Token expira por fecha
- ✅ Se detecta actividad sospechosa

**Código implementado en `res.users`:**
```python
def write(self, vals):
    if 'active' in vals and not vals['active']:
        # Revocar TODOS los tokens del usuario
        self.env['adt.mobile.token'].sudo().revoke_all_user_tokens(
            self.id, reason='user_disabled'
        )
    return super().write(vals)
```

### Auditoría Completa

Tabla `adt.mobile.access.log` registra:
- Usuario, endpoint, método HTTP
- IP, timestamp, éxito/error
- Device ID, user agent

---

## 📱 Integración en App Móvil

### Almacenar Token (Seguro)

```dart
// ✅ SÍ - Usar almacenamiento seguro
final storage = FlutterSecureStorage();
await storage.write(key: 'auth_token', value: token);

// ❌ NO - SharedPreferences sin cifrar
// prefs.setString('token', token); // INSEGURO
```

### Interceptor HTTP

```dart
class AuthInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await secureStorage.read(key: 'auth_token');
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    return handler.next(options);
  }
  
  @override
  void onError(DioError err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      // Token inválido → Logout automático
      await _handleTokenExpired();
    }
    return handler.next(err);
  }
  
  Future<void> _handleTokenExpired() async {
    await secureStorage.delete(key: 'auth_token');
    navigatorKey.currentState?.pushNamedAndRemoveUntil('/login', (route) => false);
  }
}
```

### Manejo de Errores 401/403

```dart
try {
  final response = await dio.get('/endpoint');
} on DioError catch (e) {
  if (e.response?.statusCode == 401) {
    // Token expirado o revocado
    showDialog('Tu sesión ha expirado. Inicia sesión nuevamente.');
    await handleLogout();
  } else if (e.response?.statusCode == 403) {
    // Usuario desactivado
    showDialog('Tu cuenta ha sido desactivada. Contacta al administrador.');
    await handleLogout();
  }
}
```

---

## 🎯 Escenarios Críticos Resueltos

### ❌ Problema Original
**Usuario desactivado puede seguir enviando datos desde app abierta.**

### ✅ Solución Implementada

1. **Admin desactiva usuario en Odoo**
   ```python
   user.active = False  # Triggers write()
   ```

2. **Sistema revoca automáticamente TODOS sus tokens**
   ```python
   Token.revoke_all_user_tokens(user.id, 'user_disabled')
   ```

3. **Próximo request del app**
   ```python
   token_rec = Token.validate_token(plain_token)
   # token_rec is None (revoked) → 401 Unauthorized
   ```

4. **App detecta 401 y cierra sesión**
   ```dart
   if (statusCode == 401) {
     await logout();
     navigateToLogin();
   }
   ```

**Resultado:** Usuario pierde acceso en **el próximo request** ✅

---

## 📊 Monitoreo (Admin Odoo)

### Ver Tokens Activos

```python
tokens = env['adt.mobile.token'].search([
    ('active', '=', True),
    ('user_id', '=', user_id)
])

for t in tokens:
    print(f"{t.device_name} - Último uso: {t.last_used}")
```

### Revocar Token Manualmente

```python
# Desde vista de usuario o Python
Token.revoke_all_user_tokens(user_id, reason='manual')
```

### Ver Accesos Sospechosos

```python
Log = env['adt.mobile.access.log']
is_suspicious = Log.detect_suspicious_activity(user_id, minutes=5, max_requests=50)

if is_suspicious:
    # Alerta al administrador
    pass
```

---

## 🛡️ Mejores Prácticas

### ✅ DO
- Usar HTTPS en producción
- Almacenar tokens en Keychain/Keystore
- Implementar certificate pinning
- Limpiar token al logout
- Manejar 401/403 correctamente
- Usar device_id persistente (UUID)

### ❌ DON'T
- No usar HTTP
- No almacenar tokens sin cifrar
- No loguear tokens en consola
- No ignorar respuestas 401
- No confiar solo en validaciones cliente

---

## 📦 Instalación

1. Copiar módulo a `addons/`
2. Actualizar lista de apps en Odoo
3. Instalar "ADT Expedientes"
4. Los modelos y endpoints se crean automáticamente

---

## 🧪 Testing de Seguridad

### Test 1: Token Inválido
```bash
curl -H "Authorization: Bearer token_falso" https://api.com/endpoint
# Esperado: 401 Unauthorized
```

### Test 2: Usuario Desactivado
```python
user.active = False
# Hacer request con token del usuario
# Esperado: 403 Forbidden
```

### Test 3: Token Expirado
```python
token_rec, token = Token.generate_token(user_id, days_valid=0)
time.sleep(1)
result = Token.validate_token(token)
# Esperado: None (revocado automáticamente)
```

---

## 📚 Modelos Implementados

- `adt.mobile.token` - Tokens de autenticación (SHA256)
- `adt.mobile.access.log` - Log de auditoría
- `res.users` (extend) - Auto-revocación de tokens

---

## 🆘 Soporte

**Documentación completa:** Ver este README completo con todos los detalles de implementación.

**Versión:** 15.0.2.0.0  
**Última actualización:** Febrero 2026

---

## 🔐 Resumen Arquitectura

```
┌─────────────┐       ┌──────────────┐       ┌──────────────┐
│  Mobile App │  -->  │ Odoo Backend │  -->  │   Database   │
│             │       │              │       │              │
│ - Token     │       │ - Validate   │       │ - Tokens     │
│   Storage   │       │   Every Req  │       │   (SHA256)   │
│ - Auto      │       │ - Check User │       │ - Access Log │
│   Logout    │       │ - Rate Limit │       │ - Users      │
└─────────────┘       └──────────────┘       └──────────────┘

Flujo:
1. Login → Generate Token (SHA256 hash stored)
2. Request → Validate Token → Check User Active
3. If invalid → 401 → App logout automatically
4. Admin disables user → All tokens revoked INSTANTLY
```

**La última palabra la tiene SIEMPRE el backend. ✅**
