# Culqi — Preguntas técnicas para el consultor de integración

## Contexto actual de la infraestructura

- Aplicación desplegada en **AWS EC2** con **IP pública fija**.
- Corre dentro de **contenedor Docker**.
- **Sin HTTPS** actualmente (solo HTTP, sin dominio ni certificado TLS asociado).
- Stack: Odoo (módulos custom en `addons/`).

Esto es relevante porque Culqi generalmente exige HTTPS para:
- El checkout / Tokens.js (captura de tarjeta en el navegador del cliente).
- La recepción de webhooks/notificaciones.
- El uso en modo producción (llaves `pk_live_` / `sk_live_`).

---

## 1. Requisitos de conectividad y certificado

- ¿Es obligatorio HTTPS para poder usar las llaves de **producción** (`sk_live_` / `pk_live_`), o solo para el checkout embebido (Tokens.js)?
- ¿Culqi certifica o valida el dominio/IP antes de habilitar producción? ¿Cuál es el proceso (checklist, revisión manual, sandbox previo)?
- ¿Aceptan integración vía **IP fija sin dominio**, o es obligatorio contar con un dominio (para emitir certificado TLS, ej. Let's Encrypt)?
- ¿Hay requisito de **whitelisting de IP saliente** (la IP del EC2 que llamará a la API de Culqi) o de IP entrante (para webhooks)?
- ¿La comunicación debe hacerse solo a través de sus dominios oficiales (`api.culqi.com`, `checkout.culqi.com`, `secure.culqi.com`), o existen endpoints regionales/alternativos?

## 2. Modelo de integración (Checkout vs API directa)

- ¿Qué modalidad recomiendan para este caso: **Checkout de Culqi (redirección/modal con Tokens.js)** o **integración vía API + captura propia del formulario de tarjeta**?
- Si se usa **Tokens.js** (captura de tarjeta en frontend): ¿los datos de tarjeta pasan por nuestro servidor en algún momento, o van directo del navegador del cliente a Culqi (evitando alcance PCI-DSS)?
- ¿Existe SDK/librería oficial para backend (Node, PHP, Python) o se integra por REST directo? (el stack actual es Odoo/Python).
- ¿Cuál es el flujo recomendado para **suscripciones / cobros recurrentes**, si aplica a futuro?

## 3. Autenticación y llaves

- ¿Cómo se gestionan los ambientes: **test** vs **producción**? ¿Las llaves `pk_test_/sk_test_` y `pk_live_/sk_live_` son independientes por comercio o por cada integración?
- ¿Existe rotación periódica obligatoria de `secret_key`, o solo se rota ante incidente?
- ¿Cómo se recomienda almacenar la `secret_key` en un entorno Docker/EC2 (variables de entorno, secret manager, etc.) según sus lineamientos de seguridad?

## 4. Webhooks / notificaciones

- ¿Culqi envía **webhooks** (eventos de cargo, contracargo, reembolso) o el modelo es solo request/response síncrono al crear el cargo?
- Si hay webhooks: ¿qué eventos existen (`charge.creation.succeeded`, `charge.creation.failed`, `refund`, `chargeback`, etc.)?
- ¿Los webhooks requieren endpoint HTTPS **público**? ¿Aceptan un endpoint HTTP durante pruebas o sandbox?
- ¿Cómo se valida la autenticidad del webhook (firma HMAC, IP de origen, header secreto)?
- ¿Hay reintentos automáticos si nuestro endpoint responde error o timeout? ¿Cuántos y con qué backoff?

## 5. Seguridad y cumplimiento PCI-DSS

- ¿Qué nivel de responsabilidad PCI-DSS recae en nuestro servidor si usamos Tokens.js (SAQ A) vs si manejamos el número de tarjeta directamente (SAQ D)?
- ¿Exigen algún cuestionario de seguridad (SAQ) o certificación previa para habilitar producción?
- ¿Hay restricciones sobre **loggear** datos de tarjeta, token, CVV, etc.? ¿Qué campos de la respuesta son seguros de almacenar en nuestra base de datos (Odoo)?
- ¿Requieren cifrado en tránsito TLS 1.2+ mínimo? ¿Alguna versión de cifrado o cipher suite específica que rechacen?

## 6. Flujo de pago y manejo de errores

- ¿Cuál es el flujo exacto: `token` (frontend) → `cargo` (backend, `POST /v2/charges`) → confirmación?
- ¿Soportan **3D Secure / autenticación adicional**? ¿Es obligatorio para todas las tarjetas o solo algunas (regulación BCRP/Reyes en Perú)?
- ¿Qué códigos de error / declinaciones debemos mapear (fondos insuficientes, tarjeta bloqueada, antifraude, etc.)?
- ¿Manejan **antifraude propio** (score, reglas) que pueda rechazar transacciones sin intervención nuestra?
- ¿Cuál es el timeout recomendado para las llamadas a su API desde nuestro backend?

## 7. Monedas, montos y comisiones

- ¿Qué monedas soportan (PEN, USD, ambas simultáneamente)?
- ¿Formato de monto esperado (céntimos/enteros)?
- ¿Cuál es la estructura de comisión (% + fijo), y si varía por tipo de tarjeta (crédito/débito) o por método (Yape, otros).
- ¿Manejan otros métodos de pago además de tarjeta (Yape, PagoEfectivo, transferencia) que interese integrar en el mismo flujo?

## 8. Reembolsos y contracargos

- ¿Los reembolsos se hacen vía API (`POST /v2/refunds`) o requieren gestión manual desde su panel?
- ¿Reembolsos parciales soportados?
- ¿Cuál es el proceso ante un **contracargo (chargeback)**: notificación, plazo de respuesta, evidencia requerida?

## 9. Ambiente de pruebas (sandbox)

- ¿Tarjetas de prueba disponibles y sus escenarios (aprobado, rechazado, fondos insuficientes)?
- ¿El sandbox de Culqi tiene los mismos requisitos de HTTPS que producción, o se puede probar sobre HTTP/localhost/IP sin certificado?
- ¿Hay un panel de pruebas para simular webhooks manualmente?

## 10. Liquidación y conciliación

- ¿Cuál es el ciclo de liquidación (T+1, T+2, semanal) y a qué cuenta bancaria se acredita?
- ¿Proveen reportes/API para conciliar transacciones (listado de cargos, exportables, reportería)?
- ¿Existe ambiente de **panel administrativo** (dashboard Culqi) para ver transacciones en tiempo real?

## 11. Alta como comercio / onboarding

- ¿Qué documentación legal/comercial se requiere para habilitar la cuenta en modo producción (RUC, representante legal, cuenta bancaria)?
- ¿Cuánto tiempo toma la aprobación para pasar de test a producción?
- ¿Hay límites de monto/transacciones mientras la cuenta está en revisión inicial?

---

## Notas para nuestro equipo (a resolver internamente antes/durante la reunión)

- [ ] Definir si se habilita HTTPS en el EC2 (dominio + certificado, ej. Nginx reverse proxy + Let's Encrypt) — probablemente será requisito no negociable de Culqi.
- [ ] Confirmar si el checkout se hace client-side (Tokens.js) para reducir alcance PCI, dado que hoy no hay HTTPS.
- [ ] Validar si el contenedor Docker actual expone puertos directamente o hay un proxy/load balancer delante que se pueda usar para terminar TLS.
- [ ] Revisar cómo se gestionan hoy los secretos/variables de entorno en el contenedor, para definir dónde vivirá la `secret_key` de Culqi.
