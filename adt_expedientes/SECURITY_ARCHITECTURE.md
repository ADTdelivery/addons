# 🔐 Arquitectura de Seguridad - Documentación Técnica

## Sistema de Autenticación Token-Based para APIs Móviles

**Versión:** 15.0.3.0.0  
**Fecha:** Febrero 2026  
**Autor:** Equipo ADT Security

---

## 📐 Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MOBILE APPLICATION                          │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ Secure       │  │ HTTP         │  │ Error Handler           │  │
│  │ Storage      │  │ Interceptor  │  │ - Detect 401/403        │  │
│  │ (Keychain)   │  │ - Inject     │  │ - Auto logout           │  │
│  │              │  │   Token      │  │ - Navigate to login     │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬─────────────────┘  │
└─────────┼──────────────────┼──────────────────┼────────────────────┘
          │                  │                  │
          │ Store/Read       │ Authorization:   │ Handle
          │ Token            │ Bearer <token>   │ Errors
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ODOO BACKEND (API)                          │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │              mobile_api.py (Controller)                     │   │
│  │  ┌──────────────────────────────────────────────────────┐  │   │
│  │  │  _authenticate_request()                             │  │   │
│  │  │    1. Extract token from Authorization header        │  │   │
│  │  │    2. Call Token.validate_token(plain_token)         │  │   │
│  │  │    3. Return (user, token, error) tuple              │  │   │
│  │  └──────────────────────────────────────────────────────┘  │   │
│  │                                                              │   │
│  │  Endpoints:                                                  │   │
│  │    POST /token/create  → Generate new token                 │   │
│  │    POST /token/revoke  → Revoke token (logout)              │   │
│  │    All other endpoints → Require valid token                │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │           adt.mobile.token (Model)                          │   │
│  │  ┌──────────────────────────────────────────────────────┐  │   │
│  │  │  validate_token(plain_token, request_info)           │  │   │
│  │  │    1. Hash token (SHA256)                            │  │   │
│  │  │    2. Search in DB (active=True)                     │  │   │
│  │  │    3. Check expiry date                              │  │   │
│  │  │    4. Check user.active                              │  │   │
│  │  │    5. Rate limiting check                            │  │   │
│  │  │    6. Update last_used, requests_count               │  │   │
│  │  │    7. Log access (adt.mobile.access.log)             │  │   │
│  │  │    8. Return token record or None                    │  │   │
│  │  └──────────────────────────────────────────────────────┘  │   │
│  │                                                              │   │
│  │  generate_token(user_id, days_valid, device_info)           │   │
│  │    → Returns (token_record, plain_token_string)             │   │
│  │                                                              │   │
│  │  revoke_all_user_tokens(user_id, reason)                    │   │
│  │    → Marks all user tokens as active=False                  │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │           res.users (Extended Model)                        │   │
│  │  ┌──────────────────────────────────────────────────────┐  │   │
│  │  │  write(vals)                                         │  │   │
│  │  │    if 'active' in vals and not vals['active']:      │  │   │
│  │  │      Token.revoke_all_user_tokens(user_id)          │  │   │
│  │  │    return super().write(vals)                        │  │   │
│  │  └──────────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────────┐  │   │
│  │  │  unlink()                                            │  │   │
│  │  │    Token.revoke_all_user_tokens(user_id)            │  │   │
│  │  │    return super().unlink()                           │  │   │
│  │  └──────────────────────────────────────────────────────┘  │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       POSTGRESQL DATABASE                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐      │
│  │  adt_mobile_token                                        │      │
│  │  ─────────────────────────────────────────────────────  │      │
│  │  id | token (SHA256) | user_id | active | expiry       │      │
│  │  device_id | device_name | device_os | app_version     │      │
│  │  requests_count | last_used | revoked_at | revoked_by  │      │
│  │  revoked_reason | issued_at | ip_address                │      │
│  └─────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐      │
│  │  adt_mobile_access_log                                   │      │
│  │  ─────────────────────────────────────────────────────  │      │
│  │  id | token_id | user_id | endpoint | method            │      │
│  │  ip_address | success | error_message | timestamp       │      │
│  │  device_id | user_agent | response_time                 │      │
│  └─────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐      │
│  │  res_users (Odoo Core)                                   │      │
│  │  ─────────────────────────────────────────────────────  │      │
│  │  id | login | password | active | ...                   │      │
│  └─────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo Detallado de Autenticación

### 1. Login (Generar Token)

```
┌─────┐                              ┌─────┐                    ┌──────┐
│ App │                              │ API │                    │  DB  │
└──┬──┘                              └──┬──┘                    └───┬──┘
   │                                    │                           │
   │ POST /token/create                 │                           │
   │ {db, login, pwd, device_info}      │                           │
   ├───────────────────────────────────>│                           │
   │                                    │                           │
   │                                    │ Authenticate user         │
   │                                    ├──────────────────────────>│
   │                                    │<──────────────────────────┤
   │                                    │ User validated            │
   │                                    │                           │
   │                                    │ Generate random token     │
   │                                    │ (secrets.token_urlsafe)   │
   │                                    │                           │
   │                                    │ Hash token (SHA256)       │
   │                                    │                           │
   │                                    │ Revoke old tokens         │
   │                                    │ (same device_id)          │
   │                                    ├──────────────────────────>│
   │                                    │<──────────────────────────┤
   │                                    │                           │
   │                                    │ Insert new token          │
   │                                    │ (hash, device_info, etc)  │
   │                                    ├──────────────────────────>│
   │                                    │<──────────────────────────┤
   │                                    │                           │
   │ {success, token, expiry, user}     │                           │
   │<───────────────────────────────────┤                           │
   │                                    │                           │
   │ Store token in Keychain            │                           │
   │                                    │                           │
```

### 2. Request Autenticado

```
┌─────┐                              ┌─────┐                    ┌──────┐
│ App │                              │ API │                    │  DB  │
└──┬──┘                              └──┬──┘                    └───┬──┘
   │                                    │                           │
   │ GET /endpoint                      │                           │
   │ Authorization: Bearer <token>      │                           │
   ├───────────────────────────────────>│                           │
   │                                    │                           │
   │                                    │ Extract token from header │
   │                                    │                           │
   │                                    │ Hash token (SHA256)       │
   │                                    │                           │
   │                                    │ SELECT * FROM token       │
   │                                    │ WHERE token=hash          │
   │                                    │   AND active=true         │
   │                                    ├──────────────────────────>│
   │                                    │<──────────────────────────┤
   │                                    │ Token record              │
   │                                    │                           │
   │                                    │ Check expiry < now()      │
   │                                    │ Check user.active         │
   │                                    │ Check rate limit          │
   │                                    │                           │
   │                                    │ Update last_used          │
   │                                    │ Increment requests_count  │
   │                                    ├──────────────────────────>│
   │                                    │<──────────────────────────┤
   │                                    │                           │
   │                                    │ Insert access_log         │
   │                                    ├──────────────────────────>│
   │                                    │<──────────────────────────┤
   │                                    │                           │
   │                                    │ Execute business logic    │
   │                                    │ (create expediente, etc)  │
   │                                    │                           │
   │ {success, data: {...}}             │                           │
   │<───────────────────────────────────┤                           │
   │                                    │                           │
```

### 3. Usuario Desactivado

```
┌───────┐                    ┌─────┐              ┌──────┐          ┌─────┐
│ Admin │                    │ API │              │  DB  │          │ App │
└───┬───┘                    └──┬──┘              └───┬──┘          └──┬──┘
    │                           │                     │                │
    │ user.active = False       │                     │                │
    ├──────────────────────────>│                     │                │
    │                           │                     │                │
    │                           │ res.users.write()   │                │
    │                           │ triggers override   │                │
    │                           │                     │                │
    │                           │ revoke_all_tokens() │                │
    │                           │                     │                │
    │                           │ UPDATE token        │                │
    │                           │ SET active=false    │                │
    │                           │ WHERE user_id=X     │                │
    │                           ├────────────────────>│                │
    │                           │<────────────────────┤                │
    │                           │ Tokens revoked      │                │
    │                           │                     │                │
    │ ✅ User deactivated       │                     │                │
    │<──────────────────────────┤                     │                │
    │                           │                     │                │
    │                           │                     │ User makes req │
    │                           │                     │<───────────────┤
    │                           │ validate_token()    │                │
    │                           │ → Returns None      │                │
    │                           │ (token revoked)     │                │
    │                           │                     │                │
    │                           │ 401 Unauthorized    │                │
    │                           ├────────────────────────────────────>│
    │                           │                     │                │
    │                           │                     │ Detect 401     │
    │                           │                     │ Delete token   │
    │                           │                     │ Navigate login │
    │                           │                     │                │
```

---

## 🔒 Medidas de Seguridad Implementadas

### 1. **Hashing de Tokens (SHA256)**

**❌ Problema:** Almacenar tokens en texto claro es un riesgo crítico.
**✅ Solución:** Solo almacenamos el hash SHA256 del token.

```python
# Generación
plain_token = secrets.token_urlsafe(48)  # 64 caracteres
token_hash = hashlib.sha256(plain_token.encode()).hexdigest()

# Almacenar solo el hash
rec.token = token_hash  # SHA256 hash

# Validación
received_hash = hashlib.sha256(received_token.encode()).hexdigest()
rec = search([('token', '=', received_hash)])
```

**Ventaja:** Si alguien accede a la BD, NO puede usar los tokens (solo tiene hashes).

### 2. **Device Binding (Un Token por Dispositivo)**

**❌ Problema:** Usuario puede tener tokens de múltiples dispositivos sin control.
**✅ Solución:** Un dispositivo = un token activo.

```python
if device_data.get('device_id'):
    old_tokens = search([
        ('user_id', '=', user_id),
        ('device_id', '=', device_data.get('device_id')),
        ('active', '=', True)
    ])
    old_tokens.write({'active': False})  # Revocar antiguos
```

**Ventaja:** Control total de sesiones por dispositivo.

### 3. **Validación en Cada Request**

**❌ Problema:** App guarda user_id localmente y lo envía sin validar en backend.
**✅ Solución:** Backend valida SIEMPRE el token.

```python
def _authenticate_request(self):
    # Extraer token
    # Validar token (hash, expiry, user active, rate limit)
    # Si falla cualquier check → 401
    # Si ok → continuar
```

**Ventaja:** Backend tiene SIEMPRE la última palabra.

### 4. **Revocación Automática**

**❌ Problema:** Usuario desactivado puede seguir usando la app.
**✅ Solución:** Override de `write()` y `unlink()` en `res.users`.

```python
def write(self, vals):
    if 'active' in vals and not vals['active']:
        self.env['adt.mobile.token'].revoke_all_user_tokens(self.id)
    return super().write(vals)
```

**Ventaja:** Tokens revocados INSTANTÁNEAMENTE al desactivar usuario.

### 5. **Rate Limiting**

**❌ Problema:** Ataque de fuerza bruta o abuso de API.
**✅ Solución:** Límite de 100 requests por minuto por token.

```python
if rec.last_request_time:
    diff = (now - last_req).total_seconds()
    if diff < 0.6:  # < 0.6 seg entre requests
        _logger.warning('Rate limit hit')
        # Opcional: revocar token
```

**Ventaja:** Protección contra abuso.

### 6. **Auditoría Completa**

**❌ Problema:** No hay trazabilidad de quién accede y cuándo.
**✅ Solución:** Log de cada acceso en `adt.mobile.access.log`.

```python
self.env['adt.mobile.access.log'].sudo().create({
    'token_id': rec.id,
    'user_id': rec.user_id.id,
    'endpoint': request_info.get('endpoint'),
    'ip_address': request_info.get('ip'),
    'success': True,
})
```

**Ventaja:** Trazabilidad completa para auditorías y detección de anomalías.

---

## 🎯 Casos de Uso Críticos

### Caso 1: Empleado Despedido

**Escenario:**
- Empleado es despedido
- Aún tiene la app instalada
- Podría enviar información malintencionada

**Solución:**
1. Admin desactiva usuario en Odoo
2. `res.users.write()` detecta `active=False`
3. Todos los tokens del usuario son revocados automáticamente
4. Próximo request del ex-empleado → **401 Unauthorized**
5. App detecta 401 → cierra sesión → redirige a login

**Resultado:** Ex-empleado pierde acceso INMEDIATAMENTE ✅

### Caso 2: Dispositivo Perdido/Robado

**Escenario:**
- Usuario pierde su celular
- Ladrón tiene acceso a la app abierta

**Solución:**
1. Usuario contacta soporte
2. Soporte busca tokens del usuario
3. Revoca manualmente el token del dispositivo perdido
4. Otros dispositivos del usuario siguen funcionando

**Código:**
```python
token = env['adt.mobile.token'].search([
    ('user_id', '=', user_id),
    ('device_id', '=', 'UUID-del-dispositivo-perdido')
])
token.write({'active': False, 'revoked_reason': 'manual'})
```

### Caso 3: Token Expirado

**Escenario:**
- Token de 30 días cumple su ciclo
- Usuario intenta usarlo

**Solución:**
1. App envía request con token
2. `validate_token()` compara `expiry < now()`
3. Token es marcado como revocado automáticamente
4. Retorna **401**
5. App solicita re-login

### Caso 4: Ataque de Fuerza Bruta

**Escenario:**
- Atacante intenta muchos requests rápidos

**Detección:**
1. Rate limiting detecta > 100 req/min
2. Log registra IP y patrón
3. Opcional: auto-revocar token
4. Admin es notificado

**Código:**
```python
suspicious = Log.detect_suspicious_activity(user_id, minutes=5, max_requests=50)
if suspicious:
    Token.revoke_all_user_tokens(user_id, reason='suspicious')
```

---

## 📊 Modelo de Datos Detallado

### adt_mobile_token

| Campo | Tipo | Descripción | Index |
|-------|------|-------------|-------|
| id | Integer | PK | ✅ |
| token | Char(64) | SHA256 hash (no texto claro) | ✅ Unique |
| user_id | Many2one(res.users) | Usuario dueño | ✅ |
| active | Boolean | Estado (False = revocado) | ✅ |
| expiry | Datetime | Fecha de expiración | ✅ |
| issued_at | Datetime | Fecha de creación | - |
| last_used | Datetime | Último acceso | - |
| device_id | Char | UUID del dispositivo | ✅ |
| device_name | Char | Ej: "iPhone 13 Pro" | - |
| device_os | Char | Ej: "iOS 15.1" | - |
| app_version | Char | Versión de la app | - |
| requests_count | Integer | Total de requests | - |
| last_request_time | Datetime | Para rate limiting | - |
| revoked_at | Datetime | Cuándo se revocó | - |
| revoked_by | Many2one(res.users) | Quién lo revocó | - |
| revoked_reason | Selection | manual/expired/user_disabled/etc | - |
| ip_address | Char | IP al generar | - |

**Constraints:**
- `token` debe ser único (`unique constraint`)

### adt_mobile_access_log

| Campo | Tipo | Descripción | Index |
|-------|------|-------------|-------|
| id | Integer | PK | ✅ |
| token_id | Many2one(adt.mobile.token) | Token usado | ✅ |
| user_id | Many2one(res.users) | Usuario | ✅ |
| endpoint | Char | Ruta API | ✅ |
| method | Char | GET/POST/PUT/DELETE | - |
| ip_address | Char | IP origen | ✅ |
| success | Boolean | True/False | ✅ |
| error_message | Text | Error si falló | - |
| timestamp | Datetime | Fecha/hora | ✅ |
| device_id | Char | Device ID | ✅ |
| user_agent | Char | User agent | - |
| response_time | Float | Tiempo de respuesta (ms) | - |

---

## 🔧 Configuración y Mantenimiento

### Tareas CRON Recomendadas

#### 1. Limpieza de Tokens Expirados
**Frecuencia:** Cada hora  
**Código:**
```python
env['adt.mobile.token'].cleanup_expired_tokens()
```

#### 2. Limpieza de Logs Antiguos
**Frecuencia:** Semanal  
**Código:**
```python
env['adt.mobile.access.log'].cleanup_old_logs(days=90)
```

### Monitoreo Recomendado

#### Dashboard de Seguridad

```python
# Tokens activos por usuario
active_tokens = env['adt.mobile.token'].search_count([('active', '=', True)])

# Requests en últimas 24 horas
today_logs = env['adt.mobile.access.log'].search_count([
    ('timestamp', '>=', hace_24_horas)
])

# Intentos fallidos (401/403)
failed_attempts = env['adt.mobile.access.log'].search_count([
    ('success', '=', False),
    ('timestamp', '>=', hace_24_horas)
])
```

---

## 🚨 Alertas de Seguridad

### Alerta 1: Múltiples Intentos Fallidos
```python
failed = Log.search([
    ('user_id', '=', user_id),
    ('success', '=', False),
    ('timestamp', '>=', hace_10_minutos)
])

if len(failed) > 5:
    # Enviar email al admin
    # Revocar tokens del usuario
    pass
```

### Alerta 2: Acceso desde IP Sospechosa
```python
# Comparar IP actual con IPs históricas del usuario
known_ips = Log.search([
    ('user_id', '=', user_id)
]).mapped('ip_address')

if current_ip not in known_ips:
    # Notificar al usuario y admin
    pass
```

---

## 📚 Referencias

- **OWASP API Security Top 10:** https://owasp.org/API-Security/
- **Token-Based Authentication:** https://jwt.io/introduction
- **Python Secrets Module:** https://docs.python.org/3/library/secrets.html
- **Odoo Security Guidelines:** https://www.odoo.com/documentation/15.0/developer/reference/security.html

---

**Última actualización:** Febrero 2026  
**Versión:** 15.0.3.0.0  
**Mantenedor:** Equipo ADT Security
