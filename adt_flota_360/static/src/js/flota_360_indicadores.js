odoo.define('adt_flota_360.Indicadores', function (require) {
    'use strict';

    /**
     * Indicadores SAT Lima (gerencia): estados de las papeletas, antigüedad, deuda y las
     * más urgentes, filtrables por financiera, cronograma y situación del cliente.
     * Cada recuadro y barra abre la lista de esas papeletas SAT; las urgentes y los
     * vehículos abren su ficha de Flota 360 en la pestaña Papeleta SAT.
     * Usa los filtros de "Cartera y financieras" (.adt_cart, de adt_comercial).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

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

    var Indicadores = AbstractAction.extend({
        template: 'adt_flota_360.Indicadores',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="limpiar"]': '_onLimpiar',
            'click [data-financiera]': '_onFinanciera',
            'click [data-estado]': '_onEstado',
            'click [data-clientes]': '_onClientes',
            'click [data-lista]': '_onLista',
            'click [data-vehiculo]': '_onVehiculo',
            'keydown tr[data-vehiculo]': '_onVehiculoTecla',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.financiera = null;
            this.estado = null;
            this.clientes = null;
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

        _load: function () {
            var self = this;
            var seq = ++this._seq;
            return this._rpc({
                model: 'adt.flota360', method: 'indicadores', args: [],
                kwargs: {financiera: this.financiera, estado: this.estado, clientes: this.clientes},
            }).then(function (data) {
                if (seq === self._seq) {
                    self.data = data;
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
        _lista: function (titulo, ids) {
            var clave = 'l' + _.size(this._listas);
            this._listas[clave] = {titulo: titulo, ids: ids};
            return clave;
        },

        _render: function () {
            var d = this.data;
            this._listas = {};
            if (!d.disponible) {
                this._ref('subtitle').text('');
                this._ref('facetas').empty();
                this._ref('body').html('<div class="adt_cart__empty">El módulo de papeletas SAT (adt_papeletas) no está instalado ' +
                    'o no tienes acceso.</div>');
                return;
            }
            this._ref('subtitle').text('Al ' + fecha(d.fecha) + ' · ' + plural(d.total, 'papeleta', 'papeletas') + ' en el SAT · ' +
                plural(d.pendientes, 'pendiente de pago', 'pendientes de pago'));
            this._renderFiltros();
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
                return '<button type="button" class="adt_find__box is-' + t.nivel + (vacio ? ' is-empty' : '') + '"' +
                    (vacio ? ' disabled="disabled"' : ' data-lista="' + self._lista(t.label, t.ids) + '"') +
                    ' title="' + (vacio ? 'Sin papeletas' : 'Ver las papeletas') + '">' +
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
        _htmlBarras: function (titulo, icono, filas, vacio) {
            var self = this;
            var max = _.max(_.pluck(filas, 'n').concat([1]));
            var cuerpo = filas.length && _.some(filas, function (f) { return f.n; })
                ? '<ul class="adt_sat__bars">' + filas.map(function (f) {
                    var nivel = f.nivel || 'info';
                    var ancho = f.n ? Math.max(f.n * 100 / max, 2) : 0;
                    var detalle = plural(f.n, 'papeleta', 'papeletas') + ' · ' + soles(f.monto);
                    return '<li><button type="button" class="adt_sat__bar' + (f.n ? '' : ' is-zero') + '"' +
                        (f.n ? ' data-lista="' + self._lista(titulo + ': ' + f.label, f.ids) + '"' : ' disabled="disabled"') +
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

        _renderFiltros: function () {
            var d = this.data;
            var chip = function (attr, valor, activo, texto, n, punto) {
                return '<button type="button" class="adt_cart__fchip' + (activo ? ' is-active' : '') + (!n && !activo ? ' is-zero' : '') +
                    '" ' + attr + '="' + esc(String(valor)) + '" aria-pressed="' + activo + '">' +
                    (punto ? '<i class="adt_cart__fchip-dot is-' + esc(punto) + '" aria-hidden="true"></i>' : '') +
                    esc(texto) + '<span class="adt_cart__fchip-n">' + entero(n) + '</span></button>';
            };
            var fila = function (icono, titulo, attr, actual, todos, opciones, punto) {
                var propio = _.findWhere(opciones, {id: null});  // segmentos de cliente: total propio
                opciones = _.reject(opciones, {id: null});
                var total = propio ? propio.n : opciones.reduce(function (a, o) { return a + (o.n || 0); }, 0);
                return '<div class="adt_cart__facet"><span class="adt_cart__facet-label"><i class="fa ' + icono + '" aria-hidden="true"></i>' +
                    titulo + '</span><div class="adt_cart__facet-chips">' +
                    chip(attr, 'todos', actual === null, todos, total) +
                    opciones.map(function (o) { return chip(attr, o.id, actual === o.id, o.name, o.n, punto && o.id); }).join('') +
                    '</div></div>';
            };
            var filtrado = this.financiera !== null || this.estado !== null || this.clientes !== null;
            this._ref('facetas').html(
                fila('fa-university', 'Financiera', 'data-financiera', this.financiera, 'Todas', d.financieras) +
                fila('fa-calendar-check-o', 'Cronograma', 'data-estado', this.estado, 'Todos', d.estados, true) +
                (d.clientes ? fila('fa-user-o', 'Clientes', 'data-clientes', this.clientes, 'Todos', d.clientes) : '') +
                (filtrado ? '<button type="button" class="adt_cart__count-clear adt_find__clear" data-action="limpiar">' +
                    '<i class="fa fa-times" aria-hidden="true"></i> Quitar filtros</button>' : ''));
        },

        // Lista de las papeletas SAT detrás de un recuadro o barra.
        _onLista: function (ev) {
            var l = this._listas[ev.currentTarget.getAttribute('data-lista')];
            if (!l) { return; }
            this.do_action({
                type: 'ir.actions.act_window', name: 'Papeletas SAT · ' + l.titulo, res_model: 'adt.papeleta.sat',
                views: [[false, 'list'], [false, 'form']], domain: [['id', 'in', l.ids]], target: 'current',
            });
        },

        // Ficha del vehículo en Flota 360, abierta en la pestaña Papeleta SAT.
        _onVehiculo: function (ev) {
            this.do_action({
                type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                params: {vehicle_id: parseInt(ev.currentTarget.getAttribute('data-vehiculo'), 10), tab: 'papeletas'},
            });
        },

        _onVehiculoTecla: function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onVehiculo(ev);
            }
        },

        _onFinanciera: function (ev) {
            var v = ev.currentTarget.getAttribute('data-financiera');
            this.financiera = v === 'todos' ? null : parseInt(v, 10);
            this._recargar();
        },

        _onEstado: function (ev) {
            var v = ev.currentTarget.getAttribute('data-estado');
            this.estado = v === 'todos' ? null : v;
            this._recargar();
        },

        _onClientes: function (ev) {
            var v = ev.currentTarget.getAttribute('data-clientes');
            this.clientes = v === 'todos' ? null : v;
            this._recargar();
        },

        _onLimpiar: function () {
            this.financiera = this.estado = this.clientes = null;
            this._recargar();
        },

        _onRefresh: function () {
            this._recargar();
        },
    });

    core.action_registry.add('adt_flota_360_indicadores', Indicadores);
    return Indicadores;
});
