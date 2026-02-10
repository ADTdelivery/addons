# Ejemplos de Prueba para Servicios con Nombres

## 1️⃣ Pruebas para partner/create

### 1.1 Crear partner con todos los campos de nombre
```bash
curl -X POST http://localhost:8069/adt_expedientes/mobile/partner/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "nombre_completo": "María Elena",
    "apellido_paterno": "González",
    "apellido_materno": "López",
    "document_number": "12345678",
    "nationality": "peruana",
    "mobile": "987654321",
    "email": "maria@example.com",
    "country_id": "PE",
    "state_id": "LIM"
  }'
```

### 1.2 Crear partner sin apellido materno
```bash
curl -X POST http://localhost:8069/adt_expedientes/mobile/partner/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "nombre_completo": "Carlos",
    "apellido_paterno": "Rodríguez",
    "document_number": "87654321",
    "mobile": "999888777"
  }'
```

### 1.3 Crear partner solo con nombre (modo tradicional)
```bash
curl -X POST http://localhost:8069/adt_expedientes/mobile/partner/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "name": "Empresa ABC S.A.C.",
    "document_number": "20123456789",
    "mobile": "987654321"
  }'
```

### Respuestas partner/create

#### Éxito
```json
{
  "success": true,
  "data": {
    "id": 456
  }
}
```

#### Error - Partner duplicado
```json
{
  "success": true,
  "data": {
    "id": 456,
    "message": "existing"
  }
}
```

#### Error - Sin nombre
```json
{
  "success": false,
  "error": "name or (nombre_completo/apellido_paterno/apellido_materno) required"
}
```

---

## 2️⃣ Pruebas para expediente/create

### 1. Con todos los campos de nombre
```bash
curl -X POST http://localhost:8069/adt_expedientes/mobile/expediente/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "cliente_id": 123,
    "vehiculo": "moto_deluxe_200",
    "nombre_completo": "Juan Carlos",
    "apellido_paterno": "Pérez",
    "apellido_materno": "García",
    "direccion_cliente": "Av. Principal 123"
  }'
```

### 2. Sin apellido materno
```bash
curl -X POST http://localhost:8069/adt_expedientes/mobile/expediente/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "cliente_id": 456,
    "vehiculo": "moto_standard_150",
    "nombre_completo": "María",
    "apellido_paterno": "González",
    "apellido_materno": ""
  }'
```

### 3. Usando document_number en lugar de cliente_id
```bash
curl -X POST http://localhost:8069/adt_expedientes/mobile/expediente/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -d '{
    "document_number": "12345678",
    "vehiculo": "moto_deluxe_200",
    "nombre_completo": "Pedro",
    "apellido_paterno": "Ramírez",
    "apellido_materno": "Silva"
  }'
```

## Respuestas Esperadas

### Éxito
```json
{
  "success": true,
  "data": {
    "id": 789
  }
}
```

### Error - Cliente no encontrado
```json
{
  "success": false,
  "error": "cliente_id is required (or provide document_number/dni to lookup partner)"
}
```

### Error - Actualización de partner fallida
```json
{
  "success": false,
  "error": "Error actualizando datos del cliente: [detalle del error]"
}
```

## Verificación en Odoo

Después de crear el expediente, verifica:

1. **Expediente creado**: Ve a Expedientes y busca el ID retornado
2. **Partner actualizado**: Ve a Contactos y busca el partner con el cliente_id
3. **Campos actualizados**:
   - `name` debe mostrar el nombre completo concatenado
   - `nombre_completo`, `apellido_paterno`, `apellido_materno` deben tener los valores enviados

## Logs en Odoo

Busca en los logs de Odoo:
```
INFO: Partner 123 actualizado con nombre: Juan Carlos Pérez García
```

## Notas para Desarrollo Móvil

1. **Campos requeridos**:
   - `cliente_id` O `document_number`/`dni`
   - Al menos uno de: `nombre_completo`, `apellido_paterno`, `apellido_materno`

2. **Campos opcionales**:
   - `vehiculo`, `fecha`, `direccion_cliente`, `placa`, `chasis`

3. **Token de autenticación**:
   - Debe enviarse en el header `Authorization: Bearer TOKEN`
   - O en el body como `{"token": "TOKEN"}`

4. **Comportamiento**:
   - Si envías los campos de nombre, el partner se actualiza automáticamente
   - Si no los envías, el partner mantiene sus valores actuales
   - El nombre completo se construye concatenando los tres campos
