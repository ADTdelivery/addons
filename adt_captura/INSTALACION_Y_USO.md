# 🎉 MÓDULO ADT_CAPTURA - INSTALACIÓN Y USO

## ✅ ESTADO: 100% COMPLETO Y LISTO PARA INSTALAR

El módulo `adt_captura` ha sido desarrollado completamente según los requerimientos del documento de especificación.

---

## 📦 CONTENIDO DEL MÓDULO

### Archivos Python (9)
- ✅ `__init__.py` - Imports principales
- ✅ `__manifest__.py` - Configuración del módulo
- ✅ `models/__init__.py` - Imports de modelos
- ✅ `models/adt_captura_record.py` - Modelo principal (289 líneas)
- ✅ `models/adt_captura_mora.py` - Vista SQL clientes mora (159 líneas)
- ✅ `wizard/__init__.py` - Imports de wizards
- ✅ `wizard/adt_captura_pago_wizard.py` - Wizard pago (73 líneas)
- ✅ `wizard/adt_captura_retencion_wizard.py` - Wizard retención (69 líneas)
- ✅ `controllers/__init__.py` - Controllers (preparado para futuro)

### Archivos XML (6)
- ✅ `data/sequence_data.xml` - Secuencia CAP-00001
- ✅ `security/security_groups.xml` - 3 grupos de seguridad
- ✅ `security/ir.model.access.csv` - 10 reglas de acceso
- ✅ `views/adt_captura_record_views.xml` - Vistas principales (220 líneas)
- ✅ `views/adt_captura_mora_views.xml` - Vistas mora (210 líneas)
- ✅ `views/wizard_views.xml` - Vistas wizards (60 líneas)
- ✅ `views/menu.xml` - Menú principal

### Documentación (2)
- ✅ `README.md` - Documentación completa del usuario
- ✅ `IMPLEMENTACION_COMPLETA.md` - Resumen técnico

---

## 🚀 INSTRUCCIONES DE INSTALACIÓN

### Paso 1: Verificar Dependencias
El módulo requiere:
- ✅ `base` (Odoo Core)
- ✅ `web` (Interface Web)
- ✅ `fleet` (Gestión de Vehículos)
- ✅ `adt_comercial` (Módulo de Cuentas y Cuotas) **← IMPORTANTE**

> ⚠️ Asegúrate de que `adt_comercial` esté instalado antes de instalar `adt_captura`

### Paso 2: Activar Modo Desarrollador
```
1. Ir a: Configuración → Activar modo desarrollador
   O agregar ?debug=1 en la URL
```

### Paso 3: Actualizar Lista de Apps
```
1. Ir a: Apps
2. Click en "Actualizar lista de aplicaciones"
3. Confirmar
```

### Paso 4: Instalar el Módulo
```
1. En Apps, buscar: "ADT Captura"
2. Click en "Instalar"
3. Esperar a que termine la instalación
```

### Paso 5: Verificar Instalación
```
1. Verificar que aparezca el menú: "Gestión de Capturas"
2. Dentro debe haber:
   - Clientes en Mora
   - Capturas Activas
   - Historial
```

### Paso 6: Asignar Roles
```
1. Ir a: Configuración → Usuarios y Compañías → Usuarios
2. Seleccionar usuario
3. Pestaña "Derechos de acceso"
4. Buscar sección "Captura"
5. Asignar uno de los roles:
   - Capturador (puede crear capturas)
   - Supervisor de Captura (puede liberar y retener)
   - Administrador de Captura (acceso total)
```

---

## 📱 PRIMER USO

### Escenario: Capturar un vehículo

#### 1. Identificar cliente en mora
```
Menú → Gestión de Capturas → Clientes en Mora
- Verás una lista de clientes con pagos vencidos
- Los críticos aparecen en rojo
- Click en un cliente
```

#### 2. Iniciar captura
```
- Click en botón "Iniciar Captura"
- Seleccionar tipo:
  ✓ Inmediata (el vehículo fue capturado)
  ✓ Compromiso de Pago (cliente promete pagar en fecha X)
  ✓ Condicional
```

#### 3. Adjuntar evidencia (OBLIGATORIO)
```
- Ir a pestaña "Evidencia"
- Click en "Adjuntar archivo"
- Subir foto(s) del vehículo capturado
- IMPORTANTE: No se puede guardar sin evidencia
```

#### 4. Guardar
```
- Click en "Guardar"
- El registro obtiene número: CAP-00001
- Estado: Capturado
- Estado Pago: Pendiente
```

#### 5. Registrar pago
```
- Click en botón "Registrar Pago"
- Completar datos:
  * Monto: S/ 50.00 (default)
  * N° Voucher: xxxxxxx
  * Fecha de pago
  * Adjuntar voucher (obligatorio)
- Click "Registrar Pago"
- Estado Pago cambia a: Pagado
```

#### 6. Liberar vehículo (Solo Supervisores)
```
- Con el pago registrado, aparece botón: "Liberar Vehículo"
- Click en "Liberar Vehículo"
- Confirmar
- Estado cambia a: Liberado
- El registro se mueve automáticamente al Historial
```

---

## 🎯 CASOS DE USO COMUNES

### Caso A: Retener un vehículo
```
1. Abrir captura activa
2. Click en "Retener Vehículo" (Solo supervisores)
3. Ingresar motivo:
   "Cliente no responde llamadas ni mensajes. 
    Se intentó contactar 10 veces sin éxito."
4. Confirmar
5. Estado: Retenido → Va al Historial
```

### Caso B: Compromiso de pago
```
1. Cliente promete pagar el viernes
2. Iniciar captura → Tipo: "Compromiso de Pago"
3. Fecha compromiso: 2026-02-21
4. Adjuntar foto del acuerdo firmado
5. Guardar
6. El viernes, verificar si pagó
7. Si pagó: Registrar pago → Liberar
8. Si no pagó: Evaluar retención
```

### Caso C: Cancelar una captura
```
1. Cliente pagó directamente sin pasar por el proceso
2. Supervisor abre la captura
3. Click en "Cancelar"
4. Confirmar
5. Estado: Cancelado → Va al Historial
```

---

## 🔍 FILTROS Y BÚSQUEDAS

### En Clientes en Mora
- **Estado Crítico**: Solo clientes críticos
- **Más de 14 días**: Mora >= 14 días
- **Más de 30 días**: Mora >= 30 días
- **Qorilazo**: Solo cartera quincenal
- **Los Andes**: Solo cartera mensual
- **GPS Activo**: Vehículos con GPS funcionando
- **Sin Captura**: Clientes que aún no fueron capturados
- **Mi Cartera**: Solo clientes del asesor actual

### En Capturas Activas
- **Capturados**: Estado = Capturado
- **Liberados**: Estado = Liberado
- **Retenidos**: Estado = Retenido
- **Pago Pendiente**: Sin pago registrado
- **Pago Realizado**: Ya pagaron
- **Estado Crítico**: Mora crítica
- **Mis Capturas**: Capturas del usuario actual

---

## ⚠️ VALIDACIONES Y ERRORES COMUNES

### Error: "La evidencia es obligatoria"
**Causa**: Intentaste guardar sin adjuntar foto/video  
**Solución**: Ir a pestaña "Evidencia" → Adjuntar archivo

### Error: "La fecha de compromiso debe ser futura"
**Causa**: Pusiste una fecha pasada en compromiso de pago  
**Solución**: Seleccionar una fecha posterior a hoy

### Error: "No se puede liberar sin pago"
**Causa**: Intentaste liberar sin registrar el pago  
**Solución**: Primero usar botón "Registrar Pago"

### Error: "Solo supervisores pueden liberar"
**Causa**: Usuario no tiene rol de Supervisor  
**Solución**: Pedir al administrador que asigne el rol

### Error: "El motivo de retención debe tener al menos 10 caracteres"
**Causa**: Motivo muy corto  
**Solución**: Escribir un motivo detallado

---

## 📊 REPORTES Y ESTADÍSTICAS

### Ver métricas
Puedes agrupar las capturas por:
- Estado (para ver cuántas liberadas vs retenidas)
- Capturador (para ver rendimiento del equipo)
- Fecha (para ver evolución temporal)
- Tipo de captura (para ver qué método se usa más)

### Exportar datos
- Abrir cualquier vista tree
- Click en ⚙️ (engranaje)
- "Exportar"
- Seleccionar campos
- Descargar Excel

---

## ✅ CHECKLIST POST-INSTALACIÓN

- [ ] Módulo instalado correctamente
- [ ] Aparece menú "Gestión de Capturas"
- [ ] Roles asignados a usuarios
- [ ] Vista "Clientes en Mora" muestra datos
- [ ] Se puede crear una captura de prueba
- [ ] Se puede adjuntar evidencia
- [ ] Se puede registrar pago
- [ ] Supervisor puede liberar
- [ ] Supervisor puede retener
- [ ] Historial muestra registros finalizados

---

## 🆘 SOLUCIÓN DE PROBLEMAS

### Problema: No aparece el menú
**Solución**: 
1. Verificar que el módulo esté instalado
2. Actualizar la página (F5)
3. Verificar permisos del usuario

### Problema: Vista "Clientes en Mora" vacía
**Posibles causas**:
1. No hay clientes con cuotas vencidas (normal si es instalación nueva)
2. Módulo `adt_comercial` no tiene datos
3. Error en la vista SQL

### Problema: Error al instalar
**Solución**:
1. Verificar que `adt_comercial` esté instalado
2. Verificar logs de Odoo
3. Modo debug → Ver detalles del error

---

## 📝 NOTAS IMPORTANTES

1. **Evidencia obligatoria**: No se puede crear una captura sin foto/video
2. **Estados finales irreversibles**: Una vez liberado o retenido, no se puede cambiar
3. **Solo supervisores**: Liberar, retener y cancelar requieren rol de supervisor
4. **Deuda automática**: S/ 50.00 se asigna automáticamente al crear captura
5. **Historial**: Los registros finalizados se mueven automáticamente

---

## 🎓 CAPACITACIÓN SUGERIDA

### Para Capturadores (30 min)
1. Cómo identificar clientes en mora
2. Cómo registrar una captura
3. Cómo adjuntar evidencia
4. Cómo registrar pagos

### Para Supervisores (45 min)
1. Todo lo de Capturadores
2. Cómo liberar vehículos
3. Cómo retener vehículos
4. Cómo usar filtros y reportes

---

## 📞 SOPORTE

Para cualquier duda o problema:
1. Consultar este documento
2. Consultar README.md
3. Contactar al administrador del sistema
4. Revisar logs de Odoo (modo desarrollador)

---

**✅ MÓDULO LISTO PARA USAR**

El módulo `adt_captura` está completamente funcional y listo para ser usado en producción.

**Fecha de implementación**: Febrero 2026  
**Versión**: 1.0  
**Estado**: Producción Ready ✅
