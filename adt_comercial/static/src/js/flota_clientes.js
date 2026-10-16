odoo.define('adt_comercial.FlotaClientes', function (require) {
    'use strict';

    /**
     * Vistas del menú Flota, con el mismo diseño que Flota 360:
     *  - Candidatos a préstamo: clientes aptos, por evaluar y no aptos (puntaje del Dashboard de Clientes).
     *  - Traspaso notarial: motos por pasar a nombre del cliente y etapa de su traspaso (adt.traspaso.notarial).
     * Los datos vienen de adt.comercial.clientes.dashboard, así las reglas son las mismas en todas las vistas.
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var esc = _.escape;
    var LOTE = 50;

    function normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim();
    }

    function fecha(f) {
        return f ? moment(f).format('DD/MM/YYYY') : '—';
    }

    function st(cls, texto) {
        return '<span class="adt_cf__st is-' + cls + '"><i></i>' + esc(texto) + '</span>';
    }

    function celda(principal, sub) {
        return principal + (sub ? '<div class="adt_cf__sub">' + sub + '</div>' : '');
    }

    function csv(val) {
        return '"' + String(val === null || val === undefined ? '' : val).replace(/"/g, '""') + '"';
    }

    var FlotaClientes = AbstractAction.extend({
        template: 'adt_comercial.FlotaClientes',
        hasControlPanel: false,

        events: {
            'click [data-tab]': '_onTab',
            'input [data-ref="q"]': '_onBuscar',
            'change [data-ref="financiera"]': '_onFinanciera',
            'click [data-row]': '_onAbrir',
            'click [data-cuenta]': '_onAbrirCuenta',
            'click [data-action="cerrar"]': '_cerrar',
            'click [data-action="mas"]': '_onMas',
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="export"]': '_onExport',
            'click [data-action="guardar"]': '_onGuardar',
            'click [data-action="historial"]': '_onHistorial',
            'keydown': '_onKeydown',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.tab = this.tabs[0].key;
            this.q = '';
            this.financiera = null;
            this.limite = LOTE;
            this.abierto = null;
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._renderFinancieras();
                self._render();
            });
        },

        _load: function () {
            var self = this;
            return this._rpc({
                model: 'adt.comercial.clientes.dashboard',
                method: 'get_dashboard_data',
                args: [],
                kwargs: {traspasos: this.modo === 'traspasos'},
            }).then(function (data) {
                self.data = data;
                self.hoy = moment(data.hoy);
                self.clientesPorId = _.indexBy(data.clientes, 'id');
                self._preparar();
            });
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        // ------------------------------------------------------------------ datos
        _base: function () {
            var fid = this.financiera;
            return this._items().filter(function (r) { return fid === null || r.financiera_id === fid; });
        },

        _enTab: function (r, key) {
            return _.findWhere(this.tabs, {key: key}).filtro.call(this, r);
        },

        _filas: function () {
            var self = this;
            var tab = _.findWhere(this.tabs, {key: this.tab});
            var q = normalizar(this.q);
            return this._base().filter(function (r) {
                return tab.filtro.call(self, r) && (!q || r._buscar.indexOf(q) !== -1);
            }).sort(function (a, b) {
                var va = tab.orden(a);
                var vb = tab.orden(b);
                var cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
                return (tab.desc ? -cmp : cmp) || a.nombre.localeCompare(b.nombre);
            });
        },

        // ------------------------------------------------------------------ render
        _render: function () {
            var self = this;
            var base = this._base();
            this._ref('subtitulo').text('Al ' + this.hoy.format('DD/MM/YYYY'));
            // Cada indicador es también la pestaña que filtra la lista.
            var subs = this._subtitulos(base);
            this._ref('figuras').attr('role', 'tablist').html(this.tabs.map(function (t) {
                var activo = self.tab === t.key;
                var n = base.filter(function (r) { return t.filtro.call(self, r); }).length;
                var sub = subs[t.key] || {};
                return '<button type="button" role="tab" data-tab="' + t.key + '" aria-selected="' + activo + '" class="adt_cf__figure' +
                    (sub.cls ? ' is-' + sub.cls : t.cls && n ? ' is-' + t.cls : '') + (activo ? ' is-active' : '') + '">' +
                    '<span class="adt_cf__figure-label">' + esc(t.label) + '</span>' +
                    '<span class="adt_cf__figure-value">' + n.toLocaleString('es-PE') + '</span>' +
                    '<span class="adt_cf__figure-sub">' + esc(sub.texto || t.sub || '') + '</span></button>';
            }).join(''));
            this._renderGrid();
        },

        _renderGrid: function () {
            var self = this;
            var filas = this._filas();
            var cols = this._columnas();
            var visibles = filas.slice(0, this.limite);
            var head = cols.map(function (c) { return '<th' + (c.num ? ' class="is-num"' : '') + '>' + esc(c.label) + '</th>'; }).join('');
            var body = visibles.map(function (r) {
                return '<tr data-row="' + r._id + '"' + (r._id === self.abierto ? ' class="is-selected"' : '') + '>' + cols.map(function (c) {
                    return '<td class="' + (c.num ? 'is-num' : '') + (c.wrap ? ' is-wrap' : '') + '">' + c.html.call(self, r) + '</td>';
                }).join('') + '</tr>';
            }).join('');
            this._ref('grid').html(filas.length ?
                '<table class="adt_cf__table"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>' :
                '<div class="adt_cf__empty">' + esc(this.q ? 'Nada coincide con la búsqueda.' : _.findWhere(this.tabs, {key: this.tab}).vacio) + '</div>');
            this._ref('more').html(filas.length ? '<span>' + visibles.length + ' de ' + filas.length + '</span>' +
                (filas.length > visibles.length ? '<button type="button" class="adt_cf__btn" data-action="mas">Mostrar ' +
                    Math.min(LOTE, filas.length - visibles.length) + ' más</button>' : '') : '');
        },

        _renderFinancieras: function () {
            var $sel = this._ref('financiera');
            $sel.html('<option value="">Todas las financieras</option>' + this.data.financieras.map(function (f) {
                return '<option value="' + f.id + '">' + esc(f.nombre) + '</option>';
            }).join(''));
            $sel.prop('hidden', this.data.financieras.length < 2);
        },

        _abrirPanel: function (html) {
            this._ref('side').html(html);
            this.$el.addClass('is-side-open');
        },

        _cerrar: function () {
            this.abierto = null;
            this.$el.removeClass('is-side-open');
            this.$('tr.is-selected').removeClass('is-selected');
        },

        _cabecera: function (titulo, sub, estado) {
            return '<header class="adt_cf__side-head"><div class="adt_cf__side-title">' + esc(titulo) +
                '<div class="adt_cf__sub">' + esc(sub) + '</div><div class="mt-2">' + estado + '</div></div>' +
                '<button type="button" class="adt_cf__btn is-icon" data-action="cerrar" aria-label="Cerrar"><i class="fa fa-times"></i></button></header>';
        },

        _opciones: function (map, actual, vacio) {
            return (vacio ? '<option value="">' + esc(vacio) + '</option>' : '') + _.map(map, function (label, key) {
                return '<option value="' + key + '"' + (key === actual ? ' selected' : '') + '>' + esc(label) + '</option>';
            }).join('');
        },

        _guardar: function (metodo, id, valores) {
            var self = this;
            var $btn = this.$('[data-action="guardar"]').prop('disabled', true);
            return this._rpc({
                model: 'adt.comercial.clientes.dashboard',
                method: metodo,
                args: [id, valores],
            }).then(function () {
                return self._load();
            }).then(function () {
                self._render();
                self._renderPanel();
                self.displayNotification({type: 'success', message: 'Cambios guardados.'});
            }).guardedCatch(function () {
                $btn.prop('disabled', false);
            });
        },

        // ------------------------------------------------------------------ eventos
        _onTab: function (ev) {
            this.tab = ev.currentTarget.getAttribute('data-tab');
            this.limite = LOTE;
            this._render();
        },

        _onBuscar: _.debounce(function (ev) {
            this.q = ev.target.value || '';
            this.limite = LOTE;
            this._renderGrid();
        }, 200),

        _onFinanciera: function (ev) {
            this.financiera = ev.currentTarget.value === '' ? null : parseInt(ev.currentTarget.value, 10);
            this.limite = LOTE;
            this._render();
        },

        _onMas: function () {
            this.limite += LOTE;
            this._renderGrid();
        },

        _onAbrir: function (ev) {
            this.abierto = parseInt(ev.currentTarget.getAttribute('data-row'), 10);
            this.$('tr.is-selected').removeClass('is-selected');
            $(ev.currentTarget).addClass('is-selected');
            this._renderPanel();
            this._ref('side').find('.adt_cf__side-body').scrollTop(0);
        },

        _onAbrirCuenta: function (ev) {
            ev.preventDefault();
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
            var $btn = this.$('[data-action="refresh"]').prop('disabled', true);
            this._load().then(function () {
                self._renderFinancieras();
                self._render();
                if (self.abierto) { self._renderPanel(); }
            }).finally(function () {
                $btn.prop('disabled', false);
            });
        },

        _onKeydown: function (ev) {
            if (ev.key === 'Escape' && this.abierto) { this._cerrar(); }
        },

        _onExport: function () {
            var self = this;
            var cols = this._columnas();
            var lineas = [cols.map(function (c) { return csv(c.label); }).join(',')];
            this._filas().forEach(function (r) {
                lineas.push(cols.map(function (c) {
                    return csv($('<div>').html(c.html.call(self, r)).text().replace(/\s+/g, ' ').trim());
                }).join(','));
            });
            var blob = new Blob(['﻿' + lineas.join('\r\n')], {type: 'text/csv;charset=utf-8'});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = this.modo + '_' + this.tab + '_' + moment().format('YYYYMMDD_HHmm') + '.csv';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
        },

        _onHistorial: function (ev) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: ev.currentTarget.getAttribute('data-model'),
                res_id: parseInt(ev.currentTarget.getAttribute('data-id'), 10),
                views: [[false, 'form']],
                target: 'current',
            });
        },
    });

    // ====================================================================== Candidatos a préstamo

    var SEGMENTO = {
        apto: {cls: 'ok', label: 'Apto'},
        evaluar: {cls: 'atencion', label: 'Evaluar'},
        pagando_bien: {cls: 'info', label: 'Pagando, buen pagador'},
        pagando_alerta: {cls: 'atencion', label: 'Pagando, con alertas'},
        no_prestar: {cls: 'critico', label: 'No apto'},
    };

    function segmento(key) {
        var s = SEGMENTO[key] || {cls: 'neutral', label: '—'};
        return st(s.cls, s.label);
    }

    var CandidatosPrestamo = FlotaClientes.extend({
        modo: 'candidatos',
        titulo: 'Candidatos a préstamo',
        tabs: [
            {key: 'apto', label: 'Aptos', cls: 'ok', vacio: 'No hay clientes aptos para un nuevo préstamo.',
                filtro: function (c) { return c.segmento === 'apto'; }, orden: function (c) { return c.puntaje; }, desc: true},
            {key: 'pronto', label: 'Terminan pronto', vacio: 'Ningún buen pagador termina pronto.',
                filtro: function (c) { return c.segmento === 'pagando_bien' && c.termina && c.termina <= this._limitePronto; },
                orden: function (c) { return c.termina; }},
            {key: 'evaluar', label: 'Evaluar', cls: 'atencion', vacio: 'No hay clientes por evaluar.',
                filtro: function (c) { return c.segmento === 'evaluar'; }, orden: function (c) { return c.puntaje; }, desc: true},
            {key: 'no_prestar', label: 'No aptos', cls: 'critico', vacio: 'No hay clientes no aptos.',
                filtro: function (c) { return c.segmento === 'no_prestar'; }, orden: function (c) { return c.puntaje; }},
            {key: 'llamar', label: 'Llamar hoy', sub: 'seguimientos vencidos', vacio: 'No hay llamadas pendientes para hoy.',
                filtro: function (c) {
                    var s = c.seguimiento;
                    return s && s.proximo_contacto && s.proximo_contacto <= this.data.hoy && c.segmento !== 'no_prestar' &&
                        !_.contains(['no_interesado', 'nuevo_prestamo'], s.estado);
                },
                orden: function (c) { return c.seguimiento.proximo_contacto; }},
            {key: 'todos', label: 'Todos', sub: 'con historial de créditos', vacio: 'No hay clientes con historial de créditos.',
                filtro: function () { return true; }, orden: function (c) { return c.nombre; }},
        ],

        _items: function () {
            return this.data.clientes;
        },

        _preparar: function () {
            this._limitePronto = this.hoy.clone().add(this.data.dias_proximos, 'days').format('YYYY-MM-DD');
            this.data.clientes.forEach(function (c) {
                c._id = c.id;
                c._buscar = normalizar([c.nombre, c.documento, c.telefono,
                    _.pluck(c.creditos, 'referencia').join(' '), _.pluck(c.creditos, 'moto').join(' ')].join(' '));
            });
        },

        _subtitulos: function (base) {
            var self = this;
            var en = function (k) { return base.filter(function (c) { return self._enTab(c, k); }); };
            var aptos = en('apto');
            var noAptos = en('no_prestar');
            var sinContactar = aptos.filter(function (c) { return !c.seguimiento || c.seguimiento.estado === 'por_contactar'; }).length;
            var tipo = function (m) { return m.replace(/\s*\(.*\)$/, '').replace(/:.*$/, ''); };
            var motivos = _.countBy(_.flatten(noAptos.map(function (c) { return _.uniq(c.bloqueos.map(tipo)); })));
            var principal = _.max(_.pairs(motivos), function (p) { return p[1]; });
            return {
                apto: {texto: sinContactar + ' sin contactar'},
                pronto: {texto: 'en ' + this.data.dias_proximos + ' días'},
                evaluar: {texto: 'puntaje ' + this.data.umbral_minimo + '–' + (this.data.umbral_apto - 1)},
                no_prestar: {texto: principal && principal[0] ? principal[0] : ''},
            };
        },

        _columnas: function () {
            var cols = [
                {label: 'Cliente', html: function (c) { return celda('<b>' + esc(c.nombre) + '</b>', esc(c.documento)); }},
                {label: 'Teléfono', html: function (c) { return esc(c.telefono || '—'); }},
                {label: 'Puntaje', num: true, html: function (c) {
                    return '<span class="adt_cf__score is-' + this._zona(c.puntaje) + '">' + c.puntaje + '</span>';
                }},
                {label: 'A tiempo', num: true, html: function (c) { return c.puntualidad === null ? '—' : c.puntualidad + '%'; }},
                {label: 'Créditos', num: true, html: function (c) { return c.n_terminados + '/' + c.n_creditos; }},
            ];
            if (this.tab === 'no_prestar') {
                cols.push({label: 'Motivo', wrap: true, html: function (c) {
                    return c.bloqueos.map(function (b) { return '<span class="adt_cf__badge is-critico">' + esc(b) + '</span>'; }).join('');
                }});
                return cols;
            }
            if (this.tab === 'pronto') {
                cols.push({label: 'Termina', html: function (c) { return fecha(c.termina); }});
            } else if (this.tab === 'llamar' || this.tab === 'todos') {
                cols.push({label: 'Estado', html: function (c) { return segmento(c.segmento); }});
            } else {
                cols.push({label: 'Terminó', html: function (c) { return fecha(c.termino); }});
            }
            cols.push({label: 'Seguimiento', html: function (c) {
                var s = c.seguimiento;
                if (!s) { return '<span class="adt_cf__muted">—</span>'; }
                var cerrado = _.contains(['no_interesado', 'nuevo_prestamo'], s.estado);
                var vencido = !cerrado && s.proximo_contacto && s.proximo_contacto <= this.data.hoy;
                return celda(esc(this.data.estados_seguimiento[s.estado] || ''), s.proximo_contacto && !cerrado ?
                    '<span class="' + (vencido ? 'adt_cf__score is-critico' : '') + '">llamar ' + fecha(s.proximo_contacto) + '</span>' : '');
            }});
            return cols;
        },

        _zona: function (puntaje) {
            return puntaje >= this.data.umbral_apto ? 'ok' : puntaje >= this.data.umbral_minimo ? 'atencion' : 'critico';
        },

        _renderPanel: function () {
            var self = this;
            var c = this.clientesPorId[this.abierto];
            if (!c) { this._cerrar(); return; }
            var s = c.seguimiento || {estado: 'por_contactar', clasificacion_manual: '', motivo_manual: '', proximo_contacto: null, notas: ''};
            var dato = function (label, valor, cls) {
                return '<div' + (cls ? ' class="is-' + cls + '"' : '') + '><dt>' + esc(label) + '</dt><dd>' + valor + '</dd></div>';
            };
            var descuentos = c.factores.length || c.bloqueos.length ?
                '<section class="adt_cf__sec"><div class="adt_cf__label">Descuentos al puntaje</div>' +
                c.bloqueos.map(function (b) { return '<span class="adt_cf__badge is-critico">' + esc(b) + '</span>'; }).join('') +
                '<ul class="adt_cf__list">' + c.factores.map(function (f) {
                    return '<li><span>' + esc(f.texto) + '</span><b>' + f.puntos + '</b></li>';
                }).join('') + '</ul></section>' : '';
            var creditos = c.creditos.slice().reverse().map(function (k) {
                return '<tr data-cuenta="' + k.id + '"><td>' + celda('<b>' + esc(k.referencia) + '</b>', esc(k.moto)) + '</td>' +
                    '<td>' + celda(esc(k.estado_texto), k.estado === 'en_curso' && k.restantes ? k.restantes + ' cuotas por pagar' : 'hasta ' + fecha(k.fin)) + '</td>' +
                    '<td class="text-right">' + (k.puntualidad === null ? '—' : k.puntualidad + '%') + '</td></tr>';
            }).join('');
            this._abrirPanel(
                this._cabecera(c.nombre, _.compact([c.documento, c.telefono, c.financiera]).join(' · '), segmento(c.segmento)) +
                '<div class="adt_cf__side-body">' +
                '<section class="adt_cf__sec"><dl class="adt_cf__fields">' +
                dato('Puntaje', c.puntaje + ' / 100', this._zona(c.puntaje) === 'ok' ? 'ok' : this._zona(c.puntaje) === 'critico' ? 'critico' : '') +
                dato('Pagó a tiempo', c.puntualidad === null ? '—' : c.puntualidad + '%') +
                dato('Atraso promedio', c.atraso_promedio + ' días') +
                dato('Atraso máximo', c.atraso_maximo + ' días') +
                dato('Capturas', c.capturas, c.capturas ? 'critico' : '') +
                dato('Papeletas', c.papeletas) +
                '</dl></section>' + descuentos +
                '<section class="adt_cf__sec"><div class="adt_cf__label">Créditos</div><table class="adt_cf__dtable"><tbody>' + creditos + '</tbody></table></section>' +
                '<section class="adt_cf__sec"><div class="adt_cf__label">Seguimiento</div><div class="adt_cf__form">' +
                '<label><span>Estado</span><select class="adt_cf__input" data-ref="estado">' + this._opciones(this.data.estados_seguimiento, s.estado) + '</select></label>' +
                '<label><span>Próximo contacto</span><input type="date" class="adt_cf__input" data-ref="proximo" value="' + esc(s.proximo_contacto || '') + '"/></label>' +
                '<label class="is-full"><span>Clasificación</span><select class="adt_cf__input" data-ref="clasificacion">' +
                this._opciones(this.data.clasificaciones, s.clasificacion_manual, 'Automática (según puntaje)') + '</select></label>' +
                '<label class="is-full"><span>Motivo de la clasificación</span><input type="text" class="adt_cf__input" data-ref="motivo" value="' +
                esc(s.motivo_manual || '') + '"/></label>' +
                '<label class="is-full"><span>Notas</span><textarea class="adt_cf__input" rows="3" data-ref="notas">' + esc(s.notas || '') + '</textarea></label>' +
                '</div><p class="adt_cf__error" data-ref="error" hidden="hidden"></p><div class="adt_cf__form-foot">' +
                (c.seguimiento ? '<button type="button" class="adt_cf__btn" data-action="historial" data-model="adt.cliente.seguimiento" data-id="' +
                    c.seguimiento.id + '">Historial</button>' : '<span></span>') +
                '<button type="button" class="adt_cf__btn is-primary" data-action="guardar">Guardar</button></div></section>' +
                '</div>'
            );
            self._ref('side').find('[data-ref="motivo"]').closest('label').prop('hidden', !s.clasificacion_manual);
        },

        events: _.extend({}, FlotaClientes.prototype.events, {
            'change [data-ref="clasificacion"]': '_onClasificacion',
        }),

        _onClasificacion: function (ev) {
            this._ref('side').find('[data-ref="motivo"]').closest('label').prop('hidden', !ev.currentTarget.value);
        },

        _onGuardar: function () {
            var $p = this._ref('side');
            var clasificacion = $p.find('[data-ref="clasificacion"]').val();
            var valores = {
                estado: $p.find('[data-ref="estado"]').val(),
                proximo_contacto: $p.find('[data-ref="proximo"]').val() || false,
                clasificacion_manual: clasificacion || false,
                motivo_manual: clasificacion ? $p.find('[data-ref="motivo"]').val() : false,
                notas: $p.find('[data-ref="notas"]').val(),
            };
            if (clasificacion === 'no_prestar' && !(valores.motivo_manual || '').trim()) {
                $p.find('[data-ref="error"]').text('Indica el motivo para marcarlo como No apto.').prop('hidden', false);
                return;
            }
            this._guardar('guardar_seguimiento', this.abierto, valores);
        },
    });

    // ====================================================================== Traspaso notarial

    var ETAPA_CLS = {pendiente: 'neutral', documentos: 'atencion', en_notaria: 'info', en_registros: 'info', completado: 'ok'};

    var TraspasoNotarial = FlotaClientes.extend({
        modo: 'traspasos',
        titulo: 'Traspaso notarial',
        tabs: [
            {key: 'listo', label: 'Listos para notaría', vacio: 'No hay motos pagadas esperando su traspaso.',
                filtro: function (t) { return t.etapa === 'listo'; }, orden: function (t) { return t.fin || ''; }},
            {key: 'preparar', label: 'Ir preparando', vacio: 'Ninguna cuenta termina de pagar pronto.',
                filtro: function (t) { return t.etapa === 'preparar'; }, orden: function (t) { return t.fin || '9999'; }},
            {key: 'en_tramite', label: 'En trámite', vacio: 'No hay traspasos en trámite.',
                filtro: function (t) { return t.etapa === 'en_tramite'; }, orden: function (t) { return t.traspaso.fecha_firma || t.fin || ''; }},
            {key: 'completado', label: 'Completados', cls: 'ok', vacio: 'Aún no hay traspasos completados.',
                filtro: function (t) { return t.etapa === 'completado'; }, orden: function (t) { return t.traspaso.fecha_completado || ''; }, desc: true},
            {key: 'observadas', label: 'Con observaciones', cls: 'critico', sub: 'sin placa, papeletas o deuda',
                vacio: 'Ninguna moto por traspasar tiene observaciones.',
                filtro: function (t) { return t.etapa !== 'completado' && t.alertas.length > 0; }, orden: function (t) { return t.fin || ''; }},
        ],

        _items: function () {
            return this.data.traspasos;
        },

        _preparar: function () {
            var hoy = this.hoy;
            this.data.traspasos.forEach(function (t) {
                t._id = t.cuenta_id;
                t._dias = t.terminada && t.fin ? hoy.diff(moment(t.fin), 'days') : null;
                t._buscar = normalizar([t.nombre, t.documento, t.telefono, t.referencia, t.placa, t.moto,
                    t.traspaso ? t.traspaso.notaria : ''].join(' '));
            });
        },

        _subtitulos: function (base) {
            var en = function (k) { return base.filter(function (t) { return t.etapa === k; }); };
            var listos = en('listo');
            var demorados = listos.filter(function (t) { return t._dias > 30; }).length;
            var tramite = en('en_tramite');
            var enNotaria = tramite.filter(function (t) { return t.traspaso.estado !== 'documentos'; }).length;
            var completados = en('completado');
            var mes = this.hoy.format('YYYY-MM');
            return {
                listo: {cls: demorados ? 'atencion' : '', texto: demorados ? demorados + ' esperan más de 30 días' : 'pagaron todo'},
                preparar: {texto: 'terminan en ' + this.data.dias_preparar_traspaso + ' días'},
                en_tramite: {texto: enNotaria + ' en notaría o SUNARP'},
                completado: {texto: completados.filter(function (t) {
                    return (t.traspaso.fecha_completado || '').slice(0, 7) === mes;
                }).length + ' este mes'},
            };
        },

        _columnas: function () {
            var cols = [
                {label: 'Cliente', html: function (t) { return celda('<b>' + esc(t.nombre) + '</b>', esc(t.telefono || t.documento)); }},
                {label: 'Placa', html: function (t) { return celda(this._placa(t), esc(t.moto)); }},
                {label: 'Cuenta', html: function (t) { return esc(t.referencia); }},
            ];
            var observaciones = {label: 'Observaciones', wrap: true, html: function (t) {
                return t.alertas.map(function (a) { return '<span class="adt_cf__badge is-critico">' + esc(a) + '</span>'; }).join('') ||
                    '<span class="adt_cf__muted">—</span>';
            }};
            var candidato = {label: 'Nuevo préstamo', html: function (t) {
                var c = this.clientesPorId[t.cliente_id];
                return c ? segmento(c.segmento) : '<span class="adt_cf__muted">—</span>';
            }};
            var notaria = {label: 'Notaría', html: function (t) {
                return celda(esc(t.traspaso.notaria || '—'), t.traspaso.fecha_firma ? 'firma ' + fecha(t.traspaso.fecha_firma) : '');
            }};
            switch (this.tab) {
                case 'listo':
                    return cols.concat([{label: 'Pagó', html: function (t) {
                        return celda(fecha(t.fin), t._dias > 0 ? '<span class="' + (t._dias > 30 ? 'adt_cf__score is-atencion' : '') + '">hace ' + t._dias + ' días</span>' : '');
                    }}, candidato, observaciones]);
                case 'preparar':
                    return cols.concat([{label: 'Termina', html: function (t) {
                        return celda(fecha(t.fin), t.restantes + (t.restantes === 1 ? ' cuota' : ' cuotas'));
                    }}, candidato, observaciones]);
                case 'en_tramite':
                    return cols.concat([{label: 'Etapa', html: function (t) {
                        return st(ETAPA_CLS[t.traspaso.estado], this.data.estados_traspaso[t.traspaso.estado]);
                    }}, notaria, observaciones]);
                case 'observadas':
                    return cols.concat([{label: 'Etapa', html: function (t) {
                        return t.traspaso ? st(ETAPA_CLS[t.traspaso.estado], this.data.estados_traspaso[t.traspaso.estado]) :
                            st('neutral', t.terminada ? 'Listo para notaría' : 'Por terminar de pagar');
                    }}, observaciones]);
                default:
                    return cols.concat([notaria, {label: 'Completado', html: function (t) { return fecha(t.traspaso.fecha_completado); }}]);
            }
        },

        _placa: function (t) {
            return t.placa ? '<span class="adt_cf__plate">' + esc(t.placa) + '</span>' : '<span class="adt_cf__plate is-empty">Sin placa</span>';
        },

        _renderPanel: function () {
            var t = _.find(this.data.traspasos, function (x) { return x.cuenta_id === this.abierto; }, this);
            if (!t) { this._cerrar(); return; }
            var tr = t.traspaso || {estado: 'pendiente', notaria: '', fecha_firma: null, fecha_completado: null, notas: ''};
            var estados = this.data.estados_traspaso;
            var requierenPago = this.data.estados_requieren_pago;
            var claves = _.keys(estados);
            var actual = claves.indexOf(tr.estado);
            var c = this.clientesPorId[t.cliente_id];
            var dato = function (label, valor) { return '<div><dt>' + esc(label) + '</dt><dd>' + valor + '</dd></div>'; };
            var pasos = claves.map(function (k, i) {
                var cls = i < actual || tr.estado === 'completado' ? 'is-done' : i === actual ? 'is-current' : '';
                return '<li class="' + cls + '"><i></i>' + esc(estados[k]) + '</li>';
            }).join('');
            var opciones = claves.map(function (k) {
                var bloqueada = !t.terminada && _.contains(requierenPago, k);
                return '<option value="' + k + '"' + (k === tr.estado ? ' selected' : '') + (bloqueada ? ' disabled' : '') + '>' +
                    esc(estados[k]) + (bloqueada ? ' (al terminar de pagar)' : '') + '</option>';
            }).join('');
            this._abrirPanel(
                this._cabecera(t.nombre, _.compact([t.documento, t.telefono, t.financiera]).join(' · '),
                    t.traspaso ? st(ETAPA_CLS[tr.estado], estados[tr.estado]) : st('neutral', t.terminada ? 'Listo para notaría' : 'Por terminar de pagar')) +
                '<div class="adt_cf__side-body">' +
                '<section class="adt_cf__sec"><dl class="adt_cf__fields">' +
                dato('Cuenta', '<a href="#" data-cuenta="' + t.cuenta_id + '">' + esc(t.referencia) + '</a>') +
                dato('Placa', this._placa(t)) +
                dato('Moto', esc(t.moto || '—')) +
                dato(t.terminada ? 'Pagó su última cuota' : 'Termina de pagar', fecha(t.fin) + (t.terminada ? '' : ' · ' + t.restantes + ' cuotas')) +
                dato('Nuevo préstamo', c ? segmento(c.segmento) : '—') +
                '</dl>' + (t.alertas.length ? '<div class="mt-3">' + t.alertas.map(function (a) {
                    return '<span class="adt_cf__badge is-critico">' + esc(a) + '</span>';
                }).join('') + '</div>' : '') + '</section>' +
                '<section class="adt_cf__sec"><div class="adt_cf__label">Etapas</div><ol class="adt_cf__steps">' + pasos + '</ol></section>' +
                '<section class="adt_cf__sec"><div class="adt_cf__label">Registrar avance</div><div class="adt_cf__form">' +
                '<label class="is-full"><span>Etapa</span><select class="adt_cf__input" data-ref="t-estado">' + opciones + '</select></label>' +
                '<label><span>Notaría</span><input type="text" class="adt_cf__input" data-ref="t-notaria" value="' + esc(tr.notaria || '') + '"/></label>' +
                '<label><span>Fecha de firma</span><input type="date" class="adt_cf__input" data-ref="t-firma" value="' + esc(tr.fecha_firma || '') + '"/></label>' +
                '<label data-ref="t-completado-wrap"' + (tr.estado === 'completado' ? '' : ' hidden="hidden"') + '><span>Fecha completado</span>' +
                '<input type="date" class="adt_cf__input" data-ref="t-completado" value="' + esc(tr.fecha_completado || '') + '"/></label>' +
                '<label class="is-full"><span>Notas</span><textarea class="adt_cf__input" rows="3" data-ref="t-notas">' + esc(tr.notas || '') + '</textarea></label>' +
                '</div><div class="adt_cf__form-foot">' +
                (t.traspaso ? '<button type="button" class="adt_cf__btn" data-action="historial" data-model="adt.traspaso.notarial" data-id="' +
                    t.traspaso.id + '">Historial</button>' : '<span></span>') +
                '<button type="button" class="adt_cf__btn is-primary" data-action="guardar">Guardar</button></div></section>' +
                '</div>'
            );
        },

        events: _.extend({}, FlotaClientes.prototype.events, {
            'change [data-ref="t-estado"]': '_onEstado',
        }),

        _onEstado: function (ev) {
            this._ref('t-completado-wrap').prop('hidden', ev.currentTarget.value !== 'completado');
        },

        _onGuardar: function () {
            var $p = this._ref('side');
            var estado = $p.find('[data-ref="t-estado"]').val();
            this._guardar('guardar_traspaso', this.abierto, {
                estado: estado,
                notaria: $p.find('[data-ref="t-notaria"]').val(),
                fecha_firma: $p.find('[data-ref="t-firma"]').val() || false,
                fecha_completado: estado === 'completado' ? ($p.find('[data-ref="t-completado"]').val() || false) : false,
                notas: $p.find('[data-ref="t-notas"]').val(),
            });
        },
    });

    core.action_registry.add('adt_candidatos_prestamo', CandidatosPrestamo);
    core.action_registry.add('adt_traspaso_notarial', TraspasoNotarial);

    return {CandidatosPrestamo: CandidatosPrestamo, TraspasoNotarial: TraspasoNotarial};
});
