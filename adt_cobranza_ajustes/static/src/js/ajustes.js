odoo.define('adt_cobranza_ajustes.Ajustes', function (require) {
    'use strict';
    var Flota360 = require('adt_flota_360.Flota360');
    var Dialog = require('web.Dialog');
    var esc = _.escape;

    function money(monto, simbolo) {
        return (simbolo || 'S/') + ' ' + Number(monto || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    function r2(n) { return Math.round((Number(n) || 0) * 100) / 100; }
    function fechaTxt(iso) {
        if (!iso) { return '—'; }
        var p = iso.slice(0, 10).split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    }
    function sumarDias(iso, dias) {
        var d = new Date(iso + 'T12:00:00');
        d.setDate(d.getDate() + dias);
        return d.toISOString().slice(0, 10);
    }
    // Fecha de la cuota k (0 = la primera) según la periodicidad; los meses son meses reales.
    function sumarPeriodo(iso, periodo, k) {
        if (periodo !== 'mensual') {
            return sumarDias(iso, (periodo === 'semanal' ? 7 : 15) * k);
        }
        var d = new Date(iso + 'T12:00:00'), dia = d.getDate();
        d.setDate(1);
        d.setMonth(d.getMonth() + k);
        d.setDate(Math.min(dia, new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()));
        return d.toISOString().slice(0, 10);
    }
    var PERIODOS = [['semanal', 'Semana'], ['quincena', 'Quincena'], ['mensual', 'Mes']];
    var ICONO_LINEA = {creada: 'fa-plus-circle', eliminada: 'fa-minus-circle', modificada: 'fa-pencil'};

    Flota360.include({
        events: _.extend({}, Flota360.prototype.events, {
            'click [data-ajuste-deshacer]': '_onDeshacerAjuste',
            'click [data-ajuste-filtro]': '_onFiltroAjustes',
            'input [data-ed]': '_onEditorCampo',
            'change [data-ed]': '_onEditorCampo',
            'click [data-ed-accion]': '_onEditorAccion',
            'click [data-ed-mora]': '_onEditorMora',
            'click [data-ed-aplicar]': '_onEditorAplicar',
            'click [data-ed-paso]': '_onEditorPaso',
            'click [data-ed-modo]': '_onEditorModo',
            'click [data-ed-gen]': '_onEditorGen',
        }),
        init: function () {
            this._super.apply(this, arguments);
            this._simularAjusteDiferido = _.debounce(this._simularAjuste.bind(this), 300);
        },
        destroy: function () {
            this._simularAjusteDiferido.cancel();
            return this._super.apply(this, arguments);
        },

        _ejecutar: function (a) {
            if (a && a.tipo === 'editor_crono') {
                return this._abrirEditor(a.cuenta_id);
            }
            return this._super.apply(this, arguments);
        },

        // ------------------------------------------------------------------
        // Formularios de ajuste: vista previa en vivo (el servidor aplica y descarta)
        // ------------------------------------------------------------------

        _abrirForm: function (clave) {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                var m = self._modal;
                if (clave !== 'ajuste' || !m || !m.spec || m.spec.clave !== 'ajuste') { return; }
                var $m = self._ref('modal');
                // Vista previa en la columna derecha, a la vista mientras se completa el formulario.
                $m.find('.adt_f360__modal').addClass('is-ajuste is-split');
                $m.find('.adt_f360__modal-foot').before('<aside class="adt_f360__modal-side"><div class="adt_f360__ajprev" data-ajuste-preview aria-live="polite">' +
                    '<p class="adt_f360__muted">Calculando cómo quedará…</p></div></aside>');
                // El motivo va bajo la vista previa: así el formulario cabe sin desplazarse.
                // Al eliminar es el único campo y se queda a la izquierda.
                if (m.params.tipo !== 'eliminar') {
                    $m.find('[data-campo-wrap="motivo"]').closest('.adt_f360__fieldset').addClass('is-side')
                        .appendTo($m.find('.adt_f360__modal-side'));
                }
                $m.find('[data-guardar] span').text(m.params.tipo === 'eliminar' ? 'Eliminar cuota' : 'Aplicar ajuste');
                $m.find('[data-guardar]').toggleClass('is-danger', m.params.tipo === 'eliminar');
                self._simularAjuste();
            });
        },
        _actualizarForm: function () {
            this._super.apply(this, arguments);
            var m = this._modal;
            if (m && m.spec && m.spec.clave === 'ajuste') {
                this._simularAjusteDiferido();
            }
        },
        _simularAjuste: function () {
            var self = this, m = this._modal;
            if (!m || !m.spec || m.spec.clave !== 'ajuste') { return; }
            // El motivo no cambia el resultado: escribirlo no recalcula ni mueve la vista previa.
            var clave = JSON.stringify(_.omit(m.valores, 'motivo'));
            if (clave === m.ajClave) { return; }
            m.ajClave = clave;
            var seq = (m.ajSeq || 0) + 1;
            m.ajSeq = seq;
            return this._llamar('simular_ajuste', {vehicle_id: this._drawerId, params: m.params, valores: _.clone(m.valores)})
                .then(function (res) {
                    if (self._modal !== m || m.ajSeq !== seq) { return; }
                    var $prev = self._ref('modal').find('[data-ajuste-preview]').html(self._htmlVistaPrevia(res));
                    self._enfocarPrincipal($prev);
                }).catch(function (err) {
                    if (err && err.event) { err.event.preventDefault(); }
                    if (self._modal === m && m.ajSeq === seq) {
                        m.ajClave = null;
                        self._ref('modal').find('[data-ajuste-preview]').html(self._htmlVistaPrevia({error: self._error(err)}));
                    }
                });
        },
        // Centra la lista en la cuota que motivó el ajuste; el resto queda a un desplazamiento.
        _enfocarPrincipal: function ($cont) {
            var lista = $cont.find('.adt_f360__ajlines')[0];
            var li = lista && $(lista).find('.is-principal')[0];
            if (li) {
                lista.scrollTop = Math.max(li.offsetTop - (lista.clientHeight - li.offsetHeight) / 2, 0);
            }
        },

        _htmlVistaPrevia: function (r) {
            if (r.error) {
                return '<p class="adt_f360__ajprev-error"><i class="fa fa-exclamation-circle" aria-hidden="true"></i>' + esc(r.error) + '</p>';
            }
            var cambio = r2(r.deuda_despues - r.deuda_antes);
            return '<div class="adt_f360__label">Así quedará</div>' + this._htmlLineasAjuste(r) +
                '<div class="adt_f360__ajprev-foot"><span>Deuda pendiente</span><span>' + esc(money(r.deuda_antes)) +
                    ' <i class="fa fa-long-arrow-right" aria-hidden="true"></i> <b>' + esc(money(r.deuda_despues)) + '</b>' +
                    (cambio ? ' <em class="' + (cambio > 0 ? 'is-up' : 'is-down') + '">' + (cambio > 0 ? '+' : '−') + esc(money(Math.abs(cambio))) + '</em>' : '') +
                '</span></div>' +
                (r.mora_perdonada ? '<div class="adt_f360__ajprev-foot is-perdon"><span>Mora perdonada</span><b>' + esc(money(r.mora_perdonada)) + '</b></div>' : '');
        },
        _htmlLineasAjuste: function (r) {
            if (!r.lineas.length) { return '<p class="adt_f360__muted">Sin cambios en las cuotas.</p>'; }
            return (r.lineas.length > 1 ? '<div class="adt_f360__sub adt_f360__ajcount">' + r.lineas.length + ' cuotas cambian</div>' : '') +
                '<ul class="adt_f360__ajlines">' + r.lineas.map(function (l) {
                return '<li class="is-' + l.accion + (l.principal ? ' is-principal' : '') + '"><i class="fa ' + ICONO_LINEA[l.accion] + '" aria-hidden="true"></i>' +
                    '<b>' + esc(l.cuota) + '</b><span>' + esc(l.texto) + '</span></li>';
            }).join('') + '</ul>';
        },

        // ------------------------------------------------------------------
        // Pestaña «Ajustes» de la cuenta
        // ------------------------------------------------------------------

        _pestanasCuentaExtra: function (c) {
            var extra = this._super.apply(this, arguments);
            var self = this;
            if (!c.ajustes || (!c.ajustes.length && c.state !== 'en_curso')) { return extra; }
            return extra.concat([{key: 'ajustes', label: 'Historial de ajustes y refinanciamientos', icon: 'fa-history', n: c.ajustes.length,
                                  render: function () { return self._htmlAjustes(c); }}]);
        },
        // Historial de ajustes; «Refinanciamientos» filtra los cambios de cronograma completos y
        // muestra el cronograma pendiente antes y después de cada uno.
        _htmlAjustes: function (c) {
            var self = this;
            if (!c.ajustes.length) {
                return this._vacio('Aún no hay ajustes. Usa las opciones de cada cuota o el menú de la cuenta para reprogramar, trasladar saldos, acordar mora o editar el cronograma.', 'fa-sliders');
            }
            this.filtroAjustes = this.filtroAjustes || {};
            var filtro = this.filtroAjustes[c.id] || 'todos';
            var refin = c.ajustes.filter(function (a) { return a.clave === 'editar'; });
            var lista = filtro === 'refin' ? refin : c.ajustes;
            var seg = '<div class="adt_f360__ptab-tools"><div class="adt_f360__seg">' + [['todos', 'Todos', c.ajustes.length], ['refin', 'Refinanciamientos', refin.length]].map(function (x) {
                return '<button type="button" class="' + (filtro === x[0] ? 'is-active' : '') + '" data-ajuste-filtro="' + x[0] + '" data-cuenta="' + c.id + '">' +
                    x[1] + ' (' + x[2] + ')</button>';
            }).join('') + '</div></div>';
            if (!lista.length) {
                return seg + this._vacio('Esta cuenta no tiene refinanciamientos registrados.', 'fa-table');
            }
            return seg + '<ol class="adt_f360__ajlist">' + lista.map(function (a) {
                var revertido = a.estado === 'revertido';
                return '<li class="adt_f360__ajcard' + (revertido ? ' is-revertido' : '') + (a.clave === 'editar' ? ' is-refin' : '') + '">' +
                    '<header><div><b>' + esc(a.tipo) + '</b>' + (revertido ? ' <span class="adt_f360__ajtag">Deshecho</span>' : '') +
                        '<span class="adt_f360__sub">' + esc(fechaTxt(a.fecha)) + ' · ' + esc(a.usuario) + '</span></div>' +
                        (a.deshacer ? '<button type="button" class="adt_f360__btn is-small" data-ajuste-deshacer="' + a.id + '">' +
                            '<i class="fa fa-undo" aria-hidden="true"></i><span>Deshacer</span></button>' : '') + '</header>' +
                    (a.motivo ? '<p class="adt_f360__ajmotivo"><i class="fa fa-quote-left" aria-hidden="true"></i>' + esc(a.motivo) + '</p>' : '') +
                    (a.cronograma ? self._htmlRefinanciamiento(a.cronograma) : self._htmlLineasAjuste(a)) +
                    '<div class="adt_f360__ajprev-foot"><span>Deuda pendiente</span><span>' + esc(money(a.deuda_antes)) +
                        ' <i class="fa fa-long-arrow-right" aria-hidden="true"></i> <b>' + esc(money(a.deuda_despues)) + '</b></span></div>' +
                    (a.mora_perdonada ? '<div class="adt_f360__ajprev-foot is-perdon"><span>Mora perdonada</span><b>' + esc(money(a.mora_perdonada)) + '</b></div>' : '') +
                    (a.diferencia ? '<div class="adt_f360__ajdif"><b>' + (a.diferencia > 0 ? '+' : '−') + esc(money(Math.abs(a.diferencia))) +
                        ' respecto a lo refinanciado</b><span>' + esc(a.diferencia_motivo) + '</span></div>' : '') +
                    '</li>';
            }).join('') + '</ol>';
        },
        // Resumen del refinanciamiento y, a pedido, los dos cronogramas lado a lado.
        _htmlRefinanciamiento: function (cr) {
            var resumen = function (filas) {
                var total = filas.reduce(function (s, f) { return s + f.saldo; }, 0);
                return '<b>' + filas.length + '</b> cuotas · <b>' + esc(money(total)) + '</b>' +
                    (filas.length ? '<span class="adt_f360__sub">' + esc(fechaTxt(filas[0].fecha)) + ' – ' + esc(fechaTxt(_.last(filas).fecha)) + '</span>' : '');
            };
            var tabla = function (titulo, filas) {
                return '<div><div class="adt_f360__label">' + titulo + '</div><div class="adt_f360__refin-scroll"><table class="adt_f360__dtable">' +
                    '<thead><tr><th>Cuota</th><th>Vence</th><th class="is-num">Pendiente</th></tr></thead><tbody>' + filas.map(function (f) {
                        return '<tr><td>' + esc(f.nombre) + (f.tipo ? ' <span class="adt_f360__ajtag">' + esc(f.tipo) + '</span>' : '') + '</td>' +
                            '<td>' + esc(fechaTxt(f.fecha)) + '</td><td class="is-num">' + esc(money(f.saldo)) + '</td></tr>';
                    }).join('') + '</tbody></table></div></div>';
            };
            return '<div class="adt_f360__refin">' +
                '<div class="adt_f360__refin-sum"><div><span class="adt_f360__label">Antes</span>' + resumen(cr.antes) + '</div>' +
                    '<i class="fa fa-long-arrow-right" aria-hidden="true"></i>' +
                    '<div><span class="adt_f360__label">Después</span>' + resumen(cr.despues) + '</div></div>' +
                '<details class="adt_f360__refin-det"><summary>Ver cronograma antes y después</summary>' +
                    '<div class="adt_f360__refin-grid">' + tabla('Cronograma anterior', cr.antes) + tabla('Cronograma nuevo', cr.despues) + '</div>' +
                '</details></div>';
        },
        _onFiltroAjustes: function (ev) {
            this.filtroAjustes = this.filtroAjustes || {};
            this.filtroAjustes[ev.currentTarget.getAttribute('data-cuenta')] = ev.currentTarget.getAttribute('data-ajuste-filtro');
            this._renderDrawer();
        },
        _onDeshacerAjuste: function (ev) {
            var self = this, id = parseInt(ev.currentTarget.getAttribute('data-ajuste-deshacer'), 10);
            Dialog.confirm(this, '¿Deshacer este ajuste? Las cuotas vuelven a como estaban antes de aplicarlo.', {
                title: 'Deshacer ajuste',
                confirm_callback: function () {
                    return self._llamar('revertir_ajuste', {vehicle_id: self._drawerId, ajuste_id: id}).then(function (res) {
                        self.displayNotification({type: 'success', message: res.mensaje});
                        return self._recargar();
                    }).catch(function (err) {
                        if (err && err.event) { err.event.preventDefault(); }
                        self.displayNotification({type: 'danger', title: 'No se pudo deshacer', message: self._error(err)});
                    });
                },
            });
        },

        // ------------------------------------------------------------------
        // Refinanciar o editar el cronograma: asistente en 3 pasos.
        //   1. Qué se refinancia: deuda + mora (según lo que se decida) + adicional = total.
        //   2. Nuevo cronograma: cuotas iguales o editar las actuales; debe sumar el total.
        //   3. Confirmar: antes → después (simulado en el servidor) y motivo.
        // ------------------------------------------------------------------

        _abrirEditor: function (cuentaId) {
            var self = this;
            return this._llamar('editor_cronograma', {vehicle_id: this._drawerId, cuenta_id: cuentaId}).then(function (d) {
                var libres = d.filas.filter(function (f) { return !f.pagado; });
                var ed = {
                    d: d, paso: 1, adicional: 0, motivo: '', dif_motivo: '', modo: null, prev: null,
                    mora_accion: d.mora > 0 ? 'incluir' : 'mantener', mora_acordada: d.mora, mora_fecha: d.hoy,
                    gen_n: Math.max(libres.length, 1), gen_desde: d.hoy,
                    gen_por: 'n', gen_monto: d.monto_cuota || 0, gen_periodo: d.periodicidad || 'quincena', gen_resto: 'aparte',
                    filas: d.filas.map(function (f) { return _.extend({}, f, {fija: false}); }),
                };
                self._mostrarModal({tipo: 'editor', ancho: true, ed: ed}, self._htmlEditor(ed));
                self._ref('modal').find('.adt_f360__modal').addClass('is-split is-editor');
                // Empieza arriba: el modal enfoca el primer campo y eso desplazaba la columna de opciones.
                if (document.activeElement) { document.activeElement.blur(); }
                self._ref('modal').find('.adt_f360__modal-body').scrollTop(0);
                self._editorTotales();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                self.displayNotification({type: 'danger', title: 'No disponible', message: self._error(err)});
            });
        },
        _renderEditor: function () {
            var m = this._modal;
            this._ref('modal').find('.adt_f360__modal').html(this._htmlEditor(m.ed));
            this._editorTotales();
        },
        _editorMora: function (ed) {
            return r2(Math.min(Math.max(Number(ed.mora_acordada) || 0, 0), ed.d.mora));
        },
        _editorObjetivo: function (ed) {
            return r2(ed.d.deuda + (Number(ed.adicional) || 0) + (ed.mora_accion === 'incluir' ? this._editorMora(ed) : 0));
        },
        _editorSuma: function (ed) {
            return r2(ed.filas.reduce(function (s, f) { return s + (Number(f.saldo) || 0); }, 0));
        },
        _editorDif: function (ed) {
            return r2(this._editorSuma(ed) - this._editorObjetivo(ed));
        },
        // Se puede seguir si cuadra o si la diferencia (más o menos que lo refinanciado) está explicada.
        _editorCuadra: function (ed) {
            return (Math.abs(this._editorDif(ed)) < 0.005 || !!ed.dif_motivo.trim()) && ed.filas.length &&
                _.every(ed.filas, function (f) { return f.fecha; });
        },

        // Dos columnas: a la izquierda las opciones y botones del paso; a la derecha el monto que se
        // refinancia, su resumen y el detalle de las cuotas.
        _htmlEditor: function (ed) {
            var pasos = ['Qué se refinancia', 'Nuevo cronograma', 'Confirmar'];
            var stepper = '<ol class="adt_f360__wiz-steps">' + pasos.map(function (t, i) {
                var n = i + 1, estado = n === ed.paso ? 'is-active' : (n < ed.paso ? 'is-done' : '');
                return '<li class="' + estado + '">' + (n < ed.paso ? '<button type="button" data-ed-paso="' + n + '">' : '<span>') +
                    '<b>' + (n < ed.paso ? '<i class="fa fa-check" aria-hidden="true"></i>' : n) + '</b>' + t +
                    (n < ed.paso ? '</button>' : '</span>') + '</li>';
            }).join('') + '</ol>';
            var p = ed.paso === 1 ? this._htmlEdPaso1(ed) : (ed.paso === 2 ? this._htmlEdPaso2(ed) : this._htmlEdPaso3(ed));
            var siguiente = ed.paso < 3
                ? '<button type="button" class="adt_f360__btn is-primary" data-ed-paso="' + (ed.paso + 1) + '" data-ed-siguiente><span>Siguiente</span><i class="fa fa-arrow-right" aria-hidden="true"></i></button>'
                : '<button type="button" class="adt_f360__btn is-primary" data-ed-aplicar><i class="fa fa-check" aria-hidden="true"></i><span>Aplicar refinanciamiento</span></button>';
            return this._modalCabecera('Refinanciar cronograma', ed.d.titular + ' · ' + ed.d.referencia) + stepper +
                '<div class="adt_f360__modal-body adt_f360__wiz">' + p.izq + '</div>' +
                '<aside class="adt_f360__modal-side adt_f360__wiz-der">' + this._htmlEdTotal(ed) + p.der + '</aside>' +
                '<footer class="adt_f360__modal-foot"><div class="adt_f360__modal-error" data-ref="modal-error" role="alert"></div>' +
                (ed.paso > 1 ? '<button type="button" class="adt_f360__btn" data-ed-paso="' + (ed.paso - 1) + '"><i class="fa fa-arrow-left" aria-hidden="true"></i><span>Atrás</span></button>' : '') +
                '<button type="button" class="adt_f360__btn" data-modal-close>Cancelar</button>' + siguiente + '</footer>';
        },

        // Derecha, en todos los pasos: de dónde sale el total a refinanciar.
        _htmlEdTotal: function (ed) {
            var d = ed.d, mon = d.moneda;
            if (ed.paso > 1) {
                // Compacto: deja espacio para las cuotas.
                return '<div class="adt_f360__wiz-sumline"><span>Deuda <b>' + esc(money(d.deuda, mon)) + '</b></span>' +
                    (d.mora > 0 ? '<span>+ Mora <b data-ed-v="mora"></b></span>' : '') +
                    '<span>+ Adicional <b data-ed-v="adicional"></b></span>' +
                    '<span class="is-total">Total a refinanciar <b data-ed-v="objetivo"></b></span></div>';
            }
            return '<div class="adt_f360__wiz-sum">' +
                '<div><span>Deuda pendiente <small>' + d.filas.length + ' cuotas</small></span><b>' + esc(money(d.deuda, mon)) + '</b></div>' +
                (d.mora > 0 ? '<div><span>+ Mora</span><b data-ed-v="mora"></b></div>' : '') +
                '<div><span>+ Monto adicional</span><b data-ed-v="adicional"></b></div>' +
                '<div class="is-total"><span>Total a refinanciar</span><b data-ed-v="objetivo"></b></div></div>';
        },

        // Paso 1: qué hacer con la mora y si se suma algo (izquierda); el cronograma actual (derecha).
        _htmlEdPaso1: function (ed) {
            var d = ed.d, mon = d.moneda;
            var OPC = [
                ['incluir', 'fa-plus-circle', 'Sumarla al cronograma', 'Se reparte en las nuevas cuotas.'],
                ['perdonar', 'fa-gift', 'Perdonarla', 'No se cobra.'],
                ['cargo', 'fa-calendar-plus-o', 'Cobrarla aparte', 'Queda como un cargo con su fecha.'],
                ['mantener', 'fa-minus-circle', 'Dejarla como está', 'Cada cuota conserva su mora.'],
            ];
            var izq = (d.mora > 0 ? '<h4 class="adt_f360__wiz-q">¿Qué hacemos con la mora de ' + esc(money(d.mora, mon)) + '?</h4>' +
                '<div class="adt_f360__wiz-opts" role="radiogroup">' + OPC.map(function (o) {
                    var on = ed.mora_accion === o[0];
                    return '<button type="button" role="radio" aria-checked="' + on + '" class="adt_f360__wiz-opt' + (on ? ' is-active' : '') + '" data-ed-mora="' + o[0] + '">' +
                        '<i class="fa ' + o[1] + '" aria-hidden="true"></i><b>' + o[2] + '</b><small>' + o[3] + '</small></button>';
                }).join('') + '</div>' +
                (ed.mora_accion === 'incluir' || ed.mora_accion === 'cargo'
                    ? '<div class="adt_f360__wiz-field"><label>Mora a cobrar</label><input type="number" step="0.01" min="0" class="adt_f360__input is-num is-big" data-ed="mora_acordada" value="' + r2(ed.mora_acordada).toFixed(2) + '"/>' +
                      '<small class="adt_f360__muted" data-ed-perdon></small></div>' +
                      (ed.mora_accion === 'cargo' ? '<div class="adt_f360__wiz-field"><label>El cargo vence el</label><input type="date" class="adt_f360__input" data-ed="mora_fecha" value="' + esc(ed.mora_fecha) + '"/></div>' : '')
                    : '') : '') +
                '<h4 class="adt_f360__wiz-q">¿Se suma algún monto?</h4>' +
                '<div class="adt_f360__wiz-field"><label>Monto adicional <small>gastos, intereses (opcional)</small></label>' +
                    '<input type="number" step="0.01" min="0" class="adt_f360__input is-num is-big" data-ed="adicional" value="' + r2(ed.adicional).toFixed(2) + '"/></div>';
            var der = '<div class="adt_f360__label">Cronograma actual</div><div class="adt_f360__wiz-lista"><table class="adt_f360__dtable">' +
                '<thead><tr><th>Cuota</th><th>Vence</th><th class="is-num">Pendiente</th></tr></thead><tbody>' + d.filas.map(function (f) {
                    return '<tr class="' + (f.vencida ? 'is-vencida' : '') + '"><td>' + esc(f.nombre) + (f.tipo ? ' <small class="adt_f360__muted">' + esc(f.tipo) + '</small>' : '') +
                        '</td><td>' + esc(fechaTxt(f.fecha)) + '</td><td class="is-num">' + esc(money(f.saldo, mon)) + '</td></tr>';
                }).join('') + '</tbody></table></div>';
            return {izq: izq, der: der};
        },

        // Paso 2: cómo se arma el cronograma (izquierda); el plan, si cuadra y la tabla de cuotas (derecha).
        _htmlEdPaso2: function (ed) {
            var seg = function (campo, opciones, cls) {
                return '<div class="adt_f360__seg is-block' + (cls || '') + '">' + opciones.map(function (o) {
                    return '<button type="button" class="' + (String(ed[campo]) === o[0] ? 'is-active' : '') + '" data-ed-gen="' + campo + '" data-valor="' + o[0] + '">' + o[1] + '</button>';
                }).join('') + '</div>';
            };
            var izq = '<h4 class="adt_f360__wiz-q">¿Cómo armamos el cronograma?</h4>' +
                '<div class="adt_f360__seg is-block adt_f360__wiz-modo" role="radiogroup">' + [['iguales', 'fa-th-list', 'Cuotas iguales'], ['editar', 'fa-pencil', 'Editar las actuales']].map(function (o) {
                    return '<button type="button" role="radio" aria-checked="' + (ed.modo === o[0]) + '"' + (ed.modo === o[0] ? ' class="is-active"' : '') +
                        ' data-ed-modo="' + o[0] + '"><i class="fa ' + o[1] + '" aria-hidden="true"></i> ' + o[2] + '</button>';
                }).join('') + '</div>';
            if (ed.modo === 'iguales') {
                izq += '<div class="adt_f360__wiz-field"><label>Calcular por</label>' + seg('gen_por', [['n', 'Cantidad de cuotas'], ['monto', 'Monto de cuota']]) + '</div>' +
                    (ed.gen_por === 'monto'
                        ? '<div class="adt_f360__wiz-field"><label>Monto de cada cuota</label><input type="number" step="0.01" min="0.01" class="adt_f360__input is-num is-big" data-ed="gen_monto" value="' + r2(ed.gen_monto).toFixed(2) + '"/></div>'
                        : '<div class="adt_f360__wiz-field"><label>Cantidad de cuotas</label><input type="number" min="1" max="400" class="adt_f360__input is-num is-big" data-ed="gen_n" value="' + ed.gen_n + '"/></div>') +
                    '<div class="adt_f360__wiz-field"><label>Primera cuota vence el</label><input type="date" class="adt_f360__input" data-ed="gen_desde" value="' + esc(ed.gen_desde) + '"/></div>' +
                    '<div class="adt_f360__wiz-field"><label>Cada</label>' + seg('gen_periodo', PERIODOS) + '</div>' +
                    (ed.gen_por === 'monto' ? '<div class="adt_f360__wiz-field"><label>Lo que sobra</label>' +
                        seg('gen_resto', [['aparte', 'Última menor'], ['ultima', 'A la última'], ['primera', 'A la primera']]) + '</div>' : '');
            }
            if (ed.modo) {
                izq += '<div class="adt_f360__wiz-acciones">' +
                    (ed.modo === 'iguales' ? '<button type="button" class="adt_f360__btn is-small is-ghost" data-ed-accion="generar" title="Descarta los cambios hechos a mano en la tabla">' +
                        '<i class="fa fa-refresh" aria-hidden="true"></i><span>Volver a generar</span></button>' : '') +
                    '<button type="button" class="adt_f360__btn is-small is-ghost" data-ed-accion="agregar"><i class="fa fa-plus" aria-hidden="true"></i><span>Agregar cuota</span></button>' +
                    '<button type="button" class="adt_f360__btn is-small is-ghost" data-ed-accion="repartir" title="Ajusta las cuotas con candado abierto para que el total cuadre">' +
                        '<i class="fa fa-balance-scale" aria-hidden="true"></i><span>Repartir diferencia</span></button></div>';

            }
            var der = ed.modo
                ? '<div class="adt_f360__wiz-estado">' +
                    (ed.modo === 'iguales' ? '<div class="adt_f360__wiz-plan"><i class="fa fa-calculator" aria-hidden="true"></i><span data-ed-v="plan"></span></div>' : '') +
                    '<div class="adt_f360__wiz-bar" data-ed-barra></div></div>' +
                    '<div class="adt_f360__wiz-dif d-none" data-ed-dif><label for="f360_ed_dif" data-ed-dif-t></label>' +
                        '<textarea id="f360_ed_dif" class="adt_f360__input" rows="2" data-ed="dif_motivo" placeholder="Ej.: se condona parte de la deuda; se agregan gastos de cobranza.">' +
                        esc(ed.dif_motivo) + '</textarea><small>O usa «Repartir diferencia» a la izquierda para que cuadre.</small></div>' +
                  '<div class="adt_f360__edtable-wrap"><table class="adt_f360__dtable adt_f360__edtable"><thead><tr>' +
                    '<th>Cuota</th><th>Vence</th><th class="is-num">Monto</th><th></th></tr></thead><tbody data-ed-filas>' + this._htmlEditorFilas(ed) + '</tbody></table></div>'
                : '<p class="adt_f360__wiz-empty">Elige a la izquierda cómo armar el nuevo cronograma.</p>';
            return {izq: izq, der: der};
        },
        _htmlEditorFilas: function (ed) {
            if (!ed.filas.length) {
                return '<tr><td colspan="4" class="adt_f360__muted adt_f360__pad">Sin cuotas. Genera cuotas o agrega una.</td></tr>';
            }
            return ed.filas.map(function (f, i) {
                return '<tr class="' + (f.vencida ? 'is-vencida' : '') + (f.id ? '' : ' is-nueva') + '">' +
                    '<td><input type="text" class="adt_f360__input" data-ed="nombre" data-i="' + i + '" value="' + esc(f.nombre) + '" aria-label="Nombre"/>' +
                        (f.pagado ? '<small class="adt_f360__muted">ya pagó ' + esc(money(f.pagado)) + '</small>' : '') + '</td>' +
                    '<td><input type="date" class="adt_f360__input" data-ed="fecha" data-i="' + i + '" value="' + esc(f.fecha) + '" aria-label="Vence"/></td>' +
                    '<td class="is-num"><div class="adt_f360__edmonto"><input type="number" step="0.01" min="0" class="adt_f360__input is-num is-big" data-ed="saldo" data-i="' + i + '" value="' + r2(f.saldo).toFixed(2) + '" aria-label="Monto"/>' +
                        '<button type="button" class="adt_f360__icon-btn is-small' + (f.fija ? ' is-on' : '') + '" data-ed-accion="fijar" data-i="' + i + '" title="' +
                        (f.fija ? 'Monto fijo: «Repartir» no lo cambia' : 'Monto libre: «Repartir» puede ajustarlo') + '"><i class="fa ' + (f.fija ? 'fa-lock' : 'fa-unlock-alt') + '" aria-hidden="true"></i></button></div></td>' +
                    '<td>' + (f.pagado ? '' : '<button type="button" class="adt_f360__icon-btn is-small is-danger" data-ed-accion="quitar" data-i="' + i + '" title="Quitar">' +
                        '<i class="fa fa-trash-o" aria-hidden="true"></i></button>') + '</td></tr>';
            }).join('');
        },

        // Paso 3: lo que pasa con la mora y el motivo (izquierda); antes → después y el detalle (derecha).
        _htmlEdPaso3: function (ed) {
            var d = ed.d, mon = d.moneda;
            var tarjeta = function (titulo, n, total, desde, hasta, cls) {
                return '<div class="adt_f360__wiz-card ' + cls + '"><span>' + titulo + '</span><b>' + esc(money(total, mon)) + '</b>' +
                    '<small>' + n + ' cuotas' + (desde ? ' · ' + esc(fechaTxt(desde)) + ' – ' + esc(fechaTxt(hasta)) : '') + '</small></div>';
            };
            var nuevas = _.sortBy(ed.filas, 'fecha');
            var MORA = {incluir: 'se suma al cronograma', perdonar: 'se perdona', cargo: 'se cobra aparte el ' + fechaTxt(ed.mora_fecha), mantener: 'se deja como está'};
            var perdon = (ed.mora_accion === 'incluir' || ed.mora_accion === 'cargo') ? r2(d.mora - this._editorMora(ed)) : (ed.mora_accion === 'perdonar' ? d.mora : 0);
            var izq = '<ul class="adt_f360__wiz-facts">' +
                    (d.mora > 0 ? '<li><i class="fa fa-exclamation-circle" aria-hidden="true"></i><span>Mora de ' + esc(money(d.mora, mon)) + ': ' + esc(MORA[ed.mora_accion]) +
                        (perdon > 0.004 ? ' · se perdonan <b>' + esc(money(perdon, mon)) + '</b>' : '') + '</span></li>' : '') +
                    (Number(ed.adicional) ? '<li><i class="fa fa-plus-circle" aria-hidden="true"></i><span>Monto adicional: ' + esc(money(ed.adicional, mon)) + '</span></li>' : '') +
                    (Math.abs(this._editorDif(ed)) >= 0.005 ? '<li class="is-dif"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i><span>El cronograma suma <b>' +
                        esc(money(Math.abs(this._editorDif(ed)), mon)) + (this._editorDif(ed) > 0 ? ' más' : ' menos') + '</b> que lo refinanciado: «' + esc(ed.dif_motivo) + '»</span></li>' : '') +
                    '<li><i class="fa fa-list-ol" aria-hidden="true"></i><span>' + nuevas.length + ' cuotas nuevas</span></li>' +
                '</ul>' +
                '<div class="adt_f360__wiz-field"><label for="f360_ed_motivo">Motivo del refinanciamiento <span class="adt_f360__req">*</span></label>' +
                    '<textarea id="f360_ed_motivo" class="adt_f360__input" rows="4" data-ed="motivo" placeholder="Ej.: acuerdo con el cliente por atraso; la cuota 10 se paga con la gratificación.">' + esc(ed.motivo) + '</textarea></div>';
            var der = '<div class="adt_f360__wiz-compare">' +
                    tarjeta('Antes', d.filas.length, d.deuda, d.filas.length && d.filas[0].fecha, d.filas.length && _.last(d.filas).fecha, '') +
                    '<i class="fa fa-long-arrow-right" aria-hidden="true"></i>' +
                    tarjeta('Después', nuevas.length, this._editorSuma(ed), nuevas.length && nuevas[0].fecha, nuevas.length && _.last(nuevas).fecha, 'is-new') +
                '</div>' +
                '<div class="adt_f360__ajprev" data-ed-prev>' + (ed.prev ? this._htmlVistaPrevia(ed.prev) : '<p class="adt_f360__muted">Calculando los cambios…</p>') + '</div>';
            return {izq: izq, der: der};
        },

        // Cifras vivas de cada paso y estado de los botones (sin redibujar: no se pierde el foco).
        _editorTotales: function () {
            var m = this._modal;
            if (!m || m.tipo !== 'editor') { return; }
            var ed = m.ed, $m = this._ref('modal'), mon = ed.d.moneda;
            var objetivo = this._editorObjetivo(ed), suma = this._editorSuma(ed), dif = r2(objetivo - suma);
            var moraTxt = {incluir: money(this._editorMora(ed), mon), perdonar: 'Se perdona', cargo: 'Aparte', mantener: 'Sin cambios'}[ed.mora_accion];
            $m.find('[data-ed-v="mora"]').text(moraTxt).toggleClass('is-muted', ed.mora_accion !== 'incluir');
            $m.find('[data-ed-v="adicional"]').text(money(Number(ed.adicional) || 0, mon)).toggleClass('is-muted', !Number(ed.adicional));
            $m.find('[data-ed-v="objetivo"]').text(money(objetivo, mon));
            if (ed.paso === 2 && ed.modo === 'iguales') {
                $m.find('[data-ed-v="plan"]').html(this._textoPlan(this._planIguales(ed), mon));
            }
            var perdon = r2(ed.d.mora - this._editorMora(ed));
            $m.find('[data-ed-perdon]').text(perdon > 0.004 ? 'Se perdonan ' + money(perdon, mon) : '');
            var cuadra = Math.abs(dif) < 0.005, mas = dif < 0;  // dif = objetivo − suma
            var explicada = !cuadra && !!ed.dif_motivo.trim();
            $m.find('[data-ed-barra]').toggleClass('is-ok', cuadra).toggleClass('is-bad', !cuadra && !explicada).toggleClass('is-warn', explicada).html(
                '<span>Suma <b>' + esc(money(suma, mon)) + '</b> · ' + ed.filas.length + ' cuotas</span>' +
                (cuadra ? '<span class="adt_f360__wiz-ok"><i class="fa fa-check-circle" aria-hidden="true"></i>Cuadra</span>'
                    : '<span class="adt_f360__wiz-bad">' + esc(money(Math.abs(dif), mon)) + (mas ? ' más' : ' menos') + ' que lo refinanciado' +
                      (explicada ? ' · explicado' : '') + '</span>'));
            $m.find('[data-ed-dif]').toggleClass('d-none', cuadra);
            $m.find('[data-ed-dif-t]').html('El nuevo cronograma suma <b>' + esc(money(Math.abs(dif), mon)) + (mas ? ' más' : ' menos') +
                '</b> que lo refinanciado. ¿Por qué? <span class="adt_f360__req">*</span>');
            $m.find('[data-ed-accion="repartir"]').prop('disabled', cuadra);
            $m.find('[data-ed-siguiente]').prop('disabled', ed.paso === 2 && !this._editorCuadra(ed));
            // Siempre un booleano: .prop('disabled', undefined) no cambia nada y el botón quedaba desactivado.
            $m.find('[data-ed-aplicar]').prop('disabled', !ed.motivo.trim() || !ed.prev || !!ed.prev.error || !!m.guardando);
        },

        // Montos del cronograma de cuotas iguales: por cantidad (los centavos van a la última)
        // o por monto de cuota (lo que sobra queda aparte, se suma a la última o a la primera).
        _planIguales: function (ed) {
            var conPagos = ed.filas.filter(function (f) { return f.pagado > 0; });
            var total = r2(this._editorObjetivo(ed) - this._editorSuma({filas: conPagos}));
            if (total <= 0) { return []; }
            if (ed.gen_por === 'monto') {
                var m = r2(ed.gen_monto);
                if (m <= 0) { return null; }
                var k = Math.floor(total / m + 1e-9), resto = r2(total - k * m);
                if (k > 400) { return null; }
                var montos = _.range(k).map(function () { return m; });
                if (resto >= 0.005) {
                    if (ed.gen_resto === 'aparte' || !k) { montos.push(resto); }
                    else if (ed.gen_resto === 'ultima') { montos[k - 1] = r2(m + resto); }
                    else { montos[0] = r2(m + resto); }
                }
                return montos;
            }
            var n = Math.max(parseInt(ed.gen_n, 10) || 0, 0);
            if (!n) { return null; }
            var base = Math.floor(total / n * 100) / 100;
            return _.range(n).map(function (i) { return i === n - 1 ? r2(total - base * (n - 1)) : base; });
        },
        _textoPlan: function (montos, mon) {
            if (!montos) { return 'Completa los datos para calcular.'; }
            if (!montos.length) { return 'No hay saldo por refinanciar.'; }
            var grupos = [];
            montos.forEach(function (x) {
                var g = _.last(grupos);
                if (g && g[1] === x) { g[0] += 1; } else { grupos.push([1, x]); }
            });
            return grupos.map(function (g) { return '<b>' + g[0] + '</b> × ' + esc(money(g[1], mon)); }).join(' + ') +
                ' <span class="adt_f360__muted">· ' + montos.length + ' cuotas</span>';
        },
        _generarIguales: function (ed) {
            var montos = this._planIguales(ed);
            if (!montos || !ed.gen_desde) { return this._modalError('Indica la cantidad o el monto de cuota y la fecha de inicio.'); }
            // Las cuotas con pagos se quedan (no se pueden quitar); el resto se reemplaza.
            var conPagos = ed.filas.filter(function (f) { return f.pagado > 0; });
            ed.filas = conPagos.concat(montos.map(function (x, k) {
                return {id: false, nombre: 'Cuota R-' + (k + 1), fecha: sumarPeriodo(ed.gen_desde, ed.gen_periodo, k),
                        saldo: x, pagado: 0, tipo: '', fija: false};
            }));
        },
        _onEditorGen: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'editor') { return; }
            var ed = m.ed, campo = ev.currentTarget.getAttribute('data-ed-gen');
            ed[campo] = ev.currentTarget.getAttribute('data-valor');
            if (campo === 'gen_por' && ed.gen_por === 'monto' && !(ed.gen_monto > 0)) {
                ed.gen_monto = r2(this._editorObjetivo(ed) / Math.max(parseInt(ed.gen_n, 10) || 1, 1));
            }
            this._modalError('');
            this._generarIguales(ed);
            this._renderEditor();
        },
        _irPasoEditor: function (paso) {
            var self = this, m = this._modal, ed = m.ed;
            if (paso === 3 && !this._editorCuadra(ed)) {
                return this._modalError('El cronograma no suma lo refinanciado: explica el motivo de la diferencia o usa «Repartir diferencia».');
            }
            this._modalError('');
            ed.paso = paso;
            if (paso === 2 && !ed.modo) {
                ed.modo = 'iguales';
                this._generarIguales(ed);
            }
            if (paso === 3) {
                ed.prev = null;
                this._llamar('aplicar_editor', {vehicle_id: this._drawerId, cuenta_id: ed.d.cuenta_id, datos: this._datosEditor(ed), simular: true}).then(function (res) {
                    if (self._modal !== m || ed.paso !== 3) { return; }
                    ed.prev = res;
                    self._ref('modal').find('[data-ed-prev]').html(self._htmlVistaPrevia(res));
                    self._editorTotales();
                }).catch(function (err) {
                    if (err && err.event) { err.event.preventDefault(); }
                    ed.prev = {error: self._error(err)};
                    self._ref('modal').find('[data-ed-prev]').html(self._htmlVistaPrevia(ed.prev));
                });
            }
            this._renderEditor();
        },
        _datosEditor: function (ed) {
            return {
                filas: ed.filas.map(function (f) { return {id: f.id || false, nombre: f.nombre, fecha: f.fecha, saldo: r2(f.saldo)}; }),
                adicional: r2(ed.adicional), mora_accion: ed.mora_accion, mora_acordada: r2(ed.mora_acordada),
                mora_fecha: ed.mora_fecha, motivo: ed.motivo,
                diferencia_motivo: Math.abs(this._editorDif(ed)) >= 0.005 ? ed.dif_motivo : '',
            };
        },
        _onEditorPaso: function (ev) {
            if (this._modal && this._modal.tipo === 'editor') {
                this._irPasoEditor(parseInt(ev.currentTarget.getAttribute('data-ed-paso'), 10));
            }
        },
        _onEditorModo: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'editor') { return; }
            var ed = m.ed;
            ed.modo = ev.currentTarget.getAttribute('data-ed-modo');
            ed.filas = ed.modo === 'editar' ? ed.d.filas.map(function (f) { return _.extend({}, f, {fija: false}); }) : ed.filas;
            if (ed.modo === 'iguales') { this._generarIguales(ed); }
            this._renderEditor();
        },
        _onEditorCampo: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'editor') { return; }
            var el = ev.currentTarget, campo = el.getAttribute('data-ed'), i = el.getAttribute('data-i'), ed = m.ed;
            if (i !== null) {
                var f = ed.filas[parseInt(i, 10)];
                f[campo] = campo === 'saldo' ? (parseFloat(el.value) || 0) : el.value;
                if (campo === 'saldo' && !f.fija) {
                    f.fija = true;
                    $(el).siblings('[data-ed-accion="fijar"]').addClass('is-on').find('i').removeClass('fa-unlock-alt').addClass('fa-lock');
                }
            } else {
                ed[campo] = el.value;
            }
            // Cuotas iguales: al confirmar la cantidad o la fecha, la tabla se vuelve a generar.
            if (ev.type === 'change' && (campo === 'gen_n' || campo === 'gen_monto' || campo === 'gen_desde') && ed.modo === 'iguales') {
                this._generarIguales(ed);
                this._ref('modal').find('[data-ed-filas]').html(this._htmlEditorFilas(ed));
            }
            this._editorTotales();
        },
        _onEditorMora: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'editor') { return; }
            m.ed.mora_accion = ev.currentTarget.getAttribute('data-ed-mora');
            this._renderEditor();
        },
        _onEditorAccion: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'editor') { return; }
            var ed = m.ed, accion = ev.currentTarget.getAttribute('data-ed-accion'), i = parseInt(ev.currentTarget.getAttribute('data-i'), 10);
            this._modalError('');
            if (accion === 'fijar') {
                ed.filas[i].fija = !ed.filas[i].fija;
            } else if (accion === 'quitar') {
                ed.filas.splice(i, 1);
            } else if (accion === 'agregar') {
                var ultima = _.last(ed.filas);
                ed.filas.push({id: false, nombre: 'Cuota adicional', fecha: ultima && ultima.fecha ? sumarPeriodo(ultima.fecha, ed.gen_periodo, 1) : ed.d.hoy,
                               saldo: 0, pagado: 0, tipo: '', fija: false});
            } else if (accion === 'generar') {
                this._generarIguales(ed);
            } else if (accion === 'repartir') {
                var libres = ed.filas.filter(function (f) { return !f.fija; });
                if (!libres.length) { return this._modalError('Todas las cuotas tienen el monto fijo: desbloquea alguna para repartir.'); }
                var dif = r2(this._editorObjetivo(ed) - this._editorSuma(ed));
                var parte = Math.trunc(dif / libres.length * 100) / 100;
                libres.forEach(function (f, k) {
                    f.saldo = r2(f.saldo + (k === libres.length - 1 ? dif - parte * (libres.length - 1) : parte));
                });
                if (libres.some(function (f) { return f.saldo < 0; })) {
                    libres.forEach(function (f) { f.saldo = Math.max(f.saldo, 0); });
                    this._modalError('No alcanza sin dejar montos negativos: revisa las cuotas fijas.');
                }
            }
            this._ref('modal').find('[data-ed-filas]').html(this._htmlEditorFilas(ed));
            this._editorTotales();
            if (accion === 'agregar') {
                // La fila nueva se ve y queda lista para escribir el monto: si no, no se nota que se agregó.
                var $fila = this._ref('modal').find('[data-ed-filas] tr').last();
                $fila.addClass('is-recien')[0].scrollIntoView({behavior: 'smooth', block: 'center'});
                $fila.find('[data-ed="saldo"]').trigger('focus').trigger('select');
                setTimeout(function () { $fila.removeClass('is-recien'); }, 1600);
            }
        },
        // Confirmación como la del pago: check animado, el nuevo total y lo que cambió.
        _mostrarRefinOk: function (res, mon) {
            var r = res.resumen || {}, cuotas = (r.cronograma && r.cronograma.despues) || [];
            var total = cuotas.reduce(function (t, q) { return t + q.saldo; }, 0);
            var notas = [];
            if (r.mora_perdonada) {
                notas.push(['', 'fa-gift', 'Se perdonaron <b>' + esc(money(r.mora_perdonada, mon)) + '</b> de mora.']);
            }
            if (r.diferencia) {
                notas.push(['is-warn', 'fa-exclamation-triangle', 'El cronograma suma <b>' + esc(money(Math.abs(r.diferencia), mon)) +
                    (r.diferencia > 0 ? ' más' : ' menos') + '</b> que lo refinanciado: «' + esc(r.diferencia_motivo) + '».']);
            }
            var html = '<div class="adt_f360__paid" role="status">' +
                '<svg class="adt_f360__paid-check" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l7.5 7.5L37.5 19"/></svg>' +
                '<h2 id="adt_f360_modal_t">Refinanciamiento aplicado</h2>' +
                '<p class="adt_f360__paid-amount">' + esc(money(total, mon)) + '</p>' +
                '<p class="adt_f360__paid-meta">' + cuotas.length + ' cuotas' +
                    (cuotas.length ? ' · ' + esc(fechaTxt(cuotas[0].fecha)) + ' – ' + esc(fechaTxt(_.last(cuotas).fecha)) : '') +
                    (res.nombre ? ' · ' + esc(res.nombre) : '') + '</p>' +
                notas.map(function (n) {
                    return '<p class="adt_f360__paid-note ' + n[0] + '"><i class="fa ' + n[1] + '" aria-hidden="true"></i><span>' + n[2] + '</span></p>';
                }).join('') +
                '<p class="adt_f360__paid-hint">Queda en el historial de ajustes; se puede deshacer desde ahí.</p>' +
                '</div><footer class="adt_f360__modal-foot is-center">' +
                '<button type="button" class="adt_f360__btn is-primary" data-modal-close><i class="fa fa-list-ol" aria-hidden="true"></i><span>Ver el cronograma</span></button></footer>';
            this._modal = {tipo: 'refin_ok'};
            var $m = this._ref('modal').find('.adt_f360__modal').removeClass('is-split is-editor is-wide').addClass('is-paid').html(html);
            $m.find('.adt_f360__modal-foot .is-primary').trigger('focus');
        },
        _onEditorAplicar: function () {
            var self = this, m = this._modal;
            if (!m || m.tipo !== 'editor' || m.guardando) { return; }
            if (!m.ed.motivo.trim()) { return this._modalError('Escribe el motivo del refinanciamiento.'); }
            m.guardando = true;
            this._ref('modal').find('[data-ed-aplicar]').prop('disabled', true).addClass('is-loading');
            this._modalError('');
            return this._llamar('aplicar_editor', {vehicle_id: this._drawerId, cuenta_id: m.ed.d.cuenta_id, datos: this._datosEditor(m.ed)}).then(function (res) {
                m.guardando = false;
                self._mostrarRefinOk(res, m.ed.d.moneda);
                return self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                m.guardando = false;
                if (self._modal !== m) { return; }
                self._modalError(self._error(err));
                self._editorTotales();
            });
        },
    });
});
