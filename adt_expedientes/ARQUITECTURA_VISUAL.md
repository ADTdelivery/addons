# 🗺️ Arquitectura Visual - Firebase Push Notifications

## 📐 Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────┐
│                          APP MÓVIL                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Flutter    │  │ React Native │  │     Web      │              │
│  │   Android    │  │     iOS      │  │  PWA/Ionic   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
└─────────┼──────────────────┼──────────────────┼────────────────────┘
          │                  │                  │
          │ ① Login          │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ODOO - adt_expedientes                            │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              CONTROLLERS (API REST)                            │ │
│  │                                                                │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐ │ │
│  │  │  mobile_api.py │  │fcm_controller  │  │mobile_sentinel  │ │ │
│  │  │                │  │     .py        │  │   _api.py       │ │ │
│  │  │ • Login        │  │ • Register FCM │  │ • Get Report    │ │ │
│  │  │ • Create Token │  │ • Unregister   │  │ • Create Report │ │ │
│  │  │                │  │ • List Devices │  │                 │ │ │
│  │  └────────┬───────┘  └────────┬───────┘  └────────┬────────┘ │ │
│  └───────────┼──────────────────┼──────────────────┼────────────┘ │
│              │ ② Auth Token     │                  │              │
│              ▼                  │                  │              │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    MODELS                                      │ │
│  │                                                                │ │
│  │  ┌────────────┐  ┌─────────────┐  ┌────────────┐  ┌────────┐ │ │
│  │  │mobile_token│  │ fcm_device  │  │ expediente │  │sentinel│ │ │
│  │  │            │  │             │  │            │  │ report │ │ │
│  │  │ • Validate │  │ • Store FCM │  │ • States   │  │        │ │ │
│  │  │ • Expire   │  │ • Track     │  │ • Actions  │  │ • Get  │ │ │
│  │  │ • Audit    │  │ • Stats     │  │ • Notify   │  │ • Save │ │ │
│  │  └────────────┘  └─────────────┘  └──────┬─────┘  └────────┘ │ │
│  │                                           │                    │ │
│  └───────────────────────────────────────────┼────────────────────┘ │
│                                              │ ③ Change State     │
│                                              ▼                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    SERVICES                                    │ │
│  │                                                                │ │
│  │  ┌────────────────────────────────────────────────────────┐   │ │
│  │  │            firebase_service.py                         │   │ │
│  │  │                                                        │   │ │
│  │  │  • _get_access_token()      ← OAuth2                  │   │ │
│  │  │  • send_notification()      ← HTTP v1 API             │   │ │
│  │  │  • send_to_user()           ← Multi-device            │   │ │
│  │  │  • _deactivate_invalid()    ← Auto-cleanup            │   │ │
│  │  └────────────────────┬───────────────────────────────────┘   │ │
│  └───────────────────────┼───────────────────────────────────────┘ │
│                          │ ④ Push Notification                    │
└──────────────────────────┼────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               FIREBASE CLOUD MESSAGING (FCM)                         │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Firebase HTTP v1 API                                      │    │
│  │  • OAuth2 Authentication                                   │    │
│  │  • Multi-platform support                                  │    │
│  │  • Message routing                                         │    │
│  └────────────────────────┬───────────────────────────────────┘    │
└───────────────────────────┼────────────────────────────────────────┘
                            │ ⑤ Deliver Notification
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DISPOSITIVOS MÓVILES                              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  📱 Android  │  │  📱 iPhone   │  │  💻 Web PWA  │             │
│  │              │  │              │  │              │             │
│  │  ✅ Activo   │  │  ✅ Activo   │  │  ❌ Offline  │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo de Datos Detallado

### 1️⃣ Registro de Dispositivo

```
App Móvil                  Odoo                    Firebase
    │                        │                         │
    │ 1. Login               │                         │
    ├───────────────────────>│                         │
    │                        │                         │
    │ 2. Auth Token          │                         │
    │<───────────────────────┤                         │
    │                        │                         │
    │ 3. Get FCM Token       │                         │
    ├────────────────────────┼────────────────────────>│
    │                        │                         │
    │ 4. FCM Token           │                         │
    │<───────────────────────┼─────────────────────────┤
    │                        │                         │
    │ 5. Register (token)    │                         │
    ├───────────────────────>│                         │
    │                        │ ① Store in DB          │
    │                        │ ② Create/Update record  │
    │                        │                         │
    │ 6. Success             │                         │
    │<───────────────────────┤                         │
```

### 2️⃣ Envío de Notificación

```
Odoo UI              Expediente Model        Firebase Service      FCM           App
  │                        │                       │                │             │
  │ 1. Click Button        │                       │                │             │
  │ "Marcar Completo"      │                       │                │             │
  ├───────────────────────>│                       │                │             │
  │                        │                       │                │             │
  │                        │ 2. write(state)       │                │             │
  │                        ├──────────┐            │                │             │
  │                        │<─────────┘            │                │             │
  │                        │                       │                │             │
  │                        │ 3. _send_firebase_notification()       │             │
  │                        ├──────────────────────>│                │             │
  │                        │                       │                │             │
  │                        │                       │ 4. Get tokens  │             │
  │                        │                       │ (from fcm_device)           │
  │                        │                       ├───────┐        │             │
  │                        │                       │<──────┘        │             │
  │                        │                       │                │             │
  │                        │                       │ 5. OAuth2      │             │
  │                        │                       ├───────────────>│             │
  │                        │                       │                │             │
  │                        │                       │ 6. Access Token│             │
  │                        │                       │<───────────────┤             │
  │                        │                       │                │             │
  │                        │                       │ 7. HTTP POST   │             │
  │                        │                       │ /messages:send │             │
  │                        │                       ├───────────────>│             │
  │                        │                       │                │             │
  │                        │                       │ 8. Response OK │             │
  │                        │                       │<───────────────┤             │
  │                        │                       │                │             │
  │                        │                       │                │ 9. Push    │
  │                        │                       │                ├────────────>│
  │                        │                       │                │             │
  │                        │ 10. Log success       │                │ 10. Show   │
  │                        │<──────────────────────┤                │ Notification│
  │                        │                       │                │             │
  │ 11. UI Updated         │                       │                │             │
  │<───────────────────────┤                       │                │             │
```

---

## 🗂️ Estructura de Base de Datos

### Tabla: `adt_fcm_device`

```sql
CREATE TABLE adt_fcm_device (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES res_users(id) ON DELETE CASCADE,
    token VARCHAR UNIQUE NOT NULL,
    platform VARCHAR(20) NOT NULL,  -- 'android', 'ios', 'web'
    active BOOLEAN DEFAULT TRUE,
    
    -- Device Info
    device_name VARCHAR,
    device_id VARCHAR,
    device_os VARCHAR,
    app_version VARCHAR,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW(),
    last_notification_sent TIMESTAMP,
    
    -- Stats
    notification_count INTEGER DEFAULT 0,
    
    -- Audit
    create_date TIMESTAMP,
    create_uid INTEGER REFERENCES res_users(id),
    write_date TIMESTAMP,
    write_uid INTEGER REFERENCES res_users(id)
);

CREATE INDEX idx_fcm_device_user ON adt_fcm_device(user_id);
CREATE INDEX idx_fcm_device_token ON adt_fcm_device(token);
CREATE INDEX idx_fcm_device_active ON adt_fcm_device(active);
```

### Relaciones

```
res_users (1) ────────< (N) adt_fcm_device
                            ↓
                       (N) tokens FCM
                            ↓
                     Firebase Cloud Messaging
                            ↓
                       (N) Dispositivos Físicos
```

---

## 📊 Diagrama de Estados - Expediente

```
┌─────────────────┐
│  Por Revisar    │ ← Estado inicial
└────────┬────────┘
         │
         ├─────────────────────────────┐
         │                             │
         ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│   Incompleto     │          │    Rechazado     │
│   (Expediente)   │          │                  │
└────────┬─────────┘          └──────────────────┘
         │                             │
         │ 🔔 Notification             │ 🔔 Notification
         │ "Expediente incompleto"     │ "Expediente rechazado"
         │                             │
         ▼                             │
┌──────────────────┐                  │
│   Incompleto     │                  │
│  (Fase Final)    │                  │
└────────┬─────────┘                  │
         │                             │
         │ 🔔 Notification             │
         │ "Incompleto fase final"     │
         │                             │
         ▼                             │
┌──────────────────┐                  │
│    Completo      │◄─────────────────┘
└──────────────────┘
         │
         │ 🔔 Notification
         │ "Expediente aprobado"
         ▼
    [App Móvil]
```

---

## 🔐 Flujo de Seguridad

```
┌──────────────────────────────────────────────────────────────┐
│                    CAPA DE SEGURIDAD                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  1. App Request                                              │
│     ↓                                                         │
│  2. Extract Authorization Header                             │
│     ↓                                                         │
│  3. Validate Token (adt.mobile.token)                        │
│     ↓                                                         │
│  4. Check Token Expiry                                       │
│     ↓                                                         │
│  5. Verify User Active                                       │
│     ↓                                                         │
│  6. Log Access (adt.mobile.access.log)                       │
│     ↓                                                         │
│  7. Execute Endpoint Logic                                   │
│     │                                                         │
│     ├─ FCM Operations                                        │
│     ├─ Sentinel Operations                                   │
│     └─ Other Operations                                      │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Validaciones por Capa

| Capa | Validación | Acción si falla |
|------|------------|-----------------|
| **HTTP** | Header `Authorization` presente | 401 Unauthorized |
| **Token** | Token existe en BD | 401 Invalid token |
| **Expiry** | Token no expirado | 401 Expired token |
| **User** | Usuario activo | 403 Forbidden |
| **Audit** | Log de acceso | Continuar |
| **Business** | Lógica específica | 400 Bad Request |

---

## 📡 Endpoints Map

```
/adt_expedientes/
│
├── mobile/
│   │
│   ├── token/
│   │   └── create              [POST]  🔓 public  → Login
│   │
│   └── fcm/
│       ├── register            [POST]  🔒 auth    → Register FCM token
│       ├── unregister          [POST]  🔒 auth    → Deactivate token
│       └── devices             [POST]  🔒 auth    → List user devices
│
└── /api/
    └── sentinel/
        └── report/
            ├── get             [POST]  🔒 auth    → Get current report
            └── create          [POST]  🔒 auth    → Create new report
```

### Leyenda
- 🔓 = No requiere autenticación
- 🔒 = Requiere Bearer Token
- [POST] = Método HTTP
- auth = Validación de token automática

---

## 🎨 Payload Structures

### Request: Register FCM Token

```json
{
  "fcm_token": "dXYz123abc...",
  "platform": "android",
  "device_info": {
    "device_id": "uuid-123",
    "device_name": "Samsung Galaxy S21",
    "device_os": "Android 12",
    "app_version": "1.0.0"
  }
}
```

### Response: Success

```json
{
  "success": true,
  "message": "Token FCM registrado correctamente",
  "device_id": 15,
  "device_name": "Samsung Galaxy S21"
}
```

### Notification Payload (Firebase → App)

```json
{
  "notification": {
    "title": "Expediente aprobado",
    "body": "¡Felicitaciones! Tu expediente ha sido aprobado con éxito."
  },
  "data": {
    "expediente_id": "123",
    "action": "completo",
    "timestamp": "2026-02-08T10:30:00",
    "cliente_id": "456",
    "cliente_name": "Juan Pérez"
  }
}
```

---

## 🔍 Monitoreo y Logs

### Log Flow

```
Odoo Action
    ↓
[INFO] Iniciando envío de notificación...
    ↓
[INFO] Obteniendo tokens para user_id=8
    ↓
[INFO] 2 dispositivos activos encontrados
    ↓
[INFO] Obteniendo access token de Firebase
    ↓
[INFO] OAuth2 token obtenido correctamente
    ↓
[INFO] Enviando notificación a token: dXYz123...
    ↓
[INFO] Respuesta Firebase: 200 OK
    ↓
[INFO] Notificación enviada correctamente
    ↓
[INFO] Actualizando estadísticas de dispositivo
    ↓
[INFO] Notificación FCM enviada para expediente 123: 2 dispositivo(s)
```

### Queries de Monitoreo

```sql
-- Dashboard de actividad
SELECT 
    DATE(last_notification_sent) as fecha,
    COUNT(*) as notificaciones,
    COUNT(DISTINCT user_id) as usuarios_unicos
FROM adt_fcm_device
WHERE last_notification_sent >= NOW() - INTERVAL '7 days'
GROUP BY DATE(last_notification_sent)
ORDER BY fecha DESC;

-- Top usuarios por notificaciones
SELECT 
    u.login,
    COUNT(f.id) as dispositivos,
    SUM(f.notification_count) as total_notificaciones,
    MAX(f.last_notification_sent) as ultima_notificacion
FROM adt_fcm_device f
JOIN res_users u ON f.user_id = u.id
WHERE f.active = true
GROUP BY u.login
ORDER BY total_notificaciones DESC
LIMIT 10;

-- Distribución por plataforma
SELECT 
    platform,
    COUNT(*) as dispositivos,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as porcentaje
FROM adt_fcm_device
WHERE active = true
GROUP BY platform;
```

---

## 🎯 Conclusión Visual

Este diagrama muestra cómo todos los componentes trabajan juntos para proporcionar un sistema robusto, seguro y escalable de notificaciones push integrado con el módulo adt_expedientes de Odoo.

**Características clave visualizadas:**
- ✅ Separación de responsabilidades
- ✅ Flujo de autenticación seguro
- ✅ Integración Firebase sin SDK
- ✅ Multi-dispositivo por usuario
- ✅ Auditoría completa
- ✅ Escalable y mantenible

---

**Para más detalles técnicos, consulta:**
- [FIREBASE_IMPLEMENTATION.md](FIREBASE_IMPLEMENTATION.md)
- [RESUMEN_IMPLEMENTACION.md](RESUMEN_IMPLEMENTACION.md)
