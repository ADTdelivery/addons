odoo.define('adt_flota_360.Flota360', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var session = require('web.session');

    var esc = _.escape;
    var PAGINA = 40;
    var ESPERA_BUSQUEDA = 280;

    var NIVEL_LABEL = {critico: 'Crítico', atencion: 'Atención', ok: 'Al día', info: 'Info', neutral: ''};

    // Columnas de módulos en la tabla de resultados (en este orden).
    var COLUMNAS = [
        {key: 'cuentas', titulo: 'Deuda', num: true},
        {key: 'papeletas', titulo: 'Papeletas', num: true},
        {key: 'gps', titulo: 'GPS'},
        {key: 'placa', titulo: 'Placa'},
    ];

    var VISTAS_DEUDA = [['cronograma', 'Cronograma'], ['pagos', 'Pagos'], ['historial', 'Historial']];
    var FILTROS_CRONO = [['por_cobrar', 'Por cobrar'], ['todas', 'Todas'], ['pagadas', 'Pagadas']];

    // ------------------------------------------------------------------
    // Formato
    // ------------------------------------------------------------------

    function soles(n) {
        return 'S/ ' + (n || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function solesCorto(n) {
        return 'S/ ' + Math.round(n || 0).toLocaleString('es-PE');
    }

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function fecha(iso) {
        if (!iso) {
            return '—';
        }
        var p = iso.slice(0, 10).split('-');
        return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : iso;
    }

    function fechaHora(utc) {
        if (!utc) {
            return '—';
        }
        var d = new Date(utc.replace(' ', 'T') + 'Z');
        return d.toLocaleDateString('es-PE', {day: '2-digit', month: '2-digit', year: 'numeric'}) + ' ' +
            d.toLocaleTimeString('es-PE', {hour: '2-digit', minute: '2-digit'});
    }

    // Datetime UTC de Odoo ("YYYY-MM-DD HH:MM:SS") → "hace 5 min".
    function hace(utc) {
        if (!utc) {
            return 'sin reporte';
        }
        var min = Math.round((Date.now() - new Date(utc.replace(' ', 'T') + 'Z').getTime()) / 60000);
        if (min < 1) { return 'hace instantes'; }
        if (min < 60) { return 'hace ' + min + ' min'; }
        var h = Math.round(min / 60);
        if (h < 24) { return 'hace ' + h + ' h'; }
        var d = Math.round(h / 24);
        return 'hace ' + d + (d === 1 ? ' día' : ' días');
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
    }

    // Resalta el término buscado dentro de un texto.
    function marcar(texto, termino) {
        var t = esc(texto || '');
        var q = (termino || '').trim();
        if (q.length < 2) {
            return t;
        }
        var re = new RegExp('(' + esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
        return t.replace(re, '<mark>$1</mark>');
    }

    // Indicador de estado: punto de color + texto (el color nunca va solo).
    function estado(nivel, texto) {
        return '<span class="adt_f360__st is-' + (nivel || 'neutral') + '"><i aria-hidden="true"></i>' + esc(texto) + '</span>';
    }

    function badge(nivel, texto) {
        return '<span class="adt_f360__badge is-' + (nivel || 'neutral') + '">' + esc(texto) + '</span>';
    }

    var Flota360 = AbstractAction.extend({
        template: 'adt_flota_360.Main',
        hasControlPanel: false,

        events: {
            'input [data-ref="q"]': '_onInput',
            'keydown [data-ref="q"]': '_onSearchKey',
            'click [data-action="clear"]': '_onClear',
            'click [data-filtro]': '_onFiltro',
            'click [data-row]': '_onRow',
            'keydown [data-row]': '_onRowKey',
            'click [data-action="more"]': '_onMore',
            'click [data-action="close"]': '_closeDrawer',
            'click [data-action="full"]': '_onFull',
            'click [data-tab]': '_onTab',
            'click [data-accion]': '_onAccion',
            'click [data-menu]': '_onMenu',
            'click [data-vista]': '_onVistaDeuda',
            'click [data-crono]': '_onFiltroCrono',
            'click [data-expandir]': '_onExpandir',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.termino = '';
            this.filtro = 'todos';
            this.filtros = [];
            this.items = [];
            this.total = 0;
            this.contadores = {};
            this.cartera = {};
            this.detalle = null;
            this.tab = 'resumen';
            // Estado de la vista de deuda: se conserva al recargar la ficha tras una operación.
            this.vistaDeuda = {};
            this.filtroCrono = {};
            this.expandidas = {};
            this._acciones = [];
            this._seq = 0;
            this._listaSucia = false;
            this._buscarDiferido = _.debounce(this._buscar.bind(this, false), ESPERA_BUSQUEDA);
            this._onGlobalKey = this._onGlobalKey.bind(this);
            this._onGlobalClick = this._onGlobalClick.bind(this);
        },

        willStart: function () {
            var self = this;
            var filtros = this._rpc({model: 'adt.flota360', method: 'get_filtros', args: []}).then(function (f) {
                self.filtros = f;
            });
            return Promise.all([this._super.apply(this, arguments), filtros]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                document.addEventListener('keydown', self._onGlobalKey);
                document.addEventListener('click', self._onGlobalClick, true);
                self._renderFiltros();
                self._buscar(false);
            });
        },

        on_attach_callback: function () {
            this._ref('q').trigger('focus');
        },

        destroy: function () {
            document.removeEventListener('keydown', this._onGlobalKey);
            document.removeEventListener('click', this._onGlobalClick, true);
            this._super.apply(this, arguments);
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        // ------------------------------------------------------------------
        // Datos
        // ------------------------------------------------------------------

        _buscar: function (agregar) {
            var self = this;
            var seq = ++this._seq;
            if (!agregar) {
                this._renderCargando();
            }
            return this._rpc({
                model: 'adt.flota360',
                method: 'buscar',
                kwargs: {
                    termino: this.termino,
                    filtro: this.filtro,
                    offset: agregar ? this.items.length : 0,
                    limit: PAGINA,
                },
            }).then(function (res) {
                if (seq !== self._seq) {
                    return; // llegó una búsqueda más reciente
                }
                self.items = agregar ? self.items.concat(res.items) : res.items;
                self.total = res.total;
                self.contadores = res.contadores;
                self.cartera = res.cartera || {};
                self.truncado = res.truncado;
                self._renderFiltros();
                self._renderCartera();
                self._renderLista();
            });
        },

        _cargarDetalle: function (id) {
            var self = this;
            return this._rpc({model: 'adt.flota360', method: 'detalle', args: [id]}).then(function (d) {
                if (id !== self._drawerId) {
                    return;
                }
                self.detalle = d;
                self._renderDrawer();
            });
        },

        // ------------------------------------------------------------------
        // Render: búsqueda, cifras y tabla
        // ------------------------------------------------------------------

        _renderFiltros: function () {
            var self = this;
            this._ref('filtros').html(this.filtros.map(function (f) {
                var n = self.contadores[f.key];
                var activo = f.key === self.filtro;
                var alerta = f.key !== 'todos' && n > 0;
                return '<button type="button" class="adt_f360__filter' + (activo ? ' is-active' : '') +
                    '" data-filtro="' + f.key + '" aria-pressed="' + activo + '">' + esc(f.label) +
                    (n === undefined ? '' : '<span class="adt_f360__count' + (alerta ? ' is-alert' : '') + '">' + entero(n) + '</span>') +
                    '</button>';
            }).join(''));
            this.$el.toggleClass('has-query', !!this.termino);
        },

        _renderCartera: function () {
            var c = this.cartera;
            var n = this.contadores;
            var celdas = [
                ['Vehículos', entero(n.todos), this.termino ? 'Coinciden con la búsqueda' : 'Total de la flota'],
                ['Cartera vencida', soles(c.vencido), plural(n.mora || 0, 'vehículo con atraso', 'vehículos con atraso'), c.vencido > 0 ? 'critico' : ''],
                ['Mora por cobrar', soles(c.mora), 'Registrada en las cuentas', c.mora > 0 ? 'atencion' : ''],
                ['Papeletas pendientes', soles(c.papeletas), plural(n.papeletas || 0, 'vehículo', 'vehículos'), c.papeletas > 0 ? 'atencion' : ''],
                ['Capturados', entero(n.capturas), 'Captura o disolución en curso', n.capturas > 0 ? 'critico' : ''],
            ];
            this._ref('cartera').html(celdas.map(function (x) {
                return '<div class="adt_f360__figure' + (x[3] ? ' is-' + x[3] : '') + '">' +
                    '<span class="adt_f360__figure-label">' + esc(x[0]) + '</span>' +
                    '<span class="adt_f360__figure-value">' + esc(x[1]) + '</span>' +
                    '<span class="adt_f360__figure-sub">' + esc(x[2]) + '</span></div>';
            }).join(''));
        },

        _cabeceraTabla: function () {
            return '<thead><tr><th class="is-status">Estado</th><th>Placa</th><th>Vehículo</th><th>Cliente</th>' +
                COLUMNAS.map(function (c) {
                    return '<th' + (c.num ? ' class="is-num"' : '') + '>' + c.titulo + '</th>';
                }).join('') + '<th>Alertas</th></tr></thead>';
        },

        _renderCargando: function () {
            var fila = '<tr class="is-loading">' + new Array(10).join('<td><span class="adt_f360__sk"></span></td>') + '</tr>';
            this._ref('grid').html('<table class="adt_f360__table">' + this._cabeceraTabla() +
                '<tbody>' + new Array(9).join(fila) + '</tbody></table>');
            this._ref('more').empty();
        },

        _renderLista: function () {
            var self = this;
            if (!this.items.length) {
                this._ref('grid').html(
                    '<div class="adt_f360__empty"><h3>Sin resultados' + (this.termino ? ' para «' + esc(this.termino) + '»' : '') + '</h3>' +
                    '<p>Prueba con la placa sin guion, solo el número de documento o parte del nombre del cliente.</p></div>');
                this._ref('more').empty();
                return;
            }
            this._ref('grid').html('<table class="adt_f360__table">' + this._cabeceraTabla() + '<tbody>' +
                this.items.map(function (it) { return self._htmlFila(it); }).join('') + '</tbody></table>');

            var faltan = this.total - this.items.length;
            this._ref('more').html(
                '<span class="adt_f360__muted">' + entero(this.items.length) + ' de ' + entero(this.total) +
                ' · ordenados por prioridad' + (this.truncado ? ' · se evaluaron los primeros 5.000, afina la búsqueda' : '') + '</span>' +
                (faltan > 0 ? '<button type="button" class="adt_f360__btn" data-action="more">Cargar ' + Math.min(faltan, PAGINA) + ' más</button>' : ''));
        },

        _htmlPlaca: function (it, grande) {
            return it.tiene_placa
                ? '<span class="adt_f360__plate' + (grande ? ' is-large' : '') + '">' + marcar(it.placa, this.termino) + '</span>'
                : '<span class="adt_f360__plate is-empty' + (grande ? ' is-large' : '') + '">Sin placa</span>';
        },

        _celdaModulo: function (m) {
            if (!m) {
                return '<td class="adt_f360__muted">—</td>';
            }
            var principal, sub = '';
            if (m.key === 'cuentas') {
                if (m.nivel === 'critico' || m.nivel === 'atencion') {
                    principal = '<span class="adt_f360__amount is-' + m.nivel + '">' + soles(m.monto) + '</span>';
                    sub = esc(m.texto) + (m.dias ? ' · ' + m.dias + ' d de atraso' : '');
                } else {
                    principal = estado(m.nivel, m.texto);
                    sub = esc(m.referencia || '');
                }
                return '<td class="is-num">' + principal + '<div class="adt_f360__sub">' + sub + '</div></td>';
            }
            if (m.key === 'papeletas') {
                principal = m.monto ? '<span class="adt_f360__amount is-' + m.nivel + '">' + soles(m.monto) + '</span>' : estado(m.nivel, m.texto);
                return '<td class="is-num">' + principal + (m.monto ? '<div class="adt_f360__sub">' + esc(m.texto) + '</div>' : '') + '</td>';
            }
            if (m.key === 'gps') {
                return '<td>' + estado(m.nivel, m.texto) + (m.desde ? '<div class="adt_f360__sub">' + hace(m.desde) + '</div>' : '') + '</td>';
            }
            return '<td>' + estado(m.nivel, m.texto) + '</td>';
        },

        _htmlFila: function (it) {
            var self = this;
            var c = it.cliente || {};
            var q = this.termino;
            var mods = _.indexBy(it.modulos, 'key');
            var etiquetas = it.modulos.filter(function (m) {
                return m.key === 'capturas' || m.key === 'taller';
            }).map(function (m) { return badge(m.nivel, m.texto); }).join('');
            var alerta = it.alertas.length
                ? '<div class="adt_f360__alert-text is-' + it.alertas[0].nivel + '">' + esc(it.alertas[0].texto) +
                  (it.alertas.length > 1 ? ' <span class="adt_f360__muted">+' + (it.alertas.length - 1) + '</span>' : '') + '</div>'
                : '';
            return '<tr data-row="' + it.id + '" tabindex="0" class="is-' + it.salud.nivel +
                (this.detalle && this.detalle.id === it.id ? ' is-selected' : '') + '">' +
                '<td class="is-status">' + estado(it.salud.nivel, it.salud.texto) + '</td>' +
                '<td>' + this._htmlPlaca(it) + '</td>' +
                '<td><div class="adt_f360__strong">' + esc([it.marca, it.modelo].filter(Boolean).join(' ') || 'Sin modelo') + '</div>' +
                    '<div class="adt_f360__sub">' + [esc(it.anio), esc(it.color), it.chasis ? 'VIN ' + marcar(it.chasis, q) : ''].filter(Boolean).join(' · ') + '</div></td>' +
                '<td>' + (c.nombre
                    ? '<div class="adt_f360__strong">' + marcar(c.nombre, q) + '</div><div class="adt_f360__sub">' +
                      [c.documento ? marcar(c.documento, q) : '', c.telefono ? marcar(c.telefono, q) : ''].filter(Boolean).join(' · ') + '</div>'
                    : '<span class="adt_f360__muted">Sin cliente</span>') + '</td>' +
                COLUMNAS.map(function (col) { return self._celdaModulo(mods[col.key]); }).join('') +
                '<td class="is-alerts">' + etiquetas + alerta + '</td>' +
                '</tr>';
        },

        // ------------------------------------------------------------------
        // Render: ficha (panel lateral)
        // ------------------------------------------------------------------

        _accion: function (a, extraCls) {
            this._acciones.push(a);
            return '<button type="button" class="adt_f360__btn' + (a.primary ? ' is-primary' : '') + (a.danger ? ' is-danger' : '') +
                (extraCls || '') + '" data-accion="' + (this._acciones.length - 1) + '">' +
                (a.icon ? '<i class="fa ' + esc(a.icon) + '" aria-hidden="true"></i>' : '') + '<span>' + esc(a.label) + '</span></button>';
        },

        _acciones_html: function (lista, cls) {
            var self = this;
            return (lista || []).map(function (a) { return self._accion(a, cls); }).join('');
        },

        // Menú desplegable "Más" con operaciones secundarias.
        _menu: function (lista, etiqueta, cls) {
            var self = this;
            if (!lista || !lista.length) {
                return '';
            }
            return '<div class="adt_f360__menu-wrap">' +
                '<button type="button" class="adt_f360__btn' + (cls || '') + '" data-menu aria-haspopup="true" aria-expanded="false">' +
                (etiqueta ? '<span>' + esc(etiqueta) + '</span><i class="fa fa-caret-down" aria-hidden="true"></i>'
                          : '<i class="fa fa-ellipsis-h" aria-hidden="true"></i><span class="sr-only">Más operaciones</span>') +
                '</button><div class="adt_f360__menu" role="menu">' +
                lista.map(function (a) {
                    self._acciones.push(a);
                    return '<button type="button" role="menuitem" class="adt_f360__menu-item' + (a.danger ? ' is-danger' : '') +
                        '" data-accion="' + (self._acciones.length - 1) + '"><i class="fa ' + esc(a.icon || 'fa-circle-o') +
                        '" aria-hidden="true"></i>' + esc(a.label) + '</button>';
                }).join('') + '</div></div>';
        },

        _abrirDrawer: function (id) {
            this.detalle = null;
            this.tab = 'resumen';
            this.vistaDeuda = {};
            this.filtroCrono = {};
            this.expandidas = {};
            this._drawerId = id;
            this._ref('drawer').html('<div class="adt_f360__drawer-loading">Cargando ficha…</div>');
            this.$el.addClass('is-drawer-open');
            this.$('[data-row]').removeClass('is-selected').filter('[data-row="' + id + '"]').addClass('is-selected');
            return this._cargarDetalle(id);
        },

        _closeDrawer: function () {
            if (!this.$el.hasClass('is-drawer-open')) {
                return;
            }
            this.$el.removeClass('is-drawer-open');
            this.$('[data-row].is-selected').removeClass('is-selected');
            var id = this._drawerId;
            this.detalle = null;
            this._drawerId = null;
            if (this._listaSucia) {
                this._listaSucia = false;
                this._buscar(false);
            } else if (id) {
                this.$('[data-row="' + id + '"]').trigger('focus');
            }
        },

        _renderDrawer: function () {
            var d = this.detalle;
            var $drawer = this._ref('drawer');
            var scroll = $drawer.find('.adt_f360__db').scrollTop() || 0;
            this._acciones = [];
            if (!d) {
                $drawer.html('<div class="adt_f360__drawer-loading">El vehículo ya no existe o no tienes acceso.</div>');
                return;
            }
            var self = this;
            var c = d.cliente || {};
            var mods = _.indexBy(d.modulos, 'key');
            var tabs = [{key: 'resumen', titulo: 'Resumen'}].concat(
                d.secciones.filter(function (s) { return s.key !== 'vehiculo' && s.key !== 'cliente'; }));

            var head =
                '<header class="adt_f360__dh">' +
                    '<div class="adt_f360__dh-main">' +
                        this._htmlPlaca(d, true) +
                        '<div class="adt_f360__dh-text">' +
                            '<div class="adt_f360__dh-title">' + esc([d.marca, d.modelo].filter(Boolean).join(' ') || 'Vehículo') +
                                ' <span class="adt_f360__muted">' + esc([d.anio, d.color].filter(Boolean).join(' · ')) + '</span></div>' +
                            '<div class="adt_f360__dh-sub">' + (c.nombre
                                ? esc(c.nombre) + (c.documento ? ' · ' + esc(c.documento) : '') + (c.telefono ? ' · ' + esc(c.telefono) : '')
                                : 'Sin cliente asignado') + '</div>' +
                        '</div>' +
                        '<div class="adt_f360__dh-status">' + estado(d.salud.nivel, d.salud.texto) + '</div>' +
                        '<div class="adt_f360__dh-tools">' +
                            this._menu(d.acciones, 'Registrar', '') +
                            '<button type="button" class="adt_f360__icon-btn" data-action="full" title="Abrir formulario del vehículo">' +
                                '<i class="fa fa-external-link" aria-hidden="true"></i></button>' +
                            '<button type="button" class="adt_f360__icon-btn" data-action="close" title="Cerrar (Esc)">' +
                                '<i class="fa fa-times" aria-hidden="true"></i></button>' +
                        '</div>' +
                    '</div>' +
                    '<nav class="adt_f360__tabs" role="tablist">' + tabs.map(function (t) {
                        var m = mods[t.key];
                        var marca = m && (m.nivel === 'critico' || m.nivel === 'atencion')
                            ? '<i class="adt_f360__tab-dot is-' + m.nivel + '" title="' + NIVEL_LABEL[m.nivel] + '"></i>' : '';
                        return '<button type="button" role="tab" class="adt_f360__tab' + (t.key === self.tab ? ' is-active' : '') +
                            '" data-tab="' + t.key + '" aria-selected="' + (t.key === self.tab) + '">' + esc(t.titulo) + marca + '</button>';
                    }).join('') + '</nav>' +
                '</header>';

            var seccion = _.findWhere(d.secciones, {key: this.tab});
            var body;
            if (this.tab === 'resumen') {
                body = this._htmlResumen(d);
            } else if (seccion && seccion.deuda) {
                body = this._htmlDeuda(seccion);
            } else {
                body = this._htmlSeccion(seccion);
            }
            $drawer.html(head + '<div class="adt_f360__db">' + body + '</div>');
            $drawer.find('.adt_f360__db').scrollTop(scroll);
        },

        _panel: function (titulo, contenido, acciones, extra) {
            return '<section class="adt_f360__panel' + (extra || '') + '">' +
                '<header class="adt_f360__panel-head"><h3>' + esc(titulo) + '</h3>' +
                (acciones ? '<div class="adt_f360__panel-actions">' + acciones + '</div>' : '') + '</header>' +
                '<div class="adt_f360__panel-body">' + contenido + '</div></section>';
        },

        _htmlResumen: function (d) {
            var self = this;
            var tabs = _.pluck(d.secciones, 'key');
            var alertas = d.alertas.length
                ? '<ul class="adt_f360__alerts">' + d.alertas.map(function (a) {
                    var ir = tabs.indexOf(a.modulo) >= 0;
                    return '<li class="is-' + a.nivel + '"' + (ir ? ' data-tab="' + a.modulo + '" role="button" tabindex="0"' : '') + '>' +
                        estado(a.nivel, NIVEL_LABEL[a.nivel]) + '<span class="adt_f360__alert-msg">' + esc(a.texto) + '</span>' +
                        (ir ? '<span class="adt_f360__link">Ver detalle</span>' : '') + '</li>';
                }).join('') + '</ul>'
                : '<p class="adt_f360__muted">Ningún módulo reporta pendientes para este vehículo.</p>';

            var modulos = '<table class="adt_f360__dtable"><thead><tr><th>Módulo</th><th>Estado</th><th class="is-num">Importe</th><th></th></tr></thead><tbody>' +
                d.modulos.map(function (m) {
                    var ir = tabs.indexOf(m.key) >= 0;
                    return '<tr' + (ir ? ' data-tab="' + m.key + '" class="is-link"' : '') + '><td class="adt_f360__strong">' + esc(m.titulo) + '</td>' +
                        '<td>' + estado(m.nivel, m.texto) + (m.desde ? ' <span class="adt_f360__muted">· ' + hace(m.desde) + '</span>' : '') +
                        (m.dias ? ' <span class="adt_f360__muted">· ' + m.dias + ' d de atraso</span>' : '') + '</td>' +
                        '<td class="is-num">' + (m.monto ? soles(m.monto) : '') + '</td>' +
                        '<td class="is-num">' + (ir ? '<i class="fa fa-angle-right adt_f360__muted" aria-hidden="true"></i>' : '') + '</td></tr>';
                }).join('') + '</tbody></table>';

            var html = this._panel('Alertas', alertas) + this._panel('Estado por módulo', modulos, null, ' is-flush');
            ['vehiculo', 'cliente'].forEach(function (key) {
                var s = _.findWhere(d.secciones, {key: key});
                if (s) {
                    html += self._htmlSeccion(s);
                }
            });
            return '<div class="adt_f360__cols">' + html + '</div>';
        },

        _htmlCampos: function (campos) {
            if (!campos || !campos.length) {
                return '';
            }
            return '<dl class="adt_f360__fields">' + campos.map(function (c) {
                return '<div><dt>' + esc(c[0]) + '</dt><dd>' + esc(c[1]) + '</dd></div>';
            }).join('') + '</dl>';
        },

        _htmlKpis: function (kpis) {
            if (!kpis || !kpis.length) {
                return '';
            }
            return '<dl class="adt_f360__facts">' + kpis.map(function (k) {
                var valor = k.monto !== undefined ? soles(k.monto) : esc(k.texto);
                return '<div' + (k.nivel ? ' class="is-' + k.nivel + '"' : '') + '><dt>' + esc(k.label) + '</dt><dd>' + valor +
                    (k.sub ? ' <span class="adt_f360__muted">' + esc(k.sub) + '</span>' : '') + '</dd></div>';
            }).join('') + '</dl>';
        },

        _htmlGps: function (g) {
            var mapa = '';
            if (g.lat && g.lon) {
                var d = 0.006;
                var bbox = [g.lon - d, g.lat - d, g.lon + d, g.lat + d].join(',');
                mapa = '<iframe class="adt_f360__map" loading="lazy" title="Ubicación del vehículo" ' +
                    'src="https://www.openstreetmap.org/export/embed.html?bbox=' + encodeURIComponent(bbox) +
                    '&amp;layer=mapnik&amp;marker=' + encodeURIComponent(g.lat + ',' + g.lon) + '"></iframe>';
            }
            var nivel = g.status === 'online' ? 'ok' : (g.status === 'offline' ? 'atencion' : 'neutral');
            return '<div class="adt_f360__gps">' +
                '<div class="adt_f360__gps-line">' + estado(nivel, g.estado) +
                '<span class="adt_f360__muted">Último reporte del equipo ' + hace(g.ultimo) +
                (g.refrescado ? ' · consultado a Traccar ' + hace(g.refrescado) : '') + '</span></div>' +
                (g.direccion ? '<div class="adt_f360__gps-addr">' + esc(g.direccion) + '</div>' : '') +
                mapa + '</div>';
        },

        // Documentos del expediente: rechazados (con observación) y sin cargar primero.
        _htmlDocumentos: function (docs) {
            if (!docs || !docs.length) {
                return '';
            }
            var NIV = {rechazado: ['critico', 'Rechazado'], aceptado: ['ok', 'Aceptado']};
            // Los no cargados se resumen en una línea: varios no aplican según el tipo de cliente.
            var faltan = docs.filter(function (d) { return d.estado === 'falta'; });
            var cargados = docs.filter(function (d) { return d.estado !== 'falta'; });
            return '<div class="adt_f360__label adt_f360__docs-title">Documentos</div>' +
                (cargados.length ? '<ul class="adt_f360__doclist">' + cargados.map(function (d) {
                    var n = NIV[d.estado];
                    return '<li class="is-' + d.estado + '"><span class="adt_f360__doclist-name">' + esc(d.label) + '</span>' +
                        estado(n[0], n[1]) + (d.obs ? '<div class="adt_f360__doclist-obs">' + esc(d.obs) + '</div>' : '') + '</li>';
                }).join('') + '</ul>' : '<p class="adt_f360__muted">Aún no se cargan documentos.</p>') +
                (faltan.length ? '<div class="adt_f360__doclist-missing"><b>Sin cargar:</b> ' +
                    faltan.map(function (d) { return esc(d.label); }).join(', ') + '</div>' : '');
        },

        _htmlItem: function (it) {
            return '<article class="adt_f360__item">' +
                '<div class="adt_f360__item-head"><div><span class="adt_f360__strong">' + esc(it.titulo) + '</span>' +
                (it.badge ? ' ' + badge(it.badge.nivel, it.badge.texto) : '') +
                (it.subtitulo ? '<div class="adt_f360__sub">' + esc(it.subtitulo) + '</div>' : '') + '</div>' +
                ((it.acciones && it.acciones.length) || (it.mas && it.mas.length)
                    ? '<div class="adt_f360__item-actions">' + this._acciones_html(it.acciones, ' is-small') +
                      this._menu(it.mas, 'Más', ' is-small') + '</div>' : '') +
                '</div>' +
                this._htmlKpis(it.kpis) +
                (it.nota ? '<div class="adt_f360__note">' + esc(it.nota) + '</div>' : '') +
                this._htmlDocumentos(it.documentos) +
                '</article>';
        },

        _htmlSeccion: function (s) {
            if (!s) {
                return '';
            }
            var self = this;
            var contenido = this._htmlCampos(s.campos);
            if (s.documentos && s.documentos.length) {
                contenido += '<div class="adt_f360__docs"><span class="adt_f360__label">Documentos</span>' + s.documentos.map(function (doc) {
                    return estado(doc.ok ? 'ok' : 'neutral', doc.label + (doc.ok ? '' : ' (falta)'));
                }).join('') + '</div>';
            }
            if (s.gps) {
                contenido += this._htmlGps(s.gps);
            }
            contenido += this._htmlKpis(s.kpis);
            if (s.items) {
                contenido += s.items.length
                    ? s.items.map(function (it) { return self._htmlItem(it); }).join('')
                    : '<p class="adt_f360__muted">' + esc(s.vacio || 'Sin registros.') + '</p>';
            } else if (s.vacio && !s.campos && !s.gps) {
                contenido += '<p class="adt_f360__muted">' + esc(s.vacio) + '</p>';
            }
            return this._panel(s.titulo, contenido, this._acciones_html(s.acciones, ' is-small'));
        },

        // ------------------------------------------------------------------
        // Render: deuda
        // ------------------------------------------------------------------

        _htmlDeuda: function (s) {
            var self = this;
            var html = '';
            if (!s.deuda.length) {
                return this._panel('Deuda', '<p class="adt_f360__muted">' + esc(s.vacio) + '</p>', this._acciones_html(s.acciones, ' is-small'));
            }
            s.deuda.forEach(function (cuenta, i) {
                html += self._htmlCuenta(cuenta, i === 0);
            });
            if (s.acciones && s.acciones.length) {
                html += '<div class="adt_f360__footer-actions">' + this._acciones_html(s.acciones, ' is-small') + '</div>';
            }
            return html;
        },

        _htmlCuenta: function (c, vigente) {
            var f = c.cifras;
            var vista = this.vistaDeuda[c.id] || 'cronograma';
            var pct = f.total_cuotas ? Math.round(f.pagadas * 100 / f.total_cuotas) : 0;
            var historica = !vigente && ['cancelado', 'pagado'].indexOf(c.state) >= 0;

            var cabecera =
                '<header class="adt_f360__acc-head">' +
                    '<div><div class="adt_f360__acc-title"><span class="adt_f360__mono">' + esc(c.referencia) + '</span> ' +
                        badge(c.nivel, c.estado) + (c.recuperado ? ' ' + badge('critico', 'Recuperado') : '') +
                        (c.captura_prioridad ? ' ' + badge('atencion', 'Captura ' + c.captura_prioridad.toLowerCase()) : '') + '</div>' +
                    '<div class="adt_f360__sub">' + esc(c.detalle) + '</div></div>' +
                    '<div class="adt_f360__acc-actions">' + this._acciones_html(c.acciones) + this._menu(c.mas, 'Más', '') + '</div>' +
                '</header>';

            var cifras = '<div class="adt_f360__acc-figures">' + [
                ['Para ponerse al día', soles(f.al_dia), f.vencidas ? plural(f.vencidas, 'cuota vencida', 'cuotas vencidas') + ' + mora' : 'Sin cuotas vencidas', f.al_dia > 0 ? 'critico' : 'ok'],
                ['Para cancelar hoy', soles(f.cancelar_hoy), f.cancelar_nota, ''],
                ['Capital pendiente', soles(f.capital), 'Cuota ' + soles(f.cuota), ''],
                ['Mora pendiente', soles(f.mora), f.mora_registrada ? soles(f.mora_registrada) + ' ya registrada' : 'Calculada a hoy', f.mora > 0 ? 'atencion' : ''],
                ['Días de atraso', f.dias_atraso ? entero(f.dias_atraso) : '0', f.dias_atraso ? 'Desde la cuota más antigua' : 'Al día', f.dias_atraso > 0 ? 'critico' : ''],
            ].map(function (x) {
                return '<div class="adt_f360__figure' + (x[3] ? ' is-' + x[3] : '') + '">' +
                    '<span class="adt_f360__figure-label">' + esc(x[0]) + '</span>' +
                    '<span class="adt_f360__figure-value">' + esc(x[1]) + '</span>' +
                    '<span class="adt_f360__figure-sub">' + esc(x[2]) + '</span></div>';
            }).join('') + '</div>';

            var avance = '<div class="adt_f360__acc-progress">' +
                '<div class="adt_f360__acc-progress-head">' +
                    '<span><b>' + f.pagadas + '</b> de ' + f.total_cuotas + ' cuotas pagadas <span class="adt_f360__muted">(' + pct + '%)</span></span>' +
                    '<span><b>' + soles(f.pagado) + '</b> pagado de ' + soles(f.financiado) + '</span>' +
                '</div>' +
                '<div class="adt_f360__progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct +
                    '" aria-label="Avance de pago"><span style="width:' + pct + '%"></span></div>' +
                '<div class="adt_f360__acc-progress-foot">' +
                    (c.proxima ? '<span>Próximo vencimiento <b>' + fecha(c.proxima.fecha) + '</b> · ' + soles(c.proxima.monto) +
                        ' <span class="adt_f360__muted">(' + (c.proxima.dias === 0 ? 'hoy' : 'en ' + plural(c.proxima.dias, 'día', 'días')) + ')</span></span>' : '') +
                    (c.ultimo_pago ? '<span>Último pago <b>' + fecha(c.ultimo_pago.fecha) + '</b> · ' + soles(c.ultimo_pago.monto) +
                        (c.ultimo_pago.ref ? ' <span class="adt_f360__muted">op. ' + esc(c.ultimo_pago.ref) + '</span>' : '') + '</span>' : '') +
                '</div>' +
                '</div>';

            var reportes = c.reportes.length ? this._htmlReportes(c.reportes) : '';

            var vistas = '<div class="adt_f360__subtabs">' + VISTAS_DEUDA.map(function (v) {
                var n = v[0] === 'cronograma' ? c.cuotas.length : (v[0] === 'pagos' ? c.pagos.length : c.historial.length);
                return '<button type="button" class="adt_f360__subtab' + (vista === v[0] ? ' is-active' : '') + '" data-vista="' +
                    v[0] + '" data-cuenta="' + c.id + '">' + v[1] + ' <span class="adt_f360__muted">' + n + '</span></button>';
            }).join('') + (vista === 'cronograma' ? this._htmlFiltroCrono(c) : '') + '</div>';

            var contenido;
            if (vista === 'pagos') {
                contenido = this._htmlPagos(c.pagos);
            } else if (vista === 'historial') {
                contenido = this._htmlHistorial(c.historial);
            } else {
                contenido = this._htmlCronograma(c);
            }

            return '<section class="adt_f360__panel adt_f360__account' + (historica ? ' is-historic' : '') + '">' +
                cabecera + cifras + avance + reportes + vistas + contenido + '</section>';
        },

        _htmlFiltroCrono: function (c) {
            var actual = this.filtroCrono[c.id] || 'por_cobrar';
            return '<div class="adt_f360__seg">' + FILTROS_CRONO.map(function (x) {
                return '<button type="button" class="' + (actual === x[0] ? 'is-active' : '') + '" data-crono="' + x[0] +
                    '" data-cuenta="' + c.id + '">' + x[1] + '</button>';
            }).join('') + '</div>';
        },

        _htmlReportes: function (reportes) {
            var self = this;
            return '<div class="adt_f360__notice">' +
                '<div class="adt_f360__notice-title">' + plural(reportes.length, 'pago informado desde la app', 'pagos informados desde la app') +
                ' por validar</div>' +
                '<table class="adt_f360__dtable"><thead><tr><th>Fecha</th><th>Cuota</th><th class="is-num">Monto</th><th>Operación</th>' +
                '<th class="is-num">Mora</th><th>Comprobantes</th><th></th></tr></thead><tbody>' +
                reportes.map(function (r) {
                    return '<tr><td>' + fechaHora(r.fecha) + '</td><td>' + esc(r.cuota) + '</td><td class="is-num">' + soles(r.monto) + '</td>' +
                        '<td class="adt_f360__mono">' + esc(r.operacion || '—') + '</td>' +
                        '<td class="is-num">' + (r.mora ? soles(r.mora) + (r.operacion_mora ? '<div class="adt_f360__sub">op. ' + esc(r.operacion_mora) + '</div>' : '') : '—') + '</td>' +
                        '<td>' + r.comprobantes + '</td>' +
                        '<td class="is-actions">' + self._acciones_html(r.acciones, ' is-small') + '</td></tr>' +
                        (r.comentario ? '<tr class="is-note"><td colspan="7">' + esc(r.comentario) + '</td></tr>' : '');
                }).join('') + '</tbody></table></div>';
        },

        _htmlCronograma: function (c) {
            var self = this;
            var filtro = this.filtroCrono[c.id] || 'por_cobrar';
            var filas = c.cuotas.filter(function (q) {
                if (filtro === 'pagadas') { return q.grupo === 'pagada'; }
                if (filtro === 'por_cobrar') { return q.grupo === 'vencida' || q.grupo === 'a_cuenta' || q.grupo === 'por_vencer' || q.mora > 0; }
                return true;
            });
            if (!filas.length) {
                return '<p class="adt_f360__muted adt_f360__pad">' +
                    (filtro === 'por_cobrar' ? 'No hay cuotas por cobrar en esta cuenta.' : 'Sin cuotas para mostrar.') + '</p>';
            }
            var total = {monto: 0, pagado: 0, saldo: 0, mora: 0};
            var cuerpo = filas.map(function (q) {
                total.monto += q.monto; total.pagado += q.pagado; total.saldo += q.saldo; total.mora += q.mora;
                var abierta = !!self.expandidas[q.id];
                var marcas = (q.observaciones.length ? '<i class="fa fa-comment-o" title="' + q.observaciones.length + ' observación(es)"></i>' : '') +
                    (q.reportes.length ? '<i class="fa fa-mobile is-info" title="Pago informado desde la app por validar"></i>' : '') +
                    (q.mora_manual ? '<i class="fa fa-pencil" title="Mora editada manualmente"></i>' : '');
                var fila = '<tr class="is-' + q.grupo + (abierta ? ' is-open' : '') + '">' +
                    '<td class="is-toggle"><button type="button" class="adt_f360__toggle" data-expandir="' + q.id + '" aria-expanded="' + abierta +
                        '" title="Ver pagos y observaciones"><i class="fa fa-angle-' + (abierta ? 'down' : 'right') + '" aria-hidden="true"></i></button></td>' +
                    '<td><span class="adt_f360__strong">' + esc(q.nombre) + '</span>' + (q.tipo ? ' ' + badge('info', q.tipo) : '') +
                        '<span class="adt_f360__marks">' + marcas + '</span></td>' +
                    '<td>' + fecha(q.fecha) + '</td>' +
                    '<td class="is-num">' + soles(q.monto) + '</td>' +
                    '<td class="is-num">' + (q.pagado ? soles(q.pagado) : '—') + '</td>' +
                    '<td class="is-num adt_f360__strong">' + (q.saldo ? soles(q.saldo) : '—') + '</td>' +
                    '<td class="is-num">' + (q.mora ? '<span class="adt_f360__amount is-atencion">' + soles(q.mora) + '</span><div class="adt_f360__sub">' +
                        q.mora_dias + ' d' + (q.mora_registrada ? ' · registrada' : '') + '</div>' : '—') + '</td>' +
                    '<td>' + badge(q.nivel, q.estado) + '</td>' +
                    '<td>' + (q.pago_fecha ? fecha(q.pago_fecha) +
                        (q.pago_ref ? '<div class="adt_f360__sub adt_f360__mono">' + esc(q.pago_ref) + '</div>' : '') : '<span class="adt_f360__muted">—</span>') + '</td>' +
                    '<td class="is-actions">' + self._acciones_html(q.acciones, ' is-small') + self._menu(q.mas, '', ' is-small is-icon') + '</td>' +
                    '</tr>';
                return fila + (abierta ? '<tr class="is-detail"><td></td><td colspan="9">' + self._htmlDetalleCuota(q) + '</td></tr>' : '');
            }).join('');
            return '<div class="adt_f360__scroll-x"><table class="adt_f360__dtable adt_f360__crono"><thead><tr><th></th><th>Cuota</th><th>Vence</th>' +
                '<th class="is-num">Monto</th><th class="is-num">Pagado</th><th class="is-num">Saldo</th><th class="is-num">Mora</th>' +
                '<th>Estado</th><th>Pago</th><th></th></tr></thead><tbody>' + cuerpo + '</tbody>' +
                '<tfoot><tr><td></td><td colspan="2">' + plural(filas.length, 'cuota', 'cuotas') + '</td>' +
                '<td class="is-num">' + soles(total.monto) + '</td><td class="is-num">' + soles(total.pagado) + '</td>' +
                '<td class="is-num">' + soles(total.saldo) + '</td><td class="is-num">' + soles(total.mora) + '</td><td colspan="3"></td></tr></tfoot>' +
                '</table></div>';
        },

        _htmlDetalleCuota: function (q) {
            var html = '<div class="adt_f360__qdetail">';
            html += '<div><div class="adt_f360__label">Pagos aplicados</div>' + (q.pagos.length ? this._htmlPagos(q.pagos, true)
                : '<p class="adt_f360__muted">Sin pagos registrados.</p>') + '</div>';
            html += '<div><div class="adt_f360__label">Observaciones</div>' + (q.observaciones.length
                ? '<ul class="adt_f360__obs">' + q.observaciones.map(function (o) {
                    return '<li><span class="adt_f360__muted">' + fecha(o.fecha) + '</span> ' + esc(o.texto) +
                        (o.adjuntos ? ' <span class="adt_f360__muted">· ' + plural(o.adjuntos, 'adjunto', 'adjuntos') + '</span>' : '') + '</li>';
                }).join('') + '</ul>'
                : '<p class="adt_f360__muted">Sin observaciones.</p>') + '</div>';
            if (q.reportes.length) {
                html += '<div>' + this._htmlReportes(q.reportes) + '</div>';
            }
            return html + '</div>';
        },

        _htmlPagos: function (pagos, compacto) {
            if (!pagos.length) {
                return '<p class="adt_f360__muted adt_f360__pad">Sin pagos registrados.</p>';
            }
            var total = 0;
            var filas = pagos.map(function (p) {
                total += p.monto;
                return '<tr><td>' + fecha(p.fecha) + '</td>' + (compacto ? '' : '<td>' + esc(p.cuota) + '</td>') +
                    '<td class="is-num">' + soles(p.monto) + '</td><td class="adt_f360__mono">' + esc(p.ref || '—') + '</td>' +
                    '<td>' + esc(p.diario) + '</td>' +
                    '<td class="is-num">' + (p.mora ? soles(p.mora) : '—') + '</td>' +
                    '<td>' + (p.mora_estado ? badge(p.mora_estado === 'Pagada' ? 'ok' : 'atencion', 'Mora ' + p.mora_estado.toLowerCase()) : '') + '</td></tr>';
            }).join('');
            return '<div class="adt_f360__scroll-x"><table class="adt_f360__dtable"><thead><tr><th>Fecha</th>' + (compacto ? '' : '<th>Cuota</th>') +
                '<th class="is-num">Monto</th><th>Operación</th><th>Diario</th><th class="is-num">Mora</th><th></th></tr></thead><tbody>' + filas + '</tbody>' +
                (compacto ? '' : '<tfoot><tr><td colspan="2">' + plural(pagos.length, 'pago', 'pagos') + '</td><td class="is-num">' + soles(total) +
                    '</td><td colspan="4"></td></tr></tfoot>') + '</table></div>';
        },

        _htmlHistorial: function (eventos) {
            if (!eventos.length) {
                return '<p class="adt_f360__muted adt_f360__pad">Sin movimientos registrados en la cuenta.</p>';
            }
            return '<ol class="adt_f360__timeline">' + eventos.map(function (e) {
                return '<li><div class="adt_f360__sub">' + fechaHora(e.fecha) + (e.autor ? ' · ' + esc(e.autor) : '') + '</div>' +
                    (e.texto ? '<div>' + esc(e.texto) + '</div>' : '') +
                    (e.cambios.length ? '<div class="adt_f360__changes">' + e.cambios.map(esc).join('<br/>') + '</div>' : '') + '</li>';
            }).join('') + '</ol>';
        },

        // ------------------------------------------------------------------
        // Operaciones
        // ------------------------------------------------------------------

        _recargar: function () {
            this._listaSucia = true;
            if (this._drawerId && this.$el.hasClass('is-drawer-open')) {
                return this._cargarDetalle(this._drawerId);
            }
        },

        _ejecutar: function (a) {
            var self = this;
            var alCerrar = {on_close: function () { self._recargar(); }};
            if (a.tipo === 'url') {
                window.open(a.url, a.url.indexOf('tel:') === 0 ? '_self' : '_blank', 'noopener');
                return;
            }
            if (a.tipo === 'abrir') {
                this.do_action({
                    type: 'ir.actions.act_window',
                    res_model: a.model,
                    res_id: a.res_id || undefined,
                    views: [[false, 'form']],
                    target: 'new',
                    context: a.context || {},
                }, alCerrar);
                return;
            }
            var correr = function () {
                // Misma ruta que los botones de los formularios: el servidor normaliza
                // la acción devuelta (clean_action) para que el cliente pueda abrirla.
                return self._rpc({
                    route: '/web/dataset/call_button',
                    params: {
                        model: a.model,
                        method: a.method,
                        args: a.args || [[a.res_id]],
                        kwargs: {context: session.user_context},
                    },
                }).then(function (res) {
                    if (res && typeof res === 'object' && res.type) {
                        return self.do_action(res, alCerrar);
                    }
                    self.displayNotification({type: 'success', message: a.label + ': operación registrada.'});
                    self._recargar();
                });
            };
            if (a.confirm) {
                Dialog.confirm(this, a.confirm, {confirm_callback: correr, title: a.label});
            } else {
                correr();
            }
        },

        // ------------------------------------------------------------------
        // Eventos
        // ------------------------------------------------------------------

        _onInput: function (ev) {
            this.termino = ev.currentTarget.value;
            this.$el.toggleClass('has-query', !!this.termino);
            this._buscarDiferido();
        },

        _onSearchKey: function (ev) {
            var self = this;
            if (ev.key === 'Enter') {
                this._buscarDiferido.cancel();
                this._buscar(false).then(function () {
                    if (self.items.length === 1) {
                        self._abrirDrawer(self.items[0].id);
                    }
                });
            } else if (ev.key === 'ArrowDown') {
                ev.preventDefault();
                this.$('[data-row]').first().trigger('focus');
            } else if (ev.key === 'Escape' && this.termino) {
                ev.stopPropagation();
                this._onClear();
            }
        },

        _onClear: function () {
            this.termino = '';
            this._ref('q').val('').trigger('focus');
            this._buscarDiferido.cancel();
            this._buscar(false);
        },

        _onFiltro: function (ev) {
            var key = ev.currentTarget.getAttribute('data-filtro');
            this.filtro = key === this.filtro && key !== 'todos' ? 'todos' : key;
            this._renderFiltros();
            this._buscar(false);
        },

        _onRow: function (ev) {
            this._abrirDrawer(parseInt(ev.currentTarget.getAttribute('data-row'), 10));
        },

        // ↑/↓ recorren la tabla; Enter abre la ficha.
        _onRowKey: function (ev) {
            var $row = $(ev.currentTarget);
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onRow(ev);
            } else if (ev.key === 'ArrowDown') {
                ev.preventDefault();
                $row.next('[data-row]').trigger('focus');
            } else if (ev.key === 'ArrowUp') {
                ev.preventDefault();
                var $prev = $row.prev('[data-row]');
                ($prev.length ? $prev : this._ref('q')).trigger('focus');
            }
        },

        _onMore: function () {
            this._ref('more').find('button').prop('disabled', true).text('Cargando…');
            this._buscar(true);
        },

        _onTab: function (ev) {
            var tab = ev.currentTarget.getAttribute('data-tab');
            if (!this.detalle || (tab !== 'resumen' && !_.findWhere(this.detalle.secciones, {key: tab}))) {
                return;
            }
            this.tab = tab;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__db').scrollTop(0);
        },

        _onVistaDeuda: function (ev) {
            this.vistaDeuda[ev.currentTarget.getAttribute('data-cuenta')] = ev.currentTarget.getAttribute('data-vista');
            this._renderDrawer();
        },

        _onFiltroCrono: function (ev) {
            this.filtroCrono[ev.currentTarget.getAttribute('data-cuenta')] = ev.currentTarget.getAttribute('data-crono');
            this._renderDrawer();
        },

        _onExpandir: function (ev) {
            var id = ev.currentTarget.getAttribute('data-expandir');
            this.expandidas[id] = !this.expandidas[id];
            this._renderDrawer();
        },

        _onMenu: function (ev) {
            ev.stopPropagation();
            var $wrap = $(ev.currentTarget).closest('.adt_f360__menu-wrap');
            var abrir = !$wrap.hasClass('is-open');
            this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open').find('[data-menu]').attr('aria-expanded', 'false');
            if (abrir) {
                $wrap.addClass('is-open').find('[data-menu]').attr('aria-expanded', 'true');
                // Abrir hacia arriba si no hay espacio debajo.
                var rect = $wrap[0].getBoundingClientRect();
                $wrap.toggleClass('is-up', window.innerHeight - rect.bottom < 260 && rect.top > 260);
            }
        },

        _onAccion: function (ev) {
            ev.stopPropagation();
            this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
            var a = this._acciones[parseInt(ev.currentTarget.getAttribute('data-accion'), 10)];
            if (a) {
                this._ejecutar(a);
            }
        },

        _onFull: function () {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'fleet.vehicle',
                res_id: this._drawerId,
                views: [[false, 'form']],
                target: 'current',
            });
        },

        _onGlobalClick: function (ev) {
            if (this.$el && !$(ev.target).closest('.adt_f360__menu-wrap').length) {
                this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
            }
        },

        _onGlobalKey: function (ev) {
            if (!this.$el || !this.$el.is(':visible') || $('.modal:visible').length) {
                return;
            }
            var enInput = /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName) || ev.target.isContentEditable;
            if (ev.key === 'Escape') {
                if (this.$('.adt_f360__menu-wrap.is-open').length) {
                    this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
                } else {
                    this._closeDrawer();
                }
            } else if (ev.key === '/' && !enInput) {
                ev.preventDefault();
                this._closeDrawer();
                this._ref('q').trigger('focus').trigger('select');
            } else if ((ev.key === 'Enter' || ev.key === ' ') && !enInput && $(ev.target).is('[data-tab]:not(button)')) {
                ev.preventDefault();
                $(ev.target).trigger('click');
            }
        },
    });

    core.action_registry.add('adt_flota_360', Flota360);

    return Flota360;
});
