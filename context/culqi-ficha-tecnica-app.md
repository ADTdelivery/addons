# Ficha técnica de la aplicación — para consultor Culqi

> Documento de referencia con los datos técnicos de **nuestra** app, listo para responder preguntas del consultor de Culqi durante el onboarding/integración. Completar los campos marcados `[COMPLETAR]` antes de la reunión.

## 1. Plataforma y tipo de aplicación

| Campo | Valor |
|---|---|
| Tipo de app | Backend web (ERP), sin app móvil nativa involucrada en el flujo de pago |
| Framework | Odoo (ERP open source) |
| Versión de Odoo | 15.0 (mayoría de módulos custom en `15.0.x.y.z`; hay 1 módulo en migración a `16.0.1.0.0` — `[CONFIRMAR cuál y estado de la migración]`) |
| Lenguaje backend | Python |
| Versión de Python | `[COMPLETAR — ej. 3.8 / 3.10, confirmar en el contenedor con `python3 --version`]` (local dev: 3.9.6) |
| Frontend del checkout de pago | `[COMPLETAR — se definirá según modalidad elegida: vista Owl/QWeb dentro de Odoo, o página standalone servida aparte]` |
| Base de datos | PostgreSQL `[COMPLETAR versión]` |
| Gestor de dependencias Python | `pip` + `requirements.txt` por módulo (no hay un `requirements.txt` global unificado; cada addon declara sus libs, ej. `requests>=2.28.0`) |
| Inyección de dependencias | No aplica un framework de DI (tipo Hilt/Spring). Odoo resuelve todo vía su **ORM** (herencia de modelos `_inherit`/`_name`) y registro de módulos en `__manifest__.py`; los "servicios" externos (como el cliente HTTP a Culqi) se implementarían como una clase/helper Python importado directamente o un modelo de Odoo (`ir.config_parameter` para config, `models.AbstractModel` para el servicio) |
| Módulo/addon dedicado a pagos | `[COMPLETAR — nombre del addon nuevo o existente donde se integrará Culqi, ej. `adt_pagos_culqi`]` |

## 2. Infraestructura y despliegue

| Campo | Valor |
|---|---|
| Proveedor cloud | AWS |
| Cómputo | EC2, IP pública **fija** (Elastic IP) |
| Contenerización | Docker (la app corre dentro de un contenedor) |
| Imagen base del contenedor | `[COMPLETAR — ej. odoo:15.0 oficial, o imagen custom]` |
| Orquestación | `[COMPLETAR — docker run manual / docker-compose / otro]` |
| Servidor de aplicación | Odoo (servidor WSGI/gevent embebido) |
| Proxy reverso delante del contenedor | `[COMPLETAR — ¿hay Nginx/Apache/ALB delante, o el puerto de Odoo (8069) se expone directo?]` |
| `proxy_mode` de Odoo | `[COMPLETAR — activado/desactivado según exista proxy]` |
| Puertos expuestos | `[COMPLETAR — ej. 8069 HTTP, 8072 longpolling]` |
| **HTTPS/TLS** | **No configurado actualmente** — la app corre solo sobre HTTP en la IP pública |
| Dominio asociado | `[COMPLETAR — ¿existe dominio disponible para emitir certificado, o solo se usa la IP?]` |
| Certificado TLS | No existe aún (pendiente de definir: Let's Encrypt vía proxy, ACM + ALB, u otro) |
| mTLS (autenticación mutua cliente-servidor) | No implementado. La llamada a Culqi sería **saliente** (server-to-server, TLS estándar del lado cliente); no se prevé mTLS salvo que Culqi lo exija explícitamente para webhooks |
| Ambientes | `[COMPLETAR — ¿existen ambientes separados de prod/staging/dev, o solo hay un servidor único?]` |
| Backups | `[COMPLETAR — política de backup de BD/contenedor]` |

## 3. Seguridad y manejo de datos

| Campo | Valor |
|---|---|
| Autenticación de usuarios finales | Login nativo de Odoo (usuario/password), `[COMPLETAR si hay SSO/2FA]` |
| Gestión de secretos (API keys) | `[COMPLETAR — variables de entorno del contenedor, `ir.config_parameter` cifrado, secret manager, etc.]` |
| Almacenamiento de datos de tarjeta | **No se prevé almacenar PAN/CVV.** La intención es usar tokenización de Culqi (Tokens.js) para no manejar datos sensibles de tarjeta en nuestro servidor |
| Alcance PCI-DSS esperado | SAQ A (si se usa Tokens.js/checkout embebido sin tocar el PAN en backend) — `[CONFIRMAR con Culqi]` |
| Logging | `[COMPLETAR — a dónde van los logs de Odoo (stdout del contenedor, archivo, CloudWatch), y si se filtran datos sensibles]` |
| Cifrado en tránsito (llamadas salientes a Culqi) | TLS estándar vía `requests`/`urllib3` de Python (soporta TLS 1.2+) |
| Cifrado en reposo (BD) | `[COMPLETAR — ¿el volumen EBS/RDS está cifrado?]` |
| WAF / rate limiting | `[COMPLETAR — si existe algo delante del EC2 (Cloudflare, ALB+WAF, Security Groups)]` |
| Grupo de seguridad EC2 (firewall) | `[COMPLETAR — puertos abiertos, IPs permitidas de entrada/salida]` |

## 4. Integración prevista con Culqi

| Campo | Valor |
|---|---|
| Modalidad de integración | `[COMPLETAR una vez definida con el consultor — Checkout/Tokens.js vs API directa]` |
| Componente que llama a la API de Culqi | Backend Odoo (Python), llamada server-side saliente con `requests` |
| Componente que captura el token de tarjeta | `[COMPLETAR — frontend embebido en la vista de Odoo, o página externa]` |
| Endpoint que recibirá webhooks de Culqi | `[COMPLETAR — URL pública, hoy inexistente por falta de HTTPS]` |
| Moneda(s) a procesar | `[COMPLETAR — PEN / USD]` |
| Volumen estimado de transacciones | `[COMPLETAR]` |
| Casos de uso del cobro | `[COMPLETAR — ej. pago de cuota de crédito/leasing vehicular, servicios ADT, etc.]` |

## 5. Contactos y responsables

| Rol | Nombre / contacto |
|---|---|
| Responsable técnico (infra/EC2/Docker) | `[COMPLETAR]` |
| Responsable de la integración (backend Odoo) | `[COMPLETAR]` |
| Responsable comercial/legal (alta como comercio) | `[COMPLETAR]` |

---

### Pendientes antes de la reunión con Culqi

- [ ] Confirmar versión exacta de Python y PostgreSQL en el contenedor productivo.
- [ ] Confirmar si hay proxy reverso o el puerto de Odoo está expuesto directo en el Security Group.
- [ ] Decidir si se habilitará dominio + certificado TLS antes de la integración (muy probablemente obligatorio).
- [ ] Definir el addon/módulo Odoo donde vivirá la integración de pagos.
- [ ] Definir dónde se guardará la `secret_key` de Culqi de forma segura.

> Ver también: [[culqi-preguntas-tecnicas-consultor]] (preguntas a hacerle al consultor de Culqi).
