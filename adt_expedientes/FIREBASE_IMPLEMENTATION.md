# 🔔 Firebase Push Notifications - Implementación Completa

## 📋 Índice
1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura](#arquitectura)
3. [Componentes Implementados](#componentes-implementados)
4. [Configuración](#configuración)
5. [Uso desde la App Móvil](#uso-desde-la-app-móvil)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Resumen Ejecutivo

Se ha implementado exitosamente un sistema completo de notificaciones push usando **Firebase Cloud Messaging (FCM)** en el módulo `adt_expedientes`.

### ✅ Funcionalidades Implementadas

- **Notificaciones automáticas** cuando se presionan botones en Odoo:
  - ✅ Rechazar expediente
  - ✅ Marcar incompleto - Expediente
  - ✅ Marcar incompleto - Fase Final
  - ✅ Marcar completo

- **Gestión de tokens FCM**:
  - ✅ Registro de dispositivos móviles
  - ✅ Soporte multi-dispositivo por usuario
  - ✅ Desactivación automática de tokens inválidos
  - ✅ API REST segura con autenticación por tokens

- **Integración con adt_sentinel**:
  - ✅ API para consultar reportes Sentinel
  - ✅ API para crear reportes Sentinel
  - ✅ Autenticación unificada con el sistema de tokens existente

---

## 🏗️ Arquitectura

```
┌─────────────────┐
│   App Móvil     │
│  (Flutter/RN)   │
└────────┬────────┘
         │ 1. Envía FCM Token
         ▼
┌─────────────────────────────────────┐
│  Odoo - adt_expedientes             │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ FCM Controller               │  │
│  │ /adt/mobile/fcm/register     │  │
│  └──────────┬───────────────────┘  │
│             │                       │
│             ▼                       │
│  ┌──────────────────────────────┐  │
│  │ FCM Device Model             │  │
│  │ (adt.fcm.device)             │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ Expediente Model             │  │
│  │ - action_rechazar            │  │
│  │ - action_mark_incompleto_*   │  │
│  │ - action_mark_completo       │  │
│  └──────────┬───────────────────┘  │
│             │ 2. Trigger Notification
│             ▼                       │
│  ┌──────────────────────────────┐  │
│  │ Firebase Service             │  │
│  │ - OAuth2 Token               │  │
│  │ - HTTP v1 API                │  │
│  └──────────┬───────────────────┘  │
└─────────────┼───────────────────────┘
              │ 3. Send Push
              ▼
     ┌────────────────────┐
     │ Firebase Cloud     │
     │ Messaging (FCM)    │
     └────────┬───────────┘
              │ 4. Deliver
              ▼
     ┌────────────────────┐
     │   App Móvil        │
     │  (Notificación)    │
     └────────────────────┘
```

---

## 📦 Componentes Implementados

### 1. **Modelo: `adt.fcm.device`**
📁 `models/fcm_device.py`

Almacena tokens FCM de dispositivos móviles.

**Campos principales:**
- `user_id`: Usuario propietario
- `token`: Token FCM (único)
- `platform`: android/ios/web
- `device_name`, `device_os`, `app_version`
- `active`: Estado del dispositivo
- `notification_count`: Contador de notificaciones
- `last_seen`, `last_notification_sent`

**Métodos clave:**
- `register_or_update_device()`: Registra o actualiza un dispositivo
- `get_active_tokens_for_user()`: Obtiene tokens activos de un usuario
- `deactivate_device()`: Desactiva un dispositivo

---

### 2. **Servicio: `FirebaseService`**
📁 `services/firebase_service.py`

Servicio desacoplado para enviar notificaciones FCM usando HTTP v1 (sin SDK).

**Características:**
- ✅ OAuth2 con Service Account
- ✅ Gestión automática de access tokens
- ✅ Envío a múltiples dispositivos
- ✅ Manejo de errores y retry logic
- ✅ Desactivación automática de tokens inválidos
- ✅ Logging completo

**Métodos principales:**
```python
firebase = FirebaseService(env)

# Enviar a dispositivos específicos
firebase.send_notification(
    tokens=['token1', 'token2'],
    title='Título',
    body='Mensaje',
    data={'expediente_id': 123}
)

# Enviar a todos los dispositivos de un usuario
firebase.send_to_user(
    user_id=8,
    title='Título',
    body='Mensaje',
    data={'action': 'rechazado'}
)
```

---

### 3. **Controller: FCM Endpoints**
📁 `controllers/fcm_controller.py`

API REST para gestión de tokens FCM desde la app móvil.

#### **Endpoints:**

##### 📱 **POST** `/adt/mobile/fcm/register`
Registra o actualiza un token FCM.

**Request:**
```json
{
  "fcm_token": "dXYz123...",
  "platform": "android",
  "device_info": {
    "device_id": "UUID-123",
    "device_name": "Samsung Galaxy S21",
    "device_os": "Android 12",
    "app_version": "1.0.0"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Token FCM registrado correctamente",
  "device_id": 15
}
```

##### 📱 **POST** `/adt/mobile/fcm/unregister`
Desactiva un token FCM.

**Request:**
```json
{
  "fcm_token": "dXYz123..."
}
```

##### 📱 **POST** `/adt/mobile/fcm/devices`
Lista dispositivos del usuario autenticado.

**Response:**
```json
{
  "success": true,
  "devices": [
    {
      "id": 1,
      "device_name": "iPhone 13 Pro",
      "platform": "ios",
      "active": true,
      "notification_count": 45
    }
  ]
}
```

---

### 4. **Controller: Sentinel API**
📁 `controllers/mobile_sentinel_api.py`

API para integración con adt_sentinel (ya existente, documentado aquí).

##### 📱 **POST** `/api/sentinel/report/get`
Consulta reporte Sentinel vigente.

**Request:**
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
    "image_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
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

##### 📱 **POST** `/api/sentinel/report/create`
Crea un nuevo reporte Sentinel.

**Request:**
```json
{
  "document_number": "12345678",
  "image_base64": "iVBORw0KGgo...",
  "image_filename": "sentinel_febrero.png",
  "query_user_id": 8,
  "query_date": "2026-02-05"
}
```

---

### 5. **Integración en Expediente**
📁 `models/expediente.py`

#### **Método: `_send_firebase_notification()`**
Envía notificación Firebase al cliente del expediente.

```python
def _send_firebase_notification(self, title, body, action_type):
    """
    Envía notificación push al cliente asociado al expediente.
    
    Args:
        title: Título de la notificación
        body: Mensaje
        action_type: 'rechazado', 'incompleto', 'completo'
    """
```

#### **Acciones modificadas:**

```python
def action_mark_incompleto_expediente(self):
    self.write({'state': 'incompleto_expediente'})
    self._send_firebase_notification(
        title='Expediente incompleto',
        body='Tu expediente está incompleto. Por favor revisa los datos.',
        action_type='incompleto_expediente'
    )

def action_mark_incompleto_fase_final(self):
    self.write({'state': 'incompleto_fase_final'})
    self._send_firebase_notification(
        title='Expediente incompleto - Fase Final',
        body='Tu expediente está incompleto en la fase final.',
        action_type='incompleto_fase_final'
    )

def action_mark_completo(self):
    self.write({'state': 'completo'})
    self._send_firebase_notification(
        title='Expediente aprobado',
        body='¡Felicitaciones! Tu expediente ha sido aprobado.',
        action_type='completo'
    )
```

#### **Wizard de rechazo:**
📁 `wizard/expediente_rechazo_wizard.py`

```python
def action_confirmar(self):
    self.expediente_id.write({
        'state': 'rechazado',
        'fecha_rechazo': self.fecha_rechazo,
        'motivo_rechazo': self.motivo_rechazo,
    })
    
    # Enviar notificación
    self.expediente_id._send_firebase_notification(
        title='Expediente rechazado',
        body=f'Tu expediente ha sido rechazado. Motivo: {self.motivo_rechazo[:100]}',
        action_type='rechazado'
    )
```

---

### 6. **Vistas Odoo**
📁 `views/fcm_device_views.xml`

- Tree view: Lista todos los dispositivos
- Form view: Detalles y gestión de un dispositivo
- Search view: Filtros por usuario, plataforma, estado
- Menú en Configuración > Dispositivos FCM

---

## ⚙️ Configuración

### 1. **Instalar dependencias Python**

```bash
pip install google-auth requests
```

O crear `requirements.txt`:
```txt
google-auth>=2.16.0
requests>=2.28.0
```

### 2. **Obtener Service Account de Firebase**

1. Ir a [Firebase Console](https://console.firebase.google.com/)
2. Seleccionar tu proyecto
3. **Configuración del proyecto** (⚙️) > **Cuentas de servicio**
4. Click en **"Generar nueva clave privada"**
5. Descargar el archivo JSON (ej: `firebase-adminsdk-xxx.json`)

### 3. **Subir Service Account al servidor**

Subir el archivo JSON a tu servidor Odoo:
```bash
# Ejemplo: subir a /opt/odoo/config/
scp firebase-adminsdk-xxx.json user@servidor:/opt/odoo/config/
chmod 600 /opt/odoo/config/firebase-adminsdk-xxx.json
```

### 4. **Configurar Odoo**

Ir a: **Configuración > Técnico > Parámetros del Sistema**

Crear 2 parámetros:

| Clave | Valor | Ejemplo |
|-------|-------|---------|
| `firebase.service_account_path` | Ruta completa al JSON | `/opt/odoo/config/firebase-adminsdk-xxx.json` |
| `firebase.project_id` | ID del proyecto Firebase | `mi-proyecto-12345` |

**Comando SQL alternativo:**
```sql
INSERT INTO ir_config_parameter (key, value) VALUES 
    ('firebase.service_account_path', '/opt/odoo/config/firebase-adminsdk-xxx.json'),
    ('firebase.project_id', 'mi-proyecto-12345');
```

### 5. **Actualizar módulo**

```bash
# Reiniciar Odoo con actualización
./odoo-bin -u adt_expedientes -d nombre_bd
```

---

## 📱 Uso desde la App Móvil

### Flujo de autenticación y registro FCM

#### **1. Login (obtener token de autenticación)**

**POST** `/adt_expedientes/mobile/token/create`

```json
{
  "db": "nombre_bd",
  "login": "usuario",
  "password": "contraseña",
  "device_info": {
    "device_id": "UUID-dispositivo",
    "device_name": "Samsung Galaxy S21",
    "device_os": "Android 12",
    "app_version": "1.0.0"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "token": "abc123...",
    "user_id": 8,
    "user_name": "María Torres"
  }
}
```

#### **2. Registrar token FCM**

**POST** `/adt/mobile/fcm/register`

**Headers:**
```
Authorization: Bearer abc123...
```

**Body:**
```json
{
  "fcm_token": "dXYz789...",
  "platform": "android",
  "device_info": {
    "device_id": "UUID-dispositivo",
    "device_name": "Samsung Galaxy S21",
    "device_os": "Android 12",
    "app_version": "1.0.0"
  }
}
```

#### **3. Recibir notificaciones**

La app recibirá notificaciones push cuando un administrador cambie el estado del expediente.

**Payload recibido:**
```json
{
  "notification": {
    "title": "Expediente aprobado",
    "body": "¡Felicitaciones! Tu expediente ha sido aprobado."
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

## 🧪 Testing

### 1. **Probar registro de token FCM**

```bash
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "fcm_token": "test_token_123",
    "platform": "android",
    "device_info": {
      "device_name": "Test Device",
      "device_os": "Android 12"
    }
  }'
```

### 2. **Probar desde Odoo UI**

1. Ir a un expediente
2. Presionar botón **"Marcar Completo"**
3. Verificar logs de Odoo:
   ```
   INFO: Notificación FCM enviada para expediente 123: 1 dispositivo(s)
   ```

### 3. **Ver dispositivos registrados**

**Odoo UI:**
- Ir a: **Configuración > Dispositivos FCM**

**API:**
```bash
curl -X POST http://localhost:8069/adt/mobile/fcm/devices \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json"
```

### 4. **Probar Sentinel API**

**Consultar reporte:**
```bash
curl -X POST http://localhost:8069/api/sentinel/report/get \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_number": "12345678"}'
```

---

## 🔧 Troubleshooting

### ❌ Error: "No se encontró la configuración firebase.service_account_path"

**Solución:** Configurar los parámetros del sistema (ver sección Configuración).

---

### ❌ Error: "FileNotFoundError: Service account file not found"

**Causas:**
1. Ruta incorrecta en `firebase.service_account_path`
2. Archivo no existe en el servidor
3. Permisos insuficientes

**Solución:**
```bash
# Verificar que el archivo existe
ls -la /opt/odoo/config/firebase-adminsdk-xxx.json

# Dar permisos al usuario de Odoo
chown odoo:odoo /opt/odoo/config/firebase-adminsdk-xxx.json
chmod 600 /opt/odoo/config/firebase-adminsdk-xxx.json
```

---

### ❌ Error: "ModuleNotFoundError: No module named 'google.auth'"

**Solución:**
```bash
# Instalar dependencias
pip3 install google-auth requests

# O con el usuario de Odoo
sudo -u odoo pip3 install google-auth requests
```

---

### ❌ No se envían notificaciones

**Checklist:**
1. ✅ Verificar que el cliente tiene un usuario asociado
2. ✅ Verificar que el usuario tiene dispositivos FCM registrados
3. ✅ Verificar logs de Odoo para ver errores
4. ✅ Verificar que el token FCM es válido
5. ✅ Verificar configuración de Firebase

**Ver logs:**
```bash
tail -f /var/log/odoo/odoo.log | grep -i fcm
```

---

### ❌ Token inválido (401/404 de Firebase)

**Comportamiento:** El sistema automáticamente desactiva tokens inválidos.

**Solución:** La app móvil debe detectar tokens inválidos y re-registrarlos.

---

## 📊 Monitoreo

### Ver estadísticas en Odoo

**SQL Query:**
```sql
SELECT 
    u.login,
    COUNT(f.id) as dispositivos,
    SUM(f.notification_count) as notificaciones_totales,
    MAX(f.last_notification_sent) as ultima_notificacion
FROM adt_fcm_device f
JOIN res_users u ON f.user_id = u.id
WHERE f.active = true
GROUP BY u.login
ORDER BY notificaciones_totales DESC;
```

---

## 🎉 Resumen Final

### ✅ Implementado

- ✅ Modelo `adt.fcm.device` para gestión de tokens
- ✅ Servicio `FirebaseService` con OAuth2 y HTTP v1
- ✅ Controller con 3 endpoints FCM
- ✅ Integración en acciones de expediente
- ✅ Notificaciones automáticas en 4 estados
- ✅ Vistas Odoo para administración
- ✅ Security (ir.model.access.csv)
- ✅ Integración con adt_sentinel (ya existente)
- ✅ Documentación completa

### 🚀 Características

- **Seguro**: Autenticación con tokens, validación en cada request
- **Escalable**: Soporte multi-dispositivo, preparado para queue_job
- **Robusto**: Manejo de errores, logs completos, desactivación automática
- **Modular**: Código desacoplado, fácil de mantener

### 📈 Próximos pasos (opcional)

- [ ] Implementar queue_job para envío async
- [ ] Agregar estadísticas de notificaciones en dashboard
- [ ] Implementar topics de Firebase para notificaciones masivas
- [ ] Agregar preferencias de notificación por usuario

---

**🎯 Sistema completamente funcional y listo para producción!**
