odoo.define('adt_comercial.ClientesDashboard', function (require) {
    'use strict';

    /**
     * Dashboard de Clientes: a quién volver a prestar, a quién seguir y a quién no prestar.
     * Puntaje de comportamiento (0-100) calculado con el historial de pagos, capturas y papeletas,
     * más el seguimiento comercial que registra el equipo (adt.cliente.seguimiento).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;

    // Segmentos: color de estado + ícono + texto (nunca solo color).
    var SEGMENTOS = [
        {key: 'apto', cls: 'ok', icon: '✓'},
        {key: 'evaluar', cls: 'warn', icon: '?'},
        {key: 'pagando_bien', cls: 'info', icon: '↻'},
        {key: 'pagando_alerta', cls: 'info-soft', icon: '!'},
        {key: 'no_prestar', cls: 'bad', icon: '✕'},
    ];

    var TABS = [
        {key: 'apto', label: 'Listos para nuevo préstamo', sort: {key: 'puntaje', dir: -1}},
        {key: 'pronto', label: 'Terminan pronto', sort: {key: 'termina', dir: 1}},
        {key: 'llamar', label: 'Llamar hoy', sort: {key: 'proximo', dir: 1}},
        {key: 'evaluar', label: 'Evaluar', sort: {key: 'puntaje', dir: -1}},
        {key: 'no_prestar', label: 'No prestar', sort: {key: 'puntaje', dir: 1}},
        {key: 'todos', label: 'Todos', sort: {key: 'nombre', dir: 1}},
    ];

    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var PAGINA = 20;
    var MESES_PIPELINE = 6;

    function pct(part, total) {
        return total > 0 ? (part / total) * 100 : 0;
    }

    function normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim();
    }

    function fecha(f) {
        return f ? moment(f).format('DD/MM/YYYY') : '—';
    }

    var ClientesDashboard = AbstractAction.extend({
        template: 'adt_comercial.ClientesDashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="seguimientos"]': '_onVerSeguimientos',
            'click [data-action="cerrar"]': '_cerrarPanel',
            'click [data-action="guardar"]': '_onGuardar',
            'click [data-action="historial"]': '_onHistorial',
            'click [data-action="export"]': '_onExport',
            'click [data-financiera]': '_onFinanciera',
            'click [data-tab]': '_onTab',
            'click [data-sort]': '_onSort',
            'click [data-page]': '_onPage',
            'click [data-cliente]': '_onAbrirCliente',
            'click [data-cuenta]': '_onAbrirCuenta',
            'change [data-ref="clasificacion"]': '_onClasificacion',
            'input [data-ref="buscar"]': '_onBuscar',
            'keydown': '_onKeydown',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.financiera = null;
            this.tab = 'apto';
            this.sort = TABS[0].sort;
            this.busqueda = '';
            this.page = 0;
            this.clienteAbierto = null;
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
                model: 'adt.comercial.clientes.dashboard',
                method: 'get_dashboard_data',
                args: [],
            }).then(function (data) {
                self.data = data;
                self.hoy = moment(data.hoy);
                data.clientes.forEach(function (c) {
                    c._buscar = normalizar([c.nombre, c.documento, c.telefono, c.financiera,
                        _.pluck(c.creditos, 'referencia').join(' '), _.pluck(c.creditos, 'moto').join(' ')].join(' '));
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

        _seg: function (key) {
            return _.extend({label: this.data.segmentos[key]}, _.findWhere(SEGMENTOS, {key: key}));
        },

        _badge: function (key) {
            var s = this._seg(key);
            return '<span class="adt_cli__badge adt_cli__badge--' + s.cls + '"><i class="adt_cli__icon adt_cli__icon--' + s.cls +
                '" aria-hidden="true">' + s.icon + '</i>' + esc(s.label) + '</span>';
        },

        _zona: function (puntaje) {
            return puntaje >= this.data.umbral_apto ? 'ok' : puntaje >= this.data.umbral_minimo ? 'warn' : 'bad';
        },

        _puntajeHtml: function (puntaje) {
            return '<span class="adt_cli__score"><span class="adt_cli__score-track"><span class="adt_cli__fill--' + this._zona(puntaje) +
                '" style="width:' + puntaje + '%"></span></span><b>' + puntaje + '</b></span>';
        },

        // ------------------------------------------------------------------ datos filtrados
        _clientes: function () {
            var fid = this.financiera;
            return this.data.clientes.filter(function (c) { return fid === null || c.financiera_id === fid; });
        },

        _limitePronto: function () {
            return this.hoy.clone().add(this.data.dias_proximos, 'days').format('YYYY-MM-DD');
        },

        _enTab: function (c, tab) {
            var hoy = this.data.hoy;
            var seg = c.seguimiento;
            switch (tab) {
                case 'pronto': return c.segmento === 'pagando_bien' && c.termina && c.termina <= this._limitePronto();
                case 'llamar': return seg && seg.proximo_contacto && seg.proximo_contacto <= hoy &&
                    !_.contains(['no_interesado', 'nuevo_prestamo'], seg.estado) && c.segmento !== 'no_prestar';
                case 'todos': return true;
                default: return c.segmento === tab;
            }
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var nombre = this.financiera === null ? 'todas las financieras' :
                (_.findWhere(this.data.financieras, {id: this.financiera}) || {}).nombre;
            this._ref('subtitle').text('Al ' + this.hoy.format('DD/MM/YYYY') + ' · ' + nombre +
                ' · a quién volver a prestar y a quién no');
            this._renderFinancieras();
            var clientes = this._clientes();
            if (!clientes.length) {
                this._ref('body').html('<div class="adt_fin__empty">No hay clientes con historial de créditos para este filtro.</div>');
                return;
            }
            this._ref('body').html(
                this._heroHtml(clientes) +
                this._card('¿Cómo está nuestra cartera de clientes?', clientes.length + ' clientes con historial · toca un segmento para ver la lista',
                    this._segmentosHtml(clientes)) +
                '<div class="adt_cob__grid2">' +
                this._card('Embudo de recompra', 'De los que terminaron de pagar, ¿cuántos volvieron a sacar?', this._embudoHtml(clientes)) +
                this._card('¿Por qué no prestarles?', 'Motivos de los clientes marcados como No prestar', this._motivosHtml(clientes)) +
                '</div>' +
                '<div class="adt_cob__grid2">' +
                this._card('Próximos a terminar de pagar', 'Clientes con crédito en curso, por mes en que terminan', this._pipelineHtml(clientes)) +
                this._card('Calidad de la cartera', 'Cuántos clientes hay en cada rango de puntaje', this._distribucionHtml(clientes)) +
                '</div>' +
                '<section class="adt_fin__card adt_cob__gestion" data-ref="lista"></section>' +
                this._comoSeLeeHtml()
            );
            this._renderLista();
        },

        _renderFinancieras: function () {
            var self = this;
            var chips = [{id: null, nombre: 'Todas las financieras'}].concat(this.data.financieras);
            this._ref('financieras').html(chips.map(function (f) {
                var activo = self.financiera === f.id;
                return '<button type="button" class="adt_fin__chip' + (activo ? ' is-active' : '') + '" data-financiera="' +
                    (f.id === null ? 'todas' : f.id) + '" aria-pressed="' + activo + '">' + esc(f.nombre) + '</button>';
            }).join(''));
        },

        _card: function (title, subtitle, content) {
            return '<section class="adt_fin__card">' +
                '<header class="adt_fin__card-head"><h2>' + esc(title) + '</h2>' +
                (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</header>' + content + '</section>';
        },

        // Cuatro respuestas estratégicas.
        _heroHtml: function (clientes) {
            var self = this;
            var aptos = clientes.filter(function (c) { return c.segmento === 'apto'; });
            var terminaron = clientes.filter(function (c) { return c.n_terminados > 0; });
            var volvieron = terminaron.filter(function (c) { return c.recompra; });
            var pronto = clientes.filter(function (c) { return self._enTab(c, 'pronto'); });
            var noPrestar = clientes.filter(function (c) { return c.segmento === 'no_prestar'; });
            var recuperadas = noPrestar.filter(function (c) { return _.contains(c.bloqueos, 'Moto recuperada'); }).length;
            var oportunidad = aptos.reduce(function (a, c) { return a + (c.ultimo_monto || 0); }, 0);
            var items = [
                {cls: 'ok', tab: 'apto', titulo: 'Listos para un nuevo préstamo', valor: aptos.length,
                    texto: 'Terminaron de pagar y fueron buenos pagadores. Oportunidad: <b>' + this._money(oportunidad) +
                        '</b> (valor de su última moto).'},
                {cls: 'info', tab: 'todos', titulo: 'Terminaron de pagar', valor: terminaron.length,
                    texto: '<b>' + volvieron.length + '</b> ya volvieron a sacar otro préstamo (' +
                        Math.round(pct(volvieron.length, terminaron.length)) + '% de recompra).'},
                {cls: 'info', tab: 'pronto', titulo: 'Terminan en los próximos ' + this.data.dias_proximos + ' días', valor: pronto.length,
                    texto: 'Buenos pagadores que pronto podrían recibir una nueva oferta.'},
                {cls: 'bad', tab: 'no_prestar', titulo: 'No prestar', valor: noPrestar.length,
                    texto: recuperadas ? '<b>' + recuperadas + '</b> con moto recuperada.' : 'Por historial de atrasos, capturas o decisión del equipo.'},
            ];
            return '<div class="adt_cli__hero">' + items.map(function (i) {
                return '<button type="button" class="adt_cli__hero-item adt_cli__hero-item--' + i.cls + '" data-tab="' + i.tab + '">' +
                    '<span class="adt_fin__question">' + esc(i.titulo) + '</span>' +
                    '<span class="adt_fin__big">' + i.valor.toLocaleString('es-PE') + '</span>' +
                    '<span class="adt_fin__sentence">' + i.texto + '</span></button>';
            }).join('') + '</div>';
        },

        _segmentosHtml: function (clientes) {
            var self = this;
            var total = clientes.length;
            var conteo = _.countBy(clientes, 'segmento');
            var barra = SEGMENTOS.filter(function (s) { return conteo[s.key]; }).map(function (s) {
                var seg = self._seg(s.key);
                var tip = '<b>' + seg.label + '</b><br/>' + conteo[s.key] + ' clientes (' + Math.round(pct(conteo[s.key], total)) + '%)';
                return '<span class="adt_cob__seg adt_cli__fill--' + s.cls + '" style="flex-grow:' + conteo[s.key] + '" data-tab="' +
                    (s.key.indexOf('pagando') === 0 ? 'todos' : s.key) + '" data-tip="' + esc(tip) + '"></span>';
            }).join('');
            var leyenda = SEGMENTOS.map(function (s) {
                var seg = self._seg(s.key);
                return '<div class="adt_cli__seg-item">' + self._badge(s.key) +
                    '<b>' + (conteo[s.key] || 0) + '</b><span class="adt_fin__muted">' + Math.round(pct(conteo[s.key] || 0, total)) + '%</span></div>';
            }).join('');
            return '<div class="adt_cob__bar adt_cli__bar">' + barra + '</div><div class="adt_cli__seg-legend">' + leyenda + '</div>';
        },

        _embudoHtml: function (clientes) {
            var base = clientes.filter(function (c) { return c.n_terminados > 0 && c.segmento !== 'no_prestar'; });
            var estado = function (c) { return c.seguimiento && c.seguimiento.estado; };
            var pasos = [
                {label: 'Terminaron de pagar (sin bloqueo)', n: base.length},
                {label: 'Contactados', n: base.filter(function (c) { return c.recompra || (estado(c) && estado(c) !== 'por_contactar'); }).length},
                {label: 'Interesados', n: base.filter(function (c) { return c.recompra || _.contains(['interesado', 'nuevo_prestamo'], estado(c)); }).length},
                {label: 'Volvieron a sacar', n: base.filter(function (c) { return c.recompra || estado(c) === 'nuevo_prestamo'; }).length},
            ];
            if (!base.length) {
                return '<p class="adt_fin__muted">Aún no hay clientes que hayan terminado de pagar.</p>';
            }
            var filas = pasos.map(function (p, i) {
                var ancho = pct(p.n, base.length);
                return '<div class="adt_cli__funnel-row">' +
                    '<span class="adt_cli__funnel-label">' + esc(p.label) + '</span>' +
                    '<span class="adt_cli__funnel-track"><span style="width:' + Math.max(ancho, p.n ? 2 : 0) + '%;opacity:' + (1 - i * 0.18) + '"></span></span>' +
                    '<span class="adt_cli__funnel-val"><b>' + p.n + '</b> <span class="adt_fin__muted">' + Math.round(ancho) + '%</span></span></div>';
            }).join('');
            var sinContactar = base.length - pasos[1].n;
            return '<div class="adt_cli__funnel">' + filas + '</div>' +
                (sinContactar ? '<p class="adt_fin__note"><b>' + sinContactar + '</b> clientes que terminaron de pagar todavía no han sido contactados.</p>' : '');
        },

        _motivosHtml: function (clientes) {
            var bloqueados = clientes.filter(function (c) { return c.segmento === 'no_prestar'; });
            if (!bloqueados.length) {
                return '<p class="adt_cob__ok"><i class="adt_cob__icon adt_cob__icon--ok">✓</i>No hay clientes marcados como No prestar.</p>';
            }
            // Agrupa los motivos por su tipo (quita los detalles entre paréntesis o después de ":").
            var tipo = function (m) { return m.replace(/\s*\(.*\)$/, '').replace(/:.*$/, ''); };
            var conteo = {};
            bloqueados.forEach(function (c) {
                _.uniq(c.bloqueos.map(tipo)).forEach(function (m) { conteo[m] = (conteo[m] || 0) + 1; });
            });
            var filas = _.map(conteo, function (n, m) { return {m: m, n: n}; }).sort(function (a, b) { return b.n - a.n; });
            var max = _.max(_.pluck(filas, 'n')) || 1;
            return '<div class="adt_cob__hbars">' + filas.map(function (f) {
                return '<div class="adt_cob__hbar" data-tip="' + esc('<b>' + f.m + '</b><br/>' + f.n + ' clientes') + '">' +
                    '<span class="adt_cob__hbar-label">' + esc(f.m) + '</span>' +
                    '<span class="adt_cob__track"><span class="adt_cli__fill--bad" style="width:' + (f.n / max * 100) + '%"></span></span>' +
                    '<span class="adt_cob__hbar-val">' + f.n + '</span></div>';
            }).join('') + '</div><p class="adt_fin__note">Un cliente puede tener más de un motivo.</p>';
        },

        _pipelineHtml: function (clientes) {
            var self = this;
            var meses = [];
            for (var i = 0; i < MESES_PIPELINE; i++) {
                meses.push(this.hoy.clone().add(i, 'months').format('YYYY-MM'));
            }
            var datos = {};
            meses.forEach(function (m) { datos[m] = {bien: 0, alerta: 0}; });
            clientes.forEach(function (c) {
                if (!c.termina || !_.contains(['pagando_bien', 'pagando_alerta'], c.segmento)) { return; }
                var d = datos[c.termina.slice(0, 7)];
                if (d) { d[c.segmento === 'pagando_bien' ? 'bien' : 'alerta'] += 1; }
            });
            var max = _.max(meses.map(function (m) { return datos[m].bien + datos[m].alerta; })) || 1;
            var cols = meses.map(function (m) {
                var d = datos[m];
                var total = d.bien + d.alerta;
                var h = total / max * 85;
                var etiqueta = MESES[parseInt(m.slice(5), 10) - 1] + ' ' + m.slice(2, 4);
                var tip = '<b>Terminan en ' + etiqueta + '</b><br/>Buen pagador: ' + d.bien + '<br/>Con alertas: ' + d.alerta;
                return '<div class="adt_cob__col" data-tip="' + esc(tip) + '">' +
                    '<div class="adt_cob__col-plot">' +
                    '<span class="adt_cob__col-val" style="bottom:calc(' + h + '% + 4px)">' + total + '</span>' +
                    '<span class="adt_cli__stack" style="height:' + h + '%">' +
                    (d.bien ? '<span class="adt_cli__fill--info" style="flex-grow:' + d.bien + '"></span>' : '') +
                    (d.alerta ? '<span class="adt_cli__fill--info-soft" style="flex-grow:' + d.alerta + '"></span>' : '') +
                    '</span></div><span class="adt_cob__col-label">' + esc(etiqueta) + '</span></div>';
            }).join('');
            return '<div class="adt_fin__legend"><span><i class="adt_fin__dot adt_cli__fill--info"></i>Buen pagador</span>' +
                '<span><i class="adt_fin__dot adt_cli__fill--info-soft"></i>Con alertas</span></div>' +
                '<div class="adt_cob__cols">' + cols + '</div>' +
                '<p class="adt_fin__note">Contactar a los buenos pagadores antes de que terminen ayuda a que vuelvan a sacar con nosotros.</p>';
        },

        _distribucionHtml: function (clientes) {
            var self = this;
            var rangos = [];
            for (var i = 0; i < 10; i++) { rangos.push({min: i * 10, max: i === 9 ? 100 : i * 10 + 9, n: 0}); }
            clientes.forEach(function (c) { rangos[Math.min(9, Math.floor(c.puntaje / 10))].n += 1; });
            var max = _.max(_.pluck(rangos, 'n')) || 1;
            var cols = rangos.map(function (r) {
                var h = r.n / max * 85;
                var zona = self._zona(r.min);
                var tip = '<b>Puntaje ' + r.min + '–' + r.max + '</b><br/>' + r.n + ' clientes';
                return '<div class="adt_cob__col" data-tip="' + esc(tip) + '">' +
                    '<div class="adt_cob__col-plot">' + (r.n ? '<span class="adt_cob__col-val" style="bottom:calc(' + h + '% + 4px)">' + r.n + '</span>' : '') +
                    '<span class="adt_cob__col-bar adt_cli__fill--' + zona + '" style="height:' + h + '%"></span></div>' +
                    '<span class="adt_cob__col-label">' + r.min + '</span></div>';
            }).join('');
            var promedio = clientes.length ? Math.round(clientes.reduce(function (a, c) { return a + c.puntaje; }, 0) / clientes.length) : 0;
            return '<div class="adt_fin__legend">' +
                '<span><i class="adt_fin__dot adt_cli__fill--bad"></i>Menos de ' + this.data.umbral_minimo + ': no prestar</span>' +
                '<span><i class="adt_fin__dot adt_cli__fill--warn"></i>' + this.data.umbral_minimo + '–' + (this.data.umbral_apto - 1) + ': evaluar</span>' +
                '<span><i class="adt_fin__dot adt_cli__fill--ok"></i>' + this.data.umbral_apto + ' o más: buen pagador</span></div>' +
                '<div class="adt_cob__cols adt_cli__hist">' + cols + '</div>' +
                '<p class="adt_fin__note">Puntaje promedio de la cartera: <b>' + promedio + '/100</b>.</p>';
        },

        // ------------------------------------------------------------------ lista
        _columnas: function () {
            var cols = [
                {key: 'nombre', label: 'Cliente'},
                {key: 'telefono', label: 'Teléfono'},
                {key: 'puntaje', label: 'Puntaje', num: true},
                {key: 'creditos', label: 'Créditos', num: true},
                {key: 'puntualidad', label: 'Pagó a tiempo', num: true},
                {key: 'capturas', label: 'Capturas', num: true},
                {key: 'financiera', label: 'Financiera'},
            ];
            if (this.tab === 'pronto') {
                cols.push({key: 'termina', label: 'Termina'});
            } else if (this.tab === 'no_prestar') {
                cols.push({key: 'motivos', label: 'Motivo'});
            } else if (this.tab === 'todos') {
                cols.push({key: 'segmento', label: 'Segmento'});
            } else {
                cols.push({key: 'termino', label: 'Terminó de pagar'});
            }
            if (this.tab !== 'no_prestar') {
                cols.push({key: 'proximo', label: 'Seguimiento'});
            }
            return cols;
        },

        _valorOrden: function (c, key) {
            switch (key) {
                case 'creditos': return c.n_creditos;
                case 'proximo': return (c.seguimiento && c.seguimiento.proximo_contacto) || '9999';
                case 'termina': return c.termina || '9999';
                case 'termino': return c.termino || '';
                case 'puntualidad': return c.puntualidad === null ? -1 : c.puntualidad;
                case 'motivos': return c.bloqueos.join(' ');
                default: return c[key];
            }
        },

        _filas: function () {
            var self = this;
            var q = normalizar(this.busqueda);
            var filas = this._clientes().filter(function (c) {
                return self._enTab(c, self.tab) && (!q || c._buscar.indexOf(q) !== -1);
            });
            var key = this.sort.key;
            var dir = this.sort.dir;
            return filas.sort(function (a, b) {
                var va = self._valorOrden(a, key);
                var vb = self._valorOrden(b, key);
                var r = typeof va === 'number' ? va - vb : String(va || '').localeCompare(String(vb || ''));
                return r * dir || a.nombre.localeCompare(b.nombre);
            });
        },

        _celda: function (c, col) {
            var seg = c.seguimiento;
            switch (col.key) {
                case 'nombre':
                    return '<td><b>' + esc(c.nombre) + '</b>' + (c.documento ? '<span class="adt_fin__doc">' + esc(c.documento) + '</span>' : '') + '</td>';
                case 'puntaje': return '<td>' + this._puntajeHtml(c.puntaje) + '</td>';
                case 'creditos':
                    return '<td class="num">' + c.n_terminados + ' de ' + c.n_creditos + (c.recompra ? ' <span class="adt_cli__tag">recompra</span>' : '') + '</td>';
                case 'puntualidad': return '<td class="num">' + (c.puntualidad === null ? '—' : c.puntualidad + '%') + '</td>';
                case 'capturas': return '<td class="num' + (c.capturas ? ' adt_fin__loss-text' : '') + '">' + c.capturas + '</td>';
                case 'termina': return '<td>' + fecha(c.termina) + '</td>';
                case 'termino': return '<td>' + fecha(c.termino) + '</td>';
                case 'segmento': return '<td>' + this._badge(c.segmento) + '</td>';
                case 'motivos': return '<td class="adt_cli__motivos">' + esc(c.bloqueos.join(' · ')) + '</td>';
                case 'proximo':
                    if (!seg) { return '<td class="adt_fin__muted">Sin seguimiento</td>'; }
                    var cerrado = _.contains(['no_interesado', 'nuevo_prestamo'], seg.estado);
                    var vencido = !cerrado && seg.proximo_contacto && seg.proximo_contacto <= this.data.hoy;
                    return '<td>' + esc(this.data.estados_seguimiento[seg.estado] || '') +
                        (seg.proximo_contacto && !cerrado ? '<span class="adt_fin__doc' + (vencido ? ' adt_fin__loss-text' : '') + '">llamar ' + fecha(seg.proximo_contacto) + '</span>' : '') + '</td>';
                default:
                    return '<td' + (col.num ? ' class="num"' : '') + '>' + esc(c[col.key] || '—') + '</td>';
            }
        },

        _renderLista: function () {
            var self = this;
            var $box = this._ref('lista');
            if (!$box.length) { return; }
            var clientes = this._clientes();
            var filas = this._filas();
            var cols = this._columnas();
            var paginas = Math.max(1, Math.ceil(filas.length / PAGINA));
            this.page = Math.min(this.page, paginas - 1);
            var inicio = this.page * PAGINA;

            var tabs = TABS.map(function (t) {
                var n = clientes.filter(function (c) { return self._enTab(c, t.key); }).length;
                return '<button type="button" role="tab" class="adt_cob__tab' + (self.tab === t.key ? ' is-active' : '') + '" data-tab="' + t.key +
                    '" aria-selected="' + (self.tab === t.key) + '">' + esc(t.label) + ' <span class="adt_cob__tab-n">' + n + '</span></button>';
            }).join('');
            var head = cols.map(function (c) {
                var flecha = self.sort.key === c.key ? (self.sort.dir > 0 ? ' ▲' : ' ▼') : '';
                return '<th class="is-sortable' + (c.num ? ' num' : '') + '" data-sort="' + c.key + '">' + esc(c.label) + flecha + '</th>';
            }).join('');
            var body = filas.slice(inicio, inicio + PAGINA).map(function (c) {
                return '<tr data-cliente="' + c.id + '">' + cols.map(function (col) { return self._celda(c, col); }).join('') + '</tr>';
            }).join('') || '<tr><td colspan="' + cols.length + '" class="adt_fin__muted">' +
                (this.busqueda ? 'Ningún cliente coincide con la búsqueda.' : 'No hay clientes en esta lista.') + '</td></tr>';
            var pager = '<footer class="adt_fin__pager"><span>' + (filas.length ? (inicio + 1) + '–' + Math.min(filas.length, inicio + PAGINA) + ' de ' : '') +
                filas.length + ' clientes</span>' +
                (paginas > 1 ? '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-page="-1"' + (this.page === 0 ? ' disabled' : '') + '>‹ Anterior</button>' +
                    '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-page="1"' + (this.page >= paginas - 1 ? ' disabled' : '') + '>Siguiente ›</button>' : '') +
                '</footer>';

            var buscarFoco = document.activeElement && document.activeElement.getAttribute('data-ref') === 'buscar';
            $box.html('<header class="adt_fin__card-head adt_cob__gestion-head"><div><h2>Clientes</h2>' +
                '<p>Toca un cliente para ver su historial y registrar el seguimiento</p></div>' +
                '<div class="adt_cob__tools"><input type="search" class="adt_cob__search" data-ref="buscar" value="' + esc(this.busqueda) +
                '" placeholder="Buscar cliente, DNI, teléfono, placa o cuenta…"/>' +
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

        // ------------------------------------------------------------------ ficha del cliente (panel lateral)
        _renderPanel: function () {
            var self = this;
            var c = _.findWhere(this.data.clientes, {id: this.clienteAbierto});
            if (!c) { this._cerrarPanel(); return; }
            var seg = c.seguimiento || {estado: 'por_contactar', clasificacion_manual: '', motivo_manual: '', proximo_contacto: null, notas: ''};
            var factores = c.factores.length ? '<ul class="adt_cli__factores">' + c.factores.map(function (f) {
                return '<li><span>' + esc(f.texto) + '</span><b>' + f.puntos + '</b></li>';
            }).join('') + '</ul>' : '<p class="adt_cob__ok"><i class="adt_cob__icon adt_cob__icon--ok">✓</i>Sin descuentos: siempre pagó a tiempo.</p>';
            var bloqueos = c.bloqueos.length ? '<div class="adt_fin__verdict adt_fin__verdict--bad"><i class="adt_fin__status adt_fin__status--bad" aria-hidden="true">✕</i>' +
                '<span><b>No prestar:</b> ' + esc(c.bloqueos.join(' · ')) + '</span></div>' : '';
            var creditos = c.creditos.slice().reverse().map(function (k) {
                return '<tr data-cuenta="' + k.id + '"><td><b>' + esc(k.referencia) + '</b><span class="adt_fin__doc">' + esc(k.moto) + '</span></td>' +
                    '<td>' + esc(k.estado_texto) + (k.estado === 'en_curso' && k.restantes ? '<span class="adt_fin__doc">' + k.restantes + ' cuotas por pagar</span>' : '') + '</td>' +
                    '<td>' + fecha(k.desembolso) + '<span class="adt_fin__doc">a ' + fecha(k.fin) + '</span></td>' +
                    '<td class="num">' + (k.puntualidad === null ? '—' : k.puntualidad + '%') + (k.capturas ? '<span class="adt_fin__doc adt_fin__loss-text">' + k.capturas + ' captura(s)</span>' : '') + '</td></tr>';
            }).join('');
            var opciones = function (map, actual, vacio) {
                return (vacio ? '<option value="">' + esc(vacio) + '</option>' : '') + _.map(map, function (label, key) {
                    return '<option value="' + key + '"' + (key === actual ? ' selected' : '') + '>' + esc(label) + '</option>';
                }).join('');
            };
            this._ref('panel').html(
                '<header class="adt_cli__panel-head"><div><h2>' + esc(c.nombre) + '</h2><p>' +
                esc(_.compact([c.documento, c.telefono, c.financiera]).join(' · ')) + '</p>' + this._badge(c.segmento) + '</div>' +
                '<button type="button" class="adt_cli__close" data-action="cerrar" aria-label="Cerrar">×</button></header>' +
                '<section class="adt_cli__panel-sec"><h3>Puntaje de comportamiento</h3>' +
                '<div class="adt_cli__big-score"><b>' + c.puntaje + '</b><span>/100</span>' + this._puntajeHtml(c.puntaje) + '</div>' +
                '<p class="adt_fin__muted">Empieza en 100 y descuenta por atrasos, capturas, papeletas y deudas.</p>' + factores + bloqueos + '</section>' +
                '<section class="adt_cli__panel-sec"><h3>Sus créditos</h3><table class="adt_fin__table adt_fin__table--click"><thead><tr>' +
                '<th>Cuenta</th><th>Estado</th><th>Desde</th><th class="num">A tiempo</th></tr></thead><tbody>' + creditos + '</tbody></table></section>' +
                '<section class="adt_cli__panel-sec adt_cli__form"><h3>Seguimiento</h3>' +
                '<label><span>Estado</span><select data-ref="estado">' + opciones(this.data.estados_seguimiento, seg.estado) + '</select></label>' +
                '<label><span>Próximo contacto</span><input type="date" data-ref="proximo" value="' + esc(seg.proximo_contacto || '') + '"/></label>' +
                '<label><span>Clasificación</span><select data-ref="clasificacion">' +
                opciones(this.data.clasificaciones, seg.clasificacion_manual, 'Automática (según puntaje)') + '</select></label>' +
                '<label data-ref="motivo-wrap"' + (seg.clasificacion_manual ? '' : ' hidden') + '><span>Motivo</span>' +
                '<input type="text" data-ref="motivo" value="' + esc(seg.motivo_manual || '') + '" placeholder="Ej.: conflictivo, amenazó al cobrador…"/></label>' +
                '<label><span>Notas</span><textarea data-ref="notas" rows="3" placeholder="Qué se habló, qué moto le interesa…">' + esc(seg.notas || '') + '</textarea></label>' +
                '<p class="adt_cli__form-error" data-ref="error" hidden></p>' +
                '<div class="adt_cli__form-actions">' +
                (c.seguimiento ? '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-action="historial">Ver historial de cambios</button>' : '<span></span>') +
                '<button type="button" class="adt_fin__btn" data-action="guardar">Guardar seguimiento</button></div>' +
                (c.seguimiento && c.seguimiento.actualizado ? '<p class="adt_fin__muted adt_cli__updated">Última actualización: ' +
                    moment.utc(c.seguimiento.actualizado).local().format('DD/MM/YYYY HH:mm') + (c.seguimiento.responsable ? ' · ' + esc(c.seguimiento.responsable) : '') + '</p>' : '') +
                '</section>'
            );
            this.$el.addClass('adt_cli--panel');
        },

        _cerrarPanel: function () {
            this.clienteAbierto = null;
            this.$el.removeClass('adt_cli--panel');
        },

        // ------------------------------------------------------------------ eventos
        _onAbrirCliente: function (ev) {
            this.clienteAbierto = parseInt(ev.currentTarget.getAttribute('data-cliente'), 10);
            this._hideTip();
            this._renderPanel();
            this._ref('panel').scrollTop(0);
        },

        _onClasificacion: function (ev) {
            this._ref('motivo-wrap').prop('hidden', !ev.currentTarget.value);
        },

        _onGuardar: function () {
            var self = this;
            var valores = {
                estado: this._ref('estado').val(),
                proximo_contacto: this._ref('proximo').val() || false,
                clasificacion_manual: this._ref('clasificacion').val() || false,
                motivo_manual: this._ref('clasificacion').val() ? this._ref('motivo').val() : false,
                notas: this._ref('notas').val(),
            };
            if (valores.clasificacion_manual === 'no_prestar' && !(valores.motivo_manual || '').trim()) {
                this._ref('error').text('Indica el motivo para marcar al cliente como "No prestar".').prop('hidden', false);
                this._ref('motivo').focus();
                return;
            }
            var $btn = this.$('[data-action="guardar"]').prop('disabled', true).text('Guardando…');
            this._rpc({
                model: 'adt.comercial.clientes.dashboard',
                method: 'guardar_seguimiento',
                args: [this.clienteAbierto, valores],
            }).then(function () {
                // Recarga para recalcular el segmento (la clasificación manual puede cambiarlo).
                return self._load();
            }).then(function () {
                self._render();
                self._renderPanel();
                self.displayNotification({type: 'success', message: 'Seguimiento guardado.'});
            }).guardedCatch(function () {
                $btn.prop('disabled', false).text('Guardar seguimiento');
            });
        },

        _onHistorial: function () {
            var c = _.findWhere(this.data.clientes, {id: this.clienteAbierto});
            if (!c || !c.seguimiento) { return; }
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'adt.cliente.seguimiento',
                res_id: c.seguimiento.id,
                views: [[false, 'form']],
                target: 'current',
            });
        },

        _onVerSeguimientos: function () {
            this.do_action('adt_comercial.action_cliente_seguimiento');
        },

        _onAbrirCuenta: function (ev) {
            ev.stopPropagation();
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'adt.comercial.cuentas',
                res_id: parseInt(ev.currentTarget.getAttribute('data-cuenta'), 10),
                views: [[this.data.vista_cuenta, 'form']],
                target: 'current',
            });
        },

        _onRefresh: function () {
            var self = this;
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true).text('Actualizando…');
            this._load().then(function () {
                self._render();
                if (self.clienteAbierto) { self._renderPanel(); }
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

        _onTab: function (ev) {
            var key = ev.currentTarget.getAttribute('data-tab');
            this.tab = key;
            this.sort = _.findWhere(TABS, {key: key}).sort;
            this.page = 0;
            this._hideTip();
            this._renderLista();
            if (!$(ev.currentTarget).hasClass('adt_cob__tab')) {
                var box = this._ref('lista')[0];
                this.$('.adt_fin__scroll').animate({scrollTop: box.offsetTop - 16}, 250);
            }
        },

        _onSort: function (ev) {
            var key = ev.currentTarget.getAttribute('data-sort');
            var numerica = _.contains(['puntaje', 'creditos', 'puntualidad', 'capturas'], key);
            this.sort = {key: key, dir: this.sort.key === key ? -this.sort.dir : (numerica ? -1 : 1)};
            this._renderLista();
        },

        _onPage: function (ev) {
            this.page += parseInt(ev.currentTarget.getAttribute('data-page'), 10);
            this._renderLista();
        },

        _onBuscar: _.debounce(function (ev) {
            this.busqueda = ev.target.value || '';
            this.page = 0;
            this._renderLista();
        }, 200),

        _onKeydown: function (ev) {
            if (ev.key === 'Escape' && this.clienteAbierto) { this._cerrarPanel(); }
        },

        _onExport: function () {
            var self = this;
            var quote = function (val) { return '"' + String(val === null || val === undefined ? '' : val).replace(/"/g, '""') + '"'; };
            var lineas = [['Cliente', 'Documento', 'Teléfono', 'Segmento', 'Puntaje', 'Créditos terminados', 'Créditos', 'Pagó a tiempo %',
                'Capturas', 'Financiera', 'Terminó de pagar', 'Termina', 'Motivos', 'Seguimiento', 'Próximo contacto'].map(quote).join(',')];
            this._filas().forEach(function (c) {
                var seg = c.seguimiento || {};
                lineas.push([c.nombre, c.documento, c.telefono, self.data.segmentos[c.segmento], c.puntaje, c.n_terminados, c.n_creditos,
                    c.puntualidad, c.capturas, c.financiera, c.termino, c.termina, c.bloqueos.join(' · '),
                    seg.estado ? self.data.estados_seguimiento[seg.estado] : '', seg.proximo_contacto].map(quote).join(','));
            });
            var blob = new Blob(['﻿' + lineas.join('\r\n')], {type: 'text/csv;charset=utf-8'});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'clientes_' + this.tab + '_' + moment().format('YYYYMMDD_HHmm') + '.csv';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
        },

        _comoSeLeeHtml: function () {
            var d = this.data;
            return '<details class="adt_fin__howto"><summary>¿Cómo se calcula el puntaje y los segmentos?</summary><ul>' +
                '<li><b>Puntaje (0–100):</b> empieza en 100. Resta hasta 40 puntos por cuotas no pagadas a tiempo (se toleran 3 días), hasta 20 por el atraso promedio, ' +
                '10–15 si llegó a atrasarse más de 30/60 días, 15 por captura (máx. 30), 40 por disolución de contrato, 50 si se le recuperó la moto, ' +
                '5 por papeleta (máx. 15), 10 si tiene una papeleta impaga y 20 si hoy debe cuotas con más de 30 días de atraso.</li>' +
                '<li><b>No prestar:</b> moto recuperada, disolución de contrato, 2 o más capturas, puntaje menor a ' + d.umbral_minimo + ', o marcado así por el equipo.</li>' +
                '<li><b>Listo para nuevo préstamo:</b> terminó de pagar, no tiene crédito en curso y su puntaje es ' + d.umbral_apto + ' o más. Entre ' + d.umbral_minimo +
                ' y ' + (d.umbral_apto - 1) + ' queda en <b>Evaluar</b>.</li>' +
                '<li><b>Pagando:</b> tiene un crédito en curso; buen pagador si su puntaje es ' + d.umbral_apto + ' o más.</li>' +
                '<li><b>Recompra:</b> sacó otro crédito después de terminar de pagar uno.</li>' +
                '<li>La <b>clasificación manual</b> del seguimiento reemplaza a la automática; "No prestar" siempre tiene prioridad.</li>' +
                '</ul></details>';
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

    core.action_registry.add('adt_clientes_dashboard', ClientesDashboard);

    return ClientesDashboard;
});
