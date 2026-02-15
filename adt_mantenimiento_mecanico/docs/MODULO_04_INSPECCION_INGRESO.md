# MÓDULO 4: INSPECCIÓN DE INGRESO

## Objetivo
Documentar el estado completo del vehículo al momento de ingreso para evitar reclamos posteriores y tener respaldo legal.

## Importancia Crítica
⚠️ **Este módulo es CRÍTICO para evitar reclamos legales**

La inspección documentada protege tanto al taller como al cliente, estableciendo el estado inicial del vehículo antes de cualquier intervención.

## Evaluación por Sistemas

### Sistemas a Inspeccionar

#### 1. Motor
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 2. Transmisión
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 3. Frenos
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 4. Suspensión
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 5. Sistema Eléctrico
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 6. Llantas
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 7. Carrocería
- Estado: Bueno / Regular / Malo
- Observaciones específicas
- Evidencia fotográfica (opcional)

#### 8. Accesorios
- Estado: Bueno / Regular / Malo
- Observaciones específicos
- Evidencia fotográfica (opcional)

## Información por Sistema

### Para cada sistema se registra:
- ✅ Estado general (Bueno / Regular / Malo)
- ✅ Observaciones detalladas
- ✅ Evidencia fotográfica (opcional pero recomendada)
- ✅ Fecha y hora de inspección
- ✅ Inspector responsable

## Reglas de Negocio

### Validaciones Críticas
1. ✅ NO se puede avanzar a diagnóstico sin inspección completa
2. ✅ Si se marca "Malo" → sugerir acción correctiva automática
3. ✅ Guardar registro como respaldo legal
4. ✅ Requiere firma digital del cliente confirmando estado inicial

## Funcionalidades Especiales

### Sugerencias Automáticas
Si el sistema detecta estado "Malo":
- Generar trabajo correctivo sugerido
- Alertar al asesor
- Incluir en cotización automática

### Evidencias Fotográficas
- Permitir múltiples fotos por sistema
- Almacenar metadata (fecha, hora, usuario)
- Disponible para revisión posterior
- Adjuntable a reporte final

### Comparación Post-Servicio
- Comparar estado inicial vs final
- Demostrar mejoras realizadas
- Justificar trabajos ejecutados

## Checklist de Inspección

### Elementos Adicionales a Verificar
- [ ] Nivel de combustible
- [ ] Objetos personales en el vehículo
- [ ] Documentos en la unidad
- [ ] Accesorios removibles
- [ ] Rayones o daños preexistentes
- [ ] Condición de tapizado
- [ ] Estado de instrumentación

## Alertas del Sistema
- 🔴 Inspección incompleta
- 🟡 Sistema marcado como "Malo"
- ⚠️ Falta evidencia fotográfica en daño severo
- 📸 Recordatorio: tomar fotos de daños

## Reportes Relacionados
- Inspecciones por inspector
- Sistemas con mayor incidencia de fallas
- Análisis de estado por modelo de vehículo
- Comparativo antes/después
- Respaldo legal por orden

---

## 🧪 CASOS DE PRUEBA

### Caso de Prueba 1: Inspección Completa
**Objetivo**: Verificar registro completo de inspección

**Pre-condiciones**:
- Orden de mantenimiento creada
- Usuario con permisos de inspector

**Pasos**:
1. Abrir orden
2. Acceder a "Inspección de Ingreso"
3. Evaluar 8 sistemas:
   - Motor: Bueno
   - Transmisión: Bueno
   - Frenos: Regular
   - Suspensión: Bueno
   - Sistema Eléctrico: Bueno
   - Llantas: Malo
   - Carrocería: Regular
   - Accesorios: Bueno
4. Agregar observaciones en cada sistema
5. Guardar inspección

**Resultado Esperado**:
- ✅ Todos los sistemas registrados
- ✅ Inspector asignado automáticamente
- ✅ Fecha y hora registradas
- ✅ Permite avanzar a diagnóstico

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 2: Bloqueo - Inspección Incompleta
**Objetivo**: Verificar que no se puede avanzar sin inspección completa

**Pre-condiciones**:
- Orden creada
- Inspección parcial (solo 3 de 8 sistemas)

**Pasos**:
1. Abrir orden con inspección incompleta
2. Intentar avanzar a "Diagnóstico"
3. Observar respuesta

**Resultado Esperado**:
- 🔴 Sistema bloquea avance
- 🔴 Error: "Inspección incompleta. Complete los 8 sistemas"
- 🔴 Lista sistemas pendientes
- ⚠️ No permite continuar

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 3: Sugerencia Automática - Sistema Malo
**Objetivo**: Verificar sugerencia cuando sistema está "Malo"

**Pre-condiciones**:
- Inspección en proceso

**Pasos**:
1. Marcar sistema "Frenos" como "Malo"
2. Agregar observación: "Pastillas gastadas"
3. Guardar

**Resultado Esperado**:
- ✅ Sistema sugiere automáticamente: "Cambio de pastillas de freno"
- ✅ Alerta al asesor
- ✅ Se agrega a lista de trabajos sugeridos
- ✅ Se incluye en cotización automática

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 4: Evidencia Fotográfica
**Objetivo**: Verificar adjuntar fotos a inspección

**Pre-condiciones**:
- Inspección en proceso
- Daño visible en carrocería

**Pasos**:
1. Marcar "Carrocería" como "Malo"
2. Agregar observación: "Rayón en costado izquierdo"
3. Adjuntar 2 fotos del daño
4. Guardar

**Resultado Esperado**:
- ✅ Fotos se adjuntan correctamente
- ✅ Metadata registrada (fecha, hora, usuario)
- ✅ Fotos visibles en inspección
- ✅ Disponibles para reporte final

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 5: Alerta - Falta Foto en Daño Severo
**Objetivo**: Verificar recordatorio de foto para daño severo

**Pre-condiciones**:
- Inspección en proceso

**Pasos**:
1. Marcar sistema como "Malo"
2. Agregar observación crítica
3. NO adjuntar foto
4. Intentar guardar

**Resultado Esperado**:
- ⚠️ Alerta: "Recomendado: Adjuntar evidencia fotográfica"
- ⚠️ Permite continuar pero con advertencia
- 📸 Recordatorio visible en la inspección

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 6: Firma Digital del Cliente
**Objetivo**: Verificar firma digital obligatoria

**Pre-condiciones**:
- Inspección completa

**Pasos**:
1. Completar inspección
2. Intentar finalizar
3. Solicitar firma del cliente
4. Cliente firma digitalmente

**Resultado Esperado**:
- ✅ Sistema solicita firma obligatoria
- ✅ No permite finalizar sin firma
- ✅ Firma se registra correctamente
- ✅ Fecha y hora de firma guardadas

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 7: Checklist Adicional
**Objetivo**: Verificar elementos adicionales de inspección

**Pre-condiciones**:
- Inspección de 8 sistemas completa

**Pasos**:
1. Acceder a checklist adicional
2. Marcar:
   - [x] Nivel de combustible: 1/2 tanque
   - [x] Objetos personales: Ninguno
   - [x] Documentos: SOAT en guantera
   - [x] Accesorios removibles: Casco
3. Guardar

**Resultado Esperado**:
- ✅ Checklist se guarda correctamente
- ✅ Respaldo legal completo
- ✅ Evita reclamos futuros

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 8: Comparación Pre/Post Servicio
**Objetivo**: Verificar comparación de estados

**Pre-condiciones**:
- Orden completada
- Inspección inicial: Frenos = Malo
- Trabajo realizado: Cambio de frenos

**Pasos**:
1. Acceder a "Comparación"
2. Ver estado inicial vs final
3. Generar reporte

**Resultado Esperado**:
- ✅ Muestra estado inicial: Malo
- ✅ Muestra estado final: Bueno
- ✅ Lista trabajos realizados
- ✅ Justifica cobro del servicio
- ✅ Reporte visual claro

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 9: Inspección por Inspector
**Objetivo**: Verificar asignación de inspector

**Pre-condiciones**:
- Usuario con rol "Inspector"

**Pasos**:
1. Loguearse como inspector
2. Crear inspección
3. Completar sistemas
4. Guardar

**Resultado Esperado**:
- ✅ Inspector se asigna automáticamente
- ✅ Queda registrado quién inspeccionó
- ✅ Permite generar reporte por inspector
- ✅ Trazabilidad completa

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 10: Reporte - Sistemas con Mayor Fallas
**Objetivo**: Verificar análisis estadístico

**Pre-condiciones**:
- Al menos 20 inspecciones en sistema

**Pasos**:
1. Acceder a "Reportes"
2. Seleccionar "Sistemas con Mayor Incidencia de Fallas"
3. Definir período: Último mes
4. Generar

**Resultado Esperado**:
- ✅ Gráfico de barras con sistemas
- ✅ Porcentaje de fallas por sistema
- ✅ Sistema más problemático identificado
- ✅ Útil para capacitación

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 11: Exportar Inspección a PDF
**Objetivo**: Verificar generación de documento

**Pre-condiciones**:
- Inspección completa con fotos

**Pasos**:
1. Abrir inspección completa
2. Clic en "Exportar a PDF"
3. Generar documento

**Resultado Esperado**:
- ✅ PDF generado correctamente
- ✅ Incluye todos los sistemas
- ✅ Incluye fotos adjuntas
- ✅ Incluye firma del cliente
- ✅ Formato profesional

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

### Caso de Prueba 12: Editar Inspección Después de Guardar
**Objetivo**: Verificar restricción de edición

**Pre-condiciones**:
- Inspección completa y guardada
- Orden ya en "Diagnóstico"

**Pasos**:
1. Abrir inspección completa
2. Intentar modificar un sistema
3. Intentar guardar cambios

**Resultado Esperado**:
- 🔴 Sistema no permite editar
- 🔴 Campos en modo solo lectura
- ⚠️ Mensaje: "Inspección finalizada no se puede modificar"
- ✅ Protege integridad del respaldo legal

**Resultado Obtenido**: _____________

**Estado**: [ ] Pasa [ ] Falla

---

## 📋 Resumen de Casos de Prueba

| # | Caso | Tipo | Prioridad |
|---|------|------|-----------|
| 1 | Inspección Completa | Funcional | Alta |
| 2 | Bloqueo Inspección Incompleta | Validación | Alta |
| 3 | Sugerencia Sistema Malo | Lógica | Alta |
| 4 | Evidencia Fotográfica | Funcional | Media |
| 5 | Alerta Falta Foto | Alerta | Media |
| 6 | Firma Digital Cliente | Validación | Alta |
| 7 | Checklist Adicional | Funcional | Media |
| 8 | Comparación Pre/Post | Análisis | Media |
| 9 | Asignación Inspector | Sistema | Media |
| 10 | Reporte Sistemas Fallados | Reporte | Baja |
| 11 | Exportar a PDF | Funcional | Media |
| 12 | Restricción Edición | Seguridad | Alta |

**Total**: 12 casos de prueba

