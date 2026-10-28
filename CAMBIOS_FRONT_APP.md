# Cambios a implementar en el Front (App móvil)

Resumen de los cambios de backend que requieren ajustes en la app. Todos los endpoints
son JSON-RPC (`POST`, `type='json'`): el cuerpo va dentro de `params`:

```json
{ "jsonrpc": "2.0", "params": { ... } }
```

---

## 1. Simulador de financiamiento (`adt_simulador_prospecto_financiamiento`)

### 1.1 Cuota inicial sugerida por vehículo

`POST /api/simulador/vehiculos` ahora devuelve la cuota inicial configurada en cada producto:

```json
{
  "ok": true,
  "vehiculos": [
    { "id": 1, "nombre": "TVS DELUXE 200CC", "cuota_inicial": 2000.0 },
    { "id": 2, "nombre": "TVS DURAMAX 225CC", "cuota_inicial": 2000.0 }
  ]
}
```

**Qué hacer en el front**

- [ ] Al seleccionar un vehículo, **precargar (pintar)** el campo "Cuota inicial" con `cuota_inicial`.
- [ ] El campo sigue siendo **editable**: el usuario puede cambiarlo antes de calcular.

### 1.2 Cálculo de cuotas

`POST /api/simulador/cuotas`

| Parámetro       | Estado       | Notas |
|-----------------|--------------|-------|
| `vehiculo_id`   | Obligatorio  | Sin cambios. |
| `plazo_meses`   | Obligatorio  | Sin cambios. |
| `cuota_inicial` | **Opcional** | Si se envía, se usa ese valor. Si no se envía (o va vacío), se usa la del vehículo. |
| `cargo_diario`  | **Nuevo, opcional** | Monto fijo por día. Por defecto **5.00**. |
| `cliente_id`, `fecha_inicio`, `frecuencia` | Opcionales | Sin cambios. |

Validaciones del backend (respuesta `{"ok": false, "codigo": "validacion", "error": "..."}`):
- La cuota inicial no puede ser negativa ni mayor o igual al importe a financiar.
- El cargo diario no puede ser negativo.

**Campos nuevos en la respuesta** (también en `simulaciones/listar` y `simulaciones/detalle`):

```json
{
  "cuota_inicial": 2000.0,
  "cargo_diario": 5.0,
  "total_cargo_diario": 3900.0,
  "cuota_mensual": 1293.04,
  "cuota_semanal": 301.71,
  "cuota_diaria": 43.10
}
```

> Las cuotas **ya incluyen** el cargo diario (diaria + 5, semanal + 35, mensual + 150).
> Ejemplo 25,000 / inicial 2,000 / 26 meses: diaria 38.10 → **43.10**.

**Qué hacer en el front**

- [ ] Enviar `cuota_inicial` solo con el valor que muestra el campo (precargado o editado).
- [ ] Mostrar las cuotas tal como llegan (no sumar el cargo en el front).
- [ ] (Opcional) Mostrar "Cargo diario" y "Total cargo diario" en el resultado.
- [ ] No es necesario enviar `cargo_diario` salvo que se quiera un valor distinto de 5.00.

---

## 2. Expedientes (`adt_expedientes`)

### 2.1 Nueva sección: Beneficiario (opcional, al final del expediente)

Campos nuevos, **todos opcionales** (no cuentan para el progreso ni para faltantes):

| Campo                          | Tipo            | Cómo se envía |
|--------------------------------|-----------------|---------------|
| `foto_beneficiario_documento`  | Imagen (base64) | `upload_image` / `upload_image_multipart` |
| `beneficiario_celular`         | Texto           | `expediente/create` o `expediente/update` |
| `beneficiario_parentesco`      | Selección (código) | `expediente/create` o `expediente/update` |

**Subir la foto**

```json
POST /adt_expedientes/mobile/expediente/upload_image
{ "expediente_id": 10, "field_name": "foto_beneficiario_documento", "image_base64": "<base64>" }
```

**Guardar celular y parentesco**

```json
POST /adt_expedientes/mobile/expediente/update
{ "expediente_id": 10, "vals": { "beneficiario_celular": "987654321", "beneficiario_parentesco": "conyuge" } }
```

**Opciones de parentesco (endpoint nuevo)** — usar para llenar el selector, no hardcodear:

```json
POST /adt_expedientes/mobile/expediente/parentesco_options
→ { "success": true, "data": [ { "value": "conyuge", "label": "Cónyuge" }, ... ] }
```

Valores actuales: `conyuge`, `conviviente`, `hijo`, `padre`, `madre`, `hermano`, `abuelo`,
`nieto`, `tio`, `sobrino`, `primo`, `suegro`, `cunado`, `yerno_nuera`, `otro`.
Enviar un valor fuera de la lista devuelve `success: false`.

**Lectura** — `summary_by_asesora` incluye un bloque nuevo por expediente:

```json
"beneficiario": {
  "foto_documento": { "present": true, "state": "aceptado", "obs": "" },
  "celular": { "value": "987654321" },
  "parentesco": { "value": "conyuge", "label": "Cónyuge" }
}
```

En `by_asesora` llegan como `foto_beneficiario_documento_present`, `beneficiario_celular`,
`beneficiario_parentesco`.

**Qué hacer en el front**

- [ ] Agregar la sección "Beneficiario (opcional)" al **final** del flujo del expediente.
- [ ] Foto del documento del beneficiario, celular y selector de parentesco (desde `parentesco_options`).
- [ ] No bloquear el avance ni el envío si la sección está vacía.
- [ ] Mostrar el bloque `beneficiario` en el detalle/resumen del expediente.

### 2.2 Pasaporte deshabilitado

Los clientes extranjeros ahora **solo** registran **Carné de Extranjería** (anverso y reverso).

| Endpoint | Comportamiento nuevo con campos de pasaporte |
|----------|----------------------------------------------|
| `upload_image`, `upload_image_multipart` | Rechaza `foto_pasaporte_*` con error: *"El pasaporte ya no se registra; los clientes extranjeros deben usar Carné de Extranjería."* |
| `set_doc_state` | Rechaza `estado_foto_pasaporte`. |
| `expediente/create`, `expediente/update` | Ignora silenciosamente los campos de pasaporte. |

**Cambios en las respuestas**

- Faltantes (`expediente/progress` y `by_asesora` → `missing`): la clave
  `foto_ce_or_pasaporte` **se renombró a `foto_ce`**.
- `summary_by_asesora` → `identity`: ya **no** vienen `pasaporte_frente` / `pasaporte_reverso`.
  Solo en expedientes antiguos que tenían pasaporte llega (solo lectura):

  ```json
  "identity": {
    "ce_frente": { ... },
    "ce_reverso": { ... },
    "pasaporte_historico": { "frente": { ... }, "reverso": { ... } }
  }
  ```
- El progreso de extranjeros ahora cuenta `foto_ce_frente` y `foto_ce_reverso` (el % puede variar levemente).

**Qué hacer en el front**

- [ ] Quitar la opción / pantalla de carga de **Pasaporte** (anverso y reverso).
- [ ] Para extranjeros, solicitar solo Carné de Extranjería.
- [ ] Actualizar el texto/mapeo del faltante: `foto_ce_or_pasaporte` → `foto_ce`.
- [ ] Dejar de leer `identity.pasaporte_frente` / `identity.pasaporte_reverso`.
- [ ] (Opcional) Si llega `identity.pasaporte_historico`, mostrarlo como solo lectura en expedientes antiguos.

---

## 3. Fotos que salen de costado en el PDF (recomendaciones)

Causa principal: el celular guarda la foto "acostada" con una marca EXIF de rotación. La app la
muestra bien, pero el generador de PDF de Odoo ignora esa marca. La corrección principal se
hará en el backend (enderezar al guardar). **Pendiente de implementar en backend.**

Desde el front se recomienda:

- [ ] **No perder la orientación al comprimir.** Si la app redimensiona/comprime la imagen antes
      de subirla, aplicar primero la rotación EXIF (o conservar el EXIF). Varias librerías borran
      el EXIF sin rotar los píxeles y la foto llega de costado sin forma de corregirla.
- [ ] **Guía de encuadre en la cámara** para documentos (DNI, CE, licencia, documento del
      beneficiario): marco horizontal que obligue a encuadrar el documento derecho.
- [ ] (Opcional) **Vista previa con botón "Rotar"** antes de confirmar la subida.
- [ ] Enviar JPEG con un lado mayor de ~1920 px (reduce peso y tiempo de generación del PDF).

---

## 4. Lista y detalle de capturas (`adt_captura`)

Todo es **aditivo**: las claves que la app ya lee siguen igual.

### 4.1 Lista — `GET /api/adt/captura/mora`

- **Orden:** por defecto `order=monto` (cuotas vencidas + deuda SAT, de mayor a menor). `order=dias` sigue disponible.
- **Filtro por estado de la deuda:** `source_type=mora` (solo cronograma), `papeleta` (solo papeleta SAT),
  `ambos`, o varios separados por coma (`mora,ambos`). También acepta `cronograma` y `sat`.
- **Nuevo `estados_deuda`:** cantidad por estado, calculada con los demás filtros, para pintar los chips:
  `[{key: "todos"|"mora"|"papeleta"|"ambos", label, count}]`.
- **Por registro:**
  - `estado_deuda`: texto del estado.
  - `papeletas`: las papeletas SAT pendientes, cada una con `estado_pago`, `estado_sat`, `deuda`,
    `fecha_emision`, `codigo_falta`, `url_copia_sat` e `imagenes`.
  - `client`: ahora también trae `documento`, `telefono`, `celular`, `email` y `direccion`.

### 4.2 Detalle — `GET /api/adt/captura/mora/detail?cuenta_id=` (o `?vehicle_id=`)

Claves nuevas en `record`:

- `deuda`: estado, cronograma (monto, cuotas, días, cuota más antigua), papeletas SAT (cantidad, deuda) y total.
- `contacto`: datos personales, domicilio (y el del expediente), `referencias`, `imagen_dni` y sus otras `cuentas`.
- `gps`: `registrado`, `estado`, `sin_senal`, `ultimo_reporte`, `horas_sin_reporte`, ubicación, `mapa_url`, batería, IMEI.
  Si `registrado` es `false`, el vehículo no tiene equipo.
- `refinanciamientos`: `total` y `registros`. Cada registro trae fecha, cuotas, monto, pagadas, retrasadas y saldo.
- `capturas`: todas las capturas del vehículo o la cuenta. Cada una trae los datos de cada paso
  (`captura`, `cobro`, `decision`, `recolocacion`), con sus archivos e `historial`.
- `papeletas`: todas las papeletas SAT del vehículo, con `imagenes`. Lo mismo devuelve `/detail/papeletas`.

### 4.3 Archivos (imágenes, voucher, evidencias)

Cada archivo llega como `{nombre, mimetype, es_imagen, es_video, tamano, url, expira}`. La `url`
(`/api/adt/adjunto/<id>?expira=&firma=`) abre el archivo sin sesión y **vence a las 24 h**. Si responde 410,
hay que volver a pedir la lista o el detalle. Para forzar la descarga se agrega `&descargar=1`.

Las fechas con hora vienen en ISO con zona UTC (`...+00:00`): convertir a hora de Lima al mostrar.

---

## Checklist rápido

- [ ] Simulador: precargar cuota inicial desde `/api/simulador/vehiculos` (editable).
- [ ] Simulador: enviar `cuota_inicial` del campo; mostrar cuotas con cargo diario incluido.
- [ ] Expediente: sección Beneficiario (foto, celular, parentesco) al final, opcional.
- [ ] Expediente: selector de parentesco desde `parentesco_options`.
- [ ] Expediente: quitar Pasaporte; extranjeros solo CE.
- [ ] Expediente: renombrar faltante `foto_ce_or_pasaporte` → `foto_ce`.
- [ ] Fotos: conservar orientación al comprimir + guía de encuadre.
- [ ] Capturas: chips de `estados_deuda`, papeletas con imagen en la lista y detalle (contacto, GPS, refinanciamientos, capturas).
