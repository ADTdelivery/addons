# Lógica de Visibilidad de Campos — Módulo Expediente

## Criterios de Bifurcación

La visibilidad de los campos del expediente se determina por dos criterios principales del cliente:

1. **Nacionalidad** — si el cliente es peruano o extranjero
2. **Ocupación** — si el cliente es mototaxista o no mototaxista

Hay un tercer criterio transversal: el tipo de vivienda (alquilada o propia/familiar).

---

## 1. Campos por Nacionalidad

### Persona Peruana

Se solicita el Documento Nacional de Identidad (DNI), que tiene anverso y reverso.

| Campo | Descripción |
|-------|-------------|
| DNI Anverso | Foto del frente del DNI |
| DNI Reverso | Foto del reverso del DNI |
| Estado DNI | Indica si el documento fue aceptado o rechazado |
| Observaciones DNI | Razón del rechazo (aparece solo si el estado es "rechazado") |

---

### Persona Extranjera

Para extranjeros se admiten dos tipos de documento de identidad: Carnet de Extranjería (CE) o Pasaporte. Ambos bloques se muestran para que se suba el que corresponda.

#### Carnet de Extranjería

| Campo | Descripción |
|-------|-------------|
| CE Anverso | Foto del frente del Carnet de Extranjería |
| CE Reverso | Foto del reverso del Carnet de Extranjería |
| Estado CE | Indica si el documento fue aceptado o rechazado |
| Observaciones CE | Razón del rechazo (aparece solo si el estado es "rechazado") |

#### Pasaporte

| Campo | Descripción |
|-------|-------------|
| Pasaporte Anverso | Foto del frente del pasaporte |
| Pasaporte Reverso | Foto del reverso del pasaporte |
| Estado Pasaporte | Indica si el documento fue aceptado o rechazado |
| Observaciones Pasaporte | Razón del rechazo (aparece solo si el estado es "rechazado") |

---

## 2. Campos por Ocupación

### Mototaxista

Se solicitan documentos propios del vehículo y datos laborales relacionados con la actividad de mototaxi.

| Campo | Descripción |
|-------|-------------|
| Foto en la moto | Foto del cliente sobre su moto |
| Estado (Foto en moto) | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| SOAT | Foto del documento de seguro obligatorio |
| Estado SOAT | Aceptado o rechazado |
| Observaciones SOAT | Razón del rechazo |
| Tarjeta de Propiedad (Frente) | Foto del frente del documento de propiedad de la moto |
| Tarjeta de Propiedad (Reverso) | Foto del reverso del documento de propiedad de la moto |
| Estado Tarjeta de Propiedad | Aceptado o rechazado |
| Observaciones Tarjeta | Razón del rechazo |
| Ganancia diaria / mensual | Ingreso estimado del mototaxista |
| Tiempo trabajando | Antigüedad en la actividad |
| Empresa asociada | Empresa para la que trabaja (si aplica) |
| Moto propia o alquilada | Indica si la moto es propia o alquilada |

---

### No Mototaxista

Se solicitan documentos que acrediten el lugar de trabajo e ingresos del cliente en otro tipo de actividad.

| Campo | Descripción |
|-------|-------------|
| Lugar de trabajo | Foto del sitio donde trabaja el cliente |
| Estado (Lugar de trabajo) | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| Lugar del negocio | Foto del local comercial o negocio del cliente |
| Estado (Lugar del negocio) | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| Boletas / Contrato / Recibos | Comprobantes de ingresos o relación laboral |
| Estado (Boletas) | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| Estado de cuenta | Extracto bancario o financiero |
| Estado (Estado de cuenta) | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| Ganancia diaria / mensual | Ingreso estimado del cliente |
| Tiempo trabajando | Antigüedad en la actividad o empleo |

---

## 3. Campos por Tipo de Vivienda

Este criterio es independiente de la nacionalidad y la ocupación.

### Vivienda Alquilada

Cuando el cliente declara que su vivienda es alquilada, se habilitan campos adicionales para sustentar la situación habitacional.

| Campo | Descripción |
|-------|-------------|
| Número del dueño / contacto | Teléfono del propietario del inmueble |
| Contrato de alquiler | Foto del contrato de arrendamiento |
| Estado (Contrato) | Aceptado o rechazado |
| Observaciones Contrato | Razón del rechazo |

### Vivienda Propia o Familiar

No se solicitan documentos adicionales de vivienda.

---

## 4. Campos Comunes (Siempre Visibles)

Estos campos se muestran para todos los clientes, independientemente de su nacionalidad u ocupación.

### Datos Generales

| Campo | Descripción |
|-------|-------------|
| Cliente | Nombre del cliente vinculado al expediente |
| Asesora | Asesora responsable |
| Fecha | Fecha de creación del expediente |
| Vehículo | Tipo de vehículo de interés |
| Nacionalidad | Nacionalidad del cliente (referencial) |
| Ocupación | Ocupación del cliente (referencial) |

### Documentos de Identidad (Sección Compartida)

La sección de documentos de identidad bifurca según la nacionalidad (ver sección 1).

### Licencia

| Campo | Descripción |
|-------|-------------|
| Licencia | Foto de la licencia de conducir |
| Estado Licencia | Aceptado o rechazado |
| Observaciones | Razón del rechazo |

### Domicilio

| Campo | Descripción |
|-------|-------------|
| Recibo de luz o agua | Foto del recibo domiciliario |
| Estado Recibo | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| Tipo de vivienda | Alquilada, propia o familiar |
| Tiempo viviendo allí | Antigüedad en el domicilio actual |
| Ubicación (foto) | Foto de la ubicación del domicilio |
| Estado Ubicación | Aceptado o rechazado |
| Observaciones | Razón del rechazo |
| Fachada del domicilio | Foto exterior del domicilio |
| Estado Fachada | Aceptado o rechazado |
| Observaciones | Razón del rechazo |

Los campos de contrato de alquiler y contacto del propietario aparecen solo si el tipo de vivienda es "alquilada" (ver sección 3).

### Sentinel (Evaluación Crediticia)

| Campo | Descripción |
|-------|-------------|
| Sentinel - Score | Captura del puntaje Sentinel |
| Sentinel - Deudas | Captura del detalle de deudas en Sentinel |
| Estado Sentinel | Aceptado o rechazado |
| Observaciones | Razón del rechazo |

### Referencias Personales

Se registran hasta cuatro referencias personales. Cada una incluye nombre, teléfono y vínculo con el cliente.

| Campo | Descripción |
|-------|-------------|
| Referencia 1 a 4 | Nombre, teléfono y vínculo de cada referencia |
| Estado Referencias | Aceptado o rechazado |
| Observaciones | Razón del rechazo |

### Fase Final (Entrega)

| Campo | Descripción |
|-------|-------------|
| Foto con el cliente | Foto tomada en el momento de la entrega |
| Placa | Número de placa del vehículo entregado |
| Chasis | Número de chasis del vehículo entregado |

---

## 5. Patrón de Observaciones

Todos los bloques documentales siguen el mismo patrón:

- Se sube el documento (foto).
- Se asigna un estado: **aceptado** o **rechazado**.
- El campo de observaciones **solo aparece cuando el estado es "rechazado"**, para que el revisor explique el motivo.

---

## Resumen Visual de Bifurcaciones

```
EXPEDIENTE
├── Nacionalidad
│   ├── Peruana → DNI (anverso + reverso)
│   └── Extranjera → CE (anverso + reverso) + Pasaporte (anverso + reverso)
│
├── Ocupación
│   ├── Mototaxista → Foto en moto + SOAT + Tarjeta de propiedad + datos laborales moto
│   └── No mototaxista → Lugar de trabajo + Lugar de negocio + Boletas + Estado de cuenta + datos laborales
│
└── Tipo de Vivienda
    ├── Alquilada → Contacto del dueño + Contrato de alquiler
    └── Propia / Familiar → (sin campos adicionales)
```
