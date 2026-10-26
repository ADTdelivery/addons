odoo.define('adt_flota_360.Pagos', function (require) {
    'use strict';
    var Flota360 = require('adt_flota_360.Flota360');
    var esc = _.escape;
    var TYPES = {
        'adt.register.payment': ['cuota', 'default_cuota_id'],
        'adt.pagar.mora.wizard': ['mora', 'default_cuota_id'],
        'adt.cancelar.credito.wizard': ['cascada', 'default_cuenta_id']
    };
    function money(amount, currency) { return (currency || 'PEN') + ' ' + Number(amount || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    Flota360.include({
        events: _.extend({}, Flota360.prototype.events, {
            'click [data-pago-resto]': '_onPagarResto',
            'change [data-pago-cuota]': '_onCuotaPago',
            'click [data-pago-cuotas-sel]': '_onCuotasPagoSel',
        }),
        init: function () {
            this._super.apply(this, arguments);
            this._simularPagoDiferido = _.debounce(this._simularPago.bind(this), 250);
        },
        destroy: function () {
            this._simularPagoDiferido.cancel();
            return this._super.apply(this, arguments);
        },
        do_action: function (action) {
            var type = action && TYPES[action.res_model], context = action && action.context;
            if (type && this._drawerId && context && context[type[1]]) {
                return this._abrirForm('pago', false, {
                    tipo: type[0], id: context[type[1]],
                    monto: context.default_amount || false,
                    operacion: context.default_communication || ''
                });
            }
            return this._super.apply(this, arguments);
        },
        _abrirForm: function (clave) {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                var m = self._modal;
                if (clave !== 'pago' || !m || !m.spec || m.spec.clave !== 'pago') { return; }
                // Recibo en la columna derecha: siempre a la vista lo que se va a cobrar.
                self._ref('modal').find('.adt_f360__modal').addClass('is-pago is-split');
                self._ref('modal').find('.adt_f360__modal-foot').before('<aside class="adt_f360__modal-side">' +
                    '<div class="adt_f360__label">Recibo</div><div class="adt_f360__receipt" data-pago-resumen aria-live="polite"></div></aside>');
                self._ref('modal').find('.adt_f360__modal-body').prepend('<p class="adt_f360__pay-help">' + esc(m.spec.pago_ayuda) + '</p>');
                self._ref('modal').find('[data-guardar] span').text('Registrar pago');
                m.pagoCalculo = m.spec.pago_resumen;
                if (m.params.tipo === 'cascada') {
                    // Lista de cuotas para «Elegir cuotas», en la columna derecha sobre el recibo.
                    self._ref('modal').find('.adt_f360__modal-side').prepend('<section class="adt_f360__paysel d-none" data-pago-cuotas></section>');
                    self._renderCuotasPago();
                }
                self._renderPagoResumen();
            });
        },
        _renderCuotasPago: function () {
            var m = this._modal, c = m.pagoCalculo, cur = c.moneda;
            var detalle = c.detalle || [];
            var ids = _.intersection(m.valores.cuota_ids || [], _.pluck(detalle, 'id'));
            m.valores.cuota_ids = ids;
            m.cuotasFecha = m.valores.payment_date;
            var $sec = this._ref('modal').find('[data-pago-cuotas]');
            var scroll = $sec.find('.adt_f360__paysel-list').scrollTop() || 0;
            $sec.html('<div class="adt_f360__paysel-tools"><span class="adt_f360__label" data-pago-cuotas-n></span>' +
                    '<button type="button" class="adt_f360__btn is-small is-ghost" data-pago-cuotas-sel="vencidas">Las vencidas</button>' +
                    '<button type="button" class="adt_f360__btn is-small is-ghost" data-pago-cuotas-sel="todas">Todas</button>' +
                    '<button type="button" class="adt_f360__btn is-small is-ghost" data-pago-cuotas-sel="ninguna">Ninguna</button></div>' +
                (detalle.length ? '<div class="adt_f360__paysel-list" role="group" aria-label="Cuotas a pagar">' + detalle.map(function (q) {
                    var on = _.contains(ids, q.id);
                    return '<label class="adt_f360__paysel-item' + (on ? ' is-on' : '') + (q.vencida ? ' is-vencida' : '') + '">' +
                        '<input type="checkbox" data-pago-cuota="' + q.id + '"' + (on ? ' checked="checked"' : '') + '/>' +
                        '<span class="adt_f360__paysel-name"><b>' + esc(q.nombre) + '</b>' + (q.tipo ? ' <small>' + esc(q.tipo) + '</small>' : '') + '</span>' +
                        '<span class="adt_f360__paysel-date">' + (q.fecha ? q.fecha.split('-').reverse().join('/') : '—') + '</span>' +
                        '<span class="adt_f360__paysel-amt">' + esc(money(q.saldo, cur)) +
                            (q.mora ? '<small>+ mora ' + esc(money(q.mora, cur)) + '</small>' : '') + '</span></label>';
                }).join('') + '</div>' : '<p class="adt_f360__muted">No hay cuotas con saldo pendiente.</p>'));
            $sec.find('.adt_f360__paysel-list').scrollTop(scroll);
            this._contarCuotasPago();
        },
        _contarCuotasPago: function () {
            var m = this._modal, n = (m.valores.cuota_ids || []).length;
            this._ref('modal').find('[data-pago-cuotas-n]').text(n ? n + (n === 1 ? ' cuota elegida' : ' cuotas elegidas') : 'Cuotas a pagar');
        },
        _onCuotaPago: function (ev) {
            var m = this._modal, id = parseInt(ev.currentTarget.getAttribute('data-pago-cuota'), 10);
            if (!m || !m.spec || m.spec.clave !== 'pago') { return; }
            m.valores.cuota_ids = ev.currentTarget.checked ? _.union(m.valores.cuota_ids || [], [id]) : _.without(m.valores.cuota_ids || [], id);
            m.sucio = true;
            $(ev.currentTarget).closest('.adt_f360__paysel-item').toggleClass('is-on', ev.currentTarget.checked);
            this._modalError('');
            this._contarCuotasPago();
            this._renderPagoResumen();
        },
        _onCuotasPagoSel: function (ev) {
            var m = this._modal, modo = ev.currentTarget.getAttribute('data-pago-cuotas-sel');
            var detalle = m.pagoCalculo.detalle || [];
            m.valores.cuota_ids = _.pluck(modo === 'ninguna' ? [] : (modo === 'vencidas' ? _.where(detalle, {vencida: true}) : detalle), 'id');
            m.sucio = true;
            this._modalError('');
            this._renderCuotasPago();
            this._renderPagoResumen();
        },
        _actualizarForm: function () {
            this._super.apply(this, arguments);
            var m = this._modal;
            if (m && m.spec && m.spec.clave === 'pago') {
                this._renderPagoResumen();
                this._simularPagoDiferido();
            }
        },
        _onCampo: function (ev) {
            this._super.apply(this, arguments);
            var m = this._modal, name = ev.currentTarget.getAttribute('data-campo');
            if (!m || !m.spec || m.spec.clave !== 'pago') { return; }
            if (name === 'mora') {
                m.valores.mora_manual = true;
                this._ref('modal').find('[data-campo="mora_manual"]').prop('checked', true);
            }
            if (name === 'mora_manual' && !m.valores.mora_manual && m.pagoCalculo) {
                m.valores.mora = m.pagoCalculo.mora_auto;
                this._ref('modal').find('[data-campo="mora"]').val(m.valores.mora);
            }
            this._renderPagoResumen();
        },
        // Recibo: cada concepto en una línea y el total al final. La mora pendiente se muestra
        // tachada y fuera del total, para que el cambio pagada/pendiente se note de inmediato.
        _renderPagoResumen: function () {
            var m = this._modal;
            if (!m || !m.spec || m.spec.clave !== 'pago' || !m.pagoCalculo) { return; }
            var c = m.pagoCalculo, v = m.valores, tipo = m.params.tipo, cur = c.moneda;
            var linea = function (etiqueta, monto, extra, cls) {
                return '<div class="adt_f360__receipt-line' + (cls ? ' ' + cls : '') + '"><span>' + etiqueta + '</span>' +
                    (extra || '') + '<strong>' + esc(money(monto, cur)) + '</strong></div>';
            };
            var lineas = [], notas = [], total, saldo;
            if (tipo === 'cuota') {
                var amount = Number(v.amount || 0), mora = Number(v.mora || 0), cobraMora = v.mora_state === 'paid';
                total = amount + (cobraMora ? mora : 0);
                saldo = Math.max(c.capital - amount, 0);
                lineas.push(linea('Abono a la cuota' + (saldo > 0.004 ? ' <small>de ' + esc(money(c.capital, cur)) + '</small>' : ''), amount));
                if (mora > 0) {
                    lineas.push(linea('Mora' + (c.mora_dias ? ' <small>' + c.mora_dias + ' días</small>' : ''), mora,
                        '<em class="adt_f360__receipt-tag ' + (cobraMora ? 'is-ok' : 'is-warn') + '">' + (cobraMora ? 'Se cobra ahora' : 'Queda pendiente') + '</em>',
                        cobraMora ? 'is-ok' : 'is-excluded'));
                    if (!cobraMora) { notas.push('La mora de ' + money(mora, cur) + ' queda registrada como pendiente y no se suma al total.'); }
                }
                if (saldo > 0.004) { notas.push('Abono parcial: el saldo de ' + money(saldo, cur) + ' pasa a una subcuota para cobrarlo después.'); }
            } else if (tipo === 'mora') {
                total = Number(v.amount || 0);
                saldo = Math.max(c.mora_auto - total, 0);
                lineas.push(linea('Mora pendiente', c.mora_auto));
                if (saldo > 0.004) { notas.push('Abono parcial: quedarán ' + money(saldo, cur) + ' de mora pendiente.'); }
            } else if (v.modo === 'elegir') {
                var elegidas = (c.detalle || []).filter(function (q) { return _.contains(v.cuota_ids || [], q.id); });
                var capital = elegidas.reduce(function (t, q) { return t + q.saldo; }, 0);
                var moraSel = elegidas.reduce(function (t, q) { return t + q.mora; }, 0);
                total = capital + (v.cobrar_mora ? moraSel : 0);
                lineas.push(linea('Cuotas elegidas <small>' + elegidas.length + '</small>', capital));
                if (moraSel > 0) {
                    lineas.push(linea('Mora de esas cuotas', moraSel,
                        '<em class="adt_f360__receipt-tag ' + (v.cobrar_mora ? 'is-ok' : 'is-warn') + '">' + (v.cobrar_mora ? 'Se cobra ahora' : 'Queda pendiente') + '</em>',
                        v.cobrar_mora ? 'is-ok' : 'is-excluded'));
                }
                if (elegidas.length) {
                    notas.push(elegidas.map(function (q) { return q.nombre; }).join(', ') + ' quedan pagadas por completo.');
                } else {
                    notas.push('Marca en la lista las cuotas que paga el cliente.');
                }
            } else {
                total = v.modo === 'todo' ? c.total : Number(v.monto || 0);
                saldo = Math.max(c.total - total, 0);
                lineas.push(linea('Capital pendiente' + (c.cuotas ? ' <small>' + c.cuotas + ' cuotas</small>' : ''), c.capital));
                lineas.push(linea('Mora pendiente', c.mora_auto));
                if (saldo > 0.004) { notas.push('Se aplica desde la cuota más antigua; quedarán ' + money(saldo, cur) + ' por pagar.'); }
            }
            if (tipo === 'cascada') {
                this._ref('modal').find('[data-pago-cuotas]').toggleClass('d-none', v.modo !== 'elegir');
            }
            var $r = this._ref('modal').find('[data-pago-resumen]');
            $r.html('<div class="adt_f360__receipt-lines">' + lineas.join('') + '</div>' +
                '<div class="adt_f360__receipt-total"><span>Total a recibir</span><strong data-pago-total>' + esc(money(total, cur)) + '</strong></div>' +
                (notas.length ? '<ul class="adt_f360__receipt-notes">' + notas.map(function (n) {
                    return '<li><i class="fa fa-info-circle" aria-hidden="true"></i>' + esc(n) + '</li>'; }).join('') + '</ul>' : ''));
            // Resalta el total cada vez que cambia.
            if (m.pagoTotal !== undefined && m.pagoTotal !== total) {
                var el = $r.find('[data-pago-total]')[0];
                el.classList.add('is-bump');
                el.addEventListener('animationend', function () { el.classList.remove('is-bump'); }, {once: true});
            }
            m.pagoTotal = total;
        },
        _simularPago: function () {
            var self = this, m = this._modal;
            if (!m || !m.spec || m.spec.clave !== 'pago' || m.guardando || !m.valores.payment_date) { return; }
            var date = m.valores.payment_date, seq = (m.pagoSeq || 0) + 1;
            m.pagoSeq = seq;
            return this._llamar('simular_pago', {vehicle_id: this._drawerId, params: m.params, payment_date: date}).then(function (data) {
                if (self._modal !== m || m.guardando || m.pagoSeq !== seq || m.valores.payment_date !== date) { return; }
                m.pagoCalculo = data;
                if (m.params.tipo === 'cascada' && m.cuotasFecha !== date) {
                    self._renderCuotasPago();
                }
                if (m.params.tipo === 'cuota' && !m.valores.mora_manual) {
                    m.valores.mora = data.mora_auto;
                    self._ref('modal').find('[data-campo="mora"]').val(data.mora_auto);
                }
                self._renderPagoResumen();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                if (self._modal === m && !m.guardando) { self._modalError(self._error(err)); }
            });
        },
        _onSubmitModal: function (ev) {
            var self = this, m = this._modal;
            if (!m || !m.spec || m.spec.clave !== 'pago') { return this._super.apply(this, arguments); }
            ev.preventDefault();
            if (m.guardando) { return; }
            var invalid = [];
            m.spec.secciones.forEach(function (sec) { sec.campos.forEach(function (c) { if (self._marcarCampo(c, true)) { invalid.push(c); } }); });
            if (invalid.length) {
                this._modalError('Revisa los campos marcados antes de registrar el pago.');
                this._ref('modal').find('[data-campo="' + invalid[0].name + '"]').trigger('focus');
                return;
            }
            if (m.params.tipo === 'cascada' && m.valores.modo === 'elegir' && !(m.valores.cuota_ids || []).length) {
                this._modalError('Marca al menos una cuota para pagar.');
                this._ref('modal').find('[data-pago-cuotas]')[0].scrollIntoView({behavior: 'smooth', block: 'start'});
                return;
            }
            m.guardando = true;
            this._modalError('');
            this._ref('modal').find('input, select, [data-guardar], [data-seg-campo]').prop('disabled', true);
            this._ref('modal').find('[data-guardar]').addClass('is-loading').find('span').text('Registrando pago…');
            return this._llamar('guardar', {clave: 'pago', vehicle_id: this._drawerId, params: m.params, valores: _.clone(m.valores)}).then(function (res) {
                m.guardando = false;
                // Si la ficha mostraba la cuota abonada en parte, pasa a la subcuota con el saldo.
                if (res.siguiente && res.siguiente.tipo === 'cuota' && self.cuotaSel === m.params.id) {
                    self.cuotaSel = res.siguiente.id;
                }
                self._mostrarPagoOk(res);
                return self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                m.guardando = false;
                if (self._modal !== m) { return; }
                self._ref('modal').find('input, select, [data-seg-campo]').prop('disabled', false);
                self._ref('modal').find('[data-guardar] span').text('Registrar pago');
                self._modalError(self._error(err));
            });
        },
        // Confirmación a pantalla del popup: check animado, importe cobrado y, si quedó saldo,
        // el acceso directo para pagar el resto.
        _mostrarPagoOk: function (res) {
            var resto = res.siguiente;
            var html = '<div class="adt_f360__paid" role="status">' +
                '<svg class="adt_f360__paid-check" viewBox="0 0 52 52" aria-hidden="true">' +
                    '<circle cx="26" cy="26" r="24"/><path d="M15 27l7.5 7.5L37.5 19"/></svg>' +
                '<h2 id="adt_f360_modal_t">Pago registrado</h2>' +
                '<p class="adt_f360__paid-amount">' + esc(money(res.total, res.moneda)) + '</p>' +
                '<p class="adt_f360__paid-meta">' + esc(res.concepto || '') + (res.operacion ? ' · Op. ' + esc(res.operacion) : '') + '</p>' +
                (res.restante > 0 ? '<p class="adt_f360__paid-note is-warn"><i class="fa fa-clock-o" aria-hidden="true"></i>Queda un saldo de <b>' +
                    esc(money(res.restante, res.moneda)) + '</b>' + (resto && resto.tipo === 'cuota' ? ' en ' + esc(resto.nombre) : '') + '.</p>' : '') +
                (res.mora_pendiente > 0 ? '<p class="adt_f360__paid-note"><i class="fa fa-info-circle" aria-hidden="true"></i>La mora de <b>' +
                    esc(money(res.mora_pendiente, res.moneda)) + '</b> quedó pendiente.</p>' : '') +
                '</div><footer class="adt_f360__modal-foot is-center">' +
                '<button type="button" class="adt_f360__btn' + (resto ? '' : ' is-primary') + '" data-modal-close>Cerrar</button>' +
                (resto ? '<button type="button" class="adt_f360__btn is-primary" data-pago-resto="' + resto.tipo + '" data-id="' + resto.id + '">' +
                    '<i class="fa fa-money" aria-hidden="true"></i><span>Pagar el resto</span></button>' : '') + '</footer>';
            this._modal = {tipo: 'pago_ok'};
            var $m = this._ref('modal').find('.adt_f360__modal').removeClass('is-pago is-split').addClass('is-paid').html(html);
            $m.find('.adt_f360__modal-foot .is-primary').trigger('focus');
        },
        _onPagarResto: function (ev) {
            var tipo = ev.currentTarget.getAttribute('data-pago-resto'), id = parseInt(ev.currentTarget.getAttribute('data-id'), 10);
            this._cerrarModal(true);
            return this._abrirForm('pago', false, {tipo: tipo, id: id});
        },
        // El pago es un formulario corto y precargado: cerrar no pide confirmar el descarte.
        _cerrarModal: function () {
            var m = this._modal;
            if (m && m.spec && m.spec.clave === 'pago') {
                if (m.guardando) { return; }
                m.sucio = false;
            }
            return this._super.apply(this, arguments);
        }
    });
});
