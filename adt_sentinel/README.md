# ADT Sentinel - Repositorio de Consultas Crediticias

## ⚠️ ACLARACIÓN CRÍTICA

**Este módulo NO es un sistema de evaluación crediticia.**

### ❌ Lo que NO hace:
- NO calcula scores crediticios
- NO aprueba ni rechaza créditos
- NO define líneas de crédito
- NO toma decisiones financieras
- NO interpreta reportes

### ✅ Lo que SÍ hace:
- Almacena imágenes de reportes Sentinel
- Controla vigencia mensual
- Evita consultas duplicadas
- Reduce costos operativos
- Mantiene histórico completo

---

## 🎯 Objetivo del Módulo

La empresa utiliza la plataforma **Sentinel** para consultar historial crediticio de clientes. Cada consulta cuesta **S/ 10.00**.

### Problema anterior:
- Varios asesores consultaban el mismo DNI el mismo día
- Se pagaba múltiples veces por la misma información
- El score crediticio solo cambia una vez al mes

### Solución:
Este módulo centraliza las consultas y permite **reutilizar reportes** dentro del mismo mes, reduciendo costos significativamente.

---

## 📊 Reglas de Negocio

### 1️⃣ Vigencia Mensual
- Cada reporte es válido **solo durante el mes** en que fue consultado
- Al cambiar de mes, los reportes anteriores pasan a estado **VENCIDO**
- Se permite una nueva consulta por mes

### 2️⃣ Una Consulta por DNI por Mes
- Solo se permite **1 reporte vigente** por DNI por mes
- Todos los usuarios comparten el mismo reporte
- Constraint a nivel de base de datos garantiza esta regla

### 3️⃣ Búsqueda Previa Obligatoria
Antes de permitir una nueva consulta:
1. El sistema busca por DNI
2. Si existe reporte vigente → Se reutiliza (sin costo adicional)
3. Si no existe → Se permite subir nueva imagen (costo S/ 10)

### 4️⃣ Histórico Permanente
- Los reportes **NO pueden eliminarse**
- Sirven como trazabilidad y auditoría
- Solo se puede editar el campo "Observaciones"

---

## 🚀 Uso del Módulo

### Flujo de Trabajo

```
┌─────────────────────────────────────────┐
│ 1. Usuario: Menú > Sentinel >         │
│    Consultar DNI                       │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 2. Ingresar DNI (8 dígitos)           │
│    Clic en "Buscar"                    │
└─────────────────────────────────────────┘
              ↓
         ¿Existe vigente?
              ↓
    ┌─────────┴─────────┐
    │                   │
   SÍ                  NO
    │                   │
    ↓                   ↓
┌─────────┐      ┌──────────────┐
│ Mostrar │      │ Permitir     │
│ reporte │      │ subir imagen │
│ existente│      │ (S/ 10)      │
└─────────┘      └──────────────┘
```

### Ejemplo Práctico

**Escenario:** 3 asesores necesitan consultar el DNI 12345678 el 04/02/2026

1. **Asesor A** (9:00 AM):
   - Busca DNI 12345678
   - No existe reporte vigente
   - Sube imagen del reporte Sentinel
   - **Costo: S/ 10**

2. **Asesor B** (10:30 AM):
   - Busca DNI 12345678
   - Sistema encuentra reporte de Asesor A
   - Ve la imagen sin necesidad de nueva consulta
   - **Costo: S/ 0**

3. **Asesor C** (14:00 PM):
   - Busca DNI 12345678
   - Sistema encuentra reporte de Asesor A
   - Ve la imagen sin necesidad de nueva consulta
   - **Costo: S/ 0**

**Ahorro: S/ 20** (2 consultas evitadas)

---

## 💰 Impacto Económico

### Antes del módulo:
- 10 asesores × 5 consultas/día = 50 consultas
- Si 30% son duplicadas = 15 consultas innecesarias/día
- 15 × S/ 10 = **S/ 150/día desperdiciados**
- **S/ 3,000/mes** en costos evitables

### Con el módulo:
- Consultas duplicadas eliminadas
- **Ahorro mensual: S/ 3,000**
- **ROI inmediato**

---

## 📁 Estructura del Módulo

```
adt_sentinel/
├── __init__.py
├── __manifest__.py
├── README.md
│
├── models/
│   ├── __init__.py
│   └── sentinel.py              # Modelo principal
│
├── wizard/
│   ├── __init__.py
│   ├── sentinel_query_wizard.py # Lógica de búsqueda/carga
│   └── sentinel_query_wizard_views.xml
│
├── views/
│   ├── sentinel_report_views.xml # Vistas del modelo
│   ├── sentinel_menu.xml         # Menús
│   └── sentinel_views.xml        # (obsoleto)
│
├── security/
│   └── ir.model.access.csv      # Permisos
│
└── static/
    └── description/
        └── icon.png
```

---

## 🔐 Seguridad y Permisos

### Usuarios normales (group_user):
- ✅ Consultar DNI
- ✅ Ver reportes vigentes
- ✅ Subir nuevas imágenes
- ✅ Editar observaciones
- ❌ Eliminar registros

### Administradores (group_system):
- ✅ Todo lo anterior
- ✅ Acceso al histórico completo
- ❌ Eliminar registros (prohibido por diseño)

---

## 🧪 Casos de Validación

### ✅ Caso 1: Consultas múltiples el mismo día
**Entrada:** 3 asesores buscan DNI 87654321 el mismo día  
**Resultado esperado:** Solo el primero puede subir imagen, los otros 2 ven el reporte existente  
**✓ Validado**

### ✅ Caso 2: Cambio de mes
**Entrada:** Reporte creado en enero, consultado en febrero  
**Resultado esperado:** Sistema no encuentra reporte vigente, permite nueva consulta  
**✓ Validado**

### ✅ Caso 3: DNI nuevo
**Entrada:** Búsqueda de DNI nunca consultado  
**Resultado esperado:** Permite subir imagen  
**✓ Validado**

### ✅ Caso 4: Intento de duplicado
**Entrada:** Asesor intenta subir segunda imagen para mismo DNI en el mes  
**Resultado esperado:** Error por constraint unique  
**✓ Validado**

### ✅ Caso 5: Eliminación prohibida
**Entrada:** Usuario intenta eliminar un reporte  
**Resultado esperado:** Error "Operación no permitida"  
**✓ Validado**

---

## 🛠️ Instalación

### 1. Copiar módulo
```bash
cp -r adt_sentinel /ruta/a/odoo/addons/
```

### 2. Actualizar lista de apps
En Odoo: Apps > Actualizar lista de aplicaciones

### 3. Instalar módulo
Apps > Buscar "ADT Sentinel" > Instalar

### 4. Verificar menú
Debe aparecer: **Sentinel** en la barra superior

---

## 📋 Menús Disponibles

1. **🔍 Consultar DNI** → Wizard de búsqueda/carga
2. **✅ Reportes Vigentes** → Solo reportes del mes actual
3. **📋 Todos los Reportes** → Vista completa
4. **📚 Histórico** → Reportes agrupados por fecha

---

## 🔧 Configuración Técnica

### Dependencias
- `base` (Odoo core)
- `contacts` (gestión de contactos)

### Base de datos
- Tabla: `adt_sentinel_report`
- Índices en: `document_number`, `query_date`, `is_current_month`
- Constraint: `unique(document_number, query_month, query_year)`

### Almacenamiento
- Imágenes en filestore (no en BD)
- Campo `attachment=True` para optimización

---

## 📞 Soporte

Para consultas sobre el módulo:
- **Desarrollador:** ADT
- **Versión:** 1.0.0
- **Compatible con:** Odoo 15.0+

---

## 📝 Notas Importantes

1. **NO modificar campos protegidos:** DNI, imagen, fecha y usuario son readonly después de creación
2. **Vigencia automática:** El estado se recalcula automáticamente cada mes
3. **Histórico completo:** Todos los registros se conservan para auditoría
4. **Trazabilidad:** Cada registro guarda quién y cuándo consultó

---

## 🔄 Versionamiento

### v1.0.0 (04/02/2026)
- ✅ Modelo `adt.sentinel.report`
- ✅ Wizard de consulta con validaciones
- ✅ Vigencia mensual automática
- ✅ Constraint para evitar duplicados
- ✅ Histórico permanente
- ✅ Vistas optimizadas
- ✅ Documentación completa

---

## ⚖️ Licencia

LGPL-3 - Ver archivo LICENSE para más detalles
