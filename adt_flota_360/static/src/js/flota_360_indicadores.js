odoo.define('adt_flota_360.Indicadores', function (require) {
    'use strict';

    /**
     * Indicadores SAT Lima (gerencia): estados de las papeletas, antigüedad, deuda y las
     * más urgentes, filtrables (popup «Filtros») por vehículos con cliente / en stock,
     * financiera, cronograma y situación del cliente.
     * Cada recuadro y barra abre la lista de esas papeletas SAT; las urgentes y los
     * vehículos abren su ficha de Flota 360 en la pestaña Papeleta SAT.
     * Usa los filtros de "Cartera y financieras" (.adt_cart, de adt_comercial).
     *
     * Pestaña «Captura SAT»: órdenes de captura del SAT (adt_captura_sat) cruzadas con la
     * flota (vehículo, cliente, razón social, financiera, captura interna) y con las
     * papeletas (SAT o internas) del documento de cada orden. Se carga al abrirla.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var FiltrosPopup = require('adt_comercial.FiltrosPopup');

    var esc = _.escape;
    var NIVEL_ICONO = {critico: 'fa-exclamation-circle', atencion: 'fa-clock-o', ok: 'fa-check-circle',
                       info: 'fa-info-circle', neutral: 'fa-minus-circle'};

    function soles(n) {
        return 'S/ ' + (n || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
    }

    function fecha(f) {
        return f ? moment(f).format('DD/MM/YYYY') : '—';
    }

    function nivelPunto(nivel) {
        return '<i class="fa ' + (NIVEL_ICONO[nivel] || NIVEL_ICONO.neutral) + ' adt_sat__ico is-' + (nivel || 'neutral') +
            '" aria-hidden="true"></i>';
    }

    var MODELOS = {
        'adt.papeleta.sat': {nombre: 'Papeletas SAT', uno: 'papeleta', varios: 'papeletas'},
        'adt.captura.sat': {nombre: 'Órdenes de captura SAT', uno: 'orden', varios: 'órdenes'},
        'fleet.vehicle': {nombre: 'Vehículos', uno: 'vehículo', varios: 'vehículos'},
    };
    var COINCIDE = {exacta: 'Mismo número y placa', vehiculo: 'Mismo número y vehículo', documento: 'Solo coincide el número'};

    var Indicadores = AbstractAction.extend(FiltrosPopup.mixin, {
        template: 'adt_flota_360.Indicadores',
        hasControlPanel: false,

        events: _.extend({}, FiltrosPopup.events, {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-tab]': '_onTab',
            'click [data-orden]': '_onOrden',
            'click [data-papeleta]': '_onPapeleta',
            'click [data-lista]': '_onLista',
            'click [data-vehiculo]': '_onVehiculo',
            'keydown tr[data-vehiculo]': '_onVehiculoTecla',
        }),

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var params = (action && action.params) || {};
            this.tab = params.tab === 'capturas' ? 'capturas' : 'papeletas';
            this.cap = null;  // datos de la pestaña Captura SAT (se piden al abrirla)
            this.financiera = null;
            this.estado = null;
            this.clientes = null;
            this.grupo = null;  // 'clientes' (con dueño), 'stock' (sin dueño) o null = todos
            this.data = null;
            this._listas = {};
            this._seq = 0;
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () { self._render(); });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _filtros: function () {
            return {financiera: this.financiera, estado: this.estado, clientes: this.clientes, grupo: this.grupo};
        },

        // Papeletas siempre (de ahí salen los conteos del popup de filtros); capturas solo si
        // la pestaña está abierta o ya se cargó, para no consultarlas sin necesidad.
        _load: function () {
            var self = this;
            var seq = ++this._seq;
            var pedidos = [this._rpc({model: 'adt.flota360', method: 'indicadores', args: [], kwargs: this._filtros()})];
            if (this.tab === 'capturas' || this.cap) {
                pedidos.push(this._rpc({model: 'adt.flota360', method: 'capturas_sat', args: [], kwargs: this._filtros()}));
            }
            return Promise.all(pedidos).then(function (res) {
                if (seq === self._seq) {
                    self.data = res[0];
                    if (res.length > 1) {
                        self.cap = res[1];
                    }
                }
            });
        },

        _recargar: function () {
            var self = this;
            this.$el.addClass('is-loading');
            return this._load().then(function () {
                self.$el.removeClass('is-loading');
                self._render();
            });
        },

        // Guarda los ids de una lista y devuelve su clave para data-lista.
        _lista: function (titulo, ids, modelo) {
            var clave = 'l' + _.size(this._listas);
            this._listas[clave] = {titulo: titulo, ids: ids, modelo: modelo || 'adt.papeleta.sat'};
            return clave;
        },

        _render: function () {
            var d = this.data;
            var self = this;
            this._listas = {};
            this.$('[data-tab]').each(function () {
                var activa = this.getAttribute('data-tab') === self.tab;
                this.classList.toggle('is-active', activa);
                this.setAttribute('aria-selected', activa ? 'true' : 'false');
            });
            this._ref('tab-capturas-n').text(this.cap && this.cap.disponible && this.cap.total ? entero(this.cap.total) : '');
            if (this.tab === 'capturas') {
                this._fpopRender();
                this._renderCapturas();
                return;
            }
            if (!d.disponible) {
                this._ref('subtitle').text('');
                this._ref('fpop').empty();
                this._ref('aplicados').empty();
                this._ref('body').html('<div class="adt_cart__empty">El módulo de papeletas SAT (adt_papeletas) no está instalado ' +
                    'o no tienes acceso.</div>');
                return;
            }
            this._ref('subtitle').text('Al ' + fecha(d.fecha) + ' · ' + plural(d.total, 'papeleta', 'papeletas') + ' en el SAT · ' +
                plural(d.pendientes, 'pendiente de pago', 'pendientes de pago'));
            this._fpopRender();
            this._ref('body').html(
                this._htmlRecuadros(d.recuadros) +
                '<section class="adt_sat__cols">' +
                    this._htmlBarras('Estados en el SAT', 'fa-university', d.estados_sat, 'Sin papeletas registradas.') +
                    this._htmlBarras('Antigüedad de las pendientes', 'fa-hourglass-half', d.antiguedad, 'Sin papeletas pendientes.') +
                '</section>' +
                this._htmlUrgentes(d.urgentes) +
                '<section class="adt_sat__cols">' +
                    this._htmlVehiculos(d.vehiculos) +
                    this._htmlFechas(d.fechas) +
                '</section>' +
                this._htmlBarras('Faltas más frecuentes (pendientes)', 'fa-gavel', d.faltas, 'Sin papeletas pendientes.'));
        },

        _htmlRecuadros: function (recuadros) {
            var self = this;
            return '<section class="adt_find__grid adt_sat__grid">' + recuadros.map(function (t) {
                var vacio = !t.ids.length;
                var m = MODELOS[t.modelo || 'adt.papeleta.sat'];
                return '<button type="button" class="adt_find__box is-' + t.nivel + (vacio ? ' is-empty' : '') + '"' +
                    (vacio ? ' disabled="disabled"' : ' data-lista="' + self._lista(t.label, t.ids, t.modelo) + '"') +
                    ' title="' + (vacio ? 'Sin ' + m.varios : 'Ver ' + m.varios) + '">' +
                    '<span class="adt_find__box-head"><i class="fa ' + t.icon + '" aria-hidden="true"></i>' + esc(t.label) +
                        (vacio ? '' : '<i class="fa fa-angle-right adt_find__box-go" aria-hidden="true"></i>') + '</span>' +
                    '<span class="adt_find__box-value">' + esc(t.valor) + '</span>' +
                    '<span class="adt_find__box-sub">' + esc(t.sub) + '</span></button>';
            }).join('') + '</section>';
        },

        _panel: function (titulo, icono, cuerpo, extra) {
            return '<section class="adt_sat__panel"><header class="adt_sat__panel-head"><h3><i class="fa ' + icono +
                '" aria-hidden="true"></i>' + esc(titulo) + '</h3>' + (extra || '') + '</header>' +
                '<div class="adt_sat__panel-body">' + cuerpo + '</div></section>';
        },

        // Barras horizontales: una sola medida (cantidad), el monto va en texto al lado.
        _htmlBarras: function (titulo, icono, filas, vacio, modelo) {
            var self = this;
            var m = MODELOS[modelo || 'adt.papeleta.sat'];
            var max = _.max(_.pluck(filas, 'n').concat([1]));
            var cuerpo = filas.length && _.some(filas, function (f) { return f.n; })
                ? '<ul class="adt_sat__bars">' + filas.map(function (f) {
                    var nivel = f.nivel || 'info';
                    var ancho = f.n ? Math.max(f.n * 100 / max, 2) : 0;
                    var detalle = plural(f.n, m.uno, m.varios) + ' · ' + soles(f.monto);
                    return '<li><button type="button" class="adt_sat__bar' + (f.n ? '' : ' is-zero') + '"' +
                        (f.n ? ' data-lista="' + self._lista(titulo + ': ' + f.label, f.ids, modelo) + '"' : ' disabled="disabled"') +
                        ' title="' + esc(f.label + ': ' + detalle) + '">' +
                        '<span class="adt_sat__bar-label">' + (f.nivel ? nivelPunto(nivel) : '') + esc(f.label) + '</span>' +
                        '<span class="adt_sat__bar-track"><span class="adt_sat__bar-fill is-' + nivel + '" style="width:' + ancho + '%"></span></span>' +
                        '<span class="adt_sat__bar-n">' + entero(f.n) + '</span>' +
                        '<span class="adt_sat__bar-monto">' + soles(f.monto) + '</span>' +
                    '</button></li>';
                }).join('') + '</ul>'
                : '<p class="adt_sat__vacio">' + esc(vacio) + '</p>';
            return this._panel(titulo, icono, cuerpo);
        },

        _htmlUrgentes: function (urgentes) {
            var cuerpo = urgentes.length
                ? '<div class="adt_sat__table-wrap"><table class="adt_sat__table"><thead><tr>' +
                    '<th>Prioridad</th><th>Papeleta</th><th>Placa / cliente</th><th>Estado SAT</th>' +
                    '<th>Infracción</th><th class="is-num">Días</th><th class="is-num">Deuda</th><th></th></tr></thead><tbody>' +
                    urgentes.map(function (u, i) {
                        return '<tr class="is-' + u.nivel + '"' + (u.vehicle_id ? ' data-vehiculo="' + u.vehicle_id + '" tabindex="0"' : '') + '>' +
                            '<td><span class="adt_sat__rank">' + (i + 1) + '</span><span class="adt_sat__motivo is-' + u.nivel + '">' +
                                nivelPunto(u.nivel) + esc(u.motivo) + '</span></td>' +
                            '<td class="adt_sat__mono">' + esc(u.numero) + '</td>' +
                            '<td><span class="adt_sat__strong">' + esc(u.placa || '—') + '</span>' +
                                '<span class="adt_sat__sub">' + esc(u.cliente || (u.vehicle_id ? 'Sin cliente' : 'Sin vehículo')) + '</span></td>' +
                            '<td>' + esc(u.estado) + '</td>' +
                            '<td>' + fecha(u.fecha) + '</td>' +
                            '<td class="is-num adt_sat__dias is-' + u.nivel + '">' + entero(u.dias) + '</td>' +
                            '<td class="is-num adt_sat__strong">' + soles(u.monto) + '</td>' +
                            '<td class="is-num">' + (u.vehicle_id ? '<i class="fa fa-angle-right" aria-hidden="true"></i>' : '') + '</td></tr>';
                    }).join('') + '</tbody></table></div>'
                : '<p class="adt_sat__vacio"><i class="fa fa-check-circle" aria-hidden="true"></i> Sin papeletas pendientes de pago.</p>';
            return this._panel('Las más urgentes', 'fa-fire', cuerpo,
                '<span class="adt_sat__muted">Coactiva, medida cautelar y luego las de más días</span>');
        },

        _htmlVehiculos: function (vehiculos) {
            var cuerpo = vehiculos.length
                ? '<div class="adt_sat__table-wrap"><table class="adt_sat__table"><thead><tr>' +
                    '<th>Vehículo</th><th class="is-num">Papeletas</th><th class="is-num">Días</th><th class="is-num">Deuda</th></tr></thead><tbody>' +
                    vehiculos.map(function (v) {
                        return '<tr class="is-' + v.nivel + '" data-vehiculo="' + v.vehicle_id + '" tabindex="0">' +
                            '<td><span class="adt_sat__strong">' + esc(v.placa) + '</span>' +
                                '<span class="adt_sat__sub">' + esc(v.cliente || 'Sin cliente') + '</span></td>' +
                            '<td class="is-num">' + entero(v.n) + (v.coactivas ? ' <span class="adt_sat__chip is-critico">' +
                                entero(v.coactivas) + ' coactiva/cautelar</span>' : '') + '</td>' +
                            '<td class="is-num">' + entero(v.dias) + '</td>' +
                            '<td class="is-num adt_sat__strong">' + soles(v.monto) + '</td></tr>';
                    }).join('') + '</tbody></table></div>'
                : '<p class="adt_sat__vacio">Ningún vehículo con papeletas pendientes.</p>';
            return this._panel('Vehículos con más deuda SAT', 'fa-motorcycle', cuerpo);
        },

        _htmlFechas: function (fechas) {
            return this._panel('Fechas clave', 'fa-calendar', '<dl class="adt_sat__fechas">' + fechas.map(function (f) {
                var valor = f.fecha !== undefined ? fecha(f.fecha)
                    : (f.fecha_hora !== undefined ? (f.fecha_hora ? moment.utc(f.fecha_hora).local().format('DD/MM/YYYY HH:mm') : '—') : esc(f.texto));
                return '<div class="adt_sat__fecha' + (f.nivel ? ' is-' + f.nivel : '') + '"><dt>' + esc(f.label) + '</dt>' +
                    '<dd><span class="adt_sat__fecha-v">' + valor + '</span>' +
                    (f.sub ? '<span class="adt_sat__sub">' + esc(f.sub) + '</span>' : '') + '</dd></div>';
            }).join('') + '</dl>');
        },

        // ------------------------------------------------------------------
        // Pestaña Captura SAT
        // ------------------------------------------------------------------

        _renderCapturas: function () {
            var c = this.cap;
            if (!c) {
                this._ref('subtitle').text('');
                this._ref('body').html('<div class="adt_cart__empty">Cruzando las órdenes de captura con la flota y las papeletas…</div>');
                return;
            }
            if (!c.disponible) {
                this._ref('subtitle').text('');
                this._ref('body').html('<div class="adt_cart__empty">El módulo de capturas SAT (adt_captura_sat) no está instalado ' +
                    'o no tienes acceso.</div>');
                return;
            }
            var cob = c.cobertura;
            this._ref('subtitle').text('Al ' + fecha(c.fecha) + ' · ' + plural(c.total, 'orden vigente', 'órdenes vigentes') +
                ' · ' + plural(c.vehiculos_n, 'vehículo', 'vehículos') + ' · ' + soles(c.monto) +
                (cob && cob.ultima ? ' · última consulta ' + moment.utc(cob.ultima).local().format('DD/MM/YYYY HH:mm') : ''));
            var M = 'adt.captura.sat';
            this._ref('body').html(
                this._htmlRecuadros(c.recuadros) +
                this._htmlCruce(c.filas) +
                '<section class="adt_sat__cols">' +
                    this._htmlBarras('Por razón social', 'fa-building-o', c.por_razon_social, 'Sin órdenes vigentes.', M) +
                    this._htmlBarras('Por financiera', 'fa-university', c.por_financiera, 'Sin órdenes vigentes.', M) +
                '</section>' +
                this._htmlBarras('Por concepto', 'fa-gavel', c.por_concepto, 'Sin órdenes vigentes.', M));
        },

        _htmlHallazgos: function (lista) {
            return '<ul class="adt_sat__hallazgos">' + lista.map(function (h) {
                return '<li class="is-' + h.nivel + '">' + nivelPunto(h.nivel) + esc(h.texto) + '</li>';
            }).join('') + '</ul>';
        },

        _htmlPapeleta: function (p) {
            if (!p) {
                return '<span class="adt_sat__muted">Sin papeleta</span>';
            }
            var titulo = (p.tipo === 'sat' ? 'Papeleta SAT' : 'Papeleta interna') + ' · ' + (COINCIDE[p.coincide] || '');
            return '<button type="button" class="adt_sat__link" data-papeleta="' + p.id + '" data-papeleta-tipo="' + p.tipo +
                '" title="' + esc(titulo) + '">' + '<i class="fa fa-link" aria-hidden="true"></i>' + esc(p.numero) + '</button>' +
                '<span class="adt_sat__sub">' + esc([p.estado, p.deuda ? soles(p.deuda) : '', p.falta].filter(Boolean).join(' · ')) +
                (p.tipo === 'sat' && p.interna ? ' · interna ' + esc(p.interna) : '') +
                (p.coincide === 'documento' ? ' <span class="adt_sat__chip is-atencion">solo número</span>' : '') + '</span>';
        },

        // Tabla del cruce: una fila por vehículo (o placa fuera de la flota) con sus órdenes.
        _htmlCruce: function (filas) {
            var self = this;
            var MATCH = {placa: 'Encontrado por placa (sin vincular)', placa_original: 'Encontrado por placa original',
                         sin_flota: 'No está en la flota'};
            var cuerpo = filas.length
                ? '<div class="adt_sat__table-wrap"><table class="adt_sat__table adt_sat__cruce"><thead><tr>' +
                    '<th>Hallazgos</th><th>Vehículo en flota</th><th>Cliente / empresa</th>' +
                    '<th>Orden SAT</th><th>Papeleta relacionada</th><th class="is-num">Días</th><th class="is-num">Monto</th><th></th>' +
                    '</tr></thead><tbody>' +
                    filas.map(function (f) {
                        var v = f.vehiculo;
                        var abre = f.vehicle_id ? ' data-vehiculo="' + f.vehicle_id + '" tabindex="0"' : '';
                        var vehiculo = v
                            ? '<span class="adt_sat__strong">' + esc(v.placa || f.placa) + '</span>' +
                              '<span class="adt_sat__sub">' + esc(v.nombre || '') + '</span>' +
                              (MATCH[f.match] ? '<span class="adt_sat__chip is-atencion">' + esc(MATCH[f.match]) + '</span>' : '')
                            : '<span class="adt_sat__strong">' + esc(f.placa) + '</span>' +
                              '<span class="adt_sat__chip is-atencion">' + esc(MATCH.sin_flota) + '</span>';
                        var cliente = v
                            ? (v.con_cliente
                                ? '<span class="adt_sat__strong">' + esc(v.cliente || 'Con cliente') + '</span>' +
                                  (v.documento ? '<span class="adt_sat__sub">' + esc(v.documento) + '</span>' : '')
                                : '<span class="adt_sat__muted"><i class="fa fa-cubes" aria-hidden="true"></i> En stock</span>') +
                              '<span class="adt_sat__sub">' + esc([v.razon_social, v.financiera].filter(Boolean).join(' · ')) + '</span>'
                            : '<span class="adt_sat__muted">—</span>';
                        var ordenes = f.ordenes.map(function (o) {
                            return '<div class="adt_sat__orden"><button type="button" class="adt_sat__link adt_sat__mono" data-orden="' + o.id +
                                '" title="Abrir la orden de captura">' + esc(o.documento) + '</button>' +
                                '<span class="adt_sat__sub">' + esc([o.concepto, o.anio, soles(o.monto), o.gestion,
                                                                     o.responsable].filter(Boolean).join(' · ')) + '</span></div>';
                        }).join('');
                        var papeletas = f.ordenes.map(function (o) {
                            return '<div class="adt_sat__orden">' + self._htmlPapeleta(o.papeleta) + '</div>';
                        }).join('');
                        return '<tr class="is-' + f.nivel + '"' + abre + '>' +
                            '<td>' + self._htmlHallazgos(f.hallazgos) + '</td>' +
                            '<td>' + vehiculo + '</td>' +
                            '<td>' + cliente + '</td>' +
                            '<td>' + ordenes + '</td>' +
                            '<td>' + papeletas + '</td>' +
                            '<td class="is-num adt_sat__dias is-' + f.nivel + '">' + entero(f.dias) + '</td>' +
                            '<td class="is-num adt_sat__strong">' + soles(f.monto) + '</td>' +
                            '<td class="is-num">' + (f.vehicle_id ? '<i class="fa fa-angle-right" aria-hidden="true"></i>' : '') + '</td></tr>';
                    }).join('') + '</tbody></table></div>'
                : '<p class="adt_sat__vacio"><i class="fa fa-check-circle" aria-hidden="true"></i> Ningún vehículo con orden de captura vigente.</p>';
            return this._panel('Cruce: órdenes de captura · flota · papeletas', 'fa-random', cuerpo,
                '<span class="adt_sat__muted">Primero las motos con cliente; el documento de la orden se cruza con el número de papeleta</span>');
        },

        _onTab: function (ev) {
            var tab = ev.currentTarget.getAttribute('data-tab');
            if (tab === this.tab) { return; }
            this.tab = tab;
            if (tab === 'capturas' && !this.cap) {
                this._render();  // «Cruzando…» mientras llega
                this._recargar();
                return;
            }
            this._render();
        },

        _onOrden: function (ev) {
            ev.stopPropagation();
            this.do_action({
                type: 'ir.actions.act_window', name: 'Orden de captura SAT', res_model: 'adt.captura.sat',
                res_id: parseInt(ev.currentTarget.getAttribute('data-orden'), 10),
                views: [[false, 'form']], target: 'current',
            });
        },

        _onPapeleta: function (ev) {
            ev.stopPropagation();
            var sat = ev.currentTarget.getAttribute('data-papeleta-tipo') === 'sat';
            this.do_action({
                type: 'ir.actions.act_window', name: sat ? 'Papeleta SAT' : 'Papeleta',
                res_model: sat ? 'adt.papeleta.sat' : 'adt.papeleta',
                res_id: parseInt(ev.currentTarget.getAttribute('data-papeleta'), 10),
                views: [[false, 'form']], target: 'current',
            });
        },

        _fpopValores: function () {
            return {grupo: this.grupo, financiera: this.financiera, estado: this.estado, clientes: this.clientes};
        },

        _fpopDefecto: function () {
            return {grupo: null, financiera: null, estado: null, clientes: null};
        },

        // Secciones del popup con la cantidad de vehículos de cada opción.
        _fpopSecciones: function () {
            var d = this.data;
            var g = d.grupos || {};
            var opciones = function (lista, todos, punto) {
                var propio = _.findWhere(lista, {id: null});  // segmentos de cliente: total propio
                lista = _.reject(lista || [], {id: null});
                var total = propio ? propio.n : lista.reduce(function (a, o) { return a + (o.n || 0); }, 0);
                return [{valor: null, name: todos, n: total}].concat(lista.map(function (o) {
                    return {valor: o.id, name: o.name, n: o.n, punto: punto && o.id};
                }));
            };
            var secciones = [];
            if (g.clientes !== undefined) {
                secciones.push({clave: 'grupo', icono: 'fa-th-large', titulo: 'Vehículos', opciones: [
                    {valor: null, name: 'Todos', n: g.clientes + g.stock},
                    {valor: 'clientes', name: 'Con cliente', n: g.clientes},
                    {valor: 'stock', name: 'En stock', n: g.stock},
                ]});
            }
            secciones.push({clave: 'financiera', icono: 'fa-university', titulo: 'Financiera', opciones: opciones(d.financieras, 'Todas')});
            secciones.push({clave: 'estado', icono: 'fa-calendar-check-o', titulo: 'Cronograma', opciones: opciones(d.estados, 'Todos', true)});
            if (d.clientes) {
                secciones.push({clave: 'clientes', icono: 'fa-user-o', titulo: 'Clientes', opciones: opciones(d.clientes, 'Todos')});
            }
            return secciones;
        },

        _fpopAplicar: function (v) {
            _.extend(this, v);
            this._recargar();
        },

        // Lista de las papeletas SAT detrás de un recuadro o barra.
        _onLista: function (ev) {
            var l = this._listas[ev.currentTarget.getAttribute('data-lista')];
            if (!l) { return; }
            this.do_action({
                type: 'ir.actions.act_window', name: MODELOS[l.modelo].nombre + ' · ' + l.titulo, res_model: l.modelo,
                views: [[false, 'list'], [false, 'form']], domain: [['id', 'in', l.ids]], target: 'current',
            });
        },

        // Ficha del vehículo en Flota 360, abierta en la pestaña Papeleta SAT.
        _onVehiculo: function (ev) {
            this.do_action({
                type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                params: {vehicle_id: parseInt(ev.currentTarget.getAttribute('data-vehiculo'), 10),
                         tab: this.tab === 'capturas' ? null : 'papeletas'},
            });
        },

        _onVehiculoTecla: function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onVehiculo(ev);
            }
        },

        _onRefresh: function () {
            this._recargar();
        },
    });

    core.action_registry.add('adt_flota_360_indicadores', Indicadores);
    return Indicadores;
});
