odoo.define('adt_expedientes.Dashboard', function (require) {
    'use strict';

    /**
     * Dashboard de Expedientes: cuántos ingresan, en qué etapa están, cuántos se aprueban o rechazan,
     * qué documentos se observan más y qué expedientes llevan más tiempo sin resolverse.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;

    // Color por estado (estado + texto, nunca solo color).
    var ESTILO = {
        por_revisar: 'info',
        incompleto_expediente: 'warn',
        incompleto_fase_final: 'warn',
        aprobado_sin_desembolso: 'info-soft',
        completo: 'ok',
        rechazado: 'bad',
    };
    var PERIODOS = [
        {key: 'mes', label: 'Este mes'},
        {key: '3m', label: 'Últimos 3 meses'},
        {key: '12m', label: 'Últimos 12 meses'},
        {key: 'todo', label: 'Todo'},
    ];
    var TABS = [
        {key: 'en_proceso', label: 'En proceso'},
        {key: 'aprobado_sin_desembolso', label: 'Aprobados sin desembolso'},
        {key: 'rechazado', label: 'Rechazados'},
    ];
    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var DIAS_ESTANCADO = 7;
    var PAGINA = 15;

    function pct(part, total) {
        return total > 0 ? (part / total) * 100 : 0;
    }

    var ExpedientesDashboard = AbstractAction.extend({
        template: 'adt_expedientes.Dashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-periodo]': '_onPeriodo',
            'change [data-ref="asesora"]': '_onAsesora',
            'click [data-asesora]': '_onAsesoraFila',
            'click [data-tab]': '_onTab',
            'click [data-page]': '_onPage',
            'click [data-expediente]': '_onAbrir',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.periodo = '3m';
            this.asesora = null;
            this.tab = 'en_proceso';
            this.page = 0;
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
            return this._rpc({model: 'adt.expediente.dashboard', method: 'get_dashboard_data', args: []}).then(function (data) {
                self.data = data;
                self.hoy = moment(data.hoy);
                self.grupo = {};
                self.etiqueta = {};
                data.estados.forEach(function (e) { self.grupo[e.key] = e.grupo; self.etiqueta[e.key] = e.label; });
                data.expedientes.forEach(function (x) {
                    x.dias = x.fecha ? self.hoy.diff(moment(x.fecha), 'days') : 0;
                });
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _desde: function () {
            switch (this.periodo) {
                case 'mes': return this.hoy.clone().startOf('month').format('YYYY-MM-DD');
                case '3m': return this.hoy.clone().subtract(3, 'months').format('YYYY-MM-DD');
                case '12m': return this.hoy.clone().subtract(12, 'months').format('YYYY-MM-DD');
                default: return null;
            }
        },

        // Expedientes del periodo (por fecha de ingreso) y de la asesora elegida.
        _filtrados: function (sinPeriodo) {
            var desde = sinPeriodo ? null : this._desde();
            var asesora = this.asesora;
            return this.data.expedientes.filter(function (x) {
                return (asesora === null || x.asesora_id === asesora) && (!desde || (x.fecha && x.fecha >= desde));
            });
        },

        _badge: function (estado) {
            return '<span class="adt_exp__badge adt_exp__badge--' + ESTILO[estado] + '"><i></i>' + esc(this.etiqueta[estado] || estado) + '</span>';
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var self = this;
            var periodo = _.findWhere(PERIODOS, {key: this.periodo}).label.toLowerCase();
            var asesora = this.asesora === null ? 'todas las asesoras' :
                (_.findWhere(this.data.expedientes, {asesora_id: this.asesora}) || {}).asesora;
            this._ref('subtitle').text('Al ' + this.hoy.format('DD/MM/YYYY') + ' · ingresados ' + periodo + ' · ' + asesora);
            this._ref('periodos').html(PERIODOS.map(function (p) {
                return '<button type="button" class="adt_exp__chip' + (p.key === self.periodo ? ' is-active' : '') + '" data-periodo="' + p.key + '">' + p.label + '</button>';
            }).join(''));
            var asesoras = _.sortBy(_.uniq(this.data.expedientes.map(function (x) { return x.asesora_id + '|' + x.asesora; })), function (a) { return a.split('|')[1]; });
            this._ref('asesora').html('<option value="">Todas</option>' + asesoras.map(function (a) {
                var p = a.split('|');
                return '<option value="' + p[0] + '"' + (String(self.asesora) === p[0] ? ' selected' : '') + '>' + esc(p[1]) + '</option>';
            }).join(''));

            var xs = this._filtrados();
            if (!this.data.expedientes.length) {
                this._ref('body').html('<div class="adt_exp__empty">Aún no hay expedientes registrados.</div>');
                return;
            }
            this._ref('body').html(
                this._kpisHtml(xs) +
                '<div class="adt_exp__grid">' +
                this._card('¿En qué etapa están?', 'Expedientes ingresados en el periodo, por estado actual', this._etapasHtml(xs)) +
                this._card('Ingresos por mes', 'Últimos 12 meses, según cómo terminaron', this._mesesHtml()) +
                '</div>' +
                this._card('Desempeño por asesora', 'Toca una asesora para ver solo sus expedientes', this._asesorasHtml(xs), 'wide') +
                '<div class="adt_exp__grid">' +
                this._card('Documentos más observados', 'Documentos marcados como rechazados en los expedientes del periodo', this._documentosHtml(xs)) +
                this._card('Últimos rechazos', 'Motivo registrado al rechazar', this._rechazosHtml(xs)) +
                '</div>' +
                '<section class="adt_exp__card" data-ref="lista"></section>'
            );
            this._renderLista();
        },

        _card: function (title, subtitle, content, size) {
            return '<section class="adt_exp__card' + (size === 'wide' ? ' adt_exp__card--wide' : '') + '">' +
                '<header class="adt_exp__card-head"><h2>' + esc(title) + '</h2>' + (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</header>' +
                content + '</section>';
        },

        _kpisHtml: function (xs) {
            var self = this;
            var porGrupo = _.countBy(xs, function (x) { return self.grupo[x.estado]; });
            var enProceso = xs.filter(function (x) { return self.grupo[x.estado] === 'en_proceso'; });
            var estancados = enProceso.filter(function (x) { return x.dias > DIAS_ESTANCADO; }).length;
            var sinDesembolso = xs.filter(function (x) { return x.estado === 'aprobado_sin_desembolso'; }).length;
            var aprobados = porGrupo.aprobado || 0;
            var rechazados = porGrupo.rechazado || 0;
            var tasa = pct(aprobados, aprobados + rechazados);
            var kpis = [
                {cls: 'info', label: 'Ingresados', value: xs.length, sub: 'en el periodo'},
                {cls: 'warn', label: 'En proceso', value: enProceso.length, sub: estancados ? estancados + ' con más de ' + DIAS_ESTANCADO + ' días' : 'ninguno estancado', tab: 'en_proceso'},
                {cls: 'ok', label: 'Aprobados', value: aprobados, sub: sinDesembolso ? sinDesembolso + ' aún sin desembolso' : 'todos desembolsados', tab: 'aprobado_sin_desembolso'},
                {cls: 'bad', label: 'Rechazados', value: rechazados, sub: Math.round(pct(rechazados, xs.length)) + '% de los ingresados', tab: 'rechazado'},
                {cls: 'ok', label: 'Tasa de aprobación', value: Math.round(tasa) + '%', sub: 'de los ya resueltos (aprobados o rechazados)'},
            ];
            return '<div class="adt_exp__kpis">' + kpis.map(function (k) {
                return '<' + (k.tab ? 'button type="button" data-tab="' + k.tab + '"' : 'div') + ' class="adt_exp__kpi adt_exp__kpi--' + k.cls + '">' +
                    '<span class="adt_exp__kpi-label">' + esc(k.label) + '</span>' +
                    '<span class="adt_exp__kpi-value">' + esc(String(k.value)) + '</span>' +
                    '<span class="adt_exp__kpi-sub">' + esc(k.sub) + '</span></' + (k.tab ? 'button' : 'div') + '>';
            }).join('') + '</div>';
        },

        _etapasHtml: function (xs) {
            var self = this;
            var conteo = _.countBy(xs, 'estado');
            var max = _.max(_.values(conteo)) || 1;
            return '<div class="adt_exp__hbars">' + this.data.estados.map(function (e) {
                var n = conteo[e.key] || 0;
                var tip = '<b>' + esc(e.label) + '</b><br/>' + n + ' expedientes (' + Math.round(pct(n, xs.length)) + '%)';
                return '<div class="adt_exp__hbar" data-tip="' + esc(tip) + '">' +
                    '<span class="adt_exp__hbar-label">' + self._badge(e.key) + '</span>' +
                    '<span class="adt_exp__track"><span class="adt_exp__fill--' + ESTILO[e.key] + '" style="width:' + (n / max * 100) + '%"></span></span>' +
                    '<span class="adt_exp__hbar-val">' + n + '</span></div>';
            }).join('') + '</div>';
        },

        _mesesHtml: function () {
            var self = this;
            var xs = this._filtrados(true);
            var meses = [];
            for (var i = 11; i >= 0; i--) { meses.push(this.hoy.clone().subtract(i, 'months').format('YYYY-MM')); }
            var datos = {};
            meses.forEach(function (m) { datos[m] = {aprobado: 0, en_proceso: 0, rechazado: 0}; });
            xs.forEach(function (x) {
                var d = x.fecha && datos[x.fecha.slice(0, 7)];
                if (d) { d[self.grupo[x.estado]] += 1; }
            });
            var max = _.max(meses.map(function (m) { var d = datos[m]; return d.aprobado + d.en_proceso + d.rechazado; })) || 1;
            var orden = [['aprobado', 'ok', 'Aprobados'], ['en_proceso', 'warn', 'En proceso'], ['rechazado', 'bad', 'Rechazados']];
            var cols = meses.map(function (m) {
                var d = datos[m];
                var total = d.aprobado + d.en_proceso + d.rechazado;
                var h = total / max * 85;
                var etiqueta = MESES[parseInt(m.slice(5), 10) - 1] + ' ' + m.slice(2, 4);
                var tip = '<b>' + etiqueta + '</b>' + orden.map(function (o) { return '<br/>' + o[2] + ': ' + d[o[0]]; }).join('');
                return '<div class="adt_exp__col" data-tip="' + esc(tip) + '"><div class="adt_exp__col-plot">' +
                    (total ? '<span class="adt_exp__col-val" style="bottom:calc(' + h + '% + 4px)">' + total + '</span>' : '') +
                    '<span class="adt_exp__stack" style="height:' + h + '%">' + orden.map(function (o) {
                        return d[o[0]] ? '<span class="adt_exp__fill--' + o[1] + '" style="flex-grow:' + d[o[0]] + '"></span>' : '';
                    }).join('') + '</span></div><span class="adt_exp__col-label">' + etiqueta + '</span></div>';
            }).join('');
            return '<div class="adt_exp__legend">' + orden.map(function (o) {
                return '<span><i class="adt_exp__fill--' + o[1] + '"></i>' + o[2] + '</span>';
            }).join('') + '</div><div class="adt_exp__cols">' + cols + '</div>';
        },

        _asesorasHtml: function (xs) {
            var self = this;
            var filas = _.map(_.groupBy(xs, 'asesora_id'), function (rows) {
                var g = _.countBy(rows, function (x) { return self.grupo[x.estado]; });
                var aprob = g.aprobado || 0;
                var rech = g.rechazado || 0;
                return {id: rows[0].asesora_id, nombre: rows[0].asesora, total: rows.length, proceso: g.en_proceso || 0,
                    aprobados: aprob, rechazados: rech, tasa: pct(aprob, aprob + rech), resueltos: aprob + rech};
            }).sort(function (a, b) { return b.total - a.total; });
            if (!filas.length) { return '<p class="adt_exp__muted">Sin expedientes en el periodo.</p>'; }
            return '<div class="adt_exp__table-wrap"><table class="adt_exp__table adt_exp__table--click"><thead><tr>' +
                '<th>Asesora</th><th class="num">Ingresados</th><th class="num">En proceso</th><th class="num">Aprobados</th>' +
                '<th class="num">Rechazados</th><th>Tasa de aprobación</th></tr></thead><tbody>' +
                filas.map(function (f) {
                    return '<tr data-asesora="' + f.id + '"' + (self.asesora === f.id ? ' class="is-active"' : '') + '><td><b>' + esc(f.nombre) + '</b></td>' +
                        '<td class="num">' + f.total + '</td><td class="num">' + f.proceso + '</td><td class="num">' + f.aprobados + '</td>' +
                        '<td class="num">' + f.rechazados + '</td><td>' + (f.resueltos ?
                            '<span class="adt_exp__meter"><span class="adt_exp__fill--ok" style="width:' + f.tasa + '%"></span></span><span class="adt_exp__pct">' + Math.round(f.tasa) + '%</span>' :
                            '<span class="adt_exp__muted">sin resueltos</span>') + '</td></tr>';
                }).join('') + '</tbody></table></div>';
        },

        _documentosHtml: function (xs) {
            var conteo = {};
            xs.forEach(function (x) { x.observados.forEach(function (d) { conteo[d] = (conteo[d] || 0) + 1; }); });
            var filas = _.map(conteo, function (n, d) { return {d: d, n: n}; }).sort(function (a, b) { return b.n - a.n; }).slice(0, 8);
            if (!filas.length) { return '<p class="adt_exp__ok">✓ Ningún documento observado en el periodo.</p>'; }
            var max = filas[0].n;
            return '<div class="adt_exp__hbars">' + filas.map(function (f) {
                return '<div class="adt_exp__hbar" data-tip="' + esc('<b>' + f.d + '</b><br/>Observado en ' + f.n + ' expedientes (' + Math.round(pct(f.n, xs.length)) + '%)') + '">' +
                    '<span class="adt_exp__hbar-label">' + esc(f.d) + '</span>' +
                    '<span class="adt_exp__track"><span class="adt_exp__fill--warn" style="width:' + (f.n / max * 100) + '%"></span></span>' +
                    '<span class="adt_exp__hbar-val">' + f.n + '</span></div>';
            }).join('') + '</div><p class="adt_exp__note">Los documentos que más se observan son los que conviene explicar mejor al cliente desde el inicio.</p>';
        },

        _rechazosHtml: function (xs) {
            var rechazados = xs.filter(function (x) { return x.estado === 'rechazado'; })
                .sort(function (a, b) { return (b.fecha_rechazo || b.fecha || '').localeCompare(a.fecha_rechazo || a.fecha || ''); }).slice(0, 8);
            if (!rechazados.length) { return '<p class="adt_exp__ok">✓ Sin rechazos en el periodo.</p>'; }
            return '<ul class="adt_exp__rechazos">' + rechazados.map(function (x) {
                return '<li data-expediente="' + x.id + '"><div><b>' + esc(x.cliente) + '</b><span class="adt_exp__muted"> · ' + esc(x.asesora) + ' · ' +
                    moment(x.fecha_rechazo || x.fecha).format('DD/MM/YYYY') + '</span></div>' +
                    '<p>' + esc(x.motivo_rechazo || 'Sin motivo registrado') + '</p></li>';
            }).join('') + '</ul>';
        },

        _renderLista: function () {
            var self = this;
            var $box = this._ref('lista');
            if (!$box.length) { return; }
            var xs = this._filtrados(true);
            var enTab = function (x, tab) {
                return tab === 'en_proceso' ? self.grupo[x.estado] === 'en_proceso' : x.estado === tab;
            };
            var filas = xs.filter(function (x) { return enTab(x, self.tab); }).sort(function (a, b) { return b.dias - a.dias; });
            var paginas = Math.max(1, Math.ceil(filas.length / PAGINA));
            this.page = Math.min(this.page, paginas - 1);
            var inicio = this.page * PAGINA;
            var tabs = TABS.map(function (t) {
                var n = xs.filter(function (x) { return enTab(x, t.key); }).length;
                return '<button type="button" class="adt_exp__tab' + (t.key === self.tab ? ' is-active' : '') + '" data-tab="' + t.key + '">' +
                    esc(t.label) + ' <span>' + n + '</span></button>';
            }).join('');
            var body = filas.slice(inicio, inicio + PAGINA).map(function (x) {
                return '<tr data-expediente="' + x.id + '"><td><b>' + esc(x.cliente) + '</b></td><td>' + esc(x.asesora) + '</td>' +
                    '<td>' + self._badge(x.estado) + '</td><td>' + esc(x.vehiculo) + '</td>' +
                    '<td class="num' + (x.dias > DIAS_ESTANCADO && self.tab !== 'rechazado' ? ' adt_exp__late' : '') + '">' + x.dias + '</td>' +
                    '<td class="adt_exp__obs">' + esc(self.tab === 'rechazado' ? (x.motivo_rechazo || '—') : (x.observados.join(', ') || '—')) + '</td></tr>';
            }).join('') || '<tr><td colspan="6" class="adt_exp__muted">No hay expedientes en esta lista.</td></tr>';
            $box.html('<header class="adt_exp__card-head"><h2>Expedientes para atender</h2>' +
                '<p>Todos los periodos · ordenados por días desde que ingresaron · toca uno para abrirlo</p></header>' +
                '<nav class="adt_exp__tabs">' + tabs + '</nav>' +
                '<div class="adt_exp__table-wrap"><table class="adt_exp__table adt_exp__table--click"><thead><tr>' +
                '<th>Cliente</th><th>Asesora</th><th>Estado</th><th>Vehículo</th><th class="num">Días</th><th>' +
                (this.tab === 'rechazado' ? 'Motivo del rechazo' : 'Documentos observados') + '</th></tr></thead><tbody>' + body + '</tbody></table></div>' +
                (paginas > 1 ? '<footer class="adt_exp__pager"><span>' + (inicio + 1) + '–' + Math.min(filas.length, inicio + PAGINA) + ' de ' + filas.length + '</span>' +
                    '<button type="button" class="adt_exp__btn adt_exp__btn--ghost" data-page="-1"' + (this.page === 0 ? ' disabled' : '') + '>‹ Anterior</button>' +
                    '<button type="button" class="adt_exp__btn adt_exp__btn--ghost" data-page="1"' + (this.page >= paginas - 1 ? ' disabled' : '') + '>Siguiente ›</button></footer>' : ''));
        },

        // ------------------------------------------------------------------ eventos
        _onRefresh: function () {
            var self = this;
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true).text('Actualizando…');
            this._load().then(function () { self._render(); }).finally(function () {
                $btn.prop('disabled', false).text('Actualizar');
            });
        },

        _onPeriodo: function (ev) {
            this.periodo = ev.currentTarget.getAttribute('data-periodo');
            this._hideTip();
            this._render();
        },

        _onAsesora: function (ev) {
            this.asesora = ev.currentTarget.value ? parseInt(ev.currentTarget.value, 10) : null;
            this.page = 0;
            this._render();
        },

        _onAsesoraFila: function (ev) {
            var id = parseInt(ev.currentTarget.getAttribute('data-asesora'), 10);
            this.asesora = this.asesora === id ? null : id;
            this.page = 0;
            this._render();
        },

        _onTab: function (ev) {
            this.tab = ev.currentTarget.getAttribute('data-tab');
            this.page = 0;
            this._renderLista();
            if (!$(ev.currentTarget).hasClass('adt_exp__tab')) {
                this.$('.adt_exp__scroll').animate({scrollTop: this._ref('lista')[0].offsetTop - 16}, 250);
            }
        },

        _onPage: function (ev) {
            this.page += parseInt(ev.currentTarget.getAttribute('data-page'), 10);
            this._renderLista();
        },

        _onAbrir: function (ev) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'adt.expediente',
                res_id: parseInt(ev.currentTarget.getAttribute('data-expediente'), 10),
                views: [[false, 'form']],
                target: 'current',
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
            this._hideTip();
        },

        _hideTip: function () {
            this._ref('tooltip').removeClass('is-visible');
        },
    });

    core.action_registry.add('adt_expedientes_dashboard', ExpedientesDashboard);

    return ExpedientesDashboard;
});
