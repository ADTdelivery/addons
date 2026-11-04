odoo.define('adt_flota_360.GpsMapa', function (require) {
    'use strict';

    /**
     * Mapas del monitoreo GPS. Mismo enfoque que el mapa en vivo de adt_traccar_device
     * (live_map_field.js): Leaflet 1.9.4 cargado bajo demanda desde unpkg, solo cuando se
     * abre un mapa, y con las mismas marcas data-adt-leaflet-* para no cargarlo dos veces
     * si ambos módulos están instalados. Teselas de OpenStreetMap.
     */
    var LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    var LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    var CENTRO_LIMA = [-12.0464, -77.0428];
    var COLOR = {ok: '#2b8a3e', atencion: '#e67700', critico: '#c92a2a', neutral: '#868e96', info: '#1c7ed6'};
    var promesa = null;

    function cargar() {
        if (window.L && window.L.map) {
            return Promise.resolve(window.L);
        }
        if (promesa) {
            return promesa;
        }
        promesa = new Promise(function (resolve, reject) {
            if (!document.querySelector('link[data-adt-leaflet-css]')) {
                var link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = LEAFLET_CSS;
                link.setAttribute('data-adt-leaflet-css', '1');
                document.head.appendChild(link);
            }
            var listo = function () {
                if (window.L && window.L.map) { resolve(window.L); } else { reject(new Error('Leaflet no disponible')); }
            };
            var existente = document.querySelector('script[data-adt-leaflet-js]');
            if (existente) {
                if (window.L) { listo(); return; }
                existente.addEventListener('load', listo);
                existente.addEventListener('error', function () { reject(new Error('No se pudo cargar Leaflet')); });
                return;
            }
            var script = document.createElement('script');
            script.src = LEAFLET_JS;
            script.setAttribute('data-adt-leaflet-js', '1');
            script.onload = listo;
            script.onerror = function () {
                promesa = null;
                reject(new Error('No se pudo cargar el mapa (' + LEAFLET_JS + '). Revisa la conexión a internet.'));
            };
            document.head.appendChild(script);
        });
        return promesa;
    }

    function crear(L, el, opciones) {
        var mapa = L.map(el, _.extend({zoomControl: true, attributionControl: true}, opciones || {}))
            .setView(CENTRO_LIMA, 11);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19, attribution: '&copy; OpenStreetMap',
        }).addTo(mapa);
        return mapa;
    }

    function capaGeocerca(L, g, opciones) {
        var estilo = _.extend({color: g.color || '#d9480f', weight: 2, fillOpacity: 0.12}, opciones || {});
        var capa = g.tipo === 'circulo'
            ? L.circle([g.lat, g.lon], _.extend({radius: g.radio || 0}, estilo))
            : L.polygon(g.puntos || [], estilo);
        capa.bindTooltip(_.escape(g.name), {sticky: true});
        return capa;
    }

    function marcador(L, lat, lon, nivel, opciones) {
        return L.circleMarker([lat, lon], _.extend({
            radius: 7, color: '#fff', weight: 2, fillColor: COLOR[nivel] || COLOR.neutral, fillOpacity: 0.95,
        }, opciones || {}));
    }

    // Flecha de dirección para el vehículo en vivo (rotada según el rumbo).
    function iconoVehiculo(L, nivel, curso) {
        return L.divIcon({
            className: 'adt_gps__veh',
            html: '<span style="background:' + (COLOR[nivel] || COLOR.info) + ';transform:rotate(' + (curso || 0) +
                'deg)"><i class="fa fa-location-arrow"></i></span>',
            iconSize: [30, 30], iconAnchor: [15, 15],
        });
    }

    function ajustar(mapa, capas, zoomMax) {
        var grupo = window.L.featureGroup(capas.filter(Boolean));
        if (grupo.getLayers().length) {
            mapa.fitBounds(grupo.getBounds().pad(0.15), {maxZoom: zoomMax || 16});
        }
    }

    return {cargar: cargar, crear: crear, capaGeocerca: capaGeocerca, marcador: marcador,
            iconoVehiculo: iconoVehiculo, ajustar: ajustar, COLOR: COLOR, CENTRO: CENTRO_LIMA};
});
