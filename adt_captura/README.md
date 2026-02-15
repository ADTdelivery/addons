# Módulo ADT Captura - Gestión de Capturas de Vehículos en Mora

## 📋 Descripción

Módulo completo para la gestión del proceso de captura de vehículos con pagos en mora, incluyendo:

- ✅ Identificación automática de clientes en mora
- ✅ Registro de capturas con evidencia obligatoria
- ✅ Gestión de pagos de intervención (S/ 50.00)
- ✅ Control de liberación y retención de vehículos
- ✅ Historial completo con trazabilidad
- ✅ Validaciones de negocio robustas
- ✅ Sistema de roles y permisos

## 🎯 Características Principales

### 1. Vista de Clientes en Mora
- **Modelo**: `adt.captura.mora` (Vista SQL automática)
- Muestra clientes con cuotas vencidas
- Calcula días de mora automáticamente
- Identifica estado crítico según tipo de cartera:
  - **Qorilazo**: ≥ 14 días = Crítico
  - **Los Andes**: ≥ 7 días = Crítico
- Información de GPS, contacto y asesor
- Botón directo para iniciar captura

### 2. Registro de Capturas
- **Modelo**: `adt.captura.record`
- Tipos de captura:
  - Inmediata
  - Compromiso de Pago (requiere fecha futura)
  - Condicional
- Evidencia obligatoria (imágenes/videos)
- Deuda automática de S/ 50.00
- Estados: Capturado → Liberado / Retenido / Cancelado
- Seguimiento de pagos: Pendiente / Pagado

### 3. Gestión de Pagos
- Wizard para registrar pago de intervención
- Campos: Voucher, número, fecha, monto
- Validaciones: voucher obligatorio, fecha no futura
- Notificación automática al registrar

### 4. Retención de Vehículos
- Wizard para retener vehículo
- Motivo obligatorio (mínimo 10 caracteres)
- Solo supervisores pueden retener
- Acción irreversible

## 👥 Roles y Permisos

### Capturador
- ✅ Ver clientes en mora
- ✅ Crear capturas
- ✅ Adjuntar evidencia
- ✅ Registrar pagos
- ❌ No puede liberar ni retener

### Supervisor
- ✅ Todo lo del Capturador
- ✅ Liberar vehículos (con pago registrado)
- ✅ Retener vehículos
- ✅ Cancelar capturas

### Administrador
- ✅ Acceso total
- ✅ Configuraciones
- ✅ Eliminar registros

## 🔄 Flujos de Trabajo

### Flujo 1: Captura Normal
```
1. Ver "Clientes en Mora"
2. Seleccionar cliente → "Iniciar Captura"
3. Completar formulario:
   - Tipo de captura
   - Adjuntar evidencia (obligatorio)
   - Observaciones
4. Guardar → Estado: "Capturado"
5. "Registrar Pago" → Adjuntar voucher
6. Estado pago: "Pagado"
7. Supervisor → "Liberar Vehículo"
8. Estado: "Liberado" → Va a Historial
```

### Flujo 2: Retención
```
1. Desde captura activa
2. Supervisor → "Retener Vehículo"
3. Ingresar motivo (obligatorio)
4. Confirmar
5. Estado: "Retenido" → Va a Historial
```

### Flujo 3: Compromiso de Pago
```
1. Iniciar captura
2. Tipo: "Compromiso de Pago"
3. Fecha compromiso (debe ser futura)
4. Adjuntar evidencia
5. Guardar
6. Seguimiento hasta cumplimiento
```

## 🔐 Validaciones Implementadas

### Al Crear Captura
- ❌ Evidencia obligatoria (no se puede guardar sin imágenes/videos)
- ❌ Fecha compromiso debe ser futura (si tipo = compromiso)
- ❌ No duplicar capturas activas para misma cuenta

### Al Registrar Pago
- ❌ Voucher obligatorio
- ❌ Monto mayor a cero
- ❌ Fecha no futura

### Al Liberar
- ❌ Solo supervisores
- ❌ Pago debe estar registrado
- ❌ Solo desde estado "Capturado"

### Al Retener
- ❌ Solo supervisores
- ❌ Motivo obligatorio (mín. 10 caracteres)
- ❌ Solo desde estado "Capturado"
- ❌ Acción irreversible

## 📊 Estructura de Datos

### adt.captura.record (Tabla física)
```
- name: Número (CAP-00001)
- partner_id: Cliente
- cuenta_id: Cuenta
- vehicle_id: Vehículo (automático)
- capture_type: Tipo captura
- commitment_date: Fecha compromiso
- evidence_attachment_ids: Evidencias (M2M)
- notes: Observaciones
- intervention_fee: Monto intervención (default 50)
- state: Estado (capturado/liberado/retenido/cancelado)
- payment_state: Estado pago (pendiente/pagado)
- voucher_file: Archivo voucher
- voucher_number: N° voucher
- payment_date: Fecha pago
- retention_reason: Motivo retención
- retention_date: Fecha retención
- capturador_id: Usuario que capturó
- supervisor_id: Usuario supervisor
- dias_mora: Días de mora (computed)
- tipo_cartera: Tipo (computed from cuenta)
- estado_mora: Normal/Crítico (computed)
```

### adt.captura.mora (Vista SQL - Solo lectura)
```
- partner_id: Cliente
- cuenta_id: Cuenta
- vehicle_id: Vehículo
- reference_no: N° cuenta
- dias_mora: Días mora (calculado)
- tipo_cartera: Qorilazo/Los Andes
- estado_mora: Normal/Crítico
- fecha_cronograma: Primera cuota vencida
- monto_vencido: Total vencido
- numero_cuotas_vencidas: Cantidad
- gps_chip: Chip GPS
- gps_activo: GPS activo
- phone, mobile, vat: Contacto
- user_id: Asesor
- captura_existente: Ya tiene captura activa
```

## 🎨 Vistas Disponibles

### Clientes en Mora
- Tree view con colores (crítico=rojo, normal=amarillo)
- Form view con toda la información
- Kanban view para visualización de tarjetas
- Search con múltiples filtros

### Capturas Activas
- Tree view con badges de estado
- Form completo con header buttons
- Chatter para seguimiento
- Botones contextuales según estado

### Historial
- Tree view solo lectura
- Filtrado por estados finales
- Sin opción de crear

## 📱 Menús

```
Gestión de Capturas
└── Operaciones
    ├── Clientes en Mora (Vista SQL)
    ├── Capturas Activas (Estado = Capturado)
    └── Historial (Estados finales)
```

## ⚙️ Configuración

### 1. Instalación
```bash
# Activar modo desarrollador
# Apps → Buscar "ADT Captura" → Instalar
```

### 2. Asignar Roles
```
Configuración → Usuarios y Compañías → Usuarios
→ Seleccionar usuario
→ Pestaña "Derechos de acceso"
→ Asignar grupo:
   - Capturador
   - Supervisor de Captura
   - Administrador de Captura
```

### 3. Verificar Secuencia
La secuencia `CAP-00001` se crea automáticamente.

## 🧪 Casos de Prueba

### ✅ Crear captura inmediata
1. Cliente en mora → Iniciar captura
2. Tipo: Inmediata
3. Adjuntar foto
4. Guardar
**Esperado**: CAP-00001 creado, estado=Capturado

### ✅ Validar evidencia obligatoria
1. Intentar guardar sin evidencia
**Esperado**: Error "La evidencia es obligatoria"

### ✅ Registrar pago
1. Captura activa → Registrar Pago
2. Completar voucher
**Esperado**: Estado pago = Pagado, notificación

### ✅ Liberar sin pago
1. Captura sin pago → Liberar
**Esperado**: Error "No se puede liberar sin pago"

### ✅ Retener vehículo
1. Supervisor → Retener
2. Motivo: "Cliente no responde"
**Esperado**: Estado = Retenido, va a historial

### ✅ Compromiso fecha futura
1. Tipo compromiso, fecha pasada
**Esperado**: Error "Fecha debe ser futura"

## 🔍 Búsquedas y Filtros

### Vista Mora
- Estado Crítico
- Más de 14/30 días
- Tipo cartera (Qorilazo/Los Andes)
- GPS Activo/Sin GPS
- Sin captura / Ya capturado
- Mi cartera (filtro por asesor)

### Vista Capturas
- Por estado (Capturado/Liberado/Retenido)
- Por estado pago
- Estado crítico
- Mis capturas
- Por fecha
- Agrupar por estado, tipo, capturador, fecha

## 📈 Métricas y Reportes

El módulo permite obtener:
- Total capturas por estado
- Capturas por capturador
- Días promedio de mora
- Monto total de intervenciones
- Tasa de liberación vs retención
- Tiempo promedio de resolución

## 🔗 Dependencias

- `base`: Core Odoo
- `web`: Interface web
- `fleet`: Gestión de vehículos
- `adt_comercial`: Cuentas y cuotas (requerido)

## 🚀 Resultado Final

El módulo está 100% funcional y cumple con todos los requerimientos:

✅ Identificación automática de clientes en mora  
✅ Registro de capturas con evidencia  
✅ Gestión de pagos  
✅ Liberación y retención controlada  
✅ Historial completo  
✅ Validaciones robustas  
✅ Roles y permisos  
✅ Trazabilidad total  
✅ Interfaz intuitiva  
✅ Preparado para producción  

## 📞 Soporte

Para cualquier consulta o mejora, contactar al equipo de desarrollo ADT.

---
**Versión**: 1.0  
**Fecha**: Febrero 2026  
**Estado**: ✅ Producción Ready
