odoo.define('adt_dashboard_ceo.Dashboard', function (require) {
    'use strict';

    /**
     * Dashboard Ejecutivo: el estado de la compañía en una pantalla.
     * Indicadores clave de cada área, alertas para decidir, tendencias de 12 meses
     * y acceso directo al dashboard de cada área.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;
    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var ICONOS = {bad: '!', warn: '!', info: 'i', ok: '✓'};
    var AREAS = {
        cobranza: 'Cobranza', financieras: 'Financieras', clientes: 'Clientes',
        flota: 'Flota', expedientes: 'Expedientes', ventas: 'Ventas',
    };
    var ESTADOS_COBRANZA = [
        {key: 'al_dia', label: 'Al día', cls: 'ok'},
        {key: 'deuda', label: 'Con deuda', cls: 'warn'},
        {key: 'orden', label: 'Orden de captura', cls: 'serious'},
        {key: 'capturada', label: 'Capturada', cls: 'bad'},
    ];
    var SEGMENTOS = [
        {key: 'apto', cls: 'ok'}, {key: 'evaluar', cls: 'warn'}, {key: 'pagando_bien', cls: 'info'},
        {key: 'pagando_alerta', cls: 'info-soft'}, {key: 'no_prestar', cls: 'bad'},
    ];

    function pct(part, total) {
        return total > 0 ? (part / total) * 100 : 0;
    }

    function mesLabel(key) {
        return MESES[parseInt(key.slice(5), 10) - 1] + ' ' + key.slice(2, 4);
    }

    var CeoDashboard = AbstractAction.extend({
        template: 'adt_dashboard_ceo.Dashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-area]': '_onArea',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () { self._render(); });
        },

        _load: function () {
            var self = this;
            return this._rpc({model: 'adt.ceo.dashboard', method: 'get_dashboard_data', args: []}).then(function (data) {
                self.data = data;
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

        _noDisponible: function () {
            return '<p class="adt_fin__muted">Información no disponible por ahora.</p>';
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var d = this.data;
            this._ref('subtitle').text('Al ' + moment(d.hoy).format('DD/MM/YYYY') + ' · ventas, cobranza, financieras, clientes, expedientes y flota');
            this._ref('body').html(
                this._kpisHtml() +
                this._card('Alertas para decidir', 'Lo que conviene atender primero', this._alertasHtml(), null, 'wide') +
                '<div class="adt_cob__grid2">' +
                this._card('Ventas por mes', 'Créditos desembolsados en los últimos 12 meses', this._ventasHtml(), null) +
                this._card('Recaudación por mes', 'Cobrado frente a lo que vencía cada mes', this._recaudoHtml(), 'cobranza') +
                this._card('Financieras', 'Ganancia de ADT y deuda con las financieras', this._financierasHtml(), 'financieras') +
                this._card('Cartera de cobranza', 'Estado de las cuentas en curso', this._cobranzaHtml(), 'cobranza') +
                this._card('Clientes', 'A quién volver a prestar y a quién no', this._clientesHtml(), 'clientes') +
                this._card('Expedientes', 'Solicitudes en camino a convertirse en ventas', this._expedientesHtml(), 'expedientes') +
                '</div>' +
                this._card('Flota y stock', 'Motos disponibles para vender', this._flotaHtml(), 'flota', 'wide')
            );
        },

        _card: function (title, subtitle, content, area, size) {
            return '<section class="adt_fin__card' + (size === 'wide' ? ' adt_ceo__wide' : '') + '">' +
                '<header class="adt_fin__card-head adt_ceo__card-head"><div><h2>' + esc(title) + '</h2>' +
                (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</div>' +
                (area ? '<button type="button" class="adt_ceo__link" data-area="' + area + '">Abrir dashboard ›</button>' : '') +
                '</header>' + content + '</section>';
        },

        _kpisHtml: function () {
            var d = this.data;
            var v = d.ventas;
            var cob = d.cobranza;
            var fin = d.financieras;
            var flo = d.flota;
            var exp = d.expedientes;
            var cli = d.clientes;
            var nivelPar = cob && (cob.par30 >= 10 ? 'bad' : cob.par30 >= 5 ? 'warn' : 'ok');
            var nivelCobro = cob && cob.vencia_mes_hasta_hoy > 0 && (cob.tasa_cobro_mes < 85 ? 'bad' : cob.tasa_cobro_mes < 95 ? 'warn' : 'ok');
            var nivelStock = flo && flo.cobertura_meses !== undefined &&
                (flo.cobertura_meses < 1 ? 'bad' : flo.cobertura_meses > 4 ? 'warn' : 'ok');
            var tiles = [
                {label: 'Ventas del mes', value: v.mes_n + (v.mes_n === 1 ? ' crédito' : ' créditos'),
                    sub: this._money(v.mes_monto) + ' · promedio ' + v.promedio_mensual.toLocaleString('es-PE') + '/mes'},
                cob && {area: 'cobranza', nivel: nivelCobro, label: 'Recaudado este mes', value: this._money(cob.cobrado_mes),
                    sub: cob.vencia_mes_hasta_hoy > 0 ? Math.round(cob.tasa_cobro_mes) + '% de lo que vencía' : 'aún no vencen cuotas'},
                cob && {area: 'cobranza', nivel: nivelPar, label: 'Morosidad +30 días', value: cob.par30.toLocaleString('es-PE') + '%',
                    sub: this._money(cob.riesgo) + ' de saldo en riesgo'},
                fin && {area: 'financieras', nivel: 'ok', label: 'Ganancia lograda', value: this._money(fin.ganancia_actual),
                    sub: 'de ' + this._money(fin.ganancia_esperada) + ' al final'},
                fin && {area: 'financieras', label: 'Deuda con financieras', value: this._money(fin.pendiente),
                    sub: 'este mes ' + this._money(fin.pagar_mes)},
                flo && {area: 'flota', nivel: nivelStock, label: 'Motos en stock', value: flo.stock.toLocaleString('es-PE'),
                    sub: Math.round(100 - flo.sin_placa_pct) + '% con placa' +
                        (flo.cobertura_meses !== undefined ? ' · cubre ' + flo.cobertura_meses + ' meses' : '')},
                exp && {area: 'expedientes', label: 'Expedientes en proceso', value: exp.en_proceso.toLocaleString('es-PE'),
                    sub: exp.sin_desembolso + ' aprobados sin desembolso'},
                cli && {area: 'clientes', nivel: cli.aptos ? 'ok' : null, label: 'Clientes para volver a prestar', value: cli.aptos.toLocaleString('es-PE'),
                    sub: 'oportunidad ' + this._money(cli.oportunidad, true)},
            ].filter(Boolean);
            return '<div class="adt_ceo__kpis">' + tiles.map(function (t) {
                var tag = t.area ? 'button type="button" data-area="' + t.area + '"' : 'div';
                return '<' + tag + ' class="adt_ceo__kpi' + (t.nivel ? ' adt_ceo__kpi--' + t.nivel : '') + '">' +
                    '<span class="adt_ceo__kpi-label">' + (t.nivel && t.nivel !== 'ok' ? '<i class="adt_cob__icon adt_cob__icon--' + t.nivel + '" aria-hidden="true">!</i>' : '') +
                    esc(t.label) + '</span>' +
                    '<span class="adt_ceo__kpi-value">' + esc(t.value) + '</span>' +
                    '<span class="adt_ceo__kpi-sub">' + esc(t.sub) + '</span></' + (t.area ? 'button' : 'div') + '>';
            }).join('') + '</div>';
        },

        _alertasHtml: function () {
            var alertas = this.data.alertas;
            if (!alertas.length) {
                return '<p class="adt_cob__ok"><i class="adt_cob__icon adt_cob__icon--ok">✓</i>Sin alertas por ahora.</p>';
            }
            var acciones = this.data.acciones;
            return '<ul class="adt_ceo__alertas">' + alertas.map(function (a) {
                return '<li class="adt_ceo__alerta adt_ceo__alerta--' + a.nivel + '">' +
                    '<i class="adt_cli__icon adt_cli__icon--' + a.nivel + ' adt_ceo__alerta-icon" aria-hidden="true">' + ICONOS[a.nivel] + '</i>' +
                    '<div><span class="adt_ceo__alerta-area">' + esc(AREAS[a.area] || '') + '</span>' +
                    '<b>' + esc(a.titulo) + '</b><p>' + esc(a.texto) + '</p></div>' +
                    (acciones[a.area] ? '<button type="button" class="adt_ceo__link" data-area="' + a.area + '">Ver ›</button>' : '<span></span>') +
                    '</li>';
            }).join('') + '</ul>';
        },

        _columnas: function (serie, valor, etiqueta, tip, color) {
            var max = _.max(serie.map(valor)) || 1;
            return '<div class="adt_cob__cols">' + serie.map(function (s) {
                var val = valor(s);
                var h = val / max * 85;
                return '<div class="adt_cob__col" data-tip="' + esc(tip(s)) + '"><div class="adt_cob__col-plot adt_ceo__plot">' +
                    (val ? '<span class="adt_cob__col-val" style="bottom:calc(' + h + '% + 4px)">' + esc(etiqueta(s)) + '</span>' : '') +
                    '<span class="adt_cob__col-bar ' + color + '" style="height:' + h + '%"></span></div>' +
                    '<span class="adt_cob__col-label">' + mesLabel(s.mes) + '</span></div>';
            }).join('') + '</div>';
        },

        _ventasHtml: function () {
            var self = this;
            var v = this.data.ventas;
            return this._columnas(v.serie, function (s) { return s.n; }, function (s) { return s.n; }, function (s) {
                return '<b>' + mesLabel(s.mes) + '</b><br/>' + s.n + ' créditos<br/>' + self._money(s.monto) + ' en motos';
            }, 'adt_cli__fill--info') +
                '<p class="adt_fin__note">Promedio de los 3 meses anteriores: <b>' + v.promedio_mensual.toLocaleString('es-PE') + '</b> créditos al mes.' +
                (v.mes_n ? ' Este mes van <b>' + v.mes_n + '</b> (proyección ~' + Math.round(v.proyeccion_mes) + ').' : '') + '</p>';
        },

        _recaudoHtml: function () {
            var self = this;
            var cob = this.data.cobranza;
            if (!cob) { return this._noDisponible(); }
            var max = _.max(cob.serie.map(function (s) { return Math.max(s.cobrado, s.programado); })) || 1;
            var cols = cob.serie.map(function (s) {
                var tasa = pct(s.cobrado, s.vencido_a_hoy);
                var tip = '<b>' + mesLabel(s.mes) + '</b><br/>Cobrado: ' + self._money(s.cobrado) + '<br/>Vencía en el mes: ' + self._money(s.programado) +
                    (s.vencido_a_hoy ? '<br/>' + Math.round(tasa) + '% de lo vencido' + (s.vencido_a_hoy !== s.programado ? ' hasta hoy' : '') : '');
                return '<div class="adt_fin__month" data-tip="' + esc(tip) + '"><div class="adt_fin__month-plot adt_ceo__month-plot">' +
                    '<span class="adt_fin__bar adt_cob__prog" style="height:' + (s.programado / max * 100) + '%"></span>' +
                    '<span class="adt_fin__bar is-in" style="height:' + (s.cobrado / max * 100) + '%"></span></div>' +
                    '<span class="adt_fin__month-label">' + mesLabel(s.mes) + '</span>' +
                    '<span class="adt_cob__rate">' + (s.vencido_a_hoy ? Math.round(tasa) + '%' : '—') + '</span></div>';
            }).join('');
            return '<div class="adt_fin__legend"><span><i class="adt_fin__dot is-in"></i>Cobrado</span>' +
                '<span><i class="adt_fin__dot adt_cob__prog"></i>Vencía</span>' +
                '<span class="adt_fin__muted">% = cobrado sobre lo vencido (en el mes actual, hasta hoy)</span></div>' +
                '<div class="adt_fin__calendar adt_ceo__calendar">' + cols + '</div>';
        },

        _financierasHtml: function () {
            var fin = this.data.financieras;
            if (!fin) { return this._noDisponible(); }
            var fila = function (titulo, cls, hecho, total, texto) {
                return '<div class="adt_ceo__meter-row"><div class="adt_ceo__meter-head"><span>' + esc(titulo) + '</span><b>' + texto + '</b></div>' +
                    '<span class="adt_fin__meter"><span class="' + cls + '" style="width:' + Math.min(100, pct(hecho, total)) + '%"></span></span></div>';
            };
            return fila('Ganancia lograda', 'is-gain', fin.ganancia_actual, fin.ganancia_esperada,
                this._money(fin.ganancia_actual) + ' de ' + this._money(fin.ganancia_esperada)) +
                fila('Pagado a financieras', 'is-out', fin.pagado, fin.total, this._money(fin.pagado) + ' de ' + this._money(fin.total)) +
                '<div class="adt_cob__facts adt_ceo__facts">' +
                '<div><span>Pagar este mes</span><b>' + this._money(fin.pagar_mes) + '</b></div>' +
                '<div><span>Pagar el próximo mes</span><b>' + this._money(fin.pagar_siguiente) + '</b></div>' +
                '<div><span>ADT adelantando</span><b' + (fin.adelantado > 0.5 ? ' class="adt_fin__loss-text"' : '') + '>' + this._money(fin.adelantado) + '</b>' +
                '<em>' + fin.desfase_cuentas + ' cuentas en rojo</em></div></div>';
        },

        _barraEstados: function (items, total) {
            return '<div class="adt_cob__bar">' + items.filter(function (i) { return i.n; }).map(function (i) {
                return '<span class="adt_cob__seg ' + i.fill + '" style="flex-grow:' + i.n + '" data-tip="' +
                    esc('<b>' + i.label + '</b><br/>' + i.n + ' (' + Math.round(pct(i.n, total)) + '%)') + '"></span>';
            }).join('') + '</div><div class="adt_ceo__legend">' + items.map(function (i) {
                return '<span><i class="adt_fin__dot ' + i.fill + '"></i>' + esc(i.label) + ' <b>' + i.n + '</b></span>';
            }).join('') + '</div>';
        },

        _cobranzaHtml: function () {
            var cob = this.data.cobranza;
            if (!cob) { return this._noDisponible(); }
            var items = ESTADOS_COBRANZA.map(function (e) {
                return {label: e.label, n: cob.estados[e.key] || 0, fill: 'adt_cob__seg--' + e.cls};
            });
            return this._barraEstados(items, cob.cuentas) +
                '<div class="adt_cob__facts adt_ceo__facts">' +
                '<div><span>Saldo por cobrar</span><b>' + this._money(cob.saldo) + '</b></div>' +
                '<div><span>Vencido sin pagar</span><b>' + this._money(cob.vencido) + '</b></div>' +
                '<div><span>Recaudado hoy</span><b>' + this._money(cob.cobrado_hoy) + '</b></div></div>';
        },

        _clientesHtml: function () {
            var cli = this.data.clientes;
            if (!cli) { return this._noDisponible(); }
            var items = SEGMENTOS.map(function (s) {
                return {label: cli.etiquetas[s.key], n: cli.segmentos[s.key] || 0, fill: 'adt_cli__fill--' + s.cls};
            });
            return this._barraEstados(items, cli.total) +
                '<div class="adt_cob__facts adt_ceo__facts">' +
                '<div><span>Terminaron de pagar</span><b>' + cli.terminaron + '</b><em>' + cli.recompra + '% volvió a sacar</em></div>' +
                '<div><span>Terminan en 90 días</span><b>' + cli.pronto + '</b><em>buenos pagadores</em></div>' +
                '<div><span>Llamar hoy</span><b>' + cli.llamar_hoy + '</b><em>seguimientos vencidos</em></div></div>';
        },

        _expedientesHtml: function () {
            var exp = this.data.expedientes;
            if (!exp) { return this._noDisponible(); }
            var orden = [['por_revisar', 'adt_cli__fill--info'], ['incompleto_expediente', 'adt_cli__fill--warn'],
                ['incompleto_fase_final', 'adt_cli__fill--warn'], ['aprobado_sin_desembolso', 'adt_cli__fill--ok']];
            var max = _.max(orden.map(function (o) { return exp.pipeline[o[0]] || 0; })) || 1;
            return '<div class="adt_cob__hbars">' + orden.map(function (o) {
                var n = exp.pipeline[o[0]] || 0;
                return '<div class="adt_cob__hbar"><span class="adt_cob__hbar-label">' + esc(exp.etiquetas[o[0]] || o[0]) + '</span>' +
                    '<span class="adt_cob__track"><span class="' + o[1] + '" style="width:' + (n / max * 100) + '%"></span></span>' +
                    '<span class="adt_cob__hbar-val">' + n + '</span></div>';
            }).join('') + '</div>' +
                '<div class="adt_cob__facts adt_ceo__facts">' +
                '<div><span>Ingresados (30 días)</span><b>' + exp.ingresados_30 + '</b></div>' +
                '<div><span>Tasa de aprobación (90 días)</span><b>' + Math.round(exp.tasa_aprobacion_90) + '%</b></div>' +
                '<div><span>Estancados +7 días</span><b' + (exp.estancados ? ' class="adt_fin__loss-text"' : '') + '>' + exp.estancados + '</b></div></div>';
        },

        _flotaHtml: function () {
            var flo = this.data.flota;
            if (!flo) { return this._noDisponible(); }
            var max = flo.modelos.length ? flo.modelos[0].n : 1;
            var placas = flo.placas;
            var items = [
                {label: 'Placa lista', n: placas.lista || 0, fill: 'adt_cli__fill--ok'},
                {label: 'En trámite', n: placas.tramite || 0, fill: 'adt_cli__fill--warn'},
                {label: 'Sin placa', n: placas.sin_placa || 0, fill: 'adt_cob__seg--serious'},
            ];
            return '<div class="adt_ceo__flota"><div>' +
                '<p class="adt_ceo__mini-title">Stock por estado de placa</p>' + this._barraEstados(items, flo.stock) +
                '<div class="adt_cob__facts adt_ceo__facts">' +
                '<div><span>Flota total</span><b>' + flo.total + '</b></div>' +
                '<div><span>Stock sin dueño</span><b>' + flo.stock + '</b></div>' +
                (flo.cobertura_meses !== undefined ? '<div><span>Cobertura</span><b>' + flo.cobertura_meses + ' meses</b><em>al ritmo de ventas actual</em></div>' : '') +
                '</div></div><div><p class="adt_ceo__mini-title">Modelos con más stock</p><div class="adt_cob__hbars">' +
                flo.modelos.map(function (m) {
                    return '<div class="adt_cob__hbar"><span class="adt_cob__hbar-label">' + esc(m.modelo) + '</span>' +
                        '<span class="adt_cob__track"><span class="adt_cli__fill--info" style="width:' + (m.n / max * 100) + '%"></span></span>' +
                        '<span class="adt_cob__hbar-val">' + m.n + '</span></div>';
                }).join('') + '</div></div></div>';
        },

        // ------------------------------------------------------------------ eventos
        _onArea: function (ev) {
            var xmlid = this.data.acciones[ev.currentTarget.getAttribute('data-area')];
            if (xmlid) {
                this._hideTip();
                this.do_action(xmlid);
            }
        },

        _onRefresh: function () {
            var self = this;
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true).text('Actualizando…');
            this._load().then(function () { self._render(); }).finally(function () {
                $btn.prop('disabled', false).text('Actualizar');
            });
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
            this._ref('tooltip').removeClass('is-visible');
        },

        _hideTip: function () {
            this._ref('tooltip').removeClass('is-visible');
        },
    });

    core.action_registry.add('adt_ceo_dashboard', CeoDashboard);

    return CeoDashboard;
});
