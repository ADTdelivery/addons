odoo.define('adt_traccar_device.LiveMapField', function (require) {
"use strict";

/**
 * Mapa embebido con la última posición del vehículo, que se refresca solo
 * mientras la ficha está abierta (polling cada POLL_INTERVAL_MS contra
 * /adt_traccar_device/live_position — ver controllers/traccar_live_position.py).
 *
 * No es un websocket directo navegador↔Traccar (ver plan-adt-traccar-device.md,
 * sección 4.6, para el porqué de esa decisión): el navegador solo habla con
 * Odoo (mismo origen, sin problemas de CORS); es Odoo quien le pregunta a
 * Traccar server-side, reusando exactamente la misma lógica que ya usa el
 * botón "Actualizar" (action_refresh_gps_status).
 *
 * Se "cuelga" del campo traccar_credential_active_id (un Many2one) solo
 * para tener acceso a this.recordData (los demás campos gps_* del mismo
 * registro) y a this.value.res_id (el id de la credencial a pollear) — no
 * se usa como selector de Many2one, se reemplaza toda su renderización.
 *
 * Uso en una vista:
 *   <field name="traccar_credential_active_id" widget="adt_live_map"/>
 *
 * Depende de Leaflet (https://leafletjs.com/), cargado de forma perezosa
 * desde CDN la primera vez que el widget se monta (no se agrega como asset
 * global, para no pesar en el resto del backend de Odoo).
 */

var AbstractField = require('web.AbstractField');
var fieldRegistry = require('web.field_registry');

var LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
var LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
var POLL_INTERVAL_MS = 8000;
var DEFAULT_ZOOM = 15;

var STATUS_LABELS = {
    online: 'En línea',
    offline: 'Desconectado',
    unknown: 'Desconocido',
};

var _leafletLoadingPromise = null;

function ensureLeafletLoaded() {
    if (window.L) {
        return Promise.resolve(window.L);
    }
    if (_leafletLoadingPromise) {
        return _leafletLoadingPromise;
    }
    _leafletLoadingPromise = new Promise(function (resolve, reject) {
        if (!document.querySelector('link[data-adt-leaflet-css]')) {
            var $link = $('<link>', {
                rel: 'stylesheet',
                href: LEAFLET_CSS,
                'data-adt-leaflet-css': '1',
            });
            $('head').append($link);
        }
        var $script = $('<script>', {
            src: LEAFLET_JS,
            'data-adt-leaflet-js': '1',
        });
        $script.on('load', function () {
            resolve(window.L);
        });
        $script.on('error', function () {
            reject(new Error('No se pudo cargar Leaflet desde ' + LEAFLET_JS));
        });
        $('head').append($script);
    });
    return _leafletLoadingPromise;
}

var LiveMapField = AbstractField.extend({
    className: 'o_adt_live_map_field',
    supportedFieldTypes: ['many2one'],

    /**
     * @override
     */
    init: function () {
        this._super.apply(this, arguments);
        this._leafletMap = null;
        this._leafletMarker = null;
        this._pollTimer = null;
        this._mapReady = false;
    },

    /**
     * @override
     */
    destroy: function () {
        this._stopPolling();
        $(document).off('.adt_live_map_' + this.cid);
        if (this._leafletMap) {
            this._leafletMap.remove();
            this._leafletMap = null;
        }
        this._super.apply(this, arguments);
    },

    /**
     * @override
     * Se llama en cada (re)render — incluye la primera vez y cada vez que
     * cambia algún campo del registro (ej. después de guardar).
     */
    _render: function () {
        var self = this;
        var credentialId = this.value && this.value.res_id;

        if (!credentialId) {
            this._stopPolling();
            this.$el.html(
                '<div class="alert alert-info mb0" role="alert">' +
                'Este vehículo todavía no está registrado en Traccar — registralo con el ' +
                'botón "Traccar" (arriba) para ver su ubicación en el mapa.</div>'
            );
            return;
        }

        if (!this._mapReady) {
            this._renderSkeleton();
            ensureLeafletLoaded().then(function (L) {
                self._initMap(L);
                self._mapReady = true;
                self._paintFromRecordData();
                self._startPolling();
            }).catch(function (err) {
                self.$('.o_adt_live_map_canvas').replaceWith(
                    $('<div>', {
                        class: 'alert alert-warning mb0',
                        text: 'No se pudo cargar el mapa (' + err.message + '). ' +
                              'Los datos numéricos de abajo siguen actualizándose igual.',
                    })
                );
            });
        } else {
            this._paintFromRecordData();
        }
    },

    // ── UI ───────────────────────────────────────────────────────────────
    _renderSkeleton: function () {
        this.$el.empty();
        this.$el.append(
            '<div class="o_adt_live_map_panel mb8">' +
                '<span class="o_adt_live_map_badge badge"/> ' +
                '<span class="o_adt_live_map_speed"/> ' +
                '<span class="o_adt_live_map_battery"/> ' +
                '<span class="o_adt_live_map_updated text-muted"/>' +
            '</div>' +
            '<div class="o_adt_live_map_canvas"/>'
        );
    },

    _initMap: function (L) {
        var $canvas = this.$('.o_adt_live_map_canvas');
        this._leafletMap = L.map($canvas[0], {
            zoomControl: true,
            attributionControl: true,
        }).setView([0, 0], 2);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors',
        }).addTo(this._leafletMap);

        var icon = L.divIcon({
            html: '<div class="o_adt_live_map_marker">🚗</div>',
            className: 'o_adt_live_map_marker_wrapper',
            iconSize: [30, 30],
            iconAnchor: [15, 15],
        });
        this._leafletMarker = L.marker([0, 0], {icon: icon}).addTo(this._leafletMap);

        // Leaflet calcula el tamaño del mapa en el momento en que se crea.
        // Si en ese momento la pestaña "Traccar / GPS" no es la visible
        // (display:none), el mapa queda con tamaño 0 y se ve roto/en blanco
        // aunque después se abra la pestaña. Dos mitigaciones:
        //   1) invalidateSize() con un pequeño delay tras crear el mapa
        //      (por si el layout todavía se estaba acomodando).
        //   2) invalidateSize() cada vez que se hace click en un tab del
        //      formulario (por si esta pestaña se activa después).
        var self = this;
        setTimeout(function () {
            if (self._leafletMap) {
                self._leafletMap.invalidateSize();
            }
        }, 300);

        // Delegado en document (con namespace propio para poder limpiarlo en
        // destroy sin afectar otros listeners) — así no depende de encontrar
        // el contenedor exacto del notebook.
        $(document).on('click.adt_live_map_' + this.cid, '.nav-link, a[data-toggle="tab"]', function () {
            setTimeout(function () {
                if (self._leafletMap) {
                    self._leafletMap.invalidateSize();
                }
            }, 150);
        });
    },

    _paintFromRecordData: function (data) {
        // data viene del polling; si no hay data todavía, se pinta con lo
        // que ya trae el registro (recordData) para no esperar el primer
        // tick del polling.
        data = data || {
            status: this.recordData.gps_status,
            latitude: this.recordData.gps_latitude,
            longitude: this.recordData.gps_longitude,
            speed_kmh: this.recordData.gps_speed_kmh,
            battery_level: this.recordData.gps_battery_level,
            last_update: this.recordData.gps_last_update,
        };
        this._updatePanel(data);
        this._updateMarker(data);
    },

    _updatePanel: function (data) {
        var statusLabel = STATUS_LABELS[data.status] || 'Desconocido';
        var $badge = this.$('.o_adt_live_map_badge')
            .text(statusLabel)
            .removeClass('badge-success badge-secondary badge-warning')
            .addClass(
                data.status === 'online' ? 'badge-success' :
                data.status === 'offline' ? 'badge-secondary' : 'badge-warning'
            );
        this.$('.o_adt_live_map_speed').text(
            (data.speed_kmh || 0).toFixed(0) + ' km/h'
        );
        this.$('.o_adt_live_map_battery').text(
            data.battery_level ? (data.battery_level.toFixed(0) + '% batería') : ''
        );
        this.$('.o_adt_live_map_updated').text(
            data.last_update ? ('Último reporte: ' + data.last_update) : ''
        );
        void $badge; // silencia linters sobre variable no usada más allá del chain
    },

    _updateMarker: function (data) {
        if (!this._leafletMap || !this._leafletMarker) {
            return;
        }
        var lat = data.latitude;
        var lon = data.longitude;
        if (!lat && !lon) {
            return;
        }
        var latLng = [lat, lon];
        this._leafletMarker.setLatLng(latLng);
        this._leafletMap.setView(latLng, this._leafletMap.getZoom() > 2 ? this._leafletMap.getZoom() : DEFAULT_ZOOM);
    },

    // ── Polling ──────────────────────────────────────────────────────────
    _startPolling: function () {
        this._stopPolling();
        var self = this;
        this._pollTimer = setInterval(function () {
            self._pollOnce();
        }, POLL_INTERVAL_MS);
    },

    _stopPolling: function () {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    },

    _pollOnce: function () {
        var self = this;
        var credentialId = this.value && this.value.res_id;
        if (!credentialId) {
            this._stopPolling();
            return;
        }
        this._rpc({
            route: '/adt_traccar_device/live_position',
            params: {credential_id: credentialId},
        }).then(function (result) {
            if (result && !result.error) {
                self._paintFromRecordData(result);
            }
            // Si hay error (ej. Traccar caído momentáneamente), se ignora
            // este tick y se reintenta en el próximo — no se corta el
            // polling por un error puntual.
        }).guardedCatch(function () {
            // Error de red/RPC — igual, no se corta el polling.
        });
    },
});

fieldRegistry.add('adt_live_map', LiveMapField);

return LiveMapField;

});
