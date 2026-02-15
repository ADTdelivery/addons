# MÓDULO 3: CLIENTE Y CRÉDITO

## Objetivo
Gestionar la información completa del propietario del vehículo y controlar su situación financiera cuando tiene crédito activo.

## 3.1 Datos del Propietario

### Información Personal
- Nombres completos
- Tipo de documento
- Número de documento (DNI, RUC, etc.)
- Fecha de nacimiento
- Dirección completa
- Teléfono principal
- Teléfono secundario
- Correo electrónico
- Contacto de emergencia

### Características del Módulo
- ✅ Registro completo del cliente
- ✅ Asociación con múltiples vehículos
- ✅ Historial financiero acumulado
- ✅ Clasificación de cliente (frecuente, nuevo, VIP)

## 3.2 Control de Crédito

### Información Financiera
Cuando el vehículo tiene financiamiento:

- **Empresa financiera**: Entidad que otorgó el crédito
- **Número de contrato**: Identificador único del crédito
- **Estado de pagos**:
  - Al día
  - Atrasado
  - Cancelado
  - En mora
- **Monto del crédito**
- **Fecha de inicio**
- **Fecha de vencimiento**
- **Cuotas pendientes**

## Reglas de Negocio

### Validaciones Críticas
1. ✅ Si estado = "Atrasado" → alerta roja visible
2. ✅ Si contrato "Cancelado" → bloquear nuevo crédito
3. ✅ Permitir reporte agrupado por financiera
4. ✅ Validar antes de autorizar trabajos costosos

## Alertas del Sistema

### Alertas Financieras
- 🔴 Cliente con crédito atrasado (bloqueo preventivo)
- 🟡 Cliente próximo a mora
- 🟢 Cliente al día con buen historial
- ⚠️ Cliente sin historial crediticio

### Alertas Comerciales
- 💎 Cliente VIP o frecuente
- 🆕 Cliente nuevo (primera visita)
- ⏰ Cliente inactivo (tiempo sin servicio)

## Funcionalidades Especiales

### Historial del Cliente
- Total gastado acumulado
- Frecuencia de visitas
- Vehículos asociados
- Promedio ticket
- Última fecha de visita
- Servicios más solicitados

### Control de Riesgo
- Evaluación de crédito
- Historial de pagos
- Reporte por entidad financiera
- Bloqueo automático si aplica

## Reportes Relacionados
- Clientes por estado crediticio
- Clientes por empresa financiera
- Ranking de clientes frecuentes
- Clientes inactivos
- Análisis de cartera por cliente
- Clientes con mayor gasto acumulado

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Registrar Nuevo Cliente
**Objetivo**: Verificar registro completo de cliente

**Pre-condiciones**:
- Usuario con permisos

**Pasos**:
1. Acceder a "Clientes"
2. Clic en "Crear"
3. Llenar información personal:
   - Nombres: Juan Pérez
   - DNI: 12345678
   - Teléfono: 987654321
   - Correo: juan@email.com
   - Dirección: Av. Principal 123
4. Guardar

**Resultado Esperado**:
- ✅ Cliente se registra exitosamente
- ✅ DNI es único (no duplicado)
- ✅ Clasificación automática: "Nuevo"
- ✅ Historial vacío creado

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Validación - DNI Duplicado
**Objetivo**: Verificar que no se permiten DNIs duplicados

**Pre-condiciones**:
- Cliente existente con DNI: 87654321

**Pasos**:
1. Crear nuevo cliente
2. Ingresar DNI: 87654321 (ya existe)
3. Intentar guardar

**Resultado Esperado**:
- 🔴 Sistema muestra error: "Ya existe un cliente con este DNI"
- 🔴 No permite guardar
- ⚠️ Opción de ver cliente existente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Registrar Crédito Financiero
**Objetivo**: Verificar registro de crédito para vehículo

**Pre-condiciones**:
- Cliente registrado
- Vehículo asociado al cliente

**Pasos**:
1. Abrir ficha de cliente
2. Agregar crédito financiero
3. Llenar datos:
   - Empresa: Banco XYZ
   - Número contrato: CRED-001
   - Monto: S/. 10,000
   - Estado: Al día
   - Fecha inicio: 01/01/2026
4. Guardar

**Resultado Esperado**:
- ✅ Crédito se registra correctamente
- ✅ Se asocia al vehículo
- 🟢 Indicador "Al día" visible
- ✅ Datos financieros completos

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Alerta - Cliente con Crédito Atrasado
**Objetivo**: Verificar alerta cuando cliente tiene atraso

**Pre-condiciones**:
- Cliente con crédito en estado "Atrasado"

**Pasos**:
1. Abrir ficha de cliente
2. Observar alertas
3. Intentar crear nueva orden de mantenimiento

**Resultado Esperado**:
- 🔴 Alerta roja visible: "Cliente con crédito atrasado"
- 🔴 Muestra entidad financiera y días de atraso
- ⚠️ Al crear orden muestra advertencia
- ✅ Permite continuar pero registra advertencia

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Cliente Próximo a Mora
**Objetivo**: Verificar alerta preventiva de mora

**Pre-condiciones**:
- Cliente con crédito "Al día"
- Próxima cuota vence en 3 días

**Pasos**:
1. Abrir ficha de cliente
2. Observar panel de alertas

**Resultado Esperado**:
- 🟡 Alerta amarilla: "Cliente próximo a mora"
- 🟡 Muestra días restantes
- ⚠️ Sugiere notificar al cliente
- ✅ Link a información del crédito

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Cliente VIP - Clasificación Automática
**Objetivo**: Verificar clasificación automática a VIP

**Pre-condiciones**:
- Cliente con más de 10 visitas
- Gasto acumulado > S/. 5,000

**Pasos**:
1. Abrir ficha de cliente
2. Verificar clasificación
3. Observar beneficios

**Resultado Esperado**:
- 💎 Clasificación: "VIP"
- 💎 Indicador visual destacado
- ✅ Muestra beneficios disponibles
- ✅ Descuentos automáticos aplicables

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Historial Financiero del Cliente
**Objetivo**: Verificar visualización de historial financiero

**Pre-condiciones**:
- Cliente con al menos 5 órdenes completadas

**Pasos**:
1. Abrir cliente
2. Acceder a "Historial Financiero"
3. Revisar datos

**Resultado Esperado**:
- ✅ Total gastado acumulado correcto
- ✅ Promedio de ticket calculado
- ✅ Frecuencia de visitas (mensual, trimestral)
- ✅ Última fecha de visita
- ✅ Gráfico de gastos en el tiempo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Cliente Inactivo - Alerta
**Objetivo**: Verificar alerta de cliente inactivo

**Pre-condiciones**:
- Cliente sin visitas hace más de 6 meses

**Pasos**:
1. Ejecutar proceso de análisis de clientes
2. Abrir cliente inactivo
3. Observar alertas

**Resultado Esperado**:
- ⏰ Alerta: "Cliente inactivo (X meses sin servicio)"
- ⏰ Sugiere campaña de reactivación
- ✅ Opción de enviar recordatorio
- ✅ Muestra última fecha de visita

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Múltiples Vehículos por Cliente
**Objetivo**: Verificar asociación de múltiples vehículos

**Pre-condiciones**:
- Cliente registrado

**Pasos**:
1. Abrir cliente
2. Asociar 3 vehículos diferentes
3. Guardar
4. Verificar asociaciones

**Resultado Esperado**:
- ✅ Los 3 vehículos se asocian correctamente
- ✅ Lista de vehículos visible en ficha
- ✅ Estadísticas por vehículo
- ✅ Total gastado por cada vehículo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Bloqueo por Crédito Cancelado
**Objetivo**: Verificar restricción para nuevo crédito

**Pre-condiciones**:
- Cliente con crédito en estado "Cancelado" por mora

**Pasos**:
1. Abrir cliente
2. Intentar registrar nuevo crédito
3. Observar respuesta del sistema

**Resultado Esperado**:
- 🔴 Sistema muestra advertencia: "Cliente con crédito cancelado previo"
- 🔴 Requiere autorización de supervisor
- ⚠️ Muestra historial de créditos cancelados
- ✅ No permite guardar sin autorización

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 11: Reporte por Entidad Financiera
**Objetivo**: Verificar reporte agrupado por financiera

**Pre-condiciones**:
- Múltiples clientes con créditos de diferentes entidades

**Pasos**:
1. Acceder a "Reportes"
2. Seleccionar "Créditos por Entidad Financiera"
3. Generar reporte

**Resultado Esperado**:
- ✅ Lista agrupada por entidad
- ✅ Cantidad de créditos por entidad
- ✅ Monto total por entidad
- ✅ Estado de créditos (al día, atrasados)
- ✅ Gráfico comparativo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 12: Servicios Más Solicitados por Cliente
**Objetivo**: Verificar análisis de preferencias

**Pre-condiciones**:
- Cliente con historial variado

**Pasos**:
1. Abrir cliente
2. Acceder a "Servicios Solicitados"
3. Ver estadísticas

**Resultado Esperado**:
- ✅ Lista ordenada por frecuencia
- ✅ Tipos de servicio más solicitados
- ✅ Gasto promedio por tipo
- ✅ Sugerencias personalizadas

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Registrar Nuevo Cliente | Funcional | Alta |
| 2 | DNI Duplicado | Validación | Alta |
| 3 | Registrar Crédito | Funcional | Alta |
| 4 | Alerta Crédito Atrasado | Alerta | Alta |
| 5 | Cliente Próximo a Mora | Alerta | Media |
| 6 | Clasificación VIP | Lógica | Media |
| 7 | Historial Financiero | Análisis | Media |
| 8 | Cliente Inactivo | Alerta | Baja |
| 9 | Múltiples Vehículos | Funcional | Media |
| 10 | Bloqueo Crédito Cancelado | Validación | Alta |
| 11 | Reporte por Financiera | Reporte | Media |
| 12 | Servicios Más Solicitados | Análisis | Baja |

**Total**: 12 casos de prueba

