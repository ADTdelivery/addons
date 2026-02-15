# MÓDULO 9: MECÁNICO RESPONSABLE

## Objetivo
Gestionar la información de los mecánicos, su especialización, desempeño y asignación a las órdenes de trabajo.

## Información del Mecánico

### Datos Personales
- **Nombre completo**: Nombres y apellidos
- **DNI**: Documento de identidad
- **Fecha de nacimiento**: Para cálculo de edad
- **Foto**: Fotografía del mecánico
- **Dirección**: Domicilio
- **Teléfono**: Contacto principal
- **Correo electrónico**: Para notificaciones
- **Fecha de ingreso**: Cuándo comenzó a trabajar
- **Estado**: Activo / Inactivo / Licencia / Vacaciones

### Información Profesional
- **Especialidad**: Área de expertise
  - Mecánica General
  - Motor
  - Sistema Eléctrico
  - Frenos y Suspensión
  - Transmisión
  - Carrocería
  - Pintura
  - Diagnóstico Electrónico
- **Nivel de experiencia**:
  - Aprendiz
  - Junior
  - Senior
  - Experto
  - Master
- **Certificaciones**: Títulos y certificados
- **Años de experiencia**: Total acumulado
- **Especialización en marcas**: Marcas que domina

### Firma Digital
- ✅ Firma digitalizada del mecánico
- ✅ Utilizada en órdenes de trabajo
- ✅ Validación de trabajos completados
- ✅ Respaldo legal

## Reglas de Negocio

### Validaciones Críticas

#### 1. Asignación de Trabajos
- ✅ Solo mecánicos ACTIVOS pueden asignarse
- ✅ Si especialidad no coincide con trabajo → advertencia
- ✅ Validar disponibilidad (no sobrecarga)
- ✅ Respetar nivel según complejidad

#### 2. Registro de Comisión
- ✅ Calcular comisión automática si aplica
- ✅ Base según tipo de trabajo
- ✅ Bonificación por eficiencia
- ✅ Descuento por retrabajo

#### 3. Control de Carga de Trabajo
- ✅ Máximo de trabajos simultáneos
- ✅ Alertar si está sobrecargado
- ✅ Balancear carga entre mecánicos
- ✅ Priorizar según urgencia

## Especialidades Principales

### Detalle de Especializaciones

#### Mecánica General
- Mantenimientos preventivos
- Revisiones generales
- Ajustes básicos
- **Nivel mínimo**: Junior

#### Especialista en Motor
- Reparación de motor
- Rectificación
- Sincronización
- Diagnóstico de fallas
- **Nivel mínimo**: Senior

#### Electricista
- Sistema eléctrico completo
- Diagnóstico electrónico
- Programación de ECU
- Instalación de accesorios
- **Nivel mínimo**: Senior

#### Especialista en Frenos
- Sistema de frenos completo
- ABS (si aplica)
- Suspensión
- Dirección
- **Nivel mínimo**: Junior

#### Especialista en Transmisión
- Embrague
- Caja de cambios
- Cadena y piñones
- Diferencial (si aplica)
- **Nivel mínimo**: Senior

## Evaluación de Desempeño

### Métricas de Evaluación

#### 1. Eficiencia
- Promedio de eficiencia en trabajos
- Meta: > 95%
- Cálculo mensual

#### 2. Calidad
- Tasa de retrabajo
- Meta: < 5%
- Impacta comisiones

#### 3. Productividad
- Trabajos completados
- Horas efectivas trabajadas
- Comparación con promedio

#### 4. Satisfacción del Cliente
- Calificación promedio
- Comentarios positivos
- Recomendaciones

#### 5. Versatilidad
- Cantidad de tipos de trabajo
- Diversidad de marcas atendidas
- Capacidad de aprendizaje

## Funcionalidades Especiales

### Sistema de Comisiones
```
Comisión Base = % del valor de mano de obra
Bonificación Eficiencia = Si eficiencia > 100%
Bonificación Calidad = Si sin retrabajo
Penalización = Si hay retrabajo
```

### Capacitación y Desarrollo
- Registro de cursos tomados
- Certificaciones vigentes
- Fechas de vencimiento
- Plan de capacitación
- Objetivos de desarrollo

### Disponibilidad
- Horario de trabajo
- Días laborales
- Turnos especiales
- Días no disponibles
- Permisos y licencias

## Alertas del Sistema

### Alertas de Asignación
- ⚠️ Especialidad no coincide con trabajo
- 🔴 Mecánico no está activo
- 🟡 Mecánico sobrecargado
- 📊 Bajo nivel para complejidad del trabajo

### Alertas de Desempeño
- 📉 Eficiencia por debajo del promedio
- 🔄 Alta tasa de retrabajo
- ⏰ Trabajos retrasados
- 💬 Calificación baja del cliente

### Alertas Administrativas
- 📜 Certificación próxima a vencer
- 📚 Capacitación pendiente
- 💼 Evaluación trimestral pendiente
- 🎂 Cumpleaños / Aniversario laboral

## Historial del Mecánico

### Información Histórica
- Total de órdenes completadas
- Total de horas trabajadas
- Especialidades desarrolladas
- Evolución de eficiencia
- Historial de comisiones
- Incidentes registrados
- Reconocimientos obtenidos

## Validaciones Adicionales

### Controles de Calidad
1. ✅ DNI debe ser único
2. ✅ Al menos una especialidad definida
3. ✅ Firma digital obligatoria
4. ✅ Nivel acorde a experiencia
5. ✅ Certificaciones vigentes para trabajos críticos

## Vinculación con Otros Módulos

### Integración con:
- **Órdenes**: Asignación de trabajos
- **Mano de Obra**: Cálculo de eficiencia
- **Comisiones**: Sistema de pago
- **Recursos Humanos**: Datos laborales
- **Capacitación**: Desarrollo profesional
- **Control de Calidad**: Evaluación

## Reportes Relacionados
- Ranking de mecánicos por eficiencia
- Productividad individual
- Comisiones ganadas
- Análisis de especialización
- Trabajos por mecánico
- Tasa de retrabajo
- Satisfacción del cliente por mecánico
- Carga de trabajo actual
- Disponibilidad semanal
- Evolución de desempeño
- Certificaciones vigentes
- Plan de capacitación

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Registrar Nuevo Mecánico
**Objetivo**: Verificar registro completo de mecánico

**Pre-condiciones**:
- Usuario con permisos de administración

**Pasos**:
1. Acceder a "Mecánicos"
2. Crear nuevo:
   - Nombre: Carlos Rodríguez
   - DNI: 45678912
   - Especialidad: Motor
   - Nivel: Senior
   - Años experiencia: 8
3. Cargar firma digital
4. Guardar

**Resultado Esperado**:
- ✅ Mecánico registrado correctamente
- ✅ Estado: Activo
- ✅ Firma digital guardada
- ✅ DNI único validado

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Asignación Según Especialidad
**Objetivo**: Verificar advertencia cuando especialidad no coincide

**Pre-condiciones**:
- Mecánico especialidad: Electricista
- Trabajo: Reparación de motor

**Pasos**:
1. Intentar asignar mecánico electricista a trabajo de motor
2. Observar advertencia

**Resultado Esperado**:
- ⚠️ Advertencia: "Especialidad del mecánico no coincide"
- ⚠️ Permite continuar pero registra
- ✅ Sugiere mecánico con especialidad correcta

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Control de Carga de Trabajo
**Objetivo**: Verificar alerta de sobrecarga

**Pre-condiciones**:
- Mecánico con 5 trabajos activos (máximo configurado: 4)

**Pasos**:
1. Intentar asignar 6to trabajo
2. Observar alerta

**Resultado Esperado**:
- ⚠️ Alerta: "Mecánico sobrecargado (5/4 trabajos)"
- ⚠️ Sugiere balancear carga
- ✅ Permite continuar con autorización
- ✅ Muestra carga de otros mecánicos

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Cálculo de Comisión con Bonificaciones
**Objetivo**: Verificar cálculo completo de comisión

**Pre-condiciones**:
- Trabajo completado
- Eficiencia: 110%
- Sin retrabajo

**Pasos**:
1. Completar trabajo
2. Sistema calcula comisión
3. Ver desglose

**Resultado Esperado**:
- ✅ Comisión base: 10% mano de obra
- ✅ Bonificación eficiencia: +5%
- ✅ Bonificación calidad: +5%
- ✅ Total comisión calculada correctamente

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Penalización por Retrabajo
**Objetivo**: Verificar descuento en comisión

**Pre-condiciones**:
- Trabajo con retrabajo detectado

**Pasos**:
1. Completar trabajo con retrabajo
2. Ver cálculo de comisión

**Resultado Esperado**:
- ✅ Comisión base calculada
- 🔴 Penalización aplicada: -10%
- ⚠️ Alerta al mecánico
- ✅ Registrado en evaluación

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Alerta - Certificación Próxima a Vencer
**Objetivo**: Verificar alertas de capacitación

**Pre-condiciones**:
- Certificación "Diagnóstico Electrónico" vence en 15 días

**Pasos**:
1. Abrir ficha de mecánico
2. Ver panel de alertas

**Resultado Esperado**:
- 📜 Alerta: "Certificación próxima a vencer"
- 📜 Muestra días restantes
- ⚠️ Sugiere renovación
- ✅ Link a plan de capacitación

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Evaluación de Desempeño Trimestral
**Objetivo**: Verificar cálculo de métricas

**Pre-condiciones**:
- Mecánico con trabajos en último trimestre

**Pasos**:
1. Acceder a evaluación
2. Ver métricas calculadas

**Resultado Esperado**:
- ✅ Eficiencia promedio: 98%
- ✅ Tasa de retrabajo: 3%
- ✅ Calificación cliente: 4.5/5
- ✅ Trabajos completados: 45
- ✅ Evaluación global: Bueno

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Validación - Solo Mecánicos Activos
**Objetivo**: Verificar filtro de asignación

**Pre-condiciones**:
- Mecánico en estado "Inactivo" o "Licencia"

**Pasos**:
1. Intentar asignar trabajo a mecánico inactivo
2. Observar respuesta

**Resultado Esperado**:
- 🔴 Error: "Mecánico no está activo"
- 🔴 No permite asignación
- ✅ Solo muestra mecánicos activos en lista

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Historial Completo del Mecánico
**Objetivo**: Verificar registro histórico

**Pre-condiciones**:
- Mecánico con 2 años de trayectoria

**Pasos**:
1. Abrir mecánico
2. Acceder a "Historial"
3. Ver información

**Resultado Esperado**:
- ✅ Total órdenes completadas: 450
- ✅ Total horas trabajadas: 900 hrs
- ✅ Evolución de eficiencia (gráfico)
- ✅ Historial de comisiones
- ✅ Reconocimientos obtenidos

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Reporte - Ranking de Mecánicos
**Objetivo**: Verificar comparación de desempeño

**Pre-condiciones**:
- 5 mecánicos activos con trabajos

**Pasos**:
1. Acceder a reportes
2. "Ranking de Mecánicos"
3. Período: Último mes
4. Generar

**Resultado Esperado**:
- ✅ Lista ordenada por desempeño global
- ✅ Métricas clave por mecánico
- ✅ Identificación del mejor mecánico del mes
- ✅ Áreas de mejora por persona
- ✅ Gráfico comparativo

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Registrar Mecánico | Funcional | Alta |
| 2 | Asignación por Especialidad | Validación | Media |
| 3 | Control Carga Trabajo | Alerta | Media |
| 4 | Cálculo Comisión | Cálculo | Alta |
| 5 | Penalización Retrabajo | Lógica | Alta |
| 6 | Alerta Certificación | Alerta | Media |
| 7 | Evaluación Desempeño | Análisis | Media |
| 8 | Solo Mecánicos Activos | Validación | Alta |
| 9 | Historial Mecánico | Funcional | Media |
| 10 | Ranking Mecánicos | Reporte | Media |

**Total**: 10 casos de prueba

