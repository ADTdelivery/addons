odoo.define('adt_flota_360.Gps', function (require) {
    'use strict';

    /**
     * Monitoreo GPS (vista 7 de Flota 360).
     *
     * Pestañas:
     * - Vehículos: recuadros (filtran), motivos de los que no reportan y la lista, con
     *   selección para crear en Odoo los vehículos que solo existen en Traccar.
     * - Mapa: todos los dispositivos filtrados con su estado y las geocercas.
     * - Geocercas: lista y editor (círculo o polígono dibujado en el mapa).
     * Filtros compartidos por Vehículos y Mapa: placa (buscador propio), texto libre,
     * origen (Odoo / solo Traccar…), estado, conexión, grupo, cliente, antigüedad del
     * último reporte y geocerca.
     *
     * Panel lateral (drawer): detalle del dispositivo (resumen, en vivo, recorrido por
     * fechas, historial), configuración y editor de geocercas.
     * La lista se refresca sola al llegar un evento por el bus de Odoo (tiempo real) y
     * cada minuto como respaldo. Las notificaciones las muestra el servicio
     * adt_flota_360_gps_alertas en cualquier pantalla.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Mapa = require('adt_flota_360.GpsMapa');

    var esc = _.escape;
    var ALERTAS_OFF = 'adt_f360_gps_alertas_off';
    var PRUEBA_RECIBIDA = 'adt_f360_gps_prueba_recibida';
    var BUS_TIPO = 'adt_flota_360.gps';
    var REFRESCO_MS = 60000;
    var VIVO_MS = 8000;
    var PAGINA = 150;
    var NIVEL_ICONO = {critico: 'fa-exclamation-circle', atencion: 'fa-clock-o', ok: 'fa-check-circle',
                       info: 'fa-info-circle', neutral: 'fa-minus-circle'};
    var ESTADO_LABEL = {reportando: 'Reportando', demorado: 'Demorado', sin_reporte: 'Sin reportar',
                        nunca: 'Nunca reportó', deshabilitado: 'Deshabilitado'};
    var ESTADO_ORDEN = {sin_reporte: 0, nunca: 1, demorado: 2, reportando: 3, deshabilitado: 4};
    var NO_REPORTA = {sin_reporte: true, nunca: true};
    var FILTROS_VACIOS = {placa: '', buscar: '', origen: '', estado: '', conexion: '', grupo: '', cliente: '',
                          antiguedad: '', geocerca: '', sin_gps: false, motivo: ''};
    var SELECTS = [
        {clave: 'origen', label: 'Origen', opciones: [['', 'Odoo y Traccar'], ['odoo', 'Con vehículo en Odoo'],
            ['traccar', 'Solo en Traccar'], ['ambiguo', 'Varias placas posibles'], ['creado', 'Creados desde Traccar'],
            ['manual', 'Relacionados a mano']]},
        {clave: 'estado', label: 'Estado', opciones: [['', 'Todos los estados'], ['no_reporta', 'No reportan'],
            ['reportando', 'Reportando'], ['demorado', 'Demorado'], ['sin_reporte', 'Sin reportar'],
            ['nunca', 'Nunca reportó'], ['deshabilitado', 'Deshabilitado']]},
        {clave: 'conexion', label: 'Conexión', opciones: [['', 'Toda conexión'], ['online', 'En línea'],
            ['offline', 'Desconectado'], ['unknown', 'Desconocido']]},
        {clave: 'cliente', label: 'Cliente', opciones: [['', 'Con o sin cliente'], ['con', 'Con cliente'],
            ['sin', 'Sin cliente']]},
        {clave: 'antiguedad', label: 'Último reporte', opciones: [['', 'Cualquier fecha'], ['60', 'Hace más de 1 h'],
            ['1440', 'Hace más de 24 h'], ['10080', 'Hace más de 7 días'], ['43200', 'Hace más de 30 días'],
            ['nunca', 'Nunca reportó']]},
    ];
    var PRESETS = [['hoy', 'Hoy'], ['ayer', 'Ayer'], ['24h', 'Últimas 24 h'], ['7d', 'Últimos 7 días']];

    // ------------------------------------------------------------------
    // Utilidades
    // ------------------------------------------------------------------

    function entero(n) { return (n || 0).toLocaleString('es-PE'); }
    function plural(n, uno, varios) { return entero(n) + ' ' + (n === 1 ? uno : varios); }
    function fechaHora(f) { return f ? moment.utc(f).local().format('DD/MM/YYYY HH:mm') : '—'; }
    function hora(f) { return f ? moment.utc(f).local().format('DD/MM HH:mm:ss') : '—'; }
    function minutosDesde(f) {
        return f ? Math.max(0, Math.floor((Date.now() - moment.utc(f).valueOf()) / 60000)) : null;
    }
    function duracion(m) {
        if (m < 60) { return m + ' min'; }
        if (m < 60 * 48) { return Math.floor(m / 60) + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : ''); }
        return Math.floor(m / 1440) + ' días';
    }
    function hace(f) {
        var m = minutosDesde(f);
        if (m === null) { return 'Sin reportes'; }
        return m < 1 ? 'hace un momento' : 'hace ' + duracion(m);
    }
    function icono(nivel) {
        return '<i class="fa ' + (NIVEL_ICONO[nivel] || NIVEL_ICONO.neutral) + ' adt_sat__ico is-' + (nivel || 'neutral') +
            '" aria-hidden="true"></i>';
    }
    function chipEstado(estado, nivel, texto) {
        return '<span class="adt_sat__motivo is-' + nivel + ' adt_gps__estado">' + icono(nivel) +
            esc(texto || ESTADO_LABEL[estado] || estado) + '</span>';
    }
    function normalizar(t) { return (t || '').toString().toUpperCase().replace(/[^0-9A-Z]/g, ''); }
    function leer(clave) { try { return window.localStorage.getItem(clave); } catch (e) { return null; } }
    function guardar(clave, valor) {
        try {
            if (valor === null) { window.localStorage.removeItem(clave); } else { window.localStorage.setItem(clave, valor); }
        } catch (e) { /* almacenamiento bloqueado */ }
    }
    function urlMapa(lat, lon) { return (lat || lon) ? 'https://www.google.com/maps?q=' + lat + ',' + lon : null; }
    function boton(accion, texto, ic, extra) {
        return '<button type="button" class="adt_cart__btn ' + (extra || 'adt_cart__btn--ghost') + '" ' + accion + '>' +
            (ic ? '<i class="fa ' + ic + '" aria-hidden="true"></i>' : '') + esc(texto) + '</button>';
    }
    function localInput(m) { return m.format('YYYY-MM-DDTHH:mm'); }
    function aUtc(valor) { return moment(valor).utc().format('YYYY-MM-DD HH:mm:ss'); }

    var Gps = AbstractAction.extend({
        template: 'adt_flota_360.Gps',
        hasControlPanel: false,

        events: {
            'click [data-action="sync"]': '_onSync',
            'click [data-action="notificaciones"]': '_onNotificaciones',
            'click [data-action="probar"]': '_onProbar',
            'click [data-action="config"]': '_abrirConfig',
            'click [data-action="cerrar"]': '_cerrarDrawer',
            'click [data-tab]': '_onTab',
            'click [data-box]': '_onBox',
            'click [data-motivo]': '_onMotivo',
            'click [data-action="odoo_sin_gps"]': '_onOdooSinGps',
            'click [data-action="mas"]': '_onMas',
            'click [data-action="limpiar"]': '_onLimpiar',
            'input [data-f]': '_onFiltroTexto',
            'change select[data-f]': '_onFiltroSelect',
            'click tr[data-id] td:not(.adt_gps__check)': '_onFila',
            'keydown tr[data-id]': '_onFilaTecla',
            'click .adt_gps__pop-ver': '_onPopupVer',
            'change [data-sel]': '_onSeleccion',
            'click [data-action="sel_creables"]': '_onSelCreables',
            'click [data-action="crear_sel"]': '_onCrearSeleccion',
            'click [data-dtab]': '_onDetalleTab',
            'click [data-d-action]': '_onDrawerAccion',
            'input [data-ref="buscar-vehiculo"]': '_onBuscarVehiculo',
            'click [data-elegir]': '_onElegirVehiculo',
            'click [data-m-action]': '_onModalAccion',
            'click [data-preset]': '_onPreset',
            'click [data-r-action]': '_onRecorridoAccion',
            'input [data-ref="r-slider"]': '_onSlider',
            'click [data-c-action]': '_onConfigAccion',
            'click [data-geo]': '_onGeoLista',
            'click [data-g-action]': '_onGeoAccion',
            'input [data-g]': '_onGeoCampo',
            'change [data-g]': '_onGeoCampo',
            'input [data-ref="g-buscar"]': '_renderGeoDispositivos',
            'change [data-gd]': '_onGeoDispositivo',
            'keydown': '_onTecla',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var params = (action && action.params) || {};
            this.tab = 'lista';
            this.f = _.clone(FILTROS_VACIOS);
            if (params.filtro === 'no_reporta') { this.f.estado = 'no_reporta'; }
            this.limite = PAGINA;
            this.data = null;
            this.detalle = null;
            this.sel = {};
            this._mapas = {};
            this._abrir = params.dispositivo_id ? parseInt(params.dispositivo_id, 10) : null;
            this._seq = 0;
            this._filtrarDiferido = _.debounce(this._aplicarFiltros.bind(this), 200);
            this._buscarVehiculoDiferido = _.debounce(this._cargarVehiculos.bind(this), 300);
            this._recargaBus = _.debounce(this._autoRefresco.bind(this, true), 1500);
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._render();
                self._timer = setInterval(function () { self._autoRefresco(false); }, REFRESCO_MS);
                // Tiempo real: cada evento que llega por el bus refresca la vista.
                self.call('bus_service', 'onNotification', self, self._onBus);
                if (self._abrir) {
                    self._abrirDetalle(self._abrir);
                    self._abrir = null;
                }
            });
        },

        destroy: function () {
            clearInterval(this._timer);
            this._pararVivo();
            this._pararPlay();
            this.call('bus_service', 'off', 'notification', this);
            this._quitarMapas();
            this._super.apply(this, arguments);
        },

        _ref: function (name) { return this.$('[data-ref="' + name + '"]'); },

        _llamar: function (metodo, kwargs, silencioso) {
            return this._rpc({model: 'adt.flota360', method: metodo, args: [], kwargs: kwargs || {}},
                             silencioso ? {shadow: true} : undefined);
        },

        _load: function (silencioso) {
            var self = this;
            var seq = ++this._seq;
            return this._llamar('gps_tablero', {}, silencioso).then(function (data) {
                if (seq === self._seq) { self.data = data; }
            });
        },

        _recargar: function () {
            var self = this;
            this.$el.addClass('is-loading');
            return this._load().then(function () {
                self.$el.removeClass('is-loading');
                self._render();
            }, function () {
                self.$el.removeClass('is-loading');
            });
        },

        // Relee sin perder pestaña, filtros, foco ni el mapa abierto.
        _autoRefresco: function (porBus) {
            if (!porBus && document.hidden) { return; }
            if (this._ref('modal').children().length) { return; }
            var self = this;
            this._load(true).then(function () {
                self._renderCabecera();
                if (self.tab === 'lista') {
                    self._renderResumen();
                    self._renderLista();
                } else if (self.tab === 'mapa') {
                    self._pintarMapaGeneral(false);
                } else if (self.tab === 'geocercas' && !self.$el.hasClass('is-drawer-open')) {
                    self._renderBody();
                }
            });
        },

        _onBus: function (notifs) {
            var self = this;
            _.each(notifs, function (n) {
                if (n.type !== BUS_TIPO || !n.payload || n.payload.prueba) { return; }
                self._recargaBus();
                if (self.detalle && _.some(n.payload.eventos, function (e) { return e.dispositivo_id === self.detalle.id; })
                        && self.dtab === 'resumen') {
                    self._recargarDetalle();
                }
            });
        },

        _quitarMapas: function (claves) {
            var self = this;
            _.each(claves || _.keys(this._mapas), function (k) {
                if (self._mapas[k]) {
                    self._mapas[k].remove();
                    delete self._mapas[k];
                }
            });
        },

        // ------------------------------------------------------------------
        // Render general
        // ------------------------------------------------------------------

        _render: function () {
            this._renderCabecera();
            this._renderTabs();
            this._renderFiltros();
            this._renderBody();
        },

        _renderCabecera: function () {
            var d = this.data;
            var meta = d.meta;
            this._ref('subtitle').text((meta.ultima_sync ? 'Última lectura de Traccar: ' + fechaHora(meta.ultima_sync) +
                ' (' + hace(meta.ultima_sync) + ')' : 'Aún no se ha leído Traccar') + ' · ' +
                plural(d.items.length, 'dispositivo', 'dispositivos'));
            this._ref('vivo').html(meta.tiempo_real
                ? '<span class="adt_gps__rt is-on" title="Traccar envía los eventos al instante (webhook). Último: ' +
                    esc(fechaHora(meta.webhook_ultimo)) + '"><i class="fa fa-circle" aria-hidden="true"></i>Tiempo real</span>'
                : '<span class="adt_gps__rt" title="Sin webhook de Traccar: Odoo lee Traccar cada ' + (meta.frecuencia || 1) +
                    ' min. Actívalo en Configuración → Tiempo real."><i class="fa fa-circle-o" aria-hidden="true"></i>' +
                    'Cada ' + (meta.frecuencia || 1) + ' min</span>');
            this._ref('config').toggleClass('d-none', !meta.manager);
            this._renderNotif();
            var avisos = [];
            if (meta.error) {
                avisos.push('<div class="adt_gps__aviso is-critico">' + icono('critico') + '<span><b>No se pudo leer Traccar' +
                    (meta.error_fecha ? ' (' + fechaHora(meta.error_fecha) + ')' : '') + ':</b> ' + esc(meta.error) +
                    '. Los estados mostrados son los de la última lectura correcta.</span></div>');
            }
            if (!meta.cron_activo) {
                avisos.push('<div class="adt_gps__aviso is-atencion">' + icono('atencion') + '<span>La sincronización ' +
                    'automática está desactivada: la lista solo se actualiza con «Sincronizar ahora».</span></div>');
            }
            if (!meta.soy_destinatario) {
                avisos.push('<div class="adt_gps__aviso is-info">' + icono('info') + '<span>No estás entre los usuarios ' +
                    'que reciben las alertas (Configuración → Alertas).</span></div>');
            }
            this._ref('aviso').html(avisos.join(''));
        },

        _renderNotif: function () {
            var soporta = 'Notification' in window;
            var permiso = soporta ? Notification.permission : 'denied';
            var off = leer(ALERTAS_OFF) === '1';
            var html, titulo;
            if (!soporta) {
                html = '<i class="fa fa-bell" aria-hidden="true"></i>Alertas en Odoo';
                titulo = 'Este navegador no admite notificaciones (o la página no está en HTTPS); las alertas se muestran dentro de Odoo.';
            } else if (off) {
                html = '<i class="fa fa-bell-slash" aria-hidden="true"></i>Alertas desactivadas';
                titulo = 'Activar las alertas en este navegador';
            } else if (permiso === 'granted') {
                html = '<i class="fa fa-bell" aria-hidden="true"></i>Alertas activas';
                titulo = 'Recibes notificaciones del navegador y dentro de Odoo. Clic para desactivarlas aquí.';
            } else if (permiso === 'denied') {
                html = '<i class="fa fa-bell-o" aria-hidden="true"></i>Navegador bloqueado';
                titulo = 'El navegador bloqueó las notificaciones de este sitio: habilítalas en el candado de la barra de ' +
                    'direcciones. Mientras tanto las alertas se muestran dentro de Odoo.';
            } else {
                html = '<i class="fa fa-bell-o" aria-hidden="true"></i>Activar notificaciones';
                titulo = 'Permitir notificaciones del navegador para enterarte al momento';
            }
            this._ref('notif').html(html).attr('title', titulo).toggleClass('is-on', !off && permiso === 'granted');
        },

        _renderTabs: function () {
            var self = this;
            var tabs = [['lista', 'Vehículos', 'fa-list', this.data.items.length], ['mapa', 'Mapa', 'fa-map-o', null],
                        ['geocercas', 'Geocercas', 'fa-dot-circle-o', this.data.geocercas.length]];
            this._ref('tabs').html(tabs.map(function (t) {
                var activo = self.tab === t[0];
                return '<button type="button" role="tab" data-tab="' + t[0] + '" aria-selected="' + activo + '" class="' +
                    (activo ? 'is-active' : '') + '"><i class="fa ' + t[2] + '" aria-hidden="true"></i>' + t[1] +
                    (t[3] !== null ? ' <span class="adt_gps__tab-n">' + entero(t[3]) + '</span>' : '') + '</button>';
            }).join(''));
        },

        _renderFiltros: function () {
            if (this.tab === 'geocercas') {
                this._ref('filtros').empty();
                return;
            }
            var f = this.f;
            var d = this.data;
            var grupos = _.uniq(_.compact(_.pluck(d.items, 'grupo'))).sort();
            var selects = SELECTS.slice();
            if (grupos.length) {
                selects.push({clave: 'grupo', label: 'Grupo', opciones: [['', 'Todo grupo']].concat(grupos.map(function (g) {
                    return [g, g];
                }))});
            }
            if (d.geocercas.length) {
                selects.push({clave: 'geocerca', label: 'Geocerca', opciones: [['', 'Cualquier lugar']].concat(
                    d.geocercas.map(function (g) { return [String(g.id), 'Dentro de ' + g.name]; }))});
            }
            this._ref('filtros').html(
                '<div class="adt_gps__busca">' +
                    '<label class="adt_gps__search is-placa"><i class="fa fa-id-card-o" aria-hidden="true"></i>' +
                        '<input type="search" data-f="placa" placeholder="Placa (ej. 0312RC, ABC-123)" aria-label="Buscar por placa" value="' +
                        esc(f.placa) + '"/></label>' +
                    '<label class="adt_gps__search is-libre"><i class="fa fa-search" aria-hidden="true"></i>' +
                        '<input type="search" data-f="buscar" placeholder="Cliente, IMEI, modelo, teléfono…" aria-label="Buscar" value="' +
                        esc(f.buscar) + '"/></label>' +
                '</div>' +
                '<div class="adt_gps__selects">' + selects.map(function (s) {
                    var valor = f[s.clave] || '';
                    return '<label class="adt_gps__select' + (valor ? ' is-set' : '') + '"><span>' + esc(s.label) + '</span>' +
                        '<select data-f="' + s.clave + '">' + s.opciones.map(function (o) {
                            return '<option value="' + esc(o[0]) + '"' + (o[0] === valor ? ' selected="selected"' : '') + '>' +
                                esc(o[1]) + '</option>';
                        }).join('') + '</select></label>';
                }).join('') +
                    '<span data-ref="limpiar"></span>' +
                '</div>');
            this._renderLimpiar();
        },

        _nFiltros: function () {
            var f = this.f;
            return _.filter(_.keys(FILTROS_VACIOS), function (k) { return !!f[k]; }).length;
        },

        _renderLimpiar: function () {
            var n = this._nFiltros();
            this._ref('limpiar').html(n ? '<button type="button" class="adt_gps__link" data-action="limpiar">' +
                '<i class="fa fa-times" aria-hidden="true"></i> Quitar filtros (' + n + ')</button>' : '');
        },

        _renderBody: function () {
            this._quitarMapas(['general', 'geocercas']);
            var d = this.data;
            if (!d.items.length && this.tab !== 'geocercas') {
                this._ref('body').html('<div class="adt_cart__empty">' + (d.meta.ultima_sync
                    ? 'Traccar no tiene dispositivos registrados.'
                    : 'Pulsa «Sincronizar ahora» para traer los dispositivos de Traccar.') + '</div>');
                return;
            }
            if (this.tab === 'mapa') {
                this._ref('body').html('<section class="adt_sat__panel adt_gps__mapa-panel">' +
                    '<header class="adt_sat__panel-head"><h3><i class="fa fa-map-o" aria-hidden="true"></i>' +
                    '<span data-ref="mapa-titulo">Mapa</span></h3>' + this._leyenda() + '</header>' +
                    '<div class="adt_gps__mapa is-general" data-ref="mapa-general"></div></section>');
                this._pintarMapaGeneral(true);
            } else if (this.tab === 'geocercas') {
                this._renderGeocercas();
            } else {
                this._ref('body').html('<div data-ref="resumen"></div>' +
                    '<section class="adt_sat__panel adt_gps__lista">' +
                        '<header class="adt_sat__panel-head"><h3><i class="fa fa-list" aria-hidden="true"></i>' +
                            '<span data-ref="lista-titulo">Dispositivos</span></h3><div data-ref="acciones-lista" ' +
                            'class="adt_gps__acciones-lista"></div></header>' +
                        '<div class="adt_sat__panel-body" data-ref="lista"></div>' +
                    '</section>');
                this._renderResumen();
                this._renderLista();
            }
        },

        _leyenda: function () {
            return '<div class="adt_gps__leyenda">' + [['ok', 'Reportando'], ['atencion', 'Demorado'],
                ['critico', 'No reporta'], ['neutral', 'Deshabilitado']].map(function (l) {
                    return '<span><i style="background:' + Mapa.COLOR[l[0]] + '"></i>' + l[1] + '</span>';
                }).join('') + '</div>';
        },

        // ------------------------------------------------------------------
        // Filtros
        // ------------------------------------------------------------------

        _coincide: function (i, f) {
            if (f.estado) {
                if (f.estado === 'no_reporta' ? !NO_REPORTA[i.estado] : i.estado !== f.estado) { return false; }
            }
            if (f.sin_gps && !i.sin_gps) { return false; }
            if (f.motivo && !(NO_REPORTA[i.estado] && i.motivo === f.motivo)) { return false; }
            if (f.origen) {
                var ok = {odoo: !!i.vehicle_id, traccar: !i.vehicle_id, ambiguo: i.metodo === 'ambiguo',
                          creado: i.metodo === 'creado', manual: i.manual}[f.origen];
                if (!ok) { return false; }
            }
            if (f.conexion && i.conexion !== f.conexion) { return false; }
            if (f.grupo && i.grupo !== f.grupo) { return false; }
            if (f.cliente === 'con' && !i.cliente) { return false; }
            if (f.cliente === 'sin' && i.cliente) { return false; }
            if (f.antiguedad) {
                var m = minutosDesde(i.ultimo);
                if (f.antiguedad === 'nunca' ? m !== null : (m === null || m < parseInt(f.antiguedad, 10))) { return false; }
            }
            if (f.geocerca && (i.geocercas || []).indexOf(parseInt(f.geocerca, 10)) === -1) { return false; }
            if (f.placa) {
                var qp = normalizar(f.placa);
                if (qp && [i.placa, i.placa_detectada, i.nombre].every(function (t) { return normalizar(t).indexOf(qp) === -1; })) {
                    return false;
                }
            }
            if (f.buscar) {
                var q = f.buscar.trim().toUpperCase();
                var texto = [i.nombre, i.imei, i.placa, i.cliente, i.vehiculo, i.telefono, i.grupo, i.motivo].join(' ').toUpperCase();
                if (q && texto.indexOf(q) === -1 && normalizar(texto).indexOf(normalizar(q)) === -1) { return false; }
            }
            return true;
        },

        _filtrados: function () {
            var self = this;
            var lista = this.data.items.filter(function (i) { return self._coincide(i, self.f); });
            return _.sortBy(lista, function (i) {
                var m = minutosDesde(i.ultimo);
                return [ESTADO_ORDEN[i.estado], 1e9 - (m === null ? 1e9 : m)].map(function (x) {
                    return ('000000000000' + Math.round(x)).slice(-12);
                }).join('|');
            });
        },

        _aplicarFiltros: function () {
            this.limite = PAGINA;
            this._renderLimpiar();
            this.$('.adt_gps__select').each(function () {
                $(this).toggleClass('is-set', !!$(this).find('select').val());
            });
            if (this.tab === 'mapa') {
                this._pintarMapaGeneral(true);
            } else {
                this._renderResumen();
                this._renderLista();
            }
        },

        _onFiltroTexto: function (ev) {
            if (ev.currentTarget.tagName === 'SELECT') { return; }
            this.f[ev.currentTarget.getAttribute('data-f')] = ev.currentTarget.value;
            this._filtrarDiferido();
        },

        _onFiltroSelect: function (ev) {
            this.f[ev.currentTarget.getAttribute('data-f')] = ev.currentTarget.value;
            this._aplicarFiltros();
        },

        _onLimpiar: function () {
            this.f = _.clone(FILTROS_VACIOS);
            this._renderFiltros();
            this._aplicarFiltros();
        },

        _onTab: function (ev) {
            var tab = ev.currentTarget.getAttribute('data-tab');
            if (tab === this.tab) { return; }
            this.tab = tab;
            this._renderTabs();
            this._renderFiltros();
            this._renderBody();
        },

        // ------------------------------------------------------------------
        // Pestaña Vehículos
        // ------------------------------------------------------------------

        _renderResumen: function () {
            var self = this;
            var items = this.data.items;
            var f = this.f;
            var cuenta = function (fn) { return _.filter(items, fn).length; };
            var noReporta = cuenta(function (i) { return NO_REPORTA[i.estado]; });
            var reportando = cuenta(function (i) { return i.estado === 'reportando'; });
            var demorado = cuenta(function (i) { return i.estado === 'demorado'; });
            var nunca = cuenta(function (i) { return i.estado === 'nunca'; });
            var sinGps = cuenta(function (i) { return i.sin_gps; });
            var soloTraccar = cuenta(function (i) { return !i.vehicle_id; });
            var creables = cuenta(function (i) { return i.puede_crear; });
            var deshab = cuenta(function (i) { return i.estado === 'deshabilitado'; });
            var odoo = this.data.odoo_sin_gps || {n: 0};
            var activos = items.length - deshab;
            var pct = activos ? Math.round(reportando * 100 / activos) : 0;
            var caja = function (clave, campo, valorFiltro, label, ic, n, sub, nivel) {
                var activo = clave !== 'odoo_sin_gps' && f[campo] === valorFiltro;
                var vacio = clave === 'odoo_sin_gps' ? !odoo.n : !n;
                var attr = clave === 'odoo_sin_gps' ? (odoo.n ? ' data-action="odoo_sin_gps"' : ' disabled="disabled"')
                    : (vacio && !activo ? ' disabled="disabled"' : ' data-box="' + clave + '" aria-pressed="' + activo + '"');
                return '<button type="button" class="adt_find__box is-' + nivel + (vacio ? ' is-empty' : '') +
                    (activo ? ' is-active' : '') + '"' + attr + '>' +
                    '<span class="adt_find__box-head"><i class="fa ' + ic + '" aria-hidden="true"></i>' + esc(label) +
                    '<i class="fa ' + (activo ? 'fa-times' : 'fa-angle-right') + ' adt_find__box-go" aria-hidden="true"></i></span>' +
                    '<span class="adt_find__box-value">' + entero(n) + '</span>' +
                    '<span class="adt_find__box-sub">' + esc(sub) + '</span></button>';
            };
            var meta = this.data.meta;
            this._ref('resumen').html('<section class="adt_find__grid adt_sat__grid adt_gps__grid">' + [
                caja('no_reporta', 'estado', 'no_reporta', 'No reportan', 'fa-exclamation-triangle', noReporta,
                     noReporta ? 'Más de ' + meta.minutos_sin_reporte + ' min sin datos o nunca reportaron' : 'Todos los equipos activos reportan',
                     noReporta ? 'critico' : 'ok'),
                caja('reportando', 'estado', 'reportando', 'Reportando', 'fa-check-circle', reportando, pct + ' % de los equipos activos', 'ok'),
                caja('demorado', 'estado', 'demorado', 'Reporte demorado', 'fa-clock-o', demorado,
                     'Entre ' + meta.minutos_demora + ' y ' + meta.minutos_sin_reporte + ' min sin datos', demorado ? 'atencion' : 'ok'),
                caja('nunca', 'estado', 'nunca', 'Nunca reportaron', 'fa-question-circle', nunca,
                     'Registrados en Traccar sin ningún dato', nunca ? 'critico' : 'ok'),
                caja('sin_gps', 'sin_gps', true, 'Comunican sin señal GPS', 'fa-crosshairs', sinGps,
                     'Envían datos pero sin posición válida', sinGps ? 'atencion' : 'ok'),
                caja('traccar', 'origen', 'traccar', 'Solo en Traccar', 'fa-chain-broken', soloTraccar,
                     creables ? plural(creables, 'se puede crear en Odoo', 'se pueden crear en Odoo') : 'Sin vehículo en Odoo',
                     soloTraccar ? 'atencion' : 'ok'),
                caja('odoo_sin_gps', null, null, 'Vehículos de Odoo sin GPS', 'fa-motorcycle', odoo.n,
                     'Con cliente y placa, sin equipo en Traccar', odoo.n ? 'atencion' : 'ok'),
                caja('deshabilitado', 'estado', 'deshabilitado', 'Deshabilitados', 'fa-ban', deshab, 'Desactivados en Traccar', 'neutral'),
            ].join('') + '</section>' + this._htmlMotivos());
        },

        _onBox: function (ev) {
            var clave = ev.currentTarget.getAttribute('data-box');
            var mapa = {no_reporta: ['estado', 'no_reporta'], reportando: ['estado', 'reportando'],
                        demorado: ['estado', 'demorado'], nunca: ['estado', 'nunca'], deshabilitado: ['estado', 'deshabilitado'],
                        sin_gps: ['sin_gps', true], traccar: ['origen', 'traccar']}[clave];
            if (!mapa) { return; }
            this.f[mapa[0]] = this.f[mapa[0]] === mapa[1] ? FILTROS_VACIOS[mapa[0]] : mapa[1];
            this._renderFiltros();
            this._aplicarFiltros();
        },

        _htmlMotivos: function () {
            var self = this;
            var grupos = _.countBy(_.filter(this.data.items, function (i) { return NO_REPORTA[i.estado]; }), 'motivo');
            var filas = _.sortBy(_.map(grupos, function (n, motivo) { return {motivo: motivo, n: n}; }), function (r) { return -r.n; });
            if (!filas.length) { return ''; }
            var max = filas[0].n;
            return '<section class="adt_sat__panel"><header class="adt_sat__panel-head"><h3><i class="fa fa-stethoscope" ' +
                'aria-hidden="true"></i>¿Por qué no reportan?</h3><span class="adt_sat__muted">Deducido de la última ' +
                'posición que envió cada equipo · clic para filtrar</span></header><div class="adt_sat__panel-body"><ul class="adt_sat__bars">' +
                filas.map(function (r) {
                    var activo = self.f.motivo === r.motivo;
                    return '<li><button type="button" class="adt_sat__bar adt_gps__bar' + (activo ? ' is-active' : '') +
                        '" data-motivo="' + esc(r.motivo) + '" aria-pressed="' + activo + '" title="' + esc(r.motivo) + '">' +
                        '<span class="adt_sat__bar-label">' + esc(r.motivo) + '</span>' +
                        '<span class="adt_sat__bar-track"><span class="adt_sat__bar-fill is-critico" style="width:' +
                            Math.max(r.n * 100 / max, 2) + '%"></span></span>' +
                        '<span class="adt_sat__bar-n">' + entero(r.n) + '</span></button></li>';
                }).join('') + '</ul></div></section>';
        },

        _onMotivo: function (ev) {
            var motivo = ev.currentTarget.getAttribute('data-motivo');
            this.f.motivo = this.f.motivo === motivo ? '' : motivo;
            this._aplicarFiltros();
        },

        _renderLista: function () {
            var self = this;
            var lista = this._filtrados();
            var visibles = lista.slice(0, this.limite);
            var manager = this.data.meta.manager;
            var creables = _.filter(lista, function (i) { return i.puede_crear; });
            var nSel = _.size(this.sel);
            this._ref('lista-titulo').text((this._nFiltros() ? 'Filtrados' : 'Dispositivos') + ' · ' + entero(lista.length));
            this._ref('acciones-lista').html(manager && (creables.length || nSel)
                ? (creables.length ? boton('data-action="sel_creables"', 'Seleccionar los ' + entero(creables.length) +
                    ' que se pueden crear', 'fa-check-square-o') : '') +
                  (nSel ? boton('data-action="crear_sel"', 'Crear ' + plural(nSel, 'vehículo', 'vehículos') + ' en Odoo',
                    'fa-plus', '') : '')
                : '');
            if (!lista.length) {
                this._ref('lista').html('<p class="adt_sat__vacio">Ningún dispositivo coincide con los filtros.</p>');
                return;
            }
            this._ref('lista').html('<div class="adt_sat__table-wrap"><table class="adt_sat__table adt_gps__table"><thead><tr>' +
                (manager ? '<th class="adt_gps__check"></th>' : '') +
                '<th>Estado</th><th>Dispositivo en Traccar</th><th>Vehículo en Odoo</th><th>Último reporte</th>' +
                '<th>Motivo</th><th></th></tr></thead><tbody>' + visibles.map(function (i) {
                    var nivel = i.sin_gps ? 'atencion' : i.nivel;
                    var vehiculo = i.vehicle_id
                        ? '<span class="adt_sat__strong">' + esc(i.placa || '—') + '</span>' +
                          '<span class="adt_sat__sub">' + esc([i.vehiculo, i.cliente || 'Sin cliente'].filter(Boolean).join(' · ')) + '</span>' +
                          (i.metodo === 'creado' ? '<span class="adt_sat__chip is-info">Creado desde Traccar</span>' : '') +
                          (i.otros_dispositivos ? '<span class="adt_sat__chip is-atencion">+' + i.otros_dispositivos + ' equipo</span>' : '')
                        : '<span class="adt_gps__sinv">' + icono(i.metodo === 'ambiguo' ? 'atencion' : 'neutral') +
                          (i.metodo === 'ambiguo' ? 'Varias placas posibles' : 'Solo en Traccar') + '</span>' +
                          (i.placa_detectada ? '<span class="adt_sat__sub">Placa leída: ' + esc(i.placa_detectada) + '</span>' : '');
                    var check = manager ? '<td class="adt_gps__check">' + (i.puede_crear ? '<input type="checkbox" data-sel="' +
                        i.id + '" aria-label="Seleccionar para crear en Odoo"' + (self.sel[i.id] ? ' checked="checked"' : '') + '/>' : '') +
                        '</td>' : '';
                    return '<tr class="is-' + nivel + '" data-id="' + i.id + '" tabindex="0">' + check +
                        '<td>' + chipEstado(i.estado, nivel) + '</td>' +
                        '<td><span class="adt_sat__strong">' + esc(i.nombre) + '</span><span class="adt_sat__sub adt_sat__mono">' +
                            esc(i.imei || '—') + '</span></td>' +
                        '<td>' + vehiculo + '</td>' +
                        '<td><span class="adt_sat__strong">' + esc(hace(i.ultimo)) + '</span><span class="adt_sat__sub">' +
                            fechaHora(i.ultimo) + '</span></td>' +
                        '<td class="adt_gps__motivo">' + esc(i.motivo) + '</td>' +
                        '<td class="is-num"><i class="fa fa-angle-right" aria-hidden="true"></i></td></tr>';
                }).join('') + '</tbody></table></div>' +
                (lista.length > visibles.length ? '<div class="adt_gps__mas">' + boton('data-action="mas"',
                    'Mostrar más (' + entero(lista.length - visibles.length) + ' restantes)') + '</div>' : ''));
        },

        _onMas: function () {
            this.limite += PAGINA;
            this._renderLista();
        },

        _onSeleccion: function (ev) {
            var id = parseInt(ev.currentTarget.getAttribute('data-sel'), 10);
            if (ev.currentTarget.checked) { this.sel[id] = true; } else { delete this.sel[id]; }
            this._renderLista();
        },

        _onSelCreables: function () {
            var self = this;
            _.each(this._filtrados(), function (i) { if (i.puede_crear) { self.sel[i.id] = true; } });
            this._renderLista();
        },

        _onCrearSeleccion: function () {
            var ids = _.map(_.keys(this.sel), Number);
            this._confirmarCrear(ids);
        },

        _confirmarCrear: function (ids) {
            var meta = this.data.meta;
            var items = _.filter(this.data.items, function (i) { return ids.indexOf(i.id) !== -1; });
            if (!meta.modelo_id) {
                this._modal('Crear vehículos en Odoo', '<p>' + icono('atencion') + 'Primero elige en <b>Configuración → ' +
                    'Vehículos que faltan</b> el modelo con el que se crean los vehículos (luego puedes corregir cada uno).</p>',
                    boton('data-m-action="cerrar"', 'Cerrar') + (meta.manager ? boton('data-m-action="ir_config"', 'Ir a configuración', 'fa-sliders', '') : ''));
                return;
            }
            this._crearIds = ids;
            this._modal('Crear ' + plural(ids.length, 'vehículo', 'vehículos') + ' en Odoo',
                '<p>Se crearán con la placa leída del nombre en Traccar y el modelo <b>' + esc(meta.modelo_nombre) +
                '</b>, y quedarán relacionados con su dispositivo. Si ya existe un vehículo con esa placa, solo se relaciona.</p>' +
                '<ul class="adt_gps__lista-corta">' + items.slice(0, 12).map(function (i) {
                    return '<li><b>' + esc(i.placa_detectada) + '</b> <span class="adt_sat__muted">← ' + esc(i.nombre) + '</span></li>';
                }).join('') + (items.length > 12 ? '<li class="adt_sat__muted">… y ' + (items.length - 12) + ' más</li>' : '') + '</ul>',
                boton('data-m-action="cerrar"', 'Cancelar') + boton('data-m-action="crear"', 'Crear vehículos', 'fa-plus', ''));
        },

        _onOdooSinGps: function () {
            this.do_action({
                type: 'ir.actions.act_window', name: 'Vehículos sin equipo en Traccar', res_model: 'fleet.vehicle',
                views: [[false, 'list'], [false, 'form']], domain: [['id', 'in', this.data.odoo_sin_gps.ids]], target: 'current',
            });
        },

        _onFila: function (ev) {
            this._abrirDetalle(parseInt($(ev.currentTarget).closest('tr').attr('data-id'), 10));
        },

        _onFilaTecla: function (ev) {
            if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.tagName !== 'INPUT') {
                ev.preventDefault();
                this._abrirDetalle(parseInt(ev.currentTarget.getAttribute('data-id'), 10));
            }
        },

        // ------------------------------------------------------------------
        // Pestaña Mapa
        // ------------------------------------------------------------------

        _pintarMapaGeneral: function (encuadrar) {
            var self = this;
            var $el = this._ref('mapa-general');
            if (!$el.length) { return; }
            Mapa.cargar().then(function (L) {
                if (!self._ref('mapa-general').length) { return; }
                var mapa = self._mapas.general;
                if (!mapa) {
                    mapa = self._mapas.general = Mapa.crear(L, $el[0]);
                    self._capasGeneral = L.layerGroup().addTo(mapa);
                    encuadrar = true;
                }
                self._capasGeneral.clearLayers();
                var capas = [];
                _.each(self.data.geocercas, function (g) {
                    Mapa.capaGeocerca(L, g).addTo(self._capasGeneral);
                });
                var lista = self._filtrados().filter(function (i) { return i.lat || i.lon; });
                _.each(lista, function (i) {
                    var nivel = i.sin_gps ? 'atencion' : i.nivel;
                    var m = Mapa.marcador(L, i.lat, i.lon, nivel).bindPopup(
                        '<div class="adt_gps__pop"><b>' + esc(i.placa || i.nombre) + '</b><br/>' +
                        esc(ESTADO_LABEL[i.estado] || '') + ' · ' + esc(hace(i.ultimo)) + '<br/>' +
                        (i.cliente ? esc(i.cliente) + '<br/>' : '') +
                        '<span class="adt_sat__muted">' + esc(i.motivo) + '</span><br/>' +
                        '<button type="button" class="adt_gps__pop-ver" data-pid="' + i.id + '">Ver detalle</button></div>');
                    m.bindTooltip(esc(i.placa || i.nombre));
                    m.addTo(self._capasGeneral);
                    capas.push(m);
                });
                var sinPos = self._filtrados().length - lista.length;
                self._ref('mapa-titulo').text(plural(lista.length, 'dispositivo', 'dispositivos') + ' en el mapa' +
                    (sinPos ? ' · ' + entero(sinPos) + ' sin posición' : ''));
                if (encuadrar) { Mapa.ajustar(mapa, capas, 15); }
                setTimeout(function () { mapa.invalidateSize(); }, 50);
            }, function (err) {
                self._ref('mapa-general').html('<p class="adt_sat__vacio">' + esc(err.message) + '</p>');
            });
        },

        _onPopupVer: function (ev) {
            this._abrirDetalle(parseInt(ev.currentTarget.getAttribute('data-pid'), 10));
        },

        // ------------------------------------------------------------------
        // Pestaña Geocercas
        // ------------------------------------------------------------------

        _renderGeocercas: function () {
            var geos = this.data.geocercas;
            var manager = this.data.meta.manager;
            var lista = geos.length ? '<ul class="adt_gps__geos">' + geos.map(function (g) {
                var forma = g.tipo === 'circulo' ? 'Círculo de ' + entero(Math.round(g.radio)) + ' m' : 'Polígono de ' + g.puntos.length + ' puntos';
                var alertas = [g.entrada ? 'entrada' : '', g.salida ? 'salida' : ''].filter(Boolean);
                var traccar = !g.publicar ? 'Solo en Odoo' : (g.traccar_error ? 'Error al publicar en Traccar' : (g.traccar_id ? 'Publicada en Traccar' : 'Pendiente de publicar'));
                return '<li><button type="button" data-geo="' + g.id + '" class="adt_gps__geo">' +
                    '<span class="adt_gps__geo-color" style="background:' + esc(g.color) + '"></span>' +
                    '<span class="adt_gps__geo-txt"><b>' + esc(g.name) + '</b>' +
                    '<span class="adt_sat__sub">' + esc(forma) + ' · ' + (g.alcance === 'todos' ? 'Todos los dispositivos' :
                        plural(g.dispositivos.length, 'dispositivo', 'dispositivos')) + '</span>' +
                    '<span class="adt_sat__sub">' + (alertas.length ? '<i class="fa fa-bell" aria-hidden="true"></i> Alerta al ' + alertas.join(' y ')
                        : '<i class="fa fa-bell-slash" aria-hidden="true"></i> Sin alertas') + ' · ' +
                        '<span class="' + (g.traccar_error ? 'adt_gps__txt-error' : '') + '" title="' + esc(g.traccar_error) + '">' +
                        esc(traccar) + '</span></span></span>' +
                    '<span class="adt_gps__geo-n" title="Dispositivos dentro ahora"><b>' + entero(g.dentro) + '</b>dentro</span>' +
                    '</button></li>';
            }).join('') + '</ul>' : '<p class="adt_sat__vacio">Aún no hay geocercas. Crea una para recibir alertas cuando un ' +
                'vehículo entre o salga de una zona (taller, base, zona de riesgo…).</p>';
            this._ref('body').html('<section class="adt_gps__geo-layout">' +
                '<div class="adt_sat__panel"><header class="adt_sat__panel-head"><h3><i class="fa fa-dot-circle-o" ' +
                'aria-hidden="true"></i>Geocercas · ' + entero(geos.length) + '</h3>' +
                (manager ? boton('data-g-action="nueva"', 'Nueva geocerca', 'fa-plus', '') : '') + '</header>' +
                '<div class="adt_sat__panel-body">' + lista + '</div></div>' +
                '<div class="adt_sat__panel"><div class="adt_gps__mapa is-geos" data-ref="mapa-geos"></div></div></section>');
            var self = this;
            Mapa.cargar().then(function (L) {
                var $m = self._ref('mapa-geos');
                if (!$m.length) { return; }
                var mapa = self._mapas.geocercas = Mapa.crear(L, $m[0]);
                var capas = geos.map(function (g) {
                    return Mapa.capaGeocerca(L, g).on('click', function () { self._abrirGeocerca(g.id); }).addTo(mapa);
                });
                Mapa.ajustar(mapa, capas, 15);
                setTimeout(function () { mapa.invalidateSize(); }, 50);
            }, function (err) {
                self._ref('mapa-geos').html('<p class="adt_sat__vacio">' + esc(err.message) + '</p>');
            });
        },

        _onGeoLista: function (ev) {
            this._abrirGeocerca(parseInt(ev.currentTarget.getAttribute('data-geo'), 10));
        },

        // ------------------------------------------------------------------
        // Drawer
        // ------------------------------------------------------------------

        _abrirDrawer: function (modo, html) {
            this._pararVivo();
            this._pararPlay();
            this._quitarMapas(['vivo', 'recorrido', 'editor']);
            this.drawerModo = modo;
            this.$el.addClass('is-drawer-open');
            this._ref('drawer').attr('class', 'adt_gps__drawer is-' + modo).html(html);
        },

        _cerrarDrawer: function () {
            this._pararVivo();
            this._pararPlay();
            this._quitarMapas(['vivo', 'recorrido', 'editor']);
            this.$el.removeClass('is-drawer-open');
            this.detalle = null;
            this.drawerModo = null;
            this._geo = null;
            this._cerrarModal();
        },

        _drawerHead: function (titulo, sub) {
            return '<header class="adt_gps__drawer-head"><div><h2>' + esc(titulo) + '</h2>' +
                (sub ? '<p class="adt_sat__sub">' + esc(sub) + '</p>' : '') + '</div>' +
                '<button type="button" class="adt_gps__close" data-action="cerrar" aria-label="Cerrar"><i class="fa fa-times"></i></button></header>';
        },

        _seccion: function (titulo, ic, cuerpo, extra) {
            return '<section class="adt_gps__sec"><h4><i class="fa ' + ic + '" aria-hidden="true"></i>' + esc(titulo) +
                (extra || '') + '</h4>' + cuerpo + '</section>';
        },

        _dl: function (filas) {
            return '<dl class="adt_gps__dl">' + filas.filter(function (f) { return f[1] !== undefined && f[1] !== null && f[1] !== ''; })
                .map(function (f) { return '<div><dt>' + esc(f[0]) + '</dt><dd>' + (f[2] ? f[1] : esc(f[1])) + '</dd></div>'; })
                .join('') + '</dl>';
        },

        _kpi: function (label, valor, ref) {
            return '<div class="adt_gps__kpi"><span>' + esc(label) + '</span><b' + (ref ? ' data-ref="' + ref + '"' : '') + '>' +
                esc(valor) + '</b></div>';
        },

        // ------------------------------------------------------------------
        // Detalle del dispositivo
        // ------------------------------------------------------------------

        _abrirDetalle: function (id, tab) {
            var self = this;
            this.dtab = tab || 'resumen';
            this._abrirDrawer('detalle', '<div class="adt_gps__drawer-body"><p class="adt_sat__vacio">Cargando…</p></div>');
            return this._llamar('gps_dispositivo', {dispositivo_id: id}).then(function (d) {
                self.detalle = d;
                self._renderDetalle();
            }, function () {
                self._cerrarDrawer();
            });
        },

        _recargarDetalle: function () {
            var self = this;
            if (!this.detalle) { return; }
            return this._llamar('gps_dispositivo', {dispositivo_id: this.detalle.id}, true).then(function (d) {
                if (self.detalle && self.detalle.id === d.id) {
                    self.detalle = d;
                    if (self.dtab === 'resumen' || self.dtab === 'historial') { self._renderDetalleTab(); }
                }
            });
        },

        _renderDetalle: function () {
            var d = this.detalle;
            var v = d.vehiculo || {};
            var self = this;
            var tabs = [['resumen', 'Resumen', 'fa-stethoscope'], ['vivo', 'En vivo', 'fa-crosshairs'],
                        ['recorrido', 'Recorrido', 'fa-road'], ['historial', 'Historial', 'fa-history']];
            this._ref('drawer').html(
                this._drawerHead(v.placa || d.nombre, (v.placa ? d.nombre + ' · ' : '') + 'IMEI ' + (d.imei || '—')) +
                '<nav class="adt_gps__dtabs" role="tablist">' + tabs.map(function (t) {
                    return '<button type="button" role="tab" data-dtab="' + t[0] + '" class="' + (self.dtab === t[0] ? 'is-active' : '') +
                        '" aria-selected="' + (self.dtab === t[0]) + '"><i class="fa ' + t[2] + '" aria-hidden="true"></i>' + t[1] + '</button>';
                }).join('') + '</nav>' +
                '<div class="adt_gps__drawer-body" data-ref="dt"></div>');
            this._renderDetalleTab();
        },

        _onDetalleTab: function (ev) {
            this.dtab = ev.currentTarget.getAttribute('data-dtab');
            this.$('[data-dtab]').each(function () {
                var activo = this.getAttribute('data-dtab') === ev.currentTarget.getAttribute('data-dtab');
                $(this).toggleClass('is-active', activo).attr('aria-selected', activo);
            });
            this._renderDetalleTab();
        },

        _renderDetalleTab: function () {
            this._pararVivo();
            this._pararPlay();
            this._quitarMapas(['vivo', 'recorrido']);
            var $dt = this._ref('dt');
            if (this.dtab === 'vivo') {
                $dt.html(this._htmlVivo());
                this._iniciarVivo();
            } else if (this.dtab === 'recorrido') {
                $dt.html(this._htmlRecorrido());
            } else if (this.dtab === 'historial') {
                $dt.html(this._htmlHistorial(this.detalle.eventos));
            } else {
                $dt.html(this._htmlResumen());
            }
        },

        _htmlResumen: function () {
            var d = this.detalle;
            var v = d.vehiculo || {};
            var manager = this.data.meta.manager;
            var nivel = d.estado === 'reportando' && !d.posicion_valida ? 'atencion' : d.nivel;
            var url = urlMapa(d.lat, d.lon);
            var botones = [];
            if (d.vehicle_id) {
                botones.push(boton('data-d-action="ficha"', 'Ficha Flota 360', 'fa-id-card-o', ''));
                botones.push(boton('data-d-action="vincular"', 'Cambiar vehículo', 'fa-exchange'));
                botones.push(boton('data-d-action="quitar"', 'Quitar relación', 'fa-chain-broken'));
            } else {
                if (d.puede_crear && manager) {
                    botones.push(boton('data-d-action="crear"', 'Crear vehículo ' + d.placa_detectada + ' en Odoo', 'fa-plus', ''));
                }
                botones.push(boton('data-d-action="vincular"', 'Relacionar con un vehículo', 'fa-link', d.puede_crear && manager ? undefined : ''));
            }
            if (d.manual) {
                botones.push(boton('data-d-action="auto"', 'Relación automática', 'fa-magic'));
            }
            var vehiculo = d.vehicle_id ? this._dl([
                ['Placa', v.placa || '—'], ['Modelo', v.vehiculo], ['Cliente', v.cliente || 'Sin cliente'],
                ['Teléfono', v.telefono ? '<a href="tel:' + esc(v.telefono) + '">' + esc(v.telefono) + '</a>' : '', true],
                ['Chasis', v.chasis], ['Relación', d.metodo_label + (d.placa_detectada ? ' (' + d.placa_detectada + ')' : '')],
                ['Nota', d.nota],
            ]) : '<p class="adt_gps__nota">' + icono(d.metodo === 'ambiguo' ? 'atencion' : 'neutral') + '<span>' +
                (d.metodo === 'ambiguo' ? 'Varias placas de Odoo coinciden con el nombre; relaciónalo a mano. ' + esc(d.nota)
                    : 'Ninguna placa de Odoo coincide con «' + esc(d.nombre) + '»' + (d.placa_detectada ? ' (placa leída: ' +
                        esc(d.placa_detectada) + ')' : '') + '. Se sigue monitoreando igual.' + (d.manual ? ' ' + esc(d.nota) : '')) + '</span></p>';
            var otros = d.otros.length ? '<p class="adt_gps__nota">' + icono('atencion') + '<span>Este vehículo tiene otros equipos: ' +
                d.otros.map(function (o) { return esc(o.nombre) + ' (' + esc(ESTADO_LABEL[o.estado] || o.estado) + ')'; }).join(', ') + '</span></p>' : '';
            var geos = d.geocercas.length ? '<div class="adt_gps__chips">' + d.geocercas.map(function (g) {
                return '<span class="adt_gps__chip-geo"><i style="background:' + esc(g.color) + '"></i>' + esc(g.name) + '</span>';
            }).join('') + '</div>' : '<p class="adt_sat__muted">Fuera de todas las geocercas.</p>';
            var posicion = '<div class="adt_gps__kpis">' +
                this._kpi('Velocidad', Math.round(d.velocidad || 0) + ' km/h') +
                this._kpi('Ignición', d.ignicion === 'on' ? 'Encendido' : (d.ignicion === 'off' ? 'Apagado' : '—')) +
                this._kpi('Batería GPS', d.bateria ? Math.round(d.bateria) + ' %' : '—') +
                this._kpi('Voltaje', d.voltaje ? d.voltaje.toFixed(1) + ' V' : '—') +
                this._kpi('Satélites', d.satelites || '—') +
                this._kpi('Km', d.km_total ? entero(Math.round(d.km_total)) : '—') + '</div>' +
                this._dl([
                    ['Posición', d.posicion_valida ? 'Válida' : 'Sin señal GPS'],
                    ['Fecha de la posición', d.ultima_posicion ? fechaHora(d.ultima_posicion) : ''],
                    ['Dirección', d.direccion], ['Última alarma', d.alarma],
                    ['Coordenadas', url ? '<a href="' + url + '" target="_blank" rel="noopener">' + d.lat.toFixed(5) + ', ' +
                        d.lon.toFixed(5) + ' <i class="fa fa-external-link" aria-hidden="true"></i></a>' : '', true],
                ]);
            var equipo = this._dl([
                ['IMEI', d.imei], ['ID en Traccar', String(d.traccar_id)], ['Conexión', d.conexion], ['Grupo', d.grupo],
                ['Chip / teléfono', d.telefono_chip], ['Modelo', d.modelo_equipo], ['Protocolo', d.protocolo],
                ['Contacto', d.contacto], ['Categoría', d.categoria], ['Leído de Traccar', fechaHora(d.sincronizado)],
            ]);
            var atributos = _.keys(d.atributos).length ? '<details class="adt_gps__attrs"><summary>Datos crudos de la última ' +
                'posición</summary>' + this._dl(_.map(_.keys(d.atributos).sort(), function (k) { return [k, String(d.atributos[k])]; })) +
                '</details>' : '';
            return '<div class="adt_gps__diag is-' + nivel + '">' + chipEstado(d.estado, nivel, d.estado_label) +
                    '<p class="adt_gps__diag-motivo">' + esc(d.motivo) + '</p>' +
                    '<p class="adt_sat__sub">Último reporte: ' + fechaHora(d.ultimo) + ' (' + esc(hace(d.ultimo)) + ')' +
                        (d.desde ? ' · en este estado desde ' + fechaHora(d.desde) : '') + '</p>' +
                    (d.detalle.length > 1 ? '<ul class="adt_gps__hechos">' + d.detalle.map(function (h) {
                        return '<li>' + esc(h) + '</li>';
                    }).join('') + '</ul>' : '') +
                    (!d.activo ? '<p class="adt_gps__nota">' + icono('neutral') + '<span>Este dispositivo ya no existe en Traccar.</span></p>' : '') +
                '</div>' +
                '<div class="adt_gps__acciones">' +
                    boton('data-dtab="vivo"', 'Ubicación en vivo', 'fa-crosshairs') +
                    boton('data-dtab="recorrido"', 'Ver recorrido', 'fa-road') +
                    (d.traccar_url ? '<a class="adt_cart__btn adt_cart__btn--ghost" href="' + esc(d.traccar_url) +
                        '" target="_blank" rel="noopener"><i class="fa fa-external-link" aria-hidden="true"></i>Abrir Traccar</a>' : '') +
                '</div>' +
                this._seccion('Vehículo en Odoo', 'fa-motorcycle', vehiculo + otros + '<div class="adt_gps__acciones">' + botones.join('') + '</div>') +
                this._seccion('Geocercas', 'fa-dot-circle-o', geos) +
                this._seccion('Última posición', 'fa-map-marker', posicion) +
                this._seccion('Equipo', 'fa-microchip', equipo + atributos);
        },

        _htmlHistorial: function (eventos) {
            return eventos.length ? '<ol class="adt_gps__eventos">' + eventos.map(function (e) {
                return '<li class="is-' + e.nivel + '">' + icono(e.nivel) + '<div><b>' + esc(e.tipo_label) + '</b>' +
                    '<span class="adt_sat__sub">' + fechaHora(e.fecha) + ' · ' + esc(e.mensaje) + '</span></div></li>';
            }).join('') + '</ol>' : '<p class="adt_sat__vacio">Sin eventos registrados.</p>';
        },

        // --- En vivo ------------------------------------------------------

        _htmlVivo: function () {
            return '<div class="adt_gps__vivo-head"><span class="adt_gps__rt is-on" data-ref="vivo-estado">' +
                '<i class="fa fa-circle" aria-hidden="true"></i>Conectando…</span>' +
                '<label class="adt_gps__check-label"><input type="checkbox" data-ref="vivo-seguir" checked="checked"/> Seguir al vehículo</label></div>' +
                '<div class="adt_gps__mapa is-drawer" data-ref="mapa-vivo"></div>' +
                '<div class="adt_gps__kpis">' +
                    this._kpi('Velocidad', '—', 'v-vel') + this._kpi('Ignición', '—', 'v-ign') +
                    this._kpi('Último dato', '—', 'v-ult') + this._kpi('Batería GPS', '—', 'v-bat') +
                    this._kpi('Voltaje', '—', 'v-volt') + this._kpi('Estado', '—', 'v-est') + '</div>' +
                '<p class="adt_sat__sub" data-ref="v-dir"></p>' +
                '<p class="adt_sat__muted">Se actualiza cada ' + (VIVO_MS / 1000) + ' s directamente desde Traccar mientras esta ' +
                'pestaña está abierta.</p>';
        },

        _iniciarVivo: function () {
            var self = this;
            var id = this.detalle.id;
            Mapa.cargar().then(function (L) {
                if (!self.detalle || self.detalle.id !== id || self.dtab !== 'vivo') { return; }
                self._mapas.vivo = Mapa.crear(L, self._ref('mapa-vivo')[0]);
                self._vivo = {L: L, rastro: L.polyline([], {color: '#1c7ed6', weight: 4, opacity: 0.7}).addTo(self._mapas.vivo),
                              marca: null, primero: true};
                _.each(self.data.geocercas, function (g) { Mapa.capaGeocerca(L, g).addTo(self._mapas.vivo); });
                setTimeout(function () { if (self._mapas.vivo) { self._mapas.vivo.invalidateSize(); } }, 250);
                self._tickVivo();
                self._vivoTimer = setInterval(function () { self._tickVivo(); }, VIVO_MS);
            }, function (err) {
                self._ref('mapa-vivo').html('<p class="adt_sat__vacio">' + esc(err.message) + '</p>');
            });
        },

        _tickVivo: function () {
            var self = this;
            if (!this._vivo || !this.detalle || this._vivoOcupado) { return; }
            var id = this.detalle.id;
            this._vivoOcupado = true;
            this._llamar('gps_en_vivo', {dispositivo_id: id}, true).then(function (p) {
                self._vivoOcupado = false;
                if (!self._vivo || !self.detalle || self.detalle.id !== id) { return; }
                var L = self._vivo.L;
                var nivel = p.estado === 'reportando' && !p.valida ? 'atencion' : p.nivel;
                self._ref('vivo-estado').attr('class', 'adt_gps__rt is-on is-' + nivel)
                    .html('<i class="fa fa-circle" aria-hidden="true"></i>' + esc(p.estado_label) + ' · actualizado ' + moment().format('HH:mm:ss'));
                self._ref('v-vel').text(Math.round(p.velocidad || 0) + ' km/h');
                self._ref('v-ign').text(p.ignicion === 'on' ? 'Encendido' : (p.ignicion === 'off' ? 'Apagado' : '—'));
                self._ref('v-ult').text(hace(p.ultimo));
                self._ref('v-bat').text(p.bateria ? Math.round(p.bateria) + ' %' : '—');
                self._ref('v-volt').text(p.voltaje ? p.voltaje.toFixed(1) + ' V' : '—');
                self._ref('v-est').text(p.valida ? 'GPS válido' : 'Sin señal GPS');
                self._ref('v-dir').text(p.direccion || '');
                if (!p.lat && !p.lon) { return; }
                var punto = [p.lat, p.lon];
                var icon = Mapa.iconoVehiculo(L, nivel, p.curso);
                if (!self._vivo.marca) {
                    self._vivo.marca = L.marker(punto, {icon: icon}).addTo(self._mapas.vivo);
                } else {
                    self._vivo.marca.setLatLng(punto).setIcon(icon);
                }
                var ultimos = self._vivo.rastro.getLatLngs();
                var ult = ultimos[ultimos.length - 1];
                if (!ult || ult.lat !== p.lat || ult.lng !== p.lon) { self._vivo.rastro.addLatLng(punto); }
                if (self._vivo.primero) {
                    self._mapas.vivo.setView(punto, 16);
                    self._vivo.primero = false;
                } else if (self._ref('vivo-seguir').is(':checked')) {
                    self._mapas.vivo.panTo(punto);
                }
            }, function () {
                self._vivoOcupado = false;
                self._ref('vivo-estado').attr('class', 'adt_gps__rt').html('<i class="fa fa-circle-o"></i>Sin respuesta de Traccar; reintentando…');
            });
        },

        _pararVivo: function () {
            clearInterval(this._vivoTimer);
            this._vivoTimer = null;
            this._vivo = null;
            this._vivoOcupado = false;
        },

        // --- Recorrido ----------------------------------------------------

        _htmlRecorrido: function () {
            var desde = this._rDesde || moment().startOf('day');
            var hasta = this._rHasta || moment();
            return '<div class="adt_gps__rango">' +
                '<div class="adt_gps__presets">' + PRESETS.map(function (p) {
                    return '<button type="button" data-preset="' + p[0] + '">' + p[1] + '</button>';
                }).join('') + '</div>' +
                '<div class="adt_gps__fechas">' +
                    '<label class="adt_gps__campo"><span>Desde</span><input type="datetime-local" data-ref="r-desde" value="' + localInput(desde) + '"/></label>' +
                    '<label class="adt_gps__campo"><span>Hasta</span><input type="datetime-local" data-ref="r-hasta" value="' + localInput(hasta) + '"/></label>' +
                    boton('data-r-action="ver"', 'Ver recorrido', 'fa-road', '') +
                '</div><p class="adt_sat__muted">Hasta 7 días por consulta. Los datos se leen de Traccar.</p></div>' +
                '<div data-ref="r-res"></div>';
        },

        _onPreset: function (ev) {
            var p = ev.currentTarget.getAttribute('data-preset');
            var ahora = moment();
            var rango = {hoy: [moment().startOf('day'), ahora], ayer: [moment().subtract(1, 'day').startOf('day'), moment().startOf('day')],
                         '24h': [moment().subtract(24, 'hours'), ahora], '7d': [moment().subtract(7, 'days'), ahora]}[p];
            this._ref('r-desde').val(localInput(rango[0]));
            this._ref('r-hasta').val(localInput(rango[1]));
            this._cargarRecorrido();
        },

        _onRecorridoAccion: function (ev) {
            var a = ev.currentTarget.getAttribute('data-r-action');
            if (a === 'ver') {
                this._cargarRecorrido();
            } else if (a === 'play') {
                if (this._playTimer) { this._pararPlay(); } else { this._play(); }
            } else if (a === 'parada') {
                var i = parseInt(ev.currentTarget.getAttribute('data-i'), 10);
                var s = this._recorrido && this._recorrido.paradas[i];
                if (s && this._mapas.recorrido) { this._mapas.recorrido.setView([s.lat, s.lon], 17); }
            }
        },

        _cargarRecorrido: function () {
            var self = this;
            var desde = this._ref('r-desde').val();
            var hasta = this._ref('r-hasta').val();
            if (!desde || !hasta) { return; }
            this._rDesde = moment(desde);
            this._rHasta = moment(hasta);
            this._pararPlay();
            this._quitarMapas(['recorrido']);
            var id = this.detalle.id;
            this._ref('r-res').html('<p class="adt_sat__vacio"><i class="fa fa-spinner fa-spin"></i> Consultando Traccar…</p>');
            Promise.all([Mapa.cargar(), this._llamar('gps_recorrido', {dispositivo_id: id, desde: aUtc(desde), hasta: aUtc(hasta)})])
                .then(function (res) {
                    if (!self.detalle || self.detalle.id !== id || self.dtab !== 'recorrido') { return; }
                    self._pintarRecorrido(res[0], res[1]);
                }, function (err) {
                    var msg = (err && err.message && err.message.data && err.message.data.message) || (err && err.message) || '';
                    self._ref('r-res').html('<p class="adt_sat__vacio">' + icono('critico') + esc(typeof msg === 'string' ? msg : 'No se pudo consultar el recorrido.') + '</p>');
                });
        },

        _pintarRecorrido: function (L, r) {
            this._recorrido = r;
            var res = r.resumen;
            var self = this;
            if (!r.puntos.length) {
                this._ref('r-res').html('<p class="adt_sat__vacio">' + icono('neutral') + 'El equipo no envió posiciones en ese rango.</p>' +
                    (r.eventos.length ? this._seccion('Eventos del rango', 'fa-history', this._htmlHistorial(r.eventos)) : ''));
                return;
            }
            this._ref('r-res').html(
                '<div class="adt_gps__kpis">' +
                    this._kpi('Distancia', res.distancia_km.toLocaleString('es-PE') + ' km') +
                    this._kpi('Vel. máxima', res.vel_max + ' km/h') +
                    this._kpi('En movimiento', duracion(res.minutos_movimiento)) +
                    this._kpi('Viajes', entero(res.viajes)) + this._kpi('Paradas', entero(res.paradas)) +
                    this._kpi('Posiciones', entero(r.total_puntos)) + '</div>' +
                '<div class="adt_gps__mapa is-drawer" data-ref="mapa-recorrido"></div>' +
                '<div class="adt_gps__play">' +
                    '<button type="button" class="adt_gps__close" data-r-action="play" data-ref="r-play" aria-label="Reproducir"><i class="fa fa-play"></i></button>' +
                    '<input type="range" min="0" max="' + (r.puntos.length - 1) + '" value="0" data-ref="r-slider" aria-label="Recorrer el trayecto"/>' +
                    '<span data-ref="r-pos" class="adt_gps__play-txt"></span></div>' +
                (r.paradas.length ? this._seccion('Paradas', 'fa-pause-circle', '<ol class="adt_gps__paradas">' + r.paradas.map(function (s, i) {
                    return '<li><button type="button" data-r-action="parada" data-i="' + i + '"><b>' + hora(s.desde) + ' → ' + hora(s.hasta) +
                        '</b> · ' + duracion(s.minutos) + '<span class="adt_sat__sub">' + esc(s.direccion || (s.lat.toFixed(5) + ', ' + s.lon.toFixed(5))) +
                        '</span></button></li>';
                }).join('') + '</ol>') : '') +
                (r.eventos.length ? this._seccion('Eventos del rango', 'fa-history', this._htmlHistorial(r.eventos)) : ''));
            var mapa = this._mapas.recorrido = Mapa.crear(L, this._ref('mapa-recorrido')[0]);
            var latlngs = r.puntos.map(function (p) { return [p[0], p[1]]; });
            var linea = L.polyline(latlngs, {color: '#1c7ed6', weight: 4, opacity: 0.8}).addTo(mapa);
            Mapa.marcador(L, latlngs[0][0], latlngs[0][1], 'ok', {radius: 8}).bindTooltip('Inicio ' + hora(r.puntos[0][2])).addTo(mapa);
            var fin = r.puntos[r.puntos.length - 1];
            Mapa.marcador(L, fin[0], fin[1], 'critico', {radius: 8}).bindTooltip('Fin ' + hora(fin[2])).addTo(mapa);
            _.each(r.paradas, function (s) {
                L.circleMarker([s.lat, s.lon], {radius: 6, color: '#fff', weight: 2, fillColor: '#e67700', fillOpacity: 1})
                    .bindPopup('<b>Parada · ' + duracion(s.minutos) + '</b><br/>' + hora(s.desde) + ' → ' + hora(s.hasta) +
                        '<br/>' + esc(s.direccion || '')).addTo(mapa);
            });
            this._playMarca = L.marker(latlngs[0], {icon: Mapa.iconoVehiculo(L, 'info', 0)}).addTo(mapa);
            mapa.fitBounds(linea.getBounds().pad(0.1));
            setTimeout(function () { if (self._mapas.recorrido) { self._mapas.recorrido.invalidateSize(); } }, 250);
            this._moverPlay(0);
        },

        _moverPlay: function (i) {
            var r = this._recorrido;
            if (!r || !this._playMarca) { return; }
            var p = r.puntos[i];
            this._playMarca.setLatLng([p[0], p[1]]);
            this._ref('r-slider').val(i);
            this._ref('r-pos').text(hora(p[2]) + ' · ' + p[3] + ' km/h' + (p[4] === true ? ' · encendido' : (p[4] === false ? ' · apagado' : '')));
        },

        _onSlider: function (ev) {
            this._moverPlay(parseInt(ev.currentTarget.value, 10));
        },

        _play: function () {
            var self = this;
            var r = this._recorrido;
            if (!r) { return; }
            var i = parseInt(this._ref('r-slider').val(), 10) || 0;
            if (i >= r.puntos.length - 1) { i = 0; }
            var paso = Math.max(1, Math.round(r.puntos.length / 400));
            this._ref('r-play').html('<i class="fa fa-pause"></i>');
            this._playTimer = setInterval(function () {
                i = Math.min(i + paso, r.puntos.length - 1);
                self._moverPlay(i);
                if (self._mapas.recorrido && !self._mapas.recorrido.getBounds().contains(self._playMarca.getLatLng())) {
                    self._mapas.recorrido.panTo(self._playMarca.getLatLng());
                }
                if (i >= r.puntos.length - 1) { self._pararPlay(); }
            }, 80);
        },

        _pararPlay: function () {
            clearInterval(this._playTimer);
            this._playTimer = null;
            this._ref('r-play').html('<i class="fa fa-play"></i>');
        },

        // --- Acciones del detalle -----------------------------------------

        _onDrawerAccion: function (ev) {
            var accion = ev.currentTarget.getAttribute('data-d-action');
            var d = this.detalle;
            if (!d) { return; }
            if (accion === 'ficha') {
                this.do_action({type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                                params: {vehicle_id: d.vehicle_id, tab: 'gps'}});
            } else if (accion === 'vincular') {
                this._abrirVincular();
            } else if (accion === 'quitar') {
                this._guardarVinculo(this._llamar('gps_vincular', {dispositivo_id: d.id, vehicle_id: false}),
                                     'Relación quitada: el dispositivo queda sin vehículo (se sigue monitoreando).');
            } else if (accion === 'auto') {
                this._guardarVinculo(this._llamar('gps_vinculo_automatico', {dispositivo_id: d.id}), 'Relación automática restablecida.');
            } else if (accion === 'crear') {
                this._confirmarCrear([d.id]);
            }
        },

        _guardarVinculo: function (promesa, mensaje) {
            var self = this;
            return promesa.then(function (d) {
                self.detalle = d;
                self._cerrarModal();
                self._renderDetalle();
                self.displayNotification({type: 'success', message: mensaje});
                return self._autoRefresco(true);
            });
        },

        // ------------------------------------------------------------------
        // Configuración (drawer)
        // ------------------------------------------------------------------

        _abrirConfig: function () {
            var self = this;
            this._abrirDrawer('config', '<div class="adt_gps__drawer-body"><p class="adt_sat__vacio">Cargando…</p></div>');
            this._llamar('gps_config').then(function (c) {
                self._cfg = c;
                self._renderConfig();
            });
        },

        _renderConfig: function () {
            var c = this._cfg;
            var campo = function (nombre, label, valor, ayuda) {
                return '<label class="adt_gps__campo"><span>' + esc(label) + '</span><input type="number" min="1" step="1" ' +
                    'name="' + nombre + '" value="' + esc(valor || '') + '"/>' + (ayuda ? '<small>' + esc(ayuda) + '</small>' : '') + '</label>';
            };
            var check = function (nombre, valor, label, marcado, ayuda) {
                return '<label class="adt_gps__check-label"><input type="checkbox" name="' + nombre + '" value="' + esc(valor) + '"' +
                    (marcado ? ' checked="checked"' : '') + '/> ' + esc(label) + (ayuda ? ' <small class="adt_sat__muted">' + esc(ayuda) + '</small>' : '') + '</label>';
            };
            var faltan = _.filter(this.data.items, function (i) { return i.puede_crear; }).length;
            var xml = "<entry key='event.forward.enable'>true</entry>\n<entry key='event.forward.url'>" + (c.webhook_url || '') +
                "</entry>\n<!-- Opcional: cada posición al instante (geocercas sin demora) -->\n<entry key='forward.enable'>true</entry>\n" +
                "<entry key='forward.url'>" + (c.webhook_url || '') + "</entry>\n<entry key='forward.type'>json</entry>";
            var esHttps = window.location.protocol === 'https:' || window.location.hostname === 'localhost';
            this._ref('drawer').html(this._drawerHead('Configuración del monitoreo', 'Se aplica a todos los usuarios') +
                '<div class="adt_gps__drawer-body adt_gps__config">' +
                this._seccion('Tiempo real', 'fa-bolt',
                    '<div class="adt_gps__diag is-' + (c.tiempo_real ? 'ok' : 'atencion') + '">' +
                        chipEstado('', c.tiempo_real ? 'ok' : 'atencion', c.tiempo_real ? 'Webhook activo' : 'Webhook sin actividad') +
                        '<p class="adt_sat__sub">' + (c.webhook_ultimo ? 'Último evento recibido de Traccar: ' + fechaHora(c.webhook_ultimo) + ' (' + hace(c.webhook_ultimo) + ')'
                            : 'Traccar aún no ha enviado eventos a Odoo.') + ' Mientras tanto Odoo lee Traccar cada ' + (c.frecuencia || 1) + ' min.</p></div>' +
                    '<p class="adt_gps__nota"><span>Para recibir las desconexiones y alarmas al instante, agrega esto en <code>conf/traccar.xml</code> ' +
                        'del servidor de Traccar y reinícialo. Traccar debe poder llegar a esta URL (no sirve <code>localhost</code>).</span></p>' +
                    '<label class="adt_gps__campo"><span>URL del webhook</span><div class="adt_gps__copiar"><input type="text" readonly="readonly" value="' +
                        esc(c.webhook_url || '') + '" data-ref="c-url"/>' + boton('data-c-action="copiar_url"', 'Copiar', 'fa-clipboard') + '</div></label>' +
                    '<pre class="adt_gps__pre" data-ref="c-xml">' + esc(xml) + '</pre>' +
                    '<div class="adt_gps__acciones">' + boton('data-c-action="copiar_xml"', 'Copiar configuración', 'fa-clipboard') +
                        boton('data-c-action="probar"', 'Probar notificación', 'fa-paper-plane-o') +
                        boton('data-c-action="regenerar"', 'Regenerar token', 'fa-key') + '</div>' +
                    (!esHttps ? '<p class="adt_gps__nota">' + icono('atencion') + '<span>Esta página no está en HTTPS: el navegador no permite ' +
                        'sus notificaciones del sistema. Las alertas se verán dentro de Odoo.</span></p>' : '')) +
                this._seccion('Alertas', 'fa-bell',
                    '<p class="adt_sat__muted">Qué avisa en tiempo real (notificación del navegador y dentro de Odoo).</p>' +
                    '<div class="adt_gps__checks">' + c.tipos_alerta.map(function (t) {
                        return check('alertas', t.id, t.label, c.alertas.indexOf(t.id) !== -1);
                    }).join('') + '</div>' +
                    '<p class="adt_sat__muted">Alarmas del equipo que avisan:</p><div class="adt_gps__checks is-cols">' + c.tipos_alarma.map(function (t) {
                        return check('alarmas', t.id, t.label.split(':')[0], c.alarmas.indexOf(t.id) !== -1);
                    }).join('') + '</div>' +
                    '<p class="adt_sat__muted">Quiénes reciben las alertas (ninguno marcado = todos los usuarios de Flota):</p>' +
                    '<div class="adt_gps__checks is-cols">' + (c.usuarios || []).map(function (u) {
                        return check('destinatarios', u.id, u.name, c.destinatarios.indexOf(u.id) !== -1);
                    }).join('') + '</div>') +
                this._seccion('Umbrales y frecuencia', 'fa-clock-o', '<div class="adt_gps__campos">' +
                    campo('minutos_demora', 'Demorado desde (min)', c.minutos_demora, 'Sin datos desde hace estos minutos: atención.') +
                    campo('minutos_sin_reporte', 'Sin reportar desde (min)', c.minutos_sin_reporte, 'Desde aquí se alerta «dejó de reportar».') +
                    campo('frecuencia', 'Leer Traccar cada (min)', c.frecuencia, 'Respaldo del webhook (1 a 60).') + '</div>') +
                this._seccion('Vehículos que faltan en Odoo', 'fa-plus-square',
                    '<label class="adt_gps__campo"><span>Modelo con el que se crean</span><select name="modelo_id"><option value="0">— Elegir —</option>' +
                        (c.modelos || []).map(function (m) {
                            return '<option value="' + m.id + '"' + (m.id === c.modelo_id ? ' selected="selected"' : '') + '>' + esc(m.name) + '</option>';
                        }).join('') + '</select><small>Luego puedes corregir el modelo de cada vehículo.</small></label>' +
                    check('crear_vehiculos', '1', 'Crear automáticamente en cada sincronización los vehículos que solo existen en Traccar',
                          c.crear_vehiculos, '(solo si la placa leída tiene forma de placa)') +
                    '<div class="adt_gps__acciones">' + boton('data-c-action="crear_ahora"', faltan ? 'Crear ahora los ' + entero(faltan) + ' que faltan'
                        : 'No hay vehículos por crear', 'fa-plus') + '</div>') +
                this._seccion('Lectura de la placa', 'fa-id-card-o',
                    '<label class="adt_gps__campo"><span>Palabras que se quitan del nombre del dispositivo</span>' +
                    '<textarea name="palabras_ruido" rows="4">' + esc(c.palabras_ruido) + '</textarea>' +
                    '<small>Separadas por espacios o comas. Ej.: «XYAZ12 - nuevo» → XYAZ12. Al cambiarlas se recalculan las relaciones automáticas.</small></label>') +
                '</div>' +
                '<footer class="adt_gps__drawer-foot">' + boton('data-action="cerrar"', 'Cancelar') +
                    boton('data-c-action="guardar"', 'Guardar', 'fa-check', '') + '</footer>');
        },

        _valoresConfig: function () {
            var $d = this._ref('drawer');
            var marcados = function (n) {
                return $d.find('input[name="' + n + '"]:checked').map(function () { return this.value; }).get();
            };
            return {
                minutos_demora: $d.find('[name="minutos_demora"]').val(),
                minutos_sin_reporte: $d.find('[name="minutos_sin_reporte"]').val(),
                frecuencia: $d.find('[name="frecuencia"]').val(),
                palabras_ruido: $d.find('[name="palabras_ruido"]').val(),
                alertas: marcados('alertas'), alarmas: marcados('alarmas'),
                destinatarios: marcados('destinatarios').map(Number),
                crear_vehiculos: $d.find('[name="crear_vehiculos"]').is(':checked'),
                modelo_id: parseInt($d.find('[name="modelo_id"]').val(), 10) || 0,
            };
        },

        _onConfigAccion: function (ev) {
            var self = this;
            var a = ev.currentTarget.getAttribute('data-c-action');
            var copiar = function (texto) {
                (navigator.clipboard ? navigator.clipboard.writeText(texto) : Promise.reject()).then(function () {
                    self.displayNotification({type: 'success', message: 'Copiado.'});
                }, function () {
                    self.displayNotification({type: 'warning', message: 'Selecciona el texto y cópialo a mano.'});
                });
            };
            if (a === 'copiar_url') {
                copiar(this._ref('c-url').val());
            } else if (a === 'copiar_xml') {
                copiar(this._ref('c-xml').text());
            } else if (a === 'probar') {
                this._onProbar();
            } else if (a === 'regenerar') {
                this._modal('Regenerar el token del webhook', '<p>La URL actual dejará de funcionar: tendrás que actualizarla en ' +
                    '<code>traccar.xml</code> y reiniciar Traccar.</p>', boton('data-m-action="cerrar"', 'Cancelar') +
                    boton('data-m-action="regenerar"', 'Regenerar', 'fa-key', ''));
            } else if (a === 'guardar' || a === 'crear_ahora') {
                this._llamar('gps_config_guardar', {valores: this._valoresConfig()}).then(function (c) {
                    self._cfg = c;
                    self.data.meta = _.extend(self.data.meta, c);
                    if (a === 'crear_ahora') {
                        self._cerrarDrawer();
                        self._confirmarCrear(_.pluck(_.filter(self.data.items, function (i) { return i.puede_crear; }), 'id'));
                        return;
                    }
                    self._cerrarDrawer();
                    self.displayNotification({type: 'success', message: 'Configuración guardada.'});
                    return self._recargar();
                });
            }
        },

        // ------------------------------------------------------------------
        // Editor de geocercas (drawer)
        // ------------------------------------------------------------------

        _abrirGeocerca: function (id) {
            var g = id ? _.findWhere(this.data.geocercas, {id: id}) : null;
            var manager = this.data.meta.manager;
            this._geo = g ? _.extend({}, g, {puntos: g.puntos.slice(), dispositivos: _.object(g.dispositivos, g.dispositivos.map(function () { return true; }))})
                : {id: null, name: '', descripcion: '', color: '#d9480f', tipo: 'circulo', lat: 0, lon: 0, radio: 300, puntos: [],
                   entrada: true, salida: true, alcance: 'todos', dispositivos: {}, publicar: true};
            var geo = this._geo;
            var lectura = !manager;
            var dis = lectura ? ' disabled="disabled"' : '';
            this._abrirDrawer('geocerca', this._drawerHead(g ? g.name : 'Nueva geocerca',
                    lectura ? 'Solo lectura: los administradores de Flota pueden editarla' : 'Dibuja la zona en el mapa') +
                '<div class="adt_gps__drawer-body">' +
                    '<div class="adt_gps__seg" role="group" aria-label="Forma">' +
                        '<button type="button" data-g-action="tipo" data-v="circulo" class="' + (geo.tipo === 'circulo' ? 'is-active' : '') + '"' + dis + '>' +
                            '<i class="fa fa-circle-thin"></i> Círculo</button>' +
                        '<button type="button" data-g-action="tipo" data-v="poligono" class="' + (geo.tipo === 'poligono' ? 'is-active' : '') + '"' + dis + '>' +
                            '<i class="fa fa-object-ungroup"></i> Polígono</button></div>' +
                    '<p class="adt_sat__muted" data-ref="g-ayuda"></p>' +
                    '<div class="adt_gps__mapa is-editor" data-ref="mapa-editor"></div>' +
                    '<div class="adt_gps__acciones" data-ref="g-herr"></div>' +
                    '<div class="adt_gps__campos">' +
                        '<label class="adt_gps__campo is-span2"><span>Nombre</span><input type="text" data-g="name" value="' + esc(geo.name) + '"' + dis + '/></label>' +
                        '<label class="adt_gps__campo"><span>Color</span><input type="color" data-g="color" value="' + esc(geo.color) + '"' + dis + '/></label>' +
                    '</div>' +
                    '<label class="adt_gps__campo"><span>Descripción</span><input type="text" data-g="descripcion" value="' + esc(geo.descripcion) + '"' + dis + '/></label>' +
                    '<div class="adt_gps__checks">' +
                        '<label class="adt_gps__check-label"><input type="checkbox" data-g="entrada"' + (geo.entrada ? ' checked="checked"' : '') + dis + '/> Alertar cuando un vehículo entra</label>' +
                        '<label class="adt_gps__check-label"><input type="checkbox" data-g="salida"' + (geo.salida ? ' checked="checked"' : '') + dis + '/> Alertar cuando un vehículo sale</label>' +
                        '<label class="adt_gps__check-label"><input type="checkbox" data-g="publicar"' + (geo.publicar ? ' checked="checked"' : '') + dis + '/> Publicar también en Traccar</label>' +
                    '</div>' +
                    (g && g.traccar_error ? '<p class="adt_gps__nota">' + icono('critico') + '<span>' + esc(g.traccar_error) + '</span></p>' : '') +
                    '<label class="adt_gps__campo"><span>Aplica a</span><select data-g="alcance"' + dis + '>' +
                        '<option value="todos"' + (geo.alcance === 'todos' ? ' selected="selected"' : '') + '>Todos los dispositivos</option>' +
                        '<option value="seleccion"' + (geo.alcance === 'seleccion' ? ' selected="selected"' : '') + '>Solo los que elija</option></select></label>' +
                    '<div data-ref="g-disp"></div>' +
                '</div>' +
                (manager ? '<footer class="adt_gps__drawer-foot">' + (g ? boton('data-g-action="eliminar"', 'Eliminar', 'fa-trash', 'adt_cart__btn--ghost adt_gps__btn-peligro') : '') +
                    '<span class="adt_gps__spacer"></span>' + boton('data-action="cerrar"', 'Cancelar') +
                    boton('data-g-action="guardar"', 'Guardar geocerca', 'fa-check', '') + '</footer>' : ''));
            this._renderGeoHerramientas();
            this._renderGeoDispositivos();
            var self = this;
            Mapa.cargar().then(function (L) {
                if (!self._geo || self.drawerModo !== 'geocerca') { return; }
                var mapa = self._mapas.editor = Mapa.crear(L, self._ref('mapa-editor')[0]);
                self._geoCapa = L.layerGroup().addTo(mapa);
                // Otras geocercas como referencia, en gris.
                _.each(self.data.geocercas, function (o) {
                    if (o.id !== geo.id) { Mapa.capaGeocerca(L, _.extend({}, o, {color: '#868e96'}), {fillOpacity: 0.05, dashArray: '4'}).addTo(mapa); }
                });
                if (!lectura) { mapa.on('click', function (e) { self._onGeoMapaClick(e.latlng); }); }
                self._pintarGeo(true);
                setTimeout(function () { if (self._mapas.editor) { self._mapas.editor.invalidateSize(); } }, 250);
            }, function (err) {
                self._ref('mapa-editor').html('<p class="adt_sat__vacio">' + esc(err.message) + '</p>');
            });
        },

        _renderGeoHerramientas: function () {
            var geo = this._geo;
            var manager = this.data.meta.manager;
            this._ref('g-ayuda').text(!manager ? '' : (geo.tipo === 'circulo'
                ? 'Haz clic en el mapa para ubicar el centro y ajusta el radio.'
                : 'Haz clic en el mapa para agregar los vértices del polígono (mínimo 3).'));
            if (!manager) { this._ref('g-herr').empty(); return; }
            this._ref('g-herr').html(geo.tipo === 'circulo'
                ? '<label class="adt_gps__radio"><span>Radio</span><input type="range" min="20" max="5000" step="10" data-g="radio" value="' +
                    Math.min(geo.radio, 5000) + '"/><input type="number" min="10" max="100000" step="10" data-g="radio" value="' + Math.round(geo.radio) +
                    '"/> m</label>'
                : boton('data-g-action="deshacer"', 'Deshacer punto', 'fa-undo') + boton('data-g-action="limpiar"', 'Borrar polígono', 'fa-eraser') +
                    '<span class="adt_sat__muted">' + plural(geo.puntos.length, 'punto', 'puntos') + '</span>');
        },

        _renderGeoDispositivos: function () {
            var geo = this._geo;
            if (!geo) { return; }
            var $c = this._ref('g-disp');
            if (geo.alcance !== 'seleccion') { $c.empty(); return; }
            var q = normalizar(this._ref('g-buscar').val() || '');
            var items = this.data.items.filter(function (i) {
                return !q || normalizar(i.placa + i.nombre + i.placa_detectada).indexOf(q) !== -1;
            }).slice(0, 200);
            var dis = this.data.meta.manager ? '' : ' disabled="disabled"';
            var lista = '<ul class="adt_gps__gdisp">' + items.map(function (i) {
                return '<li><label><input type="checkbox" data-gd="' + i.id + '"' + (geo.dispositivos[i.id] ? ' checked="checked"' : '') + dis + '/> ' +
                    '<b>' + esc(i.placa || i.nombre) + '</b> <span class="adt_sat__muted">' + esc(i.placa ? i.nombre : '') + '</span></label></li>';
            }).join('') + '</ul>';
            if (!this._ref('g-buscar').length) {
                $c.html('<label class="adt_gps__search is-wide"><i class="fa fa-search" aria-hidden="true"></i><input type="search" ' +
                    'data-ref="g-buscar" placeholder="Buscar placa" aria-label="Buscar dispositivo"/></label>' +
                    '<p class="adt_sat__muted" data-ref="g-nsel"></p><div data-ref="g-lista"></div>');
            }
            this._ref('g-lista').html(lista);
            this._ref('g-nsel').text(plural(_.size(geo.dispositivos), 'dispositivo elegido', 'dispositivos elegidos'));
        },

        _onGeoDispositivo: function (ev) {
            var id = parseInt(ev.currentTarget.getAttribute('data-gd'), 10);
            if (ev.currentTarget.checked) { this._geo.dispositivos[id] = true; } else { delete this._geo.dispositivos[id]; }
            this._ref('g-nsel').text(plural(_.size(this._geo.dispositivos), 'dispositivo elegido', 'dispositivos elegidos'));
        },

        _onGeoCampo: function (ev) {
            var geo = this._geo;
            if (!geo) { return; }
            var campo = ev.currentTarget.getAttribute('data-g');
            var el = ev.currentTarget;
            if (el.type === 'checkbox') {
                geo[campo] = el.checked;
            } else if (campo === 'radio') {
                geo.radio = parseFloat(el.value) || 0;
                this._ref('g-herr').find('[data-g="radio"]').not(el).val(Math.round(geo.radio));
                this._pintarGeo(false);
            } else {
                geo[campo] = el.value;
                if (campo === 'color') { this._pintarGeo(false); }
                if (campo === 'alcance') { this._renderGeoDispositivos(); }
            }
        },

        _onGeoMapaClick: function (latlng) {
            var geo = this._geo;
            if (geo.tipo === 'circulo') {
                geo.lat = latlng.lat;
                geo.lon = latlng.lng;
            } else {
                geo.puntos.push([latlng.lat, latlng.lng]);
                this._renderGeoHerramientas();
            }
            this._pintarGeo(false);
        },

        _pintarGeo: function (encuadrar) {
            var geo = this._geo;
            var L = window.L;
            if (!this._geoCapa || !L) { return; }
            this._geoCapa.clearLayers();
            var capa = null;
            if (geo.tipo === 'circulo' && (geo.lat || geo.lon)) {
                capa = Mapa.capaGeocerca(L, {tipo: 'circulo', lat: geo.lat, lon: geo.lon, radio: geo.radio, color: geo.color, name: geo.name || 'Nueva'});
                L.circleMarker([geo.lat, geo.lon], {radius: 4, color: geo.color}).addTo(this._geoCapa);
            } else if (geo.tipo === 'poligono' && geo.puntos.length) {
                capa = geo.puntos.length >= 3
                    ? Mapa.capaGeocerca(L, {tipo: 'poligono', puntos: geo.puntos, color: geo.color, name: geo.name || 'Nueva'})
                    : L.polyline(geo.puntos, {color: geo.color, dashArray: '4'});
                var self = this;
                _.each(geo.puntos, function (p) { L.circleMarker(p, {radius: 4, color: geo.color}).addTo(self._geoCapa); });
            }
            if (capa) {
                capa.addTo(this._geoCapa);
                if (encuadrar) { Mapa.ajustar(this._mapas.editor, [capa], 17); }
            } else if (encuadrar && this.data.items.length) {
                Mapa.ajustar(this._mapas.editor, [], 12);
            }
        },

        _onGeoAccion: function (ev) {
            var self = this;
            var a = ev.currentTarget.getAttribute('data-g-action');
            var geo = this._geo;
            if (a === 'nueva') {
                this._abrirGeocerca(null);
                return;
            }
            if (!geo) { return; }
            if (a === 'tipo') {
                geo.tipo = ev.currentTarget.getAttribute('data-v');
                this.$('[data-g-action="tipo"]').each(function () {
                    $(this).toggleClass('is-active', this.getAttribute('data-v') === geo.tipo);
                });
                this._renderGeoHerramientas();
                this._pintarGeo(false);
            } else if (a === 'deshacer') {
                geo.puntos.pop();
                this._renderGeoHerramientas();
                this._pintarGeo(false);
            } else if (a === 'limpiar') {
                geo.puntos = [];
                this._renderGeoHerramientas();
                this._pintarGeo(false);
            } else if (a === 'eliminar') {
                this._modal('Eliminar «' + geo.name + '»', '<p>Se elimina de Odoo' + (geo.traccar_id ? ' y de Traccar' : '') +
                    '. Ya no habrá alertas de esta zona.</p>', boton('data-m-action="cerrar"', 'Cancelar') +
                    boton('data-m-action="eliminar_geo"', 'Eliminar', 'fa-trash', 'adt_gps__btn-peligro-solid'));
            } else if (a === 'guardar') {
                var valores = _.extend(_.pick(geo, 'name', 'descripcion', 'color', 'tipo', 'lat', 'lon', 'radio', 'puntos',
                    'entrada', 'salida', 'alcance', 'publicar'), {dispositivos: _.map(_.keys(geo.dispositivos), Number)});
                this._llamar('gps_geocerca_guardar', {geocerca_id: geo.id || false, valores: valores}).then(function (r) {
                    self._cerrarDrawer();
                    self.displayNotification(r.traccar_error
                        ? {type: 'warning', sticky: true, title: 'Geocerca guardada en Odoo', message: 'No se pudo publicar en Traccar: ' + r.traccar_error}
                        : {type: 'success', message: 'Geocerca guardada. Las entradas y salidas se detectan desde ahora.'});
                    return self._recargar();
                });
            }
        },

        // ------------------------------------------------------------------
        // Modales
        // ------------------------------------------------------------------

        _modal: function (titulo, cuerpo, pie) {
            this._ref('modal').html('<div class="adt_gps__modal-back" data-m-action="cerrar"></div>' +
                '<div class="adt_gps__modal" role="dialog" aria-modal="true" aria-label="' + esc(titulo) + '">' +
                '<header><h3>' + esc(titulo) + '</h3><button type="button" class="adt_gps__close" data-m-action="cerrar" ' +
                'aria-label="Cerrar"><i class="fa fa-times"></i></button></header>' +
                '<div class="adt_gps__modal-body">' + cuerpo + '</div>' + (pie ? '<footer>' + pie + '</footer>' : '') + '</div>');
            this._ref('modal').find('input, textarea').first().focus();
        },

        _cerrarModal: function () { this._ref('modal').empty(); },

        _abrirVincular: function () {
            var d = this.detalle;
            this._modal('Relacionar «' + d.nombre + '» con un vehículo',
                '<p class="adt_sat__muted">Busca por placa (con o sin guiones), chasis o cliente. La relación manual se ' +
                'conserva en las siguientes sincronizaciones.</p>' +
                '<label class="adt_gps__search is-wide"><i class="fa fa-search" aria-hidden="true"></i><input type="search" ' +
                'data-ref="buscar-vehiculo" aria-label="Buscar vehículo" value="' + esc(d.placa_detectada || '') + '"/></label>' +
                '<div data-ref="vehiculos" class="adt_gps__resultados"></div>');
            if (d.placa_detectada) { this._cargarVehiculos(); }
        },

        _onBuscarVehiculo: function () { this._buscarVehiculoDiferido(); },

        _cargarVehiculos: function () {
            var self = this;
            var $in = this._ref('buscar-vehiculo');
            if (!$in.length) { return; }
            var texto = $in.val();
            var seq = this._seqVeh = (this._seqVeh || 0) + 1;
            if ((texto || '').trim().length < 2) {
                this._ref('vehiculos').html('<p class="adt_sat__vacio">Escribe al menos 2 caracteres.</p>');
                return;
            }
            this._llamar('gps_buscar_vehiculos', {texto: texto}).then(function (res) {
                if (seq !== self._seqVeh) { return; }
                self._ref('vehiculos').html(res.length ? '<ul>' + res.map(function (r) {
                    return '<li><button type="button" data-elegir="' + r.id + '"><span class="adt_sat__strong">' + esc(r.placa || '—') +
                        '</span><span class="adt_sat__sub">' + esc([r.vehiculo, r.cliente || 'Sin cliente'].filter(Boolean).join(' · ')) +
                        '</span>' + (r.dispositivos ? '<span class="adt_sat__chip is-atencion">Ya tiene ' +
                        plural(r.dispositivos, 'equipo', 'equipos') + '</span>' : '') + '</button></li>';
                }).join('') + '</ul>' : '<p class="adt_sat__vacio">Ningún vehículo coincide.</p>');
            });
        },

        _onElegirVehiculo: function (ev) {
            var vid = parseInt(ev.currentTarget.getAttribute('data-elegir'), 10);
            this._guardarVinculo(this._llamar('gps_vincular', {dispositivo_id: this.detalle.id, vehicle_id: vid}),
                                 'Dispositivo relacionado con el vehículo.');
        },

        _onModalAccion: function (ev) {
            var self = this;
            var accion = ev.currentTarget.getAttribute('data-m-action');
            if (accion === 'cerrar') {
                this._cerrarModal();
            } else if (accion === 'ir_config') {
                this._cerrarModal();
                this._abrirConfig();
            } else if (accion === 'crear') {
                var ids = this._crearIds || [];
                $(ev.currentTarget).prop('disabled', true);
                this._llamar('gps_crear_vehiculos', {dispositivo_ids: ids}).then(function (r) {
                    self._cerrarModal();
                    self.sel = {};
                    self.displayNotification({type: 'success', title: 'Vehículos en Odoo', message: plural(r.creados, 'vehículo creado', 'vehículos creados') +
                        ' · ' + plural(r.relacionados, 'dispositivo relacionado', 'dispositivos relacionados') +
                        (r.omitidos ? ' · ' + plural(r.omitidos, 'omitido', 'omitidos') + ' (placa ambigua o sin forma de placa)' : '')});
                    if (self.detalle && ids.indexOf(self.detalle.id) !== -1) { self._recargarDetalle(); self.dtab = 'resumen'; }
                    return self._recargar();
                }, function () { $(ev.currentTarget).prop('disabled', false); });
            } else if (accion === 'regenerar') {
                this._llamar('gps_regenerar_webhook').then(function (c) {
                    self._cerrarModal();
                    self._cfg = c;
                    self._renderConfig();
                    self.displayNotification({type: 'warning', sticky: true, message: 'Token regenerado: actualiza la URL en traccar.xml.'});
                });
            } else if (accion === 'eliminar_geo') {
                this._llamar('gps_geocerca_eliminar', {geocerca_id: this._geo.id}).then(function () {
                    self._cerrarModal();
                    self._cerrarDrawer();
                    self.displayNotification({type: 'success', message: 'Geocerca eliminada.'});
                    return self._recargar();
                });
            }
        },

        // ------------------------------------------------------------------
        // Cabecera: sincronizar, notificaciones, prueba
        // ------------------------------------------------------------------

        _onSync: function (ev) {
            var self = this;
            var $b = $(ev.currentTarget).prop('disabled', true).addClass('is-busy');
            this._llamar('gps_sincronizar').then(function (r) {
                self.displayNotification({type: 'success', title: 'Traccar leído',
                    message: plural(r.total, 'dispositivo', 'dispositivos') + ' · ' + plural(r.nuevos, 'nuevo', 'nuevos') +
                        ' · ' + plural(r.eventos, 'evento', 'eventos') + (r.creados ? ' · ' + plural(r.creados, 'vehículo creado', 'vehículos creados') : '')});
                return self._recargar();
            }).then(function () {
                $b.prop('disabled', false).removeClass('is-busy');
            }, function () {
                $b.prop('disabled', false).removeClass('is-busy');
                self._recargar();
            });
        },

        _onNotificaciones: function () {
            var self = this;
            var off = leer(ALERTAS_OFF) === '1';
            if (!('Notification' in window)) {
                this.displayNotification({type: 'info', message: 'Este navegador no permite notificaciones en esta página ' +
                    '(requiere HTTPS); las alertas se muestran dentro de Odoo.'});
                return;
            }
            if (Notification.permission === 'default') {
                guardar(ALERTAS_OFF, null);
                Notification.requestPermission().then(function (p) {
                    self._renderNotif();
                    if (p === 'granted') {
                        new Notification('Alertas de GPS activas', {body: 'Te avisaremos al momento.', tag: 'adt-gps-activadas'});
                    }
                });
                return;
            }
            if (Notification.permission === 'denied') {
                this.displayNotification({type: 'warning', sticky: true, title: 'Notificaciones bloqueadas',
                    message: 'Habilítalas desde el candado de la barra de direcciones del navegador y recarga la página. ' +
                        'Mientras tanto las alertas se muestran dentro de Odoo.'});
                return;
            }
            guardar(ALERTAS_OFF, off ? null : '1');
            this._renderNotif();
            this.displayNotification({type: off ? 'success' : 'info',
                message: off ? 'Alertas activadas en este navegador.' : 'Alertas desactivadas en este navegador.'});
        },

        // Prueba de punta a punta: el servidor envía por el bus y el servicio de alertas,
        // al recibirla, marca la hora; si no llega en 10 s el canal en tiempo real falla.
        _onProbar: function () {
            var self = this;
            var enviado = Date.now();
            this._llamar('gps_probar_notificacion').then(function () {
                setTimeout(function () {
                    var recibida = parseInt(leer(PRUEBA_RECIBIDA) || '0', 10);
                    if (recibida >= enviado) {
                        var seg = ((recibida - enviado) / 1000).toFixed(1);
                        self.displayNotification({type: 'success', title: 'Canal en tiempo real OK',
                            message: 'La alerta de prueba llegó en ' + seg + ' s.'});
                    } else {
                        self.displayNotification({type: 'danger', sticky: true, title: 'La alerta de prueba no llegó',
                            message: 'El bus de Odoo no entregó el mensaje en 10 s. Revisa que el servidor tenga el ' +
                                'longpolling activo (con workers: puerto 8072 y la ruta /longpolling en el proxy).'});
                    }
                }, 10000);
            });
        },

        _onTecla: function (ev) {
            if (ev.key !== 'Escape') { return; }
            if (this._ref('modal').children().length) {
                this._cerrarModal();
            } else if (this.$el.hasClass('is-drawer-open')) {
                this._cerrarDrawer();
            }
        },
    });

    core.action_registry.add('adt_flota_360_gps', Gps);
    return Gps;
});
