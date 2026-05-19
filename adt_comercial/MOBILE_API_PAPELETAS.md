# Mobile API - Servicios de Papeletas

Este documento describe los servicios:

- `POST /v1/papeletas/register`
- `GET /v1/papeletas`

## Autenticacion

Todos los servicios requieren header:

```http
Authorization: Bearer <token>
```

Para `POST` usar tambien:

```http
Content-Type: application/json
```

---

## 1) Registrar papeleta

**Endpoint**

```http
POST /v1/papeletas/register
```

### Request

```json
{
  "numeroPapeleta": "PAP-001",
  "fechaPapeleta": "2026-05-18",
  "monto": 150.00,
  "idVehiculo": 10,
  "fotos": [
    "<base64_1>",
    "<base64_2>"
  ]
}
```

### Campos

- `numeroPapeleta` (string, requerido)
- `fechaPapeleta` (string, requerido) formato `YYYY-MM-DD` o ISO-8601
- `monto` (number, requerido) mayor a 0
- `idVehiculo` (int, requerido)
- `fotos` (array string base64, requerido, minimo 1 imagen)

### Response 200 (OK)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "Papeleta registrada correctamente.",
  "data": {
    "id": 15,
    "numeroPapeleta": "PAP-001",
    "fechaPapeleta": "2026-05-18",
    "monto": 150.0,
    "idVehiculo": 10,
    "fotosCount": 2,
    "fotoUrls": [
      "https://tu-dominio/web/content/123",
      "https://tu-dominio/web/content/124"
    ]
  },
  "meta": {
    "timestamp": "2026-05-18T18:30:12Z",
    "requestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

### Errores comunes

- `401 TOKEN_MISSING|TOKEN_INVALID|TOKEN_EXPIRED`
- `403 FORBIDDEN` (token no autorizado para ese vehiculo)
- `404 VEHICLE_NOT_FOUND`
- `409 PAPELETA_DUPLICADA`
- `422 VALIDATION_ERROR`
- `500 INTERNAL_ERROR`

---

## 2) Listar papeletas por vehiculo

**Endpoint**

```http
GET /v1/papeletas
```

### Query params

- `idVehiculo` (opcional)
- `vehicle_id` (opcional)

Si no se envian, el servicio intenta usar `vehicle_id` del token.

### Ejemplo Request

```http
GET /v1/papeletas?idVehiculo=10
Authorization: Bearer <token>
```

### Response 200 (OK)

```json
{
  "success": true,
  "statusCode": 200,
  "message": "OK",
  "data": {
    "idVehiculo": 10,
    "placa": "ABC-123",
    "totalPapeletas": 2,
    "papeletas": [
      {
        "id": 15,
        "numeroPapeleta": "PAP-001",
        "fechaPapeleta": "2026-05-18",
        "monto": 150.0,
        "idVehiculo": 10,
        "fotosCount": 2,
        "fotoUrls": [
          "https://tu-dominio/web/content/123",
          "https://tu-dominio/web/content/124"
        ]
      },
      {
        "id": 14,
        "numeroPapeleta": "PAP-000",
        "fechaPapeleta": "2026-05-10",
        "monto": 250.0,
        "idVehiculo": 10,
        "fotosCount": 1,
        "fotoUrls": [
          "https://tu-dominio/web/content/122"
        ]
      }
    ]
  },
  "meta": {
    "timestamp": "2026-05-18T18:31:00Z",
    "requestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

### Errores comunes

- `401 TOKEN_MISSING|TOKEN_INVALID|TOKEN_EXPIRED`
- `403 FORBIDDEN`
- `404 VEHICLE_NOT_FOUND`
- `422 VALIDATION_ERROR` (si no llega `idVehiculo` y el token no tiene vehiculo)
- `500 INTERNAL_ERROR`

