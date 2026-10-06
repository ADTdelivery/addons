odoo.define('adt_comercial.CobranzaDashboard', function (require) {
    'use strict';

    /**
     * Reporte de Cobranzas: estado de la cartera (al día, con deuda, orden de captura, capturada),
     * antigüedad de la deuda, motivos de captura, recaudación por día/semana/mes y lista para gestionar.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;

    // Estados de cobranza: color de estado + ícono + texto (nunca solo color).
    var ESTADOS = [
        {key: 'al_dia', label: 'Al día', cls: 'ok', icon: '✓'},
        {key: 'deuda', label: 'Con deuda', cls: 'warn', icon: '!'},
        {key: 'orden', label: 'Orden de captura', cls: 'serious', icon: '!'},
        {key: 'capturada', label: 'Capturada', cls: 'bad', icon: '■'},
    ];

    // Antigüedad de la deuda (días desde la cuota vencida más antigua).
    var TRAMOS = [
        {label: '1–7 días', min: 1, max: 7},
        {label: '8–15 días', min: 8, max: 15},
        {label: '16–30 días', min: 16, max: 30},
        {label: '31–60 días', min: 31, max: 60},
        {label: '61–90 días', min: 61, max: 90},
        {label: 'Más de 90', min: 91, max: Infinity},
    ];
    // Rampa ordinal de un solo tono: más oscuro = más antiguo.
    var TRAMO_COLORES = ['#f3b98f', '#ee9a63', '#e57c3c', '#d2602a', '#ad4720', '#843416'];

    var RANGOS = [
        {key: 'dia', label: 'Por día', detalle: 'últimos 30 días', n: 30},
        {key: 'semana', label: 'Por semana', detalle: 'últimas 12 semanas', n: 12},
        {key: 'mes', label: 'Por mes', detalle: 'últimos 12 meses', n: 12},
    ];

    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var PAGINA = 20;
    var TOP_BARRAS = 8;

    function sum(rows, key) {
        return rows.reduce(function (acc, r) { return acc + (r[key] || 0); }, 0);
    }

    function pct(part, total) {
        return total > 0 ? (part / total) * 100 : 0;
    }

    function normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim();
    }

    function niceStep(max, ticks) {
        var raw = max / ticks;
        var mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
        var norm = raw / mag;
        return (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
    }

    var CobranzaDashboard = AbstractAction.extend({
        template: 'adt_comercial.CobranzaDashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="export"]': '_onExport',
            'click [data-financiera]': '_onFinanciera',
            'change [data-ref="cartera"]': '_onCartera',
            'click [data-rango]': '_onRango',
            'click [data-tab]': '_onTab',
            'click [data-sort]': '_onSort',
            'click [data-page]': '_onPage',
            'click [data-cuenta]': '_onOpenCuenta',
            'input [data-ref="buscar"]': '_onBuscar',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.cartera = null;
            this.financiera = null;
            this.rango = 'semana';
            this.tab = 'deuda';
            this.busqueda = '';
            this.sort = {key: 'dias', dir: -1};
            this.page = 0;
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._render();
            });
        },

        _load: function () {
            var self = this;
            return this._rpc({
                model: 'adt.comercial.cobranza.dashboard',
                method: 'get_dashboard_data',
                args: [],
            }).then(function (data) {
                self.data = data;
                self.hoy = moment(data.hoy);
                var nombres = {};
                data.financieras.forEach(function (f) { nombres[f.id] = f.nombre; });
                data.cuentas.forEach(function (c) {
                    c.financiera = nombres[c.financiera_id] || '';
                    c._buscar = normalizar([c.referencia, c.cliente, c.documento, c.telefono, c.moto, c.asesor, c.financiera].join(' '));
                });
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _money: function (value, compact) {
            var sym = this.data.moneda.simbolo;
            var abs = Math.abs(value || 0);
            var txt;
            if (compact && abs >= 1e6) {
                txt = (abs / 1e6).toLocaleString('es-PE', {maximumFractionDigits: 1}) + ' M';
            } else if (compact && abs >= 1e3) {
                txt = (abs / 1e3).toLocaleString('es-PE', {maximumFractionDigits: abs < 1e4 ? 1 : 0}) + ' mil';
            } else {
                txt = Math.round(abs).toLocaleString('es-PE');
            }
            txt = this.data.moneda.posicion === 'after' ? txt + ' ' + sym : sym + ' ' + txt;
            return (value < -0.5 ? '−' : '') + txt;
        },

        _estado: function (key) {
            return _.findWhere(ESTADOS, {key: key});
        },

        _badge: function (key) {
            var e = this._estado(key);
            return '<span class="adt_cob__badge adt_cob__badge--' + e.cls + '"><i class="adt_cob__icon adt_cob__icon--' + e.cls +
                '" aria-hidden="true">' + e.icon + '</i>' + esc(e.label) + '</span>';
        },

        // ------------------------------------------------------------------ datos filtrados
        _vista: function () {
            var cartera = this.cartera;
            var financiera = this.financiera;
            var filtro = function (r) {
                return (cartera === null || r.cartera === cartera) && (financiera === null || r.financiera_id === financiera);
            };
            return {
                cuentas: this.data.cuentas.filter(filtro),
                pagos: this.data.pagos.filter(filtro),
                programado: this.data.programado.filter(filtro),
            };
        },

        _claveFecha: function (fecha, gran) {
            if (gran === 'mes') { return fecha.slice(0, 7); }
            if (gran === 'semana') { return moment(fecha).startOf('isoWeek').format('YYYY-MM-DD'); }
            return fecha;
        },

        _buckets: function (gran, n) {
            var out = [];
            var unidad = gran === 'dia' ? 'days' : gran === 'semana' ? 'weeks' : 'months';
            for (var i = n - 1; i >= 0; i--) {
                var d = this.hoy.clone().subtract(i, unidad);
                out.push(this._claveFecha(d.format('YYYY-MM-DD'), gran));
            }
            return out;
        },

        _bucketLabel: function (key, gran, largo) {
            var m = moment(key.length === 7 ? key + '-01' : key);
            if (gran === 'mes') { return MESES[m.month()] + ' ' + m.format('YY'); }
            if (gran === 'semana') {
                return largo ? 'Semana del ' + m.format('DD/MM') + ' al ' + m.clone().add(6, 'days').format('DD/MM') : m.format('DD/MM');
            }
            return largo ? m.format('dddd DD/MM') : m.format('DD/MM');
        },

        // Cobrado y programado de un periodo [desde, hasta].
        _periodo: function (v, desde, hasta) {
            var hoyStr = this.data.hoy;
            var cobro = v.pagos.filter(function (p) { return p.fecha >= desde && p.fecha <= hasta; });
            var prog = v.programado.filter(function (p) { return p.fecha >= desde && p.fecha <= hasta; });
            return {
                cobrado: sum(cobro, 'cuota') + sum(cobro, 'mora'),
                pagos: sum(cobro, 'pagos'),
                programado: sum(prog, 'monto'),
                programadoHoy: sum(prog.filter(function (p) { return p.fecha <= hoyStr; }), 'monto'),
            };
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var nombreFinanciera = this.financiera === null ? 'todas las financieras' :
                (_.findWhere(this.data.financieras, {id: this.financiera}) || {}).nombre;
            var nombreCartera = this.cartera === null ? 'todas las carteras' :
                'cartera ' + ((_.findWhere(this.data.carteras, {codigo: this.cartera}) || {}).nombre || '').toLowerCase();
            this._ref('subtitle').text('Al ' + this.hoy.format('DD/MM/YYYY') + ' · ' + nombreFinanciera + ' · ' + nombreCartera);
            this._renderFiltros();
            var v = this._vista();
            if (!v.cuentas.length && !v.pagos.length) {
                this._ref('body').html('<div class="adt_fin__empty">No hay cuentas en curso para este filtro.</div>');
                return;
            }
            this._ref('body').html(
                this._card('Estado de la cartera hoy', v.cuentas.length + ' cuentas en curso · toca un estado para ver sus cuentas',
                    this._estadoHtml(v), 'wide') +
                '<div class="adt_cob__grid2">' +
                this._card('¿Cuánto tiempo llevan sin pagar?', 'Monto vencido según la cuota impaga más antigua', this._antiguedadHtml(v)) +
                this._card('¿Por qué tienen orden de captura?', 'Cuentas con orden de captura y capturadas, por motivo', this._motivosHtml(v)) +
                '</div>' +
                this._card('Recaudación', 'Lo cobrado frente a lo que vencía en cada periodo', this._recaudoHtml(v), 'wide') +
                '<div class="adt_cob__grid2">' +
                this._card('Por forma de pago', this._rango().detalle, this._rankingHtml(v, 'forma')) +
                this._card('Por cobrador', this._rango().detalle + ' · usuario que registró el pago', this._rankingHtml(v, 'cobrador')) +
                '</div>' +
                '<section class="adt_fin__card adt_cob__gestion" data-ref="gestion"></section>' +
                this._comoSeLeeHtml()
            );
            this._renderGestion();
        },

        _renderFiltros: function () {
            var self = this;
            var chips = [{id: null, nombre: 'Todas las financieras'}].concat(this.data.financieras);
            this._ref('financieras').html(chips.map(function (f) {
                var activo = self.financiera === f.id;
                return '<button type="button" class="adt_fin__chip' + (activo ? ' is-active' : '') + '" data-financiera="' +
                    (f.id === null ? 'todas' : f.id) + '" aria-pressed="' + activo + '">' + esc(f.nombre) + '</button>';
            }).join(''));
            var presentes = _.uniq(_.pluck(this.data.cuentas, 'cartera'));
            var opciones = [{codigo: '', nombre: 'Todas'}].concat(
                this.data.carteras.filter(function (c) { return _.contains(presentes, c.codigo); }));
            this._ref('cartera').html(opciones.map(function (c) {
                return '<option value="' + esc(c.codigo) + '"' + ((self.cartera || '') === c.codigo ? ' selected' : '') + '>' + esc(c.nombre) + '</option>';
            }).join(''));
        },

        _card: function (title, subtitle, content, size) {
            return '<section class="adt_fin__card' + (size === 'wide' ? ' adt_cob__wide' : '') + '">' +
                '<header class="adt_fin__card-head"><h2>' + esc(title) + '</h2>' +
                (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</header>' + content + '</section>';
        },

        _rango: function () {
            return _.findWhere(RANGOS, {key: this.rango});
        },

        // Indicadores + barra 100% con los cuatro estados.
        _estadoHtml: function (v) {
            var self = this;
            var total = v.cuentas.length;
            var por = _.groupBy(v.cuentas, 'estado');
            var n = function (k) { return (por[k] || []).length; };
            var saldo = sum(v.cuentas, 'saldo_pendiente');
            var vencido = sum(v.cuentas, 'vencido');
            var riesgo = sum(v.cuentas.filter(function (c) { return c.dias > 30; }), 'saldo_pendiente');
            var urgentes = (por.orden || []).filter(function (c) { return c.prioridad === 'urgente'; }).length;

            var barra = ESTADOS.filter(function (e) { return n(e.key); }).map(function (e) {
                var tip = '<b>' + e.label + '</b><br/>' + n(e.key) + ' cuentas (' + Math.round(pct(n(e.key), total)) + '%)';
                return '<span class="adt_cob__seg adt_cob__seg--' + e.cls + '" style="flex-grow:' + n(e.key) + '" data-tab="' + e.key +
                    '" data-tip="' + esc(tip) + '"></span>';
            }).join('');

            var tiles = ESTADOS.map(function (e) {
                var extra = {
                    al_dia: Math.round(pct(n('al_dia'), total)) + '% de la cartera',
                    deuda: self._money(sum(por.deuda || [], 'vencido')) + ' vencido',
                    orden: urgentes ? urgentes + (urgentes === 1 ? ' urgente' : ' urgentes') : 'ninguna urgente',
                    capturada: 'motos retenidas o en disolución',
                }[e.key];
                return '<button type="button" class="adt_cob__state adt_cob__state--' + e.cls + (self.tab === e.key ? ' is-active' : '') +
                    '" data-tab="' + e.key + '">' +
                    '<span class="adt_cob__state-label"><i class="adt_cob__icon adt_cob__icon--' + e.cls + '" aria-hidden="true">' + e.icon + '</i>' + esc(e.label) + '</span>' +
                    '<span class="adt_cob__state-value">' + n(e.key) + '</span>' +
                    '<span class="adt_cob__state-sub">' + esc(extra) + '</span></button>';
            }).join('');

            var resumen = '<div class="adt_cob__facts">' +
                '<div><span>Saldo por cobrar</span><b>' + this._money(saldo) + '</b></div>' +
                '<div><span>Vencido sin pagar</span><b>' + this._money(vencido) + '</b></div>' +
                '<div data-tip="' + esc('<b>Cartera en riesgo (PAR30)</b><br/>Saldo total de las cuentas con más de 30 días de atraso, sobre el saldo de toda la cartera. Es el indicador estándar de morosidad en créditos.') + '">' +
                '<span>Cartera en riesgo +30 días (PAR30)</span><b>' + pct(riesgo, saldo).toFixed(1) + '%</b>' +
                '<em>' + this._money(riesgo) + '</em></div></div>';

            return '<div class="adt_cob__states">' + tiles + '</div>' +
                '<div class="adt_cob__bar">' + barra + '</div>' + resumen;
        },

        _antiguedadHtml: function (v) {
            var self = this;
            var conDeuda = v.cuentas.filter(function (c) { return c.dias > 0 && c.vencido > 0.005; });
            if (!conDeuda.length) {
                return '<p class="adt_cob__ok"><i class="adt_cob__icon adt_cob__icon--ok">✓</i>Ninguna cuenta tiene cuotas vencidas.</p>';
            }
            var tramos = TRAMOS.map(function (t, i) {
                var cs = conDeuda.filter(function (c) { return c.dias >= t.min && c.dias <= t.max; });
                return {label: t.label, n: cs.length, monto: sum(cs, 'vencido'), color: TRAMO_COLORES[i]};
            });
            var max = _.max(_.pluck(tramos, 'monto')) || 1;
            var total = sum(tramos, 'monto');
            var cols = tramos.map(function (t) {
                var h = t.monto / max * 85;
                var tip = '<b>' + t.label + ' de atraso</b><br/>' + t.n + ' cuentas<br/>' + self._money(t.monto) + ' vencido (' + Math.round(pct(t.monto, total)) + '%)';
                return '<div class="adt_cob__col" data-tip="' + esc(tip) + '">' +
                    '<div class="adt_cob__col-plot">' +
                    '<span class="adt_cob__col-val" style="bottom:calc(' + h + '% + 4px)">' + esc(self._money(t.monto, true)) + '</span>' +
                    '<span class="adt_cob__col-bar" style="height:' + h + '%;background:' + t.color + '"></span></div>' +
                    '<span class="adt_cob__col-label">' + esc(t.label) + '</span>' +
                    '<span class="adt_cob__col-sub">' + t.n + (t.n === 1 ? ' cuenta' : ' cuentas') + '</span></div>';
            }).join('');
            var mas30 = sum(tramos.slice(3), 'monto');
            return '<div class="adt_cob__cols">' + cols + '</div>' +
                '<p class="adt_fin__note"><b>' + this._money(mas30) + '</b> (' + Math.round(pct(mas30, total)) +
                '% de lo vencido) tiene más de 30 días: es la deuda más difícil de recuperar.</p>';
        },

        _motivosHtml: function (v) {
            var self = this;
            var casos = v.cuentas.filter(function (c) { return c.estado === 'orden' || c.estado === 'capturada'; });
            if (!casos.length) {
                return '<p class="adt_cob__ok"><i class="adt_cob__icon adt_cob__icon--ok">✓</i>No hay cuentas con orden de captura ni capturadas.</p>';
            }
            var motivos = this.data.motivos;
            var grupos = _.keys(motivos).map(function (m) {
                var cs = casos.filter(function (c) { return c.motivo === m; });
                return {
                    motivo: m, label: motivos[m], total: cs.length,
                    orden: cs.filter(function (c) { return c.estado === 'orden'; }).length,
                    capturada: cs.filter(function (c) { return c.estado === 'capturada'; }).length,
                };
            }).filter(function (g) { return g.total; }).sort(function (a, b) { return b.total - a.total; });
            var max = _.max(_.pluck(grupos, 'total')) || 1;
            var filas = grupos.map(function (g) {
                var tip = '<b>' + g.label + '</b><br/>Orden de captura: ' + g.orden + '<br/>Capturadas: ' + g.capturada;
                return '<div class="adt_cob__hbar" data-tip="' + esc(tip) + '">' +
                    '<span class="adt_cob__hbar-label">' + esc(g.label) + '</span>' +
                    '<span class="adt_cob__track">' +
                    (g.orden ? '<span class="adt_cob__seg--serious" style="width:' + (g.orden / max * 100) + '%"></span>' : '') +
                    (g.capturada ? '<span class="adt_cob__seg--bad" style="width:' + (g.capturada / max * 100) + '%"></span>' : '') +
                    '</span><span class="adt_cob__hbar-val">' + g.total + '</span></div>';
            }).join('');
            var capturadas = casos.filter(function (c) { return c.estado === 'capturada' && c.captura; });
            var tipos = _.countBy(capturadas, function (c) { return c.captura.tipo || 'Sin tipo'; });
            var estadosCap = _.countBy(capturadas, function (c) { return c.captura.estado || 'Sin estado'; });
            var urgentes = casos.filter(function (c) { return c.estado === 'orden' && c.prioridad === 'urgente'; }).length;
            var detalle = function (map) {
                return _.map(map, function (n, k) { return esc(k) + ': <b>' + n + '</b>'; }).join(' · ');
            };
            return '<div class="adt_fin__legend"><span><i class="adt_fin__dot adt_cob__seg--serious"></i>Orden de captura</span>' +
                '<span><i class="adt_fin__dot adt_cob__seg--bad"></i>Capturada</span></div>' +
                '<div class="adt_cob__hbars">' + filas + '</div>' +
                '<ul class="adt_cob__facts-list">' +
                '<li>Órdenes urgentes: <b>' + urgentes + '</b> de ' + casos.filter(function (c) { return c.estado === 'orden'; }).length + '</li>' +
                (capturadas.length ? '<li>Capturas por tipo: ' + detalle(tipos) + '</li><li>Situación: ' + detalle(estadosCap) + '</li>' : '') +
                '</ul>';
        },

        _recaudoHtml: function (v) {
            var self = this;
            var hoy = this.data.hoy;
            var inicioSemana = this.hoy.clone().startOf('isoWeek').format('YYYY-MM-DD');
            var finSemana = this.hoy.clone().endOf('isoWeek').format('YYYY-MM-DD');
            var inicioMes = this.hoy.clone().startOf('month').format('YYYY-MM-DD');
            var finMes = this.hoy.clone().endOf('month').format('YYYY-MM-DD');
            var kpis = [
                {label: 'Hoy', p: this._periodo(v, hoy, hoy)},
                {label: 'Esta semana', p: this._periodo(v, inicioSemana, finSemana)},
                {label: 'Este mes', p: this._periodo(v, inicioMes, finMes)},
            ].map(function (k) {
                var tasa = pct(k.p.cobrado, k.p.programadoHoy);
                return '<div class="adt_cob__kpi">' +
                    '<span class="adt_cob__kpi-label">Recaudado ' + esc(k.label.toLowerCase()) + '</span>' +
                    '<span class="adt_cob__kpi-value">' + self._money(k.p.cobrado) + '</span>' +
                    '<span class="adt_cob__kpi-sub">' + k.p.pagos + (k.p.pagos === 1 ? ' pago' : ' pagos') + ' · vencía ' +
                    self._money(k.p.programadoHoy) + (k.p.programadoHoy > 0.5 ? ' (' + Math.round(tasa) + '% cobrado)' : '') + '</span></div>';
            }).join('');

            var rango = this._rango();
            var buckets = this._buckets(rango.key, rango.n);
            var datos = {};
            buckets.forEach(function (b) { datos[b] = {cobrado: 0, pagos: 0, programado: 0, programadoHoy: 0}; });
            v.pagos.forEach(function (p) {
                var d = datos[self._claveFecha(p.fecha, rango.key)];
                if (d) { d.cobrado += p.cuota + p.mora; d.pagos += p.pagos; }
            });
            v.programado.forEach(function (p) {
                var d = datos[self._claveFecha(p.fecha, rango.key)];
                if (d) {
                    d.programado += p.monto;
                    if (p.fecha <= hoy) { d.programadoHoy += p.monto; }
                }
            });
            var max = 0;
            buckets.forEach(function (b) { max = Math.max(max, datos[b].cobrado, datos[b].programado); });
            var step = niceStep(max || 1, 4);
            var top = Math.max(step * Math.ceil((max || 1) / step), step);
            var grid = '';
            for (var g = 0; g <= top + 0.5; g += step) {
                grid += '<span class="adt_fin__gridline" style="bottom:' + (g / top * 100) + '%"><em>' + esc(this._money(g, true)) + '</em></span>';
            }
            var cols = buckets.map(function (b) {
                var d = datos[b];
                var tasa = pct(d.cobrado, d.programadoHoy);
                var tip = '<b>' + esc(self._bucketLabel(b, rango.key, true)) + '</b>' +
                    '<div class="adt_fin__tip-row"><span><i class="adt_fin__dot is-in"></i>Cobrado</span><b>' + self._money(d.cobrado) + '</b></div>' +
                    '<div class="adt_fin__tip-row"><span><i class="adt_fin__dot adt_cob__prog"></i>Vencía en el periodo</span><b>' + self._money(d.programado) + '</b></div>' +
                    '<div class="adt_fin__tip-row adt_fin__tip-total"><span>' + d.pagos + ' pagos</span><b>' +
                    (d.programadoHoy > 0.5 ? Math.round(tasa) + '% cobrado' : '—') + '</b></div>';
                var tasaTxt = d.programadoHoy > 0.5 ? Math.round(tasa) + '%' : '—';
                return '<div class="adt_fin__month" data-tip="' + esc(tip) + '">' +
                    '<div class="adt_fin__month-plot">' +
                    '<span class="adt_fin__bar adt_cob__prog" style="height:' + (d.programado / top * 100) + '%"></span>' +
                    '<span class="adt_fin__bar is-in" style="height:' + (d.cobrado / top * 100) + '%"></span></div>' +
                    '<span class="adt_fin__month-label">' + esc(self._bucketLabel(b, rango.key)) + '</span>' +
                    '<span class="adt_cob__rate">' + tasaTxt + '</span></div>';
            }).join('');

            var filas = buckets.slice().reverse().map(function (b) {
                var d = datos[b];
                return '<tr><td>' + esc(self._bucketLabel(b, rango.key, true)) + '</td><td class="num">' + self._money(d.cobrado) + '</td>' +
                    '<td class="num">' + d.pagos + '</td><td class="num">' + self._money(d.programado) + '</td>' +
                    '<td class="num">' + (d.programadoHoy > 0.5 ? Math.round(pct(d.cobrado, d.programadoHoy)) + '%' : '—') + '</td></tr>';
            }).join('');

            var chips = RANGOS.map(function (r) {
                return '<button type="button" class="adt_fin__chip' + (r.key === self.rango ? ' is-active' : '') + '" data-rango="' + r.key + '">' + r.label + '</button>';
            }).join('');

            return '<div class="adt_cob__kpis">' + kpis + '</div>' +
                '<div class="adt_cob__chart-head"><div class="adt_fin__legend"><span><i class="adt_fin__dot is-in"></i>Cobrado</span>' +
                '<span><i class="adt_fin__dot adt_cob__prog"></i>Lo que vencía en el periodo</span>' +
                '<span class="adt_fin__muted">% = cobrado sobre lo que vencía hasta hoy</span></div>' +
                '<div class="adt_fin__chips">' + chips + '</div></div>' +
                '<div class="adt_fin__calendar adt_cob__calendar"><div class="adt_fin__grid-lines">' + grid + '</div>' + cols + '</div>' +
                '<details class="adt_fin__table-toggle"><summary>Ver como tabla</summary>' +
                '<table class="adt_fin__table"><thead><tr><th>Periodo</th><th class="num">Cobrado</th><th class="num">Pagos</th>' +
                '<th class="num">Vencía</th><th class="num">% cobrado</th></tr></thead><tbody>' + filas + '</tbody></table></details>';
        },

        _rankingHtml: function (v, campo) {
            var self = this;
            var rango = this._rango();
            var desde = this._buckets(rango.key, rango.n)[0];
            if (rango.key === 'mes') { desde += '-01'; }
            var pagos = v.pagos.filter(function (p) { return p.fecha >= desde; });
            var grupos = _.map(_.groupBy(pagos, campo), function (rows, nombre) {
                return {nombre: nombre, monto: sum(rows, 'cuota') + sum(rows, 'mora'), pagos: sum(rows, 'pagos')};
            }).sort(function (a, b) { return b.monto - a.monto; });
            if (!grupos.length) {
                return '<p class="adt_fin__muted">Sin pagos en este periodo.</p>';
            }
            if (grupos.length > TOP_BARRAS) {
                var resto = grupos.slice(TOP_BARRAS - 1);
                grupos = grupos.slice(0, TOP_BARRAS - 1).concat([{
                    nombre: 'Otros (' + resto.length + ')', monto: sum(resto, 'monto'), pagos: sum(resto, 'pagos')}]);
            }
            var total = sum(grupos, 'monto');
            var max = _.max(_.pluck(grupos, 'monto')) || 1;
            return '<div class="adt_cob__hbars">' + grupos.map(function (g) {
                var tip = '<b>' + esc(g.nombre) + '</b><br/>' + self._money(g.monto) + ' · ' + g.pagos + ' pagos<br/>' + Math.round(pct(g.monto, total)) + '% del total';
                return '<div class="adt_cob__hbar" data-tip="' + esc(tip) + '">' +
                    '<span class="adt_cob__hbar-label">' + esc(g.nombre) + '</span>' +
                    '<span class="adt_cob__track"><span class="is-in" style="width:' + (g.monto / max * 100) + '%"></span></span>' +
                    '<span class="adt_cob__hbar-val">' + self._money(g.monto, true) + '</span></div>';
            }).join('') + '</div>';
        },

        // ------------------------------------------------------------------ lista para gestionar
        _columnas: function () {
            var base = [
                {key: 'referencia', label: 'Cuenta'},
                {key: 'cliente', label: 'Cliente'},
                {key: 'telefono', label: 'Teléfono'},
                {key: 'moto', label: 'Moto'},
                {key: 'financiera', label: 'Financiera'},
                {key: 'cartera_label', label: 'Cartera'},
            ];
            var deuda = [
                {key: 'dias', label: 'Días sin pagar', num: true},
                {key: 'cuotas_vencidas', label: 'Cuotas vencidas', num: true},
                {key: 'vencido', label: 'Monto vencido', num: true, money: true},
            ];
            var extra = {
                al_dia: [{key: 'saldo_pendiente', label: 'Saldo por cobrar', num: true, money: true}],
                deuda: deuda,
                orden: deuda.concat([{key: 'motivo', label: 'Motivo'}, {key: 'prioridad', label: 'Prioridad'}]),
                capturada: deuda.concat([{key: 'motivo', label: 'Motivo'}, {key: 'captura', label: 'Captura'}]),
            }[this.tab];
            return base.concat(extra, [{key: 'asesor', label: 'Asesor'}]);
        },

        _filas: function () {
            var self = this;
            var q = normalizar(this.busqueda);
            var filas = this._vista().cuentas.filter(function (c) {
                return c.estado === self.tab && (!q || c._buscar.indexOf(q) !== -1);
            });
            var key = this.sort.key;
            var dir = this.sort.dir;
            return filas.sort(function (a, b) {
                var va = key === 'captura' ? (a.captura && a.captura.fecha) || '' : a[key];
                var vb = key === 'captura' ? (b.captura && b.captura.fecha) || '' : b[key];
                var r = typeof va === 'number' ? va - vb : String(va || '').localeCompare(String(vb || ''));
                return r * dir || b.dias - a.dias || a.id - b.id;
            });
        },

        _celda: function (c, col) {
            if (col.key === 'cliente') {
                return '<td><b>' + esc(c.cliente) + '</b>' + (c.documento ? '<span class="adt_fin__doc">' + esc(c.documento) + '</span>' : '') + '</td>';
            }
            if (col.key === 'motivo') {
                return '<td>' + esc(c.motivo ? this.data.motivos[c.motivo] : '—') + '</td>';
            }
            if (col.key === 'prioridad') {
                return '<td>' + (c.prioridad === 'urgente' ? '<span class="adt_cob__badge adt_cob__badge--bad"><i class="adt_cob__icon adt_cob__icon--bad">!</i>Urgente</span>' :
                    c.prioridad ? 'Normal' : '—') + '</td>';
            }
            if (col.key === 'captura') {
                var cap = c.captura || {};
                return '<td>' + esc(_.compact([cap.estado, cap.tipo]).join(' · ') || '—') +
                    (cap.fecha ? '<span class="adt_fin__doc">desde ' + moment(cap.fecha).format('DD/MM/YYYY') + (cap.razon ? ' · ' + esc(cap.razon) : '') + '</span>' : '') + '</td>';
            }
            var val = c[col.key];
            if (col.money) { return '<td class="num">' + this._money(val) + '</td>'; }
            if (col.key === 'dias') {
                return '<td class="num' + (val > 30 ? ' adt_fin__loss-text' : '') + '">' + val + '</td>';
            }
            return '<td' + (col.num ? ' class="num"' : '') + '>' + esc(val === '' || val === null || val === undefined ? '—' : val) + '</td>';
        },

        _renderGestion: function () {
            var self = this;
            var $box = this._ref('gestion');
            if (!$box.length) { return; }
            var v = this._vista();
            var conteo = _.countBy(v.cuentas, 'estado');
            var filas = this._filas();
            var cols = this._columnas();
            var paginas = Math.max(1, Math.ceil(filas.length / PAGINA));
            this.page = Math.min(this.page, paginas - 1);
            var inicio = this.page * PAGINA;

            var tabs = ESTADOS.slice().reverse().map(function (e) {
                return '<button type="button" role="tab" class="adt_cob__tab' + (self.tab === e.key ? ' is-active' : '') + '" data-tab="' + e.key +
                    '" aria-selected="' + (self.tab === e.key) + '"><i class="adt_cob__icon adt_cob__icon--' + e.cls + '" aria-hidden="true">' + e.icon + '</i>' +
                    esc(e.label) + ' <span class="adt_cob__tab-n">' + (conteo[e.key] || 0) + '</span></button>';
            }).join('');
            var head = cols.map(function (c) {
                var flecha = self.sort.key === c.key ? (self.sort.dir > 0 ? ' ▲' : ' ▼') : '';
                return '<th class="is-sortable' + (c.num ? ' num' : '') + '" data-sort="' + c.key + '">' + esc(c.label) + flecha + '</th>';
            }).join('');
            var body = filas.slice(inicio, inicio + PAGINA).map(function (c) {
                return '<tr data-cuenta="' + c.id + '">' + cols.map(function (col) { return self._celda(c, col); }).join('') + '</tr>';
            }).join('') || '<tr><td colspan="' + cols.length + '" class="adt_fin__muted">' +
                (this.busqueda ? 'Ninguna cuenta coincide con la búsqueda.' : 'No hay cuentas en este estado.') + '</td></tr>';
            var totalVencido = sum(filas, 'vencido');
            var pager = '<footer class="adt_fin__pager"><span>' + (filas.length ? (inicio + 1) + '–' + Math.min(filas.length, inicio + PAGINA) + ' de ' : '') +
                filas.length + (this.tab !== 'al_dia' && filas.length ? ' · ' + this._money(totalVencido) + ' vencido' : '') + '</span>' +
                (paginas > 1 ? '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-page="-1"' + (this.page === 0 ? ' disabled' : '') + '>‹ Anterior</button>' +
                    '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-page="1"' + (this.page >= paginas - 1 ? ' disabled' : '') + '>Siguiente ›</button>' : '') +
                '</footer>';

            var buscarFoco = document.activeElement && document.activeElement.getAttribute('data-ref') === 'buscar';
            $box.html('<header class="adt_fin__card-head adt_cob__gestion-head"><div><h2>Cuentas para gestionar</h2>' +
                '<p>Toca una cuenta para abrirla · ordenadas por días sin pagar</p></div>' +
                '<div class="adt_cob__tools"><input type="search" class="adt_cob__search" data-ref="buscar" value="' + esc(this.busqueda) +
                '" placeholder="Buscar cliente, DNI, cuenta, placa o teléfono…"/>' +
                '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-action="export">Exportar CSV</button></div></header>' +
                '<nav class="adt_cob__tabs" role="tablist">' + tabs + '</nav>' +
                '<div class="adt_fin__table-wrap adt_fin__table-wrap--full"><table class="adt_fin__table adt_fin__table--click"><thead><tr>' + head +
                '</tr></thead><tbody>' + body + '</tbody></table></div>' + pager);
            if (buscarFoco) {
                var input = $box.find('[data-ref="buscar"]')[0];
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            }
        },

        _comoSeLeeHtml: function () {
            return '<details class="adt_fin__howto"><summary>¿Cómo se calculan estos números?</summary><ul>' +
                '<li><b>Cuentas en curso:</b> cuentas con estado "En curso" (no canceladas ni terminadas de pagar).</li>' +
                '<li><b>Estado</b> (en este orden): <b>Capturada</b> si tiene una captura activa (capturado o disolución de contrato); ' +
                '<b>Orden de captura</b> si está marcada con prioridad de captura normal o urgente; <b>Con deuda</b> si tiene cuotas vencidas sin pagar; si no, <b>Al día</b>.</li>' +
                '<li><b>Días sin pagar:</b> días desde la cuota impaga más antigua.</li>' +
                '<li><b>PAR30:</b> saldo de las cuentas con más de 30 días de atraso sobre el saldo de toda la cartera.</li>' +
                '<li><b>Motivo:</b> el registrado en la captura o, si no hay, el de "Clientes en mora" (cuotas vencidas, papeleta o ambos).</li>' +
                '<li><b>Recaudado:</b> pagos de cuotas publicados (más la mora cobrada), por fecha del pago. <b>Vencía:</b> cuotas con fecha de cronograma en el periodo.</li>' +
                '</ul></details>';
        },

        // ------------------------------------------------------------------ eventos
        _onRefresh: function () {
            var self = this;
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true).text('Actualizando…');
            this._load().then(function () {
                self._render();
            }).finally(function () {
                $btn.prop('disabled', false).text('Actualizar');
            });
        },

        _onFinanciera: function (ev) {
            var raw = ev.currentTarget.getAttribute('data-financiera');
            this.financiera = raw === 'todas' ? null : parseInt(raw, 10);
            this.page = 0;
            this._hideTip();
            this._render();
        },

        _onCartera: function (ev) {
            var codigo = ev.currentTarget.value;
            this.cartera = codigo ? codigo : null;
            this.page = 0;
            this._hideTip();
            this._render();
        },

        _onRango: function (ev) {
            this.rango = ev.currentTarget.getAttribute('data-rango');
            this._hideTip();
            this._render();
        },

        _onTab: function (ev) {
            this.tab = ev.currentTarget.getAttribute('data-tab');
            this.page = 0;
            this._hideTip();
            this.$('.adt_cob__state').each(function () {
                $(this).toggleClass('is-active', this.getAttribute('data-tab') === ev.currentTarget.getAttribute('data-tab'));
            });
            this._renderGestion();
            if (!$(ev.currentTarget).hasClass('adt_cob__tab')) {
                var box = this._ref('gestion')[0];
                this.$('.adt_fin__scroll').animate({scrollTop: box.offsetTop - 16}, 250);
            }
        },

        _onSort: function (ev) {
            var key = ev.currentTarget.getAttribute('data-sort');
            var numerica = _.contains(['dias', 'cuotas_vencidas', 'vencido', 'saldo_pendiente'], key);
            this.sort = {key: key, dir: this.sort.key === key ? -this.sort.dir : (numerica ? -1 : 1)};
            this._renderGestion();
        },

        _onPage: function (ev) {
            this.page += parseInt(ev.currentTarget.getAttribute('data-page'), 10);
            this._renderGestion();
        },

        _onBuscar: _.debounce(function (ev) {
            this.busqueda = ev.target.value || '';
            this.page = 0;
            this._renderGestion();
        }, 200),

        _onOpenCuenta: function (ev) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'adt.comercial.cuentas',
                res_id: parseInt(ev.currentTarget.getAttribute('data-cuenta'), 10),
                views: [[this.data.vista_formulario, 'form']],
                target: 'current',
            });
        },

        _onExport: function () {
            var self = this;
            var cols = this._columnas();
            var quote = function (val) { return '"' + String(val === null || val === undefined ? '' : val).replace(/"/g, '""') + '"'; };
            var lineas = [cols.map(function (c) { return quote(c.label); }).join(',')];
            this._filas().forEach(function (c) {
                lineas.push(cols.map(function (col) {
                    if (col.key === 'motivo') { return quote(c.motivo ? self.data.motivos[c.motivo] : ''); }
                    if (col.key === 'captura') { return quote(c.captura ? _.compact([c.captura.estado, c.captura.tipo, c.captura.fecha]).join(' · ') : ''); }
                    if (col.key === 'cliente') { return quote(c.cliente + (c.documento ? ' (' + c.documento + ')' : '')); }
                    return quote(col.money ? (c[col.key] || 0).toFixed(2) : c[col.key]);
                }).join(','));
            });
            var blob = new Blob(['﻿' + lineas.join('\r\n')], {type: 'text/csv;charset=utf-8'});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'cobranzas_' + this.tab + '_' + moment().format('YYYYMMDD_HHmm') + '.csv';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
        },

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

    core.action_registry.add('adt_cobranza_dashboard', CobranzaDashboard);

    return CobranzaDashboard;
});
