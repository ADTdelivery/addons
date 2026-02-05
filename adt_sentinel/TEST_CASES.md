# CASOS DE PRUEBA - ADT SENTINEL

## 📋 Suite de Validación Completa

Este documento contiene todos los casos de prueba necesarios para validar el correcto funcionamiento del módulo Sentinel.

---

## ✅ CASOS DE PRUEBA FUNCIONALES

### TC001: Búsqueda de DNI No Existente

**Precondición:** DNI 11111111 nunca ha sido consultado

**Pasos:**
1. Ir a: Sentinel > Consultar DNI
2. Ingresar: 11111111
3. Clic en "Buscar"

**Resultado Esperado:**
- ✅ Mensaje: "No se encontró reporte vigente"
- ✅ Formulario de carga visible
- ✅ Advertencia de costo (S/ 10) visible
- ✅ Campo "Subir imagen" habilitado

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TC002: Subida de Primera Imagen

**Precondición:** DNI 22222222 no tiene reporte vigente

**Pasos:**
1. Buscar DNI: 22222222
2. Sistema muestra formulario de carga
3. Adjuntar imagen: sentinel_report_001.jpg
4. Agregar observación: "Primera consulta del cliente"
5. Clic en "Subir y Guardar"
6. Confirmar advertencia de costo

**Resultado Esperado:**
- ✅ Reporte creado exitosamente
- ✅ State = 'vigente'
- ✅ query_date = HOY
- ✅ query_user_id = Usuario actual
- ✅ query_month = Mes actual
- ✅ query_year = Año actual
- ✅ Imagen guardada correctamente
- ✅ Se abre vista del reporte

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TC003: Reutilización de Reporte Vigente (Mismo Usuario)

**Precondición:** DNI 22222222 tiene reporte vigente del mes actual

**Pasos:**
1. Buscar DNI: 22222222
2. Esperar resultado

**Resultado Esperado:**
- ✅ Mensaje: "✅ Reporte Encontrado"
- ✅ Muestra fecha de consulta original
- ✅ Muestra usuario que consultó
- ✅ Estado: VIGENTE
- ✅ Vista previa de imagen visible
- ✅ Botón "Ver Reporte Completo" disponible
- ✅ NO se permite subir nueva imagen
- ✅ NO se genera costo adicional

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TC004: Reutilización de Reporte Vigente (Otro Usuario)

**Precondición:** 
- Usuario A creó reporte para DNI 33333333 hoy
- Usuario B inicia sesión

**Pasos:**
1. Usuario B busca DNI: 33333333
2. Esperar resultado

**Resultado Esperado:**
- ✅ Mensaje: "✅ Reporte Encontrado"
- ✅ Muestra: "Consultado por: Usuario A"
- ✅ Usuario B puede ver la imagen
- ✅ Usuario B NO puede subir nueva imagen
- ✅ NO se genera costo para Usuario B

**Validación de Negocio:**
- ✅ Ahorro confirmado: S/ 10

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TC005: Múltiples Usuarios Mismo DNI Mismo Día

**Precondición:** DNI 44444444 no consultado

**Pasos:**
1. **09:00** - Usuario A busca 44444444 → No existe → Sube imagen
2. **10:30** - Usuario B busca 44444444 → Debe encontrar reporte de A
3. **14:00** - Usuario C busca 44444444 → Debe encontrar reporte de A
4. **16:45** - Usuario D busca 44444444 → Debe encontrar reporte de A

**Resultado Esperado:**
- ✅ Solo Usuario A pudo subir imagen
- ✅ Usuarios B, C, D ven el mismo reporte
- ✅ Total de consultas a Sentinel: 1
- ✅ Costo total: S/ 10
- ✅ Ahorro: S/ 30 (3 consultas evitadas)

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TC006: Cambio de Mes (Reporte Vencido)

**Precondición:** 
- 28/01/2026 - Reporte creado para DNI 55555555
- Sistema avanza a 01/02/2026

**Pasos:**
1. Verificar estado del reporte anterior
2. Buscar DNI: 55555555
3. Esperar resultado

**Resultado Esperado:**
- ✅ Reporte de enero tiene state = 'vencido'
- ✅ is_current_month = False
- ✅ Búsqueda NO encuentra reporte vigente
- ✅ Sistema permite subir nueva imagen
- ✅ Mensaje: "No se encontró reporte vigente"

**Validación de Negocio:**
- ✅ Nueva consulta es necesaria (score cambió en febrero)

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TC007: Histórico de Consultas

**Precondición:** 
- DNI 66666666 tiene:
  - Enero 2026: 1 reporte
  - Febrero 2026: 1 reporte
  - Marzo 2026: 1 reporte

**Pasos:**
1. Buscar DNI: 66666666
2. Clic en "Ver Histórico"

**Resultado Esperado:**
- ✅ Se muestran 3 registros
- ✅ Reporte de marzo: state = 'vigente'
- ✅ Reportes de enero y febrero: state = 'vencido'
- ✅ Ordenados por fecha descendente
- ✅ Todos los registros visibles
- ✅ NO se puede eliminar ninguno

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 🔒 CASOS DE PRUEBA DE SEGURIDAD

### TS001: Validación de Formato DNI

**Pasos:**
1. Intentar buscar con DNI inválido:
   - "1234567" (7 dígitos)
   - "123456789" (9 dígitos)
   - "12345abc" (letras)
   - "12 345 678" (espacios)

**Resultado Esperado:**
- ✅ Error: "El número de documento debe tener exactamente 8 dígitos"
- ✅ No se ejecuta búsqueda
- ✅ No se permite continuar

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TS002: Constraint de Unicidad (DNI + Mes + Año)

**Pasos:**
1. Crear reporte para DNI 77777777 (febrero 2026)
2. Intentar crear otro reporte para DNI 77777777 (febrero 2026)

**Método de prueba:**
```python
# Acceso directo al modelo (bypass wizard)
self.env['adt.sentinel.report'].create({
    'document_number': '77777777',
    'report_image': image_data,
    'query_date': '2026-02-04'
})
```

**Resultado Esperado:**
- ✅ Segunda creación falla
- ✅ Error: "Ya existe un reporte vigente para este DNI"
- ✅ IntegrityError capturado
- ✅ Base de datos mantiene integridad

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TS003: Validación de Imagen Requerida

**Pasos:**
1. Buscar DNI sin reporte vigente
2. Intentar guardar SIN adjuntar imagen
3. Clic en "Subir y Guardar"

**Resultado Esperado:**
- ✅ Error: "Imagen requerida"
- ✅ Mensaje indica costo de S/ 10
- ✅ No se crea registro
- ✅ Formulario permanece abierto

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TS004: Protección Contra Modificación de Campos

**Pasos:**
1. Abrir reporte existente (ID: 1)
2. Intentar modificar:
   - document_number → '99999999'
   - query_date → '2026-01-01'
   - query_user_id → Otro usuario

**Resultado Esperado:**
- ✅ Error: "No se pueden modificar los datos del reporte"
- ✅ Lista campos protegidos
- ✅ Valores NO cambian
- ✅ Solo campo 'notes' es editable

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TS005: Prohibición de Eliminación

**Pasos:**
1. Seleccionar cualquier reporte
2. Intentar eliminar (Action > Delete)

**Resultado Esperado:**
- ✅ Error: "Los reportes Sentinel NO pueden eliminarse"
- ✅ Mensaje explica razones (auditoría)
- ✅ Registro permanece en BD
- ✅ Histórico intacto

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TS006: Race Condition (Consultas Concurrentes)

**Pasos:**
1. Usuario A busca DNI 88888888 → No existe
2. Usuario A prepara imagen (NO ha guardado aún)
3. Usuario B busca DNI 88888888 → No existe
4. Usuario B sube imagen y guarda (éxito)
5. Usuario A intenta guardar

**Resultado Esperado:**
- ✅ Usuario B crea reporte exitosamente
- ✅ Usuario A recibe error: "Reporte duplicado detectado"
- ✅ Mensaje indica que otro usuario ya consultó
- ✅ Solo existe 1 reporte en BD
- ✅ Costo total: S/ 10 (no S/ 20)

**Validación Técnica:**
- ✅ Doble verificación en `action_upload_report()` funciona

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 📊 CASOS DE PRUEBA DE RENDIMIENTO

### TP001: Búsqueda con 1,000 Registros

**Precondición:** Base de datos con 1,000 reportes

**Pasos:**
1. Buscar DNI específico
2. Medir tiempo de respuesta

**Resultado Esperado:**
- ✅ Tiempo < 1 segundo
- ✅ Índices funcionan correctamente
- ✅ Query usa índice (document_number, is_current_month)

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TP002: Carga de Imagen Grande

**Pasos:**
1. Subir imagen de 5 MB
2. Verificar almacenamiento
3. Verificar tiempo de carga

**Resultado Esperado:**
- ✅ Imagen se guarda en filestore (no en BD)
- ✅ Campo attachment=True funciona
- ✅ Tiempo de carga < 5 segundos
- ✅ Vista previa se carga correctamente

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 🧮 CASOS DE PRUEBA DE LÓGICA DE NEGOCIO

### TB001: Cálculo Automático de Vigencia

**Pasos:**
1. Crear reporte el 15/02/2026
2. Verificar campos computed

**Resultado Esperado:**
- ✅ query_month = 2
- ✅ query_year = 2026
- ✅ state = 'vigente'
- ✅ is_current_month = True

**Pasos 2:**
1. Simular cambio a 01/03/2026
2. Refrescar reporte

**Resultado Esperado:**
- ✅ state = 'vencido' (computed automáticamente)
- ✅ is_current_month = False
- ✅ query_month y query_year NO cambian (valores originales)

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TB002: name_get() Display

**Pasos:**
1. Crear reportes con diferentes estados
2. Ver lista en tree view

**Resultado Esperado:**
- ✅ Vigente: "✅ DNI 12345678 - Feb/2026"
- ✅ Vencido: "📅 DNI 12345678 - Ene/2026"
- ✅ Formato consistente
- ✅ Iconos visibles

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 🎨 CASOS DE PRUEBA DE UI/UX

### TU001: Wizard - Paso 1 (Búsqueda)

**Pasos:**
1. Abrir: Sentinel > Consultar DNI

**Resultado Esperado:**
- ✅ Título: "🔍 Consultar Reporte Sentinel"
- ✅ Campo DNI visible y enfocado
- ✅ Placeholder: "Ej: 12345678"
- ✅ Instrucciones claras
- ✅ Botón "Buscar" destacado
- ✅ Botón "Cancelar" disponible

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TU002: Wizard - Paso 2A (Reporte Encontrado)

**Pasos:**
1. Buscar DNI con reporte vigente

**Resultado Esperado:**
- ✅ Título: "✅ Reporte Encontrado"
- ✅ Panel verde con información
- ✅ Datos visibles: DNI, Fecha, Usuario, Estado
- ✅ Mensaje: "Este reporte es válido hasta fin de mes"
- ✅ Vista previa de imagen en tab
- ✅ Botones: "Ver Reporte Completo" y "Ver Histórico"

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TU003: Wizard - Paso 2B (Permitir Carga)

**Pasos:**
1. Buscar DNI sin reporte vigente

**Resultado Esperado:**
- ✅ Título: "📸 Subir Nuevo Reporte"
- ✅ Panel azul: "No se encontró reporte vigente"
- ✅ Panel amarillo: "Advertencia de costo S/ 10"
- ✅ Campo DNI readonly
- ✅ Campo imagen con widget binary
- ✅ Campo observaciones opcional
- ✅ Vista previa de imagen si se adjunta
- ✅ Botón: "Subir y Guardar (S/ 10.00)"
- ✅ Confirmación al hacer clic

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TU004: Vista de Reporte (Form)

**Pasos:**
1. Abrir reporte vigente

**Resultado Esperado:**
- ✅ Statusbar: Estado vigente en azul
- ✅ Título: DNI grande
- ✅ Subtítulo: "✅ Reporte Vigente" (verde)
- ✅ Button box: Botón "Ver Histórico"
- ✅ Grupos de información bien organizados
- ✅ Tab 1: Imagen a buen tamaño
- ✅ Tab 2: Observaciones editables
- ✅ Chatter visible

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 📈 CASOS DE PRUEBA DE REPORTES

### TR001: Filtros de Búsqueda

**Pasos:**
1. Ir a: Sentinel > Todos los Reportes
2. Probar filtros:
   - "Vigentes"
   - "Vencidos"
   - "Mes Actual"
   - "Mis Consultas"

**Resultado Esperado:**
- ✅ Cada filtro muestra resultados correctos
- ✅ Combinación de filtros funciona
- ✅ Búsqueda por DNI funciona
- ✅ Agrupar por: Estado, Usuario, Fecha

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TR002: Vista Tree (Lista)

**Pasos:**
1. Ver lista de reportes

**Resultado Esperado:**
- ✅ Vigentes en verde (decoration-success)
- ✅ Vencidos en gris (decoration-muted)
- ✅ Columnas: DNI, Fecha, Usuario, Año, Estado
- ✅ NO se puede crear desde tree
- ✅ NO se puede eliminar

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 🔄 CASOS DE PRUEBA DE INTEGRACIÓN

### TI001: Integración con res.users

**Pasos:**
1. Crear reporte con Usuario A
2. Desactivar Usuario A
3. Ver reporte

**Resultado Esperado:**
- ✅ Reporte mantiene referencia a Usuario A
- ✅ Nombre de usuario visible
- ✅ No hay errores

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

### TI002: Chatter y Seguidores

**Pasos:**
1. Abrir reporte
2. Agregar seguidor
3. Escribir mensaje en chatter

**Resultado Esperado:**
- ✅ Seguidores funcionan
- ✅ Mensajes se guardan
- ✅ Notificaciones se envían

**Estado:** ⬜ No probado | ✅ Pasó | ❌ Falló

---

## 📋 RESUMEN DE EJECUCIÓN

### Estadísticas

- **Total de casos:** 25
- **Funcionales:** 7
- **Seguridad:** 6
- **Rendimiento:** 2
- **Lógica de negocio:** 2
- **UI/UX:** 4
- **Reportes:** 2
- **Integración:** 2

### Criterios de Aceptación

Para considerar el módulo listo para producción:
- ✅ Todos los casos funcionales deben pasar
- ✅ Todos los casos de seguridad deben pasar
- ✅ Al menos 80% de casos UI/UX deben pasar
- ✅ Rendimiento aceptable (< 2 seg por operación)

---

## 👥 Roles de Testing

- **Tester Funcional:** Ejecuta TC001-TC007
- **Tester de Seguridad:** Ejecuta TS001-TS006
- **Tester de Performance:** Ejecuta TP001-TP002
- **Tester de UI:** Ejecuta TU001-TU004
- **QA Lead:** Revisa y aprueba todos

---

**Fecha de creación:** 04/02/2026  
**Versión del módulo:** 1.0.0  
**Última actualización:** 04/02/2026
