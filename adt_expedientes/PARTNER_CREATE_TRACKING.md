# Partner Create & Update Tracking - User ID

## Cambios Implementados

Se han modificado los endpoints `/adt_expedientes/mobile/partner/create` y `/adt_expedientes/mobile/partner/update` para permitir rastrear qué usuario (asesor) creó o actualizó los partners desde la aplicación móvil.

---

## 1. Partner Create - Nuevo Parámetro

### Endpoint: `/adt_expedientes/mobile/partner/create`

### `created_by_user_id` (opcional)
- **Tipo**: Integer
- **Descripción**: ID del usuario que está creando el partner
- **Efecto**: Si se proporciona, el campo `create_uid` del partner se establecerá con este usuario

### Ejemplo de Uso - Partner Create

#### Request

```json
POST /adt_expedientes/mobile/partner/create
Content-Type: application/json
Authorization: Bearer <token>

{
    "created_by_user_id": 8,
    "vals": {
        "nombre_completo": "Juan",
        "apellido_paterno": "Perez",
        "apellido_materno": "Lopez",
        "document_number": "12345678",
        "nationality": "peruana",
        "occupation": "comerciante",
        "mobile": "987654321",
        "country_id": "PE",
        "state_id": "15"
    }
}
```

#### Response

```json
{
    "success": true,
    "data": {
        "id": 123
    }
}
```

---

## 2. Partner Update - Nuevo Parámetro

### Endpoint: `/adt_expedientes/mobile/partner/update`

### `created_by_user_id` (opcional)
- **Tipo**: Integer
- **Descripción**: ID del usuario (asesor) que está actualizando el partner
- **Efecto**: Si se proporciona, el campo `write_uid` del partner se establecerá con este usuario

### Ejemplo de Uso - Partner Update

#### Request

```json
POST /adt_expedientes/mobile/partner/update
Content-Type: application/json
Authorization: Bearer <token>

{
    "partner_id": 123,
    "created_by_user_id": 8,
    "vals": {
        "mobile": "987654321",
        "email": "juan.perez@example.com",
        "city": "Lima"
    }
}
```

O usando document_number:

```json
POST /adt_expedientes/mobile/partner/update
Content-Type: application/json
Authorization: Bearer <token>

{
    "document_number": "12345678",
    "created_by_user_id": 8,
    "vals": {
        "mobile": "987654321",
        "email": "juan.perez@example.com"
    }
}
```

#### Response

```json
{
    "success": true,
    "data": {
        "id": 123
    }
}
```

---

## Funcionalidad Partner Create

1. El endpoint extrae el parámetro `created_by_user_id` del payload
2. Verifica que el usuario exista en el sistema
3. Utiliza `.with_user(creator_user_id)` para crear el partner en el contexto de ese usuario
4. El campo `create_uid` del partner se establece automáticamente con ese usuario
5. Se registran logs informativos indicando quién creó el partner

---

## Funcionalidad Partner Update

1. El endpoint extrae el parámetro `created_by_user_id` del payload
2. Verifica que el usuario exista en el sistema
3. Utiliza `.with_user(updater_user_id)` para actualizar el partner en el contexto de ese usuario
4. El campo `write_uid` del partner se establece automáticamente con ese usuario
5. Se registran logs informativos indicando quién actualizó el partner

---

## Logs

El sistema genera logs en los siguientes casos:

### Partner Create
- **Info**: Cuando se crea exitosamente con un usuario específico
- **Warning**: Cuando el user_id proporcionado no existe o es inválido
- **Info**: Confirmación del partner creado con el nombre del usuario creador
- **Error**: Si ocurre algún error durante la creación

### Partner Update
- **Info**: Cuando se actualizará el partner con un usuario específico
- **Warning**: Cuando el user_id proporcionado no existe o es inválido
- **Info**: Confirmación del partner actualizado con el nombre del usuario que actualizó
- **Error**: Si ocurre algún error durante la actualización

---

## Compatibilidad

- Si no se proporciona `created_by_user_id`, el sistema funciona como antes
- El parámetro es completamente opcional en ambos endpoints
- No rompe la compatibilidad con implementaciones existentes

---

## Verificación

### Para Partner Create:
Para verificar que el partner fue creado por el usuario correcto:

1. En Odoo, ir al partner creado
2. Ver el campo "Creado por" (Create UID)
3. Debe mostrar el nombre del usuario cuyo ID fue proporcionado

O mediante consulta SQL:
```sql
SELECT id, name, create_uid, create_date 
FROM res_partner 
WHERE id = <partner_id>;
```

### Para Partner Update:
Para verificar que el partner fue actualizado por el usuario correcto:

1. En Odoo, ir al partner actualizado
2. Activar el modo desarrollador
3. Ver el campo "Última actualización por" (write_uid)
4. Debe mostrar el nombre del usuario cuyo ID fue proporcionado

O mediante consulta SQL:
```sql
SELECT id, name, create_uid, write_uid, write_date
FROM res_partner 
WHERE id = <partner_id>;
```

---

## Flujo Completo de Uso

```json
// 1. Crear partner con asesor
POST /adt_expedientes/mobile/partner/create
{
    "created_by_user_id": 8,
    "nombre_completo": "Maria",
    "apellido_paterno": "Rodriguez",
    "apellido_materno": "Garcia",
    "document_number": "87654321"
}
// Response: {"success": true, "data": {"id": 456}}

// 2. Actualizar partner con el mismo asesor
POST /adt_expedientes/mobile/partner/update
{
    "partner_id": 456,
    "created_by_user_id": 8,
    "vals": {
        "mobile": "999888777",
        "email": "maria.rodriguez@example.com",
        "city": "Lima"
    }
}
// Response: {"success": true, "data": {"id": 456}}

// 3. Crear expediente con ese cliente
POST /adt_expedientes/mobile/expediente/create
{
    "cliente_id": 456,
    "vehiculo": "moto_duramax_225"
}
// Response: {"success": true, "data": {"id": 50}}
```

---

## Campos Rastreados

| Endpoint | Campo Rastreado | Descripción |
|----------|----------------|-------------|
| `partner/create` | `create_uid` | Usuario que creó el partner |
| `partner/update` | `write_uid` | Usuario que actualizó el partner por última vez |

Ambos campos son nativos de Odoo y permiten una auditoría completa de las operaciones realizadas desde la aplicación móvil.

---

## 1. Partner Create - Nuevo Parámetro

### Endpoint: `/adt_expedientes/mobile/partner/create`

### `created_by_user_id` (opcional)
- **Tipo**: Integer
- **Descripción**: ID del usuario que está creando el partner
- **Efecto**: Si se proporciona, el campo `create_uid` del partner se establecerá con este usuario

### Ejemplo de Uso - Partner Create

#### Request

```json
POST /adt_expedientes/mobile/partner/create
Content-Type: application/json
Authorization: Bearer <token>

{
    "created_by_user_id": 8,
    "vals": {
        "nombre_completo": "Juan",
        "apellido_paterno": "Perez",
        "apellido_materno": "Lopez",
        "document_number": "12345678",
        "nationality": "peruana",
        "occupation": "comerciante",
        "mobile": "987654321",
        "country_id": "PE",
        "state_id": "15"
    }
}
```

#### Response

```json
{
    "success": true,
    "data": {
        "id": 123
    }
}
```

---

## 2. Expediente Update - Nuevo Parámetro

### Endpoint: `/adt_expedientes/mobile/expediente/update`

### `created_by_user_id` (opcional)
- **Tipo**: Integer
- **Descripción**: ID del usuario (asesor) que está actualizando el expediente
- **Efecto**: Si se proporciona, el campo `asesora_id` del expediente se establecerá con este usuario

### Ejemplo de Uso - Expediente Update

#### Request

```json
POST /adt_expedientes/mobile/expediente/update
Content-Type: application/json
Authorization: Bearer <token>

{
    "expediente_id": 10,
    "created_by_user_id": 8,
    "vals": {
        "direccion_cliente": "Av. Los Pinos 123",
        "placa": "ABC-123",
        "vehiculo": "moto_deluxe_200"
    }
}
```

#### Response

```json
{
    "success": true,
    "data": {
        "id": 10
    }
}
```

---

## Funcionalidad Partner Create

1. El endpoint extrae el parámetro `created_by_user_id` del payload
2. Verifica que el usuario exista en el sistema
3. Utiliza `.with_user(creator_user_id)` para crear el partner en el contexto de ese usuario
4. El campo `create_uid` del partner se establece automáticamente con ese usuario
5. Se registran logs informativos indicando quién creó el partner

---

## Funcionalidad Expediente Update

1. El endpoint extrae el parámetro `created_by_user_id` del payload
2. Verifica que el usuario exista en el sistema
3. Agrega el campo `asesora_id` a los valores a actualizar
4. El campo `asesora_id` del expediente se establece con ese usuario
5. Se registran logs informativos indicando el asesor asignado

---

## Logs

El sistema genera logs en los siguientes casos:

### Partner Create
- **Info**: Cuando se crea exitosamente con un usuario específico
- **Warning**: Cuando el user_id proporcionado no existe o es inválido
- **Info**: Confirmación del partner creado con el nombre del usuario creador

### Expediente Update
- **Info**: Cuando se actualizará el expediente con un asesora_id específico
- **Warning**: Cuando el user_id proporcionado no existe o es inválido
- **Info**: Confirmación del expediente actualizado con el nombre del asesor asignado
- **Error**: Si ocurre algún error durante la actualización

---

## Compatibilidad

- Si no se proporciona `created_by_user_id`, el sistema funciona como antes
- El parámetro es completamente opcional en ambos endpoints
- No rompe la compatibilidad con implementaciones existentes

---

## Verificación

### Para Partner:
Para verificar que el partner fue creado por el usuario correcto:

1. En Odoo, ir al partner creado
2. Ver el campo "Creado por" (Create UID)
3. Debe mostrar el nombre del usuario cuyo ID fue proporcionado

O mediante consulta SQL:
```sql
SELECT id, name, create_uid, create_date 
FROM res_partner 
WHERE id = <partner_id>;
```

### Para Expediente:
Para verificar que el expediente fue actualizado con el asesor correcto:

1. En Odoo, ir al expediente actualizado
2. Ver el campo "Asesora" (asesora_id)
3. Debe mostrar el nombre del usuario cuyo ID fue proporcionado

O mediante consulta SQL:
```sql
SELECT id, cliente_id, asesora_id, create_date, write_date
FROM adt_expediente 
WHERE id = <expediente_id>;
```

---

## Flujo Completo de Uso

```json
// 1. Crear partner con asesor
POST /adt_expedientes/mobile/partner/create
{
    "created_by_user_id": 8,
    "nombre_completo": "Maria",
    "apellido_paterno": "Rodriguez",
    "document_number": "87654321"
}
// Response: {"success": true, "data": {"id": 456}}

// 2. Crear expediente
POST /adt_expedientes/mobile/expediente/create
{
    "cliente_id": 456,
    "vehiculo": "moto_duramax_225"
}
// Response: {"success": true, "data": {"id": 50}}

// 3. Actualizar expediente con asesor
POST /adt_expedientes/mobile/expediente/update
{
    "expediente_id": 50,
    "created_by_user_id": 8,
    "vals": {
        "direccion_cliente": "Calle Lima 456",
        "placa": "XYZ-789"
    }
}
// Response: {"success": true, "data": {"id": 50}}
```

