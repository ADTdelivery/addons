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
        {key: 'expediente', titulo: 'Expediente'},
    ];

    // Navegación de la ficha, agrupada por área. Solo se muestran las secciones que
    // el servidor devuelve (módulos instalados y con acceso).
    var NAV = [
        {titulo: 'General', items: [['resumen', 'Resumen', 'fa-th-large']]},
        {titulo: 'Cliente', items: [['cliente', 'Datos del cliente', 'fa-user'], ['expediente', 'Expediente', 'fa-folder-open-o']]},
        {titulo: 'Crédito y cobranza', items: [['cuentas', 'Crédito y cuotas', 'fa-credit-card'],
            ['papeletas', 'Papeletas', 'fa-file-text-o'], ['capturas', 'Capturas', 'fa-lock']]},
        {titulo: 'Vehículo', items: [['vehiculo', 'Vehículo y documentos', 'fa-motorcycle'],
            ['placa', 'Placa y entrega', 'fa-id-card-o'], ['gps', 'GPS', 'fa-map-marker'],
            ['taller', 'Taller y mantenimiento', 'fa-wrench']]},
    ];

    var DOC_ESTADO = {
        aceptado: ['ok', 'Aceptado'], rechazado: ['critico', 'Rechazado'],
        incompleto: ['atencion', 'Incompleto'], falta: ['neutral', 'Sin cargar'],
    };
    var PASO_LABEL = {ok: 'Completo', atencion: 'Requiere atención', critico: 'Crítico', pendiente: 'Pendiente', info: 'En proceso', neutral: ''};
    var MAX_ARCHIVO_MB = 15;

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

    // Datetime UTC de Odoo <-> valor de <input type="datetime-local"> (hora local).
    function utcALocal(utc) {
        if (!utc) {
            return '';
        }
        var d = new Date(utc.replace(' ', 'T') + 'Z');
        var dos = function (n) { return (n < 10 ? '0' : '') + n; };
        return d.getFullYear() + '-' + dos(d.getMonth() + 1) + '-' + dos(d.getDate()) + 'T' + dos(d.getHours()) + ':' + dos(d.getMinutes());
    }

    function localAUtc(local) {
        if (!local) {
            return false;
        }
        return new Date(local).toISOString().slice(0, 19).replace('T', ' ');
    }

    // File -> {nombre, datos (base64 sin encabezado)}; rechaza los que exceden el límite.
    function leerArchivo(file) {
        return new Promise(function (resolve, reject) {
            if (file.size > MAX_ARCHIVO_MB * 1024 * 1024) {
                reject(new Error('«' + file.name + '» supera los ' + MAX_ARCHIVO_MB + ' MB permitidos.'));
                return;
            }
            var lector = new FileReader();
            lector.onload = function () {
                resolve({nombre: file.name, datos: String(lector.result).split(',')[1] || ''});
            };
            lector.onerror = function () { reject(new Error('No se pudo leer «' + file.name + '».')); };
            lector.readAsDataURL(file);
        });
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
            'click [data-subir]': '_onSubir',
            'change [data-ref="archivo"]': '_onArchivo',
            'dragover [data-subir-zona]': '_onDragOver',
            'dragleave [data-subir-zona]': '_onDragLeave',
            'drop [data-subir-zona]': '_onDrop',
            'click [data-ver]': '_onVer',
            'click [data-quitar]': '_onQuitar',
            'click [data-aceptar]': '_onAceptar',
            'click [data-rechazar]': '_onRechazar',
            'click [data-exp]': '_onExpediente',
            'click [data-modal-close]': '_cerrarModal',
            'submit [data-ref="modal"] form': '_onSubmitModal',
            'click [data-guardar]': '_onSubmitModal',
            'input [data-campo]': '_onCampo',
            'change [data-campo]': '_onCampo',
            'click [data-m2o-opcion]': '_onM2oOpcion',
            'focusout [data-m2o]': '_onM2oBlur',
            'click [data-modo]': '_onModoCredito',
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
            this.expSel = null;
            this._modal = null;
            this._acciones = [];
            this._seq = 0;
            this._listaSucia = false;
            this._buscarDiferido = _.debounce(this._buscar.bind(this, false), ESPERA_BUSQUEDA);
            this._onGlobalKey = this._onGlobalKey.bind(this);
            this._onGlobalClick = this._onGlobalClick.bind(this);
        },

        willStart: function () {
            var self = this;
            this._simularDiferido = _.debounce(this._simularCredito.bind(this), 250);
            this._buscarOpcionesDiferido = _.debounce(this._buscarOpciones.bind(this), 220);
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
            var fila = '<tr class="is-loading">' + new Array(COLUMNAS.length + 6).join('<td><span class="adt_f360__sk"></span></td>') + '</tr>';
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
            this.expSel = null;
            this._drawerId = id;
            this._ref('drawer').html(this._htmlAviso('Cargando ficha…'));
            this.$el.addClass('is-drawer-open');
            this.$('[data-row]').removeClass('is-selected').filter('[data-row="' + id + '"]').addClass('is-selected');
            return this._cargarDetalle(id);
        },

        _htmlAviso: function (texto) {
            return '<div class="adt_f360__drawer-loading"><button type="button" class="adt_f360__btn" data-action="close">' +
                '<i class="fa fa-arrow-left" aria-hidden="true"></i>Volver</button><p>' + esc(texto) + '</p></div>';
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
                $drawer.html(this._htmlAviso('El vehículo ya no existe o no tienes acceso.'));
                return;
            }
            var c = d.cliente || {};
            var head =
                '<header class="adt_f360__dh">' +
                    '<div class="adt_f360__dh-main">' +
                        '<button type="button" class="adt_f360__btn adt_f360__back" data-action="close" title="Volver a la lista (Esc)">' +
                            '<i class="fa fa-arrow-left" aria-hidden="true"></i>Volver</button>' +
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
                            this._menu(d.acciones, 'Registrar', ' is-primary') +
                            '<button type="button" class="adt_f360__icon-btn" data-action="full" title="Abrir formulario del vehículo en Odoo">' +
                                '<i class="fa fa-external-link" aria-hidden="true"></i></button>' +
                        '</div>' +
                    '</div>' +
                '</header>';

            var seccion = _.findWhere(d.secciones, {key: this.tab});
            var body;
            if (this.tab === 'resumen' || !seccion) {
                body = this._htmlResumen(d);
            } else if (seccion.deuda) {
                body = this._htmlDeuda(seccion);
            } else if (seccion.key === 'expediente') {
                body = this._htmlExpedientes(seccion);
            } else if (seccion.key === 'vehiculo') {
                body = this._htmlVehiculo(seccion);
            } else if (seccion.key === 'cliente') {
                body = this._htmlCliente(seccion, d);
            } else {
                body = this._htmlSeccion(seccion);
            }
            var titulo = this.tab === 'resumen' || !seccion ? 'Resumen' : seccion.titulo;
            $drawer.html(head + '<div class="adt_f360__layout">' + this._htmlNav(d) +
                '<div class="adt_f360__db"><div class="adt_f360__db-inner">' +
                '<h2 class="adt_f360__page-title">' + esc(titulo) + '</h2>' + body + '</div></div></div>');
            $drawer.find('.adt_f360__db').scrollTop(scroll);
        },

        // Menú lateral agrupado. El punto de color marca las secciones con pendientes.
        _htmlNav: function (d) {
            var self = this;
            var secciones = _.indexBy(d.secciones, 'key');
            var mods = _.indexBy(d.modulos, 'key');
            var pasos = {};
            (d.recorrido || []).forEach(function (p) {
                if (p.tab && (p.nivel === 'critico' || p.nivel === 'atencion') && pasos[p.tab] !== 'critico') {
                    pasos[p.tab] = p.nivel;
                }
            });
            return '<nav class="adt_f360__nav" aria-label="Secciones de la ficha">' + NAV.map(function (g) {
                var items = g.items.filter(function (it) { return it[0] === 'resumen' || secciones[it[0]]; });
                if (!items.length) {
                    return '';
                }
                return '<div class="adt_f360__nav-group"><div class="adt_f360__nav-title">' + esc(g.titulo) + '</div>' +
                    items.map(function (it) {
                        var m = mods[it[0]];
                        var nivel = m && (m.nivel === 'critico' || m.nivel === 'atencion') ? m.nivel : pasos[it[0]];
                        var activo = self.tab === it[0];
                        return '<button type="button" class="adt_f360__nav-item' + (activo ? ' is-active' : '') + '" data-tab="' + it[0] +
                            '"' + (activo ? ' aria-current="page"' : '') + '><i class="fa ' + it[2] + '" aria-hidden="true"></i>' +
                            '<span>' + esc(it[1]) + '</span>' +
                            (nivel ? '<i class="adt_f360__tab-dot is-' + nivel + '" title="' + NIVEL_LABEL[nivel] + '"></i>' : '') +
                            '</button>';
                    }).join('') + '</div>';
            }).join('') + '</nav>';
        },

        _panel: function (titulo, contenido, acciones, extra) {
            return '<section class="adt_f360__panel' + (extra || '') + '">' +
                '<header class="adt_f360__panel-head"><h3>' + esc(titulo) + '</h3>' +
                (acciones ? '<div class="adt_f360__panel-actions">' + acciones + '</div>' : '') + '</header>' +
                '<div class="adt_f360__panel-body">' + contenido + '</div></section>';
        },

        _htmlResumen: function (d) {
            return this._htmlRecorrido(d.recorrido || []) + this._htmlIndicadores(d);
        },

        // Un cuadro por área: estado, una cifra, una línea de contexto y, si hay, la alerta principal.
        // El detalle completo está en cada sección (el cuadro lleva a ella).
        _htmlIndicadores: function (d) {
            var sec = _.indexBy(d.secciones, 'key');
            var mods = _.indexBy(d.modulos, 'key');
            var alertas = _.groupBy(d.alertas, 'modulo');
            var tiles = [];
            // t: {tab, modulo?, icono, titulo, nivel, estado, valor, sub, pct}
            var add = function (t) {
                if (sec[t.tab]) {
                    t.alerta = (alertas[t.modulo || t.tab] || [])[0];
                    tiles.push(t);
                }
            };

            var cuenta = sec.cuentas && sec.cuentas.deuda && sec.cuentas.deuda[0];
            if (cuenta) {
                var f = cuenta.cifras;
                add({tab: 'cuentas', icono: 'fa-credit-card', titulo: 'Crédito', estado: cuenta.estado,
                    nivel: f.vencidas >= 3 ? 'critico' : (f.al_dia > 0 || cuenta.state === 'borrador' ? 'atencion' : 'ok'),
                    valor: f.al_dia > 0 ? soles(f.al_dia) : 'Al día',
                    sub: f.al_dia > 0 ? 'Vencido · ' + plural(f.dias_atraso, 'día', 'días') + ' de atraso'
                        : (cuenta.proxima ? 'Próxima cuota ' + fecha(cuenta.proxima.fecha) : 'Sin cuotas por vencer'),
                    pct: f.total_cuotas ? Math.round(f.pagadas * 100 / f.total_cuotas) : null,
                    pctLabel: f.pagadas + ' de ' + f.total_cuotas + ' cuotas pagadas'});
            } else if (sec.cuentas) {
                add({tab: 'cuentas', icono: 'fa-credit-card', titulo: 'Crédito', nivel: 'neutral', estado: 'Sin cuenta',
                    valor: 'Sin crédito', sub: 'Créalo desde «Registrar»'});
            }

            var exp = sec.expediente;
            if (exp) {
                var e = exp.expedientes && exp.expedientes[0];
                add(e ? {tab: 'expediente', icono: 'fa-folder-open-o', titulo: 'Expediente', nivel: e.nivel, estado: e.estado,
                    valor: e.avance.completos + ' / ' + e.avance.requeridos, sub: 'documentos aceptados',
                    pct: e.avance.requeridos ? Math.round(e.avance.completos * 100 / e.avance.requeridos) : null}
                    : {tab: 'expediente', icono: 'fa-folder-open-o', titulo: 'Expediente', nivel: 'atencion', estado: 'Pendiente',
                    valor: 'Sin expediente', sub: 'Recomendado antes del crédito'});
            }

            if (sec.papeletas) {
                var mp = mods.papeletas || {};
                add({tab: 'papeletas', icono: 'fa-file-text-o', titulo: 'Papeletas', nivel: mp.nivel || 'ok',
                    estado: mp.monto ? mp.texto : 'Al día', valor: mp.monto ? soles(mp.monto) : 'S/ 0.00',
                    sub: mp.monto ? 'por pagar' : 'Sin papeletas pendientes'});
            }

            if (sec.vehiculo) {
                var docs = (sec.vehiculo.documentos_vehiculo || []).filter(function (x) { return x.obligatorio; });
                var listos = docs.filter(function (x) { return x.estado === 'aceptado'; }).length;
                var mpl = mods.placa || {};
                add({tab: 'vehiculo', modulo: 'placa', icono: 'fa-motorcycle', titulo: 'Vehículo',
                    nivel: docs.length && listos < docs.length ? 'atencion' : (mpl.nivel || 'ok'),
                    estado: docs.length ? listos + '/' + docs.length + ' documentos' : (mpl.texto || ''),
                    valor: d.tiene_placa ? d.placa : 'Sin placa',
                    sub: [d.marca, d.modelo, d.anio].filter(Boolean).join(' ') || 'Vehículo',
                    pct: docs.length ? Math.round(listos * 100 / docs.length) : null,
                    pctLabel: docs.length ? 'Documentos del vehículo' : ''});
            }

            if (sec.gps) {
                var mg = mods.gps || {};
                add({tab: 'gps', icono: 'fa-map-marker', titulo: 'GPS', nivel: mg.nivel || 'neutral', estado: '',
                    valor: mg.texto || 'Sin registrar', sub: mg.desde ? 'Último reporte ' + hace(mg.desde) : 'Sin reportes'});
            }
            if (mods.capturas) {
                add({tab: 'capturas', icono: 'fa-lock', titulo: 'Captura', nivel: 'critico', estado: '',
                    valor: mods.capturas.texto, sub: 'Vehículo retenido'});
            }
            if (mods.taller) {
                add({tab: 'taller', icono: 'fa-wrench', titulo: 'Taller', nivel: mods.taller.nivel, estado: '',
                    valor: mods.taller.texto, sub: 'En el taller'});
            }

            if (!tiles.length) {
                return '<p class="adt_f360__muted">No hay información de los módulos para este vehículo.</p>';
            }
            return '<div class="adt_f360__kpis">' + tiles.map(function (t) {
                var n = t.nivel || 'neutral';
                return '<button type="button" class="adt_f360__kpi is-' + n + '" data-tab="' + t.tab + '">' +
                    '<span class="adt_f360__kpi-head"><i class="fa ' + t.icono + '" aria-hidden="true"></i><span>' + esc(t.titulo) + '</span>' +
                    (t.estado ? estado(n, t.estado) : '') + '</span>' +
                    '<span class="adt_f360__kpi-value">' + esc(t.valor) + '</span>' +
                    '<span class="adt_f360__kpi-sub">' + esc(t.sub) + '</span>' +
                    (t.pct !== null && t.pct !== undefined ? '<span class="adt_f360__kpi-progress">' +
                        '<span class="adt_f360__kpi-bar"><span style="width:' + t.pct + '%"></span></span>' +
                        (t.pctLabel ? '<span class="adt_f360__kpi-sub">' + esc(t.pctLabel) + '</span>' : '') + '</span>' : '') +
                    (t.alerta ? '<span class="adt_f360__kpi-alert is-' + t.alerta.nivel + '"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i>' +
                        esc(t.alerta.texto) + '</span>' : '') +
                    '</button>';
            }).join('') + '</div>';
        },

        // Etapas del vehículo, de la solicitud a la cobranza.
        _htmlRecorrido: function (pasos) {
            var self = this;
            if (!pasos.length) {
                return '';
            }
            var hechos = pasos.filter(function (p) { return p.nivel === 'ok'; }).length;
            return '<section class="adt_f360__panel adt_f360__journey">' +
                '<header class="adt_f360__panel-head"><h3>Recorrido del vehículo</h3>' +
                '<span class="adt_f360__muted">' + hechos + ' de ' + pasos.length + ' etapas completas</span></header>' +
                '<ol class="adt_f360__steps" style="--f3-pasos:' + pasos.length + '">' + pasos.map(function (p, i) {
                    return '<li class="adt_f360__step is-' + p.nivel + '">' +
                        '<button type="button" class="adt_f360__step-main"' + (p.tab ? ' data-tab="' + p.tab + '"' : '') + '>' +
                            '<span class="adt_f360__step-dot" aria-hidden="true">' +
                                (p.nivel === 'ok' ? '<i class="fa fa-check"></i>' : (p.nivel === 'critico' || p.nivel === 'atencion'
                                    ? '<i class="fa fa-exclamation"></i>' : (i + 1))) + '</span>' +
                            '<span class="adt_f360__step-title">' + esc(p.titulo) + '</span>' +
                            '<span class="adt_f360__step-text">' + esc(p.texto) + '</span>' +
                            (p.detalle ? '<span class="adt_f360__step-sub">' + esc(p.detalle) + '</span>' : '') +
                            '<span class="sr-only">' + esc(PASO_LABEL[p.nivel] || '') + '</span>' +
                        '</button>' +
                        (p.accion ? '<div class="adt_f360__step-cta">' + self._accion(p.accion, ' is-small' +
                            (p.nivel === 'atencion' || p.nivel === 'critico' ? ' is-primary' : '')) + '</div>' : '') +
                        '</li>';
                }).join('') + '</ol></section>';
        },

        _htmlCliente: function (s, d) {
            var html = this._htmlSeccion(s);
            var exp = _.findWhere(d.secciones, {key: 'expediente'});
            if (exp) {
                var e = exp.expedientes && exp.expedientes[0];
                html += this._panel('Expediente', e
                    ? '<div class="adt_f360__exp-mini">' + badge(e.nivel, e.estado) + '<span>' + esc(e.titulo) + '</span>' +
                      '<span class="adt_f360__muted">' + e.avance.completos + ' de ' + e.avance.requeridos + ' documentos aceptados</span></div>'
                    : this._htmlSinExpediente(exp, true),
                    '<button type="button" class="adt_f360__btn is-small" data-tab="expediente">Ir al expediente</button>');
            }
            return '<div class="adt_f360__cols">' + html + '</div>';
        },

        _htmlVehiculo: function (s) {
            var docs = s.documentos_vehiculo || [];
            var cargados = docs.filter(function (x) { return x.estado === 'aceptado'; }).length;
            return '<div class="adt_f360__cols">' + this._htmlSeccion(_.omit(s, 'documentos_vehiculo')) +
                (docs.length ? this._panel('Documentos del vehículo',
                    '<p class="adt_f360__muted adt_f360__docs-hint">' + cargados + ' de ' + docs.length +
                    ' cargados. Arrastra un archivo sobre un documento o usa «Subir». Imágenes o PDF de hasta ' + MAX_ARCHIVO_MB + ' MB.</p>' +
                    this._htmlDocs(docs, {modelo: s.modelo, res_id: s.res_id})) : '') +
                '</div>';
        },

        // ------------------------------------------------------------------
        // Render: expediente y documentos
        // ------------------------------------------------------------------

        _htmlSinExpediente: function (s, compacto) {
            var accion = (s.acciones || [])[0];
            return '<div class="adt_f360__flag' + (compacto ? ' is-compact' : '') + '">' +
                '<i class="fa fa-folder-open-o adt_f360__flag-icon" aria-hidden="true"></i>' +
                '<div><div class="adt_f360__flag-title">Sin expediente</div>' +
                '<p>' + esc(s.vacio) + '</p></div>' +
                (accion ? '<div>' + this._accion(_.extend({}, accion, {primary: true})) + '</div>' : '') + '</div>';
        },

        _htmlExpedientes: function (s) {
            var self = this;
            var lista = s.expedientes || [];
            if (!lista.length) {
                return this._htmlSinExpediente(s);
            }
            var actual = _.findWhere(lista, {id: this.expSel}) || lista[0];
            var otros = lista.length > 1
                ? '<div class="adt_f360__exp-switch"><span class="adt_f360__label">Expedientes del cliente</span>' +
                  lista.map(function (e) {
                      return '<button type="button" class="adt_f360__chip' + (e.id === actual.id ? ' is-active' : '') + '" data-exp="' + e.id + '">' +
                          esc(e.titulo.replace('Expediente del ', '')) + (e.vigente ? ' · vigente' : '') + '</button>';
                  }).join('') + '</div>'
                : '';
            var av = actual.avance;
            var pct = av.requeridos ? Math.round(av.completos * 100 / av.requeridos) : 0;
            var cabecera = '<header class="adt_f360__acc-head">' +
                '<div><div class="adt_f360__acc-title">' + esc(actual.titulo) + ' ' + badge(actual.nivel, actual.estado) + '</div>' +
                (actual.cliente ? '<div class="adt_f360__sub">' + esc(actual.cliente) + '</div>' : '') + '</div>' +
                '<div class="adt_f360__acc-actions">' + this._acciones_html(actual.acciones) + this._menu(actual.mas, 'Estado', '') + '</div>' +
                '</header>';
            var avance = '<div class="adt_f360__acc-progress">' +
                '<div class="adt_f360__acc-progress-head"><span><b>' + av.completos + '</b> de ' + av.requeridos +
                ' documentos obligatorios aceptados <span class="adt_f360__muted">(' + pct + '%)</span></span>' +
                (av.rechazados ? '<span class="adt_f360__amount is-critico">' + plural(av.rechazados, 'documento rechazado', 'documentos rechazados') + '</span>' : '') +
                '</div><div class="adt_f360__progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct +
                '"><span style="width:' + pct + '%"></span></div></div>' +
                (actual.rechazo ? '<div class="adt_f360__note is-critico">Rechazado el ' + esc(actual.fecha_rechazo) + ': ' + esc(actual.rechazo) + '</div>' : '');
            var ctx = {modelo: 'adt.expediente', res_id: actual.id, expediente: actual.id};
            var grupos = actual.grupos.map(function (g) {
                return '<section class="adt_f360__docgroup"><h4>' + esc(g.titulo) + '</h4>' + self._htmlDocs(g.documentos, ctx) + '</section>';
            }).join('');
            var dat = actual.datos;
            var datos = this._htmlCampos(dat.campos) +
                this._htmlRevision('Dirección', dat.direccion_estado, dat.direccion_obs) +
                '<div class="adt_f360__label adt_f360__docs-title">Referencias</div>' +
                (dat.referencias.length ? '<ul class="adt_f360__refs">' + dat.referencias.map(function (r) {
                    return '<li>' + esc(r) + '</li>';
                }).join('') + '</ul>' : '<p class="adt_f360__muted">Sin referencias registradas.</p>') +
                this._htmlRevision('Referencias', dat.referencias_estado, dat.referencias_obs);
            return otros +
                '<section class="adt_f360__panel">' + cabecera + avance + '</section>' +
                '<div class="adt_f360__exp-grid"><div>' + this._panel('Documentos', grupos) + '</div>' +
                '<div>' + this._panel('Datos declarados', datos) + '</div></div>';
        },

        _htmlRevision: function (label, valor, obs) {
            if (valor !== 'rechazado') {
                return '';
            }
            return '<div class="adt_f360__note is-critico">' + esc(label) + ' rechazada' + (obs ? ': ' + esc(obs) : '') + '</div>';
        },

        // Tarjetas de documentos con vista previa y operaciones.
        // ctx: {modelo, res_id, expediente?}
        _htmlDocs: function (docs, ctx) {
            var self = this;
            return '<div class="adt_f360__doccards">' + docs.map(function (d) {
                var est = DOC_ESTADO[d.estado] || DOC_ESTADO.falta;
                var archivos = d.archivos.map(function (a) { return self._htmlArchivo(d, a, ctx); }).join('');
                var revision = '';
                if (ctx.expediente && d.revisable && d.clave) {
                    var ref = ctx.expediente + '|' + d.clave;
                    revision = '<div class="adt_f360__doc-review">' +
                        // Los documentos cargados quedan aceptados por defecto: "Aceptar" solo revierte un rechazo.
                        (d.estado === 'rechazado' ? '<button type="button" class="adt_f360__btn is-small" data-aceptar="' + ref + '"><i class="fa fa-check" aria-hidden="true"></i>Aceptar</button>' : '') +
                        (d.estado !== 'rechazado' ? '<button type="button" class="adt_f360__btn is-small is-danger" data-rechazar="' + ref + '"><i class="fa fa-times" aria-hidden="true"></i>Rechazar</button>' : '') +
                        '</div>';
                }
                return '<article class="adt_f360__doc is-' + d.estado + '">' +
                    '<header class="adt_f360__doc-head"><span class="adt_f360__doc-name">' + esc(d.label) +
                    (d.obligatorio ? '' : ' <span class="adt_f360__muted">(opcional)</span>') + '</span>' +
                    estado(est[0], est[1]) + '</header>' +
                    '<div class="adt_f360__doc-files">' + archivos + '</div>' +
                    (d.obs && d.estado === 'rechazado' ? '<div class="adt_f360__doc-obs">' + esc(d.obs) + '</div>' : '') +
                    revision + '</article>';
            }).join('') + '</div>';
        },

        _htmlArchivo: function (d, a, ctx) {
            var ref = ctx.modelo + '|' + ctx.res_id + '|' + a.campo;
            var titulo = d.label + (a.lado ? ' - ' + a.lado : '');
            var vista;
            if (!a.cargado) {
                vista = '<button type="button" class="adt_f360__thumb is-empty" data-subir="' + ref + '" title="Subir ' + esc(titulo) + '">' +
                    '<i class="fa fa-cloud-upload" aria-hidden="true"></i><span>Subir</span></button>';
            } else if (a.imagen) {
                vista = '<button type="button" class="adt_f360__thumb" data-ver="' + esc(a.url) + '|1|' + esc(titulo) + '|' + esc(a.descarga) + '" title="Ver ' + esc(titulo) + '">' +
                    '<img src="' + esc(a.miniatura) + '" alt="' + esc(titulo) + '" loading="lazy"/></button>';
            } else {
                vista = '<button type="button" class="adt_f360__thumb is-file" data-ver="' + esc(a.url) + '|0|' + esc(titulo) + '|' + esc(a.descarga) + '" title="Abrir ' + esc(titulo) + '">' +
                    '<i class="fa ' + (a.mimetype === 'application/pdf' ? 'fa-file-pdf-o' : 'fa-file-o') + '" aria-hidden="true"></i>' +
                    '<span>' + esc(a.nombre || (a.mimetype === 'application/pdf' ? 'PDF' : 'Archivo')) + '</span></button>';
            }
            return '<div class="adt_f360__file" data-subir-zona="' + ref + '">' + vista +
                '<div class="adt_f360__file-meta">' + (a.lado ? '<span>' + esc(a.lado) + '</span>' : '') +
                (a.cargado ? '<span class="adt_f360__muted">' + fechaHora(a.fecha) + '</span>' : '') + '</div>' +
                (a.cargado ? '<div class="adt_f360__file-actions">' +
                    '<button type="button" class="adt_f360__icon-btn is-small" data-subir="' + ref + '" title="Reemplazar"><i class="fa fa-refresh" aria-hidden="true"></i></button>' +
                    '<a class="adt_f360__icon-btn is-small" href="' + esc(a.descarga) + '" title="Descargar"><i class="fa fa-download" aria-hidden="true"></i></a>' +
                    '<button type="button" class="adt_f360__icon-btn is-small is-danger" data-quitar="' + ref + '" title="Quitar"><i class="fa fa-trash-o" aria-hidden="true"></i></button>' +
                    '</div>' : '') +
                '</div>';
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
            if (a.tipo === 'form') {
                this._abrirForm(a.form, a.res_id, a.params);
                return;
            }
            if (a.tipo === 'credito') {
                this._abrirCredito(a.cuenta_id);
                return;
            }
            if (a.tipo === 'tab') {
                this._irA(a.tab);
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

        _irA: function (tab) {
            this.tab = tab;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__db').scrollTop(0);
        },

        _error: function (err) {
            var data = err && err.message && err.message.data;
            return (data && (data.message || data.arguments && data.arguments[0])) ||
                (err && err.message && err.message.message) || 'No se pudo completar la operación.';
        },

        // Llamada al servidor que muestra el error en el modal (en lugar del diálogo de Odoo).
        _llamar: function (method, kwargs) {
            return this._rpc({model: 'adt.flota360', method: method, kwargs: kwargs}, {shadow: true});
        },

        // ------------------------------------------------------------------
        // Modal propio de la vista
        // ------------------------------------------------------------------

        _mostrarModal: function (modal, html) {
            this._modal = modal;
            this._ref('modal').html(
                '<div class="adt_f360__modal-backdrop" data-modal-close></div>' +
                '<div class="adt_f360__modal' + (modal.ancho ? ' is-wide' : '') + '" role="dialog" aria-modal="true" aria-labelledby="adt_f360_modal_t">' +
                html + '</div>').addClass('is-open');
            var $primero = this._ref('modal').find('input:not([type=hidden]):not([type=file]), select, textarea').first();
            ($primero.length ? $primero : this._ref('modal').find('[data-modal-close]').last()).trigger('focus');
        },

        _cerrarModal: function () {
            if (!this._modal) {
                return;
            }
            this._modal = null;
            this._ref('modal').removeClass('is-open').empty();
        },

        _modalCabecera: function (titulo, ayuda) {
            return '<header class="adt_f360__modal-head"><div><h2 id="adt_f360_modal_t">' + esc(titulo) + '</h2>' +
                (ayuda ? '<p>' + esc(ayuda) + '</p>' : '') + '</div>' +
                '<button type="button" class="adt_f360__icon-btn" data-modal-close title="Cerrar (Esc)"><i class="fa fa-times" aria-hidden="true"></i></button></header>';
        },

        _modalPie: function (botones) {
            return '<footer class="adt_f360__modal-foot"><div class="adt_f360__modal-error" data-ref="modal-error" role="alert"></div>' +
                '<button type="button" class="adt_f360__btn" data-modal-close>Cancelar</button>' + botones + '</footer>';
        },

        _modalError: function (texto) {
            this._ref('modal').find('[data-ref="modal-error"]').text(texto || '');
            this._ref('modal').find('[data-guardar]').prop('disabled', false);
        },

        // ------------------------------------------------------------------
        // Formularios genéricos (descritos por el servidor)
        // ------------------------------------------------------------------

        _abrirForm: function (clave, resId, params) {
            var self = this;
            return this._llamar('formulario', {
                clave: clave, vehicle_id: this._drawerId, res_id: resId || false, params: params || {},
            }).then(function (spec) {
                var valores = _.clone(spec.valores);
                self._mostrarModal({tipo: 'form', spec: spec, valores: valores, params: params || {}, archivos: {}},
                    self._modalCabecera(spec.titulo, spec.ayuda) +
                    '<form class="adt_f360__modal-body" novalidate="novalidate">' +
                    spec.secciones.map(function (sec) {
                        return '<section class="adt_f360__fieldset">' + (sec.titulo ? '<h3 class="adt_f360__legend">' + esc(sec.titulo) + '</h3>' : '') +
                            '<div class="adt_f360__form-grid">' + sec.campos.map(function (c) {
                                return self._htmlInput(c, valores[c.name]);
                            }).join('') + '</div></section>';
                    }).join('') + '<button type="submit" class="d-none"></button></form>' +
                    self._modalPie('<button type="button" class="adt_f360__btn is-primary" data-guardar>Guardar</button>'));
                self._aplicarVisibilidad();
            }).guardedCatch(function (err) {
                self.displayNotification({type: 'danger', title: 'No disponible', message: self._error(err)});
                if (err && err.event) { err.event.preventDefault(); }
            });
        },

        _htmlInput: function (c, valor) {
            var id = 'f360_' + c.name;
            var req = c.required ? ' required="required"' : '';
            var attrs = ' id="' + id + '" name="' + c.name + '" data-campo="' + c.name + '"' + req;
            var control;
            switch (c.type) {
                case 'text':
                    control = '<textarea class="adt_f360__input" rows="3"' + attrs + '>' + esc(valor || '') + '</textarea>';
                    break;
                case 'date':
                    control = '<input type="date" class="adt_f360__input"' + attrs + ' value="' + esc(valor || '') + '"/>';
                    break;
                case 'datetime':
                    control = '<input type="datetime-local" class="adt_f360__input"' + attrs + ' value="' + esc(utcALocal(valor)) + '"/>';
                    break;
                case 'float': case 'monetary': case 'integer':
                    control = '<input type="number" class="adt_f360__input is-num"' + attrs + ' step="' + (c.type === 'integer' ? '1' : '0.01') +
                        '" value="' + esc(valor === false || valor === undefined ? '' : valor) + '"/>';
                    break;
                case 'selection':
                    control = '<select class="adt_f360__input"' + attrs + '>' + (c.required ? '' : '<option value="">—</option>') +
                        (c.options || []).map(function (o) {
                            return '<option value="' + esc(o[0]) + '"' + (String(o[0]) === String(valor) ? ' selected="selected"' : '') + '>' + esc(o[1]) + '</option>';
                        }).join('') + '</select>';
                    break;
                case 'boolean':
                    return '<label class="adt_f360__check' + (c.col === 2 ? ' is-full' : '') + '" data-campo-wrap="' + c.name + '">' +
                        '<input type="checkbox"' + attrs + (valor ? ' checked="checked"' : '') + '/><span>' + esc(c.label) + '</span></label>';
                case 'many2one':
                    control = '<div class="adt_f360__m2o" data-m2o="' + c.name + '" data-model="' + esc(c.model) + '">' +
                        '<input type="text" class="adt_f360__input" autocomplete="off"' + attrs + ' value="' + esc(valor ? valor[1] : '') + '" placeholder="Buscar…"/>' +
                        '<ul class="adt_f360__m2o-list" role="listbox"></ul></div>';
                    break;
                case 'file':
                    control = '<input type="file" class="adt_f360__input" accept="image/*,application/pdf"' + attrs + '/>' +
                        (valor ? '<span class="adt_f360__help">Ya hay un archivo cargado; elige otro para reemplazarlo.</span>' : '');
                    break;
                case 'adjuntos':
                    control = '<input type="file" multiple="multiple" class="adt_f360__input" accept="image/*,application/pdf,video/*"' + attrs + '/>' +
                        '<span class="adt_f360__help">Puedes seleccionar varios archivos (máx. ' + MAX_ARCHIVO_MB + ' MB c/u).</span>';
                    break;
                default:
                    control = '<input type="text" class="adt_f360__input"' + attrs + ' value="' + esc(valor || '') + '"/>';
            }
            return '<div class="adt_f360__field' + (c.col === 2 ? ' is-full' : '') + '" data-campo-wrap="' + c.name + '">' +
                '<label for="' + id + '">' + esc(c.label) + (c.required ? ' <span class="adt_f360__req" aria-hidden="true">*</span>' : '') + '</label>' +
                control + (c.help && c.type !== 'file' && c.type !== 'adjuntos' ? '<span class="adt_f360__help">' + esc(c.help) + '</span>' : '') + '</div>';
        },

        // Campos condicionados: visible = [campo] (si tiene valor) o [campo, valor].
        _aplicarVisibilidad: function () {
            var m = this._modal;
            if (!m || m.tipo !== 'form') {
                return;
            }
            var $modal = this._ref('modal');
            m.spec.secciones.forEach(function (sec) {
                sec.campos.forEach(function (c) {
                    if (!c.visible) {
                        return;
                    }
                    var v = m.valores[c.visible[0]];
                    var ok = c.visible.length > 1 ? String(v) === String(c.visible[1]) : !!v;
                    $modal.find('[data-campo-wrap="' + c.name + '"]').toggleClass('d-none', !ok);
                });
            });
        },

        _specCampo: function (nombre) {
            var m = this._modal;
            var encontrado = null;
            (m && m.spec ? m.spec.secciones : []).forEach(function (sec) {
                sec.campos.forEach(function (c) { if (c.name === nombre) { encontrado = c; } });
            });
            return encontrado;
        },

        _onCampo: function (ev) {
            var m = this._modal;
            if (!m) {
                return;
            }
            var el = ev.currentTarget;
            var nombre = el.getAttribute('data-campo');
            if (m.tipo === 'credito') {
                return this._onCampoCredito(el, nombre, ev.type);
            }
            var c = this._specCampo(nombre);
            if (!c) {
                return;
            }
            if (c.type === 'many2one') {
                if (ev.type === 'input') {
                    m.valores[nombre] = false;
                    this._buscarOpcionesDiferido(el, c.model);
                }
                return;
            }
            if (c.type === 'file' || c.type === 'adjuntos') {
                m.archivos[nombre] = el.files ? _.toArray(el.files) : [];
                return;
            }
            m.valores[nombre] = c.type === 'boolean' ? el.checked : el.value;
            this._aplicarVisibilidad();
        },

        // --- Selector de registros (many2one) ------------------------------

        _buscarOpciones: function (input, modelo) {
            var $wrap = $(input).closest('[data-m2o]');
            this._llamar('opciones', {modelo: modelo, termino: input.value}).then(function (res) {
                $wrap.find('.adt_f360__m2o-list').html(res.length ? res.map(function (r) {
                    return '<li role="option" data-m2o-opcion="' + r[0] + '">' + esc(r[1]) + '</li>';
                }).join('') : '<li class="is-empty">Sin coincidencias</li>').addClass('is-open');
            });
        },

        _onM2oOpcion: function (ev) {
            var $li = $(ev.currentTarget);
            var $wrap = $li.closest('[data-m2o]');
            var nombre = $wrap.attr('data-m2o');
            var valor = [parseInt($li.attr('data-m2o-opcion'), 10), $li.text()];
            $wrap.find('input').val(valor[1]);
            $wrap.find('.adt_f360__m2o-list').removeClass('is-open').empty();
            if (this._modal) {
                this._modal.valores[nombre] = valor;
                if (this._modal.tipo === 'credito') {
                    this._simularDiferido();
                }
            }
        },

        _onM2oBlur: function (ev) {
            var $wrap = $(ev.currentTarget);
            // Espera al click en la opción antes de cerrar la lista.
            setTimeout(function () { $wrap.find('.adt_f360__m2o-list').removeClass('is-open'); }, 180);
        },

        // --- Envío ---------------------------------------------------------

        _onSubmitModal: function (ev) {
            ev.preventDefault();
            var m = this._modal;
            if (!m) {
                return;
            }
            if (m.tipo === 'credito') {
                var boton = ev.currentTarget.getAttribute('data-guardar');
                // Enter dentro del asistente no guarda: se elige explícitamente borrador o aprobar.
                return boton ? this._guardarCredito(boton === 'aprobar') : undefined;
            }
            if (m.tipo !== 'form') {
                return;
            }
            var self = this;
            var faltan = [];
            m.spec.secciones.forEach(function (sec) {
                sec.campos.forEach(function (c) {
                    var oculto = self._ref('modal').find('[data-campo-wrap="' + c.name + '"]').hasClass('d-none');
                    var v = m.valores[c.name];
                    if (c.required && !oculto && c.type !== 'file' && c.type !== 'adjuntos' && (v === false || v === '' || v === undefined || v === null)) {
                        faltan.push(c.label);
                    }
                });
            });
            if (faltan.length) {
                return this._modalError('Completa: ' + faltan.join(', ') + '.');
            }
            this._ref('modal').find('[data-guardar]').prop('disabled', true);
            this._modalError('');
            var valores = {};
            _.each(m.valores, function (v, k) {
                var c = self._specCampo(k);
                if (!c || c.type === 'file' || c.type === 'adjuntos') {
                    return;
                }
                valores[k] = c.type === 'datetime' ? localAUtc(v) : (c.type === 'many2one' ? (v ? v[0] : false) : v);
            });
            var lecturas = _.map(m.archivos, function (files, nombre) {
                var c = self._specCampo(nombre);
                return Promise.all(files.map(leerArchivo)).then(function (leidos) {
                    valores[nombre] = c.type === 'file' ? (leidos[0] || undefined) : leidos;
                });
            });
            Promise.all(lecturas).then(function () {
                return self._llamar('guardar', {
                    clave: m.spec.clave, vehicle_id: self._drawerId, valores: valores,
                    res_id: m.spec.res_id || false, params: m.params,
                });
            }).then(function () {
                self._cerrarModal();
                self.displayNotification({type: 'success', message: m.spec.titulo + ': guardado.'});
                if (m.spec.clave === 'expediente') {
                    self.tab = 'expediente';
                }
                self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                self._modalError(err instanceof Error ? err.message : self._error(err));
            });
        },

        // ------------------------------------------------------------------
        // Documentos
        // ------------------------------------------------------------------

        _ref3: function (valor) {
            var p = (valor || '').split('|');
            return {modelo: p[0], res_id: parseInt(p[1], 10), campo: p[2]};
        },

        _onSubir: function (ev) {
            ev.stopPropagation();
            this._subirA = this._ref3(ev.currentTarget.getAttribute('data-subir'));
            this._ref('archivo').val('').trigger('click');
        },

        _onArchivo: function (ev) {
            var archivo = ev.currentTarget.files && ev.currentTarget.files[0];
            if (archivo && this._subirA) {
                this._subirArchivo(this._subirA, archivo);
            }
        },

        _onDragOver: function (ev) {
            ev.preventDefault();
            $(ev.currentTarget).addClass('is-drop');
        },

        _onDragLeave: function (ev) {
            $(ev.currentTarget).removeClass('is-drop');
        },

        _onDrop: function (ev) {
            ev.preventDefault();
            var $zona = $(ev.currentTarget).removeClass('is-drop');
            var dt = ev.originalEvent && ev.originalEvent.dataTransfer;
            var archivo = dt && dt.files && dt.files[0];
            if (archivo) {
                this._subirArchivo(this._ref3($zona.attr('data-subir-zona')), archivo);
            }
        },

        _subirArchivo: function (destino, archivo) {
            var self = this;
            var $zona = this.$('[data-subir-zona="' + destino.modelo + '|' + destino.res_id + '|' + destino.campo + '"]').addClass('is-loading');
            return leerArchivo(archivo).then(function (leido) {
                return self._llamar('subir_documento', {
                    modelo: destino.modelo, res_id: destino.res_id, campo: destino.campo, nombre: leido.nombre, datos: leido.datos,
                });
            }).then(function () {
                self.displayNotification({type: 'success', message: 'Documento cargado.'});
                self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                $zona.removeClass('is-loading');
                self.displayNotification({type: 'danger', title: 'No se pudo cargar', message: err instanceof Error ? err.message : self._error(err)});
            });
        },

        _onQuitar: function (ev) {
            var self = this;
            var destino = this._ref3(ev.currentTarget.getAttribute('data-quitar'));
            Dialog.confirm(this, '¿Quitar este archivo? Tendrás que volver a cargarlo.', {
                title: 'Quitar documento',
                confirm_callback: function () {
                    return self._llamar('quitar_documento', destino).then(function () { self._recargar(); });
                },
            });
        },

        _onAceptar: function (ev) {
            var self = this;
            var p = ev.currentTarget.getAttribute('data-aceptar').split('|');
            this._llamar('revisar_documento', {expediente_id: parseInt(p[0], 10), clave: p[1], estado: 'aceptado'}).then(function () {
                self._recargar();
            });
        },

        _onRechazar: function (ev) {
            var p = ev.currentTarget.getAttribute('data-rechazar').split('|');
            this._abrirForm('rechazo_documento', parseInt(p[0], 10), {clave: p[1]});
        },

        _onVer: function (ev) {
            var p = ev.currentTarget.getAttribute('data-ver').split('|');
            if (p[1] !== '1') {
                window.open(p[0], '_blank', 'noopener');
                return;
            }
            this._mostrarModal({tipo: 'visor', ancho: true},
                this._modalCabecera(p[2]) +
                '<div class="adt_f360__viewer"><img src="' + esc(p[0]) + '" alt="' + esc(p[2]) + '"/></div>' +
                '<footer class="adt_f360__modal-foot"><div class="adt_f360__modal-error"></div>' +
                '<a class="adt_f360__btn" href="' + esc(p[0]) + '" target="_blank" rel="noopener"><i class="fa fa-external-link" aria-hidden="true"></i>Abrir en otra pestaña</a>' +
                '<a class="adt_f360__btn" href="' + esc(p[3]) + '"><i class="fa fa-download" aria-hidden="true"></i>Descargar</a>' +
                '<button type="button" class="adt_f360__btn is-primary" data-modal-close>Cerrar</button></footer>');
        },

        _onExpediente: function (ev) {
            this.expSel = parseInt(ev.currentTarget.getAttribute('data-exp'), 10);
            this._renderDrawer();
        },

        // ------------------------------------------------------------------
        // Crédito: nueva cuenta con cronograma
        // ------------------------------------------------------------------

        _abrirCredito: function (cuentaId) {
            var self = this;
            return this._llamar('cuenta_inicial', {vehicle_id: this._drawerId, cuenta_id: cuentaId || false}).then(function (ini) {
                var v = ini.valores;
                self._mostrarModal({tipo: 'credito', ancho: true, ini: ini, valores: v, cuenta_id: ini.cuenta_id,
                    fraccionadoManual: !!(cuentaId && v.monto_fraccionado !== (v.monto_total || 0) - (v.monto_inicial || 0)),
                    sim: ini.simulacion},
                    self._modalCabecera(cuentaId ? 'Cronograma de la cuenta en borrador' : 'Nueva cuenta y cronograma',
                        'Vehículo ' + ini.vehiculo + '. El cronograma se genera al aprobar la cuenta; la vista previa muestra exactamente las cuotas que se crearán.') +
                    '<form class="adt_f360__modal-body adt_f360__credit" novalidate="novalidate">' +
                        '<div class="adt_f360__credit-form">' + self._htmlCreditoForm(ini) + '</div>' +
                        '<div class="adt_f360__credit-preview" data-ref="credito-preview"></div>' +
                    '<button type="submit" class="d-none"></button></form>' +
                    self._modalPie(
                        '<button type="button" class="adt_f360__btn" data-guardar="borrador">' + (cuentaId ? 'Guardar cambios' : 'Guardar como borrador') + '</button>' +
                        '<button type="button" class="adt_f360__btn is-primary" data-guardar="aprobar"><i class="fa fa-check" aria-hidden="true"></i>' +
                        (cuentaId ? 'Guardar y aprobar' : 'Crear y aprobar') + '</button>'));
                self._renderSimulacion();
            }).guardedCatch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                self.displayNotification({type: 'warning', title: 'Crédito', message: self._error(err)});
            });
        },

        _htmlCreditoForm: function (ini) {
            var v = ini.valores;
            var self = this;
            var campo = function (c) { return self._htmlInput(c, v[c.name]); };
            var seccion = function (titulo, campos, antes) {
                return '<section class="adt_f360__fieldset"><h3 class="adt_f360__legend">' + titulo + '</h3><div class="adt_f360__form-grid">' +
                    (antes || '') + campos.map(campo).join('') + '</div></section>';
            };
            var modo = '<div class="adt_f360__field is-full"><label>Cálculo de la cuota</label><div class="adt_f360__seg is-block">' +
                [['cuotas', 'Dividir en N cuotas iguales'], ['monto', 'Fijar el monto de la cuota']].map(function (x) {
                    return '<button type="button" class="' + (v.modo === x[0] ? 'is-active' : '') + '" data-modo="' + x[0] + '">' + x[1] + '</button>';
                }).join('') + '</div></div>';
            return (ini.disponible ? '' : '<div class="adt_f360__note">El vehículo figura como no disponible; revisa que no tenga otro crédito activo.</div>') +
                seccion('Cliente y condiciones', [
                    {name: 'partner_id', label: 'Cliente', type: 'many2one', model: 'res.partner', required: true},
                    {name: 'user_id', label: 'Vendedor', type: 'many2one', model: 'res.users', required: true},
                    {name: 'tipo_financiera_id', label: 'Financiera', type: 'selection', options: ini.financieras},
                    {name: 'periodicidad', label: 'Periodicidad', type: 'selection', options: ini.periodicidades, required: true},
                    {name: 'fecha_desembolso', label: 'Fecha de desembolso', type: 'date'},
                    {name: 'fecha_entrega', label: 'Fecha de entrega', type: 'date'},
                ]) +
                seccion('Montos', [
                    {name: 'monto_total', label: 'Valor del vehículo', type: 'monetary'},
                    {name: 'monto_inicial', label: 'Inicial', type: 'monetary'},
                    {name: 'monto_fraccionado', label: 'Monto a financiar', type: 'monetary', required: true,
                        help: 'Se calcula como valor − inicial; puedes ajustarlo.'},
                    {name: 'cuota_gracia', label: 'Cuota 0 (opcional)', type: 'monetary', help: 'Se cobra en la fecha de inicio.'},
                ]) +
                seccion('Cuotas', [
                    {name: 'fecha_gracia', label: 'Fecha de inicio', type: 'date', required: true,
                        help: 'La cuota 1 vence un periodo después de esta fecha.'},
                    {name: 'qty_cuotas', label: 'Número de cuotas', type: 'integer', required: true},
                    {name: 'monto_cuota', label: 'Monto de la cuota', type: 'monetary', required: true},
                    {name: 'is_available_pay_mora', label: 'Cobra mora por atraso', type: 'boolean'},
                ], modo);
        },

        _onModoCredito: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'credito') {
                return;
            }
            m.valores.modo = ev.currentTarget.getAttribute('data-modo');
            $(ev.currentTarget).addClass('is-active').siblings().removeClass('is-active');
            this._toggleMontoCuota();
            this._simularDiferido();
        },

        _toggleMontoCuota: function () {
            var m = this._modal;
            this._ref('modal').find('[data-campo-wrap="monto_cuota"]').toggleClass('d-none', m.valores.modo !== 'monto');
        },

        _onCampoCredito: function (el, nombre, tipo) {
            var m = this._modal;
            var numericos = ['monto_total', 'monto_inicial', 'monto_fraccionado', 'cuota_gracia', 'monto_cuota', 'qty_cuotas'];
            if (nombre === 'partner_id' || nombre === 'user_id') {
                if (tipo === 'input') {
                    m.valores[nombre] = false;
                    this._buscarOpcionesDiferido(el, nombre === 'partner_id' ? 'res.partner' : 'res.users');
                }
                return;
            }
            var valor = el.type === 'checkbox' ? el.checked : el.value;
            m.valores[nombre] = numericos.indexOf(nombre) >= 0 ? (parseFloat(valor) || 0) : valor;
            if (nombre === 'monto_fraccionado') {
                m.fraccionadoManual = true;
            }
            if ((nombre === 'monto_total' || nombre === 'monto_inicial') && !m.fraccionadoManual) {
                m.valores.monto_fraccionado = Math.max((m.valores.monto_total || 0) - (m.valores.monto_inicial || 0), 0);
                this._ref('modal').find('[data-campo="monto_fraccionado"]').val(m.valores.monto_fraccionado.toFixed(2));
            }
            this._simularDiferido();
        },

        _simularCredito: function () {
            var self = this;
            var m = this._modal;
            if (!m || m.tipo !== 'credito') {
                return;
            }
            var seq = m.seq = (m.seq || 0) + 1;
            this._llamar('simular_cronograma', {params: this._paramsCredito()}).then(function (sim) {
                if (self._modal === m && m.seq === seq) {
                    m.sim = sim;
                    self._renderSimulacion();
                }
            });
        },

        _paramsCredito: function () {
            var v = _.clone(this._modal.valores);
            v.partner_id = v.partner_id ? v.partner_id[0] : false;
            v.user_id = v.user_id ? v.user_id[0] : false;
            return v;
        },

        _renderSimulacion: function () {
            var m = this._modal;
            this._toggleMontoCuota();
            var sim = m.sim || {cuotas: [], errores: []};
            var $p = this._ref('modal').find('[data-ref="credito-preview"]');
            var resumen = sim.cuotas.length
                ? '<div class="adt_f360__credit-figures">' + [
                    ['Cuota', soles(sim.cuota)],
                    ['N° de cuotas', entero(m.valores.qty_cuotas)],
                    ['Total a cobrar', soles(sim.total)],
                    ['Última cuota', fecha(sim.ultima)],
                ].map(function (x) {
                    return '<div><span>' + x[0] + '</span><b>' + esc(x[1]) + '</b></div>';
                }).join('') + '</div>'
                : '';
            var mensajes = (sim.errores || []).map(function (e) { return '<div class="adt_f360__note is-critico">' + esc(e) + '</div>'; }).join('') +
                (sim.avisos || []).map(function (e) { return '<div class="adt_f360__note">' + esc(e) + '</div>'; }).join('');
            var tabla = sim.cuotas.length
                ? '<div class="adt_f360__credit-table"><table class="adt_f360__dtable"><thead><tr><th>Cuota</th><th>Vence</th><th class="is-num">Monto</th></tr></thead><tbody>' +
                  sim.cuotas.map(function (q) {
                      return '<tr><td>' + esc(q.nombre) + '</td><td>' + fecha(q.fecha) + '</td><td class="is-num">' + soles(q.monto) + '</td></tr>';
                  }).join('') + '</tbody></table></div>'
                : '<p class="adt_f360__muted adt_f360__pad">Completa los montos para ver el cronograma.</p>';
            $p.html('<div class="adt_f360__label">Vista previa del cronograma</div>' + resumen + mensajes + tabla);
        },

        _guardarCredito: function (aprobar) {
            var self = this;
            var m = this._modal;
            if (!m.valores.partner_id) {
                return this._modalError('Elige el cliente de la cuenta.');
            }
            if (m.sim && m.sim.errores && m.sim.errores.length) {
                return this._modalError(m.sim.errores[0]);
            }
            var correr = function () {
                self._ref('modal').find('[data-guardar]').prop('disabled', true);
                self._modalError('');
                return self._llamar('guardar_cuenta', {
                    vehicle_id: self._drawerId, params: self._paramsCredito(), aprobar: aprobar, cuenta_id: m.cuenta_id || false,
                }).then(function (res) {
                    self._cerrarModal();
                    self.displayNotification({type: 'success', message: aprobar
                        ? 'Cuenta ' + (res.referencia || '') + ' aprobada con su cronograma.'
                        : 'Cuenta guardada como borrador.'});
                    self.tab = 'cuentas';
                    self._recargar();
                }).guardedCatch(function (err) {
                    if (err && err.event) { err.event.preventDefault(); }
                    self._modalError(self._error(err));
                });
            };
            if (aprobar) {
                Dialog.confirm(this, '¿Aprobar la cuenta? Se generarán ' + (m.sim ? m.sim.cuotas.length : '') +
                    ' cuotas y el vehículo quedará asignado al cliente.', {title: 'Aprobar cuenta', confirm_callback: correr});
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
                if (this._modal) {
                    this._cerrarModal();
                } else if (this.$('.adt_f360__menu-wrap.is-open').length) {
                    this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
                } else {
                    this._closeDrawer();
                }
            } else if (this._modal) {
                return;
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
