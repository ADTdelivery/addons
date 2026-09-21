# Lógica Funcional --- Simulador y Cronograma de Pagos en Odoo

## 1. Objetivo

Construir un módulo configurable en **Odoo** que concentre toda la
lógica financiera del simulador y del cronograma de pagos.

La aplicación móvil utilizada por las vendedoras **no debe realizar
cálculos financieros ni contener tasas o reglas fijas**. Su función será
solicitar a Odoo las opciones disponibles, enviar los datos
seleccionados por la vendedora y mostrar el resultado calculado por
Odoo.

La vendedora debe poder simular un financiamiento indicando únicamente
los datos comerciales necesarios:

1.  **Producto** que se está cotizando.
2.  **Monto de cuota inicial** que entregará el cliente.
3.  **Tipo o frecuencia de pago:** diario, semanal o mensual.
4.  **Periodo/plazo** disponible para ese producto y modalidad.

El precio del producto, tasas, gastos, reglas, cantidad de pagos y demás
parámetros deben provenir automáticamente de Odoo.

------------------------------------------------------------------------

## 2. Hallazgos del Excel actual

En la pestaña **SIMULADOR** se identifican como elementos principales:

-   Importe a financiar.
-   Cuota inicial.
-   Capital.
-   Plazo expresado en meses.
-   Tasa efectiva anual (TEA).
-   Tasa mensual.
-   Interés diario.
-   Portes u otros conceptos.
-   Cuota mensual.
-   Cuota semanal.
-   Cuota diaria.
-   Total del crédito.
-   Total de intereses.

La fórmula principal del archivo calcula primero una **cuota mensual
mediante amortización de cuota fija**.

Posteriormente obtiene:

-   **Cuota diaria = cuota mensual / 30**
-   **Cuota semanal = cuota diaria × 7**

Por lo tanto, en el Excel actual las cifras diaria y semanal son
principalmente equivalencias de una cuota mensual.

### Cambio requerido para Odoo

Para el nuevo sistema, **Diario, Semanal y Mensual deben convertirse en
modalidades seleccionables explícitamente**.

La modalidad seleccionada por la vendedora determinará:

-   El importe que se mostrará como cuota.
-   La cantidad de pagos.
-   Las fechas de vencimiento.
-   El cronograma.
-   La forma en que se distribuyen capital e intereses.
-   Las reglas particulares que administración configure para esa
    frecuencia.

------------------------------------------------------------------------

# 3. Datos que proporcionará la vendedora

La pantalla debe ser sencilla.

## Datos seleccionados/ingresados

### Producto

Ejemplo:

> TVS DELUXE 200 CC

El producto permite a Odoo conocer automáticamente:

-   Precio.
-   Plan financiero aplicable.
-   Inicial mínima.
-   Inicial máxima, si existe.
-   Modalidades de pago disponibles.
-   Plazos disponibles.
-   Gastos y conceptos adicionales.

### Cuota inicial

Ejemplo:

> S/ 2,000.00

Este es el dinero que el cliente entrega inicialmente.

No debe confundirse con la cuota periódica que posteriormente pagará el
cliente.

### Tipo de cuota / frecuencia de pago

La vendedora seleccionará:

-   **Diario**
-   **Semanal**
-   **Mensual**

### Periodo

Después de seleccionar la frecuencia, la aplicación mostrará únicamente
los periodos permitidos por Odoo.

Ejemplo conceptual:

> Producto: TVS DELUXE 200 CC\
> Inicial: S/ 2,000\
> Tipo de cuota: Semanal\
> Periodo: 26 meses

La vendedora no ingresa:

-   TEA.
-   Tasa mensual.
-   Tasa diaria.
-   Número de cuotas.
-   Capital financiado.
-   Intereses.
-   Precio manual.
-   Fórmulas.

Todo eso lo determina Odoo.

------------------------------------------------------------------------

# 4. Flujo propuesto en la aplicación

El flujo sería:

**Seleccionar producto**

↓

**Ingresar cuota inicial**

↓

**Seleccionar tipo de cuota**

> Diario \| Semanal \| Mensual

↓

**Seleccionar periodo**

↓

**Simular**

↓

Odoo devuelve:

-   Precio del producto.
-   Cuota inicial.
-   Capital financiado.
-   Tipo de cuota.
-   Periodo.
-   Número de pagos.
-   Monto de cada cuota.
-   Primera fecha de pago.
-   Última fecha estimada.
-   Total financiado.
-   Total de intereses.
-   Gastos adicionales.
-   Total a pagar.
-   Cronograma.

------------------------------------------------------------------------

# 5. Ejemplo de experiencia de la vendedora

Supongamos:

-   Producto: TVS DELUXE 200 CC
-   Precio configurado: S/ 25,000
-   Inicial: S/ 2,000
-   Capital base: S/ 23,000
-   Plazo: 26 meses

La vendedora ingresa:

> Inicial: **S/ 2,000**

Selecciona:

> Tipo de cuota: **Semanal**

Selecciona:

> Periodo: **26 meses**

La aplicación consulta Odoo.

Odoo podría responder, por ejemplo:

> Precio: S/ 25,000\
> Inicial: S/ 2,000\
> Financiamiento: S/ 23,000\
> Modalidad: Semanal\
> Plazo: 26 meses\
> Número de pagos: calculado por Odoo\
> Cuota semanal: calculada por Odoo\
> Total del financiamiento: calculado por Odoo

La vendedora solamente comunica al cliente el resultado.

------------------------------------------------------------------------

# 6. Diferencia entre frecuencia y periodo

Estos dos conceptos deben mantenerse separados.

## Frecuencia

Indica **cada cuánto paga el cliente**.

Ejemplos:

-   Diario → paga cada día definido como cobrable.
-   Semanal → paga cada 7 días o en un día fijo de la semana.
-   Mensual → paga una vez al mes.

## Periodo

Indica **durante cuánto tiempo estará vigente el financiamiento**.

Ejemplo:

> 26 meses

Por lo tanto:

> Frecuencia = Semanal\
> Periodo = 26 meses

significa que el cliente realizará pagos semanales durante un
financiamiento cuya duración comercial es de 26 meses.

------------------------------------------------------------------------

# 7. No conviene convertir simplemente la cuota mensual

Este es un punto fundamental.

El Excel actualmente realiza aproximadamente:

> Mensual → dividir entre 30 → obtener diario\
> Diario × 7 → obtener semanal

Esto sirve para mostrar una **equivalencia comercial**, pero no
necesariamente genera un cronograma real.

Si se desea que el cliente efectivamente pague diariamente o
semanalmente, Odoo debe manejar esas modalidades como frecuencias
reales.

Por ejemplo, si el cliente elige semanal, el cronograma debería contener
vencimientos semanales reales:

> Pago 1 → fecha\
> Pago 2 → +7 días\
> Pago 3 → +7 días\
> Pago 4 → +7 días\
> ...

Y no simplemente mostrar el valor mensual dividido entre días.

Lo mismo aplica para pagos diarios.

------------------------------------------------------------------------

# 8. Configuración de frecuencias en Odoo

Odoo debería permitir administrar las modalidades.

## Modalidad mensual

Configuración conceptual:

-   Nombre: Mensual.
-   Código: MONTHLY.
-   Frecuencia: 1 mes.
-   Activa: Sí.
-   Días de gracia: configurable.
-   TEA/Tasa aplicable: configurable.
-   Plazos permitidos: configurables.

## Modalidad semanal

Configuración conceptual:

-   Nombre: Semanal.
-   Código: WEEKLY.
-   Frecuencia: 7 días.
-   Activa: Sí.
-   Día de cobro: configurable.
-   Días de gracia: configurable.
-   TEA/Tasa aplicable: configurable.
-   Plazos permitidos: configurables.

## Modalidad diaria

Configuración conceptual:

-   Nombre: Diario.
-   Código: DAILY.
-   Frecuencia: configurable.
-   Activa: Sí.
-   Cobrar domingos: Sí/No.
-   Cobrar feriados: Sí/No.
-   Días de gracia: configurable.
-   TEA/Tasa aplicable: configurable.
-   Plazos permitidos: configurables.

Esto permite que administración cambie las reglas sin modificar la app.

------------------------------------------------------------------------

# 9. Configuración de plazos

No debe permitirse que la vendedora escriba cualquier plazo.

Odoo define cuáles están autorizados.

Ejemplo:

  Periodo    Diario   Semanal   Mensual
  ---------- -------- --------- ---------
  12 meses   Sí       Sí        Sí
  18 meses   Sí       Sí        Sí
  24 meses   Sí       Sí        Sí
  26 meses   Sí       Sí        Sí
  36 meses   No       Sí        Sí

De esta manera, si la vendedora selecciona **Diario**, la app pregunta a
Odoo qué periodos están disponibles y muestra solamente esos valores.

------------------------------------------------------------------------

# 10. Conversión de TEA según frecuencia

Si se mantiene una TEA como tasa principal, Odoo debe convertirla a la
tasa efectiva correspondiente a la frecuencia.

## Mensual

Conceptualmente:

`TEM = (1 + TEA)^(1/12) - 1`

## Diaria

Utilizando la convención financiera que la empresa defina:

`TED = (1 + TEA)^(1/base_dias) - 1`

La base podría ser, por ejemplo, 360 o 365 días, pero **debe definirse
como una regla de negocio configurable**.

El Excel analizado utiliza una lógica basada en 360 días para obtener el
interés diario.

## Semanal

La tasa efectiva semanal debe derivarse utilizando la convención
aprobada por la empresa.

Por ejemplo, si se trabaja con una base diaria:

`TES = (1 + TED)^7 - 1`

La fórmula definitiva deberá respetar la política financiera real de la
empresa.

------------------------------------------------------------------------

# 11. Dos posibles políticas financieras

Antes de implementar el módulo se debe decidir cuál de estas políticas
representa el negocio.

## Opción A --- Equivalencia comercial

Se calcula siempre un crédito mensual y luego:

-   Diario = cuota mensual / 30.
-   Semanal = cuota diaria × 7.
-   Mensual = cuota mensual.

### Ventaja

Replica directamente el comportamiento observado en el simulador Excel.

### Problema

No representa necesariamente una amortización diaria o semanal real y
puede producir dificultades al construir un cronograma exacto.

------------------------------------------------------------------------

## Opción B --- Frecuencia de pago real

Cada modalidad tiene su propia frecuencia financiera:

-   Diario → amortización por pagos diarios.
-   Semanal → amortización por pagos semanales.
-   Mensual → amortización por pagos mensuales.

La tasa correspondiente al periodo y la cantidad de pagos se calculan
según esa frecuencia.

### Ventaja

Permite generar un cronograma coherente con lo que realmente pagará el
cliente.

### Recomendación funcional

Para el nuevo módulo, esta opción es más consistente **si efectivamente
el cliente realizará pagos diarios, semanales o mensuales**.

Si "diario" y "semanal" solamente se muestran como referencia comercial
y el contrato sigue siendo mensual, debe conservarse la Opción A.

Esta decisión debe confirmarse con el responsable financiero antes del
desarrollo.

------------------------------------------------------------------------

# 12. Cálculo del capital

La base inicial sería:

`Capital = Precio financiable - Cuota inicial`

Ejemplo:

`S/ 25,000 - S/ 2,000 = S/ 23,000`

Sin embargo, debe definirse qué sucede con:

-   GPS.
-   Trámite.
-   Tarjeta.
-   Placa.
-   SOAT.
-   Prendas.
-   Gastos notariales.
-   Seguro contra todo riesgo.
-   Portes.
-   ITF.
-   Otros cargos.

Cada concepto debería indicar en Odoo si:

1.  Se paga junto con la inicial.
2.  Se suma al capital financiado.
3.  Se distribuye entre las cuotas.
4.  Se cobra separadamente.
5.  No aplica.

Entonces podría existir:

`Capital financiado = Precio - Inicial + Gastos financiables`

------------------------------------------------------------------------

# 13. Cantidad de pagos

La cantidad de cuotas **no debe ingresarla la vendedora**.

Debe calcularla Odoo según:

-   Tipo de cuota.
-   Periodo.
-   Calendario.
-   Días cobrables.
-   Feriados.
-   Reglas configuradas.

## Mensual

Para 26 meses:

> 26 cuotas mensuales.

## Semanal

Para un plazo expresado comercialmente en meses, Odoo debe construir las
fechas semanales reales comprendidas entre la fecha inicial y la fecha
final del financiamiento.

No es recomendable asumir simplemente:

`26 × 4 semanas`

porque un mes calendario no equivale exactamente a cuatro semanas.

## Diario

Odoo deberá contar los días cobrables reales dentro del periodo.

Por ejemplo, si no se cobra domingo:

> lunes a sábado = días cobrables\
> domingo = omitido

Si tampoco se cobran feriados, estos deben excluirse según el calendario
configurado.

------------------------------------------------------------------------

# 14. Regla de fechas

La configuración debe establecer:

-   Fecha de desembolso/venta.
-   Cuándo comienza el primer pago.
-   Días cobrables.
-   Tratamiento de domingos.
-   Tratamiento de feriados.
-   Qué sucede si una fecha cae en día no cobrable.
-   Día fijo de cobro semanal, si aplica.
-   Día de vencimiento mensual, si aplica.

Ejemplo semanal:

> Venta: 10/10/2026\
> Primer pago: 17/10/2026\
> Segundo pago: 24/10/2026\
> Tercer pago: 31/10/2026

Ejemplo mensual:

> Venta: 10/10/2026\
> Primer pago: 10/11/2026\
> Segundo pago: 10/12/2026

------------------------------------------------------------------------

# 15. Motor de simulación

Conceptualmente Odoo recibirá:

-   Producto.
-   Cuota inicial.
-   Tipo de cuota.
-   Periodo.

Y realizará:

1.  Obtener precio vigente.
2.  Obtener plan financiero vigente.
3.  Validar cuota inicial.
4.  Obtener modalidad seleccionada.
5.  Validar que el periodo sea permitido.
6.  Determinar gastos aplicables.
7.  Calcular capital financiado.
8.  Obtener TEA/tasa configurada.
9.  Convertir tasa según frecuencia.
10. Generar fechas de pago.
11. Determinar cantidad real de cuotas.
12. Calcular monto de cuota.
13. Generar amortización.
14. Ajustar última cuota por redondeos si corresponde.
15. Calcular intereses totales.
16. Calcular gastos totales.
17. Calcular total a pagar.
18. Devolver resultado a la app.

------------------------------------------------------------------------

# 16. Cronograma de pagos

La pestaña **CRONOGRAMA DE PAGOS** del Excel intenta manejar campos
como:

-   Número de cuota.
-   Fecha.
-   Interés.
-   Capital.
-   Otros.
-   Cuota.
-   ITF.
-   Total de cuota.
-   Saldo.

En el archivo existen referencias rotas hacia el simulador, por lo que
no conviene copiar esas fórmulas literalmente.

Odoo debe reconstruir el cronograma a partir de las reglas financieras.

Ejemplo conceptual:

  -----------------------------------------------------------------------------
          N° Fecha       Capital     Interés       Otros       Cuota      Saldo
  ---------- ------- ----------- ----------- ----------- ----------- ----------
           1 Fecha 1   calculado   calculado   calculado   calculada      saldo

           2 Fecha 2   calculado   calculado   calculado   calculada      saldo

           3 Fecha 3   calculado   calculado   calculado   calculada      saldo

         ... ...             ...         ...         ...         ...        ...

           N Fecha     calculado   calculado   calculado    ajustada       0.00
             final                                                   
  -----------------------------------------------------------------------------

------------------------------------------------------------------------

# 17. Ejemplo de selección en la app

## Paso 1 --- Producto

> TVS DELUXE 200 CC\
> Precio: S/ 25,000

## Paso 2 --- Inicial

> S/ 2,000

## Paso 3 --- ¿Cómo desea pagar?

La vendedora selecciona:

> ○ Diario\
> ● Semanal\
> ○ Mensual

## Paso 4 --- Periodo

Odoo devuelve las opciones permitidas:

> 12 meses\
> 18 meses\
> 24 meses\
> 26 meses

La vendedora selecciona:

> 26 meses

## Paso 5 --- Resultado

La app muestra:

> **Cuota semanal**\
> **S/ XXX.XX**
>
> Inicial: S/ 2,000\
> Capital financiado: S/ XX,XXX\
> Periodo: 26 meses\
> Cantidad de pagos: XXX\
> Total a pagar: S/ XX,XXX
>
> Ver cronograma

------------------------------------------------------------------------

# 18. Configuración del plan financiero en Odoo

Se propone conceptualmente una entidad:

## Plan financiero

Campos principales:

-   Nombre.
-   Código.
-   Estado.
-   Fecha de inicio de vigencia.
-   Fecha de fin de vigencia.
-   Moneda.
-   TEA base.
-   Base anual: 360/365/configurable.
-   Sistema de amortización.
-   Regla de redondeo.
-   Productos aplicables.
-   Inicial mínima.
-   Inicial máxima.
-   Inicial mínima porcentual.
-   Gastos.
-   Modalidades disponibles.
-   Plazos disponibles.

------------------------------------------------------------------------

# 19. Configuración por modalidad

Cada plan debe poder tener condiciones distintas para Diario, Semanal y
Mensual.

Ejemplo:

  Modalidad     Activa            TEA Periodos
  ----------- -------- -------------- --------------------
  Diario            Sí   configurable 12, 18, 24, 26
  Semanal           Sí   configurable 12, 18, 24, 26, 36
  Mensual           Sí   configurable 12, 18, 24, 26, 36

No se debe asumir obligatoriamente que las tres modalidades tendrán la
misma tasa.

------------------------------------------------------------------------

# 20. Configuración por producto

Ejemplo conceptual:

## TVS DELUXE 200 CC

-   Precio financiable: S/ 25,000.
-   Plan: Mototaxi 2026.
-   Inicial mínima: configurable.
-   Diario: permitido.
-   Semanal: permitido.
-   Mensual: permitido.

## Otro producto

Podría tener:

-   Otro precio.
-   Otro plan.
-   Otra inicial mínima.
-   Solamente semanal y mensual.
-   Diferentes periodos.

La aplicación no necesita conocer estas reglas previamente.

------------------------------------------------------------------------

# 21. Validaciones

Odoo debe validar como mínimo:

### Inicial insuficiente

> La cuota inicial mínima para este producto es S/ X.

### Inicial superior al precio

No permitir una inicial que deje capital negativo.

### Modalidad no permitida

> Este producto no permite pagos diarios.

### Periodo no permitido

> El periodo seleccionado no está disponible para pagos semanales.

### Plan vencido

No utilizar configuraciones fuera de su vigencia.

### Producto sin plan

No permitir simulación hasta configurar un plan válido.

------------------------------------------------------------------------

# 22. Simulación vs. cotización

Conviene manejar dos estados.

## Simulación

La vendedora puede cambiar libremente:

-   Inicial.
-   Tipo de cuota.
-   Periodo.

Puede realizar múltiples simulaciones sin generar una operación formal.

## Cotización

Cuando el cliente selecciona una alternativa, se guarda una fotografía
de las condiciones utilizadas:

-   Producto.
-   Precio.
-   Inicial.
-   Capital.
-   Frecuencia.
-   Periodo.
-   Cantidad de cuotas.
-   Tasa aplicada.
-   Monto de cuota.
-   Gastos.
-   Total.
-   Cronograma.
-   Vendedora.
-   Cliente.
-   Fecha y hora.
-   Plan financiero utilizado.

Una cotización histórica **no debe cambiar** si posteriormente
administración modifica las tasas del plan.

------------------------------------------------------------------------

# 23. Responsabilidades de Odoo y de la app

## Odoo

Será responsable de:

-   Productos.
-   Precios.
-   Planes financieros.
-   Tasas.
-   Modalidades.
-   Plazos.
-   Inicial mínima.
-   Gastos.
-   Calendarios.
-   Cálculos.
-   Cronogramas.
-   Validaciones.
-   Vigencias.
-   Historial de cotizaciones.

## Aplicación móvil

Será responsable de:

-   Mostrar productos.
-   Permitir ingresar la inicial.
-   Mostrar tipos de cuota permitidos.
-   Mostrar periodos permitidos.
-   Enviar selección a Odoo.
-   Mostrar resultado.
-   Mostrar cronograma.
-   Confirmar cotización cuando corresponda.

La app **no debe duplicar el motor financiero**.

------------------------------------------------------------------------

# 24. Flujo técnico conceptual

``` text
APP
 |
 | Selecciona producto
 v
ODOO
 |
 | Devuelve precio + reglas disponibles
 v
APP
 |
 | Vendedora ingresa inicial
 | Selecciona Diario / Semanal / Mensual
 | Selecciona periodo
 v
ODOO
 |
 | Valida configuración
 | Calcula capital
 | Obtiene tasa
 | Determina frecuencia
 | Genera fechas
 | Determina número de pagos
 | Calcula cuota
 | Genera cronograma
 | Calcula total
 v
APP
 |
 | Muestra cuota
 | Muestra resumen
 | Permite ver cronograma
 v
VENDEDORA / CLIENTE
```

------------------------------------------------------------------------

# 25. Datos mínimos que debe enviar la app

Conceptualmente, una simulación requiere:

``` text
producto
cuota_inicial
tipo_cuota
periodo
```

Ejemplo:

``` text
Producto: TVS DELUXE 200 CC
Cuota inicial: 2000
Tipo de cuota: SEMANAL
Periodo: 26 meses
```

No es necesario que la app envíe:

``` text
precio
TEA
tasa semanal
tasa mensual
tasa diaria
cantidad de cuotas
intereses
capital
total
```

Estos datos pertenecen al motor de Odoo.

------------------------------------------------------------------------

# 26. Resultado mínimo que debe devolver Odoo

Conceptualmente:

``` text
Producto
Precio
Cuota inicial
Capital financiado
Tipo de cuota
Periodo
Número de cuotas
Monto de cuota
Fecha del primer pago
Fecha del último pago
Intereses
Gastos
Total del crédito
Total a pagar
Cronograma
```

------------------------------------------------------------------------

# 27. Decisiones de negocio pendientes

Antes de programar se deben confirmar estas reglas con el área
financiera:

1.  ¿Diario, semanal y mensual serán **frecuencias reales de
    amortización** o solamente equivalencias visuales de una cuota
    mensual?
2.  ¿La TEA es igual para las tres modalidades?
3.  ¿La tasa puede variar según el plazo?
4.  ¿Se utiliza base de 360 o 365 días?
5.  ¿En modalidad diaria se cobra los domingos?
6.  ¿Se cobra en feriados?
7.  ¿Cuál es la fecha del primer pago?
8.  ¿En modalidad semanal existe un día fijo de cobranza?
9.  ¿Cómo se determina la fecha final cuando el plazo se expresa en
    meses?
10. ¿Qué sucede con una última cuota que resulte diferente por
    calendario o redondeo?
11. ¿GPS se financia o se paga inicialmente?
12. ¿Trámites se financian?
13. ¿Seguro se financia?
14. ¿Portes forman parte de cada cuota?
15. ¿Cómo se calcula ITF?
16. ¿Cuál es la inicial mínima?
17. ¿La inicial mínima cambia por producto?
18. ¿Los plazos disponibles cambian por producto?
19. ¿Las tasas cambian por producto?
20. ¿Una cotización tendrá fecha de expiración?

Estas decisiones deben convertirse posteriormente en parámetros
configurables siempre que sea razonable.

------------------------------------------------------------------------

# 28. Lógica funcional final propuesta

La lógica general queda definida de la siguiente manera:

``` text
PRODUCTO
   +
CUOTA INICIAL
   +
TIPO DE CUOTA
(DIARIO / SEMANAL / MENSUAL)
   +
PERIODO
        |
        v
PLAN FINANCIERO CONFIGURADO EN ODOO
        |
        v
PRECIO + REGLAS + TASA + GASTOS
        |
        v
CAPITAL A FINANCIAR
        |
        v
FRECUENCIA DE PAGO
        |
        v
CALENDARIO Y NÚMERO DE CUOTAS
        |
        v
MONTO DE LA CUOTA
        |
        v
CRONOGRAMA
        |
        v
TOTAL A PAGAR
```

Desde el punto de vista de la vendedora, el proceso queda reducido a:

> **Producto + Inicial + Tipo de cuota + Periodo → Resultado**

Toda la complejidad financiera queda centralizada en Odoo.

------------------------------------------------------------------------

# 29. Conclusión

El nuevo simulador no debe limitarse a copiar visualmente el Excel.

El Excel actual sirve para identificar las variables y la lógica
financiera existente, pero el módulo de Odoo debe convertirlas en reglas
administrables.

La decisión más importante antes del desarrollo es confirmar si
**Diario, Semanal y Mensual representan formas reales de pago**.

Si son formas reales, cada una debe producir su propio calendario y
cronograma. La vendedora seleccionará explícitamente la modalidad y el
periodo, mientras que Odoo determinará automáticamente la cantidad de
cuotas, las fechas y el importe correspondiente.

De esta forma, la aplicación móvil permanece sencilla para las
vendedoras y toda modificación futura de tasas, plazos, precios, gastos
o reglas de cobranza puede realizarse desde Odoo sin necesidad de
publicar una nueva versión de la app.

---

# 30. Cargo adicional diario configurable desde Odoo

El sistema debe incorporar una regla adicional administrada **exclusivamente desde Odoo**.

La vendedora **no debe ingresar, seleccionar ni modificar este valor**. Para ella debe ser completamente transparente. La aplicación móvil solamente mostrará el resultado final calculado por Odoo.

## Configuración

Dentro del plan financiero se debe poder configurar, como mínimo:

- Activar/desactivar cargo adicional diario.
- Monto del cargo diario.
- Valor de referencia inicial: **S/ 5.00**.
- Fecha de inicio y fin de vigencia, si corresponde.
- Modalidades a las que aplica.
- Si aplica o no a domingos.
- Si aplica o no a feriados.
- Regla de días cobrables.

Ejemplo:

```text
Cargo adicional diario: ACTIVO
Monto: S/ 5.00
Visible/editable por vendedora: NO
```

El valor de S/ 5.00 **no debe estar programado de forma fija**. Administración podría posteriormente cambiarlo a S/ 3.00, S/ 7.00, desactivarlo o modificar su vigencia sin publicar una nueva versión de la aplicación móvil.

## Transparencia para la vendedora

La aplicación no enviará el monto del cargo diario.

La solicitud continuará siendo conceptualmente:

```text
Producto
Cuota inicial
Tipo de cuota
Periodo
```

Al recibir la solicitud, Odoo:

1. Identifica el plan financiero vigente.
2. Obtiene automáticamente el cargo diario configurado.
3. Determina los días a los que corresponde aplicarlo.
4. Incorpora el cargo al cálculo según la política financiera configurada.
5. Devuelve a la app el resultado final.

De esta manera se evita que una vendedora pueda omitir, modificar o aplicar incorrectamente el cargo.

## Registro histórico

Cuando una simulación se convierta en cotización, se debe guardar también una fotografía del cargo aplicado.

Ejemplo:

```text
Cargo diario vigente al cotizar: S/ 5.00
```

Si administración posteriormente cambia el cargo a S/ 7.00, las nuevas simulaciones utilizarán S/ 7.00, pero una cotización ya confirmada conservará las condiciones originales.

---

# 31. Aplicación del cargo en el cronograma

El cargo adicional debe quedar contemplado por el motor de cronograma.

Conceptualmente, cada vencimiento puede contener:

```text
Cuota financiera
+ Cargo(s) adicional(es) aplicables
+ Otros conceptos
+ ITF, si corresponde
= Total a pagar
```

El motor debe conservar por separado el componente financiero y el cargo adicional para mantener trazabilidad.

Por ejemplo, en una modalidad diaria, si la cuota financiera fuera S/ 38.10 y el cargo configurado aplicable al día fuera S/ 5.00:

```text
Cuota financiera:       S/ 38.10
Cargo diario:           S/  5.00
--------------------------------
Total del vencimiento:  S/ 43.10
```

La regla exacta sobre qué días generan el cargo debe provenir de la configuración de Odoo.

---

# 32. Posible cronograma de pagos en la aplicación móvil

Después de realizar una simulación, la vendedora debe poder seleccionar:

> **Ver posible cronograma de pagos**

Se denomina **posible cronograma** porque en esta etapa todavía se trata de una simulación y no necesariamente de un crédito formalizado.

Odoo debe generar el cronograma. La aplicación únicamente lo presenta.

## Ejemplo conceptual — pago diario

| N° | Fecha estimada | Capital | Interés | Cargo diario | Otros | Total estimado | Saldo |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | 01/10/2026 | calculado | calculado | S/ 5.00 | calculado | calculado | calculado |
| 2 | 02/10/2026 | calculado | calculado | S/ 5.00 | calculado | calculado | calculado |
| 3 | 03/10/2026 | calculado | calculado | S/ 5.00 | calculado | calculado | calculado |
| ... | ... | ... | ... | ... | ... | ... | ... |
| N | fecha final | calculado | calculado | según regla | calculado | calculado | S/ 0.00 |

## Ejemplo conceptual — pago semanal

| N° | Fecha estimada | Capital | Interés | Cargo adicional aplicable | Total estimado | Saldo |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 07/10/2026 | calculado | calculado | calculado por Odoo | calculado | calculado |
| 2 | 14/10/2026 | calculado | calculado | calculado por Odoo | calculado | calculado |
| 3 | 21/10/2026 | calculado | calculado | calculado por Odoo | calculado | calculado |
| ... | ... | ... | ... | ... | ... | ... |

## Ejemplo conceptual — pago mensual

| N° | Fecha estimada | Capital | Interés | Cargo adicional aplicable | Total estimado | Saldo |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 01/11/2026 | calculado | calculado | calculado por Odoo | calculado | calculado |
| 2 | 01/12/2026 | calculado | calculado | calculado por Odoo | calculado | calculado |
| ... | ... | ... | ... | ... | ... | ... |

La forma de acumular o aplicar el cargo diario cuando la frecuencia seleccionada sea semanal o mensual debe ser una regla del plan financiero y no una decisión de la aplicación.

---

# 33. Resumen que verá la vendedora

La vendedora no necesita conocer la configuración interna del plan.

Su flujo seguirá siendo:

```text
Producto
   +
Cuota inicial
   +
Tipo de cuota
(Diario / Semanal / Mensual)
   +
Periodo
        |
        v
      ODOO
        |
        |-- obtiene precio
        |-- obtiene tasa
        |-- obtiene cargo diario configurado
        |-- obtiene gastos
        |-- valida reglas
        |-- calcula cuota
        |-- genera fechas
        |-- genera cronograma
        v
RESULTADO
```

La aplicación puede mostrar:

```text
Producto: TVS DELUXE 200 CC
Inicial: S/ 2,000.00
Modalidad: Semanal
Periodo: 26 meses

Cuota estimada: S/ XXX.XX
Número estimado de pagos: XX
Total estimado: S/ XX,XXX.XX

[ Ver posible cronograma de pagos ]
```

La vendedora **no configura ni introduce el cargo diario**.

---

# 34. Configuración administrativa consolidada

El administrador de Odoo deberá poder manejar desde el plan financiero:

- TEA/tasas.
- Base de días.
- Modalidades Diario/Semanal/Mensual.
- Periodos permitidos.
- Inicial mínima.
- Inicial máxima.
- Productos.
- Gastos.
- ITF.
- Portes.
- Cargo adicional diario.
- Monto del cargo diario.
- Días sobre los que aplica el cargo.
- Domingos cobrables/no cobrables.
- Feriados cobrables/no cobrables.
- Calendario.
- Vigencias.
- Reglas de redondeo.

Ninguno de estos parámetros financieros debe quedar hardcodeado en React Native.

---

# 35. Flujo funcional actualizado

```text
VENDEDORA
   |
   | 1. Selecciona producto
   | 2. Ingresa cuota inicial
   | 3. Selecciona Diario / Semanal / Mensual
   | 4. Selecciona periodo
   v
APP MÓVIL
   |
   | Envía únicamente los datos comerciales
   v
ODOO
   |
   | Obtiene configuración vigente
   | Obtiene cargo diario vigente (ej. S/ 5.00)
   | Valida inicial
   | Obtiene tasa
   | Determina capital
   | Determina calendario
   | Determina cantidad de pagos
   | Calcula cuota
   | Aplica cargos configurados
   | Genera posible cronograma
   | Calcula total
   v
APP MÓVIL
   |
   | Muestra cuota estimada
   | Muestra cantidad de pagos
   | Muestra total
   | Permite ver cronograma
   v
VENDEDORA / CLIENTE
```

## Principio central

La experiencia de la vendedora debe permanecer sencilla:

> **Producto + Inicial + Tipo de cuota + Periodo**

Todo lo demás, incluyendo el **cargo diario configurable actualmente planteado en S/ 5.00**, debe ser resuelto automáticamente por Odoo.

El cronograma mostrado durante la simulación será un **posible cronograma de pagos**. Al formalizarse la operación, las condiciones aplicadas deberán quedar almacenadas para que cambios futuros en la configuración de Odoo no alteren retroactivamente la cotización o financiamiento confirmado.

---

# 36. Generación de PDF del cronograma de pagos

El módulo debe tener la capacidad de generar un **PDF de la simulación** para que la vendedora pueda visualizarlo, compartirlo o entregarlo al cliente.

El PDF debe generarse desde **Odoo**, utilizando exactamente los datos y reglas con los que se realizó la simulación. La aplicación móvil no debe reconstruir el cronograma ni recalcular importes para crear el documento.

## Objetivo

Después de obtener una simulación válida, la app debe disponer de una acción equivalente a:

> **Generar / Ver PDF del cronograma**

La aplicación solicitará el documento a Odoo y Odoo generará el PDF asociado a esa simulación.

## Contenido mínimo del PDF

### Identificación

- Número o código de simulación.
- Fecha y hora de la simulación.
- Estado de la simulación.
- Vendedor/a relacionado.
- Cliente relacionado.

### Información del producto

- Producto.
- Descripción comercial, si corresponde.
- Precio utilizado para la simulación.

### Condiciones de la simulación

- Cuota inicial.
- Capital financiado.
- Tipo de cuota: Diario / Semanal / Mensual.
- Periodo.
- Número estimado de cuotas.
- Monto estimado de la cuota.
- Fecha estimada del primer pago.
- Fecha estimada del último pago.
- Gastos aplicados.
- Cargo diario aplicado internamente.
- Total de intereses.
- Total estimado a pagar.

### Cronograma

El documento debe incluir el posible cronograma:

| N° | Fecha | Capital | Interés | Cargos/Otros | Cuota total | Saldo |
|---:|---|---:|---:|---:|---:|---:|
| 1 | fecha | importe | importe | importe | importe | saldo |
| 2 | fecha | importe | importe | importe | importe | saldo |
| ... | ... | ... | ... | ... | ... | ... |

### Aviso

Como se trata de una simulación, el PDF debe indicar claramente que el cronograma es **referencial/estimado** hasta que la operación sea formalizada.

El texto legal/comercial exacto debe ser configurable o definido por la empresa.

## Identidad visual

El reporte debe poder incorporar:

- Logo de la empresa.
- Razón social.
- Datos comerciales.
- Información de contacto.
- Pie de página.
- Texto de condiciones.

La generación debe realizarse mediante el mecanismo de reportes de Odoo para mantener una única fuente de información.

---

# 37. Persistencia de la simulación

Para poder generar PDFs, relacionar clientes y vendedores y consultar simulaciones anteriores, la simulación debe existir como un registro persistente en Odoo.

Conceptualmente se requiere una entidad:

## Simulación de financiamiento

Debe almacenar una fotografía de los valores utilizados al momento de calcular.

Campos conceptuales:

```text
ID
Código/Número de simulación
Fecha y hora
Estado

Vendedor
Cliente
Producto

Precio utilizado
Cuota inicial
Capital financiado

Tipo de cuota
Periodo
Cantidad de cuotas
Monto de cuota

TEA/tasa utilizada
Cargo diario utilizado
Gastos utilizados

Total intereses
Total gastos
Total estimado

Fecha primer pago
Fecha último pago

Plan financiero utilizado
Versión/condiciones aplicadas

Cronograma
PDF generado
```

La simulación debe conservar los valores utilizados aunque posteriormente se modifique la configuración general del plan financiero.

---

# 38. Relación con vendedor

Cada simulación debe quedar relacionada con el vendedor o vendedora que la creó.

La relación debe realizarse contra un registro previamente existente en Odoo.

Conceptualmente:

```text
Simulación
    |
    +---- Vendedor
```

La app no debe enviar libremente el nombre del vendedor como texto.

Debe trabajar con un identificador reconocido por Odoo, preferiblemente derivado del usuario autenticado.

## Regla recomendada

Cuando la vendedora inicia sesión en la app:

1. Odoo/API identifica al usuario autenticado.
2. Determina el vendedor relacionado.
3. Al crear una simulación, Odoo asigna automáticamente ese vendedor.
4. La vendedora no puede atribuir una simulación a otro vendedor salvo que exista un permiso administrativo específico.

Esto permite:

- Saber quién realizó cada simulación.
- Consultar simulaciones por vendedor.
- Generar estadísticas.
- Realizar seguimiento comercial.
- Evitar suplantación o asignaciones incorrectas.

---

# 39. Relación con cliente

La simulación también debe poder relacionarse con un cliente previamente registrado.

Conceptualmente:

```text
Simulación
    |
    +---- Cliente
```

El cliente debe ser un registro existente en Odoo.

La aplicación debe poder:

1. Buscar clientes autorizados.
2. Seleccionar un cliente.
3. Crear la simulación relacionada con ese cliente.

## Datos de búsqueda

Dependiendo del modelo comercial, la API puede permitir buscar por:

- DNI/documento.
- Nombre.
- Apellidos.
- Teléfono.
- Código interno.

La app debe trabajar con el **ID interno del cliente**, no únicamente con su nombre.

Ejemplo conceptual:

```text
Cliente:
ID: 458
Nombre: Juan Pérez
Documento: XXXXXXXX
```

La simulación guarda:

```text
cliente_id = 458
```

## Creación de clientes

Si la creación de clientes ya existe en la aplicación, se reutilizará ese proceso.

Si se decide permitir crear clientes desde este módulo, debe existir un endpoint independiente para ello y posteriormente utilizar el identificador devuelto para crear la simulación.

---

# 40. Relación general de entidades

La estructura conceptual será:

```text
VENDEDOR
    |
    | crea
    v
SIMULACIÓN -------- CLIENTE
    |
    +-------- PRODUCTO
    |
    +-------- PLAN FINANCIERO
    |
    +-------- MODALIDAD
    |
    +-------- PERIODO
    |
    +-------- CRONOGRAMA
    |
    +-------- PDF
```

Una simulación debe ser trazable hacia:

- Quién la realizó.
- Para qué cliente.
- Para qué producto.
- Qué plan financiero se utilizó.
- Qué configuración estaba vigente.
- Qué cronograma se generó.
- Qué PDF fue entregado.

---

# 41. API REST para la aplicación móvil

El módulo debe exponer una **API REST versionada** para ser consumida por la aplicación móvil.

Ruta base conceptual:

```text
/api/v1/financiamiento/
```

La lógica financiera debe permanecer en Odoo.

La aplicación React Native será un consumidor de servicios.

```text
APP REACT NATIVE
        |
        | HTTPS / JSON
        v
API REST ODOO
        |
        +-- autenticación
        +-- permisos
        +-- clientes
        +-- productos
        +-- configuración disponible
        +-- simulaciones
        +-- cronogramas
        +-- PDFs
        |
        v
MOTOR FINANCIERO ODOO
```

---

# 42. Principios de diseño de la API

La API debe cumplir como mínimo:

- Comunicación mediante HTTPS.
- Formato JSON para solicitudes y respuestas normales.
- Autenticación obligatoria.
- Autorización por usuario/vendedor.
- Versionado de endpoints.
- Validación de parámetros en servidor.
- Manejo uniforme de errores.
- No confiar en cálculos enviados por la app.
- No permitir que la app envíe tasas o cargos internos para determinar el resultado.
- Trazabilidad de creación de simulaciones.
- Protección de datos de clientes.
- PDF entregado únicamente a usuarios autorizados.

La API nunca debe confiar en valores financieros calculados por React Native.

---

# 43. Endpoints conceptuales

Los nombres definitivos pueden ajustarse durante el diseño técnico, pero funcionalmente se requieren los siguientes servicios.

## 43.1 Obtener usuario/vendedor autenticado

```text
GET /api/v1/financiamiento/me
```

Objetivo:

- Identificar usuario autenticado.
- Obtener vendedor relacionado.
- Conocer permisos básicos.

Respuesta conceptual:

```json
{
  "user_id": 10,
  "seller_id": 25,
  "seller_name": "Vendedora"
}
```

---

## 43.2 Listar productos financiables

```text
GET /api/v1/financiamiento/products
```

Debe devolver únicamente productos:

- Activos.
- Disponibles.
- Con plan financiero vigente.
- Autorizados para el vendedor/canal, si existe esa restricción.

La app no necesita recibir fórmulas financieras.

---

## 43.3 Obtener opciones de simulación del producto

```text
GET /api/v1/financiamiento/products/{product_id}/options
```

Objetivo:

Devolver las opciones que la vendedora sí puede seleccionar.

Ejemplo conceptual:

```json
{
  "product_id": 100,
  "price": 25000.00,
  "minimum_down_payment": 2000.00,
  "payment_types": [
    {
      "code": "DAILY",
      "name": "Diario",
      "periods": [12, 18, 24, 26]
    },
    {
      "code": "WEEKLY",
      "name": "Semanal",
      "periods": [12, 18, 24, 26, 36]
    },
    {
      "code": "MONTHLY",
      "name": "Mensual",
      "periods": [12, 18, 24, 26, 36]
    }
  ]
}
```

No es necesario exponer el cargo interno de S/ 5.00 a la vendedora.

---

## 43.4 Buscar clientes

```text
GET /api/v1/financiamiento/customers
```

Parámetros de búsqueda conceptuales:

```text
document
name
phone
```

Debe devolver clientes que el usuario tenga permiso de consultar.

---

## 43.5 Consultar un cliente

```text
GET /api/v1/financiamiento/customers/{customer_id}
```

Permite confirmar la identidad del cliente antes de generar la simulación.

---

## 43.6 Crear una simulación

```text
POST /api/v1/financiamiento/simulations
```

Datos enviados por la app:

```json
{
  "customer_id": 458,
  "product_id": 100,
  "down_payment": 2000.00,
  "payment_type": "WEEKLY",
  "period": 26
}
```

El vendedor **no debería enviarse como un valor libre**.

Odoo debe obtenerlo del usuario autenticado.

Al recibir la solicitud, Odoo debe:

1. Validar usuario.
2. Determinar vendedor.
3. Validar cliente.
4. Validar producto.
5. Obtener precio vigente.
6. Obtener plan financiero.
7. Validar inicial.
8. Validar modalidad.
9. Validar periodo.
10. Obtener tasas.
11. Obtener cargo diario configurable.
12. Obtener gastos.
13. Generar calendario.
14. Calcular cuota.
15. Generar cronograma.
16. Calcular totales.
17. Crear registro de simulación.
18. Devolver resultado.

---

# 44. Respuesta de una simulación

Respuesta conceptual:

```json
{
  "simulation_id": 1250,
  "simulation_number": "SIM-001250",
  "seller": {
    "id": 25,
    "name": "Vendedora"
  },
  "customer": {
    "id": 458,
    "name": "Juan Pérez"
  },
  "product": {
    "id": 100,
    "name": "TVS DELUXE 200 CC"
  },
  "down_payment": 2000.00,
  "financed_amount": 23000.00,
  "payment_type": "WEEKLY",
  "period": 26,
  "number_of_payments": 0,
  "installment_amount": 0.00,
  "total_interest": 0.00,
  "total_expenses": 0.00,
  "total_amount": 0.00,
  "first_payment_date": "YYYY-MM-DD",
  "last_payment_date": "YYYY-MM-DD",
  "status": "simulation"
}
```

Los importes con `0.00` son solamente marcadores conceptuales en esta especificación; el servicio debe devolver los valores calculados por el motor financiero.

---

# 45. Consultar simulación

```text
GET /api/v1/financiamiento/simulations/{simulation_id}
```

Permite recuperar una simulación ya realizada.

Debe validar que el usuario tenga autorización para visualizarla.

---

# 46. Listar simulaciones

```text
GET /api/v1/financiamiento/simulations
```

Filtros conceptuales:

```text
customer_id
product_id
date_from
date_to
status
```

Para una vendedora normal, el servicio debe limitar los resultados a sus propias simulaciones, salvo que las reglas comerciales indiquen otra cosa.

Administradores/supervisores pueden disponer de permisos adicionales.

---

# 47. Obtener cronograma

```text
GET /api/v1/financiamiento/simulations/{simulation_id}/schedule
```

Respuesta conceptual:

```json
{
  "simulation_id": 1250,
  "payment_type": "WEEKLY",
  "number_of_payments": 10,
  "payments": [
    {
      "number": 1,
      "date": "YYYY-MM-DD",
      "principal": 0.00,
      "interest": 0.00,
      "additional_charges": 0.00,
      "payment": 0.00,
      "balance": 0.00
    }
  ]
}
```

El cronograma debe provenir de los datos almacenados/calculados por Odoo.

---

# 48. Obtener PDF

```text
GET /api/v1/financiamiento/simulations/{simulation_id}/pdf
```

Este endpoint debe permitir que la app obtenga el PDF generado por Odoo.

Alternativas técnicas válidas:

- Responder directamente con `application/pdf`.
- Devolver un recurso temporal protegido para descargar el PDF.

La alternativa definitiva debe seleccionarse considerando autenticación, expiración y seguridad.

El PDF nunca debe quedar públicamente accesible mediante una URL permanente sin protección.

---

# 49. Posible endpoint de creación de cliente

Solamente si la app necesita registrar clientes desde este flujo:

```text
POST /api/v1/financiamiento/customers
```

Después de crear el cliente, Odoo devuelve:

```json
{
  "customer_id": 458
}
```

La app utiliza ese ID al crear la simulación.

Si ya existe un API de clientes en la aplicación actual, debe reutilizarse en lugar de duplicar servicios.

---

# 50. Estados de la simulación

Se recomienda definir estados funcionales.

Ejemplo:

```text
Borrador
Simulada
Cotizada
Confirmada
Expirada
Cancelada
```

No todos tienen que implementarse en la primera versión.

Como mínimo debe diferenciarse entre una simulación referencial y una operación confirmada.

---

# 51. Seguridad y permisos

Se deben definir permisos por rol.

## Vendedora

Puede:

- Consultar productos autorizados.
- Buscar/seleccionar clientes autorizados.
- Crear simulaciones.
- Consultar sus simulaciones.
- Ver cronogramas.
- Obtener PDF.

No puede:

- Modificar tasas.
- Modificar cargo diario.
- Modificar reglas financieras.
- Cambiar valores calculados.
- Atribuir arbitrariamente simulaciones a otros vendedores.

## Supervisor

Podría:

- Consultar simulaciones de su equipo.
- Consultar vendedores.
- Revisar cotizaciones.

## Administrador financiero

Puede:

- Configurar planes.
- Configurar tasas.
- Configurar cargo diario.
- Configurar modalidades.
- Configurar periodos.
- Configurar gastos.
- Configurar vigencias.

---

# 52. Reglas de integridad de la API

Cuando la app crea una simulación, **no debe enviar como valores confiables**:

```text
TEA
tasa diaria
tasa semanal
tasa mensual
cargo diario
precio definitivo
capital
intereses
número de cuotas
importe calculado
total
```

Aunque alguno de esos valores se muestre en la interfaz, Odoo debe recalcularlos utilizando su propia configuración.

Los datos principales enviados serán:

```text
customer_id
product_id
down_payment
payment_type
period
```

Y la identidad del vendedor se obtendrá de la autenticación.

---

# 53. Idempotencia y doble envío

La app móvil puede sufrir:

- Mala conexión.
- Reintentos.
- Doble pulsación del botón.
- Timeouts.

Por ello, al implementar la API se debe contemplar un mecanismo para evitar crear dos simulaciones idénticas accidentalmente ante un reintento de la misma operación.

La estrategia técnica concreta puede definirse durante la implementación mediante un identificador de solicitud/idempotencia.

---

# 54. Manejo de errores

La API debe devolver errores estructurados.

Ejemplo conceptual:

```json
{
  "success": false,
  "error": {
    "code": "INVALID_DOWN_PAYMENT",
    "message": "La cuota inicial no cumple las condiciones del plan."
  }
}
```

Posibles códigos:

```text
UNAUTHORIZED
FORBIDDEN
CUSTOMER_NOT_FOUND
PRODUCT_NOT_FOUND
PLAN_NOT_FOUND
PLAN_EXPIRED
INVALID_DOWN_PAYMENT
PAYMENT_TYPE_NOT_ALLOWED
PERIOD_NOT_ALLOWED
SIMULATION_NOT_FOUND
SIMULATION_EXPIRED
PDF_GENERATION_ERROR
```

La app debe mostrar mensajes comprensibles para la vendedora sin exponer detalles internos del servidor.

---

# 55. Flujo completo App → API → Odoo

```text
VENDEDORA
    |
    | Inicia sesión
    v
API / ODOO
    |
    | Identifica usuario y vendedor
    v
APP
    |
    | Selecciona/busca cliente
    | Selecciona producto
    | Ingresa inicial
    | Selecciona tipo de cuota
    | Selecciona periodo
    v
POST /simulations
    |
    v
ODOO
    |
    | Obtiene vendedor autenticado
    | Obtiene cliente
    | Obtiene producto
    | Obtiene plan vigente
    | Obtiene precio
    | Obtiene tasas
    | Obtiene cargo diario configurable
    | Obtiene gastos
    | Valida reglas
    | Calcula financiamiento
    | Genera cronograma
    | Guarda simulación
    v
APP
    |
    | Muestra resultado
    | Muestra posible cronograma
    |
    +---- Ver cronograma
    |
    +---- Generar/Ver PDF
              |
              v
            ODOO
              |
              | Genera PDF
              v
             APP
```

---

# 56. Flujo de PDF

```text
APP
 |
 | GET /simulations/{id}/pdf
 v
ODOO
 |
 | Valida autenticación
 | Valida permisos
 | Obtiene simulación
 | Obtiene vendedor
 | Obtiene cliente
 | Obtiene cronograma
 | Renderiza reporte
 v
PDF
 |
 v
APP MÓVIL
 |
 +-- visualizar
 +-- compartir mediante las capacidades permitidas del dispositivo
```

---

# 57. Auditoría

Cada simulación debería registrar:

- Usuario que la creó.
- Vendedor relacionado.
- Cliente.
- Fecha/hora.
- Plan utilizado.
- Valores financieros utilizados.
- Configuración del cargo diario utilizada.
- Resultado.
- Estado.

También es conveniente registrar eventos relevantes como:

- Confirmación de cotización.
- Cancelación.
- Regeneración del PDF, si se requiere auditoría.

Esto permitirá reconstruir qué condiciones fueron ofrecidas a un cliente en una fecha determinada.

---

# 58. Alcance funcional consolidado del módulo

El módulo deberá cubrir cinco bloques principales:

## A. Configuración financiera

Administrada desde Odoo:

- Productos.
- Planes.
- Tasas.
- Modalidades.
- Periodos.
- Iniciales.
- Gastos.
- Cargo diario configurable.
- Calendarios.
- Vigencias.

## B. Simulación

Entradas de la vendedora:

```text
Cliente
Producto
Cuota inicial
Tipo de cuota
Periodo
```

El vendedor se determina automáticamente por autenticación.

## C. Cronograma

Odoo genera:

- Fechas.
- Capital.
- Intereses.
- Cargos.
- Cuotas.
- Saldos.
- Totales.

La app muestra el **posible cronograma de pagos**.

## D. PDF

Odoo genera un documento asociado a la simulación que contiene:

- Cliente.
- Vendedor.
- Producto.
- Condiciones.
- Cuotas.
- Cronograma.
- Totales.
- Aviso de simulación.

## E. API REST

La aplicación consume servicios para:

- Identidad/vendedor.
- Productos.
- Opciones financieras.
- Clientes.
- Creación de simulación.
- Consulta de simulaciones.
- Cronograma.
- PDF.

---

# 59. Resultado funcional esperado

Desde la perspectiva de la vendedora:

```text
1. Inicia sesión.
2. Busca/selecciona cliente.
3. Selecciona producto.
4. Ingresa cuota inicial.
5. Selecciona Diario / Semanal / Mensual.
6. Selecciona periodo.
7. Presiona Simular.
8. Visualiza cuánto pagaría el cliente.
9. Visualiza el posible cronograma.
10. Puede obtener el PDF del cronograma.
```

Mientras tanto, de forma transparente:

```text
Odoo identifica a la vendedora
Odoo obtiene el cliente
Odoo obtiene el precio
Odoo obtiene el plan
Odoo obtiene la tasa
Odoo obtiene el cargo diario
Odoo aplica las reglas
Odoo calcula las cuotas
Odoo genera el cronograma
Odoo almacena la simulación
Odoo genera el PDF
```

El principio arquitectónico se mantiene:

> **La app captura decisiones comerciales y presenta resultados. Odoo conserva las reglas, realiza los cálculos, genera el cronograma, mantiene la trazabilidad y produce el PDF.**

