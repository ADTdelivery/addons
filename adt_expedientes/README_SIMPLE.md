# ADT Expedientes - Push Notifications

Módulo de gestión de expedientes con notificaciones push automáticas.

## Características

- ✅ Sistema de autenticación móvil (token-based)
- ✅ Notificaciones push automáticas en cambios de estado
- ✅ Integración con adt_sentinel para reportes crediticios
- ✅ API REST para aplicaciones móviles
- ✅ Gestión de dispositivos FCM

## Notificaciones Automáticas

Se envían notificaciones push cuando:
- ❌ Se rechaza un expediente
- ⚠️ Se marca como incompleto (Expediente o Fase Final)
- ✅ Se marca como completo

## API Endpoints

### Autenticación
- `POST /adt_expedientes/mobile/token/create` - Login

### FCM
- `POST /adt/mobile/fcm/register` - Registrar token
- `POST /adt/mobile/fcm/unregister` - Desactivar token
- `POST /adt/mobile/fcm/devices` - Listar dispositivos

### Sentinel
- `POST /api/sentinel/report/get` - Consultar reporte
- `POST /api/sentinel/report/create` - Crear reporte

Todos los endpoints (excepto login) requieren: `Authorization: Bearer TOKEN`

## Configuración

### Servicio de Notificaciones

El módulo envía notificaciones a través de un servicio HTTP local en:
- **URL:** `http://localhost:8030/send`
- **Método:** POST
- **Body:**
```json
{
  "token": "FCM_TOKEN",
  "title": "Título",
  "body": "Mensaje",
  "data": {
    "expediente_id": "123",
    "action": "completo"
  }
}
```

Si necesitas cambiar la URL del servicio, edita:
`services/notification_service.py` → `self.notification_url`

## Instalación

```bash
# 1. Instalar dependencia
pip3 install requests

# 2. Actualizar módulo
./odoo-bin -u adt_expedientes -d tu_bd
```

## Uso desde App Móvil

```javascript
// 1. Login
const { token } = await login('user', 'password');

// 2. Registrar token FCM
const fcmToken = await getFCMToken();
await registerFCM(token, fcmToken);

// 3. Recibir notificaciones
onNotification((notification) => {
  console.log(notification.title);
  // Navegar al expediente
});
```

## Gestión de Dispositivos

En Odoo: **Configuración > Dispositivos FCM**

Ver dispositivos registrados, estadísticas y gestionar tokens.

---

**Versión:** 15.0.4.0.0  
**Licencia:** LGPL-3
