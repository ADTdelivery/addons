odoo.define('adt_comercial.FinancieraDashboard', function (require) {
    'use strict';

    /**
     * Dashboard Gerencial de financieras, pensado para el CEO.
     * Responde dos preguntas: ¿cuánto gana ADT? y ¿cuánto hay que pagar a las financieras (y cuándo)?
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;
    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var MESES_LARGO = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
        'septiembre', 'octubre', 'noviembre', 'diciembre'];
    var HORIZONTE = 12;

    function sum(rows, key) {
        return rows.reduce(function (acc, r) { return acc + (r[key] || 0); }, 0);
    }

    function pct(part, total) {
        return total > 0 ? Math.max(0, Math.min(100, (part / total) * 100)) : 0;
    }

    function mesKey(date) {
        return date.getFullYear() + '-' + ('0' + (date.getMonth() + 1)).slice(-2);
    }

    function mesLabel(key, largo) {
        var p = key.split('-');
        var m = parseInt(p[1], 10) - 1;
        return largo ? MESES_LARGO[m] + ' ' + p[0] : MESES[m] + ' ' + p[0].slice(2);
    }

    function normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
    }

    var PAGINA_CLIENTES = 15;

    function capitalizar(texto) {
        return texto.charAt(0).toUpperCase() + texto.slice(1);
    }

    // Escala "redonda" para las líneas guía del calendario.
    function niceStep(max, ticks) {
        var raw = max / ticks;
        var mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
        var norm = raw / mag;
        var step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
        return step * mag;
    }

    var FinancieraDashboard = AbstractAction.extend({
        template: 'adt_comercial.FinancieraDashboard',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="detalle"]': '_onOpenDetalle',
            'click [data-financiera]': '_onFiltrar',
            'click [data-cuenta]': '_onOpenCuenta',
            'input [data-ref="buscar"]': '_onBuscar',
            'focus [data-ref="buscar"]': '_onBuscar',
            'keydown [data-ref="buscar"]': '_onBuscarKey',
            'blur [data-ref="buscar"]': '_onBuscarBlur',
            'mousedown [data-ref="suggest"]': '_onSuggestMousedown',
            'click [data-cliente]': '_onElegirCliente',
            'click [data-action="quitar-cliente"]': '_onQuitarCliente',
            'click [data-sort-clientes]': '_onSortClientes',
            'click [data-page-clientes]': '_onPageClientes',
            'mouseover [data-tip]': '_onTipShow',
            'mousemove [data-tip]': '_onTipMove',
            'mouseout [data-tip]': '_onTipHide',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.financieraId = null;
            this.clienteId = null;
            this.busqueda = '';
            this.sugerencias = [];
            this.sugerenciaActiva = -1;
            this.sortClientes = {key: 'ganancia_esperada', dir: -1};
            this.pageClientes = 0;
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
                model: 'adt.comercial.financiera.dashboard',
                method: 'get_dashboard_data',
                args: [],
            }).then(function (data) {
                self.data = data;
                self._hoy = moment(data.hoy).toDate();
                self._finPorCuenta = {};
                data.cuentas.forEach(function (c) {
                    self._finPorCuenta[c.id] = c.financiera_id;
                    c._buscar = normalizar([c.cliente, c.documento, c.referencia, c.moto].join(' '));
                });
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        // ------------------------------------------------------------------ formato
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

        _nombreCliente: function (id) {
            var c = _.findWhere(this.data.cuentas, {cliente_id: id});
            return c ? c.cliente : '';
        },

        _nombreFinanciera: function (id) {
            var f = _.findWhere(this.data.financieras, {id: id});
            return f ? f.name : '';
        },

        // ------------------------------------------------------------------ cálculo
        _vista: function () {
            var fid = this.financieraId;
            var cid = this.clienteId;
            var cuentas = this.data.cuentas.filter(function (c) {
                return (fid === null || c.financiera_id === fid) && (cid === null || c.cliente_id === cid);
            });
            var ids = {};
            cuentas.forEach(function (c) { ids[c.id] = true; });
            var deCuentas = function (r) { return ids[r.cuenta_id]; };
            var pagos = this.data.pagos_financiera.filter(deCuentas);
            var cobros = this.data.cobros_clientes.filter(deCuentas);

            var meses = [];
            var d = new Date(this._hoy.getFullYear(), this._hoy.getMonth(), 1);
            for (var i = 0; i < HORIZONTE; i++) {
                meses.push(mesKey(d));
                d.setMonth(d.getMonth() + 1);
            }
            var ultimoMes = meses[meses.length - 1];
            var porMes = function (rows) {
                var out = {};
                rows.forEach(function (r) { out[r.mes] = (out[r.mes] || 0) + r.monto; });
                return out;
            };
            var pagosMes = porMes(pagos);
            var cobrosMes = porMes(cobros);
            var despues = function (map) {
                return _.reduce(map, function (acc, v, k) {
                    return acc + (k !== 'sin_fecha' && k !== 'atrasado' && k > ultimoMes ? v : 0);
                }, 0);
            };
            var mesesConPago = _.keys(pagosMes).filter(function (k) { return k !== 'sin_fecha' && pagosMes[k] > 0.5; }).sort();
            var proximas = pagos.filter(function (p) { return p.proxima; }).map(function (p) { return p.proxima; }).sort();

            var desfase = cuentas.filter(function (c) { return c.semaforo === 'desfase'; })
                .map(function (c) { return _.extend({adelantado: -c.caja_neta}, c); })
                .sort(function (a, b) { return b.adelantado - a.adelantado; });

            return {
                cuentas: cuentas,
                n: cuentas.length,
                totalCliente: sum(cuentas, 'total_cliente'),
                totalFinanciera: sum(cuentas, 'total_financiera'),
                cobrado: sum(cuentas, 'cobrado'),
                pagado: sum(cuentas, 'pagado'),
                pendiente: sum(cuentas, 'pendiente'),
                gananciaActual: sum(cuentas, 'ganancia_actual'),
                gananciaEsperada: sum(cuentas, 'ganancia_esperada'),
                meses: meses,
                pagosMes: pagosMes,
                cobrosMes: cobrosMes,
                pagosDespues: despues(pagosMes),
                cobrosDespues: despues(cobrosMes),
                pagosSinFecha: pagosMes.sin_fecha || 0,
                cobrosAtrasados: cobrosMes.atrasado || 0,
                ultimoPago: mesesConPago[mesesConPago.length - 1] || null,
                proximoPago: proximas[0] || null,
                desfase: desfase,
                adelantado: sum(desfase, 'adelantado'),
            };
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var hoy = moment(this.data.hoy);
            var v = this._vista();
            var porCliente = this.clienteId !== null;
            this.$el.toggleClass('adt_fin--cliente', porCliente);
            this._renderChips();
            if (porCliente) {
                this._renderFichaCliente(v, hoy);
                return;
            }
            this._ref('crumb').empty();
            this._ref('title').text('Financieras: ganancia y pagos');
            this._ref('subtitle').text('Al ' + hoy.format('DD/MM/YYYY') + ' · ' +
                (this.financieraId === null ? 'todas las financieras' : this._nombreFinanciera(this.financieraId)));

            if (!v.n) {
                this._ref('body').html('<div class="adt_fin__empty">' + (this.data.cuentas.length ?
                    'No hay cuentas con financiera para este filtro.' :
                    'Aún no hay cuentas con datos de la financiera. Registra el cronograma en la pestaña <b>Financiera</b> de cada cuenta.') +
                    '</div>');
                return;
            }
            this._ref('body').html(
                '<div class="adt_fin__answers">' + this._gananciaHtml(v) + this._deudaHtml(v) + '</div>' +
                this._tilesHtml(v) +
                '<div class="adt_fin__grid">' +
                this._card('¿De dónde sale la ganancia?', 'Todos los contratos con financiera, de principio a fin', this._puenteHtml(v)) +
                this._card('Lo que entra y lo que sale, mes a mes', 'Próximos ' + HORIZONTE + ' meses', this._calendarioHtml(v), 'wide') +
                this._card('Ganancia por cliente',
                    'Toca un cliente para abrir su ficha · el buscador de arriba también filtra esta lista',
                    '<div data-ref="tabla-clientes"></div>', 'wide') +
                (this.financieraId !== null ? '' : this._card('Por financiera', 'Toca una financiera para ver solo sus números', this._financierasHtml(), 'wide')) +
                (v.desfase.length ? this._card('Cuentas donde ADT está poniendo dinero',
                    'Ya pagamos a la financiera más de lo que cobramos al cliente', this._desfaseHtml(v), 'wide') : '') +
                '</div>' +
                this._comoSeLeeHtml()
            );
            this._renderTablaClientes();
        },

        // ------------------------------------------------------------------ ficha de un cliente
        // Vista aparte: todo lo que se ve aquí es solo de este cliente (sin totales globales).
        _renderFichaCliente: function (v, hoy) {
            var nombre = this._nombreCliente(this.clienteId);
            var doc = v.cuentas.length && v.cuentas[0].documento;
            var financieras = _.uniq(v.cuentas.map(function (c) { return this._nombreFinanciera(c.financiera_id); }, this));
            this._ref('crumb').html('<button type="button" class="adt_fin__crumb" data-action="quitar-cliente">‹ Todos los clientes</button>');
            this._ref('title').text(nombre);
            this._ref('subtitle').text(_.compact([
                doc, v.n + (v.n === 1 ? ' moto financiada' : ' motos financiadas'),
                financieras.join(', '), 'al ' + hoy.format('DD/MM/YYYY')]).join(' · '));

            var faltaCubrir = sum(v.cuentas.map(function (c) {
                return {f: Math.max(c.total_financiera - c.cobrado, 0)};
            }), 'f');
            this._ref('body').html(
                this._fichaResumenHtml(v, faltaCubrir) +
                '<div class="adt_fin__grid">' +
                this._card('¿Cómo va este cliente?', 'Lo que él nos pagó comparado con lo que nosotros pagamos a su financiera',
                    this._fichaComparacionHtml(v, faltaCubrir), 'wide') +
                this._card(v.n === 1 ? 'Su moto' : 'Sus motos', 'Toca una cuenta para abrirla', this._cuentasClienteHtml(v), 'wide') +
                this._card('Sus pagos mes a mes', 'Próximos ' + HORIZONTE + ' meses: su cuota y la cuota que pagamos a la financiera',
                    this._calendarioHtml(v), 'wide') +
                '</div>'
            );
        },

        _fichaResumenHtml: function (v, faltaCubrir) {
            var ganancia = v.gananciaActual > 0.5 ?
                {valor: this._money(v.gananciaActual), texto: 'Lo que ya nos pagó por encima del costo de su financiera.'} :
                {valor: this._money(0), texto: 'Aún no deja ganancia: falta cobrarle <b>' + this._money(faltaCubrir) +
                    '</b> para cubrir lo que cuesta su financiera.'};
            var esteMes = v.pagosMes[v.meses[0]] || 0;
            var bloques = [
                {cls: 'gain', titulo: 'ADT ya ganó con este cliente', valor: ganancia.valor, texto: ganancia.texto},
                {cls: 'neutral', titulo: 'Ganancia cuando termine de pagar', valor: this._money(v.gananciaEsperada),
                    texto: 'Su cronograma suma <b>' + this._money(v.totalCliente) + '</b> y su financiera cuesta <b>' +
                        this._money(v.totalFinanciera) + '</b>.'},
                {cls: 'debt', titulo: 'Falta pagar a la financiera por ' + (v.n === 1 ? 'su moto' : 'sus motos'),
                    valor: this._money(v.pendiente),
                    texto: v.proximoPago ? 'Próxima cuota: <b>' + moment(v.proximoPago).format('DD/MM/YYYY') + '</b>' +
                        (esteMes > 0.5 ? ' · este mes <b>' + this._money(esteMes) + '</b>' : '') + '.' :
                        (v.pendiente > 0.5 ? 'Sin fecha de inicio registrada.' : 'Su financiera ya está pagada.')},
            ];
            return '<div class="adt_fin__ficha">' + bloques.map(function (b) {
                return '<section class="adt_fin__ficha-item adt_fin__ficha-item--' + b.cls + '">' +
                    '<p class="adt_fin__question">' + esc(b.titulo) + '</p>' +
                    '<p class="adt_fin__big">' + b.valor + '</p>' +
                    '<p class="adt_fin__sentence">' + b.texto + '</p></section>';
            }).join('') + '</div>';
        },

        // Dos barras en la misma escala: lo que pagó el cliente vs. lo que pagamos a la financiera.
        _fichaComparacionHtml: function (v, faltaCubrir) {
            var self = this;
            var escala = Math.max(v.totalCliente, v.totalFinanciera, 1);
            var fila = function (titulo, cls, hecho, total) {
                return '<div class="adt_fin__compare">' +
                    '<span class="adt_fin__compare-label">' + esc(titulo) + '</span>' +
                    '<span class="adt_fin__compare-track" style="width:' + (total / escala * 100) + '%">' +
                    '<span class="' + cls + '" style="width:' + pct(hecho, total) + '%"></span></span>' +
                    '<span class="adt_fin__compare-val"><b>' + self._money(hecho) + '</b> de ' + self._money(total) +
                    ' <span class="adt_fin__muted">(' + Math.round(pct(hecho, total)) + '%)</span></span></div>';
            };
            var veredicto;
            if (v.adelantado > 0.5) {
                veredicto = {cls: 'bad', icon: '!', texto: '<b>ADT está poniendo ' + this._money(v.adelantado) +
                    ' de su bolsillo:</b> ya pagamos a la financiera más de lo que este cliente nos ha pagado.'};
            } else if (faltaCubrir < 0.5) {
                veredicto = {cls: 'ok', icon: '✓', texto: '<b>Ya cubrió su financiera.</b> Todo lo que pague desde ahora es ganancia para ADT.'};
            } else {
                veredicto = {cls: 'ok', icon: '✓', texto: '<b>Va al día:</b> lo que nos pagó cubre lo que ya pagamos a la financiera. ' +
                    'Le falta pagar ' + this._money(faltaCubrir) + ' para empezar a dejar ganancia.'};
            }
            var atraso = v.cobrosAtrasados > 0.5 ? '<p class="adt_fin__verdict adt_fin__verdict--warn"><i class="adt_fin__status adt_fin__status--warn" aria-hidden="true">!</i>' +
                '<span>Tiene <b>' + this._money(v.cobrosAtrasados) + '</b> en cuotas vencidas sin pagar.</span></p>' : '';
            return fila('El cliente nos pagó', 'is-in', v.cobrado, v.totalCliente) +
                fila('Pagamos a la financiera', 'is-out', v.pagado, v.totalFinanciera) +
                '<p class="adt_fin__verdict adt_fin__verdict--' + veredicto.cls + '"><i class="adt_fin__status adt_fin__status--' +
                veredicto.cls + '" aria-hidden="true">' + veredicto.icon + '</i><span>' + veredicto.texto + '</span></p>' + atraso;
        },

        _renderChips: function () {
            var self = this;
            var chips = [{id: null, name: 'Todas'}].concat(this.data.financieras);
            this._ref('chips').html(chips.map(function (f) {
                var activo = self.financieraId === f.id;
                return '<button type="button" class="adt_fin__chip' + (activo ? ' is-active' : '') + '" data-financiera="' +
                    (f.id === null ? 'todas' : f.id) + '" aria-pressed="' + activo + '">' + esc(f.name) + '</button>';
            }).join(''));
        },

        _card: function (title, subtitle, content, size) {
            return '<section class="adt_fin__card' + (size === 'wide' ? ' adt_fin__card--wide' : '') + '">' +
                '<header class="adt_fin__card-head"><h2>' + esc(title) + '</h2>' +
                (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') + '</header>' + content + '</section>';
        },

        _gananciaHtml: function (v) {
            var avance = pct(v.gananciaActual, v.gananciaEsperada);
            return '<section class="adt_fin__answer adt_fin__answer--gain">' +
                '<p class="adt_fin__question">¿Cuánto ha ganado ADT?</p>' +
                '<p class="adt_fin__big">' + this._money(v.gananciaActual) + '</p>' +
                '<p class="adt_fin__sentence">Ganancia ya lograda. Cuando terminen todos los contratos, la ganancia será ' +
                '<b>' + this._money(v.gananciaEsperada) + '</b>.</p>' +
                '<div class="adt_fin__meter" data-tip="' + esc('<b>Ganancia</b><br/>Lograda: ' + this._money(v.gananciaActual) +
                    '<br/>Por lograr: ' + this._money(Math.max(v.gananciaEsperada - v.gananciaActual, 0))) + '">' +
                '<span class="is-gain" style="width:' + avance + '%"></span></div>' +
                '<p class="adt_fin__meter-caption">Llevamos el <b>' + Math.round(avance) + '%</b> de la ganancia esperada</p>' +
                '</section>';
        },

        _deudaHtml: function (v) {
            var esteMes = v.pagosMes[v.meses[0]] || 0;
            var proximoMes = v.pagosMes[v.meses[1]] || 0;
            var avance = pct(v.pagado, v.totalFinanciera);
            var fin = v.ultimoPago ? 'El último pago es en <b>' + esc(mesLabel(v.ultimoPago, true)) + '</b>.' :
                'No quedan cuotas con fecha por pagar.';
            return '<section class="adt_fin__answer adt_fin__answer--debt">' +
                '<p class="adt_fin__question">¿Cuánto falta pagar a las financieras?</p>' +
                '<p class="adt_fin__big">' + this._money(v.pendiente) + '</p>' +
                '<div class="adt_fin__due">' +
                '<div><span>Este mes</span><b>' + this._money(esteMes) + '</b></div>' +
                '<div><span>' + esc(capitalizar(mesLabel(v.meses[1], true))) + '</span><b>' + this._money(proximoMes) + '</b></div>' +
                (v.proximoPago ? '<div><span>Próximo pago</span><b>' + moment(v.proximoPago).format('DD/MM') + '</b></div>' : '') +
                '</div>' +
                '<div class="adt_fin__meter" data-tip="' + esc('<b>Deuda con financieras</b><br/>Pagado: ' + this._money(v.pagado) +
                    '<br/>Falta: ' + this._money(v.pendiente) + '<br/>Total: ' + this._money(v.totalFinanciera)) + '">' +
                '<span class="is-out" style="width:' + avance + '%"></span></div>' +
                '<p class="adt_fin__meter-caption">Ya pagamos el <b>' + Math.round(avance) + '%</b> de ' +
                this._money(v.totalFinanciera) + '. ' + fin + '</p>' +
                '</section>';
        },

        _tilesHtml: function (v) {
            var tiles = [
                {label: 'Motos con financiera', value: v.n.toLocaleString('es-PE')},
                {label: 'Cobrado a clientes', value: this._money(v.cobrado), sub: 'de ' + this._money(v.totalCliente) + ' en total'},
                {label: 'Pagado a financieras', value: this._money(v.pagado), sub: 'de ' + this._money(v.totalFinanciera) + ' en total'},
            ];
            if (v.cobrosAtrasados > 0.5) {
                tiles.push({label: 'Clientes atrasados', value: this._money(v.cobrosAtrasados), sub: 'cuotas vencidas sin pagar', alert: 'warn'});
            }
            if (v.adelantado > 0.5) {
                tiles.push({label: 'ADT está adelantando', value: this._money(v.adelantado),
                    sub: v.desfase.length + (v.desfase.length === 1 ? ' cuenta' : ' cuentas') + ' en rojo', alert: 'bad'});
            }
            return '<div class="adt_fin__tiles">' + tiles.map(function (t) {
                var icon = t.alert ? '<i class="adt_fin__status adt_fin__status--' + t.alert + '" aria-hidden="true">!</i>' : '';
                return '<div class="adt_fin__tile' + (t.alert ? ' adt_fin__tile--' + t.alert : '') + '">' +
                    '<span class="adt_fin__tile-label">' + icon + esc(t.label) + '</span>' +
                    '<span class="adt_fin__tile-value">' + esc(t.value) + '</span>' +
                    (t.sub ? '<span class="adt_fin__tile-sub">' + esc(t.sub) + '</span>' : '') + '</div>';
            }).join('') + '</div>';
        },

        // Gráfico puente: lo que pagan los clientes − lo que se lleva la financiera = ganancia.
        _puenteHtml: function (v) {
            var ganancia = v.totalCliente - v.totalFinanciera;
            var max = Math.max(v.totalCliente, v.totalFinanciera, 1);
            var h = function (val) { return Math.max(0, val) / max * 100; };
            var base = Math.max(ganancia, 0);
            var cols = [
                {cls: 'is-in', bottom: 0, height: h(v.totalCliente), value: this._money(v.totalCliente, true),
                    label: 'Lo que pagarán los clientes', tip: 'Total de los cronogramas de los clientes'},
                {cls: 'is-out', bottom: h(base), height: h(v.totalCliente) - h(base), value: '− ' + this._money(v.totalFinanciera, true),
                    label: 'Lo que se lleva la financiera', tip: 'Total de los cronogramas con las financieras'},
                {cls: ganancia >= 0 ? 'is-gain' : 'is-loss', bottom: 0, height: h(Math.abs(ganancia)), value: '= ' + this._money(ganancia, true),
                    label: ganancia >= 0 ? 'Ganancia de ADT' : 'Pérdida de ADT', tip: 'Diferencia entre ambos'},
            ];
            var self = this;
            var bars = cols.map(function (c, i) {
                var connector = i < 2 ? '<span class="adt_fin__bridge-link" style="bottom:' +
                    (i === 0 ? c.height : cols[1].bottom) + '%"></span>' : '';
                return '<div class="adt_fin__bridge-col" data-tip="' + esc('<b>' + c.label + '</b><br/>' + c.tip) + '">' +
                    '<div class="adt_fin__bridge-plot">' +
                    '<span class="adt_fin__bridge-val" style="bottom:calc(' + (c.bottom + c.height) + '% + 6px)">' + esc(c.value) + '</span>' +
                    '<span class="adt_fin__bridge-bar ' + c.cls + '" style="bottom:' + c.bottom + '%;height:' + c.height + '%"></span>' +
                    connector + '</div>' +
                    '<span class="adt_fin__bridge-label">' + esc(c.label) + '</span></div>';
            }).join('');
            var porCien = v.totalCliente > 0 ? Math.round(v.totalFinanciera / v.totalCliente * 100) : 0;
            var frase = v.totalCliente > 0 ?
                '<p class="adt_fin__takeaway">De cada <b>' + self._money(100) + '</b> que pagan los clientes, <b>' +
                self._money(porCien) + '</b> van a la financiera y <b>' + self._money(100 - porCien) + '</b> quedan para ADT.</p>' : '';
            return frase + '<div class="adt_fin__bridge">' + bars + '</div>' +
                '<p class="adt_fin__note">Los clientes ya pagaron <b>' + this._money(v.cobrado) + '</b> (' +
                Math.round(pct(v.cobrado, v.totalCliente)) + '% del total).</p>';
        },

        // Calendario: barras agrupadas por mes (entra = cobros a clientes, sale = pagos a financieras).
        _calendarioHtml: function (v) {
            var self = this;
            var uno = this.clienteId !== null;
            var et = uno ? {
                entra: 'Cuota del cliente', sale: 'Cuota a la financiera',
                legIn: 'Entra: lo que paga el cliente', legOut: 'Sale: lo que pagamos a su financiera',
            } : {
                entra: 'Cobrar a clientes', sale: 'Pagar a financieras',
                legIn: 'Entra: cobro a clientes', legOut: 'Sale: pago a financieras',
            };
            var max = 0;
            v.meses.forEach(function (m) { max = Math.max(max, v.pagosMes[m] || 0, v.cobrosMes[m] || 0); });
            var step = niceStep(max || 1, 4);
            var top = Math.max(step * Math.ceil((max || 1) / step), step);
            var grid = '';
            for (var g = 0; g <= top + 0.5; g += step) {
                grid += '<span class="adt_fin__gridline" style="bottom:' + (g / top * 100) + '%"><em>' + esc(this._money(g, true)) + '</em></span>';
            }
            var cols = v.meses.map(function (m, idx) {
                var entra = v.cobrosMes[m] || 0;
                var sale = v.pagosMes[m] || 0;
                var queda = entra - sale;
                var tip = '<b>' + mesLabel(m, true) + (idx === 0 ? ' (lo que falta del mes)' : '') + '</b>' +
                    '<div class="adt_fin__tip-row"><span><i class="adt_fin__dot is-in"></i>' + et.entra + '</span><b>' + self._money(entra) + '</b></div>' +
                    '<div class="adt_fin__tip-row"><span><i class="adt_fin__dot is-out"></i>' + et.sale + '</span><b>' + self._money(sale) + '</b></div>' +
                    '<div class="adt_fin__tip-row adt_fin__tip-total"><span>' + (queda >= 0 ? 'Queda para ADT' : 'Falta cubrir') + '</span><b>' + self._money(queda) + '</b></div>';
                return '<div class="adt_fin__month" data-tip="' + esc(tip) + '">' +
                    '<div class="adt_fin__month-plot">' +
                    '<span class="adt_fin__bar is-in" style="height:' + (entra / top * 100) + '%"></span>' +
                    '<span class="adt_fin__bar is-out" style="height:' + (sale / top * 100) + '%"></span></div>' +
                    '<span class="adt_fin__month-label">' + esc(mesLabel(m)) + '</span>' +
                    '<span class="adt_fin__month-net ' + (queda >= 0 ? 'is-pos' : 'is-neg') + '">' +
                    (queda >= 0 ? '▲ ' : '▼ ') + esc(self._money(queda, true)) + '</span></div>';
            }).join('');

            var notas = [];
            if (v.cobrosAtrasados > 0.5) {
                notas.push('Además, ' + (uno ? 'el cliente debe' : 'los clientes deben') + ' <b>' + this._money(v.cobrosAtrasados) +
                    '</b> de cuotas ya vencidas (no están en el gráfico).');
            }
            if (v.pagosDespues > 0.5) {
                notas.push('Después de ' + esc(mesLabel(v.meses[v.meses.length - 1], true)) + ' quedan <b>' + this._money(v.pagosDespues) +
                    '</b> por pagar a ' + (uno ? 'la financiera' : 'las financieras') + ' y <b>' + this._money(v.cobrosDespues) + '</b> por cobrar' +
                    (uno ? 'le.' : ' a clientes.'));
            }
            if (v.pagosSinFecha > 0.5) {
                notas.push('<b>' + this._money(v.pagosSinFecha) + '</b> por pagar a ' + (uno ? 'la financiera' : 'financieras') +
                    ' no tienen fecha de inicio registrada.');
            }

            var filas = v.meses.map(function (m) {
                var entra = v.cobrosMes[m] || 0;
                var sale = v.pagosMes[m] || 0;
                return '<tr><td>' + esc(mesLabel(m, true)) + '</td><td class="num">' + self._money(entra) + '</td><td class="num">' +
                    self._money(sale) + '</td><td class="num">' + self._money(entra - sale) + '</td></tr>';
            }).join('');

            return '<div class="adt_fin__legend"><span><i class="adt_fin__dot is-in"></i>' + et.legIn + '</span>' +
                '<span><i class="adt_fin__dot is-out"></i>' + et.legOut + '</span>' +
                '<span class="adt_fin__muted">▲ / ▼ lo que queda cada mes</span></div>' +
                '<div class="adt_fin__calendar"><div class="adt_fin__grid-lines">' + grid + '</div>' + cols + '</div>' +
                (notas.length ? '<ul class="adt_fin__notes">' + notas.map(function (n) { return '<li>' + n + '</li>'; }).join('') + '</ul>' : '') +
                '<details class="adt_fin__table-toggle"><summary>Ver como tabla</summary>' +
                '<table class="adt_fin__table"><thead><tr><th>Mes</th><th class="num">' + et.entra + '</th><th class="num">' + et.sale + '</th>' +
                '<th class="num">Queda</th></tr></thead><tbody>' + filas + '</tbody></table></details>';
        },

        _financierasHtml: function () {
            var self = this;
            var hoy = this.data.hoy;
            var mesActual = mesKey(this._hoy);
            var cards = this.data.financieras.map(function (f) {
                var cuentas = self.data.cuentas.filter(function (c) { return c.financiera_id === f.id; });
                var pagos = self.data.pagos_financiera.filter(function (p) { return self._finPorCuenta[p.cuenta_id] === f.id; });
                var total = sum(cuentas, 'total_financiera');
                var pagado = sum(cuentas, 'pagado');
                var desfase = cuentas.filter(function (c) { return c.semaforo === 'desfase'; });
                var esteMes = sum(pagos.filter(function (p) { return p.mes === mesActual; }), 'monto');
                var proxima = _.compact(_.pluck(pagos, 'proxima')).filter(function (d) { return d > hoy; }).sort()[0];
                return {
                    f: f, n: cuentas.length, total: total, pagado: pagado,
                    pendiente: sum(cuentas, 'pendiente'),
                    ganancia: sum(cuentas, 'ganancia_actual'),
                    esperada: sum(cuentas, 'ganancia_esperada'),
                    esteMes: esteMes, proxima: proxima,
                    desfase: desfase.length,
                    adelantado: -sum(desfase, 'caja_neta'),
                };
            }).sort(function (a, b) { return b.pendiente - a.pendiente; });

            return '<div class="adt_fin__fin-grid">' + cards.map(function (c) {
                return '<button type="button" class="adt_fin__fin" data-financiera="' + c.f.id + '">' +
                    '<span class="adt_fin__fin-head"><b>' + esc(c.f.name) + '</b><span class="adt_fin__muted">' + c.n + (c.n === 1 ? ' moto' : ' motos') + '</span></span>' +
                    '<span class="adt_fin__fin-row"><span>Le debemos</span><b class="adt_fin__fin-big">' + self._money(c.pendiente) + '</b></span>' +
                    '<span class="adt_fin__meter adt_fin__meter--sm"><span class="is-out" style="width:' + pct(c.pagado, c.total) + '%"></span></span>' +
                    '<span class="adt_fin__fin-caption">Pagado ' + Math.round(pct(c.pagado, c.total)) + '% de ' + self._money(c.total) + '</span>' +
                    '<span class="adt_fin__fin-row"><span>Este mes</span><b>' + self._money(c.esteMes) + '</b></span>' +
                    (c.proxima ? '<span class="adt_fin__fin-row"><span>Próximo pago</span><b>' + moment(c.proxima).format('DD/MM/YYYY') + '</b></span>' : '') +
                    '<span class="adt_fin__fin-row"><span>Ganancia lograda</span><b class="adt_fin__gain-text">' + self._money(c.ganancia) + '</b></span>' +
                    '<span class="adt_fin__fin-row"><span>Ganancia al final</span><b>' + self._money(c.esperada) + '</b></span>' +
                    (c.desfase ? '<span class="adt_fin__fin-alert"><i class="adt_fin__status adt_fin__status--bad" aria-hidden="true">!</i>ADT adelantó ' +
                        self._money(c.adelantado) + ' en ' + c.desfase + (c.desfase === 1 ? ' cuenta' : ' cuentas') + '</span>' :
                        '<span class="adt_fin__fin-ok"><i class="adt_fin__status adt_fin__status--ok" aria-hidden="true">✓</i>Sin cuentas en rojo</span>') +
                    '</button>';
            }).join('') + '</div>';
        },

        _desfaseHtml: function (v) {
            var self = this;
            var filas = v.desfase.slice(0, 10).map(function (c) {
                return '<tr data-cuenta="' + c.id + '"><td>' + esc(c.referencia) + '</td><td>' + esc(c.cliente) + '</td>' +
                    '<td>' + esc(c.moto) + '</td><td>' + esc(self._nombreFinanciera(c.financiera_id)) + '</td>' +
                    '<td class="num">' + self._money(c.pagado) + '</td><td class="num">' + self._money(c.cobrado) + '</td>' +
                    '<td class="num adt_fin__loss-text">' + self._money(c.adelantado) + '</td></tr>';
            }).join('');
            var mas = v.desfase.length > 10 ? '<p class="adt_fin__note">Y ' + (v.desfase.length - 10) + ' cuentas más. Usa "Ver cuentas" para la lista completa.</p>' : '';
            return '<div class="adt_fin__table-wrap"><table class="adt_fin__table adt_fin__table--click"><thead><tr>' +
                '<th>Cuenta</th><th>Cliente</th><th>Moto</th><th>Financiera</th><th class="num">Pagado a financiera</th>' +
                '<th class="num">Cobrado al cliente</th><th class="num">ADT adelantó</th></tr></thead><tbody>' + filas + '</tbody></table></div>' + mas;
        },

        // ------------------------------------------------------------------ clientes
        _estadoCliente: function (r) {
            if (r.adelantado > 0.5) {
                return '<span class="adt_fin__state adt_fin__state--bad"><i class="adt_fin__status adt_fin__status--bad" aria-hidden="true">!</i>ADT adelanta ' + this._money(r.adelantado) + '</span>';
            }
            if (r.ganancia_actual > 0.5) {
                return '<span class="adt_fin__state adt_fin__state--ok"><i class="adt_fin__status adt_fin__status--ok" aria-hidden="true">✓</i>Ya deja ganancia</span>';
            }
            return '<span class="adt_fin__state"><i class="adt_fin__status adt_fin__status--idle" aria-hidden="true">•</i>Recuperando</span>';
        },

        // Agrupa por cliente las cuentas del filtro de financiera (y del texto buscado).
        _filasClientes: function () {
            var fid = this.financieraId;
            var q = normalizar(this.busqueda);
            var map = {};
            this.data.cuentas.forEach(function (c) {
                if (fid !== null && c.financiera_id !== fid) { return; }
                var r = map[c.cliente_id] || (map[c.cliente_id] = {
                    id: c.cliente_id, nombre: c.cliente, documento: c.documento, n: 0, _buscar: '',
                    cobrado: 0, total_cliente: 0, total_financiera: 0, ganancia_actual: 0, ganancia_esperada: 0, adelantado: 0,
                });
                r.n++;
                r._buscar += ' ' + c._buscar;
                r.cobrado += c.cobrado;
                r.total_cliente += c.total_cliente;
                r.total_financiera += c.total_financiera;
                r.ganancia_actual += c.ganancia_actual;
                r.ganancia_esperada += c.ganancia_esperada;
                if (c.semaforo === 'desfase') { r.adelantado += -c.caja_neta; }
            });
            var filas = _.values(map).filter(function (r) { return !q || r._buscar.indexOf(q) !== -1; });
            filas.forEach(function (r) { r.avance = pct(r.ganancia_actual, r.ganancia_esperada); });
            var key = this.sortClientes.key;
            var dir = this.sortClientes.dir;
            return filas.sort(function (a, b) {
                var res = key === 'nombre' ? a.nombre.localeCompare(b.nombre) : a[key] - b[key];
                return res * dir || a.nombre.localeCompare(b.nombre);
            });
        },

        _renderTablaClientes: function () {
            var $cont = this._ref('tabla-clientes');
            if (!$cont.length) { return; }
            var self = this;
            var filas = this._filasClientes();
            var paginas = Math.max(1, Math.ceil(filas.length / PAGINA_CLIENTES));
            this.pageClientes = Math.min(this.pageClientes, paginas - 1);
            var inicio = this.pageClientes * PAGINA_CLIENTES;
            var cols = [
                {key: 'nombre', label: 'Cliente'},
                {key: 'n', label: 'Motos', num: true},
                {key: 'cobrado', label: 'Cobrado', num: true},
                {key: 'ganancia_actual', label: 'Ganancia lograda', num: true},
                {key: 'ganancia_esperada', label: 'Ganancia al final', num: true},
                {key: 'avance', label: 'Avance'},
                {key: 'adelantado', label: 'Estado'},
            ];
            var head = cols.map(function (c) {
                var flecha = self.sortClientes.key === c.key ? (self.sortClientes.dir > 0 ? ' ▲' : ' ▼') : '';
                return '<th class="is-sortable' + (c.num ? ' num' : '') + '" data-sort-clientes="' + c.key + '">' + esc(c.label) + flecha + '</th>';
            }).join('');
            var body = filas.slice(inicio, inicio + PAGINA_CLIENTES).map(function (r) {
                return '<tr data-cliente="' + r.id + '"><td><b>' + esc(r.nombre) + '</b>' +
                    (r.documento ? '<span class="adt_fin__doc">' + esc(r.documento) + '</span>' : '') + '</td>' +
                    '<td class="num">' + r.n + '</td><td class="num">' + self._money(r.cobrado) + '</td>' +
                    '<td class="num adt_fin__gain-text"><b>' + self._money(r.ganancia_actual) + '</b></td>' +
                    '<td class="num">' + self._money(r.ganancia_esperada) + '</td>' +
                    '<td><span class="adt_fin__meter adt_fin__meter--inline"><span class="is-gain" style="width:' + r.avance + '%"></span></span>' +
                    '<span class="adt_fin__pct">' + Math.round(r.avance) + '%</span></td>' +
                    '<td>' + self._estadoCliente(r) + '</td></tr>';
            }).join('') || '<tr><td colspan="7" class="adt_fin__muted">Ningún cliente coincide con "' + esc(this.busqueda) + '".</td></tr>';
            var tot = {
                cobrado: sum(filas, 'cobrado'), ganancia_actual: sum(filas, 'ganancia_actual'),
                ganancia_esperada: sum(filas, 'ganancia_esperada'), n: sum(filas, 'n'),
            };
            var foot = filas.length ? '<tfoot><tr><td>Total · ' + filas.length + (filas.length === 1 ? ' cliente' : ' clientes') +
                (this.busqueda ? ' encontrados' : '') + '</td><td class="num">' + tot.n + '</td><td class="num">' + this._money(tot.cobrado) + '</td>' +
                '<td class="num adt_fin__gain-text">' + this._money(tot.ganancia_actual) + '</td><td class="num">' + this._money(tot.ganancia_esperada) + '</td>' +
                '<td><span class="adt_fin__pct">' + Math.round(pct(tot.ganancia_actual, tot.ganancia_esperada)) + '%</span></td><td></td></tr></tfoot>' : '';
            var pager = paginas > 1 ? '<footer class="adt_fin__pager"><span>' + (inicio + 1) + '–' + Math.min(filas.length, inicio + PAGINA_CLIENTES) +
                ' de ' + filas.length + '</span>' +
                '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-page-clientes="-1"' + (this.pageClientes === 0 ? ' disabled' : '') + '>‹ Anterior</button>' +
                '<button type="button" class="adt_fin__btn adt_fin__btn--ghost" data-page-clientes="1"' + (this.pageClientes >= paginas - 1 ? ' disabled' : '') + '>Siguiente ›</button></footer>' : '';
            $cont.html('<div class="adt_fin__table-wrap adt_fin__table-wrap--full"><table class="adt_fin__table adt_fin__table--click"><thead><tr>' + head +
                '</tr></thead><tbody>' + body + '</tbody>' + foot + '</table></div>' + pager);
        },

        _cuentasClienteHtml: function (v) {
            var self = this;
            var filas = v.cuentas.map(function (c) {
                var r = _.extend({adelantado: c.semaforo === 'desfase' ? -c.caja_neta : 0}, c);
                return '<tr data-cuenta="' + c.id + '"><td><b>' + esc(c.referencia) + '</b></td><td>' + esc(c.moto) + '</td>' +
                    '<td>' + esc(self._nombreFinanciera(c.financiera_id)) + '</td>' +
                    '<td class="num">' + self._money(c.pagado) + ' <span class="adt_fin__muted">/ ' + self._money(c.total_financiera) + '</span></td>' +
                    '<td class="num">' + self._money(c.cobrado) + ' <span class="adt_fin__muted">/ ' + self._money(c.total_cliente) + '</span></td>' +
                    '<td class="num adt_fin__gain-text"><b>' + self._money(c.ganancia_actual) + '</b></td>' +
                    '<td class="num">' + self._money(c.ganancia_esperada) + '</td><td>' + self._estadoCliente(r) + '</td></tr>';
            }).join('');
            return '<div class="adt_fin__table-wrap"><table class="adt_fin__table adt_fin__table--click"><thead><tr>' +
                '<th>Cuenta</th><th>Moto</th><th>Financiera</th><th class="num">Pagado a financiera</th><th class="num">Cobrado al cliente</th>' +
                '<th class="num">Ganancia lograda</th><th class="num">Ganancia al final</th><th>Estado</th></tr></thead><tbody>' + filas + '</tbody></table></div>';
        },

        // Sugerencias del buscador: clientes que coinciden por nombre, documento, cuenta o placa.
        _renderSugerencias: function () {
            var self = this;
            var $list = this._ref('suggest');
            if (!this.sugerencias.length) {
                $list.removeClass('is-open').empty();
                return;
            }
            $list.addClass('is-open').html(this.sugerencias.map(function (r, i) {
                return '<li role="option" data-cliente="' + r.id + '" class="' + (i === self.sugerenciaActiva ? 'is-active' : '') + '"' +
                    ' aria-selected="' + (i === self.sugerenciaActiva) + '">' +
                    '<span><b>' + esc(r.nombre) + '</b>' + (r.documento ? ' <span class="adt_fin__muted">' + esc(r.documento) + '</span>' : '') + '</span>' +
                    '<span class="adt_fin__suggest-meta">' + r.n + (r.n === 1 ? ' moto' : ' motos') + ' · ganancia ' + esc(self._money(r.ganancia_actual)) + '</span></li>';
            }).join(''));
        },

        _seleccionarCliente: function (id) {
            this.clienteId = id;
            this.financieraId = null;
            this.busqueda = '';
            this.sugerencias = [];
            this._ref('buscar').val('').blur();
            this._renderSugerencias();
            this._hideTip();
            this._render();
            this.$('.adt_fin__scroll').scrollTop(0);
        },

        _onBuscar: function (ev) {
            this.busqueda = ev.currentTarget.value || '';
            this.sugerenciaActiva = -1;
            this.sugerencias = normalizar(this.busqueda).length >= 2 ? this._filasClientes().slice(0, 8) : [];
            this._renderSugerencias();
            this.pageClientes = 0;
            this._renderTablaClientes();
        },

        _onBuscarKey: function (ev) {
            var n = this.sugerencias.length;
            if (ev.key === 'ArrowDown' && n) {
                ev.preventDefault();
                this.sugerenciaActiva = (this.sugerenciaActiva + 1) % n;
                this._renderSugerencias();
            } else if (ev.key === 'ArrowUp' && n) {
                ev.preventDefault();
                this.sugerenciaActiva = (this.sugerenciaActiva - 1 + n) % n;
                this._renderSugerencias();
            } else if (ev.key === 'Enter' && n) {
                ev.preventDefault();
                this._seleccionarCliente(this.sugerencias[Math.max(this.sugerenciaActiva, 0)].id);
            } else if (ev.key === 'Escape') {
                this.sugerencias = [];
                this._renderSugerencias();
            }
        },

        _onBuscarBlur: function () {
            var self = this;
            // Espera para que el clic en una sugerencia llegue antes de cerrar la lista.
            setTimeout(function () {
                self.sugerencias = [];
                self._renderSugerencias();
            }, 200);
        },

        _onSuggestMousedown: function (ev) {
            ev.preventDefault();  // evita que el buscador pierda el foco antes del clic
        },

        _onElegirCliente: function (ev) {
            ev.preventDefault();
            this._seleccionarCliente(parseInt(ev.currentTarget.getAttribute('data-cliente'), 10));
        },

        _onQuitarCliente: function () {
            this.clienteId = null;
            this._render();
        },

        _onSortClientes: function (ev) {
            var key = ev.currentTarget.getAttribute('data-sort-clientes');
            this.sortClientes = {key: key, dir: this.sortClientes.key === key ? -this.sortClientes.dir : (key === 'nombre' ? 1 : -1)};
            this._renderTablaClientes();
        },

        _onPageClientes: function (ev) {
            this.pageClientes += parseInt(ev.currentTarget.getAttribute('data-page-clientes'), 10);
            this._renderTablaClientes();
        },

        _comoSeLeeHtml: function () {
            return '<details class="adt_fin__howto"><summary>¿Cómo se calculan estos números?</summary><ul>' +
                '<li><b>Ganancia lograda:</b> lo cobrado a cada cliente por encima de lo que cuesta su financiera.</li>' +
                '<li><b>Ganancia al final:</b> total del cronograma del cliente menos total del cronograma con la financiera.</li>' +
                '<li><b>Falta pagar:</b> cuotas a la financiera cuya fecha aún no llega. Las cuotas vencidas se consideran pagadas.</li>' +
                '<li><b>Entra cada mes:</b> saldo de las cuotas de clientes que vencen ese mes. Las cuotas ya vencidas se muestran aparte.</li>' +
                '<li><b>ADT adelantando:</b> cuentas donde ya se pagó a la financiera más de lo cobrado al cliente.</li>' +
                '</ul></details>';
        },

        // ------------------------------------------------------------------ acciones
        _onRefresh: function () {
            var self = this;
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true).text('Actualizando…');
            this._load().then(function () {
                self._render();
            }).finally(function () {
                $btn.prop('disabled', false).text('Actualizar');
            });
        },

        _onFiltrar: function (ev) {
            var raw = ev.currentTarget.getAttribute('data-financiera');
            var id = raw === 'todas' ? null : parseInt(raw, 10);
            this.financieraId = this.financieraId === id ? null : id;
            this._hideTip();
            this._render();
            this.$('.adt_fin__scroll').scrollTop(0);
        },

        _onOpenDetalle: function () {
            var domain = [['fin_monto_total', '>', 0]];
            if (this.financieraId !== null) {
                domain.push(['tipo_financiera_id', '=', this.financieraId || false]);
            }
            if (this.clienteId !== null) {
                domain.push(['partner_id', '=', this.clienteId || false]);
            }
            var vistas = this.data.vistas;
            this.do_action({
                type: 'ir.actions.act_window',
                name: 'Detalle por vehículo' + (this.clienteId !== null ? ' - ' + this._nombreCliente(this.clienteId) :
                    this.financieraId !== null ? ' - ' + this._nombreFinanciera(this.financieraId) : ''),
                res_model: 'adt.comercial.cuentas',
                views: [[vistas.lista, 'list'], [vistas.formulario, 'form']],
                search_view_id: [vistas.busqueda],
                domain: domain,
                target: 'current',
            });
        },

        _onOpenCuenta: function (ev) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'adt.comercial.cuentas',
                res_id: parseInt(ev.currentTarget.getAttribute('data-cuenta'), 10),
                views: [[this.data.vistas.formulario, 'form']],
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

    core.action_registry.add('adt_financiera_dashboard', FinancieraDashboard);

    return FinancieraDashboard;
});
