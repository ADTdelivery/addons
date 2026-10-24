odoo.define('adt_flota_360.CobranzaRentabilidad', function (require) {
    'use strict';

    /**
     * Cobranza y rentabilidad (gerencia), contada como una historia de arriba a abajo:
     *   titular de la semana → ¿nos están pagando? → ¿cuánto nos cuesta? → ¿qué nos queda? → ¿qué motos nos dejan más?
     * Debajo del buscador está la lista de clientes: al elegir uno, toda la historia es de ese cliente.
     * El detalle (tablas y método) queda plegado al final.
     *
     * Hereda de "Cartera y financieras" sus datos y utilidades; los montos llegan en céntimos enteros.
     */
    var core = require('web.core');
    var CarteraReporte = require('adt_comercial.CarteraReporte');

    var esc = _.escape;
    var PERIODOS = [4, 8, 12, 26];
    var POR_PAGINA = 20;
    var CLIENTES_VISIBLES = 8;
    var SITUACION = {
        en_curso: ['En curso', 'info'], aprobado: ['Aprobado', 'info'], pagado: ['Pagada', 'pos'],
        recuperada: ['Recuperada', 'neg'], anulada: ['Anulada', 'muted'],
    };
    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

    function normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim();
    }

    function sumar(filas, fn) {
        return filas.reduce(function (acc, f) { return acc + (fn(f) || 0); }, 0);
    }

    function fecha(iso) {
        if (!iso) { return '—'; }
        var p = iso.split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    }

    // Lunes ISO -> "13–19 oct".
    function semanaCorta(iso) {
        var d = moment(iso);
        var fin = d.clone().add(6, 'days');
        return d.date() + (d.month() === fin.month() ? '' : ' ' + MESES[d.month()]) + '–' +
            fin.date() + ' ' + MESES[fin.month()];
    }

    function plural(n, uno, varios) {
        return n + ' ' + (n === 1 ? uno : varios);
    }

    var COLUMNAS_MOTO = [
        {key: 'placa', label: 'Placa', tipo: 'texto'},
        {key: 'clientes', label: 'Cliente(s)', tipo: 'texto'},
        {key: 'situacion', label: 'Situación', tipo: 'texto'},
        {key: 'creditos', label: 'Créditos', tipo: 'entero', title: 'Créditos de la moto (todos los clientes)'},
        {key: 'refinanciamientos', label: 'Refin.', tipo: 'entero', title: 'Refinanciamientos detectados'},
        {key: 'recaudado', label: 'Recaudado', tipo: 'monto', title: 'Inicial + cuotas + cargos de refinanciamiento + moras cobradas'},
        {key: 'fin_pagado', label: 'Pagado financiera', tipo: 'monto', title: 'Cuotas de la financiera ya vencidas (ADT las paga en su fecha)'},
        {key: 'ganado_hoy', label: 'Ganado hasta hoy', tipo: 'monto', signo: true, title: 'Recaudado − pagado a la financiera'},
        {key: 'por_cobrar', label: 'Por cobrar', tipo: 'monto', title: 'Lo que falta cobrar del crédito en curso'},
        {key: 'fin_pendiente', label: 'Falta pagar fin.', tipo: 'monto'},
        {key: 'ganancia', label: 'Ganancia total', tipo: 'monto', signo: true,
            title: 'Recaudado + por cobrar − total del plan de la financiera'},
    ];

    var CobranzaRentabilidad = CarteraReporte.extend({
        template: 'adt_flota_360.CobranzaRentabilidad',

        events: _.extend({}, CarteraReporte.prototype.events, {
            'click [data-semanas]': '_onSemanas',
            'click [data-moto-sort]': '_onMotoSort',
            'click [data-moto-pagina]': '_onMotoPagina',
            'click [data-buscar]': '_onBuscarCliente',
            'click [data-action="limpiar"]': '_onLimpiar',
            'click [data-action="mas-clientes"]': '_onMasClientes',
            'click details[data-detalle] > summary': '_onDetalle',
        }),

        init: function () {
            this._super.apply(this, arguments);
            this.nSemanas = 12;
            this.motoSort = {key: 'ganancia', dir: -1};
            this.motoPagina = 0;
            this.todosClientes = false;
            this.abierto = {};
        },

        _load: function () {
            var self = this;
            return this._rpc({
                model: 'adt.flota360.cobranza.rentabilidad',
                method: 'get_report_data',
                args: [],
            }).then(function (data) {
                self.data = data;
                var texto = function (f) { return normalizar([f.cliente, f.documento, f.referencia, f.placa].join(' ')); };
                data.cuentas.concat(data.recuperadas, data.creditos).forEach(function (f) { f._buscar = texto(f); });
                data.recuperadas.forEach(function (f) {
                    f._cliente = f.documento || f.cliente;
                    f._etiqueta = f.cliente + (f.documento ? ' · ' + f.documento : '');
                });
                data.motos.forEach(function (m) {
                    m.clientes = _.pluck(m.titulares, 'cliente').join(' / ');
                    m.fin_pendiente = m.fin_total - m.fin_pagado;
                    m._buscar = normalizar([m.placa, m.clientes, _.pluck(m.titulares, 'documento').join(' '),
                        m.referencias.join(' ')].join(' '));
                });
                self.clientes = self._agruparClientes(data.creditos);
            });
        },

        // Un cliente puede tener varios créditos (motos): se juntan por documento (o nombre).
        _agruparClientes: function (creditos) {
            var porClave = {};
            creditos.forEach(function (c) {
                var clave = c.documento || c.cliente;
                var k = porClave[clave] || (porClave[clave] = {
                    clave: clave, cliente: c.cliente, documento: c.documento, placas: [],
                    vencido: 0, cubriendo: 0, cuotas: 0, recuperada: false, _buscar: ''});
                if (c.placa && k.placas.indexOf(c.placa) === -1) { k.placas.push(c.placa); }
                k.vencido += c.vencido;
                k.cubriendo += c.cubriendo;
                k.cuotas += c.cuotas_vencidas;
                k.recuperada = k.recuperada || c.estado === 'cancelado';
                k._buscar += ' ' + c._buscar;
            });
            return _.sortBy(_.values(porClave), function (k) { return -(k.cubriendo * 1e6 + k.vencido); });
        },

        // ------------------------------------------------------------------ filtros
        _buscados: function (filas) {
            var q = normalizar(this.busqueda);
            return q ? filas.filter(function (f) { return f._buscar.indexOf(q) !== -1; }) : filas;
        },

        // Índices (en data.semanas) de las semanas visibles: las N cerradas y la semana en curso.
        _indices: function () {
            var total = this.data.semanas.length;
            return _.range(Math.max(total - 1 - this.nSemanas, 0), total);
        },

        _serie: function (creditos, recuperadas) {
            var ultima = this.data.semanas.length - 1;
            return this._indices().map(function (i) {
                var s = {i: i, lunes: this.data.semanas[i], enCurso: i === ultima,
                    esperado: 0, noPagado: 0, cubierto: 0, sigue: 0, morosos: 0, creditos: 0, recuperadas: 0};
                creditos.forEach(function (c) {
                    var f = c.semanas[i];
                    if (!f) { return; }
                    s.esperado += f[0];
                    s.noPagado += f[1];
                    s.cubierto += f[2];
                    s.sigue += f[3];
                    s.creditos += 1;
                    if (f[1] > 0) { s.morosos += 1; }
                });
                recuperadas.forEach(function (r) { s.recuperadas += r.semanas[i] || 0; });
                s.pagado = s.esperado - s.noPagado;
                s.sinCubrir = s.noPagado - s.cubierto;
                s.mora = s.esperado ? s.noPagado / s.esperado : null;
                return s;
            }, this);
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            this._ref('subtitle').text('Al ' + fecha(this.data.hoy) + ' · semanas de lunes a domingo');
            this._renderChips();
            var creditos = this._buscados(this.data.creditos);
            var clientes = this._buscados(this.clientes);
            var serie = this._serie(creditos, this._recuperadas(false));
            var cerradas = serie.filter(function (s) { return !s.enCurso && s.esperado; });
            var ctx = {
                creditos: creditos,
                clientes: clientes,
                uno: this.busqueda && clientes.length === 1 ? clientes[0] : null,
                serie: serie,
                ult: cerradas[cerradas.length - 1],
                ant: cerradas[cerradas.length - 2],
                cartera: this._vista(this._filas()),
                recuperadas: this._recuperadas(false),
                motos: this._buscados(this.data.motos),
            };
            this._ref('body').html(
                this._clientesHtml(ctx) +
                this._titularHtml(ctx) +
                this._capituloPagos(ctx) +
                this._capituloCosto(ctx) +
                this._capituloQueda(ctx) +
                this._capituloMotos(ctx) +
                this._detalleHtml('semanas', 'Ver semana a semana', this._tablaSemanas(serie)) +
                this._detalleHtml('motos', 'Ver todas las motos (' + ctx.motos.length + ')', this._tablaMotos(ctx.motos)) +
                this._metodoCobranzaHtml()
            );
        },

        _renderChips: function () {
            var self = this;
            var chips = PERIODOS.map(function (n) {
                return '<button type="button" class="adt_cart__chip' + (self.nSemanas === n ? ' is-active' : '') +
                    '" data-semanas="' + n + '">' + n + ' semanas</button>';
            }).join('');
            this._ref('chips').html('<div class="adt_cart__chipgroup"><span>Periodo</span>' + chips + '</div>');
        },

        // Lista de clientes, justo debajo del buscador.
        _clientesHtml: function (ctx) {
            var self = this;
            if (ctx.uno) {
                var c = ctx.uno;
                return '<div class="adt_cobr__clientes is-uno"><div class="adt_cobr__cliente is-activo">' +
                    '<span class="adt_cobr__avatar">' + esc(c.cliente.charAt(0)) + '</span>' +
                    '<div><b>' + esc(c.cliente) + '</b><small>' + esc([c.documento].concat(c.placas).filter(Boolean).join(' · ')) + '</small></div>' +
                    this._estadoCliente(c) +
                    '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-action="limpiar">× Ver todos</button></div></div>';
            }
            var lista = this.busqueda ? ctx.clientes : ctx.clientes.filter(function (k) { return k.vencido > 0; });
            var visibles = this.todosClientes ? lista : lista.slice(0, CLIENTES_VISIBLES);
            var titulo = this.busqueda ?
                plural(lista.length, 'cliente coincide', 'clientes coinciden') + ' con "' + esc(this.busqueda) + '"' :
                'Clientes que hoy nos cuestan más';
            if (!lista.length) {
                return '<div class="adt_cobr__clientes"><p class="adt_cobr__clientes-t">' +
                    (this.busqueda ? titulo : 'Ningún cliente en curso tiene cuotas atrasadas') + '</p></div>';
            }
            return '<div class="adt_cobr__clientes"><p class="adt_cobr__clientes-t">' + titulo +
                (this.busqueda ? '<button type="button" class="adt_cobr__link" data-action="limpiar">× Quitar filtro</button>' : '') + '</p>' +
                '<div class="adt_cobr__clientes-grid">' + visibles.map(function (k) {
                    return '<button type="button" class="adt_cobr__cliente" data-buscar="' + esc(k.documento || k.cliente) + '">' +
                        '<span class="adt_cobr__avatar">' + esc(k.cliente.charAt(0)) + '</span>' +
                        '<div><b>' + esc(k.cliente) + '</b><small>' + esc(k.placas.join(' · ') || k.documento) + '</small></div>' +
                        self._estadoCliente(k) + '</button>';
                }).join('') + '</div>' +
                (lista.length > CLIENTES_VISIBLES ? '<button type="button" class="adt_cobr__link" data-action="mas-clientes">' +
                    (this.todosClientes ? 'Ver menos' : 'Ver los ' + lista.length) + '</button>' : '') + '</div>';
        },

        _estadoCliente: function (k) {
            if (k.cubriendo > 0) {
                return '<span class="adt_cobr__pill is-neg" title="Lo que ADT le está adelantando a la financiera">' +
                    this._money(k.cubriendo) + '</span>';
            }
            if (k.vencido > 0) { return '<span class="adt_cobr__pill is-warn">' + plural(k.cuotas, 'cuota', 'cuotas') + ' atrasada' + (k.cuotas === 1 ? '' : 's') + '</span>'; }
            if (k.recuperada) { return '<span class="adt_cobr__pill is-muted">Recuperada</span>'; }
            return '<span class="adt_cobr__pill is-pos">Al día</span>';
        },

        // Titular: lo que pasó la última semana cerrada, en una frase y tres números.
        _titularHtml: function (ctx) {
            var ult = ctx.ult;
            var quien = ctx.uno ? esc(ctx.uno.cliente) : 'los clientes';
            var pagaron = ctx.uno ? 'pagó' : 'pagaron';
            var dejaron = ctx.uno ? 'dejó' : 'dejaron';
            var frase;
            if (!ult) {
                frase = 'No hubo cuotas por cobrar en el periodo elegido.';
            } else if (!ult.noPagado) {
                frase = 'La semana del <b>' + semanaCorta(ult.lunes) + '</b> ' + quien + ' ' + pagaron + ' todo a tiempo: ' +
                    '<b>' + this._money(ult.esperado) + '</b>.';
            } else {
                var dif = ctx.ant && ctx.ant.mora !== null ? ult.mora - ctx.ant.mora : null;
                frase = 'La semana del <b>' + semanaCorta(ult.lunes) + '</b> ' + quien + ' ' + dejaron + ' de pagarnos ' +
                    '<b class="neg">' + this._money(ult.noPagado) + '</b> de ' + this._money(ult.esperado) +
                    (dif === null ? '' : dif > 0.005 ? ', <b class="neg">más</b> que la semana anterior' :
                        dif < -0.005 ? ', <b class="pos">menos</b> que la semana anterior' : ', igual que la semana anterior') +
                    '. Para seguir al día con la financiera, ADT puso <b>' + this._money(ult.cubierto) + '</b>.';
            }
            var cubriendo = sumar(ctx.creditos, function (c) { return c.cubriendo; });
            var ganancia = sumar(ctx.motos, function (m) { return m.ganancia; });
            var stat = function (label, valor, tono, sub) {
                return '<div class="adt_cobr__stat' + (tono ? ' is-' + tono : '') + '"><span>' + label + '</span><b>' + valor + '</b>' +
                    (sub ? '<small>' + sub + '</small>' : '') + '</div>';
            };
            return '<section class="adt_cobr__titular"><p class="adt_cobr__frase">' + frase + '</p><div class="adt_cobr__stats">' +
                stat('Morosidad de la semana', ult ? this._pct(ult.mora) : '—', ult && ult.mora > 0.1 ? 'neg' : '',
                    ult ? plural(ult.morosos, 'crédito no pagó', 'créditos no pagaron') : '') +
                stat('ADT está adelantando hoy', this._money(cubriendo), cubriendo ? 'neg' : 'pos', 'por cuotas atrasadas') +
                stat(ctx.uno ? 'Su moto nos dejará' : 'Las motos nos dejarán', this._money(ganancia), ganancia < 0 ? 'neg' : 'pos',
                    ctx.uno ? 'al terminar de pagar' : 'al terminar · ' + this._money(ctx.motos.length ? Math.round(ganancia / ctx.motos.length) : 0) + ' por moto') +
                '</div></section>';
        },

        _capitulo: function (num, pregunta, respuesta, cuerpo) {
            return '<section class="adt_cobr__cap"><header><span>' + num + '</span><div><h2>' + esc(pregunta) + '</h2>' +
                '<p>' + respuesta + '</p></div></header>' + cuerpo + '</section>';
        },

        // 1. ¿Nos están pagando? Barras por semana; para un cliente, su semáforo de pagos.
        _capituloPagos: function (ctx) {
            var cerradas = ctx.serie.filter(function (s) { return !s.enCurso && s.esperado; });
            var esperado = sumar(cerradas, function (s) { return s.esperado; });
            var noPagado = sumar(cerradas, function (s) { return s.noPagado; });
            var peor = _.max(cerradas, function (s) { return s.mora; });
            var respuesta = !cerradas.length ? 'Sin cuotas en el periodo.' :
                'En ' + plural(cerradas.length, 'semana', 'semanas') + ' quedó sin pagar el <b>' + this._pct(esperado ? noPagado / esperado : null) +
                '</b> de lo que debían' + (peor && peor.mora > 0 ? '. La peor fue la del ' + semanaCorta(peor.lunes) + ' (' + this._pct(peor.mora) + ').' : '.');
            var cuerpo = ctx.uno ? this._semaforo(ctx.serie) : this._grafico(ctx.serie);
            return this._capitulo(1, '¿Nos están pagando?', respuesta, cuerpo);
        },

        // Un cuadro por semana: verde pagó, ámbar pagó una parte, rojo no pagó, gris sin cuota.
        _semaforo: function (serie) {
            var self = this;
            return '<div class="adt_cobr__semaforo">' + serie.map(function (s, k) {
                var d = moment(s.lunes);
                // El mes solo en la primera semana y cuando cambia.
                var etiqueta = d.date() + (!k || d.month() !== moment(serie[k - 1].lunes).month() ? ' ' + MESES[d.month()] : '');
                var cls = !s.esperado ? 'is-vacio' : !s.noPagado ? 'is-ok' : s.noPagado < s.esperado ? 'is-parcial' : 'is-no';
                var tip = semanaCorta(s.lunes) + (s.esperado ? ': debía ' + self._money(s.esperado) +
                    (s.noPagado ? ', no pagó ' + self._money(s.noPagado) : ', pagó a tiempo') : ': sin cuota');
                return '<div class="' + cls + '" title="' + esc(tip) + '"><i></i><small>' + esc(etiqueta) + '</small></div>';
            }).join('') + '</div><ul class="adt_cobr__legend"><li><i class="is-ok"></i>Pagó a tiempo</li>' +
                '<li><i class="is-parcial"></i>Pagó una parte</li><li><i class="is-no"></i>No pagó</li><li><i class="is-vacio"></i>Sin cuota</li></ul>';
        },

        // Barras apiladas por semana: pagaron · no pagaron (lo cubrió ADT) · no pagaron (resto).
        _grafico: function (serie) {
            var self = this;
            var max = _.max(serie.map(function (s) { return s.esperado; })) || 1;
            var W = 640, H = 170, base = H - 20, alto = base - 6;
            var paso = W / serie.length, ancho = Math.max(Math.min(paso - 6, 34), 4);
            var barras = serie.map(function (s, k) {
                var x = k * paso + (paso - ancho) / 2;
                var y = base;
                var segmentos = [[s.pagado, 'is-pagado'], [s.sinCubrir, 'is-resto'], [s.cubierto, 'is-cubierto']].map(function (p) {
                    var h = p[0] / max * alto;
                    if (h <= 0) { return ''; }
                    y -= h;
                    // 2px de separación entre segmentos.
                    return '<rect class="' + p[1] + '" x="' + x.toFixed(1) + '" y="' + (y + 1).toFixed(1) + '" width="' +
                        ancho.toFixed(1) + '" height="' + Math.max(h - 2, 1).toFixed(1) + '" rx="2"/>';
                }).join('');
                var tip = 'Semana ' + semanaCorta(s.lunes) + (s.enCurso ? ' (en curso)' : '') +
                    '\nDebían: ' + self._money(s.esperado) + '\nPagaron a tiempo: ' + self._money(s.pagado) +
                    '\nNo pagaron: ' + self._money(s.noPagado) + ' (' + self._pct(s.mora) + ')' +
                    '\nADT cubrió: ' + self._money(s.cubierto);
                var etiqueta = (k % Math.ceil(serie.length / 8) === 0 || s.enCurso) ?
                    '<text x="' + (x + ancho / 2).toFixed(1) + '" y="' + (H - 4) + '">' + esc(s.enCurso ? 'hoy' :
                        semanaCorta(s.lunes).split('–')[0]) + '</text>' : '';
                return '<g class="adt_cobr__bar' + (s.enCurso ? ' is-curso' : '') + '"><title>' + esc(tip) + '</title>' +
                    '<rect class="is-hit" x="' + (k * paso).toFixed(1) + '" y="0" width="' + paso.toFixed(1) + '" height="' + base + '"/>' +
                    segmentos + '</g>' + etiqueta;
            }).join('');
            return '<div class="adt_cobr__chart"><ul class="adt_cobr__legend">' +
                '<li><i class="is-pagado"></i>Pagaron a tiempo</li><li><i class="is-cubierto"></i>No pagaron · lo puso ADT</li>' +
                '<li><i class="is-resto"></i>No pagaron · ganancia que no llegó</li></ul>' +
                '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Cobranza semanal">' +
                '<line class="adt_cobr__axis" x1="0" x2="' + W + '" y1="' + base + '" y2="' + base + '"/>' + barras + '</svg></div>';
        },

        // 2. ¿Cuánto nos cuesta? Del dinero que ADT puso: cuánto volvió y cuánto sigue afuera.
        _capituloCosto: function (ctx) {
            var cubierto = sumar(ctx.serie, function (s) { return s.cubierto; });
            var sigue = sumar(ctx.serie, function (s) { return s.sigue; });
            var recuperadas = sumar(ctx.serie, function (s) { return s.recuperadas; });
            var afuera = sigue + recuperadas;
            var respuesta = !cubierto && !recuperadas ?
                'En ' + plural(this.nSemanas, 'semana', 'semanas') + ' ADT no tuvo que poner dinero por clientes que no pagaron.' :
                'En ' + plural(this.nSemanas, 'semana', 'semanas') + ' ADT puso <b>' + this._money(cubierto + recuperadas) +
                    '</b> para no atrasarse con la financiera. Hoy siguen afuera <b class="neg">' + this._money(afuera) + '</b>.';
            var paso = function (label, cents, tono, signo) {
                return '<div class="adt_cobr__paso' + (tono ? ' is-' + tono : '') + '">' + (signo ? '<em>' + signo + '</em>' : '') +
                    '<span>' + label + '</span><b>' + this._money(cents) + '</b></div>';
            }.bind(this);
            var flujo = '<div class="adt_cobr__flujo">' +
                paso('Cubrimos por clientes atrasados', cubierto, '') +
                paso('Nos devolvieron al pagar tarde', cubierto - sigue, 'pos', '−') +
                paso('Pagamos por motos recuperadas', recuperadas, '', '+') +
                paso('Sigue saliendo de ADT', afuera, 'neg', '=') + '</div>';
            var motos = ctx.recuperadas.filter(function (r) { return r.pendiente > 0; });
            var nota = motos.length ? '<p class="adt_cobr__nota">' + plural(motos.length, 'moto recuperada', 'motos recuperadas') +
                ' sin nuevo cliente: aún debemos <b>' + this._money(sumar(motos, function (r) { return r.pendiente; })) +
                '</b> a la financiera por ellas.</p>' : '';
            return this._capitulo(2, '¿Cuánto nos cuesta?', respuesta, flujo + nota);
        },

        // 3. ¿Qué nos queda? Nos deben − debemos = nos queda.
        _capituloQueda: function (ctx) {
            var v = ctx.cartera;
            if (!v.n) {
                return this._capitulo(3, '¿Qué nos queda?', 'Sin créditos en curso para esta búsqueda.', '');
            }
            var termino = function (label, cents, tono) {
                return '<div class="adt_cobr__termino' + (tono ? ' is-' + tono : '') + '"><span>' + label + '</span><b>' +
                    this._money(cents) + '</b></div>';
            }.bind(this);
            var atrasado = v.porCobrar ? v.vencido / v.porCobrar : 0;
            return this._capitulo(3, '¿Qué nos queda?',
                'Cuando ' + (ctx.uno ? 'termine de pagar' : 'los ' + plural(v.n, 'crédito', 'créditos') + ' en curso terminen') +
                ', a ADT le quedarán <b class="' + (v.gananciaPorRealizar < 0 ? 'neg' : 'pos') + '">' + this._money(v.gananciaPorRealizar) + '</b>.',
                '<div class="adt_cobr__ecuacion">' + termino('Nos deben', v.porCobrar) + '<em>−</em>' +
                termino('Debemos a la financiera', v.deuda) + '<em>=</em>' +
                termino('Nos queda', v.gananciaPorRealizar, v.gananciaPorRealizar < 0 ? 'neg' : 'pos') + '</div>' +
                (v.vencido ? '<div class="adt_cobr__barra" title="' + esc(this._pct(atrasado)) + ' de lo que nos deben ya venció">' +
                    '<i style="width:' + Math.max(atrasado * 100, 1).toFixed(1) + '%"></i></div>' +
                    '<p class="adt_cobr__nota"><b>' + this._money(v.vencido) + '</b> (' + this._pct(atrasado) + ') de lo que nos deben ya está atrasado.</p>' : ''));
        },

        // 4. ¿Qué motos nos dejan más? Las que más ganan y las que menos (o pierden).
        _capituloMotos: function (ctx) {
            var self = this;
            var motos = ctx.motos;
            if (!motos.length) {
                return this._capitulo(4, '¿Cuánto nos deja cada moto?', 'Ninguna moto coincide con la búsqueda.', '');
            }
            var total = sumar(motos, function (m) { return m.ganancia; });
            var hoy = sumar(motos, function (m) { return m.ganado_hoy; });
            var refin = sumar(motos, function (m) { return m.refinanciamientos; });
            var respuesta = ctx.uno && motos.length === 1 ?
                'Esta moto ya nos dejó <b>' + this._money(hoy) + '</b> y al terminar nos dejará <b class="' + (total < 0 ? 'neg' : 'pos') + '">' +
                    this._money(total) + '</b>' + (refin ? ', contando ' + plural(refin, 'refinanciamiento', 'refinanciamientos') : '') + '.' :
                'Ya ganamos <b>' + this._money(hoy) + '</b> y al terminar ganaremos <b class="' + (total < 0 ? 'neg' : 'pos') + '">' +
                    this._money(total) + '</b> con ' + plural(motos.length, 'moto', 'motos') +
                    (refin ? ' (incluye ' + plural(refin, 'refinanciamiento', 'refinanciamientos') + ')' : '') + '.';
            var orden = _.sortBy(motos, 'ganancia');
            var mejores = orden.slice(-3).reverse();
            var peores = orden.slice(0, 3).filter(function (m) { return mejores.indexOf(m) === -1; });
            var max = _.max(motos.map(function (m) { return Math.abs(m.ganancia); })) || 1;
            var fila = function (m) {
                return '<li data-buscar="' + esc(m.placa || m.titulares[0] && m.titulares[0].documento || '') + '" title="Ver solo esta moto">' +
                    '<span><b>' + esc(m.placa || '—') + '</b> ' + esc(m.clientes) +
                    (m.situacion === 'recuperada' ? ' <em class="adt_cobr__pill is-muted">recuperada</em>' : '') +
                    (m.refinanciamientos ? ' <em class="adt_cobr__pill is-muted">' + m.refinanciamientos + ' refin.</em>' : '') + '</span>' +
                    '<i class="' + (m.ganancia < 0 ? 'is-neg' : '') + '" style="width:' + (Math.abs(m.ganancia) / max * 100).toFixed(1) + '%"></i>' +
                    '<b class="' + (m.ganancia < 0 ? 'neg' : '') + '">' + self._money(m.ganancia) + '</b></li>';
            };
            var cuerpo = ctx.uno && motos.length <= 3 ? '<ul class="adt_cobr__ranking">' + motos.map(fila).join('') + '</ul>' :
                '<div class="adt_cobr__rankings"><div><h3>Las que más nos dejan</h3><ul class="adt_cobr__ranking">' + mejores.map(fila).join('') + '</ul></div>' +
                (peores.length ? '<div><h3>' + (peores[0].ganancia < 0 ? 'Las que nos hacen perder' : 'Las que menos nos dejan') +
                    '</h3><ul class="adt_cobr__ranking">' + peores.map(fila).join('') + '</ul></div>' : '') + '</div>';
            return this._capitulo(4, '¿Cuánto nos deja cada moto?', respuesta, cuerpo);
        },

        // ------------------------------------------------------------------ detalle (plegado)
        _detalleHtml: function (clave, titulo, cuerpo) {
            return '<details class="adt_cart__card adt_cobr__detalle" data-detalle="' + clave + '"' +
                (this.abierto[clave] || this.imprimiendo ? ' open' : '') + '><summary>' + esc(titulo) + '</summary>' + cuerpo + '</details>';
        },

        _tablaSemanas: function (serie) {
            var self = this;
            var celda = function (c, cls) {
                return '<td class="num' + (cls ? ' ' + cls : '') + '">' + (c ? self._money(c) : '—') + '</td>';
            };
            var filas = serie.slice().reverse().map(function (s) {
                return '<tr' + (s.enCurso ? ' class="is-muted"' : '') + '><td>' + esc(semanaCorta(s.lunes)) +
                    (s.enCurso ? ' · en curso' : '') + '</td>' + celda(s.esperado) + celda(s.pagado) + celda(s.noPagado) +
                    '<td class="num' + (s.mora > 0.1 ? ' neg' : '') + '">' + self._pct(s.mora) + '</td>' +
                    '<td class="num">' + (s.creditos ? s.morosos + ' / ' + s.creditos : '—') + '</td>' +
                    celda(s.cubierto, 'is-strong') + celda(s.cubierto - s.sigue) + celda(s.sigue) + celda(s.recuperadas) + '</tr>';
            }).join('');
            return '<div class="adt_cart__tablewrap adt_cart__tablewrap--full"><table class="adt_cart__table"><thead><tr>' +
                '<th>Semana</th><th class="num">Debían pagar</th><th class="num">Pagaron a tiempo</th><th class="num">No pagaron</th>' +
                '<th class="num">Morosidad</th><th class="num" title="Créditos que no pagaron completa su cuota / créditos con cuota esa semana">Créditos morosos</th>' +
                '<th class="num">ADT cubrió</th><th class="num">Ya nos devolvieron</th><th class="num">Sigue pendiente</th>' +
                '<th class="num" title="Cuotas a la financiera de motos recuperadas: las paga ADT por completo">Motos recuperadas</th>' +
                '</tr></thead><tbody>' + filas + '</tbody></table></div>';
        },

        _tablaMotos: function (motos) {
            var self = this;
            if (!motos.length) { return '<p class="adt_cart__note">Ninguna moto coincide con la búsqueda.</p>'; }
            var tot = function (k) { return sumar(motos, function (m) { return m[k]; }); };
            var s = this.motoSort;
            var col = _.findWhere(COLUMNAS_MOTO, {key: s.key});
            var ordenadas = _.sortBy(motos, function (m) {
                var v = s.key === 'situacion' ? (SITUACION[m.situacion] || [m.situacion])[0] : m[s.key];
                return col.tipo === 'texto' ? normalizar(v) : v;
            });
            if (s.dir < 0) { ordenadas.reverse(); }
            var paginas = Math.ceil(ordenadas.length / POR_PAGINA);
            this.motoPagina = Math.min(this.motoPagina, paginas - 1);
            var visibles = this.imprimiendo ? ordenadas : ordenadas.slice(this.motoPagina * POR_PAGINA, (this.motoPagina + 1) * POR_PAGINA);
            var cabecera = COLUMNAS_MOTO.map(function (c) {
                return '<th class="is-sortable' + (c.tipo === 'texto' ? '' : ' num') + (s.key === c.key ? ' is-sorted' : '') +
                    '" data-moto-sort="' + c.key + '"' + (c.title ? ' title="' + esc(c.title) + '"' : '') + '>' + esc(c.label) +
                    (s.key === c.key ? (s.dir > 0 ? ' ▴' : ' ▾') : '') + '</th>';
            }).join('');
            var celda = function (m, c) {
                if (c.key === 'situacion') {
                    var st = SITUACION[m.situacion] || [m.situacion, 'muted'];
                    return '<td><span class="adt_cobr__pill is-' + st[1] + '">' + esc(st[0]) + '</span>' +
                        (m.situacion === 'recuperada' && m.desde ? '<small class="adt_cart__muted"> desde ' + fecha(m.desde) + '</small>' : '') + '</td>';
                }
                if (c.key === 'clientes') {
                    return '<td class="adt_cobr__titulares">' + m.titulares.map(function (t) {
                        return esc(t.cliente) + (t.documento ? '<small class="adt_cart__muted"> ' + esc(t.documento) + '</small>' : '');
                    }).join('<br/>') + '</td>';
                }
                if (c.key === 'fin_pagado' || c.key === 'fin_pendiente') {
                    return '<td class="num">' + (m.con_financiera ? self._money(m[c.key]) : '<span class="adt_cart__muted">sin plan</span>') + '</td>';
                }
                if (c.tipo === 'monto') {
                    return '<td class="num' + (c.signo && m[c.key] < 0 ? ' neg' : c.signo ? ' pos is-strong' : '') + '">' + self._money(m[c.key]) + '</td>';
                }
                return '<td' + (c.tipo === 'entero' ? ' class="num"' : '') + '>' + esc(m[c.key] || (c.tipo === 'entero' ? '0' : '—')) + '</td>';
            };
            var filas = visibles.map(function (m) {
                return '<tr data-cuenta="' + m.cuenta_id + '" title="Abrir el último crédito de la moto">' +
                    COLUMNAS_MOTO.map(function (c) { return celda(m, c); }).join('') + '</tr>';
            }).join('');
            var totales = '<tr>' + COLUMNAS_MOTO.map(function (c) {
                if (c.key === 'placa') { return '<td>Total</td>'; }
                if (c.tipo === 'monto') { return '<td class="num' + (c.signo && tot(c.key) < 0 ? ' neg' : '') + '">' + self._money(tot(c.key)) + '</td>'; }
                if (c.tipo === 'entero') { return '<td class="num">' + tot(c.key) + '</td>'; }
                return '<td></td>';
            }).join('') + '</tr>';
            var pager = paginas > 1 && !this.imprimiendo ? '<div class="adt_cart__pager">' +
                '<span>' + (this.motoPagina * POR_PAGINA + 1) + '–' + Math.min((this.motoPagina + 1) * POR_PAGINA, ordenadas.length) +
                ' de ' + ordenadas.length + '</span>' +
                '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-moto-pagina="' + (this.motoPagina - 1) + '"' +
                    (this.motoPagina ? '' : ' disabled') + '>‹ Anterior</button>' +
                '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-moto-pagina="' + (this.motoPagina + 1) + '"' +
                    (this.motoPagina < paginas - 1 ? '' : ' disabled') + '>Siguiente ›</button></div>' : '';
            var sinFin = motos.filter(function (m) { return !m.con_financiera; }).length;
            return '<div class="adt_cart__tablewrap"><table class="adt_cart__table adt_cart__table--detalle adt_cobr__motos"><thead><tr>' +
                cabecera + '</tr></thead><tbody>' + filas + '</tbody><tfoot>' + totales + '</tfoot></table></div>' + pager +
                (sinFin ? '<p class="adt_cart__note">' + sinFin + (sinFin === 1 ? ' moto no tiene' : ' motos no tienen') +
                    ' plan de la financiera cargado: su ganancia no descuenta ese costo.</p>' : '');
        },

        _metodoCobranzaHtml: function () {
            return '<details class="adt_cart__card adt_cart__method"><summary>¿Cómo se calcula?</summary><ul>' +
                '<li><b>Semanas</b> de lunes a domingo. Cada cuota cuenta en la semana de su fecha; un pago parcial y su subcuota son la misma cuota. La semana en curso solo incluye lo ya vencido.</li>' +
                '<li><b>No pagaron</b>: lo que quedó sin pagar al cerrar el domingo. <b>Morosidad</b> = no pagaron ÷ debían pagar.</li>' +
                '<li><b>Lo puso ADT</b>: a cada cuota del cliente le toca la parte de la financiera de su periodo (cuota mensual repartida por días). ADT pone lo menor entre lo que el cliente no pagó y esa parte; el resto es ganancia que no llegó, no sale de caja. Si el cliente paga tarde, se lo devuelve.</li>' +
                '<li><b>Motos recuperadas</b>: retiradas al cliente y sin nuevo crédito; ADT paga su financiera completa desde que el crédito pasó a cancelado.</li>' +
                '<li><b>¿Qué nos queda?</b>: igual que "Cartera y financieras" (créditos en curso).</li>' +
                '<li><b>Ganancia por moto</b>: todos sus créditos (original, refinanciamientos, reventas). Inicial + cuotas + cargos + moras cobradas + lo que falta cobrar − el plan completo de la financiera. Una moto recuperada puede salir en pérdida: no se cuenta lo que vale la moto.</li>' +
                '<li><b>Limitación</b>: al refinanciar, el sistema borra las cuotas impagas; esas semanas quedan con lo que sí se pagó.</li>' +
                '</ul></details>';
        },

        // ------------------------------------------------------------------ eventos
        _filtrar: function (texto) {
            this.busqueda = texto;
            this._ref('buscar').val(texto);
            this.motoPagina = 0;
            this.todosClientes = false;
            this._render();
        },

        _onSemanas: function (ev) {
            this.nSemanas = parseInt($(ev.currentTarget).data('semanas'), 10);
            this._render();
        },

        _onMotoSort: function (ev) {
            var key = $(ev.currentTarget).data('moto-sort');
            var col = _.findWhere(COLUMNAS_MOTO, {key: key});
            this.motoSort = {key: key, dir: this.motoSort.key === key ? -this.motoSort.dir : (col.tipo === 'texto' ? 1 : -1)};
            this.motoPagina = 0;
            this._render();
        },

        _onMotoPagina: function (ev) {
            this.motoPagina = parseInt($(ev.currentTarget).data('moto-pagina'), 10);
            this._render();
            this.$('.adt_cobr__motos')[0].scrollIntoView({block: 'nearest'});
        },

        _onBuscarCliente: function (ev) {
            this._filtrar(String($(ev.currentTarget).data('buscar')));
            this.$('.adt_cart__scroll').scrollTop(0);
        },

        _onLimpiar: function () {
            this._filtrar('');
            this._ref('buscar').focus();
        },

        _onMasClientes: function () {
            this.todosClientes = !this.todosClientes;
            this._render();
        },

        // Recuerda qué detalles están abiertos al volver a pintar (el clic aún no cambió el estado).
        _onDetalle: function (ev) {
            var detalle = ev.currentTarget.parentNode;
            this.abierto[$(detalle).data('detalle')] = !detalle.open;
        },

        _onBuscar: _.debounce(function (ev) {
            this.busqueda = ev.target.value;
            this.motoPagina = 0;
            this.todosClientes = false;
            this._render();
        }, 200),
    });

    core.action_registry.add('adt_flota_360_cobranza_rentabilidad', CobranzaRentabilidad);
    return CobranzaRentabilidad;
});
