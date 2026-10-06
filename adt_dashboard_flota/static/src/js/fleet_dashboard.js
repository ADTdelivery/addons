odoo.define('adt_dashboard_flota.FleetDashboard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;

    // Orden fijo de estados de placa: el color sigue al estado, nunca al ranking.
    var PLATE_ORDER = ['lista', 'tramite', 'sin_placa'];
    var PLATE_CLASS = {lista: 'is-ready', tramite: 'is-progress', sin_placa: 'is-none'};

    var FILTERS = [
        {key: 'vehicle_type_label', label: 'Tipo'},
        {key: 'brand', label: 'Marca'},
        {key: 'model', label: 'Modelo'},
        {key: 'year', label: 'Año'},
        {key: 'color', label: 'Color'},
        {key: 'state', label: 'Estado flota'},
        {key: 'plate_status', label: 'Placa'},
    ];

    var TABLE_COLUMNS = [
        {key: 'plate', label: 'Placa'},
        {key: 'model', label: 'Modelo'},
        {key: 'brand', label: 'Marca'},
        {key: 'year', label: 'Año'},
        {key: 'color', label: 'Color'},
        {key: 'state', label: 'Estado flota'},
        {key: 'plate_status', label: 'Estado placa'},
        {key: 'procedure_state', label: 'Trámite', procedureOnly: true},
        {key: 'vin', label: 'Chasis / VIN'},
    ];

    // Muestra visual del color de la moto (acompaña siempre al nombre, nunca lo reemplaza).
    var COLOR_SWATCHES = [
        [/NEGR/, '#141414'], [/BLANC/, '#ffffff'], [/GUIND|VINO|BURDE/, '#7b1e2b'],
        [/ROJ/, '#d32f2f'], [/CELEST/, '#4fb3e8'], [/AZUL/, '#1e4fd8'],
        [/VERDE/, '#2e9d3a'], [/AMARILL/, '#f2c200'], [/NARANJ/, '#f07c00'],
        [/PLATA|PLATEAD/, '#c0c0c0'], [/PLOM|GRIS/, '#7d7d7d'], [/MARR|CAF/, '#6d4c33'],
        [/MORAD|LILA|VIOLET/, '#6a3fb5'], [/ROSA|FUCSI/, '#e05298'], [/DORAD/, '#c9a227'],
        [/BEIG|CREMA/, '#e3d3b0'],
    ];

    // Rampa secuencial (un solo tono, claro → oscuro) para el mapa de calor.
    var HEAT_STEPS = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'];

    function fmt(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function pct(part, total) {
        return total ? Math.round(((part || 0) * 1000) / total) / 10 : 0;
    }

    function swatchFor(colorName) {
        for (var i = 0; i < COLOR_SWATCHES.length; i++) {
            if (COLOR_SWATCHES[i][0].test(colorName)) {
                return COLOR_SWATCHES[i][1];
            }
        }
        return null;
    }

    function compareYears(a, b) {
        var na = parseInt(a, 10);
        var nb = parseInt(b, 10);
        if (isNaN(na) && isNaN(nb)) { return String(a).localeCompare(String(b)); }
        if (isNaN(na)) { return 1; }
        if (isNaN(nb)) { return -1; }
        return na - nb;
    }

    var FleetDashboard = AbstractAction.extend({
        template: 'adt_dashboard_flota.Dashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="reset"]': '_onReset',
            'click [data-action="export"]': '_onExport',
            'change [data-filter]': '_onFilterChange',
            'click [data-dim]': '_onGroupClick',
            'click [data-open]': '_onOpenList',
            'click [data-vehicle-id]': '_onOpenVehicle',
            'input [data-ref="search"]': '_onSearch',
            'click [data-sort]': '_onSort',
            'click [data-page]': '_onPage',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.filters = {};
            this.search = '';
            this.sort = {key: 'model', dir: 1};
            this.page = 0;
            this.pageSize = 25;
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._renderAll();
            });
        },

        // ------------------------------------------------------------------
        // Datos
        // ------------------------------------------------------------------

        _load: function () {
            var self = this;
            return this._rpc({
                model: 'adt.fleet.dashboard',
                method: 'get_dashboard_data',
                args: [],
            }).then(function (data) {
                self.data = data;
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _plateLabel: function (status) {
            return this.data.plate_status_labels[status] || status;
        },

        _matches: function (vehicle) {
            var filters = this.filters;
            return _.every(_.keys(filters), function (key) {
                return !filters[key] || vehicle[key] === filters[key];
            });
        },

        _fleetRows: function () {
            return this.data.vehicles.filter(this._matches.bind(this));
        },

        _group: function (rows, key) {
            var map = {};
            rows.forEach(function (v) {
                var k = v[key];
                var g = map[k] || (map[k] = {key: k, label: k, total: 0, lista: 0, tramite: 0, sin_placa: 0});
                g.total++;
                g[v.plate_status]++;
            });
            return _.values(map);
        },

        _byTotal: function (groups) {
            return groups.sort(function (a, b) {
                return b.total - a.total || String(a.label).localeCompare(String(b.label));
            });
        },

        // ------------------------------------------------------------------
        // Render
        // ------------------------------------------------------------------

        _renderAll: function () {
            var generated = this.data.generated_at ? moment.utc(this.data.generated_at).local() : moment();
            this._ref('updated').text('Actualizado ' + generated.format('DD/MM/YYYY HH:mm'));
            this._renderFilters();
            this._renderBody();
        },

        _renderFilters: function () {
            var self = this;
            var vehicles = this.data.vehicles;
            var html = FILTERS.map(function (f) {
                var counts = _.countBy(vehicles.filter(function (v) { return !v.has_owner; }), f.key);
                var values = _.uniq(_.pluck(vehicles, f.key));
                if (f.key === 'year') {
                    values.sort(compareYears);
                } else if (f.key === 'plate_status') {
                    values = PLATE_ORDER.filter(function (s) { return _.contains(values, s); });
                } else {
                    values.sort();
                }
                var options = values.map(function (val) {
                    var label = f.key === 'plate_status' ? self._plateLabel(val) : val;
                    return '<option value="' + esc(val) + '"' + (self.filters[f.key] === val ? ' selected' : '') + '>' +
                        esc(label) + ' (' + fmt(counts[val] || 0) + ')</option>';
                }).join('');
                return '<label class="adt_fd__filter' + (self.filters[f.key] ? ' is-set' : '') + '">' +
                    '<span>' + esc(f.label) + '</span>' +
                    '<select data-filter="' + f.key + '"><option value="">Todos</option>' + options + '</select>' +
                    '</label>';
            }).join('');
            var activeCount = _.compact(_.values(this.filters)).length;
            html += '<button type="button" class="adt_fd__btn adt_fd__btn--ghost" data-action="reset"' +
                (activeCount ? '' : ' disabled') + '>Limpiar filtros' + (activeCount ? ' (' + activeCount + ')' : '') + '</button>';
            this._ref('filters').html(html);
        },

        _renderBody: function () {
            var fleet = this._fleetRows();
            var stock = fleet.filter(function (v) { return !v.has_owner; });
            this._current = {fleet: fleet, stock: stock};

            var html = this._kpisHtml(fleet, stock) + this._plateOverviewHtml(stock);
            if (!stock.length) {
                html += '<div class="adt_fd__empty">No hay motos en stock para los filtros seleccionados.</div>';
            } else {
                html += '<div class="adt_fd__grid">' +
                    this._card('Stock por modelo', 'Haz clic en una barra para filtrar', this._hbarsHtml(this._byTotal(this._group(stock, 'model')), 'model'), 'wide') +
                    this._card('Stock por año', 'Año de modelo', this._columnsHtml(this._group(stock, 'year').sort(function (a, b) { return compareYears(a.key, b.key); }), 'year')) +
                    this._card('Stock por color', null, this._hbarsHtml(this._byTotal(this._group(stock, 'color')), 'color', {swatch: true})) +
                    this._card('Stock por estado de flota', null, this._hbarsHtml(this._group(stock, 'state').sort(this._byStateSeq(stock)), 'state')) +
                    this._card('Stock por marca', null, this._hbarsHtml(this._byTotal(this._group(stock, 'brand')), 'brand')) +
                    this._card('Mapa de stock: modelo × año', 'Intensidad = unidades en stock', this._heatmapHtml(stock), 'wide') +
                    this._card('Flota por modelo: stock vs. con dueño', 'Toda la flota activa con los filtros aplicados', this._fleetCompositionHtml(fleet), 'wide') +
                    this._card('Resumen por modelo', 'Avance de placas del stock', this._summaryTableHtml(stock), 'wide') +
                    '</div>';
            }
            html += '<section class="adt_fd__card adt_fd__card--wide adt_fd__detail" data-ref="detail"></section>';
            this._ref('body').html(html);
            this._renderDetail();
        },

        _byStateSeq: function (rows) {
            var seq = {};
            rows.forEach(function (v) { seq[v.state] = v.state_seq; });
            return function (a, b) { return (seq[a.key] - seq[b.key]) || (b.total - a.total); };
        },

        _card: function (title, subtitle, content, size) {
            return '<section class="adt_fd__card' + (size === 'wide' ? ' adt_fd__card--wide' : '') + '">' +
                '<header class="adt_fd__card-head"><h2>' + esc(title) + '</h2>' +
                (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</header>' +
                '<div class="adt_fd__card-body">' + content + '</div></section>';
        },

        _legendHtml: function () {
            var self = this;
            return '<div class="adt_fd__legend">' + PLATE_ORDER.map(function (s) {
                return '<span><i class="adt_fd__dot ' + PLATE_CLASS[s] + '"></i>' + esc(self._plateLabel(s)) + '</span>';
            }).join('') + '</div>';
        },

        _kpisHtml: function (fleet, stock) {
            var counts = _.countBy(stock, 'plate_status');
            var owned = fleet.length - stock.length;
            var ready = counts.lista || 0;
            var tiles = [
                {open: 'fleet', label: 'Flota activa', value: fleet.length, sub: 'vehículos registrados'},
                {open: 'owned', label: 'Con dueño', value: owned, sub: pct(owned, fleet.length) + '% de la flota'},
                {open: 'stock', label: 'Stock disponible', value: stock.length, sub: pct(stock.length, fleet.length) + '% de la flota sin dueño', hero: true},
                {open: 'lista', label: 'Stock con placa lista', value: ready, sub: pct(ready, stock.length) + '% del stock', status: 'lista'},
                {open: 'tramite', label: 'Placa en trámite', value: counts.tramite || 0, sub: pct(counts.tramite, stock.length) + '% del stock', status: 'tramite'},
                {open: 'sin_placa', label: 'Sin placa', value: counts.sin_placa || 0, sub: pct(counts.sin_placa, stock.length) + '% del stock', status: 'sin_placa'},
            ];
            return '<div class="adt_fd__kpis">' + tiles.map(function (t) {
                return '<button type="button" class="adt_fd__kpi' + (t.hero ? ' adt_fd__kpi--hero' : '') + '" data-open="' + t.open + '" title="Ver vehículos">' +
                    '<span class="adt_fd__kpi-label">' + (t.status ? '<i class="adt_fd__dot ' + PLATE_CLASS[t.status] + '"></i>' : '') + esc(t.label) + '</span>' +
                    '<span class="adt_fd__kpi-value">' + fmt(t.value) + '</span>' +
                    '<span class="adt_fd__kpi-sub">' + esc(t.sub) + '</span></button>';
            }).join('') + '</div>';
        },

        _plateOverviewHtml: function (stock) {
            var self = this;
            var counts = _.countBy(stock, 'plate_status');
            var total = stock.length;
            var bar = PLATE_ORDER.filter(function (s) { return counts[s]; }).map(function (s) {
                var tip = '<div class="adt_fd__tip-title">' + esc(self._plateLabel(s)) + '</div>' +
                    '<div class="adt_fd__tip-row">Unidades<b>' + fmt(counts[s]) + '</b></div>' +
                    '<div class="adt_fd__tip-row">Del stock<b>' + pct(counts[s], total) + '%</b></div>';
                return '<span class="adt_fd__seg ' + PLATE_CLASS[s] + '" style="flex-grow:' + counts[s] + '" data-dim="plate_status" data-key="' + s + '" data-tip="' + esc(tip) + '"></span>';
            }).join('');
            var legend = PLATE_ORDER.map(function (s) {
                return '<div class="adt_fd__overview-item" data-dim="plate_status" data-key="' + s + '">' +
                    '<i class="adt_fd__dot ' + PLATE_CLASS[s] + '"></i>' +
                    '<span class="adt_fd__overview-label">' + esc(self._plateLabel(s)) + '</span>' +
                    '<b>' + fmt(counts[s] || 0) + '</b><span class="adt_fd__muted">' + pct(counts[s], total) + '%</span></div>';
            }).join('');
            return '<section class="adt_fd__card adt_fd__card--wide adt_fd__overview">' +
                '<header class="adt_fd__card-head"><h2>Estado de placas del stock</h2>' +
                '<p>' + fmt(total) + ' motos sin dueño</p></header>' +
                '<div class="adt_fd__overview-bar">' + (bar || '<span class="adt_fd__seg is-empty"></span>') + '</div>' +
                '<div class="adt_fd__overview-legend">' + legend + '</div></section>';
        },

        _tipHtml: function (title, g, totalLabel) {
            var self = this;
            return '<div class="adt_fd__tip-title">' + esc(title) + '</div>' +
                PLATE_ORDER.map(function (s) {
                    return '<div class="adt_fd__tip-row"><span><i class="adt_fd__dot ' + PLATE_CLASS[s] + '"></i>' +
                        esc(self._plateLabel(s)) + '</span><b>' + fmt(g[s]) + '</b></div>';
                }).join('') +
                '<div class="adt_fd__tip-row adt_fd__tip-total"><span>' + esc(totalLabel || 'Total stock') + '</span><b>' + fmt(g.total) + '</b></div>';
        },

        _hbarsHtml: function (groups, dim, opts) {
            var self = this;
            opts = opts || {};
            var max = _.max(_.pluck(groups, 'total')) || 1;
            var rows = groups.map(function (g) {
                var segs = PLATE_ORDER.filter(function (s) { return g[s]; }).map(function (s) {
                    return '<span class="adt_fd__seg ' + PLATE_CLASS[s] + '" style="width:' + (g[s] / max * 100) + '%"></span>';
                }).join('');
                var swatch = '';
                if (opts.swatch) {
                    var c = swatchFor(g.key);
                    swatch = '<i class="adt_fd__swatch' + (c ? '' : ' is-unknown') + '"' + (c ? ' style="background:' + c + '"' : '') + '></i>';
                }
                return '<div class="adt_fd__hbar' + (self.filters[dim] === g.key ? ' is-active' : '') + '" data-dim="' + dim + '" data-key="' + esc(g.key) + '" data-tip="' + esc(self._tipHtml(g.label, g)) + '">' +
                    '<span class="adt_fd__hbar-label">' + swatch + '<span>' + esc(g.label) + '</span></span>' +
                    '<span class="adt_fd__track">' + segs + '</span>' +
                    '<span class="adt_fd__hbar-val">' + fmt(g.total) + '</span></div>';
            }).join('');
            return this._legendHtml() + '<div class="adt_fd__hbars">' + rows + '</div>';
        },

        _columnsHtml: function (groups, dim) {
            var self = this;
            var max = _.max(_.pluck(groups, 'total')) || 1;
            var cols = groups.map(function (g) {
                var h = g.total / max * 88; // deja aire para la etiqueta superior
                var segs = PLATE_ORDER.filter(function (s) { return g[s]; }).map(function (s) {
                    return '<span class="adt_fd__seg ' + PLATE_CLASS[s] + '" style="flex-grow:' + g[s] + '"></span>';
                }).join('');
                return '<div class="adt_fd__col' + (self.filters[dim] === g.key ? ' is-active' : '') + '" data-dim="' + dim + '" data-key="' + esc(g.key) + '" data-tip="' + esc(self._tipHtml(g.label, g)) + '">' +
                    '<div class="adt_fd__col-plot">' +
                    '<span class="adt_fd__col-val" style="bottom:calc(' + h + '% + 4px)">' + fmt(g.total) + '</span>' +
                    '<div class="adt_fd__col-stack" style="height:' + h + '%">' + segs + '</div></div>' +
                    '<span class="adt_fd__col-label">' + esc(g.label) + '</span></div>';
            }).join('');
            return this._legendHtml() + '<div class="adt_fd__cols">' + cols + '</div>';
        },

        _heatmapHtml: function (stock) {
            var self = this;
            var models = _.pluck(this._byTotal(this._group(stock, 'model')), 'key');
            var years = _.uniq(_.pluck(stock, 'year')).sort(compareYears);
            var cells = {};
            stock.forEach(function (v) {
                var k = v.model + '\u0000' + v.year;
                var c = cells[k] || (cells[k] = {total: 0, lista: 0, tramite: 0, sin_placa: 0});
                c.total++;
                c[v.plate_status]++;
            });
            var max = _.max(_.pluck(_.values(cells), 'total')) || 1;
            var head = '<tr><th>Modelo</th>' + years.map(function (y) { return '<th>' + esc(y) + '</th>'; }).join('') + '<th>Total</th></tr>';
            var body = models.map(function (m) {
                var rowTotal = 0;
                var tds = years.map(function (y) {
                    var c = cells[m + '\u0000' + y];
                    if (!c) { return '<td class="adt_fd__heat-empty">·</td>'; }
                    rowTotal += c.total;
                    var step = Math.min(HEAT_STEPS.length - 1, Math.floor((c.total / max) * (HEAT_STEPS.length - 1) + 0.0001));
                    return '<td class="adt_fd__heat-cell' + (step >= 3 ? ' is-dark' : '') + '" style="background:' + HEAT_STEPS[step] + '"' +
                        ' data-dim="model" data-key="' + esc(m) + '" data-dim2="year" data-key2="' + esc(y) + '"' +
                        ' data-tip="' + esc(self._tipHtml(m + ' · ' + y, c)) + '">' + fmt(c.total) + '</td>';
                }).join('');
                return '<tr><th class="adt_fd__heat-row" data-dim="model" data-key="' + esc(m) + '">' + esc(m) + '</th>' + tds + '<td class="adt_fd__heat-total">' + fmt(rowTotal) + '</td></tr>';
            }).join('');
            var scale = '<div class="adt_fd__heat-scale"><span>Menos</span>' +
                HEAT_STEPS.map(function (c) { return '<i style="background:' + c + '"></i>'; }).join('') + '<span>Más</span></div>';
            return '<div class="adt_fd__table-wrap"><table class="adt_fd__heat"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>' + scale;
        },

        _fleetCompositionHtml: function (fleet) {
            var self = this;
            var map = {};
            fleet.forEach(function (v) {
                var g = map[v.model] || (map[v.model] = {key: v.model, stock: 0, owned: 0, total: 0});
                g.total++;
                g[v.has_owner ? 'owned' : 'stock']++;
            });
            var groups = _.values(map).sort(function (a, b) { return b.total - a.total || a.key.localeCompare(b.key); });
            var max = _.max(_.pluck(groups, 'total')) || 1;
            var rows = groups.map(function (g) {
                var tip = '<div class="adt_fd__tip-title">' + esc(g.key) + '</div>' +
                    '<div class="adt_fd__tip-row"><span><i class="adt_fd__dot is-stock"></i>Stock (sin dueño)</span><b>' + fmt(g.stock) + '</b></div>' +
                    '<div class="adt_fd__tip-row"><span><i class="adt_fd__dot is-owned"></i>Con dueño</span><b>' + fmt(g.owned) + '</b></div>' +
                    '<div class="adt_fd__tip-row adt_fd__tip-total"><span>Flota</span><b>' + fmt(g.total) + '</b></div>';
                return '<div class="adt_fd__hbar' + (self.filters.model === g.key ? ' is-active' : '') + '" data-dim="model" data-key="' + esc(g.key) + '" data-tip="' + esc(tip) + '">' +
                    '<span class="adt_fd__hbar-label"><span>' + esc(g.key) + '</span></span>' +
                    '<span class="adt_fd__track">' +
                    (g.stock ? '<span class="adt_fd__seg is-stock" style="width:' + (g.stock / max * 100) + '%"></span>' : '') +
                    (g.owned ? '<span class="adt_fd__seg is-owned" style="width:' + (g.owned / max * 100) + '%"></span>' : '') +
                    '</span><span class="adt_fd__hbar-val">' + fmt(g.stock) + ' / ' + fmt(g.total) + '</span></div>';
            }).join('');
            var legend = '<div class="adt_fd__legend"><span><i class="adt_fd__dot is-stock"></i>Stock (sin dueño)</span>' +
                '<span><i class="adt_fd__dot is-owned"></i>Con dueño</span></div>';
            return legend + '<div class="adt_fd__hbars">' + rows + '</div>';
        },

        _summaryTableHtml: function (stock) {
            var groups = this._byTotal(this._group(stock, 'model'));
            var totals = {total: 0, lista: 0, tramite: 0, sin_placa: 0};
            var body = groups.map(function (g) {
                PLATE_ORDER.concat(['total']).forEach(function (k) { totals[k] += g[k]; });
                var p = pct(g.lista, g.total);
                return '<tr data-dim="model" data-key="' + esc(g.key) + '"><td>' + esc(g.label) + '</td>' +
                    '<td class="num">' + fmt(g.total) + '</td><td class="num">' + fmt(g.lista) + '</td>' +
                    '<td class="num">' + fmt(g.tramite) + '</td><td class="num">' + fmt(g.sin_placa) + '</td>' +
                    '<td><span class="adt_fd__meter"><span class="is-ready" style="width:' + p + '%"></span></span><span class="num">' + p + '%</span></td></tr>';
            }).join('');
            var foot = '<tr><td>Total</td><td class="num">' + fmt(totals.total) + '</td><td class="num">' + fmt(totals.lista) + '</td>' +
                '<td class="num">' + fmt(totals.tramite) + '</td><td class="num">' + fmt(totals.sin_placa) + '</td>' +
                '<td><span class="num">' + pct(totals.lista, totals.total) + '%</span></td></tr>';
            return '<div class="adt_fd__table-wrap"><table class="adt_fd__table adt_fd__table--click"><thead><tr>' +
                '<th>Modelo</th><th class="num">Stock</th><th class="num">Placa lista</th><th class="num">En trámite</th><th class="num">Sin placa</th><th>% placa lista</th>' +
                '</tr></thead><tbody>' + body + '</tbody><tfoot>' + foot + '</tfoot></table></div>';
        },

        _detailRows: function () {
            var self = this;
            var q = this.search.trim().toUpperCase();
            var rows = this._current.stock;
            if (q) {
                rows = rows.filter(function (v) {
                    return [v.plate, v.model, v.brand, v.year, v.color, v.state, v.vin, v.name, self._plateLabel(v.plate_status)]
                        .join(' ').toUpperCase().indexOf(q) !== -1;
                });
            }
            var key = this.sort.key;
            var dir = this.sort.dir;
            return rows.slice().sort(function (a, b) {
                var r = key === 'year' ? compareYears(a.year, b.year)
                    : key === 'plate_status' ? PLATE_ORDER.indexOf(a.plate_status) - PLATE_ORDER.indexOf(b.plate_status)
                    : String(a[key] || '').localeCompare(String(b[key] || ''));
                return r * dir || a.id - b.id;
            });
        },

        _visibleColumns: function () {
            var withProcedures = this.data.has_plate_procedures;
            return TABLE_COLUMNS.filter(function (c) { return !c.procedureOnly || withProcedures; });
        },

        _renderDetail: function () {
            var self = this;
            var rows = this._detailRows();
            var pages = Math.max(1, Math.ceil(rows.length / this.pageSize));
            this.page = Math.min(this.page, pages - 1);
            var slice = rows.slice(this.page * this.pageSize, (this.page + 1) * this.pageSize);
            var columns = this._visibleColumns();

            var head = columns.map(function (c) {
                var arrow = self.sort.key === c.key ? (self.sort.dir > 0 ? ' ▲' : ' ▼') : '';
                return '<th data-sort="' + c.key + '" class="is-sortable">' + esc(c.label) + arrow + '</th>';
            }).join('');
            var body = slice.map(function (v) {
                return '<tr data-vehicle-id="' + v.id + '">' + columns.map(function (c) {
                    if (c.key === 'plate_status') {
                        return '<td><span class="adt_fd__badge ' + PLATE_CLASS[v.plate_status] + '"><i class="adt_fd__dot ' + PLATE_CLASS[v.plate_status] + '"></i>' + esc(self._plateLabel(v.plate_status)) + '</span></td>';
                    }
                    if (c.key === 'plate') {
                        return '<td class="adt_fd__plate">' + esc(v.plate || '—') + '</td>';
                    }
                    return '<td>' + esc(v[c.key] || '—') + '</td>';
                }).join('') + '</tr>';
            }).join('') || '<tr><td colspan="' + columns.length + '" class="adt_fd__muted">Sin resultados</td></tr>';

            var from = rows.length ? this.page * this.pageSize + 1 : 0;
            var to = Math.min(rows.length, (this.page + 1) * this.pageSize);
            var html = '<header class="adt_fd__card-head adt_fd__detail-head">' +
                '<div><h2>Detalle del stock</h2><p>' + fmt(rows.length) + ' motos · clic en una fila para abrir la ficha</p></div>' +
                '<div class="adt_fd__detail-tools">' +
                '<input type="search" class="adt_fd__search" data-ref="search" placeholder="Buscar placa, modelo, VIN…" value="' + esc(this.search) + '"/>' +
                '<button type="button" class="adt_fd__btn adt_fd__btn--ghost" data-action="export">Exportar CSV</button>' +
                '</div></header>' +
                '<div class="adt_fd__table-wrap"><table class="adt_fd__table adt_fd__table--click"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>' +
                '<footer class="adt_fd__pager"><span>' + fmt(from) + '–' + fmt(to) + ' de ' + fmt(rows.length) + '</span>' +
                '<button type="button" class="adt_fd__btn adt_fd__btn--ghost" data-page="-1"' + (this.page === 0 ? ' disabled' : '') + '>‹ Anterior</button>' +
                '<button type="button" class="adt_fd__btn adt_fd__btn--ghost" data-page="1"' + (this.page >= pages - 1 ? ' disabled' : '') + '>Siguiente ›</button>' +
                '</footer>';

            var $detail = this._ref('detail');
            var hadFocus = document.activeElement && document.activeElement.getAttribute('data-ref') === 'search';
            $detail.html(html);
            if (hadFocus) {
                var input = $detail.find('[data-ref="search"]')[0];
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            }
        },

        _setFilter: function (key, value) {
            this.filters[key] = this.filters[key] === value ? '' : value;
            this.page = 0;
            this._renderFilters();
            this._renderBody();
        },

        // ------------------------------------------------------------------
        // Handlers
        // ------------------------------------------------------------------

        _onRefresh: function () {
            var self = this;
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true).text('Actualizando…');
            this._load().then(function () {
                self._renderAll();
            }).finally(function () {
                $btn.prop('disabled', false).text('Actualizar');
            });
        },

        _onReset: function () {
            this.filters = {};
            this.page = 0;
            this._renderFilters();
            this._renderBody();
        },

        _onFilterChange: function (ev) {
            var $sel = $(ev.currentTarget);
            this.filters[$sel.data('filter')] = $sel.val();
            this.page = 0;
            this._renderFilters();
            this._renderBody();
        },

        _onGroupClick: function (ev) {
            ev.stopPropagation();
            var el = ev.currentTarget;
            var dim = el.getAttribute('data-dim');
            var key = el.getAttribute('data-key');
            var dim2 = el.getAttribute('data-dim2');
            this._hideTip();
            if (dim2) {
                // Celda del mapa de calor: fija ambos filtros a la vez.
                this.filters[dim] = key;
                this.filters[dim2] = el.getAttribute('data-key2');
                this.page = 0;
                this._renderFilters();
                this._renderBody();
                return;
            }
            this._setFilter(dim, key);
        },

        _onOpenList: function (ev) {
            var kind = ev.currentTarget.getAttribute('data-open');
            var current = this._current;
            var sets = {
                fleet: {name: 'Flota activa', rows: current.fleet},
                owned: {name: 'Vehículos con dueño', rows: current.fleet.filter(function (v) { return v.has_owner; })},
                stock: {name: 'Stock disponible', rows: current.stock},
            };
            var target = sets[kind] || {
                name: 'Stock · ' + this._plateLabel(kind),
                rows: current.stock.filter(function (v) { return v.plate_status === kind; }),
            };
            this._openVehicles(target.name, _.pluck(target.rows, 'id'));
        },

        _openVehicles: function (name, ids) {
            this.do_action({
                type: 'ir.actions.act_window',
                name: name,
                res_model: 'fleet.vehicle',
                views: [[false, 'list'], [false, 'form']],
                domain: [['id', 'in', ids]],
                target: 'current',
            });
        },

        _onOpenVehicle: function (ev) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'fleet.vehicle',
                res_id: parseInt(ev.currentTarget.getAttribute('data-vehicle-id'), 10),
                views: [[false, 'form']],
                target: 'current',
            });
        },

        _onSearch: _.debounce(function (ev) {
            this.search = ev.target.value || '';
            this.page = 0;
            this._renderDetail();
        }, 200),

        _onSort: function (ev) {
            var key = ev.currentTarget.getAttribute('data-sort');
            this.sort = {key: key, dir: this.sort.key === key ? -this.sort.dir : 1};
            this._renderDetail();
        },

        _onPage: function (ev) {
            this.page += parseInt(ev.currentTarget.getAttribute('data-page'), 10);
            this._renderDetail();
        },

        _onExport: function () {
            var self = this;
            var columns = this._visibleColumns();
            var quote = function (val) { return '"' + String(val == null ? '' : val).replace(/"/g, '""') + '"'; };
            var lines = [columns.map(function (c) { return quote(c.label); }).join(',')];
            this._detailRows().forEach(function (v) {
                lines.push(columns.map(function (c) {
                    return quote(c.key === 'plate_status' ? self._plateLabel(v.plate_status) : v[c.key]);
                }).join(','));
            });
            var blob = new Blob(['﻿' + lines.join('\r\n')], {type: 'text/csv;charset=utf-8'});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'stock_flota_' + moment().format('YYYYMMDD_HHmm') + '.csv';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
        },

        // Tooltip flotante compartido por todas las marcas.
        _onTipShow: function (ev) {
            this._ref('tooltip').html(ev.currentTarget.getAttribute('data-tip')).addClass('is-visible');
            this._onTipMove(ev);
        },

        _onTipMove: function (ev) {
            var tip = this._ref('tooltip')[0];
            var x = ev.clientX + 14;
            var y = ev.clientY + 14;
            if (x + tip.offsetWidth > window.innerWidth - 8) { x = ev.clientX - tip.offsetWidth - 14; }
            if (y + tip.offsetHeight > window.innerHeight - 8) { y = ev.clientY - tip.offsetHeight - 14; }
            tip.style.left = x + 'px';
            tip.style.top = y + 'px';
        },

        _onTipHide: function () {
            this._hideTip();
        },

        _hideTip: function () {
            this._ref('tooltip').removeClass('is-visible');
        },
    });

    core.action_registry.add('adt_fleet_dashboard', FleetDashboard);

    return FleetDashboard;
});
