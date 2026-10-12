odoo.define('adt_dashboard_flota.FleetDashboard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;

    // Severidad: color reservado + ícono + etiqueta (el color nunca va solo).
    var SEVERIDAD = {
        critico: {label: 'Crítico', icon: 'fa-exclamation-circle', cls: 'is-critical'},
        alto: {label: 'Alto', icon: 'fa-exclamation-triangle', cls: 'is-serious'},
        medio: {label: 'Medio', icon: 'fa-info-circle', cls: 'is-warning'},
    };

    // Ícono y tono (decorativo, siempre junto a su etiqueta) de cada indicador.
    var KPI = {
        flota: {icon: 'fa-motorcycle', tone: 'blue'},
        con_placa: {icon: 'fa-id-card-o', tone: 'violet'},
        stock: {icon: 'fa-cubes', tone: 'hero'},
        listas: {icon: 'fa-check-square-o', tone: 'aqua'},
        completo: {icon: 'fa-flag-checkered', tone: 'green'},
        alertas: {icon: 'fa-bell', tone: 'red'},
    };

    var DESGLOSE_PLACA = [
        ['sin_tramite', 'Sin trámite'], ['pendiente', 'Pendiente'],
        ['en_tramite', 'En trámite'], ['observado', 'Observado'],
    ];

    var MATRIZ = {
        stock_sin_placa: {tag: 'Stock sin placa', icon: 'fa-cube', tone: 'blue'},
        stock_con_placa: {tag: 'Listo para vender', icon: 'fa-tag', tone: 'green'},
        duenio_sin_placa: {tag: 'Cliente esperando placa', icon: 'fa-exclamation-circle', tone: 'red', alert: true},
        duenio_con_placa: {tag: 'Proceso completo', icon: 'fa-check-circle', tone: 'green'},
    };

    // Rampa ordinal (un tono, claro → oscuro) para los tramos de antigüedad.
    var RAMPA_ANTIGUEDAD = ['#86b6ef', '#3987e5', '#256abf', '#184f95'];

    // Categóricos validados (orden fijo) para las series del ritmo semanal.
    var SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'];

    function fmt(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function pct(part, total) {
        return total ? Math.round(((part || 0) * 100) / total) : 0;
    }

    function dias(valor) {
        return valor === null || valor === undefined ? '—' : valor.toLocaleString('es-PE', {maximumFractionDigits: 1});
    }

    function tip(titulo, filas) {
        return '<div class="adt_fd__tip-title">' + esc(titulo) + '</div>' + (filas || []).map(function (f) {
            return f[1] === undefined ? '<div class="adt_fd__tip-text">' + esc(f[0]) + '</div>'
                : '<div class="adt_fd__tip-row">' + esc(f[0]) + '<b>' + esc(f[1]) + '</b></div>';
        }).join('');
    }

    var FleetDashboard = AbstractAction.extend({
        template: 'adt_dashboard_flota.Dashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-open]': '_onOpen',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this._opens = [];
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

        _load: function () {
            var self = this;
            return this._rpc({
                model: 'adt.fleet.dashboard',
                method: 'get_operacion_data',
                args: [],
            }).then(function (data) {
                self.data = data;
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        // Registra un destino de navegación y devuelve el atributo que lo dispara.
        _open: function (target, name) {
            if (!target || !target.ids || !target.ids.length) {
                return '';
            }
            this._opens.push({model: target.model, ids: target.ids, name: name});
            return ' data-open="' + (this._opens.length - 1) + '" role="button" tabindex="0"';
        },

        _tipAttr: function (html) {
            return ' data-tip="' + esc(html) + '"';
        },

        // ------------------------------------------------------------------
        // Render
        // ------------------------------------------------------------------

        _renderAll: function () {
            var d = this.data;
            this._opens = [];
            this._ref('updated').text('Actualizado ' + moment.utc(d.generado).local().format('DD/MM/YYYY HH:mm'));
            var html = this._kpisHtml(d.kpis) +
                this._alertasHtml(d.alertas) +
                '<div class="adt_fd__grid">' +
                this._card('Combinaciones de la flota', 'fa-th-large', 'blue', 'Dueño × placa', this._matrizHtml(d.matriz, d.kpis[0].valor)) +
                '<div class="adt_fd__stack">' +
                this._card('Antigüedad del stock', 'fa-hourglass-half', 'violet', 'Motos sin dueño', this._antiguedadHtml(d.antiguedad_stock)) +
                this._card('Talleres de fibra', 'fa-wrench', 'violet', 'Carga actual', this._talleresHtml(d.talleres)) +
                '</div>' +
                this._card('Flujo en curso', 'fa-random', 'aqua', 'Motos en cada etapa ahora', this._wipHtml(d.wip), 'wide') +
                this._card('Tiempos de ciclo', 'fa-clock-o', 'orange', 'Días · últimos ' + d.ventana_dias + ' días', this._tiemposHtml(d.tiempos)) +
                this._card('Ritmo semanal', 'fa-line-chart', 'blue', 'Últimas ' + d.ritmo.semanas.length + ' semanas', this._ritmoHtml(d.ritmo)) +
                '</div>';
            this._ref('body').html(html);
        },

        _card: function (title, icon, tone, subtitle, content, size) {
            return '<section class="adt_fd__card' + (size === 'wide' ? ' adt_fd__card--wide' : '') + '">' +
                '<header class="adt_fd__card-head"><span class="adt_fd__icon is-' + tone + '"><i class="fa ' + icon + '" aria-hidden="true"></i></span>' +
                '<div><h2>' + esc(title) + '</h2>' + (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</div></header>' +
                '<div class="adt_fd__card-body">' + content + '</div></section>';
        },

        _kpisHtml: function (kpis) {
            var self = this;
            return '<div class="adt_fd__kpis">' + kpis.map(function (k) {
                var meta = KPI[k.codigo] || {icon: 'fa-circle', tone: 'blue'};
                var tieneBase = k.base !== undefined;
                var p = tieneBase ? pct(k.valor, k.base) : null;
                var tone = k.alerta && !k.valor ? 'green' : meta.tone;
                var icon = k.alerta && !k.valor ? 'fa-check' : meta.icon;
                var cls = 'adt_fd__kpi is-' + tone + (k.hero ? ' adt_fd__kpi--hero' : '');
                return '<div class="' + cls + '"' + self._open(k.abrir, k.label) + self._tipAttr(tip(k.label, [[k.ayuda]])) + '>' +
                    '<div class="adt_fd__kpi-top"><span class="adt_fd__icon is-' + tone + '"><i class="fa ' + icon + '" aria-hidden="true"></i></span>' +
                    '<span class="adt_fd__kpi-label">' + esc(k.label) + '</span></div>' +
                    '<span class="adt_fd__kpi-value">' + fmt(k.valor) + '</span>' +
                    (tieneBase ? '<span class="adt_fd__kpi-bar"><span style="width:' + p + '%"></span></span>' +
                        '<span class="adt_fd__kpi-sub">' + p + '% ' + esc(k.sub_base) + '</span>'
                        : '<span class="adt_fd__kpi-sub">' + esc(k.sub) + '</span>') +
                    '</div>';
            }).join('') + '</div>';
        },

        _alertasHtml: function (alertas) {
            var self = this;
            var activas = alertas.filter(function (a) { return a.valor; });
            var ok = alertas.filter(function (a) { return !a.valor; });
            var cards = activas.map(function (a) {
                var s = SEVERIDAD[a.severidad];
                var t = tip(a.titulo, [[s.label], [a.descripcion]].concat(a.detalle ? [[a.detalle]] : []));
                return '<div class="adt_fd__alert ' + s.cls + '"' + self._open(a.abrir, a.titulo) + self._tipAttr(t) + '>' +
                    '<span class="adt_fd__sev ' + s.cls + '"><i class="fa ' + s.icon + '" aria-hidden="true"></i>' + s.label + '</span>' +
                    '<span class="adt_fd__alert-value">' + fmt(a.valor) + '</span>' +
                    '<span class="adt_fd__alert-title">' + esc(a.titulo) + '</span>' +
                    (a.detalle ? '<span class="adt_fd__alert-detail">' + esc(a.detalle) + '</span>' : '') +
                    '</div>';
            }).join('');
            var okHtml = ok.length ? '<div class="adt_fd__ok">' + ok.map(function (a) {
                return '<span' + self._tipAttr(tip(a.titulo, [['Sin incidencias'], [a.descripcion]])) + '><i class="fa fa-check" aria-hidden="true"></i>' + esc(a.titulo) + '</span>';
            }).join('') + '</div>' : '';
            var head = '<header class="adt_fd__card-head"><span class="adt_fd__icon is-' + (activas.length ? 'red' : 'green') + '">' +
                '<i class="fa ' + (activas.length ? 'fa-bell' : 'fa-check') + '" aria-hidden="true"></i></span>' +
                '<div><h2>Alertas operativas</h2><p>' + (activas.length ? activas.length + ' requieren acción' : 'Todo en orden') + '</p></div></header>';
            return '<section class="adt_fd__card adt_fd__card--wide adt_fd__alerts">' + head +
                (cards ? '<div class="adt_fd__alert-grid">' + cards + '</div>' : '') + okHtml + '</section>';
        },

        _matrizHtml: function (matriz, total) {
            var self = this;
            var cell = function (key) {
                var c = matriz[key];
                var meta = MATRIZ[key];
                var chips = DESGLOSE_PLACA.filter(function (e) { return c.desglose[e[0]]; }).map(function (e) {
                    var item = c.desglose[e[0]];
                    return '<span class="adt_fd__chip"' + self._open(item.abrir, e[1]) + '><i class="adt_fd__dot is-' + e[0] + '"></i>' +
                        esc(e[1]) + ' <b>' + fmt(item.valor) + '</b></span>';
                }).join('');
                var tone = meta.alert && !c.valor ? 'muted' : meta.tone;
                return '<div class="adt_fd__cell is-' + tone + '"' + self._open(c.abrir, meta.tag) + '>' +
                    '<span class="adt_fd__cell-tag"><i class="fa ' + meta.icon + '" aria-hidden="true"></i> ' + esc(meta.tag) + '</span>' +
                    '<span class="adt_fd__cell-value">' + fmt(c.valor) + ' <small>' + pct(c.valor, total) + '%</small></span>' +
                    (chips ? '<div class="adt_fd__chips">' + chips + '</div>' : '') + '</div>';
            };
            return '<div class="adt_fd__matrix">' +
                '<span></span><span class="adt_fd__matrix-head">Sin placa</span><span class="adt_fd__matrix-head">Con placa</span>' +
                '<span class="adt_fd__matrix-row">Sin dueño</span>' + cell('stock_sin_placa') + cell('stock_con_placa') +
                '<span class="adt_fd__matrix-row">Con dueño</span>' + cell('duenio_sin_placa') + cell('duenio_con_placa') +
                '</div>';
        },

        _antiguedadHtml: function (tramos) {
            var self = this;
            var total = _.reduce(tramos, function (s, t) { return s + t.valor; }, 0);
            var max = _.max(_.pluck(tramos, 'valor')) || 1;
            if (!total) {
                return '<div class="adt_fd__empty">No hay motos en stock.</div>';
            }
            return '<div class="adt_fd__hbars">' + tramos.map(function (t, i) {
                var t2 = tip(t.label, [['Motos', fmt(t.valor)], ['Del stock', pct(t.valor, total) + '%']]);
                return '<div class="adt_fd__hbar"' + self._open(t.abrir, 'Stock · ' + t.label) + self._tipAttr(t2) + '>' +
                    '<span class="adt_fd__hbar-label">' + esc(t.label) + '</span>' +
                    '<span class="adt_fd__track">' + (t.valor ? '<span class="adt_fd__seg" style="width:' + (t.valor / max * 100) + '%;background:' + RAMPA_ANTIGUEDAD[i] + '"></span>' : '') + '</span>' +
                    '<span class="adt_fd__hbar-val">' + fmt(t.valor) + '</span></div>';
            }).join('') + '</div>';
        },

        _etapaHtml: function (e, max, paso, tone) {
            if (e.cerrado) {
                return '<div class="adt_fd__stage is-done"' + this._open(e.abrir, e.nombre) + this._tipAttr(tip(e.nombre, [['Trámites finalizados (acumulado)']])) + '>' +
                    '<span class="adt_fd__stage-name"><span class="adt_fd__step"><i class="fa fa-check" aria-hidden="true"></i></span>' + esc(e.nombre) + '</span>' +
                    '<span class="adt_fd__stage-value">' + fmt(e.valor) + '</span></div>';
            }
            var ok = e.valor - e.en_riesgo;
            var t = tip(e.nombre, [
                ['Motos ahora', fmt(e.valor)],
                ['Tiempo típico (mediana)', dias(e.edad_mediana) + ' d'],
                ['La que más lleva', dias(e.edad_max) + ' d'],
                [e.umbral_fuente ? 'Umbral (' + e.umbral_fuente + ')' : 'Umbral', e.umbral_fuente ? dias(e.umbral) + ' d' : 'falta historia'],
                ['En riesgo', fmt(e.en_riesgo)],
            ]);
            return '<div class="adt_fd__stage"' + this._open(e.abrir, e.nombre) + this._tipAttr(t) + '>' +
                '<span class="adt_fd__stage-name"><span class="adt_fd__step is-' + tone + '">' + paso + '</span>' + esc(e.nombre) + '</span>' +
                '<span class="adt_fd__stage-value">' + fmt(e.valor) + '</span>' +
                '<span class="adt_fd__stage-bar">' +
                (ok ? '<span class="is-' + tone + '" style="width:' + (ok / max * 100) + '%"></span>' : '') +
                (e.en_riesgo ? '<span class="is-risk" style="width:' + (e.en_riesgo / max * 100) + '%"></span>' : '') + '</span>' +
                '<span class="adt_fd__stage-foot">' +
                (e.valor ? '<span class="adt_fd__muted"><i class="fa fa-clock-o" aria-hidden="true"></i> ' + dias(e.edad_mediana) + ' d</span>' : '<span class="adt_fd__muted">vacía</span>') +
                (e.en_riesgo ? '<span class="adt_fd__sev is-serious"' + this._open(e.abrir_riesgo, e.nombre + ' · en riesgo') + '><i class="fa fa-exclamation-triangle" aria-hidden="true"></i>' + fmt(e.en_riesgo) + '</span>' : '') +
                '</span></div>';
        },

        _wipHtml: function (wip) {
            var self = this;
            var flujo = function (titulo, etapas, tone) {
                var max = _.max(_.pluck(etapas.filter(function (e) { return !e.cerrado; }), 'valor')) || 1;
                return '<div class="adt_fd__flow"><h3><i class="adt_fd__dot is-' + tone + '"></i>' + esc(titulo) + '</h3><div class="adt_fd__stages">' +
                    etapas.map(function (e, i) { return self._etapaHtml(e, max, i + 1, tone); })
                        .join('<i class="fa fa-chevron-right adt_fd__arrow" aria-hidden="true"></i>') +
                    '</div></div>';
            };
            return '<div class="adt_fd__legend"><span><i class="adt_fd__dot is-risk"></i>En riesgo: supera su SLA o el tiempo del 85% de los casos</span></div>' +
                flujo('Logística', wip.logistica, 'blue') + flujo('Trámite de placa', wip.placa, 'violet');
        },

        _tiemposHtml: function (filas) {
            var self = this;
            var max = _.max(_.map(filas, function (f) { return f.p85 || 0; })) || 1;
            var grupo = null;
            var rows = filas.map(function (f) {
                var head = '';
                if (f.grupo !== grupo) {
                    grupo = f.grupo;
                    head = '<div class="adt_fd__range-group">' + esc(grupo) + '</div>';
                }
                var t = tip(f.nombre, [['Mediana', dias(f.mediana) + ' d'], ['85% de los casos', dias(f.p85) + ' d'], ['Casos', fmt(f.n)]]);
                var barra = f.n ? '<span class="adt_fd__range-bar" style="width:' + ((f.p85 || 0) / max * 100) + '%"></span>' +
                    '<span class="adt_fd__range-dot" style="left:' + ((f.mediana || 0) / max * 100) + '%"></span>' : '';
                return head + '<div class="adt_fd__range"' + self._tipAttr(t) + '>' +
                    '<span class="adt_fd__range-label">' + esc(f.nombre) + '</span>' +
                    '<span class="adt_fd__range-track">' + barra + '</span>' +
                    '<span class="adt_fd__range-val">' + (f.n ? dias(f.mediana) + ' d' : '—') + '</span></div>';
            }).join('');
            return '<div class="adt_fd__legend"><span><i class="adt_fd__range-dot is-legend"></i>mediana</span>' +
                '<span><i class="adt_fd__range-bar is-legend"></i>hasta el 85% de los casos</span></div>' + rows;
        },

        _talleresHtml: function (talleres) {
            var self = this;
            if (!talleres.length) {
                return '<div class="adt_fd__empty">No hay talleres de fibra configurados.</div>';
            }
            var max = _.max(_.pluck(talleres, 'valor')) || 1;
            return '<div class="adt_fd__hbars">' + talleres.map(function (t) {
                var ok = t.valor - t.en_riesgo;
                var t2 = tip(t.nombre, [['En fibra ahora', fmt(t.valor)], ['En riesgo', fmt(t.en_riesgo)],
                    ['La que más lleva', dias(t.edad_max) + ' d'], ['Típico histórico', dias(t.historia.mediana) + ' d'],
                    ['85% histórico', dias(t.historia.p85) + ' d']]);
                return '<div class="adt_fd__hbar adt_fd__hbar--taller"' + self._open(t.abrir, t.nombre) + self._tipAttr(t2) + '>' +
                    '<span class="adt_fd__hbar-label">' + esc(t.nombre) + '</span>' +
                    '<span class="adt_fd__track">' +
                    (ok ? '<span class="adt_fd__seg is-violet" style="width:' + (ok / max * 100) + '%"></span>' : '') +
                    (t.en_riesgo ? '<span class="adt_fd__seg is-risk" style="width:' + (t.en_riesgo / max * 100) + '%"></span>' : '') +
                    '</span><span class="adt_fd__hbar-val">' + fmt(t.valor) + '</span>' +
                    '<span class="adt_fd__muted adt_fd__hbar-extra"><i class="fa fa-clock-o" aria-hidden="true"></i> ' + dias(t.historia.mediana) + ' d</span></div>';
            }).join('') + '</div><div class="adt_fd__legend adt_fd__legend--foot"><span><i class="adt_fd__dot is-violet"></i>En fibra</span>' +
                '<span><i class="adt_fd__dot is-risk"></i>En riesgo</span><span><i class="fa fa-clock-o" aria-hidden="true"></i> típico histórico</span></div>';
        },

        _ritmoHtml: function (ritmo) {
            // Small multiples con la misma escala para que las series sean comparables.
            var max = _.max(_.flatten(_.pluck(ritmo.series, 'valores'))) || 1;
            var multiples = ritmo.series.map(function (s, n) {
                var total = _.reduce(s.valores, function (a, b) { return a + b; }, 0);
                var cols = s.valores.map(function (v, i) {
                    return '<div class="adt_fd__col"' + ' data-tip="' + esc(tip('Semana del ' + ritmo.semanas[i], [[s.label, fmt(v)]])) + '">' +
                        '<div class="adt_fd__col-bar" style="height:' + (v / max * 100) + '%;background:' + SERIES[n] + '"></div></div>';
                }).join('');
                return '<div class="adt_fd__multiple"><div class="adt_fd__multiple-head"><span><i class="adt_fd__dot" style="background:' + SERIES[n] + '"></i>' +
                    esc(s.label) + '</span><b>' + fmt(total) + '</b></div><div class="adt_fd__cols">' + cols + '</div>' +
                    '<div class="adt_fd__cols-axis"><span>' + esc(ritmo.semanas[0]) + '</span><span>' + esc(ritmo.semanas[ritmo.semanas.length - 1]) + '</span></div></div>';
            }).join('');
            var b = ritmo.balance;
            var diff = b.entradas - b.asignadas;
            var pill = diff > 0 ? {cls: 'is-up', icon: 'fa-arrow-up', txt: 'Stock subiendo +' + fmt(diff)}
                : diff < 0 ? {cls: 'is-down', icon: 'fa-arrow-down', txt: 'Stock bajando ' + fmt(diff)}
                : {cls: 'is-flat', icon: 'fa-arrows-h', txt: 'Stock estable'};
            return '<div class="adt_fd__balance"><span class="adt_fd__pill ' + pill.cls + '"><i class="fa ' + pill.icon + '" aria-hidden="true"></i>' + pill.txt + '</span>' +
                '<span class="adt_fd__muted">últimas ' + b.semanas + ' semanas · entraron ' + fmt(b.entradas) + ' · asignadas ' + fmt(b.asignadas) + '</span></div>' +
                '<div class="adt_fd__multiples">' + multiples + '</div>';
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

        _onOpen: function (ev) {
            ev.stopPropagation();
            this._hideTip();
            var target = this._opens[parseInt(ev.currentTarget.getAttribute('data-open'), 10)];
            if (!target) {
                return;
            }
            this.do_action({
                type: 'ir.actions.act_window',
                name: target.name,
                res_model: target.model,
                views: (this.data.vistas || {})[target.model] || [[false, 'list'], [false, 'form']],
                domain: [['id', 'in', target.ids]],
                target: 'current',
            });
        },

        _onTipShow: function (ev) {
            this._ref('tooltip').html(ev.currentTarget.getAttribute('data-tip')).addClass('is-visible');
            this._onTipMove(ev);
        },

        _onTipMove: function (ev) {
            var tipEl = this._ref('tooltip')[0];
            var x = ev.clientX + 14;
            var y = ev.clientY + 14;
            if (x + tipEl.offsetWidth > window.innerWidth - 8) { x = ev.clientX - tipEl.offsetWidth - 14; }
            if (y + tipEl.offsetHeight > window.innerHeight - 8) { y = ev.clientY - tipEl.offsetHeight - 14; }
            tipEl.style.left = x + 'px';
            tipEl.style.top = y + 'px';
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
