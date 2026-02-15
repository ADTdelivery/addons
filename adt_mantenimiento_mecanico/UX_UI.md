# 🎨 GUÍA UX/UI - ADT MANTENIMIENTO MECÁNICO

## Sistema de Gestión de Órdenes de Mantenimiento para Odoo

**Versión**: 2.0  
**Fecha**: Febrero 2026  
**Plataforma**: Odoo 16-18  
**Enfoque**: Talleres de Motocicletas y Mototaxis

---

## 📑 ÍNDICE

1. [Objetivos del Framework UX](#objetivos)
2. [Principios UX Base](#principios)
3. [Sistema Visual](#sistema-visual)
4. [Componentes UI](#componentes)
5. [Patrones de Interacción](#patrones-interaccion)
6. [Experiencia por Módulo](#experiencia-modulos)
7. [Flujos de Usuario](#flujos)
8. [Accesibilidad](#accesibilidad)
9. [Performance Percibida](#performance)
10. [Design System](#design-system)
11. [Mensajes y Notificaciones](#mensajes)
12. [Checklist UX/UI](#checklist)

---

## 🎯 OBJETIVOS DEL FRAMEWORK UX {#objetivos}

### Visión General

Diseñar una experiencia que sea:

✅ **Clara para usuarios no técnicos**
- Mecánicos, asesores de servicio, cajeros
- Lenguaje simple y directo
- Iconografía intuitiva

✅ **Rápida para usuarios expertos**
- Shortcuts de teclado
- Acciones masivas
- Edición inline
- Atajos contextuales

✅ **Consistente entre módulos**
- Design system unificado
- Patrones reutilizables
- Comportamiento predecible

✅ **Visualmente moderna**
- Diseño limpio y espaciado
- Colores profesionales
- Microinteracciones fluidas

✅ **Con feedback constante**
- Estados visuales claros
- Confirmaciones inmediatas
- Mensajes informativos
- Indicadores de progreso

1️⃣ Principios UX base para Odoo
🧠 1. Sistema orientado a tareas (no a menús)

En Odoo tradicional, el usuario navega mucho por menús.
La UX moderna debe enfocarse en:

👉 “¿Qué quiere lograr el usuario?”

Ejemplo:

Crear factura

Registrar venta

Aprobar solicitud

✅ Implementación

Botones de acción primaria visibles

Acciones rápidas en dashboards

Shortcuts contextuales

⚡ 2. Reducir carga cognitiva

Cada pantalla debe responder:

Qué es esto
Qué puedo hacer
Qué pasó

🔁 3. Feedback continuo

Toda acción debe tener:

Estado visual

Confirmación

Resultado claro

Esto conecta con el flujo que definimos antes.

2️⃣ Lineamientos UI modernos
🎨 2.1 Sistema visual
Paleta recomendada

Color primario para acciones

Neutrales suaves para fondos

Colores de estado claros

Estado	Color
Success	Verde suave
Error	Rojo suave
Warning	Ámbar
Info	Azul

👉 Evitar colores saturados estilo ERP antiguo.

🧱 2.2 Layout
Diseño recomendado

Contenedores con espacio (padding 16–24)

Bordes suaves (6–10px radius)

Sombras ligeras

Esto genera sensación moderna y menos densidad visual.

🪟 2.3 Jerarquía visual

Cada vista debe tener:

1️⃣ Título claro
2️⃣ Acción primaria
3️⃣ Acciones secundarias
4️⃣ Contenido

3️⃣ Interacciones modernas con “style” en Odoo

Aquí es donde elevamos la experiencia.

🖱 Microinteracciones

Agregar:

Hover en botones

Transiciones suaves (150–250ms)

Feedback al guardar

Estados activos visibles

🔘 Botones
Acción primaria

Color sólido

Texto claro

Icono opcional

Ej:
👉 Guardar factura

Acción secundaria

Outline o ghost

⏳ Estados de carga

En Odoo tradicional muchas veces no hay feedback.

Reglas

Spinner dentro del botón

Skeleton loaders en listas

Mensaje si tarda más de 8s

4️⃣ Patrones UX específicos para módulos de Odoo
📊 List Views
Problema actual

Sobrecarga visual.

Mejora UX

✔️ Filtrado visible
✔️ Búsqueda persistente
✔️ Columnas configurables
✔️ Acciones rápidas inline

🧾 Formularios
Lineamientos

Agrupar campos por secciones

Mostrar campos progresivamente

Validación inline

Guardado automático opcional

📈 Dashboards

Un dashboard moderno debe:

Mostrar KPIs clave

Acciones rápidas

Estado del negocio

Alertas

5️⃣ Flujo UX cuando se ejecuta una acción (adaptado a Odoo)

1️⃣ Usuario presiona acción
2️⃣ Botón cambia a loading
3️⃣ Sistema bloquea doble acción
4️⃣ Mensaje de progreso si tarda
5️⃣ Confirmación visual

6️⃣ Accesibilidad y usabilidad
🔍 Reglas

Contraste AA mínimo

Tamaño de click ≥ 40px

Atajos de teclado

Navegación clara

7️⃣ Experiencia para usuarios expertos (muy importante en ERP)

Los ERP fallan cuando solo piensan en novatos.

Agregar:

✔️ Shortcuts
✔️ Acciones masivas
✔️ Edición rápida
✔️ Personalización

8️⃣ Consistencia entre módulos

Un problema clásico en Odoo es que cada módulo se siente distinto.

Debes definir:

Sistema de botones

Sistema de mensajes

Sistema de loaders

Sistema de formularios

👉 Esto se convierte en tu Design System

9️⃣ Mensajes UX recomendados
✔️ Success

“Factura creada correctamente”

⚠️ Error

“No pudimos guardar la factura. Revisa los campos obligatorios”

ℹ️ Info

“Este cliente tiene pagos pendientes”

🔟 Nivel avanzado: UX emocional en ERP

Aunque es un sistema empresarial, la experiencia debe sentirse:

Fluida

Segura

Confiable

Predecible

Un ERP moderno debe transmitir control, no complejidad.

🧩 Arquitectura UX recomendada para Odoo 15
Capas

1️⃣ Design System
2️⃣ Componentes reutilizables
3️⃣ Patrones de interacción
4️⃣ Experiencia por módulo

📋 Checklist UX/UI para Odoo moderno
Interacción

✅ Feedback en acciones
✅ Anti doble click
✅ Estados de carga

Visual

✅ Jerarquía clara
✅ Espacios adecuados
✅ Colores consistentes

Usabilidad

✅ Flujos simples
✅ Mensajes claros
✅ Acciones visibles

Performance percibida

✅ Skeleton loaders
✅ Respuesta inmediata