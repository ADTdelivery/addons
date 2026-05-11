from datetime import date, timedelta
import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

DIAS_ALERTA_DEFAULT = 3


class ADTComercialNotificacionesCron(models.Model):
    """
    Extiende adt.comercial.cuentas para agregar la lógica del cron diario
    de notificaciones de cuotas próximas a vencer y vencidas.

    Parámetros configurables en Ajustes > Parámetros del sistema:
        - adt_comercial.dias_alerta_cuotas        (default: 3)    → ventana de días próximos
        - adt_comercial.notificaciones_endpoint   (default: "")   → URL del servicio externo
    """

    _inherit = "adt.comercial.cuentas"

    # ─────────────────────────────────────────────────────────────
    # Punto de entrada del cron
    # ─────────────────────────────────────────────────────────────

    @api.model
    def cron_notificar_cuotas(self, log_only=False):
        """
        Ejecutado diariamente a las 8:00 PM hora Lima (01:00 UTC).

        Casos contemplados:
          1. Cuota próxima a vencer (sin cuotas atrasadas ni mora).
          2. Cuota próxima a vencer + cuota(s) atrasada(s) y/o mora pendiente.
        """
        hoy = date.today()

        dias_alerta = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("adt_comercial.dias_alerta_cuotas", DIAS_ALERTA_DEFAULT)
        )
        fecha_limite = hoy + timedelta(days=dias_alerta)

        cuentas = self.env["adt.comercial.cuentas"].sudo().search(
            [("state", "in", ["aprobado", "en_curso"])]
        )

        notificaciones = []

        for cuenta in cuentas:
            cuotas_activas = cuenta.cuota_ids.filtered(
                lambda c: c.type == "cuota" and c.state not in ("pagado", "anulada")
            )

            # Cuotas con vencimiento pasado
            retrasadas = cuotas_activas.filtered(lambda c: c.state == "retrasado")

            # Cuotas cuyo vencimiento cae dentro de la ventana de alerta
            proximas = cuotas_activas.filtered(
                lambda c: c.state == "pendiente"
                and c.fecha_cronograma
                and hoy <= c.fecha_cronograma <= fecha_limite
            )

            if not proximas:
                continue

            mora_pendiente_total = sum(cuenta.cuota_ids.mapped("mora_pendiente"))
            tiene_mora = mora_pendiente_total > 0.0
            tiene_retrasadas = bool(retrasadas)

            for cuota_proxima in proximas:
                dias_para_vencer = (cuota_proxima.fecha_cronograma - hoy).days

                if not tiene_retrasadas and not tiene_mora:
                    # ── CASO 1: Cuota próxima, sin deuda previa ──────────────
                    titulo = "⏰ Cuota próxima a vencer"
                    cuerpo = (
                        f"Hola {cuenta.partner_id.name or 'cliente'}, "
                        f"tu cuota {cuota_proxima.name} de S/ {cuota_proxima.monto:.2f} "
                        f"vence en {dias_para_vencer} día(s) "
                        f"({cuota_proxima.fecha_cronograma.strftime('%d/%m/%Y')}). "
                        f"Por favor realiza tu pago a tiempo."
                    )
                    tipo = "PROXIMA_A_VENCER"

                else:
                    # ── CASO 2: Próxima + retrasadas y/o mora ─────────────────
                    partes = []
                    if tiene_retrasadas:
                        total_retrasado = sum(retrasadas.mapped("saldo"))
                        partes.append(
                            f"{len(retrasadas)} cuota(s) vencida(s) por S/ {total_retrasado:.2f}"
                        )
                    if tiene_mora:
                        partes.append(
                            f"mora pendiente de S/ {mora_pendiente_total:.2f}"
                        )

                    titulo = "🚨 Cuotas vencidas y próxima a vencer"
                    cuerpo = (
                        f"Hola {cuenta.partner_id.name or 'cliente'}, "
                        f"tienes {', '.join(partes)}. "
                        f"Además, tu cuota {cuota_proxima.name} de S/ {cuota_proxima.monto:.2f} "
                        f"vence en {dias_para_vencer} día(s) "
                        f"({cuota_proxima.fecha_cronograma.strftime('%d/%m/%Y')}). "
                        f"Regulariza tu situación cuanto antes."
                    )
                    tipo = "PROXIMA_CON_DEUDA"

                data_payload = self._build_data_payload(
                    cuenta=cuenta,
                    cuota_proxima=cuota_proxima,
                    retrasadas=retrasadas,
                    mora_pendiente_total=mora_pendiente_total,
                    dias_para_vencer=dias_para_vencer,
                    tipo=tipo,
                )

                notificacion = {
                    "title": titulo,
                    "body": cuerpo,
                    "data": data_payload,
                }

                # Persistir notificacion para que la app la recupere desde /v1/notifications.
                self._guardar_notificacion_mobile(cuenta=cuenta, payload=notificacion)

                notificaciones.append(notificacion)
                self._enviar_notificacion(notificacion, log_only=log_only)

        _logger.info(
            "[ADT Cron] Notificaciones de cuotas generadas: %d | Fecha: %s | Ventana: %d días",
            len(notificaciones),
            hoy.isoformat(),
            dias_alerta,
        )

        return notificaciones

    def action_test_cron_notificaciones(self):
        """
        Botón de prueba manual del cron (solo para administradores).
        Ejecuta la lógica completa y prueba el flujo real de envío al endpoint /send.
        """
        # Ejecuta envio real para validar el flujo completo hacia el servicio de notificaciones.
        payloads = self.env["adt.comercial.cuentas"].cron_notificar_cuotas(log_only=False)

        # Log detallado para validar exactamente el mensaje que se enviaria.
        for payload in payloads:
            _logger.info(
                "[ADT Test Notificacion] title=%s | body=%s | data=%s",
                payload.get("title"),
                payload.get("body"),
                json.dumps(payload.get("data", {}), ensure_ascii=False, default=str),
            )

        if not payloads:
            mensaje = (
                "✅ El cron se ejecutó correctamente.\n\n"
                "No se encontraron cuentas con cuotas próximas a vencer "
                f"en los próximos {DIAS_ALERTA_DEFAULT} días."
            )
        else:
            lineas = []
            for p in payloads:
                d = p.get("data", {})
                lineas.append(
                    f"• [{d.get('tipo')}] {d.get('partner_name')} "
                    f"| Ref: {d.get('referencia')} "
                    f"| {p.get('title')}"
                )
            mensaje = (
                f"✅ Cron ejecutado. {len(payloads)} notificación(es) generada(s):\n\n"
                + "\n".join(lineas)
                + "\n\nSe ejecutó el envío real al endpoint configurado. Revisa los logs para validar respuesta del servicio."
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Test: Cron de Notificaciones",
                "message": mensaje,
                "type": "success" if payloads else "warning",
                "sticky": True,
            },
        }

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _build_data_payload(
        self,
        cuenta,
        cuota_proxima,
        retrasadas,
        mora_pendiente_total,
        dias_para_vencer,
        tipo,
    ):
        """
        Construye el bloque 'data' del payload de notificación.

        Estructura:
        {
            "tipo": "PROXIMA_A_VENCER" | "PROXIMA_CON_DEUDA",
            "cuenta_id": int,
            "referencia": str,
            "partner_id": int,
            "partner_name": str,
            "mobile": str,
            "cuota_proxima": { id, name, monto, fecha_vencimiento, dias_para_vencer, saldo },
            "cuotas_retrasadas": [ { id, name, monto, saldo, fecha_vencimiento } ],
            "mora_pendiente_total": float,
            "mora_dias_total": int,
        }
        """
        return {
            "tipo": tipo,
            "cuenta_id": cuenta.id,
            "referencia": cuenta.reference_no or "",
            "partner_id": cuenta.partner_id.id if cuenta.partner_id else None,
            "partner_name": cuenta.partner_id.name if cuenta.partner_id else "",
            "mobile": cuenta.mobile or "",
            "cuota_proxima": {
                "id": cuota_proxima.id,
                "name": cuota_proxima.name or "",
                "monto": cuota_proxima.monto,
                "fecha_vencimiento": cuota_proxima.fecha_cronograma.isoformat()
                if cuota_proxima.fecha_cronograma
                else None,
                "dias_para_vencer": dias_para_vencer,
                "saldo": cuota_proxima.saldo,
            },
            "cuotas_retrasadas": [
                {
                    "id": c.id,
                    "name": c.name or "",
                    "monto": c.monto,
                    "saldo": c.saldo,
                    "fecha_vencimiento": c.fecha_cronograma.isoformat()
                    if c.fecha_cronograma
                    else None,
                    "mora_pendiente": c.mora_pendiente,
                    "mora_dias": c.mora_dias,
                }
                for c in retrasadas
            ],
            "mora_pendiente_total": mora_pendiente_total,
            "mora_dias_total": cuenta.mora_dias_total,
        }

    def _guardar_notificacion_mobile(self, cuenta, payload):
        """
        Registra la notificación generada por el cron en mobile.notification.
        Si falla el guardado, no interrumpe el flujo de envío.
        """
        try:
            self.env["mobile.notification"].sudo().create({
                "title": payload.get("title") or "",
                "body": payload.get("body") or "",
                "notification_type": "PAYMENT_DUE",
                "link_type": "NONE",
                "partner_id": cuenta.partner_id.id if cuenta.partner_id else False,
                "vehicle_id": cuenta.vehiculo_id.id if getattr(cuenta, "vehiculo_id", False) else False,
                "is_read": False,
                "active": True,
                "created_at": fields.Datetime.now(),
            })
        except Exception as exc:
            _logger.exception(
                "[ADT Cron] Error guardando mobile.notification para cuenta=%s: %s",
                cuenta.id if cuenta else None,
                exc,
            )

    def _enviar_notificacion(self, payload, log_only=False):
        """
        Envía la notificación al servicio HTTP externo en formato:
            {"token": "...", "title": "...", "body": "...", "data": {...}}

        URL por defecto: http://localhost:8030/send
        Configurable vía ir.config_parameter:
          - adt_comercial.notificaciones_endpoint
          - notification.service.url
        """
        IrConfig = self.env["ir.config_parameter"].sudo()
        endpoint = (
            IrConfig.get_param("adt_comercial.notificaciones_endpoint")
            or IrConfig.get_param("notification.service.url")
            or "http://192.168.100.51:8030/send"
        )

        data_payload = payload.get("data", {})
        partner_id = data_payload.get("partner_id")

        _logger.info(
            "[ADT Notificacion] title=%r | tipo=%s | cuenta=%s | partner=%s | endpoint=%s",
            payload.get("title"),
            data_payload.get("tipo"),
            data_payload.get("referencia"),
            data_payload.get("partner_name"),
            endpoint,
        )
        _logger.info(
            "[ADT Notificacion Payload] title=%s | body=%s | data=%s",
            payload.get("title"),
            payload.get("body"),
            json.dumps(data_payload, ensure_ascii=False, default=str),
        )

        if not partner_id:
            _logger.warning("[ADT Notificacion] No se pudo resolver partner_id en payload.data")
            return

        fcm_devices = self.env["mobile.fcm.device"].sudo().search([
            ("partner_id", "=", partner_id),
            ("active", "=", True),
        ])

        if not fcm_devices:
            _logger.warning(
                "[ADT Notificacion] partner_id=%s no tiene dispositivos FCM activos.",
                partner_id,
            )
            return

        if log_only:
            _logger.info(
                "[ADT Notificacion] Modo prueba activo (log_only=True). Dispositivos destino=%s. No se envia al endpoint.",
                len(fcm_devices),
            )
            for device in fcm_devices:
                _logger.info(
                    "[ADT Notificacion][TEST] partner_id=%s device_id=%s platform=%s token=%s...",
                    partner_id,
                    device.device_id,
                    device.platform,
                    (device.fcm_token or "")[:20],
                )
            return

        try:
            import requests

            sent = 0
            failed = 0

            for device in fcm_devices:
                token = (device.fcm_token or "").strip()
                if not token:
                    failed += 1
                    continue

                body = {
                    "token": token,
                    "title": payload.get("title") or "",
                    "body": payload.get("body") or "",
                    "data": {},
                }

                try:
                    response = requests.post(endpoint, json=body, timeout=10)
                    if response.status_code == 200:
                        sent += 1
                    else:
                        failed += 1
                        _logger.error(
                            "[ADT Notificacion] Error %s enviando a device_id=%s partner_id=%s: %.300s",
                            response.status_code,
                            device.device_id,
                            partner_id,
                            response.text,
                        )
                except Exception as send_exc:
                    failed += 1
                    _logger.exception(
                        "[ADT Notificacion] Fallo de red enviando a device_id=%s partner_id=%s: %s",
                        device.device_id,
                        partner_id,
                        send_exc,
                    )

            _logger.info(
                "[ADT Notificacion] Resultado envio partner_id=%s | sent=%s | failed=%s | total=%s",
                partner_id,
                sent,
                failed,
                len(fcm_devices),
            )

        except Exception as exc:
            _logger.exception(
                "[ADT Notificacion] Error general al procesar envio a endpoint '%s': %s",
                endpoint,
                exc,
            )

