odoo.define('adt_flota_360.CargaPdf', function (require) {
    'use strict';

    /**
     * Carga de cronogramas de la financiera (gerencia).
     *
     * Al entrar solo se pide una cosa: «Sube tus cronogramas». Cada archivo soltado aparece
     * como una tarjeta que avanza sola: revisa el formato → sube (con %) → se lee el PDF y se
     * busca al cliente por DNI → muestra con qué cliente, cuenta y moto quedó vinculado, o
     * qué falta para vincularlo. Acepta PDF (aunque no tenga extensión), ZIP con PDFs y
     * carpetas completas; lo demás se descarta sin subirlo.
     *
     * La vista conduce el proceso en tandas pequeñas (carga_tanda) para mostrarlo en vivo; si
     * se cierra a medias, el cron de adt_comercial termina lo que quedó en cola.
     * El historial de cargas está en una vista aparte, a un clic.
     *
     * Sistema visual de "Cartera y financieras" (.adt_cart, de adt_comercial).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var session = require('web.session');

    var esc = _.escape;
    var SUBIDAS_EN_PARALELO = 4;
    var VINCULAR_CADA = 5;          // archivos subidos que se agregan a la carga de una vez
    var VINCULAR_ESPERA_MS = 600;   // o antes, si no llegan más en este tiempo
    var TANDA = 3;                  // PDFs leídos por llamada: respuesta rápida, avance fluido
    var ESPERA_OCUPADO_MS = 2500;   // el cron tiene tomados los PDFs: se consulta de nuevo
    var MAX_FALLOS = 3;
    var OCULTOS = /^(\.|__MACOSX$|Thumbs\.db$|desktop\.ini$)/i;

    var RESULTADO = {
        cargado: {texto: 'Vinculado', tono: 'ok', icono: 'fa-check-circle', grupo: 'ok'},
        sin_cliente: {texto: 'Sin cliente', tono: 'atencion', icono: 'fa-user-times', grupo: 'atencion'},
        revisar: {texto: 'Revisar', tono: 'atencion', icono: 'fa-eye', grupo: 'atencion'},
        error: {texto: 'No se pudo leer', tono: 'critico', icono: 'fa-exclamation-circle', grupo: 'atencion'},
        omitido: {texto: 'Omitido', tono: 'neutral', icono: 'fa-minus-circle', grupo: 'otros'},
    };
    var FILTROS = [
        {k: 'todos', texto: 'Todos'},
        {k: 'ok', texto: 'Vinculados'},
        {k: 'atencion', texto: 'Requieren atención'},
        {k: 'proceso', texto: 'En proceso'},
        {k: 'otros', texto: 'Omitidos / no soportados'},
    ];
    var DEUDA = {activa: 'Deuda activa', cancelada: 'Deuda cancelada', anulada: 'Deuda anulada'};

    // ------------------------------------------------------------ utilidades

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
    }

    function tam(bytes) {
        if (!bytes) { return ''; }
        return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(bytes / 1024)) + ' KB';
    }

    function fechaHora(f) {
        return f ? moment.utc(f).local().format('DD/MM/YYYY HH:mm') : '—';
    }

    function extension(nombre) {
        var m = /\.([a-z0-9]{1,6})$/i.exec(nombre || '');
        return m ? m[1].toLowerCase() : '';
    }

    function mensajeError(err, porDefecto) {
        if (err && err.event && err.event.preventDefault) {
            err.event.preventDefault();  // el mensaje va en la tarjeta, sin el diálogo de error de Odoo
        }
        var m = err && err.message;
        return (m && m.data && m.data.message) || (typeof m === 'string' ? m : '') || porDefecto;
    }

    function esperar(ms) {
        return new Promise(function (ok) { setTimeout(ok, ms); });
    }

    // Tipo real del archivo por sus primeros bytes: 'pdf', 'zip' o null.
    function sniff(file) {
        var trozo = file.slice(0, 1024);
        var leer = trozo.arrayBuffer ? trozo.arrayBuffer() : new Promise(function (ok, mal) {
            var r = new FileReader();
            r.onload = function () { ok(r.result); };
            r.onerror = mal;
            r.readAsArrayBuffer(trozo);
        });
        return leer.then(function (buf) {
            var b = new Uint8Array(buf);
            // Primero el ZIP: uno sin comprimir lleva el «%PDF» de sus PDFs en los primeros bytes.
            if (b[0] === 0x50 && b[1] === 0x4B && (b[2] === 0x03 || b[2] === 0x05)) {
                return 'zip';
            }
            for (var i = 0; i + 3 < b.length; i++) {
                if (b[i] === 0x25 && b[i + 1] === 0x50 && b[i + 2] === 0x44 && b[i + 3] === 0x46) {
                    return 'pdf';
                }
            }
            return null;
        }, function () { return null; });
    }

    // Recorre una carpeta arrastrada y devuelve [{file, ruta}] con todos sus archivos.
    function archivosDeEntrada(entry, ruta) {
        if (!entry || OCULTOS.test(entry.name)) {
            return Promise.resolve([]);
        }
        if (entry.isFile) {
            return new Promise(function (ok) {
                entry.file(function (f) { ok([{file: f, ruta: ruta + f.name}]); }, function () { ok([]); });
            });
        }
        var lector = entry.createReader();
        var todas = [];
        return new Promise(function (ok) {
            (function leer() {
                // readEntries entrega de a 100: se repite hasta que llega vacío.
                lector.readEntries(function (lote) {
                    if (!lote.length) {
                        return Promise.all(todas.map(function (e) {
                            return archivosDeEntrada(e, ruta + entry.name + '/');
                        })).then(function (listas) { ok(_.flatten(listas, true)); });
                    }
                    todas = todas.concat(_.toArray(lote));
                    leer();
                }, function () { ok([]); });
            })();
        });
    }

    // Anillo de avance (SVG) del resumen.
    function anillo(pct, tono) {
        var r = 26;
        var c = 2 * Math.PI * r;
        return '<svg class="adt_cpdf__ring is-' + tono + '" viewBox="0 0 64 64" aria-hidden="true">' +
            '<circle cx="32" cy="32" r="' + r + '" class="adt_cpdf__ring-bg"/>' +
            '<circle cx="32" cy="32" r="' + r + '" class="adt_cpdf__ring-fg" stroke-dasharray="' + c.toFixed(2) + '"' +
            ' stroke-dashoffset="' + (c * (1 - pct / 100)).toFixed(2) + '"/></svg>' +
            '<span class="adt_cpdf__ring-txt">' +
            (pct >= 100 && tono === 'ok' ? '<i class="fa fa-check" aria-hidden="true"></i>'
                : (pct >= 100 && tono === 'atencion' ? '<i class="fa fa-exclamation" aria-hidden="true"></i>' : Math.floor(pct) + '%')) +
            '</span>';
    }

    // ------------------------------------------------------------ acción

    var CargaPdf = AbstractAction.extend({
        template: 'adt_flota_360.CargaPdf',
        hasControlPanel: false,

        events: {
            'click [data-vista]': '_onVista',
            'click [data-action="elegir"]': '_onElegir',
            'click [data-action="carpeta"]': '_onCarpeta',
            'change .adt_cpdf__input': '_onInput',
            'click [data-drop]': '_onDropClick',
            'dragenter [data-drop]': '_onDragOver',
            'dragover [data-drop]': '_onDragOver',
            'dragleave [data-drop]': '_onDragLeave',
            'drop [data-drop]': '_onDrop',
            'keydown [data-drop]': '_onDropTecla',
            'change [data-ref="reemplazar"]': '_onReemplazar',
            'click [data-action="nueva"]': '_onNueva',
            'click [data-action="reintentar-todos"]': '_onReintentarTodos',
            'click [data-reintentar]': '_onReintentar',
            'click [data-asignar]': '_onAsignar',
            'click [data-vehiculo]': '_onVehiculo',
            'click [data-filtro]': '_onFiltro',
            'click [data-lote]': '_onAbrirLote',
            'keydown [data-lote]': '_onLoteTecla',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.vista = 'subir';
            this.loteId = null;
            this.loteInfo = null;        // carga abierta desde el historial
            this.reemplazar = true;
            this.items = [];
            this.porLinea = {};
            this.filtro = 'todos';
            this.historial = null;
            this._porVincular = [];
            this._vinculando = Promise.resolve();
            this._activas = 0;
            this._bombeando = false;
            this._fallos = 0;
            this._pctMax = 0;
            this._sucios = {};
            this._maxBytes = session.max_file_upload_size || 128 * 1024 * 1024;
            this._pintarResumen = _.throttle(this._renderResumen.bind(this), 150);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._render();
                // Salir con la carga en curso: el navegador lo advierte.
                self._antesDeSalir = function (ev) {
                    if (self._ocupado()) {
                        ev.preventDefault();
                        ev.returnValue = '';
                    }
                };
                window.addEventListener('beforeunload', self._antesDeSalir);
            });
        },

        destroy: function () {
            window.removeEventListener('beforeunload', this._antesDeSalir);
            clearTimeout(this._timerVincular);
            if (this._raf) {
                cancelAnimationFrame(this._raf);
            }
            // PDFs en cola sin leer: los termina el cron.
            if (this.loteId && _.some(this.items, function (it) { return it.fase === 'leer' || it.fase === 'leyendo'; })) {
                this._rpcCarga('carga_segundo_plano', {carga_id: this.loteId});
            }
            this._super.apply(this, arguments);
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _rpcCarga: function (method, kwargs) {
            return this._rpc({model: 'adt.flota360', method: method, args: [], kwargs: kwargs});
        },

        _subiendo: function () {
            return this._activas > 0 || _.some(this.items, function (it) {
                return it.fase === 'revisando' || it.fase === 'cola' || it.fase === 'subiendo' || it.fase === 'agregando';
            });
        },

        _ocupado: function () {
            return this._subiendo() || this._bombeando;
        },

        // ------------------------------------------------------------ render general

        _render: function () {
            var vista = this.vista;
            this.$('.adt_cpdf__nav [data-vista]').each(function () {
                var activo = this.getAttribute('data-vista') === vista;
                $(this).toggleClass('is-active', activo).attr('aria-current', activo ? 'page' : null);
            });
            if (vista === 'historial') {
                return this._renderHistorial();
            }
            this._renderSubir();
        },

        _renderSubir: function () {
            var $main = this._ref('main');
            if (!this.items.length) {
                $main.html(this._htmlHero());
                return;
            }
            $main.html(
                (this.loteInfo ? this._htmlLoteInfo() : '') +
                '<section class="adt_cpdf__panel adt_cpdf__resumen" data-ref="resumen"></section>' +
                this._htmlDropMini() +
                '<ul class="adt_cpdf__list" data-ref="lista" data-filtro="' + this.filtro + '" aria-live="polite">' +
                    this.items.map(this._htmlItem.bind(this)).join('') +
                    '<li class="adt_cpdf__list-empty">Ningún archivo en este grupo.</li>' +
                '</ul>');
            this._sucios = {};
            this._renderResumen();
        },

        // Pantalla de entrada: un solo mensaje y una zona grande para soltar.
        _htmlHero: function () {
            return '<section class="adt_cpdf__hero" data-drop="1" tabindex="0" role="button"' +
                ' aria-label="Sube tus cronogramas de la financiera: arrastra archivos o carpetas, o pulsa para elegirlos">' +
                '<div class="adt_cpdf__hero-icon"><i class="fa fa-cloud-upload" aria-hidden="true"></i></div>' +
                '<h2>Sube tus cronogramas de la financiera</h2>' +
                '<p>Arrastra aquí los PDF del plan de pagos. Los leemos, buscamos al cliente por su DNI y ' +
                    'vinculamos cada cronograma con su cuenta y su moto.</p>' +
                '<div class="adt_cpdf__hero-actions">' +
                    '<button type="button" class="adt_cart__btn adt_cpdf__btn-lg" data-action="elegir">' +
                        '<i class="fa fa-files-o" aria-hidden="true"></i>Elegir archivos</button>' +
                    '<button type="button" class="adt_cart__btn adt_cart__btn--ghost adt_cpdf__btn-lg" data-action="carpeta">' +
                        '<i class="fa fa-folder-open-o" aria-hidden="true"></i>Elegir carpeta</button>' +
                '</div>' +
                '<ul class="adt_cpdf__formatos" aria-label="Formatos aceptados">' +
                    '<li><i class="fa fa-file-pdf-o" aria-hidden="true"></i>PDF</li>' +
                    '<li><i class="fa fa-file-archive-o" aria-hidden="true"></i>ZIP con PDFs</li>' +
                    '<li><i class="fa fa-folder-o" aria-hidden="true"></i>Carpetas</li>' +
                '</ul>' +
                '<label class="adt_cpdf__check"><input type="checkbox" data-ref="reemplazar"' +
                    (this.reemplazar ? ' checked="checked"' : '') + '/>' +
                    '<span>Si la moto ya tiene un cronograma, reemplazarlo por el nuevo</span></label>' +
                '</section>';
        },

        _htmlDropMini: function () {
            return '<div class="adt_cpdf__drop-mini" data-drop="1" tabindex="0" role="button"' +
                ' aria-label="Agregar más cronogramas a esta carga">' +
                '<i class="fa fa-plus-circle" aria-hidden="true"></i>' +
                '<span><b>¿Te faltó alguno?</b> Suéltalo aquí o ' +
                '<button type="button" class="adt_cpdf__linkbtn" data-action="elegir">elige más archivos</button></span></div>';
        },

        _htmlLoteInfo: function () {
            var l = this.loteInfo;
            return '<div class="adt_cpdf__back">' +
                '<button type="button" class="adt_cpdf__linkbtn" data-vista="historial"><i class="fa fa-arrow-left" aria-hidden="true"></i>' +
                'Volver al historial</button>' +
                '<span class="adt_cart__muted">Carga del ' + esc(fechaHora(l.fecha)) + ' · ' + esc(l.autor) + '</span></div>';
        },

        // ------------------------------------------------------------ resumen

        _grupo: function (it) {
            if (it.fase === 'listo') {
                return (RESULTADO[it.linea.state] || RESULTADO.error).grupo;
            }
            if (it.fase === 'error') { return 'atencion'; }
            if (it.fase === 'ignorado') { return 'otros'; }
            if (it.fase === 'extraido') { return 'zip'; }  // el ZIP abierto: cuentan sus PDFs
            return 'proceso';
        },

        _contar: function () {
            var c = {ok: 0, atencion: 0, proceso: 0, otros: 0, leer: 0, leidos: 0,
                     bytes: 0, subidos: 0, archivos: 0, archivosHechos: 0, avance: 0, unidades: 0};
            this.items.forEach(function (it) {
                var g = this._grupo(it);
                if (g === 'zip') {
                    return;
                }
                c[g]++;
                if (!it.origen) {
                    c.archivos++;
                    if (it.fase !== 'revisando' && it.fase !== 'cola' && it.fase !== 'subiendo') { c.archivosHechos++; }
                    if (it.fase !== 'ignorado') {
                        c.bytes += it.size || 0;
                        c.subidos += it.fase === 'subiendo' ? (it.cargado || 0)
                            : (it.fase === 'revisando' || it.fase === 'cola' ? 0 : (it.size || 0));
                    }
                }
                if (it.fase === 'leer' || it.fase === 'leyendo') { c.leer++; }
                if (it.fase === 'listo') { c.leidos++; }
                c.unidades++;
                var peso = {revisando: 0, cola: 0, agregando: 0.5, leer: 0.55, leyendo: 0.75};
                c.avance += it.fase === 'subiendo' ? 0.45 * (it.size ? (it.cargado || 0) / it.size : 0)
                    : (peso[it.fase] !== undefined ? peso[it.fase] : 1);
            }, this);
            c.total = c.ok + c.atencion + c.proceso + c.otros;
            c.pct = c.unidades ? 100 * c.avance / c.unidades : 0;
            return c;
        },

        _renderResumen: function () {
            var $r = this._ref('resumen');
            if (!$r.length) {
                return;
            }
            var c = this._contar();
            var subiendo = this._subiendo();
            var ocupado = subiendo || this._bombeando || c.leer > 0;
            // El anillo no retrocede mientras avanza la misma tanda de archivos.
            var pct = ocupado ? (this._pctMax = Math.max(this._pctMax, Math.min(c.pct, 99))) : 100;
            var titulo, detalle, tono;
            if (subiendo) {
                tono = 'info';
                titulo = 'Subiendo tus cronogramas…';
                detalle = '<b>' + entero(c.archivosHechos) + ' de ' + plural(c.archivos, 'archivo', 'archivos') + '</b>' +
                    (c.bytes ? ' · ' + (tam(c.subidos) || '0 KB') + ' de ' + tam(c.bytes) : '') +
                    (c.ok ? ' · ya se vincularon ' + entero(c.ok) : '');
            } else if (ocupado) {
                tono = 'info';
                titulo = 'Vinculando con las cuentas…';
                detalle = 'Leyendo cada PDF y buscando al cliente por su DNI · <b>' + entero(c.leidos) + ' de ' +
                    entero(c.leidos + c.leer) + '</b> listos';
            } else if (!c.atencion) {
                tono = 'ok';
                titulo = c.ok ? '¡Listo! ' + plural(c.ok, 'cronograma vinculado', 'cronogramas vinculados') : 'Carga terminada';
                detalle = c.ok ? 'Cada uno quedó en la moto de su cuenta (pestaña Financiera de Flota 360).'
                    : 'No hubo cronogramas para vincular.';
            } else {
                tono = 'atencion';
                titulo = plural(c.atencion, 'cronograma requiere', 'cronogramas requieren') + ' tu atención';
                detalle = plural(c.ok, 'vinculado', 'vinculados') + '. Los marcados en amarillo o rojo puedes asignarlos a un cliente o reintentarlos.';
            }
            var self = this;
            var tabs = FILTROS.filter(function (f) { return f.k === 'todos' || c[f.k] || self.filtro === f.k; }).map(function (f) {
                var n = f.k === 'todos' ? c.total : c[f.k];
                var activo = self.filtro === f.k;
                return '<button type="button" class="adt_cart__chip adt_cpdf__tab is-' + f.k + (activo ? ' is-active' : '') + '"' +
                    ' data-filtro="' + f.k + '" aria-pressed="' + activo + '">' + esc(f.texto) +
                    '<span class="adt_cpdf__n">' + entero(n) + '</span></button>';
            }).join('');
            $r.attr('class', 'adt_cpdf__panel adt_cpdf__resumen is-' + tono).html(
                '<div class="adt_cpdf__resumen-top">' +
                    '<div class="adt_cpdf__ring-wrap">' + anillo(pct, tono) + '</div>' +
                    '<div class="adt_cpdf__resumen-txt"><h2>' + esc(titulo) + '</h2><p>' + detalle + '</p>' +
                        '<div class="adt_cpdf__stats">' +
                            this._stat('ok', 'fa-link', c.ok, c.ok === 1 ? 'vinculado' : 'vinculados') +
                            this._stat('atencion', 'fa-exclamation-triangle', c.atencion, c.atencion === 1 ? 'requiere atención' : 'requieren atención') +
                            (c.proceso ? this._stat('info', 'fa-cog' + (ocupado ? ' fa-spin' : ''), c.proceso, 'en proceso') : '') +
                        '</div></div>' +
                    '<div class="adt_cpdf__resumen-actions">' +
                        (!ocupado && c.atencion ? '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-action="reintentar-todos">' +
                            '<i class="fa fa-repeat" aria-hidden="true"></i>Reintentar los ' + entero(c.atencion) + '</button>' : '') +
                        (!ocupado ? '<button type="button" class="adt_cart__btn" data-action="nueva">' +
                            '<i class="fa fa-cloud-upload" aria-hidden="true"></i>Nueva carga</button>' : '') +
                    '</div>' +
                '</div>' +
                '<div class="adt_cpdf__bar is-' + tono + (ocupado ? ' is-live' : '') + '" role="progressbar" aria-valuemin="0"' +
                    ' aria-valuemax="100" aria-valuenow="' + Math.floor(pct) + '"><span style="width:' + pct.toFixed(1) + '%"></span></div>' +
                '<nav class="adt_cpdf__tabs" aria-label="Filtrar archivos">' + tabs + '</nav>');
        },

        _stat: function (tono, icono, n, texto) {
            return '<span class="adt_cpdf__stat is-' + tono + (n ? '' : ' is-zero') + '"><i class="fa ' + icono + '" aria-hidden="true"></i>' +
                '<b>' + entero(n) + '</b> ' + esc(texto) + '</span>';
        },

        // ------------------------------------------------------------ tarjeta de cada archivo

        _estado: function (it) {
            switch (it.fase) {
                case 'revisando': return {texto: 'Revisando formato…', tono: 'neutral', icono: 'fa-search', barra: 'indet'};
                case 'cola': return {texto: 'En espera para subir', tono: 'neutral', icono: 'fa-clock-o', barra: 0};
                case 'subiendo':
                    var p = it.size ? 100 * (it.cargado || 0) / it.size : 0;
                    return {texto: 'Subiendo ' + Math.floor(p) + '%', tono: 'info', icono: 'fa-cloud-upload', barra: p};
                case 'agregando': return {texto: it.tipo === 'zip' ? 'Abriendo el ZIP…' : 'Preparando…', tono: 'info',
                    icono: 'fa-cog fa-spin', barra: 'indet'};
                case 'leer': return {texto: 'Subido · en cola para leer', tono: 'info', icono: 'fa-hourglass-half', barra: 100, suave: true};
                case 'leyendo': return {texto: 'Leyendo y buscando al cliente…', tono: 'info', icono: 'fa-cog fa-spin', barra: 'indet'};
                case 'extraido': return {texto: 'ZIP abierto · ' + plural(it.hijos || 0, 'PDF', 'PDFs'), tono: it.hijos ? 'ok' : 'atencion',
                    icono: 'fa-folder-open-o'};
                case 'ignorado': return {texto: 'No soportado', tono: 'neutral', icono: 'fa-ban'};
                case 'error': return {texto: 'Error', tono: 'critico', icono: 'fa-exclamation-circle'};
                default: return RESULTADO[it.linea.state] || RESULTADO.error;
            }
        },

        _htmlItem: function (it) {
            var e = this._estado(it);
            var icono = it.tipo === 'zip' ? 'fa-file-archive-o' : (it.tipo === 'pdf' ? 'fa-file-pdf-o' : 'fa-file-o');
            var meta = _.compact([tam(it.size), it.origen ? 'del ZIP ' + it.origen : (it.ruta && it.ruta !== it.name ? it.ruta : '')]);
            var cuerpo = '';
            if (e.barra !== undefined) {
                cuerpo = '<div class="adt_cpdf__bar is-sm is-' + e.tono + (e.barra === 'indet' ? ' is-indet' : '') + (e.suave ? ' is-soft' : '') + '">' +
                    '<span' + (e.barra === 'indet' ? '' : ' style="width:' + e.barra.toFixed(1) + '%"') + '></span></div>';
            } else if (it.fase === 'listo') {
                cuerpo = this._htmlResultado(it);
            } else if (it.mensaje) {
                cuerpo = '<p class="adt_cpdf__item-msg">' + esc(it.mensaje) + '</p>';
            }
            if (it.fase === 'extraido' && it.ignorados && it.ignorados.length) {
                cuerpo += '<details class="adt_cpdf__ign"><summary>' +
                    plural(it.ignorados.length, 'archivo del ZIP no es PDF', 'archivos del ZIP no son PDF') +
                    '</summary><ul>' + it.ignorados.map(function (x) {
                        return '<li><b>' + esc(x.name) + '</b> · ' + esc(x.motivo) + '</li>';
                    }).join('') + '</ul></details>';
            }
            var flash = it.flash ? ' is-flash' : '';
            it.flash = false;
            return '<li class="adt_cpdf__item is-' + e.tono + flash + (it.origen ? ' is-child' : '') + '" data-key="' + it.key + '"' +
                ' data-grupo="' + this._grupo(it) + '">' +
                '<span class="adt_cpdf__item-ico"><i class="fa ' + icono + '" aria-hidden="true"></i></span>' +
                '<div class="adt_cpdf__item-main">' +
                    '<div class="adt_cpdf__item-top">' +
                        '<span class="adt_cpdf__item-name" title="' + esc(it.name) + '">' + esc(it.name) + '</span>' +
                        '<span class="adt_cpdf__item-state is-' + e.tono + '"><i class="fa ' + e.icono + '" aria-hidden="true"></i>' +
                            esc(e.texto) + '</span>' +
                    '</div>' +
                    (meta.length ? '<div class="adt_cpdf__item-meta">' + esc(meta.join(' · ')) + '</div>' : '') +
                    cuerpo +
                '</div></li>';
        },

        // Lo que hizo el sistema con el PDF: cliente → cuenta → moto, o qué falta.
        _htmlResultado: function (it) {
            var l = it.linea;
            var leido = l.dni || l.socio
                ? '<span class="adt_cpdf__leido"><i class="fa fa-id-card-o" aria-hidden="true"></i>En el PDF: ' +
                  esc(_.compact([l.socio, l.dni && 'DNI ' + l.dni]).join(' · ')) +
                  (l.cuotas ? ' · ' + plural(l.cuotas, 'cuota', 'cuotas') : '') + '</span>'
                : '';
            if (l.state === 'cargado') {
                return '<div class="adt_cpdf__vinculo">' +
                    '<span class="adt_cpdf__nodo"><i class="fa fa-user" aria-hidden="true"></i><span><small>Cliente</small><b>' +
                        esc(l.cliente || '—') + '</b></span></span>' +
                    '<i class="fa fa-long-arrow-right adt_cpdf__flecha" aria-hidden="true"></i>' +
                    '<span class="adt_cpdf__nodo"><i class="fa fa-file-text-o" aria-hidden="true"></i><span><small>Cuenta</small><b>' +
                        esc(l.cuenta || '—') + '</b></span></span>' +
                    '<i class="fa fa-long-arrow-right adt_cpdf__flecha" aria-hidden="true"></i>' +
                    (l.vehiculo_id
                        ? '<button type="button" class="adt_cpdf__nodo is-link" data-vehiculo="' + l.vehiculo_id + '" title="Ver el cronograma en Flota 360">' +
                          '<i class="fa fa-motorcycle" aria-hidden="true"></i><span><small>Moto</small><b>' + esc(l.placa) +
                          ' <i class="fa fa-external-link" aria-hidden="true"></i></b></span></button>'
                        : '') +
                    (DEUDA[l.deuda] ? '<span class="adt_cpdf__pill is-' + (l.deuda === 'activa' ? 'info' : 'neutral') + '">' +
                        esc(DEUDA[l.deuda]) + '</span>' : '') +
                    '</div>' +
                    '<div class="adt_cpdf__item-foot">' + leido +
                    (l.lectura === 'observado' ? '<span class="adt_cpdf__pill is-atencion"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i>' +
                        'Lectura observada · ' + Math.round(l.confianza || 0) + '%</span>' : '') +
                    (/Reemplazó/.test(l.mensaje) ? '<span class="adt_cpdf__pill is-neutral"><i class="fa fa-exchange" aria-hidden="true"></i>' +
                        'Reemplazó el cronograma anterior</span>' : '') +
                    '</div>';
            }
            var acciones = l.state === 'omitido' ? '' :
                '<div class="adt_cpdf__item-actions">' +
                    '<button type="button" class="adt_cart__btn adt_cpdf__btn-sm" data-asignar="' + it.key + '">' +
                        '<i class="fa fa-user-plus" aria-hidden="true"></i>Asignar a un cliente</button>' +
                    '<button type="button" class="adt_cart__btn adt_cart__btn--ghost adt_cpdf__btn-sm" data-reintentar="' + it.key + '">' +
                        '<i class="fa fa-repeat" aria-hidden="true"></i>Reintentar</button>' +
                '</div>';
            return '<p class="adt_cpdf__item-msg">' + esc(l.mensaje || '') + '</p>' +
                (leido ? '<div class="adt_cpdf__item-foot">' + leido + '</div>' : '') + acciones;
        },

        // Repinta solo las tarjetas que cambiaron, una vez por cuadro de animación.
        _marcar: function (it) {
            this._sucios[it.key] = it;
            if (!this._raf) {
                this._raf = requestAnimationFrame(this._pintar.bind(this));
            }
        },

        _pintar: function () {
            this._raf = null;
            var sucios = this._sucios;
            this._sucios = {};
            if (this.vista !== 'subir') {
                return;
            }
            var $lista = this._ref('lista');
            if (!$lista.length) {
                return this._renderSubir();
            }
            _.each(sucios, function (it) {
                var el = $lista[0].querySelector('[data-key="' + it.key + '"]');
                if (el) {
                    el.outerHTML = this._htmlItem(it);
                }
            }, this);
            this._pintarResumen();
        },

        // Inserta tarjetas nuevas (después de `despues`, o al final).
        _insertar: function (nuevos, despues) {
            if (this.vista !== 'subir') {
                return;
            }
            var $lista = this._ref('lista');
            if (!$lista.length) {
                return this._renderSubir();
            }
            var html = nuevos.map(this._htmlItem.bind(this)).join('');
            var ancla = despues && $lista[0].querySelector('[data-key="' + despues.key + '"]');
            if (ancla) {
                ancla.insertAdjacentHTML('afterend', html);
            } else {
                $lista.find('.adt_cpdf__list-empty').before(html);
            }
            this._pintarResumen();
        },

        _setLinea: function (it, linea) {
            var antes = it.fase;
            it.linea = linea;
            it.name = linea.archivo || it.name;  // un PDF sin extensión queda como «.pdf»
            this.porLinea[linea.id] = it;
            it.fase = linea.state === 'pendiente' ? 'leer' : 'listo';
            it.flash = antes !== 'listo' && it.fase === 'listo';
            this._marcar(it);
        },

        _itemDeLinea: function (l, origen) {
            var it = {key: _.uniqueId('f'), name: l.archivo, size: l.size, tipo: 'pdf', origen: origen || null};
            it.linea = l;
            it.fase = l.state === 'pendiente' ? 'leer' : 'listo';
            this.porLinea[l.id] = it;
            return it;
        },

        // ------------------------------------------------------------ historial

        _renderHistorial: function () {
            var self = this;
            var $main = this._ref('main');
            if (!this.historial) {
                $main.html('<div class="adt_cart__empty"><i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Cargando historial…</div>');
                this._rpcCarga('carga_historial', {}).then(function (lotes) {
                    self.historial = lotes;
                    if (self.vista === 'historial') { self._renderHistorial(); }
                });
                return;
            }
            var filas = this.historial;
            $main.html('<section class="adt_cpdf__panel">' +
                '<header class="adt_cpdf__panel-head"><h3><i class="fa fa-history" aria-hidden="true"></i>Cargas anteriores</h3>' +
                    '<span class="adt_cart__muted">Abre una para ver con qué cuenta quedó cada cronograma</span></header>' +
                (filas.length
                    ? '<div class="adt_cpdf__tablewrap"><table class="adt_cpdf__table"><thead><tr><th>Fecha</th><th>Subida por</th>' +
                      '<th class="is-num">Cronogramas</th><th class="is-num">Vinculados</th><th class="is-num">Requieren atención</th>' +
                      '<th>Estado</th><th></th></tr></thead><tbody>' + filas.map(function (l) {
                          var t = l.totales;
                          var estado = t.pendiente
                              ? '<span class="adt_cpdf__pill is-info"><i class="fa fa-cog" aria-hidden="true"></i>En proceso · faltan ' + entero(t.pendiente) + '</span>'
                              : (t.atencion ? '<span class="adt_cpdf__pill is-atencion"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i>Con pendientes</span>'
                                  : (t.total ? '<span class="adt_cpdf__pill is-ok"><i class="fa fa-check" aria-hidden="true"></i>Completa</span>'
                                      : '<span class="adt_cpdf__pill is-neutral">Vacía</span>'));
                          return '<tr data-lote="' + l.id + '" tabindex="0" title="Ver el detalle">' +
                              '<td><b>' + esc(fechaHora(l.fecha)) + '</b></td><td>' + esc(l.autor) + '</td>' +
                              '<td class="is-num">' + entero(t.total) + '</td>' +
                              '<td class="is-num adt_cpdf__ok">' + entero(t.cargado) + '</td>' +
                              '<td class="is-num' + (t.atencion ? ' adt_cpdf__warn' : '') + '">' + entero(t.atencion) + '</td>' +
                              '<td>' + estado + '</td><td class="is-num"><i class="fa fa-angle-right" aria-hidden="true"></i></td></tr>';
                      }).join('') + '</tbody></table></div>'
                    : '<div class="adt_cart__empty">Todavía no hay cargas.</div>') +
                '</section>');
        },

        _abrirLote: function (id) {
            var self = this;
            if (this._ocupado()) {
                return this.displayNotification({type: 'warning', message: 'Espera a que termine la carga en curso.'});
            }
            this._ref('main').html('<div class="adt_cart__empty"><i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Abriendo la carga…</div>');
            this._rpcCarga('carga_lote', {carga_id: id}).then(function (lote) {
                self._reset();
                self.loteId = lote.id;
                self.loteInfo = lote;
                self.reemplazar = lote.reemplazar;
                self.items = lote.lineas.map(function (l) { return self._itemDeLinea(l); });
                self.vista = 'subir';
                self._render();
                self._bombear();  // si quedó algo en cola, se sigue leyendo aquí
            });
        },

        _reset: function () {
            this.items = [];
            this.porLinea = {};
            this.loteId = null;
            this.loteInfo = null;
            this.filtro = 'todos';
            this._pctMax = 0;
            this._fallos = 0;
        },

        // ------------------------------------------------------------ subida

        _asegurarLote: function () {
            var self = this;
            if (this.loteId) {
                return Promise.resolve(this.loteId);
            }
            if (!this._creando) {
                this._creando = this._rpcCarga('carga_crear', {reemplazar: this.reemplazar}).then(function (id) {
                    self.loteId = id;
                    self.historial = null;
                    self._creando = null;
                    return id;
                }, function (err) {
                    self._creando = null;
                    throw err;
                });
            }
            return this._creando;
        },

        _agregar: function (files) {
            var self = this;
            files = files.filter(function (f) { return !OCULTOS.test(f.file.name); });
            if (!files.length) {
                return;
            }
            this.vista = 'subir';
            var nuevos = files.map(function (f) {
                return {key: _.uniqueId('f'), file: f.file, name: f.file.name, ruta: f.ruta || f.file.name,
                        size: f.file.size, cargado: 0, fase: 'revisando', tipo: null, mensaje: ''};
            });
            this.items = this.items.concat(nuevos);
            this._pctMax = 0;
            if (this._ref('lista').length) {
                this._insertar(nuevos);
            } else {
                this._render();
            }
            // Cada archivo se identifica por su contenido antes de subirlo.
            Promise.all(nuevos.map(function (it) {
                return sniff(it.file).then(function (tipo) {
                    it.tipo = tipo;
                    if (!it.size) {
                        self._fin(it, 'error', 'El archivo está vacío.');
                    } else if (!tipo) {
                        var ext = extension(it.name);
                        self._fin(it, 'ignorado', 'Formato no soportado' + (ext ? ' (.' + ext + ')' : '') +
                            '. Sube el PDF del plan de pagos o un ZIP con PDFs.');
                    } else if (it.size > self._maxBytes) {
                        self._fin(it, 'error', 'Pesa ' + tam(it.size) + '; el máximo por archivo es ' + tam(self._maxBytes) + '.');
                    } else {
                        it.fase = 'cola';
                        self._marcar(it);
                    }
                });
            })).then(function () {
                if (!_.findWhere(nuevos, {fase: 'cola'})) {
                    return self._pintarResumen();
                }
                return self._asegurarLote().then(function () {
                    self._siguiente();
                }, function (err) {
                    var msg = mensajeError(err, 'No se pudo iniciar la carga.');
                    nuevos.forEach(function (it) {
                        if (it.fase === 'cola') { self._fin(it, 'error', msg); }
                    });
                });
            });
        },

        _fin: function (it, fase, mensaje) {
            it.fase = fase;
            it.mensaje = mensaje || '';
            it.file = null;
            this._marcar(it);
        },

        _siguiente: function () {
            while (this._activas < SUBIDAS_EN_PARALELO) {
                var it = _.findWhere(this.items, {fase: 'cola'});
                if (!it) {
                    break;
                }
                this._subir(it);
            }
            this._programarVincular();
        },

        _subir: function (it) {
            var self = this;
            it.fase = 'subiendo';
            this._activas++;
            this._marcar(it);
            var datos = new FormData();
            datos.append('csrf_token', core.csrf_token);
            datos.append('model', 'adt.financiera.carga.pdf');
            datos.append('id', this.loteId);
            datos.append('ufile', it.file, it.name);
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/web/binary/upload_attachment');
            xhr.upload.onprogress = function (ev) {
                if (ev.lengthComputable) {
                    it.cargado = Math.min(ev.loaded, it.size);
                    self._marcar(it);
                }
            };
            xhr.onload = function () {
                var res = null;
                try {
                    res = JSON.parse(xhr.responseText)[0];
                } catch (e) {
                    res = {error: 'Respuesta inválida del servidor (' + xhr.status + ').'};
                }
                self._activas--;
                if (xhr.status !== 200 || !res || res.error) {
                    self._fin(it, 'error', (res && res.error) || 'Error ' + xhr.status + ' al subir.');
                } else {
                    it.attId = res.id;
                    it.cargado = it.size;
                    it.file = null;
                    it.fase = 'agregando';
                    self._marcar(it);
                    self._porVincular.push(it);
                }
                self._siguiente();
            };
            xhr.onerror = function () {
                self._activas--;
                self._fin(it, 'error', 'Sin conexión con el servidor.');
                self._siguiente();
            };
            xhr.send(datos);
        },

        _programarVincular: function () {
            var self = this;
            clearTimeout(this._timerVincular);
            if (!this._porVincular.length) {
                return;
            }
            var quedan = _.some(this.items, function (x) { return x.fase === 'cola' || x.fase === 'subiendo'; });
            if (this._porVincular.length >= VINCULAR_CADA || !quedan) {
                this._vincular();
            } else {
                this._timerVincular = setTimeout(function () { self._vincular(); }, VINCULAR_ESPERA_MS);
            }
        },

        // Agrega a la carga lo subido: el servidor abre los ZIP y deja los PDFs en cola para leerse.
        _vincular: function () {
            var self = this;
            var tanda = this._porVincular.splice(0);
            if (!tanda.length) {
                return;
            }
            var id = this.loteId;
            this._vinculando = this._vinculando.then(function () {
                return self._rpcCarga('carga_agregar', {carga_id: id, attachment_ids: _.pluck(tanda, 'attId')}).then(function (r) {
                    if (id !== self.loteId) {
                        return;
                    }
                    var porId = _.indexBy(r.archivos, 'id');
                    tanda.forEach(function (it) {
                        var a = porId[it.attId];
                        if (!a) {
                            return self._fin(it, 'error', 'El servidor no recibió el archivo.');
                        }
                        if (a.tipo === 'pdf') {
                            return a.lineas.length ? self._setLinea(it, a.lineas[0]) : self._fin(it, 'error', 'No se pudo poner en cola.');
                        }
                        if (a.tipo === 'zip') {
                            it.hijos = a.lineas.length;
                            it.ignorados = a.ignorados;
                            self._fin(it, 'extraido');
                            var hijos = a.lineas.map(function (l) { return self._itemDeLinea(l, it.name); });
                            var idx = self.items.indexOf(it);
                            Array.prototype.splice.apply(self.items, [idx + 1, 0].concat(hijos));
                            return self._insertar(hijos, it);
                        }
                        self._fin(it, 'ignorado', (a.ignorados[0] && a.ignorados[0].motivo) || 'No es un PDF ni un ZIP.');
                    });
                    self._bombear();
                }, function (err) {
                    var msg = mensajeError(err, 'No se pudo agregar a la carga.');
                    tanda.forEach(function (it) { self._fin(it, 'error', msg); });
                });
            });
        },

        // ------------------------------------------------------------ lectura en vivo

        // Lee la cola en tandas pequeñas mientras haya PDFs esperando; un solo ciclo a la vez.
        _bombear: function () {
            var self = this;
            if (this._bombeando || !this.loteId) {
                return;
            }
            var id = this.loteId;
            this._bombeando = true;
            this._fallos = 0;
            var paso = function () {
                if (self.isDestroyed() || id !== self.loteId) {
                    self._bombeando = false;
                    return;
                }
                var espera = _.sortBy(_.filter(self.items, function (it) { return it.fase === 'leer'; }),
                                      function (it) { return it.linea.id; });
                if (!espera.length) {
                    self._bombeando = false;
                    self._pintarResumen();
                    return;
                }
                var enLectura = espera.slice(0, TANDA);
                enLectura.forEach(function (it) { it.fase = 'leyendo'; self._marcar(it); });
                var devolver = function () {
                    enLectura.forEach(function (it) {
                        if (it.fase === 'leyendo') { it.fase = 'leer'; self._marcar(it); }
                    });
                };
                self._rpcCarga('carga_tanda', {carga_id: id, limite: TANDA}).then(function (r) {
                    self._fallos = 0;
                    r.lineas.forEach(function (l) {
                        var it = self.porLinea[l.id];
                        if (it) { self._setLinea(it, l); }
                    });
                    devolver();  // los que no tocaron en esta tanda vuelven a la cola
                    if (!r.lineas.length && r.totales.pendiente) {
                        // El cron los tiene tomados: se espera y se consulta cómo quedaron.
                        return esperar(ESPERA_OCUPADO_MS).then(function () { return self._refrescarCola(id); });
                    }
                    if (!r.totales.pendiente) {
                        // Lo que quede en «leer» ya lo leyó otro proceso: se trae su resultado.
                        return self._refrescarCola(id);
                    }
                }, function (err) {
                    mensajeError(err);
                    devolver();
                    if (++self._fallos >= MAX_FALLOS) {
                        self._bombeando = false;
                        self._rpcCarga('carga_segundo_plano', {carga_id: id});
                        self.displayNotification({type: 'warning', sticky: true, title: 'Se perdió la conexión',
                            message: 'Los cronogramas que faltan se terminarán de vincular en segundo plano. ' +
                                'Revisa el resultado más tarde en el historial.'});
                        self._pintarResumen();
                        throw new Error('detenido');
                    }
                    return esperar(2000);
                }).then(paso, function () { /* detenido */ });
            };
            paso();
        },

        _refrescarCola: function (id) {
            var ids = _.filter(this.items, function (it) { return it.fase === 'leer' && it.linea; })
                .map(function (it) { return it.linea.id; });
            return ids.length ? this._actualizarLineas(ids, id) : Promise.resolve();
        },

        _actualizarLineas: function (ids, id) {
            var self = this;
            return this._rpcCarga('carga_lineas', {carga_id: id || this.loteId, linea_ids: ids}).then(function (r) {
                r.lineas.forEach(function (l) {
                    var it = self.porLinea[l.id];
                    if (it && (l.state !== 'pendiente' || it.fase !== 'leer')) { self._setLinea(it, l); }
                });
            });
        },

        _reintentar: function (ids) {
            var self = this;
            return this._rpcCarga('carga_reintentar', {carga_id: this.loteId, linea_ids: ids || null}).then(function (r) {
                self._pctMax = 0;
                r.lineas.forEach(function (l) {
                    var it = self.porLinea[l.id];
                    if (it) { self._setLinea(it, l); }
                });
                self._bombear();
            });
        },

        // ------------------------------------------------------------ eventos

        _onVista: function (ev) {
            var vista = ev.currentTarget.getAttribute('data-vista');
            if (vista === 'historial') {
                this.historial = null;  // siempre al día
            }
            if (vista === 'subir' && this.loteInfo && !this._ocupado()) {
                this._reset();  // «Subir» desde una carga antigua: empieza una nueva
            }
            this.vista = vista;
            this._render();
        },

        _onNueva: function () {
            if (this._ocupado()) {
                return;
            }
            this._reset();
            this._render();
        },

        _abrirSelector: function (tipo) {
            this.$('.adt_cpdf__input[data-tipo="' + tipo + '"]').click();
        },

        _onElegir: function (ev) {
            ev.stopPropagation();
            this._abrirSelector('archivos');
        },

        _onCarpeta: function (ev) {
            ev.stopPropagation();
            this._abrirSelector('carpeta');
        },

        // Clic en la zona (fuera de botones y del check): abre el selector de archivos.
        _onDropClick: function (ev) {
            if (!$(ev.target).closest('button, label, input, a').length) {
                this._abrirSelector('archivos');
            }
        },

        _onDropTecla: function (ev) {
            if (ev.target === ev.currentTarget && (ev.key === 'Enter' || ev.key === ' ')) {
                ev.preventDefault();
                this._abrirSelector('archivos');
            }
        },

        _onInput: function (ev) {
            var files = _.toArray(ev.currentTarget.files).map(function (f) {
                return {file: f, ruta: f.webkitRelativePath || f.name};
            });
            ev.currentTarget.value = '';
            this._agregar(files);
        },

        _onDragOver: function (ev) {
            ev.preventDefault();
            if (ev.originalEvent.dataTransfer) {
                ev.originalEvent.dataTransfer.dropEffect = 'copy';
            }
            $(ev.currentTarget).addClass('is-over');
        },

        _onDragLeave: function (ev) {
            if (!ev.currentTarget.contains(ev.originalEvent.relatedTarget)) {
                $(ev.currentTarget).removeClass('is-over');
            }
        },

        _onDrop: function (ev) {
            var self = this;
            ev.preventDefault();
            $(ev.currentTarget).removeClass('is-over');
            var dt = ev.originalEvent.dataTransfer;
            if (!dt) {
                return;
            }
            var entradas = _.toArray(dt.items || []).map(function (i) {
                return i.kind === 'file' && i.webkitGetAsEntry ? i.webkitGetAsEntry() : null;
            });
            if (entradas.length && _.every(entradas)) {
                // Carpetas arrastradas: se recorren completas.
                Promise.all(entradas.map(function (e) { return archivosDeEntrada(e, ''); })).then(function (listas) {
                    self._agregar(_.flatten(listas, true));
                });
            } else {
                this._agregar(_.toArray(dt.files || []).map(function (f) { return {file: f, ruta: f.name}; }));
            }
        },

        _onReemplazar: function (ev) {
            this.reemplazar = ev.currentTarget.checked;
            if (this.loteId) {
                this._rpcCarga('carga_opciones', {carga_id: this.loteId, reemplazar: this.reemplazar});
            }
        },

        _onFiltro: function (ev) {
            var f = ev.currentTarget.getAttribute('data-filtro');
            this.filtro = this.filtro === f ? 'todos' : f;
            this._ref('lista').attr('data-filtro', this.filtro);
            this._renderResumen();
        },

        _itemDe: function (ev, attr) {
            return _.findWhere(this.items, {key: ev.currentTarget.getAttribute(attr)});
        },

        _onReintentar: function (ev) {
            var it = this._itemDe(ev, 'data-reintentar');
            if (it && it.linea) {
                $(ev.currentTarget).prop('disabled', true);
                this._reintentar([it.linea.id]);
            }
        },

        _onReintentarTodos: function (ev) {
            $(ev.currentTarget).prop('disabled', true);
            this._reintentar();
        },

        // Detalle del PDF (adt_comercial): se elige el cliente y su cuenta, y se carga ahí.
        _onAsignar: function (ev) {
            var self = this;
            var it = this._itemDe(ev, 'data-asignar');
            if (!it || !it.linea) {
                return;
            }
            this.do_action({
                type: 'ir.actions.act_window', name: 'Asignar «' + it.name + '» a un cliente',
                res_model: 'adt.financiera.carga.pdf.linea', res_id: it.linea.id,
                views: [[false, 'form']], target: 'new',
            }, {on_close: function () { self._actualizarLineas([it.linea.id]); }});
        },

        // Ficha del vehículo en Flota 360, en la pestaña Financiera.
        _onVehiculo: function (ev) {
            ev.stopPropagation();
            this.do_action({
                type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                params: {vehicle_id: parseInt(ev.currentTarget.getAttribute('data-vehiculo'), 10), tab: 'financiera'},
            });
        },

        _onAbrirLote: function (ev) {
            this._abrirLote(parseInt(ev.currentTarget.getAttribute('data-lote'), 10));
        },

        _onLoteTecla: function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onAbrirLote(ev);
            }
        },
    });

    core.action_registry.add('adt_flota_360_carga_pdf', CargaPdf);
    return CargaPdf;
});
