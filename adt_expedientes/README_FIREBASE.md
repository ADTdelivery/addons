# 📱 ADT Expedientes - Firebase Push Notifications + Sentinel Integration

![Version](https://img.shields.io/badge/version-15.0.4.0.0-blue)
![License](https://img.shields.io/badge/license-LGPL--3-green)
![Odoo](https://img.shields.io/badge/odoo-15.0%2B-purple)

## 🎯 Descripción

Módulo de gestión de expedientes con sistema completo de:
- ✅ **Autenticación móvil segura** (token-based)
- ✅ **Notificaciones push Firebase** (FCM HTTP v1)
- ✅ **Integración con adt_sentinel** para reportes crediticios
- ✅ **API REST completa** para aplicaciones móviles

---

## 🚀 Características Principales

### 🔐 Seguridad
- Token-based authentication con SHA256 hashing
- Device binding (un token por dispositivo)
- Validación automática en cada request
- Revocación automática al desactivar usuarios
- Auditoría completa de accesos

### 🔔 Notificaciones Push
- **Firebase Cloud Messaging** (HTTP v1, sin SDK)
- Notificaciones automáticas en cambios de estado:
  - 📕 Expediente rechazado
  - ⚠️ Expediente incompleto (Expediente/Fase Final)
  - ✅ Expediente aprobado
- Soporte multi-dispositivo (Android, iOS, Web)
- Gestión inteligente de tokens inválidos

### 🛡️ Integración Sentinel
- Consulta de reportes crediticios vigentes
- Registro de nuevos reportes con imágenes
- Control de 1 reporte por DNI por mes
- API REST segura con autenticación unificada

---

## 📦 Instalación

### 1. Clonar/copiar el módulo

```bash
cd /opt/odoo/addons
# El módulo ya está en: adt_expedientes/
```

### 2. Instalar dependencias Python

```bash
pip3 install -r adt_expedientes/requirements.txt
```

O manualmente:
```bash
pip3 install google-auth requests
```

### 3. Configurar Firebase

Ver guía rápida: [QUICK_START_FIREBASE.md](QUICK_START_FIREBASE.md)

**Resumen:**
1. Obtener Service Account JSON de Firebase Console
2. Subir a servidor: `/opt/odoo/config/firebase-adminsdk-xxx.json`
3. Configurar en Odoo:
   - `firebase.service_account_path`
   - `firebase.project_id`

### 4. Actualizar módulo

```bash
./odoo-bin -u adt_expedientes -d tu_base_datos
```

---

## 📚 Documentación

| Documento | Descripción |
|-----------|-------------|
| **[FIREBASE_IMPLEMENTATION.md](FIREBASE_IMPLEMENTATION.md)** | 📖 Documentación técnica completa |
| **[QUICK_START_FIREBASE.md](QUICK_START_FIREBASE.md)** | ⚡ Guía de configuración rápida (5 min) |
| **[API_TESTING_GUIDE.md](API_TESTING_GUIDE.md)** | 🧪 Guía de testing con Postman/Newman |

---

## 🔌 API Endpoints

Todos los endpoints requieren autenticación: `Authorization: Bearer TOKEN`

### 🔐 Autenticación

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/adt_expedientes/mobile/token/create` | POST | Crear token de autenticación |

### 🔔 Firebase FCM

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/adt/mobile/fcm/register` | POST | Registrar token FCM |
| `/adt/mobile/fcm/unregister` | POST | Desactivar token FCM |
| `/adt/mobile/fcm/devices` | POST | Listar dispositivos del usuario |

### 🛡️ Sentinel

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/sentinel/report/get` | POST | Consultar reporte vigente |
| `/api/sentinel/report/create` | POST | Crear nuevo reporte |

---

## 💻 Ejemplo de Uso

### Desde App Móvil (Flutter/React Native)

```javascript
// 1. Login
const loginResponse = await fetch(`${baseUrl}/adt_expedientes/mobile/token/create`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    db: 'mi_bd',
    login: 'usuario',
    password: 'contraseña'
  })
});

const { token } = (await loginResponse.json()).data;

// 2. Registrar token FCM
const fcmToken = await getFCMToken(); // Obtener de Firebase SDK

await fetch(`${baseUrl}/adt/mobile/fcm/register`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    fcm_token: fcmToken,
    platform: 'android',
    device_info: {
      device_name: 'Samsung Galaxy S21',
      device_os: 'Android 12'
    }
  })
});

// 3. Escuchar notificaciones
onMessageReceived((notification) => {
  console.log('Notificación:', notification.title);
  console.log('Expediente ID:', notification.data.expediente_id);
  console.log('Acción:', notification.data.action);
});
```

---

## 🎨 Estructura del Módulo

```
adt_expedientes/
├── __init__.py
├── __manifest__.py
├── requirements.txt
│
├── models/
│   ├── __init__.py
│   ├── expediente.py              # Modelo principal con notificaciones
│   ├── fcm_device.py              # Gestión de tokens FCM
│   ├── mobile_token.py            # Tokens de autenticación
│   └── ...
│
├── controllers/
│   ├── __init__.py
│   ├── mobile_api.py              # API principal de autenticación
│   ├── fcm_controller.py          # Endpoints FCM
│   └── mobile_sentinel_api.py     # Endpoints Sentinel
│
├── services/
│   ├── __init__.py
│   └── firebase_service.py        # Servicio Firebase (HTTP v1)
│
├── views/
│   ├── expediente_views.xml
│   ├── fcm_device_views.xml       # Gestión de dispositivos FCM
│   └── ...
│
├── security/
│   └── ir.model.access.csv
│
├── wizard/
│   └── expediente_rechazo_wizard.py
│
└── docs/
    ├── FIREBASE_IMPLEMENTATION.md
    ├── QUICK_START_FIREBASE.md
    └── API_TESTING_GUIDE.md
```

---

## 🔄 Flujo de Notificaciones

```
┌─────────────────────┐
│  Usuario en Odoo    │
│  presiona botón:    │
│  - Rechazar         │
│  - Incompleto       │
│  - Completo         │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────┐
│  expediente.py               │
│  action_mark_completo()      │
│    ↓                         │
│  _send_firebase_notification()│
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  firebase_service.py         │
│  - OAuth2 Token              │
│  - HTTP POST a Firebase      │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Firebase Cloud Messaging    │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  📱 App Móvil                │
│  Notificación recibida       │
└──────────────────────────────┘
```

---

## 🧪 Testing

### Quick Test

```bash
# 1. Registrar token FCM
curl -X POST http://localhost:8069/adt/mobile/fcm/register \
  -H "Authorization: Bearer TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "test123", "platform": "android"}'

# 2. Verificar en UI de Odoo
# Ir a: Configuración > Dispositivos FCM

# 3. Cambiar estado de expediente
# Ir a un expediente > Presionar "Marcar Completo"

# 4. Ver logs
tail -f /var/log/odoo/odoo.log | grep FCM
```

### Tests Completos

Ver: [API_TESTING_GUIDE.md](API_TESTING_GUIDE.md)

---

## 🔧 Configuración

### Parámetros del Sistema (ir.config_parameter)

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `firebase.service_account_path` | `/opt/odoo/config/firebase-adminsdk-xxx.json` | Ruta al Service Account JSON |
| `firebase.project_id` | `mi-proyecto-12345` | ID del proyecto Firebase |

### Variables de Entorno (opcional)

```bash
export FIREBASE_SERVICE_ACCOUNT=/opt/odoo/config/firebase-adminsdk-xxx.json
export FIREBASE_PROJECT_ID=mi-proyecto-12345
```

---

## 🐛 Troubleshooting

### Problema: No se envían notificaciones

**Checklist:**
1. ✅ Verificar que el cliente tiene usuario asociado
2. ✅ Verificar que el usuario tiene dispositivos FCM activos
3. ✅ Verificar configuración de Firebase en ir.config_parameter
4. ✅ Verificar logs de Odoo

```bash
# Ver logs
tail -f /var/log/odoo/odoo.log | grep -E "(FCM|Firebase)"
```

### Problema: Error al cargar Service Account

**Causas:**
- Ruta incorrecta en `firebase.service_account_path`
- Permisos insuficientes en el archivo JSON

**Solución:**
```bash
chmod 600 /opt/odoo/config/firebase-adminsdk-xxx.json
chown odoo:odoo /opt/odoo/config/firebase-adminsdk-xxx.json
```

### Más información

Ver: [FIREBASE_IMPLEMENTATION.md - Sección Troubleshooting](FIREBASE_IMPLEMENTATION.md#-troubleshooting)

---

## 📊 Monitoreo

### Ver dispositivos activos

**SQL:**
```sql
SELECT 
    u.login,
    COUNT(f.id) as dispositivos,
    SUM(f.notification_count) as notificaciones_totales
FROM adt_fcm_device f
JOIN res_users u ON f.user_id = u.id
WHERE f.active = true
GROUP BY u.login;
```

**UI:**
- Ir a: **Configuración > Dispositivos FCM**

---

## 🤝 Dependencias

### Módulos Odoo
- `base`
- `mail`
- `adt_sentinel`

### Python Packages
- `google-auth >= 2.16.0`
- `requests >= 2.28.0`

---

## 📝 Changelog

### v15.0.4.0.0 (2026-02-08)
- ✅ Implementación completa de Firebase Cloud Messaging
- ✅ Notificaciones automáticas en cambios de estado
- ✅ Gestión de tokens FCM multi-dispositivo
- ✅ Integración con adt_sentinel
- ✅ API REST segura para consultas Sentinel
- ✅ Documentación completa

### v15.0.3.0.0
- Token-based authentication
- Mobile API básica

---

## 👥 Soporte

Para problemas o consultas:
1. Revisar documentación: [FIREBASE_IMPLEMENTATION.md](FIREBASE_IMPLEMENTATION.md)
2. Revisar guía de troubleshooting
3. Verificar logs de Odoo

---

## 📄 Licencia

LGPL-3

---

## 🎉 Estado del Proyecto

✅ **COMPLETAMENTE IMPLEMENTADO Y LISTO PARA PRODUCCIÓN**

- [x] Modelo FCM Device
- [x] Servicio Firebase (HTTP v1)
- [x] Endpoints API REST
- [x] Integración en expediente
- [x] Notificaciones automáticas
- [x] Vistas Odoo
- [x] Security access rights
- [x] Integración Sentinel
- [x] Documentación completa
- [x] Guía de testing

---

**Made with ❤️ for ADT**
