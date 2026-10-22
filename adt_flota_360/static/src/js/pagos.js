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
                self._ref('modal').find('.adt_f360__modal-head').after('<div class="adt_f360__pay-summary" data-pago-resumen aria-live="polite"></div>');
                self._ref('modal').find('.adt_f360__modal-body').prepend('<p class="adt_f360__pay-help">' + esc(m.spec.pago_ayuda) + '</p>');
                self._ref('modal').find('[data-guardar] span').text('Registrar pago');
                m.pagoCalculo = m.spec.pago_resumen;
                self._renderPagoResumen();
            });
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
        _renderPagoResumen: function () {
            var m = this._modal;
            if (!m || !m.spec || m.spec.clave !== 'pago' || !m.pagoCalculo) { return; }
            var c = m.pagoCalculo, v = m.valores, tipo = m.params.tipo;
            var mora = tipo === 'cuota' ? Number(v.mora || 0) : c.mora_auto;
            var amount = tipo === 'cascada' ? (v.cancelar_todo ? c.total : Number(v.monto || 0)) : Number(v.amount || 0);
            var receive = amount + (tipo === 'cuota' && v.mora_state === 'paid' ? mora : 0);
            var items = [
                ['Capital pendiente', money(c.capital, c.moneda)],
                [tipo === 'cuota' ? 'Mora a la fecha' + (c.mora_dias ? ' · ' + c.mora_dias + ' días' : '') : 'Mora pendiente', money(mora, c.moneda)],
                ['Importe a recibir', money(receive, c.moneda)]
            ];
            this._ref('modal').find('[data-pago-resumen]').html(items.map(function (item) { return '<div><span>' + esc(item[0]) + '</span><strong>' + esc(item[1]) + '</strong></div>'; }).join(''));
        },
        _simularPago: function () {
            var self = this, m = this._modal;
            if (!m || !m.spec || m.spec.clave !== 'pago' || m.guardando || !m.valores.payment_date) { return; }
            var date = m.valores.payment_date, seq = (m.pagoSeq || 0) + 1;
            m.pagoSeq = seq;
            return this._llamar('simular_pago', {vehicle_id: this._drawerId, params: m.params, payment_date: date}).then(function (data) {
                if (self._modal !== m || m.guardando || m.pagoSeq !== seq || m.valores.payment_date !== date) { return; }
                m.pagoCalculo = data;
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
            m.guardando = true;
            this._modalError('');
            this._ref('modal').find('input, select, [data-guardar], [data-seg-campo]').prop('disabled', true);
            this._ref('modal').find('[data-guardar]').addClass('is-loading').find('span').text('Registrando pago…');
            return this._llamar('guardar', {clave: 'pago', vehicle_id: this._drawerId, params: m.params, valores: _.clone(m.valores)}).then(function (res) {
                m.guardando = false;
                self._cerrarModal(true);
                self.displayNotification({type: 'success', title: 'Pago registrado', message: res.mensaje});
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
        _cerrarModal: function () {
            if (this._modal && this._modal.spec && this._modal.spec.clave === 'pago' && this._modal.guardando) { return; }
            return this._super.apply(this, arguments);
        }
    });
});
