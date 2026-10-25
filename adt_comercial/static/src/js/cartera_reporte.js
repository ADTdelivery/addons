odoo.define('adt_comercial.CarteraReporte', function (require) {
    'use strict';

    /**
     * Cartera y financieras: cuentas por cobrar (clientes → ADT), cuentas por pagar
     * (ADT → financieras) y lo que le queda a ADT.
     *
     * Precisión: el servidor envía todos los montos en céntimos enteros. Aquí solo se suman
     * enteros (exacto) y se da formato al final; nunca se opera con decimales.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;
    var TRAMOS = {'1_30': 'Atrasadas hasta 1 mes', '31_60': 'Atrasadas de 1 a 2 meses', '61_90': 'Atrasadas de 2 a 3 meses', '91_mas': 'Atrasadas más de 3 meses (difíciles de cobrar)'};
    var ESTADOS = {borrador: 'Borrador', aprobado: 'Aprobado', en_curso: 'En curso', cancelado: 'Cancelado', pagado: 'Pagado'};
    var FILTROS = [['todas', 'Todos'], ['atraso', 'Con atraso'], ['contra', 'Saldo en contra'], ['alertas', 'Con alertas']];

    function normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim();
    }

    function sumar(filas, fn) {
        return filas.reduce(function (acc, f) { return acc + (fn(f) || 0); }, 0);
    }

    // Céntimos enteros -> "1,234.56" sin pasar por decimales binarios.
    function numero(cents) {
        var abs = Math.abs(cents);
        var entero = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        var dec = ('0' + (abs % 100)).slice(-2);
        return entero + '.' + dec;
    }

    // Razón entre dos montos en céntimos (enteros), como porcentaje con 2 decimales.
    function ratio(parte, total) {
        return total > 0 ? parte / total : null;
    }

    var POR_PAGINA = 20;
    var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
        'septiembre', 'octubre', 'noviembre', 'diciembre'];

    function mesLargo(clave) {
        var p = clave.split('-');
        var nombre = MESES[parseInt(p[1], 10) - 1];
        return nombre.charAt(0).toUpperCase() + nombre.slice(1) + ' ' + p[0];
    }

    function fecha(iso) {
        if (!iso) { return '—'; }
        var p = iso.split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    }

    var COLUMNAS = [
        {key: 'documento', label: 'DNI', tipo: 'texto', valor: function (f) { return f.documento; }},
        {key: 'cliente', label: 'Cliente', tipo: 'texto', valor: function (f) { return f.cliente; }},
        {key: 'placa', label: 'Placa', tipo: 'texto', valor: function (f) { return f.placa; }},
        {key: 'estado', label: 'Estado', tipo: 'texto', valor: function (f) { return ESTADOS[f.estado] || f.estado; }},
        {key: 'fin', label: 'Culmina', tipo: 'fecha', valor: function (f) { return f.fin; },
            title: 'Última cuota a la financiera'},
        {key: 'restantes', label: 'Cuotas rest.', tipo: 'entero', valor: function (f) { return f.cliente_resumen.cuotas_restantes; }},
        {key: 'cuota', label: 'Cuota cliente', tipo: 'monto', valor: function (f) { return f.cliente_resumen.cuota; }},
        {key: 'por_cobrar', label: 'Por cobrar', tipo: 'monto', total: true, valor: function (f) { return f.cliente_resumen.por_cobrar; },
            title: 'Saldo de todas las cuotas del cliente sin pagar (vencidas y por vencer)'},
        {key: 'vencido', label: 'Vencido', tipo: 'monto', total: true, valor: function (f) { return f.cliente_resumen.vencido; }},
        {key: 'atraso', label: 'Días atraso', tipo: 'entero', valor: function (f) { return f.cliente_resumen.dias_atraso; },
            title: 'Días desde la cuota impaga más antigua'},
        {key: 'cuota_fin', label: 'Cuota financiera', tipo: 'monto', total: true,
            valor: function (f) { return f.financiera.cuotas_pendientes ? f.financiera.cuota : 0; },
            title: 'Próxima cuota que ADT paga a la financiera'},
        {key: 'deuda', label: 'Deuda nominal', tipo: 'monto', total: true, valor: function (f) { return f.financiera.pendiente; },
            title: 'Suma de las cuotas a la financiera que faltan pagar (capital + interés + seguros + aportes)'},
        {key: 'liquidar', label: 'Para liquidar hoy', tipo: 'monto', total: true, valor: function (f) { return f.financiera.para_liquidar; },
            title: 'Capital pendiente + interés devengado a hoy. Solo con cronograma PDF.'},
        {key: 'a_favor', label: 'Saldo a favor', tipo: 'monto', total: true, valor: function (f) { return Math.max(saldo(f), 0); },
            title: 'Por cobrar − para liquidar (o − deuda nominal si no hay PDF, marcado con N)'},
        {key: 'en_contra', label: 'Saldo en contra', tipo: 'monto', total: true, valor: function (f) { return Math.min(saldo(f), 0); }},
        {key: 'ganancia', label: 'Ganancia del crédito', tipo: 'monto', total: true, valor: function (f) { return f.posicion.ganancia_esperada; },
            title: 'Total del cronograma del cliente − total pagado y por pagar a la financiera'},
    ];

    function cumpleFiltro(f, filtro) {
        if (filtro === 'atraso') { return f.cliente_resumen.vencido > 0; }
        if (filtro === 'contra') { return saldo(f) < 0; }
        if (filtro === 'alertas') { return f.alertas.length > 0; }
        return true;
    }

    // Saldo a favor (+) / en contra (−): contra el monto para liquidar; sin PDF, contra la deuda nominal.
    function saldo(f) {
        return f.posicion.neto_liquidar !== null ? f.posicion.neto_liquidar : f.posicion.neto_nominal;
    }

    var CarteraReporte = AbstractAction.extend({
        template: 'adt_comercial.CarteraReporte',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="exportar"]': '_onExportar',
            'click [data-action="imprimir"]': '_onImprimir',
            'click [data-financiera]': '_onFinanciera',
            'click [data-filtro]': '_onFiltro',
            'click [data-estado]': '_onEstado',
            'click [data-action="limpiar-filtros"]': '_onLimpiarFiltros',
            'click [data-sort]': '_onSort',
            'click [data-pagina]': '_onPagina',
            'click [data-action="toggle-meses"]': '_onToggleMeses',
            'click [data-cuenta]': '_onCuenta',
            'input [data-ref="buscar"]': '_onBuscar',
            'change [data-ref="cliente-recuperado"]': '_onClienteRecuperado',
            'click [data-action="limpiar-recuperado"]': '_onLimpiarRecuperado',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.financieraId = null;
            this.filtro = 'todas';
            this.estado = undefined;  // estado del cronograma; null = todos. Por defecto, la cartera activa.
            this.busqueda = '';
            this.clienteRecuperado = null;  // clave del cliente elegido en el punto 4
            this.textoRecuperado = '';
            this.sort = {key: 'saldo', dir: 1};
            this.pagina = 0;
            this.mesesAbierto = false;
            this.imprimiendo = false;
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
            return this._rpc({
                model: 'adt.comercial.cartera.reporte',
                method: 'get_report_data',
                args: [],
            }).then(function (data) {
                self.data = data;
                if (self.estado === undefined) {
                    self.estado = data.estado_activo;
                }
                data.cuentas.concat(data.recuperadas).forEach(function (f) {
                    f._buscar = normalizar([f.cliente, f.documento, f.referencia, f.placa].join(' '));
                });
                data.recuperadas.forEach(function (f) {
                    f._cliente = f.documento || f.cliente;
                    f._etiqueta = f.cliente + (f.documento ? ' · ' + f.documento : '');
                });
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _money: function (cents) {
            if (cents === null || cents === undefined) { return '—'; }
            var txt = numero(cents);
            var m = this.data.moneda;
            txt = m.posicion === 'after' ? txt + ' ' + m.simbolo : m.simbolo + ' ' + txt;
            return (cents < 0 ? '−' : '') + txt;
        },

        _pct: function (r) {
            return r === null ? '—' : (r * 100).toFixed(2) + ' %';
        },

        // ------------------------------------------------------------------ cálculo
        // `omitir` deja fuera un criterio ('financiera', 'estado' o 'filtro'): sirve para contar
        // cuántos créditos tendría cada opción de ese criterio con los demás aplicados.
        _filas: function (omitir) {
            var self = this;
            var q = normalizar(this.busqueda);
            return this.data.cuentas.filter(function (f) {
                if (omitir !== 'financiera' && self.financieraId !== null && f.financiera_id !== self.financieraId) { return false; }
                if (omitir !== 'estado' && self.estado !== null && f.estado !== self.estado) { return false; }
                if (q && f._buscar.indexOf(q) === -1) { return false; }
                return omitir === 'filtro' || cumpleFiltro(f, self.filtro);
            });
        },

        // Motos recuperadas: solo se filtran por financiera, búsqueda y el cliente elegido en el punto 4
        // (no tienen cliente que pague). Sin `porCliente` se devuelven las de todos los clientes.
        _recuperadas: function (porCliente) {
            var self = this;
            var q = normalizar(this.busqueda);
            return this.data.recuperadas.filter(function (f) {
                if (self.financieraId !== null && f.financiera_id !== self.financieraId) { return false; }
                if (porCliente && self.clienteRecuperado !== null && f._cliente !== self.clienteRecuperado) { return false; }
                return !q || f._buscar.indexOf(q) !== -1;
            });
        },

        _vista: function (filas) {
            var cli = function (k) { return sumar(filas, function (f) { return f.cliente_resumen[k]; }); };
            var fin = function (k) { return sumar(filas, function (f) { return f.financiera[k]; }); };
            var pos = function (k) { return sumar(filas, function (f) { return f.posicion[k]; }); };
            var conPdf = filas.filter(function (f) { return f.financiera.para_liquidar !== null; });
            var sinPdf = filas.filter(function (f) { return f.financiera.para_liquidar === null && f.financiera.pendiente > 0; });
            var tramos = {};
            this.data.tramos.forEach(function (t) {
                tramos[t] = sumar(filas, function (f) { return f.cliente_resumen.tramos[t]; });
            });
            var v = {
                n: filas.length,
                total: cli('total'),
                cobrado: cli('cobrado'),
                porCobrar: cli('por_cobrar'),
                vigente: cli('vigente'),
                vencido: cli('vencido'),
                tramos: tramos,
                creditosAtraso: filas.filter(function (f) { return f.cliente_resumen.vencido > 0; }).length,
                finTotal: fin('total'),
                finPagado: fin('pagado'),
                finPagadoEstimado: fin('pagado_estimado'),
                deuda: fin('pendiente'),
                capital: sumar(conPdf, function (f) { return f.financiera.capital; }),
                interesFuturo: sumar(conPdf, function (f) { return f.financiera.interes; }),
                otros: sumar(conPdf, function (f) { return f.financiera.otros; }),
                deudaPdf: sumar(conPdf, function (f) { return f.financiera.pendiente; }),
                liquidar: sumar(conPdf, function (f) { return f.financiera.para_liquidar; }),
                nSinPdf: sinPdf.length,
                deudaSinPdf: sumar(sinPdf, function (f) { return f.financiera.pendiente; }),
                pagoMensual: sumar(filas, function (f) { return f.financiera.cuotas_pendientes ? f.financiera.cuota : 0; }),
                aFavor: sumar(filas, function (f) { return Math.max(saldo(f), 0); }),
                enContra: sumar(filas, function (f) { return Math.min(saldo(f), 0); }),
                nAFavor: filas.filter(function (f) { return saldo(f) > 0; }).length,
                nEnContra: filas.filter(function (f) { return saldo(f) < 0; }).length,
                gananciaEsperada: pos('ganancia_esperada'),
                gananciaRealizada: pos('ganancia_realizada'),
                gananciaPorRealizar: pos('ganancia_por_realizar'),
                cuadreOk: filas.filter(function (f) { return f.cuadre_ok; }).length,
            };
            var meses = {};
            filas.forEach(function (f) {
                _.each(f.mensual, function (m, k) {
                    var t = meses[k] || (meses[k] = {cobrado: 0, mora: 0, pago: 0});
                    t.cobrado += m.cobrado;
                    t.mora += m.mora;
                    t.pago += m.pago;
                });
            });
            v.meses = meses;
            v.sinFecha = cli('sin_fecha');
            // Cancelar hoy = lo que pide la financiera (con PDF) + cuotas pendientes de los créditos sin PDF.
            v.cancelarHoy = v.liquidar + v.deudaSinPdf;
            v.ahorro = v.deudaPdf - v.liquidar;
            return v;
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var filas = this._filas();
            var estado = this.estado === null ? 'en todos los estados' : (ESTADOS[this.estado] || this.estado).toLowerCase();
            this._ref('subtitle').text(filas.length + (filas.length === 1 ? ' crédito ' : ' créditos ') + estado +
                ' al ' + fecha(this.data.hoy) + ' · montos exactos al céntimo');
            this._renderChips(filas.length);
            if (!this.data.cuentas.length) {
                this._ref('body').html('<div class="adt_cart__empty">Aún no hay créditos con cronograma.</div>');
                return;
            }
            var v = this._vista(filas);
            this._ref('body').html(
                this._resumenHtml(v) +
                this._mensualHtml(v) +
                this._seccion('Detalle por crédito', v.n + (v.n === 1 ? ' crédito' : ' créditos') +
                    ' · toca una fila para abrir la cuenta · los totales incluyen todos', this._tablaHtml(filas)) +
                this._seccion('Cuadre y calidad de datos', 'Controles automáticos sobre cada crédito', this._cuadreHtml(v, filas)) +
                this._metodoHtml()
            );
        },

        // Filtros con la cantidad de créditos de cada opción (con los demás filtros aplicados),
        // como en Flota 360, y el total de créditos que se están contando.
        _renderChips: function (total) {
            var self = this;
            var contar = function (omitir, clave) {
                return _.countBy(self._filas(omitir), clave);
            };
            var chip = function (attr, valor, activo, texto, n, punto) {
                return '<button type="button" class="adt_cart__fchip' + (activo ? ' is-active' : '') + (!n && !activo ? ' is-zero' : '') +
                    '" ' + attr + '="' + esc(String(valor)) + '" aria-pressed="' + activo + '">' +
                    (punto ? '<i class="adt_cart__fchip-dot is-' + esc(punto) + '" aria-hidden="true"></i>' : '') +
                    esc(texto) + '<span class="adt_cart__fchip-n">' + (n || 0) + '</span></button>';
            };
            var fila = function (icono, titulo, chips) {
                return '<div class="adt_cart__facet"><span class="adt_cart__facet-label"><i class="fa ' + icono + '" aria-hidden="true"></i>' +
                    titulo + '</span><div class="adt_cart__facet-chips">' + chips + '</div></div>';
            };

            var porFin = contar('financiera', 'financiera_id');
            var fin = chip('data-financiera', 'all', this.financieraId === null, 'Todas', _.reduce(porFin, function (a, n) { return a + n; }, 0)) +
                this.data.financieras.map(function (f) {
                    return chip('data-financiera', f.id, self.financieraId === f.id, f.name, porFin[f.id]);
                }).join('');

            var porEstado = contar('estado', 'estado');
            var est = chip('data-estado', 'all', this.estado === null, 'Todos', _.reduce(porEstado, function (a, n) { return a + n; }, 0)) +
                this.data.estados.map(function (e) {
                    return chip('data-estado', e.id, self.estado === e.id, e.name, porEstado[e.id], e.id);
                }).join('');

            var base = this._filas('filtro');
            var ver = FILTROS.map(function (p) {
                var n = base.filter(function (f) { return cumpleFiltro(f, p[0]); }).length;
                return chip('data-filtro', p[0], self.filtro === p[0], p[1], n);
            }).join('');

            var filtrado = this.financieraId !== null || this.estado !== this.data.estado_activo || this.filtro !== 'todas';
            this._ref('chips').html(
                '<div class="adt_cart__count"><b>' + total + '</b> ' + (total === 1 ? 'crédito' : 'créditos') + ' contados' +
                    (this.data.cuentas.length !== total ? ' <span>de ' + this.data.cuentas.length + '</span>' : '') +
                    (filtrado ? '<button type="button" class="adt_cart__count-clear" data-action="limpiar-filtros">' +
                        '<i class="fa fa-times" aria-hidden="true"></i> Quitar filtros</button>' : '') + '</div>' +
                fila('fa-university', 'Financiera', fin) +
                fila('fa-calendar-check-o', 'Cronograma', est) +
                fila('fa-filter', 'Ver', ver));
        },

        _seccion: function (titulo, sub, cuerpo) {
            return '<section class="adt_cart__card"><header><h2>' + esc(titulo) + '</h2>' +
                (sub ? '<p>' + esc(sub) + '</p>' : '') + '</header>' + cuerpo + '</section>';
        },

        _linea: function (texto, cents, opts) {
            opts = opts || {};
            var cls = ['adt_cart__line'];
            if (opts.total) { cls.push('is-total'); }
            if (opts.sub) { cls.push('is-sub'); }
            if (opts.signo && cents < 0) { cls.push('is-neg'); }
            if (opts.signo && cents > 0) { cls.push('is-pos'); }
            return '<div class="' + cls.join(' ') + '">' +
                '<span>' + texto + '</span><b>' + (opts.resta ? '− ' : '') + this._money(cents) + '</b></div>';
        },

        _pregunta: function (num, titulo, monto, explicacion, cuerpo, tono, cabecera) {
            return '<section class="adt_cart__answer' + (tono ? ' is-' + tono : '') + '">' +
                '<p class="adt_cart__answer-q"><span>' + num + '</span>' + esc(titulo) + '</p>' + (cabecera || '') +
                '<p class="adt_cart__answer-big">' + this._money(monto) + '</p>' +
                '<p class="adt_cart__answer-why">' + explicacion + '</p>' + cuerpo + '</section>';
        },

        // Resumen para gerencia: cuatro preguntas en lenguaje simple + el resultado de los créditos.
        _resumenHtml: function (v) {
            var self = this;
            var creditos = function (n) { return n + (n === 1 ? ' crédito' : ' créditos'); };
            var atrasoTxt = v.vencido ?
                '<b>' + this._pct(ratio(v.vencido, v.porCobrar)) + '</b> de lo que nos deben ya está atrasado ' +
                '(' + creditos(v.creditosAtraso) + ').' : 'Ningún cliente tiene cuotas atrasadas.';
            var tramos = this.data.tramos.map(function (t) {
                return v.tramos[t] ? self._linea(TRAMOS[t], v.tramos[t], {sub: true}) : '';
            }).join('');

            var deben = this._pregunta(1, '¿Cuánto nos deben los clientes?', v.porCobrar,
                'Lo que falta cobrar a los clientes de ' + creditos(v.n) + ', sumando todas sus cuotas pendientes.',
                this._linea('Cuotas que aún no vencen', v.vigente) +
                this._linea('Cuotas atrasadas (ya debieron pagarlas)', v.vencido) + tramos +
                '<p class="adt_cart__answer-foot">' + atrasoTxt + '</p>', 'in');

            var sinPdf = v.nSinPdf ? this._linea('Créditos sin cronograma de la financiera', v.deudaSinPdf) : '';
            var cancelar = '<div class="adt_cart__callout"><p>Si quisiéramos <b>cancelar todo hoy</b>, pagaríamos</p>' +
                '<b>' + this._money(v.cancelarHoy) + '</b>' +
                (v.ahorro > 0 ? '<p>Nos ahorraríamos <b>' + this._money(v.ahorro) + '</b> de intereses y cargos que todavía no se generan.</p>' : '') +
                (v.nSinPdf ? '<p class="adt_cart__muted">Incluye ' + this._money(v.deudaSinPdf) + ' de ' + creditos(v.nSinPdf) +
                    ' sin cronograma de la financiera, tomados por el total de sus cuotas.</p>' : '') + '</div>';
            var debemos = this._pregunta(2, '¿Cuánto debemos a la financiera?', v.deuda,
                'Lo que falta pagarle si seguimos pagando cuota por cuota hasta el final.',
                this._linea('El préstamo (capital)', v.capital) +
                this._linea('Intereses', v.interesFuturo) +
                this._linea('Seguro de desgravamen y aportes', v.otros) + sinPdf +
                '<p class="adt_cart__answer-foot">Cada mes pagamos aproximadamente <b>' + this._money(v.pagoMensual) +
                '</b> (la próxima cuota de cada crédito).</p>' + cancelar, 'out');

            var queda = this._pregunta(3, '¿Cuánto nos queda?', v.gananciaPorRealizar,
                'Lo que nos deben los clientes menos lo que debemos a la financiera: lo que quedará para ADT cuando todos terminen de pagar.',
                this._linea('Si además cancelamos hoy a la financiera', v.aFavor + v.enContra, {signo: true}) +
                this._linea('Créditos que dejan saldo a favor (' + v.nAFavor + ')', v.aFavor, {sub: true, signo: true}) +
                this._linea('Créditos donde lo que debe el cliente no alcanza para pagar la financiera (' + v.nEnContra + ')',
                    v.enContra, {sub: true, signo: true}) +
                (v.vencido ? '<p class="adt_cart__answer-foot">Supone que los clientes pagan todo, incluidos ' +
                    this._money(v.vencido) + ' que hoy están atrasados.</p>' : ''),
                v.gananciaPorRealizar < 0 ? 'loss' : 'gain');

            var resultado = '<section class="adt_cart__card adt_cart__result"><header><h2>Resultado de estos créditos, de principio a fin</h2>' +
                '<p>Lo que ya pasó más lo que falta: cuánto ganamos en total</p></header>' +
                this._linea('Ya cobramos a los clientes', v.cobrado) +
                this._linea('Ya pagamos a la financiera', v.finPagado, {resta: true}) +
                this._linea('Resultado hasta hoy', v.gananciaRealizada, {total: true, signo: true}) +
                this._linea('Lo que nos queda por delante (punto 3)', v.gananciaPorRealizar, {signo: true}) +
                this._linea('Ganancia total cuando terminen los créditos', v.gananciaEsperada, {total: true, signo: true}) +
                (v.n ? '<p class="adt_cart__answer-foot">En promedio, <b>' + this._money(Math.round(v.gananciaEsperada / v.n)) +
                    '</b> por crédito.' + (v.finPagadoEstimado ? ' Lo pagado a la financiera incluye ' +
                    this._money(v.finPagadoEstimado) + ' de cuotas anteriores al PDF, estimadas.' : '') + '</p>' : '') +
                '</section>';

            var excluidas = this.data.excluidas_con_deuda.map(function (e) {
                return creditos(e.cantidad) + ' ' + (ESTADOS[e.estado] || e.estado).toLowerCase() +
                    (e.cantidad === 1 ? '' : 's') + ' con ' + self._money(e.deuda) + ' pendientes con la financiera';
            });
            var nota = '';
            if (this.estado !== this.data.estado_activo) {
                nota = '<p class="adt_cart__note adt_cart__note--warn">Estos totales incluyen créditos que no están en curso: ' +
                    'no son la cartera activa. Para la cartera activa elige <b>Cronograma: En curso</b>.</p>';
            } else if (excluidas.length) {
                nota = '<p class="adt_cart__note adt_cart__note--warn">Solo se cuentan créditos en curso. ' +
                    'Atención: hay ' + excluidas.join(' y ') + ' que no están en estos totales.</p>';
            }

            return '<div class="adt_cart__answers">' + deben + debemos + queda + this._recuperadasHtml() + '</div>' +
                resultado + nota;
        },

        // Motos recuperadas: el cliente dejó de pagar y se le retiró la moto, pero ADT sigue pagando
        // la financiera para mantenerla al día. No entran en los totales de los créditos en curso.
        _recuperadasHtml: function () {
            var self = this;
            var todas = this._recuperadas(false);
            var filas = this._recuperadas(true);
            var elegido = this.clienteRecuperado !== null && filas.length ? filas[0] : null;
            var motos = function (n) { return n + (n === 1 ? ' moto' : ' motos'); };
            var conPdf = filas.filter(function (f) { return f.para_liquidar !== null; });
            var sinPdf = filas.filter(function (f) { return f.para_liquidar === null; });
            var pendiente = sumar(filas, function (f) { return f.pendiente; });
            var mensual = sumar(filas, function (f) { return f.cuota; });
            var cancelarHoy = sumar(conPdf, function (f) { return f.para_liquidar; }) +
                sumar(sinPdf, function (f) { return f.pendiente; });
            var detalle = _.sortBy(filas, function (f) { return -f.pendiente; }).map(function (f) {
                return '<li data-cuenta="' + f.id + '" title="' + esc(f.referencia + ' · ' + f.cliente) + '"><span>' +
                    esc(f.placa || f.referencia) + ' · ' + esc(f.cliente) +
                    '<small>' + f.cuotas_pendientes + (f.cuotas_pendientes === 1 ? ' cuota' : ' cuotas') +
                    ' de ' + self._money(f.cuota) + ' · culmina ' + fecha(f.fin) + '</small></span>' +
                    '<b>' + self._money(f.pendiente) + '</b></li>';
            }).join('');
            // Buscador de cliente: lista los clientes de las motos recuperadas visibles.
            var clientes = _.uniq(_.sortBy(todas, '_etiqueta'), false, '_cliente');
            var buscador = clientes.length ? '<div class="adt_cart__answer-search">' +
                '<i class="fa fa-user" aria-hidden="true"></i>' +
                '<input type="search" data-ref="cliente-recuperado" list="adt_cart_clientes_recuperados" autocomplete="off" ' +
                    'aria-label="Seleccionar un cliente" placeholder="Seleccionar cliente (nombre o DNI)…" value="' +
                    esc(elegido ? elegido._etiqueta : this.textoRecuperado) + '"/>' +
                (this.clienteRecuperado !== null || this.textoRecuperado ?
                    '<button type="button" data-action="limpiar-recuperado" title="Ver todos los clientes">×</button>' : '') +
                '<datalist id="adt_cart_clientes_recuperados">' + clientes.map(function (f) {
                    return '<option value="' + esc(f._etiqueta) + '"></option>';
                }).join('') + '</datalist></div>' +
                (this.textoRecuperado && this.clienteRecuperado === null ?
                    '<p class="adt_cart__muted">Ningún cliente con moto recuperada coincide con "' + esc(this.textoRecuperado) + '".</p>' : '')
                : '';
            return this._pregunta(4, '¿Cuánto pagamos por motos recuperadas?', pendiente,
                elegido ?
                    'Lo que falta pagar a la financiera por ' + (filas.length === 1 ? 'la moto' : 'las ' + motos(filas.length)) +
                        ' recuperada' + (filas.length === 1 ? '' : 's') + ' a <b>' + esc(elegido.cliente) + '</b>. El cliente ya no paga: lo cubre ADT.' :
                filas.length ?
                    'Lo que falta pagar a la financiera por ' + motos(filas.length) + ' que se retiraron al cliente y aún no tienen nuevo crédito. El cliente ya no paga: lo cubre ADT.' :
                    'No hay motos recuperadas con cuotas pendientes con la financiera.',
                filas.length ? (
                    this._linea('Cada mes pagamos (próxima cuota de cada moto)', mensual) +
                    this._linea('Si las cancelamos hoy', cancelarHoy) +
                    (sinPdf.length ? '<p class="adt_cart__muted">' + motos(sinPdf.length) +
                        ' sin cronograma PDF: se toman por el total de sus cuotas pendientes.</p>' : '') +
                    '<ul class="adt_cart__answer-list">' + detalle + '</ul>' +
                    '<p class="adt_cart__answer-foot">No está incluido en los puntos 1 a 3. Al colocar la moto con un nuevo cliente sale de aquí.</p>'
                ) : '', filas.length ? 'loss' : '', buscador);
        },

        // Solo meses ya cerrados (el servidor no envía el mes en curso ni los futuros). Plegable.
        _mensualHtml: function (v) {
            var self = this;
            var claves = _.keys(v.meses).filter(function (k) {
                var m = v.meses[k];
                return m.cobrado || m.mora || m.pago;
            }).sort();
            var tot = {cobrado: 0, mora: 0, pago: 0};
            claves.forEach(function (k) {
                tot.cobrado += v.meses[k].cobrado + v.meses[k].mora;
                tot.mora += v.meses[k].mora;
                tot.pago += v.meses[k].pago;
            });
            var resultado = tot.cobrado - tot.pago;
            var mesActual = mesLargo(this.data.hoy.slice(0, 7)).toLowerCase();
            var resumen = claves.length ?
                claves.length + (claves.length === 1 ? ' mes cerrado' : ' meses cerrados') + ' (' +
                    mesLargo(claves[0]) + ' a ' + mesLargo(claves[claves.length - 1]) + ') · cobramos ' +
                    this._money(tot.cobrado) + ' · pagamos ' + this._money(tot.pago) + ' · resultado ' +
                    '<b class="' + (resultado < 0 ? 'neg' : 'pos') + '">' + this._money(resultado) + '</b>' :
                'Aún no hay meses cerrados con movimientos.';
            var html = '<section class="adt_cart__card adt_cart__months' + (this.mesesAbierto ? ' is-open' : '') + '">' +
                '<header class="adt_cart__toggle-head"><div><h2>Mes a mes: lo que cobramos y lo que pagamos a la financiera</h2>' +
                '<p>' + resumen + '</p></div>' +
                (claves.length ? '<button type="button" class="adt_cart__btn adt_cart__btn--ghost adt_cart__toggle" data-action="toggle-meses">' +
                    (this.mesesAbierto ? 'Ocultar meses ▴' : 'Ver meses ▾') + '</button>' : '') + '</header>';
            if (!this.mesesAbierto || !claves.length) { return html + '</section>'; }

            var acumulado = 0;
            var celda = function (c, cls) {
                return '<td class="num' + (cls ? ' ' + cls : '') + (c < 0 ? ' neg' : '') + '">' + (c ? self._money(c) : '—') + '</td>';
            };
            var filas = claves.map(function (k) {
                var m = v.meses[k];
                var cobrado = m.cobrado + m.mora;
                var dif = cobrado - m.pago;
                acumulado += dif;
                return '<tr><td>' + esc(mesLargo(k)) + '</td>' + celda(cobrado) + celda(m.pago) +
                    celda(dif, 'is-strong') + celda(acumulado) + '</tr>';
            }).join('');
            var notas = ['El mes en curso (' + mesActual + ') aparecerá cuando termine.'];
            if (tot.mora) { notas.push('Lo cobrado incluye ' + this._money(tot.mora) + ' de moras.'); }
            if (v.finPagadoEstimado) {
                notas.push('Los pagos a la financiera anteriores al PDF son estimados con la cuota del PDF.');
            }
            return html + '<div class="adt_cart__tablewrap adt_cart__tablewrap--full"><table class="adt_cart__table adt_cart__table--meses"><thead><tr>' +
                '<th>Mes</th><th class="num">Cobramos a los clientes</th><th class="num">Pagamos a la financiera</th>' +
                '<th class="num">Nos quedó en el mes</th><th class="num">Acumulado</th></tr></thead><tbody>' + filas +
                '</tbody><tfoot><tr><td>Total</td>' + celda(tot.cobrado) + celda(tot.pago) + celda(resultado) +
                '<td class="num">' + (claves.length ? 'promedio ' + this._money(Math.round(resultado / claves.length)) + '/mes' : '') +
                '</td></tr></tfoot></table></div>' +
                '<p class="adt_cart__note">' + notas.join(' ') + '</p></section>';
        },

        _ordenar: function (filas) {
            var s = this.sort;
            var col = _.findWhere(COLUMNAS, {key: s.key});
            var val = col ? col.valor : saldo;
            return filas.slice().sort(function (a, b) {
                var x = val(a), y = val(b);
                if (x === null || x === undefined) { x = col && col.tipo === 'texto' ? '' : -Infinity; }
                if (y === null || y === undefined) { y = col && col.tipo === 'texto' ? '' : -Infinity; }
                if (typeof x === 'string') { return s.dir * x.localeCompare(y); }
                return s.dir * (x - y);
            });
        },

        _celda: function (col, f) {
            var v = col.valor(f);
            if (col.tipo === 'monto') {
                var neg = v < 0;
                var marca = (col.key === 'a_favor' || col.key === 'en_contra') && v && f.posicion.neto_liquidar === null ?
                    '<sup title="Calculado contra la deuda nominal: no hay cronograma PDF">N</sup>' : '';
                return '<td class="num' + (neg ? ' neg' : '') + '">' + (v || v === 0 ? this._money(v) : '—') + marca + '</td>';
            }
            if (col.tipo === 'entero') { return '<td class="num">' + (v || v === 0 ? v : '—') + '</td>'; }
            if (col.tipo === 'fecha') { return '<td>' + fecha(v) + '</td>'; }
            return '<td>' + esc(v || '') + '</td>';
        },

        _tablaHtml: function (filas) {
            var self = this;
            var head = '<th>#</th>' + COLUMNAS.map(function (c) {
                var activo = self.sort.key === c.key;
                return '<th class="' + (c.tipo === 'monto' || c.tipo === 'entero' ? 'num ' : '') + 'is-sortable' +
                    (activo ? ' is-sorted' : '') + '" data-sort="' + c.key + '"' +
                    (c.title ? ' title="' + esc(c.title) + '"' : '') + '>' + esc(c.label) +
                    (activo ? (self.sort.dir > 0 ? ' ▲' : ' ▼') : '') + '</th>';
            }).join('') + '<th></th>';
            var ordenadas = this._ordenar(filas);
            var paginas = Math.max(1, Math.ceil(ordenadas.length / POR_PAGINA));
            this.pagina = Math.min(this.pagina, paginas - 1);
            var desde = this.imprimiendo ? 0 : this.pagina * POR_PAGINA;
            var visibles = this.imprimiendo ? ordenadas : ordenadas.slice(desde, desde + POR_PAGINA);
            var body = visibles.map(function (f, j) {
                var i = desde + j;
                var alerta = f.alertas.length ?
                    '<span class="adt_cart__alert' + (f.cuadre_ok ? '' : ' is-bad') + '" title="' + esc(f.alertas.join('\n')) + '">!</span>' : '';
                return '<tr data-cuenta="' + f.id + '"><td class="num">' + (i + 1) + '</td>' +
                    COLUMNAS.map(function (c) { return self._celda(c, f); }).join('') + '<td>' + alerta + '</td></tr>';
            }).join('');
            var foot = '<td></td>' + COLUMNAS.map(function (c) {
                if (!c.total) { return c.key === 'cliente' ? '<td><b>Total (' + filas.length + ')</b></td>' : '<td></td>'; }
                var t = sumar(filas, c.valor);
                return '<td class="num' + (t < 0 ? ' neg' : '') + '">' + self._money(t) + '</td>';
            }).join('') + '<td></td>';
            var pager = '';
            if (!this.imprimiendo && paginas > 1) {
                var p = this.pagina;
                pager = '<div class="adt_cart__pager"><span>Mostrando ' + (desde + 1) + '–' + (desde + visibles.length) +
                    ' de ' + ordenadas.length + '</span>' +
                    '<button type="button" class="adt_cart__chip" data-pagina="' + (p - 1) + '"' + (p === 0 ? ' disabled' : '') + '>‹ Anterior</button>' +
                    '<span>Página ' + (p + 1) + ' de ' + paginas + '</span>' +
                    '<button type="button" class="adt_cart__chip" data-pagina="' + (p + 1) + '"' + (p >= paginas - 1 ? ' disabled' : '') + '>Siguiente ›</button></div>';
            }
            return '<div class="adt_cart__tablewrap"><table class="adt_cart__table adt_cart__table--detalle">' +
                '<thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody>' +
                '<tfoot><tr>' + foot + '</tr></tfoot></table></div>' + pager;
        },

        _cuadreHtml: function (v, filas) {
            var conteo = {};
            filas.forEach(function (f) {
                f.alertas.forEach(function (a) { conteo[a] = (conteo[a] || 0) + 1; });
            });
            var lista = _.map(conteo, function (n, a) { return '<li><b>' + n + '</b> ' + esc(a) + '</li>'; }).join('');
            var identidades = [
                ['Cartera por cobrar = vigente + vencida', v.porCobrar === v.vigente + v.vencido],
                ['Cronograma del cliente = cobrado + por cobrar', v.total === v.cobrado + v.porCobrar],
                ['Total financiera = pagado + deuda nominal', v.finTotal === v.finPagado + v.deuda],
                ['Ganancia esperada = realizada + por realizar',
                    v.gananciaEsperada === v.gananciaRealizada + v.gananciaPorRealizar],
                ['Deuda con PDF = capital + interés futuro + otros', v.deudaPdf === v.capital + v.interesFuturo + v.otros],
                ['Saldos a favor + en contra = cartera − cancelar hoy', v.aFavor + v.enContra === v.porCobrar - v.cancelarHoy],
            ].map(function (p) {
                return '<li class="' + (p[1] ? 'ok' : 'bad') + '">' + (p[1] ? '✔ ' : '✘ ') + esc(p[0]) + '</li>';
            }).join('');
            return '<div class="adt_cart__cuadre">' +
                '<div><h3>Identidades del total</h3><ul>' + identidades + '</ul>' +
                '<p class="adt_cart__note">' + v.cuadreOk + ' de ' + v.n + ' créditos cuadran al céntimo en todas sus identidades.</p></div>' +
                '<div><h3>Alertas de datos</h3>' + (lista ? '<ul>' + lista + '</ul>' : '<p>Sin alertas.</p>') + '</div>' +
                '</div>';
        },

        _metodoHtml: function () {
            return '<details class="adt_cart__card adt_cart__method"><summary>¿Cómo se calcula?</summary><ul>' +
                '<li><b>Por cobrar</b>: saldo de las cuotas del cronograma del cliente no anuladas. <b>Vencido</b>: cuotas con fecha anterior a hoy y saldo; se agrupa por días de atraso de cada cuota.</li>' +
                '<li><b>Deuda nominal</b>: cuotas de la financiera con vencimiento posterior a hoy. Se asume que ADT paga cada cuota en su fecha.</li>' +
                '<li><b>Para liquidar hoy</b>: capital pendiente del cronograma PDF + interés devengado desde el último vencimiento: capital · ((1 + TEA)^(días/360) − 1). Es la misma fórmula que usa la financiera en su cronograma. Confirmar con la financiera antes de pagar: puede cobrar cargos adicionales.</li>' +
                '<li><b>Saldo a favor / en contra</b>: por cobrar − para liquidar. Si el crédito no tiene PDF, por cobrar − deuda nominal (marcado <sup>N</sup>).</li>' +
                '<li><b>Ganancia del crédito</b>: total del cronograma del cliente − total de la financiera (pagado + pendiente). Las cuotas a la financiera anteriores a la primera del PDF se estiman con la cuota del PDF y se avisan como alerta.</li>' +
                '<li><b>Motos recuperadas</b>: cuentas canceladas con vehículo recuperado cuya moto no tiene un nuevo crédito aprobado o en curso. Se suma lo que falta pagar a la financiera por cada moto (una vez por moto), aunque el cliente ya no pague.</li>' +
                '<li><b>Precisión</b>: todos los montos se manejan en céntimos enteros con redondeo contable (HALF_UP); los totales son la suma exacta de las filas.</li>' +
                '</ul></details>';
        },

        // ------------------------------------------------------------------ eventos
        _onRefresh: function () {
            var self = this;
            return this._load().then(function () { self._render(); });
        },

        // El navegador arma el PDF ("Guardar como PDF") con los estilos de impresión de cartera_reporte.scss.
        _onImprimir: function () {
            var filtro = [];
            if (this.financieraId !== null) {
                var f = _.findWhere(this.data.financieras, {id: this.financieraId});
                filtro.push('Financiera: ' + (f ? f.name : ''));
            }
            filtro.push('Cronograma: ' + (this.estado === null ? 'todos los estados' : (ESTADOS[this.estado] || this.estado)));
            if (this.filtro !== 'todas') { filtro.push('Ver: ' + _.object(FILTROS)[this.filtro]); }
            if (this.busqueda) { filtro.push('Búsqueda: "' + this.busqueda + '"'); }
            this._ref('print-meta').text('Impreso el ' + moment().format('DD/MM/YYYY HH:mm') +
                (filtro.length ? ' · ' + filtro.join(' · ') : ' · todas las financieras'));
            // En papel van todos los créditos, no solo la página visible.
            this.imprimiendo = true;
            this._render();
            window.print();
            this.imprimiendo = false;
            this._render();
        },

        _onPagina: function (ev) {
            this.pagina = parseInt($(ev.currentTarget).data('pagina'), 10);
            this._render();
            this.$('.adt_cart__table--detalle')[0].scrollIntoView({block: 'nearest'});
        },

        _onToggleMeses: function () {
            this.mesesAbierto = !this.mesesAbierto;
            this._render();
        },

        _onFinanciera: function (ev) {
            var v = $(ev.currentTarget).data('financiera');
            this.financieraId = v === 'all' ? null : parseInt(v, 10);
            this.pagina = 0;
            this._render();
        },

        _onEstado: function (ev) {
            var v = String($(ev.currentTarget).attr('data-estado'));
            this.estado = v === 'all' ? null : v;
            this.pagina = 0;
            this._render();
        },

        _onLimpiarFiltros: function () {
            this.financieraId = null;
            this.estado = this.data.estado_activo;
            this.filtro = 'todas';
            this.pagina = 0;
            this._render();
        },

        _onFiltro: function (ev) {
            this.filtro = $(ev.currentTarget).data('filtro');
            this.pagina = 0;
            this._render();
        },

        _onSort: function (ev) {
            var key = $(ev.currentTarget).data('sort');
            this.sort = {key: key, dir: this.sort.key === key ? -this.sort.dir : 1};
            this.pagina = 0;
            this._render();
        },

        // Elige el cliente por su etiqueta exacta (opción de la lista) o, si lo escrito
        // coincide con un solo cliente, ese cliente.
        _onClienteRecuperado: function (ev) {
            var texto = ev.target.value.trim();
            var q = normalizar(texto);
            var todas = this._recuperadas(false);
            var exacta = _.find(todas, function (f) { return normalizar(f._etiqueta) === q; });
            var parciales = _.uniq(todas.filter(function (f) {
                return q && (normalizar(f._etiqueta).indexOf(q) !== -1 || f._buscar.indexOf(q) !== -1);
            }).map(function (f) { return f._cliente; }));
            this.clienteRecuperado = !q ? null : exacta ? exacta._cliente : parciales.length === 1 ? parciales[0] : null;
            this.textoRecuperado = this.clienteRecuperado === null ? texto : '';
            this._render();
        },

        _onLimpiarRecuperado: function () {
            this.clienteRecuperado = null;
            this.textoRecuperado = '';
            this._render();
            this._ref('cliente-recuperado').focus();
        },

        _onBuscar: _.debounce(function (ev) {
            this.busqueda = ev.target.value;
            this.pagina = 0;
            this._render();
        }, 200),

        _onCuenta: function (ev) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'adt.comercial.cuentas',
                res_id: $(ev.currentTarget).data('cuenta'),
                views: [[false, 'form']],
                target: 'current',
            });
        },

        // CSV para Excel: números con punto decimal y sin separador de miles, en soles.
        _onExportar: function () {
            var filas = this._ordenar(this._filas());
            var csv = function (v) { return '"' + String(v === null || v === undefined ? '' : v).replace(/"/g, '""') + '"'; };
            var soles = function (c) {
                if (c === null || c === undefined) { return ''; }
                var abs = Math.abs(c);
                return (c < 0 ? '-' : '') + Math.floor(abs / 100) + '.' + ('0' + (abs % 100)).slice(-2);
            };
            var lineas = [['#'].concat(COLUMNAS.map(function (c) { return c.label; }), ['Alertas']).map(csv).join(',')];
            filas.forEach(function (f, i) {
                lineas.push([i + 1].concat(COLUMNAS.map(function (c) {
                    var v = c.valor(f);
                    return c.tipo === 'monto' ? soles(v) : c.tipo === 'fecha' ? fecha(v) : v;
                }), [f.alertas.join(' | ')]).map(csv).join(','));
            });
            var blob = new Blob(['﻿' + lineas.join('\r\n')], {type: 'text/csv;charset=utf-8'});
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'cartera_financieras_' + this.data.hoy + '.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);
        },
    });

    core.action_registry.add('adt_cartera_reporte', CarteraReporte);
    return CarteraReporte;
});
