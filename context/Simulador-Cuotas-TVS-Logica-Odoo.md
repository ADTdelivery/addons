# Simulador de Cuotas TVS – Lógica y Diseño de Módulo Odoo

2026-09-20 · @Someone

## Resumen

Se analizó el archivo `SIMULADOR - CRONOGRAMA - SMM`, pestaña **SIMULADOR**, bloque de celdas D1:M12 (columna B está oculta y no interviene en el cálculo; el resto de la pestaña, filas 14 en adelante, corresponde a otro producto "MOTOGAS" y a tablas de requisitos, y no forma parte de esta lógica).

Objetivo del módulo Odoo:

1. Guardar de forma **configurable** los parámetros del producto financiero por vehículo (TVS DELUXE 200CC y TVS DURAMAX 225CC): importe a financiar y tasa efectiva anual (TEA).
2. Reproducir **exactamente** las fórmulas de la hoja para obtener C/MENSUAL, C/SEMANAL y C/DIARIA.
3. Exponer una vista/asistente de simulación dentro de Odoo para hacer pruebas.
4. Exponer una API para que la app calcule la cuota que la asesora presenta al cliente.

## Variables de entrada

| Celda hoja | Nombre en la hoja | Quién la define | Dónde se edita |
| --- | --- | --- | --- |
| F2 | IMP. A FINANCIAR | Depende del vehículo elegido (TVS DELUXE 200CC o TVS DURAMAX 225CC) | Configuración por producto en Odoo (no la digita la asesora) |
| F3 | CUOTA INICIAL | La define el usuario en el momento de simular | Odoo y App |
| F5 | PLAZO (Meses) | La define el usuario en el momento de simular | Odoo y App |
| F6 | TASA EFECTIVA ANUAL (TEA) | Política de crédito, por producto | Solo Odoo (no editable desde la app) |
| F7 | PORTES (OTROS) | Constante de la hoja (valor 1) | No interviene en las fórmulas de C/MENSUAL, SEMANAL ni DIARIA (ver sección de exclusiones) |

Cada vehículo tiene su **propio** importe a financiar base y su **propia** TEA; deben configurarse de forma independiente por producto en Odoo.

## Mapeo de fórmulas ocultas (orden exacto de cálculo)

Esta es la cadena real de la hoja, celda por celda, en el orden en que se debe ejecutar:

1. **Capital (F4)** = Importe a financiar − Cuota inicial `F4 = F2 - F3`
2. **TEA en decimales (F8)** = TEA tal como se guarda (ej. 26.82% = 0.2682). En la hoja la celda F6 ya está en decimal; F8 solo la vuelve a expresar como decimal. **En el módulo, la TEA se guarda directamente como decimal.**
3. **Interés mensual – im (E9)** = tasa efectiva mensual derivada de la TEA `E9 = (1 + F8)^(1/12) - 1`
4. **Factor A (I9)** `I9 = E9 * (1 + E9)^F5`   (F5 = plazo en meses)
5. **Factor B (K9)** `K9 = (1 + E9)^F5 - 1`
6. **C/ MENSUAL (K10)** — fórmula de cuota de amortización (sistema francés) `K10 = F4 * I9 / K9`
7. **C/ DIARIA (K12)** `K12 = K10 / 30`
8. **C/ SEMANAL (K11)** `K11 = K12 * 7`

De apoyo (informativas, no requeridas para las 3 cuotas pero útiles para mostrar el detalle del crédito):

- Interés diario id (G9) = `((1+F8)^(1/360)-1)*100` — se calcula pero **no** participa en la cadena de K10/K11/K12.
- Total cuota capital (G11) = `F4`
- Total del crédito (G12) = `K10 * F5`
- Total de intereses (G10) = `G12 - G11`

Nota clave para la implementación: **C/SEMANAL y C/DIARIA no son cálculos independientes** — ambas se derivan de C/MENSUAL (K10 → /30 → \*7). No hay una tasa semanal o diaria distinta aplicada al capital.

## Validación numérica (misma prueba que la hoja)

Con los datos que trae el archivo: Importe a financiar = 25,000; Cuota inicial = 2,000; Plazo = 26 meses; TEA = 26.82%:

| Variable | Fórmula | Valor |
| --- | --- | --- |
| Capital (F4) | F2 − F3 | 23,000.00 |
| im (E9) | (1+0.2682)^(1/12)−1 | 0.0199971988... |
| Factor A (I9) | im×(1+im)^26 | 0.033461285... |
| Factor B (K9) | (1+im)^26−1 | 0.673298631... |
| **C/ MENSUAL (K10)** | F4×I9/K9 | **1,143.0434106969...** |
| **C/ DIARIA (K12)** | K10/30 | **38.1014470232...** |
| **C/ SEMANAL (K11)** | K12×7 | **266.7101291626...** |

Estos valores fueron verificados abriendo el archivo con los cálculos ya resueltos por Excel y coinciden exactamente con la cadena de fórmulas del punto anterior.

**Importante para que la prueba dé el mismo resultado:** la hoja no redondea en ningún paso intermedio (E9, I9, K9 se mantienen con todos los decimales). El módulo debe calcular con precisión decimal completa (float/decimal de alta precisión) internamente, y solo redondear al final para mostrar en pantalla (recomendado: 2 decimales, moneda Soles). Si se redondea en un paso intermedio, el resultado final no calzará con la hoja.

## Bloque I3:K8 (GPS, trámite, seguro) — se excluye de la lógica

La hoja tiene un bloque adicional junto al simulador: I3 ("TVS DELUXE 200 CC"), I4 ("GPS"), H5 ("TRAMITE"), I6 ("SEGURO CONTRA TODO RIESGO") y las celdas `K7 = SUM(K3:K6)` y `K8 = K7 * t/c`.

En el archivo de referencia, las celdas J4, J5 y J6 (donde irían los montos de GPS/trámite/seguro) están vacías, por lo que **K7 = 0 y K8 = 0**, y ninguna de las dos se usa dentro de F4 (Capital) ni de K10/K11/K12 (las cuotas). Es decir, aunque el bloque existe visualmente al lado del simulador, no está conectado a las fórmulas que calculan la cuota.

Por instrucción expresa de no inventar reglas fuera de lo que muestra la hoja, **este bloque queda fuera del módulo**. Si en el futuro el negocio decide que GPS/trámite/seguro sí deben sumarse al importe a financiar o a la cuota, eso requiere una regla nueva y explícita del negocio, no se asume aquí.

## Diseño de módulo Odoo — modelos de datos

**1. Producto financiable** (extiende el vehículo/producto existente, o un modelo propio `financing.vehicle`):

- Nombre del vehículo (TVS DELUXE 200CC, TVS DURAMAX 225CC)
- Importe a financiar por defecto (F2)
- Tasa efectiva anual – TEA (F6), guardada en decimal
- Activo / inactivo (para dar de baja un producto sin borrarlo)

**2. Simulación** (`financing.simulation`, registro persistido — recomendado para trazabilidad de qué simuló cada asesora y cuándo):

- Producto financiero (relación al punto 1)
- Cuota inicial ingresada (F3)
- Plazo en meses ingresado (F5)
- Capital resultante (F4, calculado)
- Interés mensual – im (E9, calculado)
- C/ Mensual, C/ Semanal, C/ Diaria (K10, K11, K12, calculados)
- Usuario que simuló y fecha (útil si la simulación viene de la app o de Odoo)
- Origen de la simulación (Odoo o App), para diferenciar pruebas internas de cotizaciones reales a clientes

Todos los campos calculados (Capital, im, C/Mensual, C/Semanal, C/Diaria) deben obtenerse ejecutando exactamente la cadena de fórmulas mapeada arriba — nunca almacenarse como valor fijo, para que cualquier cambio de TEA o de importe se refleje automáticamente en nuevas simulaciones.

## Vista de configuración en Odoo

Una pantalla tipo "Ajustes > Productos financieros" con una fila por vehículo:

| Vehículo | Importe a financiar | TEA |
| --- | --- | --- |
| TVS DELUXE 200 CC | editable | editable |
| TVS DURAMAX 225 CC | editable | editable |

Reglas de acceso:

- Editable solo por administración/gerencia (grupo de seguridad restringido), igual que en la hoja Excel actual, donde estos valores los define el negocio, no la asesora.
- No visible ni editable desde la app: la app solo consulta estos valores a través de la API para calcular, nunca los recibe como parámetro editable del lado del cliente.

## Vista/asistente de simulación dentro de Odoo

Un asistente "Simular cuota" pensado para replicar y probar el Excel dentro de Odoo:

**Entradas del formulario:**

- Vehículo (selecciona TVS DELUXE 200CC o TVS DURAMAX 225CC → trae automáticamente el importe a financiar y la TEA configurados)
- Cuota inicial (input)
- Plazo en meses (input)

**Botón "Calcular"** ejecuta la cadena de fórmulas mapeada y muestra:

- Capital
- Interés mensual (im)
- C/ Mensual
- C/ Semanal
- C/ Diaria
- (Opcional, informativo) Total de intereses y Total del crédito

Este asistente es el que se usa para las pruebas de paridad: se ingresan los mismos datos del Excel (25,000 / 2,000 / 26 meses / 26.82%) y el resultado debe coincidir exactamente con C/ Mensual = 1,143.04, C/ Semanal = 266.71, C/ Diaria = 38.10 (redondeado a 2 decimales).

## Diseño de la API para la app

La asesora, desde la app, solo necesita: elegir el vehículo, el plazo en meses, y ver la cuota en el periodo que prefiera mostrar al cliente (mensual, semanal o diaria). La cuota inicial también se ingresa (es un dato que varía por cliente).

**Request** (lo que envía la app):

| Campo | Descripción |
| --- | --- |
| vehiculo\_id | TVS DELUXE 200CC o TVS DURAMAX 225CC |
| cuota\_inicial | monto ingresado por la asesora |
| plazo\_meses | plazo elegido |

La TEA y el importe a financiar **no** se envían desde la app: el backend los toma del vehículo seleccionado (configurados en Odoo).

**Response** (lo que devuelve el backend, siempre las tres a la vez):

| Campo | Descripción |
| --- | --- |
| capital | F4 |
| cuota\_mensual | K10 |
| cuota\_semanal | K11 |
| cuota\_diaria | K12 |

**Regla clave:** el "periodo de pago" (día / semana / mes) que elige la asesora en la app **no cambia la fórmula** — las tres cuotas se calculan siempre juntas con la misma cadena de fórmulas, y la app solo decide cuál de las tres mostrar en pantalla según lo que el cliente quiera ver. Esto es exactamente lo que hace la hoja: calcula C/MENSUAL, C/SEMANAL y C/DIARIA al mismo tiempo, no una u otra según una opción.

## Reglas de negocio y validaciones (solo lo que está en la hoja)

- Capital debe ser positivo: `F2 - F3 > 0` (la cuota inicial no puede ser mayor o igual al importe a financiar).
- Plazo (F5) debe ser un número entero positivo de meses. La hoja no define un tope máximo de plazo, así que no se implementa ningúno salvo que el negocio lo indique explícitamente.
- La TEA (F6) solo se edita desde Odoo (configuración del producto); nunca se recibe como parámetro desde la app.
- Los cálculos internos deben hacerse con precisión decimal completa, sin redondear en pasos intermedios (E9, I9, K9), para que el resultado final coincida exactamente con el Excel al hacer la prueba de paridad.
- El bloque GPS / Trámite / Seguro (I3:K8) **no** se implementa porque, en el archivo de referencia, no afecta el capital ni la cuota (ver sección dedicada).

  |  |  |  |
  | --- | --- | --- |
  |  |  |  |
  |  |  |  |
- La celda F7 "PORTES (OTROS)" existe en la hoja pero no participa en ninguna fórmula de C/MENSUAL, SEMANAL o DIARIA; se documenta pero no se implementa como parte del cálculo salvo instrucción futura explícita del negocio.
