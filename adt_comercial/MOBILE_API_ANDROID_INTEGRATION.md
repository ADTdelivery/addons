# Mobile API - Integracion Android

Documento de referencia para integrar los servicios definidos en `adt_comercial/controllers/mobile_api.py`.

## 1) Base URL y headers

- Base URL: `https://<tu-dominio-odoo>`
- Header para servicios protegidos:
  - `Authorization: Bearer <token>`
- Header recomendado:
  - `Content-Type: application/json`

## 2) Formato de respuestas

### 2.1 Respuesta estandar (`_success` / `_error`)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {},
  "meta": {
    "timestamp": "2026-05-19T21:00:00Z",
    "requestId": "uuid"
  }
}
```

```json
{
  "success": false,
  "statusCode": 422,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Mensaje de error",
    "details": []
  },
  "meta": {
    "timestamp": "2026-05-19T21:00:00Z",
    "requestId": "uuid"
  }
}
```

### 2.2 Respuesta contrato pagos (`_contract_error`)

Solo para `POST /api/v1/pagos/registrar`:

```json
{
  "code": "MONTO_NO_COINCIDE",
  "message": "La suma de montoPagado no coincide con montoTotal.",
  "field": "montoTotal"
}
```

---

## 3) Autenticacion

## 3.1 Login (genera token)

- **Servicio**: `Auth Login`
- **Metodo/Ruta**: `POST /v1/auth/login`
- **Auth**: No

### Request
```json
{
  "plate": "ABC-123"
}
```

### Response (200)
```json
{
  "success": true,
  "data": {
    "token": "<token>",
    "vehicleId": 10,
    "licensePlate": "ABC-123",
    "partnerId": 55,
    "partnerName": "Juan Perez",
    "expiresAt": "2026-08-17T12:30:00Z"
  }
}
```

## 3.2 Logout

- **Servicio**: `Auth Logout`
- **Metodo/Ruta**: `POST /v1/auth/logout`
- **Auth**: Bearer

### Request
```json
{
  "plate": "ABC-123",
  "deviceId": "optional-device-id"
}
```

### Response (200)
```json
{
  "success": true,
  "data": {
    "loggedOutAt": "2026-05-19T21:00:00Z"
  }
}
```

---

## 4) Core app

## 4.1 Version app

- **Servicio**: `App Version`
- **Metodo/Ruta**: `GET /v1/app/version`
- **Auth**: No

### Query/Headers
- Header opcional: `X-Platform: android|ios|all`

### Response (200)
```json
{
  "success": true,
  "data": {
    "latestVersion": "1.0.0",
    "minimumVersion": "1.0.0",
    "updateRequired": false,
    "updateAvailable": true,
    "updateMessage": null,
    "storeUrl": {
      "android": null,
      "ios": null
    },
    "maintenanceMode": false,
    "maintenanceMessage": null
  }
}
```

## 4.2 Prestamo por placa

- **Servicio**: `Loan Detail`
- **Metodo/Ruta**: `GET /v1/loans?plate=ABC-123`
- **Auth**: Bearer

### Response (200, resumen)
```json
{
  "success": true,
  "data": {
    "customer": {
      "id": "55",
      "fullName": "Juan Perez",
      "phone": "999999999",
      "address": "...",
      "nationality": null,
      "maritalStatus": "SINGLE"
    },
    "loan": {
      "id": "100",
      "referenceNo": "C-0001",
      "state": "en_curso",
      "totalDebt": 7920.0,
      "paidAmount": 660.0,
      "pendingAmount": 7260.0,
      "paidPercentage": 8.33,
      "currency": "S/",
      "plate": "ABC-123",
      "paymentType": "quincena",
      "cuotaTotal": 24,
      "cuotasPagadas": 2,
      "cuotasRetrasadas": 1,
      "montoCuotasRetrasadas": 330.0,
      "montoCuotaPendiente": 330.0,
      "totalPendienteCobrar": 660.0,
      "installments": []
    },
    "paymentAccounts": [],
    "contacts": [],
    "unreadCount": 0
  }
}
```

## 4.3 Documentos por placa

- **Servicio**: `Documents`
- **Metodo/Ruta**: `GET /v1/documents?plate=ABC-123`
- **Auth**: Bearer

### Response (200)
```json
{
  "success": true,
  "data": {
    "documents": [
      {
        "id": "doc-1-0",
        "name": "Tarjeta de Propiedad",
        "type": "GUARANTEE",
        "mimeType": "application/pdf",
        "sizeKb": 123,
        "url": "https://.../web/content/999",
        "urlExpiresAt": null,
        "uploadedAt": "2026-05-19T10:00:00Z"
      }
    ]
  }
}
```

---

## 5) Promociones y notificaciones

## 5.1 Listar promociones

- **Servicio**: `Promotions List`
- **Metodo/Ruta**: `GET /v1/promotions?page=1&pageSize=20`
- **Auth**: Bearer

## 5.2 Crear promocion

- **Servicio**: `Promotion Create`
- **Metodo/Ruta**: `POST /v1/promotions`
- **Auth**: Bearer

### Request
```json
{
  "title": "Promo",
  "body": "Texto",
  "linkType": "whatsapp",
  "deepLink": null,
  "externalUrl": "https://..."
}
```

## 5.3 Listar notificaciones

- **Servicio**: `Notifications List`
- **Metodo/Ruta**: `GET /v1/notifications?page=1&pageSize=20&unreadOnly=false`
- **Auth**: Bearer

## 5.4 Marcar notificacion leida

- **Servicio**: `Notification Read`
- **Metodo/Ruta**: `POST /v1/notifications/{id}/read`
- **Auth**: Bearer

## 5.5 Marcar todas leidas

- **Servicio**: `Notifications Read All`
- **Metodo/Ruta**: `POST /v1/notifications/read-all`
- **Auth**: Bearer

---

## 6) Pagos y cuotas

## 6.1 Registrar pagos

- **Servicio**: `Register Payment`
- **Metodo/Ruta**: `POST /api/v1/pagos/registrar`
- **Auth**: No (segun codigo actual)

### Request (resumen)
```json
{
  "creditoId": "100",
  "montoTotal": 330.0,
  "fechaPago": "2026-05-19T15:00:00Z",
  "comentario": "Pago parcial",
  "comprobante": [
    {
      "numero_operacion": "OP-001",
      "image": "<base64>"
    }
  ],
  "cuotas": [
    {
      "cuotaId": "2001",
      "montoCuota": 330.0,
      "montoMora": 0.0,
      "montoPagado": 330.0,
      "estadoPago": "PAGADO"
    }
  ]
}
```

### Response (200)
```json
{
  "success": true,
  "data": {
    "pagoId": "uuid",
    "comprobante": [{ "numero_operacion": "OP-001" }],
    "montoTotal": 330.0,
    "fechaPago": "2026-05-19T15:00:00Z",
    "cuotas": [
      {
        "cuotaId": "2001",
        "estado": "PAGADO",
        "montoPagado": 330.0,
        "saldoPendiente": 0.0,
        "voucherUrls": ["https://.../web/content/123"]
      }
    ]
  }
}
```

## 6.2 Subir voucher por cuota

- **Servicio**: `Upload Voucher`
- **Metodo/Ruta**: `POST /v1/installments/upload_voucher`
- **Auth**: No (segun codigo actual)

### Request
```json
{
  "cuota_id": 2001,
  "voucher_image": "<base64>"
}
```

---

## 7) Papeletas

## 7.1 Registrar papeleta

- **Servicio**: `Papeleta Register`
- **Metodo/Ruta**: `POST /v1/papeletas/register`
- **Auth**: Bearer

### Request
```json
{
  "numeroPapeleta": "PAP-001",
  "fechaPapeleta": "2026-05-18",
  "monto": 150.0,
  "idVehiculo": 10,
  "fotos": ["<base64>"]
}
```

### Response (200)
```json
{
  "success": true,
  "data": {
    "id": 1,
    "numeroPapeleta": "PAP-001",
    "fechaPapeleta": "2026-05-18",
    "monto": 150.0,
    "idVehiculo": 10,
    "fotosCount": 1,
    "fotoUrls": ["https://.../web/content/10"]
  }
}
```

## 7.2 Listar papeletas

- **Servicio**: `Papeletas List`
- **Metodo/Ruta**: `GET /v1/papeletas?idVehiculo=10`
- **Auth**: Bearer

---

## 8) Mantenimiento TVS (existentes)

## 8.1 Registrar linea mantenimiento

- **Servicio**: `Maintenance Record`
- **Metodo/Ruta**: `POST /v1/maintenance/record`
- **Auth**: No (segun codigo actual)

### Request
```json
{
  "vehicle_id": 10,
  "km_objetivo": 1500,
  "realizado": true,
  "attachment_ids": [1, 2],
  "fecha_inicio": "2026-05-01",
  "fecha_fin": "2026-05-02"
}
```

## 8.2 Listar lineas mantenimiento

- **Servicio**: `Maintenance Lines`
- **Metodo/Ruta**: `GET /v1/maintenance/lines?vehicle_id=10`
- **Auth**: No (segun codigo actual)

---

## 9) FCM

## 9.1 Registrar token FCM

- **Servicio**: `FCM Register`
- **Metodo/Ruta**: `POST /v1/fcm/register`
- **Auth**: Bearer

### Request
```json
{
  "fcm_token": "<fcm-token>",
  "platform": "android",
  "device_info": {
    "device_id": "A1",
    "device_name": "Samsung",
    "device_os": "Android 14",
    "app_version": "1.2.0"
  }
}
```

---

## 10) Taller - nuevos servicios

## 10.1 Buscar por placa (cliente + vehiculo)

- **Servicio**: `Workshop Search By Plate`
- **Metodo/Ruta**: `GET /v1/workshop/search-by-plate?plate=DEF-456`
- **Auth**: Bearer

### Response (200)
```json
{
  "success": true,
  "data": {
    "cliente": {
      "id": 55,
      "name": "Pedro Quispe",
      "document": "12345678",
      "phone": "999999999"
    },
    "vehiculo": {
      "id": 10,
      "plate": "DEF-456",
      "model": "Sportage",
      "brand": "Kia",
      "vin": "...",
      "displayName": "DEF-456 Kia Sportage"
    }
  }
}
```

## 10.2 Lista de productos

- **Servicio**: `Workshop Products`
- **Metodo/Ruta**: `GET /v1/workshop/products?q=filtro&page=1&pageSize=20`
- **Auth**: Bearer

### Response
```json
{
  "success": true,
  "data": {
    "items": [
      { "id": 1, "name": "Filtro de aceite", "defaultPrice": 35.0 }
    ]
  }
}
```

## 10.3 Lista de mano de obra

- **Servicio**: `Workshop Labor Templates`
- **Metodo/Ruta**: `GET /v1/workshop/labor-templates?q=filtro`
- **Auth**: Bearer

## 10.4 Catalogos de taller

- **Servicio**: `Workshop Catalogs`
- **Metodo/Ruta**: `GET /v1/workshop/catalogs`
- **Auth**: Bearer

### Response
```json
{
  "success": true,
  "data": {
    "payerTypes": [
      { "value": "adt", "label": "ADT Corporación" },
      { "value": "cliente", "label": "Cliente" },
      { "value": "ambos", "label": "Ambos" }
    ],
    "finalResultTypes": [
      { "value": "optimal", "label": "Óptimo" },
      { "value": "with_observations", "label": "Con Observaciones" },
      { "value": "follow_up", "label": "Seguimiento" }
    ],
    "workOrderStates": [
      { "value": "pending", "label": "Pendiente" },
      { "value": "in_progress", "label": "En progreso" },
      { "value": "blocked", "label": "Bloqueado" },
      { "value": "done", "label": "Finalizado" }
    ]
  }
}
```

## 10.5 Listar ordenes de trabajo

- **Servicio**: `Workshop Work Orders List`
- **Metodo/Ruta**: `GET /v1/workshop/work-orders?page=1&pageSize=20&state=...&plate=...&vehicleId=...`
- **Auth**: Bearer

### Item de lista (formato tarjeta)
```json
{
  "id": 39,
  "code": "OT-0039",
  "daysInWorkshop": 3,
  "daysLabel": "3 días",
  "state": "in_progress",
  "stateLabel": "En progreso",
  "clientName": "Pedro Quispe",
  "vehicleLabel": "DEF-456 · Kia Sportage",
  "relativeTime": "hace 3 días",
  "mechanicInitials": "JR",
  "mechanicName": "J. Ramos",
  "totalAmount": 1240.0,
  "totalAmountLabel": "S/ 1,240.00"
}
```

## 10.6 Crear/actualizar/pausar/reanudar/finalizar OT

- **Servicio**: `Workshop Work Order Save`
- **Metodo/Ruta**: `POST /v1/workshop/work-orders`
- **Auth**: Bearer

### Crear (guardado parcial)
```json
{
  "vehicleId": 10,
  "entryReason": "Mantenimiento preventivo",
  "diagnostic": "Revision inicial",
  "payerType": "cliente",
  "parts": [
    { "productId": 1, "quantity": 1, "unitPrice": 80.0, "notes": "Original" }
  ],
  "services": [
    { "serviceTemplateId": 3, "name": "Cambio de aceite", "unitPrice": 60.0 }
  ],
  "paymentSchedule": [
    { "name": "Cuota 1", "dueDate": "2026-05-30", "amount": 140.0, "payer": "cliente", "state": "pending" }
  ],
  "state": "pending"
}
```

### Actualizar
```json
{
  "workOrderId": 39,
  "diagnostic": "Se reemplaza filtro",
  "parts": [
    { "productId": 1, "quantity": 2, "unitPrice": 80.0 }
  ]
}
```

### Pausar
```json
{
  "workOrderId": 39,
  "action": "pause"
}
```

### Reanudar
```json
{
  "workOrderId": 39,
  "action": "resume"
}
```

### Finalizar
```json
{
  "workOrderId": 39,
  "action": "finalize",
  "finalState": "optimal",
  "finalNotes": "Sin observaciones"
}
```

### Response (200)
```json
{
  "success": true,
  "message": "Orden de trabajo actualizada correctamente.",
  "data": {
    "workOrder": {
      "id": 39,
      "code": "OT-0039",
      "state": "blocked",
      "stateLabel": "Bloqueado",
      "parts": [],
      "services": [],
      "paymentSchedule": []
    }
  }
}
```

---

## 11) Enums utiles para Android

### Workshop states
- `pending` -> `Pendiente`
- `in_progress` -> `En progreso`
- `blocked` -> `Bloqueado`
- `done` -> `Finalizado`

### Workshop payer types
- `adt`
- `cliente`
- `ambos`

### Workshop final results
- `optimal`
- `with_observations`
- `follow_up`

---

## 12) Notas de integracion

- En rutas `type='http'`, enviar JSON plano en body.
- En rutas `type='json'` (`/v1/auth/login`, `/v1/auth/logout`, `/v1/promotions`, `/v1/maintenance/record`), el controlador actual consume `request.jsonrequest` como objeto JSON.
- `POST /api/v1/pagos/registrar` usa formato de error distinto (`code/message/field`), manejarlo por separado en Android.
- Varios endpoints devuelven URLs de archivos para abrir en navegador (`/web/content/<id>` o `/web/image/...`).

