# Actualización de Servicios con Campos de Nombre

## Cambios Realizados

Se han modificado dos endpoints para aceptar los nuevos campos del contacto:
- `nombre_completo`
- `apellido_paterno`
- `apellido_materno`

### Endpoints Modificados:
1. `/adt_expedientes/mobile/partner/create` - Crear contacto
2. `/adt_expedientes/mobile/expediente/create` - Crear expediente

## 1️⃣ Servicio: partner/create

### Funcionalidad

Cuando se envían los campos de nombre al crear un partner, el sistema:

1. **Extrae los campos** del payload JSON
2. **Construye el nombre completo** concatenando los tres campos en el orden:
   - `nombre_completo + apellido_paterno + apellido_materno`
3. **Asigna el valor al campo `name`** automáticamente
4. **Guarda los campos individuales** en el partner

### Ejemplo de Uso

#### Request
```json
POST /adt_expedientes/mobile/partner/create
{
  "nombre_completo": "Juan",
  "apellido_paterno": "Pérez",
  "apellido_materno": "García",
  "document_number": "12345678",
  "nationality": "peruana",
  "mobile": "987654321"
}
```

#### Comportamiento
- Se crea un partner con:
  - `nombre_completo`: "Juan"
  - `apellido_paterno`: "Pérez"
  - `apellido_materno`: "García"
  - `name`: "Juan Pérez García" (auto-generado)
  - Otros campos como document_number, nationality, etc.

#### Response
```json
{
  "success": true,
  "data": {
    "id": 123
  }
}
```

### ⚠️ Validación Importante
- **Se requiere** al menos uno de los siguientes:
  - Campo `name` directamente, O
  - Al menos uno de: `nombre_completo`, `apellido_paterno`, `apellido_materno`
- Si envías los campos individuales, el `name` se construye automáticamente
- Si no envías ni `name` ni los campos individuales, se devuelve error

## 2️⃣ Servicio: expediente/create

Cuando se envían estos campos al crear un expediente, el sistema:

1. **Extrae los campos** del payload JSON
2. **Construye el nombre completo** concatenando los tres campos en el orden:
   - `nombre_completo + apellido_paterno + apellido_materno`
3. **Actualiza el partner** asociado al expediente con:
   - Los tres campos individuales (nombre_completo, apellido_paterno, apellido_materno)
   - El campo `name` con el nombre completo construido

## Ejemplo de Uso

### Request
```json
POST /adt_expedientes/mobile/expediente/create
{
  "cliente_id": 123,
  "vehiculo": "moto_deluxe_200",
  "nombre_completo": "Juan",
  "apellido_paterno": "Pérez",
  "apellido_materno": "García"
}
```

### Comportamiento
- El partner con ID 123 será actualizado con:
  - `nombre_completo`: "Juan"
  - `apellido_paterno`: "Pérez"
  - `apellido_materno`: "García"
  - `name`: "Juan Pérez García" (auto-generado)
- Se crea el expediente con el cliente_id y vehículo especificados

### Response
```json
{
  "success": true,
  "data": {
    "id": 456
  }
}
```

## Notas Importantes

1. **Campos opcionales**: Si alguno de los tres campos está vacío, se omite de la concatenación
2. **Actualización automática**: Si el partner ya existe, sus datos de nombre se actualizan automáticamente
3. **Logging**: Se registra en el log de Odoo cada vez que se actualiza un partner con el nuevo nombre
4. **Manejo de errores**: Si falla la actualización del partner, se devuelve un error descriptivo

## Escenarios de Uso

### Escenario 1: Todos los campos completos
```json
{
  "nombre_completo": "María",
  "apellido_paterno": "González",
  "apellido_materno": "López"
}
```
→ Resultado: `name = "María González López"`

### Escenario 2: Sin apellido materno
```json
{
  "nombre_completo": "Carlos",
  "apellido_paterno": "Rodríguez",
  "apellido_materno": ""
}
```
→ Resultado: `name = "Carlos Rodríguez"`

### Escenario 3: Solo nombre completo
```json
{
  "nombre_completo": "Ana María",
  "apellido_paterno": "",
  "apellido_materno": ""
}
```
→ Resultado: `name = "Ana María"`
