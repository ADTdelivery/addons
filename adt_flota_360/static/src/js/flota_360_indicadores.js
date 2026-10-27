odoo.define('adt_flota_360.Indicadores', function (require) {
    'use strict';

    /**
     * Indicadores de la flota (gerencia): cuatro recuadros filtrables por financiera,
     * cronograma y situación del cliente. Cada recuadro abre la Consulta de vehículos
     * con el mismo filtro (mismos cálculos en el servidor) y la ficha en su pestaña.
     * Usa los filtros de "Cartera y financieras" (.adt_cart, de adt_comercial).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;

    function soles(n) {
        return 'S/ ' + (n || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
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
            'click [data-ver]': '_onVer',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.financiera = null;
            this.estado = null;
            this.clientes = null;
            this.data = null;
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

        _render: function () {
            var d = this.data;
            this._ref('subtitle').text('Al ' + moment(d.fecha).format('DD/MM/YYYY') + ' · ' + plural(d.total, 'vehículo', 'vehículos'));
            this._renderFiltros();
            var p = d.papeletas;
            this._ref('body').html('<section class="adt_find__grid">' + [
                {ver: 'papeletas', tab: 'papeletas', icon: 'fa-file-text-o', label: 'Papeletas pendientes',
                 valor: soles(p.monto), sub: plural(p.vehiculos, 'vehículo', 'vehículos') +
                    (p.coactiva ? ' · ' + entero(p.coactiva) + ' en coactiva' : ''),
                 nivel: p.coactiva ? 'critico' : (p.vehiculos ? 'atencion' : 'ok')},
                {ver: 'gps_off', tab: 'gps', icon: 'fa-map-marker', label: 'Vehículos sin reportar',
                 valor: entero(d.gps.vehiculos), sub: 'GPS sin señal', nivel: d.gps.vehiculos ? 'atencion' : 'ok'},
                {ver: 'mora', tab: 'cronograma', icon: 'fa-money', label: 'Nos deben',
                 valor: soles(d.deuda.monto), sub: 'Cuotas vencidas · ' + plural(d.deuda.vehiculos, 'vehículo', 'vehículos'),
                 nivel: d.deuda.monto ? 'critico' : 'ok'},
                {ver: 'mora', tab: 'cronograma', icon: 'fa-clock-o', label: 'Mora',
                 valor: soles(d.mora.monto), sub: plural(d.mora.vehiculos, 'vehículo', 'vehículos'),
                 nivel: d.mora.monto ? 'atencion' : 'ok'},
            ].map(function (t) {
                return '<button type="button" class="adt_find__box is-' + t.nivel + '" data-ver="' + t.ver + '" data-tab="' + t.tab + '">' +
                    '<span class="adt_find__box-head"><i class="fa ' + t.icon + '" aria-hidden="true"></i>' + esc(t.label) +
                        '<i class="fa fa-angle-right adt_find__box-go" aria-hidden="true"></i></span>' +
                    '<span class="adt_find__box-value">' + esc(t.valor) + '</span>' +
                    '<span class="adt_find__box-sub">' + esc(t.sub) + '</span></button>';
            }).join('') + '</section>');
        },

        _renderFiltros: function () {
            var self = this;
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

        _onVer: function (ev) {
            var el = ev.currentTarget;
            this.do_action({
                type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                params: {filtro: el.getAttribute('data-ver'), tab: el.getAttribute('data-tab'),
                         financiera: this.financiera, estado: this.estado, clientes: this.clientes},
            });
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
