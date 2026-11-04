/** @odoo-module **/
/**
 * Alertas del monitoreo GPS en cualquier pantalla de Odoo, en tiempo real.
 *
 * - Canal principal: el bus de Odoo. El servidor envía cada evento de alerta (dejó de
 *   reportar, se desconectó, alarma, entró/salió de una geocerca, volvió a reportar)
 *   al partner de cada usuario apenas ocurre (webhook de Traccar o sincronización).
 * - Respaldo: cada minuto se pregunta al servidor por eventos posteriores al último
 *   visto (por si el longpolling estuvo caído).
 * Se muestran como notificación del navegador (si se permitió y la página es HTTPS) y
 * dentro de Odoo. El último evento visto se guarda en el navegador y lo comparten las
 * pestañas, así una alerta no se repite. Se desactiva por navegador desde la vista.
 */
import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

const RESPALDO_MS = 60000;
const BUS_TIPO = "adt_flota_360.gps";
const CLAVE_ULTIMO = "adt_f360_gps_ultimo_id";
const CLAVE_OFF = "adt_f360_gps_alertas_off";
const CLAVE_PRUEBA = "adt_f360_gps_prueba_recibida";
const MAX_INDIVIDUALES = 3;
const TITULOS = {
    sin_reporte: (e) => `Sin reportar: ${e.placa}`,
    desconectado: (e) => `Desconectado: ${e.placa}`,
    alarma: (e) => `Alarma: ${e.placa}`,
    geocerca_entrada: (e) => `${e.placa} entró a ${e.geocerca}`,
    geocerca_salida: (e) => `${e.placa} salió de ${e.geocerca}`,
    volvio: (e) => `Reportando de nuevo: ${e.placa}`,
    prueba: () => "Prueba de alertas GPS",
};
const TIPO_TOAST = { critico: "danger", atencion: "warning", info: "info", ok: "success" };

function leer(clave) {
    try {
        return browser.localStorage.getItem(clave);
    } catch (e) {
        return null;
    }
}

function guardar(clave, valor) {
    try {
        browser.localStorage.setItem(clave, String(valor));
    } catch (e) {
        // Almacenamiento bloqueado: se recuerda solo en memoria.
    }
}

export const gpsAlertasService = {
    dependencies: ["rpc", "notification", "action"],

    start(env, { rpc, notification, action }) {
        let enMemoria = null;
        let timer = null;
        let activo = true;

        const ultimoVisto = () => Number(leer(CLAVE_ULTIMO) || enMemoria || 0);
        const marcar = (id) => {
            enMemoria = id;
            guardar(CLAVE_ULTIMO, id);
        };
        const permitido = () => "Notification" in window && Notification.permission === "granted";

        const abrir = (params) => {
            window.focus();
            action.doAction({ type: "ir.actions.client", tag: "adt_flota_360_gps", name: "Monitoreo GPS", params });
        };

        const avisar = ({ titulo, cuerpo, tag, nivel, params }) => {
            const critico = nivel === "critico";
            if (permitido()) {
                const n = new Notification(titulo, { body: cuerpo, tag, requireInteraction: critico });
                n.onclick = () => {
                    abrir(params);
                    n.close();
                };
            }
            if (!permitido() || !document.hidden) {
                // Dentro de Odoo también, por si las notificaciones del sistema están silenciadas.
                notification.add(cuerpo, {
                    title: titulo,
                    type: TIPO_TOAST[nivel] || "info",
                    sticky: critico,
                    buttons: params ? [{ name: "Ver", primary: true, onClick: () => abrir(params) }] : [],
                });
            }
        };

        const notificar = (eventos) => {
            if (eventos.length > MAX_INDIVIDUALES) {
                const porTipo = {};
                for (const e of eventos) {
                    (porTipo[e.tipo_label] = porTipo[e.tipo_label] || []).push(e.placa);
                }
                const caidos = eventos.filter((e) => e.nivel === "critico");
                avisar({
                    titulo: `GPS: ${eventos.length} alertas nuevas`,
                    cuerpo: Object.entries(porTipo)
                        .map(([tipo, placas]) => `${tipo} (${placas.length}): ${placas.slice(0, 5).join(", ")}${placas.length > 5 ? "…" : ""}`)
                        .join(" · "),
                    tag: `adt-gps-lote-${eventos[eventos.length - 1].id}`,
                    nivel: caidos.length ? "critico" : "atencion",
                    params: caidos.length ? { filtro: "no_reporta" } : {},
                });
                return;
            }
            for (const e of eventos) {
                avisar({
                    titulo: (TITULOS[e.tipo] || (() => `GPS: ${e.placa}`))(e),
                    cuerpo: e.tipo === "sin_reporte" ? [e.motivo, e.cliente].filter(Boolean).join(" · ") : [e.mensaje, e.cliente].filter(Boolean).join(" · "),
                    tag: `adt-gps-${e.id}-${e.tipo}`,
                    nivel: e.nivel,
                    params: e.dispositivo_id ? { dispositivo_id: e.dispositivo_id } : null,
                });
            }
        };

        // Eventos con id mayor al último visto (compartido entre pestañas): sin duplicados.
        const procesar = (eventos, ultimoServidor) => {
            const visto = ultimoVisto();
            const nuevos = eventos.filter((e) => e.id > visto);
            const maximo = Math.max(visto, ultimoServidor || 0, ...eventos.map((e) => e.id));
            marcar(maximo);
            if (nuevos.length && leer(CLAVE_OFF) !== "1") {
                notificar(nuevos);
            }
        };

        const onBus = (notifs) => {
            for (const { type, payload } of notifs) {
                if (type !== BUS_TIPO || !payload) {
                    continue;
                }
                if (payload.prueba) {
                    guardar(CLAVE_PRUEBA, Date.now());
                    notificar(payload.eventos || []);
                    continue;
                }
                if (!ultimoVisto()) {
                    continue; // aún no se inicializó: el respaldo fija el punto de partida
                }
                procesar(payload.eventos || []);
            }
        };

        const consultar = async () => {
            if (!activo) {
                return;
            }
            const previo = ultimoVisto();
            let res;
            try {
                res = await rpc(
                    "/web/dataset/call_kw/adt.flota360/gps_alertas",
                    { model: "adt.flota360", method: "gps_alertas", args: [], kwargs: { desde_id: previo || false } },
                    { silent: true }
                );
            } catch (e) {
                return; // sin conexión o módulo actualizándose: se reintenta en la próxima vuelta
            }
            if (!res || !res.activo) {
                activo = false; // el usuario no tiene acceso a la flota
                browser.clearInterval(timer);
                return;
            }
            if (!previo || res.ultimo_id < previo) {
                marcar(res.ultimo_id); // primera vez (o base restaurada): no se notifica el pasado
                return;
            }
            procesar(res.eventos, res.ultimo_id);
        };

        env.bus.on("WEB_CLIENT_READY", null, () => {
            const busService = owl.Component.env.services.bus_service;
            if (busService) {
                busService.onNotification(this, onBus);
                busService.startPolling();
            }
        });

        browser.setTimeout(() => {
            consultar();
            timer = browser.setInterval(consultar, RESPALDO_MS);
        }, 3000 + Math.random() * 4000);
    },
};

registry.category("services").add("adt_flota_360_gps_alertas", gpsAlertasService);
