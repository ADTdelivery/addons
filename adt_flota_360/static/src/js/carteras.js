odoo.define('adt_flota_360.Carteras', function (require) {
    'use strict';
    var AbstractAction = require('web.AbstractAction');
    var Flota360 = require('adt_flota_360.Flota360');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var esc = _.escape;
    function money(n, currency) { return (currency || 'PEN') + ' ' + Number(n || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    function date(d) { return d ? d.split('-').reverse().join('/') : '—'; }
    function progress(paid, target) { var p = target ? Math.min(100, Math.round(paid / target * 100)) : 0; return '<div class="f360c-progress"><span style="width:' + p + '%"></span></div><small>' + p + '% recuperado</small>'; }
    function field(label, html) { return '<label class="f360c-field"><span>' + label + '</span>' + html + '</label>'; }
    var Cartera = AbstractAction.extend({
        hasControlPanel: false,
        className: 'f360c o_action',
        events: {
            'click [data-c="refresh"]': '_load',
            'click [data-c="new"]': '_new',
            'click [data-c="fleet"]': '_fleet',
            'input [data-c="search"]': '_renderData',
            'change [data-c="owner"], [data-c="status"]': '_renderData',
            'click [data-manage]': '_manage',
            'click [data-account]': '_account',
            'click [data-close]': '_close',
            'click [data-state]': '_filterStatus'
        },
        start: function () {
            var self = this;
            this.$el.addClass('adt_f360 f360c');
            this.$el.html('<div class="adt_f360__scroll f360c-shell"><header class="adt_f360__top">' +
                '<nav class="adt_f360__filters f360c-tabs" aria-label="Secciones de Flota 360"><button class="adt_f360__filter" data-c="fleet">Consulta 360</button><button class="adt_f360__filter is-active active">Carteras de cobranza</button></nav>' +
                '<div class="f360c-head"><div class="adt_f360__titlebar"><h1 class="adt_f360__title">Carteras de cobranza</h1><p class="adt_f360__subtitle">Gestiona tus cobros y sigue el avance de tus objetivos.</p></div><div class="f360c-actions"><button class="adt_f360__btn" data-c="refresh"><i class="fa fa-refresh" aria-hidden="true"/> Actualizar</button><button class="adt_f360__btn is-primary" data-c="new">＋ Asignar cartera</button></div></div>' +
                '<div class="f360c-toolbar"><div class="adt_f360__search"><i class="fa fa-search adt_f360__search-icon" aria-hidden="true"/><input class="adt_f360__search-input" data-c="search" type="search" placeholder="Cliente, N° de cuenta o cartera" aria-label="Buscar cuenta"/></div><select data-c="owner" aria-label="Responsable"></select></div>' +
                '<nav class="adt_f360__filters f360c-status" aria-label="Estado de las cuentas">' + ['', 'En gestión', 'Vencido', 'Resuelto', 'Cerrado sin resolver'].map(function (state) { return '<button type="button" class="adt_f360__filter' + (!state ? ' is-active' : '') + '" data-state="' + esc(state) + '">' + esc(state || 'Todas') + '</button>'; }).join('') + '</nav>' +
                '<select data-c="status" class="d-none" aria-label="Estado"><option value="">Todos los estados</option><option>En gestión</option><option>Vencido</option><option>Resuelto</option><option>Cerrado sin resolver</option></select></header>' +
                '<p class="f360c-sync" role="status"></p><div data-c="metrics"></div><section class="f360c-panel"><div class="f360c-panel-head"><div><h2>Rendimiento del equipo</h2><p>Cobros contabilizados sobre el objetivo fijado al asignar.</p></div></div><div data-c="team" class="f360c-team"></div></section>' +
                '<section class="f360c-panel"><div class="f360c-panel-head"><h2>Cuentas en seguimiento</h2></div><div data-c="table" class="adt_f360__table-wrap f360c-table" aria-live="polite"></div></section></div>');
            this._refreshTimer = setInterval(function () { if (!document.hidden && !self.isDestroyed()) { self._load(); } }, 60000);
            return this._load();
        },
        destroy: function () { clearInterval(this._refreshTimer); return this._super.apply(this, arguments); },
        _filterStatus: function (ev) { this.$('[data-c="status"]').val(ev.currentTarget.dataset.state); this._renderData(); },
        _fleet: function () { return this.do_action('adt_flota_360.action_adt_flota_360'); },
        _load: function () {
            var self = this;
            if (this._loading) { return this._loading; }
            this.$('[data-c="refresh"]').prop('disabled', true);
            this.$('.f360c-sync').text('Actualizando cobros…');
            this._loading = this._rpc({model: 'adt.flota360.cartera', method: 'tablero', args: []}).then(function (data) {
                if (self.isDestroyed()) { return; }
                self.data = data;
                self.$('[data-c="new"]').toggle(data.manager);
                self.$('[data-c="fleet"]').toggle(data.manager);
                self.$('[data-c="owner"]').toggle(data.manager);
                self.$('.f360c-tabs .active').text(data.manager ? 'Carteras de cobranza' : 'Mi cartera');
                self.$('.f360c-head h1').text(data.manager ? 'Carteras de cobranza' : 'Mi cartera');
                self.$('.f360c-head p').text(data.manager ? 'Asigna clientes, acompaña la gestión y sigue los cobros de tu equipo.' : 'Gestiona tus cobros y sigue el avance de tus objetivos.');
                self.$('[data-c="team"]').closest('.f360c-panel').find('h2').text(data.manager ? 'Rendimiento del equipo' : 'Mis indicadores');
                var old = self.$('[data-c="owner"]').val();
                self.$('[data-c="owner"]').html('<option value="">Todos los responsables</option>' + data.users.map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + '</option>'; }).join('')).val(old || '');
                self.$('.f360c-sync').text('Última actualización: ' + new Date().toLocaleTimeString('es-PE') + ' · Se actualiza automáticamente cada minuto.');
                self._renderData();
            }).catch(function (error) { self.$('.f360c-sync').text('No se pudieron actualizar los cobros. Intenta nuevamente.'); throw error; }).finally(function () { self._loading = null; self.$('[data-c="refresh"]').prop('disabled', false); });
            return this._loading;
        },
        _renderData: function () {
            if (!this.data) { return; }
            var self = this, q = (this.$('[data-c="search"]').val() || '').toLowerCase();
            var owner = this.$('[data-c="owner"]').val(), status = this.$('[data-c="status"]').val();
            var rows = this.data.rows.filter(function (r) { return (!owner || r.user_id === Number(owner)) && (!status || r.estado === status) && (r.cliente + ' ' + r.cuenta + ' ' + r.cartera).toLowerCase().includes(q); });
            this.rows = rows;
            this.$('[data-state]').each(function () { $(this).toggleClass('is-active', this.dataset.state === status); });
            var currencies = {}, team = {};
            rows.forEach(function (r) {
                var c = currencies[r.moneda] || (currencies[r.moneda] = {target: 0, paid: 0}); c.target += r.objetivo; c.paid += r.cobrado;
                var k = r.user_id + ':' + r.moneda, t = team[k] || (team[k] = {name: r.responsable, currency: r.moneda, target: 0, paid: 0, done: 0, count: 0});
                t.target += r.objetivo; t.paid += r.cobrado; t.count++; t.done += r.resuelto ? 1 : 0;
            });
            this.$('[data-c="metrics"]').html('<div class="adt_f360__figures f360c-metrics"><article><span>Cuentas asignadas</span><strong>' + rows.length + '</strong><small>' + rows.filter(function (r) { return r.resuelto; }).length + ' resueltas</small></article><article><span>Requieren atención</span><strong>' + rows.filter(function (r) { return r.estado === 'Vencido'; }).length + '</strong><small>Fuera del plazo asignado</small></article>' + '<article><span>Clientes contactados</span><strong>' + rows.filter(function (r) { return r.gestion === 'contactado' || r.gestion === 'promesa'; }).length + '</strong><small>Con gestión registrada</small></article><article><span>Promesas pendientes</span><strong>' + rows.filter(function (r) { return r.gestion === 'promesa' && !r.resuelto && !r.cerrada; }).length + '</strong><small>Compromisos por verificar</small></article>' + Object.keys(currencies).map(function (c) { var v = currencies[c]; return '<article class="f360c-highlight"><span>Cobrado · ' + esc(c) + '</span><strong>' + esc(money(v.paid, c)) + '</strong><small>Objetivo ' + esc(money(v.target, c)) + '</small>' + progress(v.paid, v.target) + '</article>'; }).join('') + '</div>');
            this.$('[data-c="metrics"] article').addClass('adt_f360__figure');
            this.$('[data-c="metrics"] article > span').addClass('adt_f360__figure-label');
            this.$('[data-c="metrics"] article > strong').addClass('adt_f360__figure-value');
            this.$('[data-c="metrics"] article > small').addClass('adt_f360__figure-sub');
            this.$('[data-c="team"]').html(Object.keys(team).map(function (k) { var t = team[k]; return '<article><div class="f360c-avatar">' + esc(t.name.slice(0, 1)) + '</div><h3>' + esc(t.name) + '</h3><p>' + t.done + ' de ' + t.count + ' cuentas resueltas</p><strong>' + esc(money(t.paid, t.currency)) + '</strong><p>de ' + esc(money(t.target, t.currency)) + '</p>' + progress(t.paid, t.target) + '</article>'; }).join('') || '<p class="f360c-empty">' + (this.data.manager ? 'Asigna tu primera cartera para ver el progreso del equipo.' : 'Todavía no tienes clientes asignados. Tu supervisor puede asignarte una cartera.') + '</p>');
            this.$('[data-c="table"]').html(rows.length ? '<table class="adt_f360__table"><thead><tr><th>Cliente / cuenta</th><th>Cartera / responsable</th><th>Avance del cobro</th><th>Plazo / estado</th><th>Última gestión</th><th>Acciones</th></tr></thead><tbody>' + rows.map(function (r) {
                return '<tr><td><button class="f360c-link" data-account="' + r.cuenta_id + '">' + esc(r.cliente) + '</button><small>' + esc(r.cuenta) + '</small></td><td>' + esc(r.cartera) + '<small>' + esc(r.responsable) + '</small></td><td><strong>' + esc(money(r.cobrado, r.moneda)) + '</strong><small>de ' + esc(money(r.objetivo, r.moneda)) + '</small>' + progress(r.cobrado, r.objetivo) + '</td><td><span class="adt_f360__badge ' + (r.resuelto ? 'is-ok' : r.estado === 'Vencido' ? 'is-atencion' : 'is-info') + '">' + esc(r.estado) + '</span><small>' + date(r.limite) + '</small></td><td>' + esc({pendiente: 'Sin contactar', contactado: 'Contactado', promesa: 'Promesa: ' + date(r.promesa), sin_respuesta: 'Sin respuesta'}[r.gestion]) + '<small class="f360c-note">' + esc(r.nota) + '</small></td><td>' + (!r.cerrada ? '<button class="adt_f360__btn is-small" data-manage="' + r.id + '">Gestionar</button>' + (self.data.manager ? ' <button class="adt_f360__btn is-small is-ghost" data-close="' + r.id + '">Cerrar</button>' : '') : '—') + '</td></tr>';
            }).join('') + '</tbody></table>' : '<p class="f360c-empty">No hay cuentas para esta selección.</p>');
        },
        _account: function (ev) {
            if (!this.data.manager) {
                var row = this.data.rows.find(function (r) { return r.cuenta_id === Number(ev.currentTarget.dataset.account); });
                var $body = $('<div class="adt_f360 f360c-form"/>').html('<h4>' + esc(row.cliente) + '</h4><p>Cuenta: ' + esc(row.cuenta) + '</p><p>Teléfono: ' + esc(row.telefono || 'Sin teléfono registrado') + '</p><p>Objetivo: ' + esc(money(row.objetivo, row.moneda)) + '</p><p>Cobrado: ' + esc(money(row.cobrado, row.moneda)) + '</p><p>Fecha límite: ' + date(row.limite) + '</p>');
                return new Dialog(this, {title: 'Mi cliente', $content: $body, buttons: [{text: 'Cerrar', close: true}]}).open();
            }
            return this.do_action({type: 'ir.actions.act_window', res_model: 'adt.comercial.cuentas', res_id: Number(ev.currentTarget.dataset.account), views: [[false, 'form']], target: 'new'}, {on_close: this._load.bind(this)}); },
        _manage: function (ev) {
            var self = this, row = this.data.rows.find(function (r) { return r.id === Number(ev.currentTarget.dataset.manage); });
            var $body = $('<div class="adt_f360 f360c-form"/>').html(field('Resultado del contacto', '<select name="gestion"><option value="pendiente">Sin contactar</option><option value="contactado">Contactado</option><option value="promesa">Promesa de pago</option><option value="sin_respuesta">Sin respuesta</option></select>') + field('Fecha de promesa', '<input type="date" name="promesa"/>') + field('Notas de seguimiento', '<textarea name="nota" rows="4" maxlength="5000"></textarea>') + '<p>El estado resuelto se verifica con los pagos contabilizados de las cuotas asignadas.</p>');
            $body.find('[name="gestion"]').val(row.gestion); $body.find('[name="promesa"]').val(row.promesa); $body.find('[name="nota"]').val(row.nota);
            var dialog = new Dialog(this, {title: row.cliente + ' · ' + row.cuenta, $content: $body, buttons: [{text: 'Guardar gestión', classes: 'btn-primary', click: function () {
                return self._rpc({model: 'adt.flota360.cartera.linea', method: 'registrar_gestion', args: [[row.id], $body.find('[name="gestion"]').val(), $body.find('[name="promesa"]').val() || false, $body.find('[name="nota"]').val()]}).then(function () { dialog.close(); return self._load(); });
            }}, {text: 'Cancelar', close: true}]}).open();
        },
        _close: function (ev) {
            var self = this, id = Number(ev.currentTarget.dataset.close);
            Dialog.confirm(this, 'Cerrar la gestión conserva su rendimiento y permite asignar nuevamente la cuenta. ¿Continuar?', {confirm_callback: function () {
                return self._rpc({model: 'adt.flota360.cartera.linea', method: 'cerrar', args: [[id]]}).then(self._load.bind(self));
            }});
        },
        _new: function () {
            var self = this, selected = new Set(), loadedRows = [], offset = 0, total = 0;
            var step = 1, busy = false, request = 0, proposal = null, appliedDomain = [], appliedSignature = '', appliedScope = '';
            var today = new Date(), localToday = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
            var $body = $('<div class="adt_f360 f360c-form f360c-wizard"/>').html(
                '<ol class="f360c-steps" aria-label="Pasos de la asignación">' + ['Responsable y plazo', 'Seleccionar clientes', 'Revisar y asignar'].map(function (label, index) { return '<li data-step-label="' + (index + 1) + '"><span>' + (index + 1) + '</span>' + label + '</li>'; }).join('') + '</ol>' +
                '<section data-step="1"><h3>1. Define quién gestionará los cobros</h3><p>Elige al cobrador, el plazo y la deuda que deberá recuperar. Después seleccionarás sus clientes.</p><div class="f360c-form-grid">' +
                field('Cobrador responsable *', '<select name="user" aria-label="Cobrador responsable"><option value="">Elige un cobrador</option>' + this.data.users.map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + '</option>'; }).join('') + '</select>') +
                field('Fecha límite para la gestión *', '<input name="deadline" type="date" min="' + localToday + '" aria-label="Fecha límite para la gestión"/>') +
                field('¿Qué deuda debe cobrar?', '<select name="scope" aria-label="Deuda a cobrar"><option value="due">Cuotas vencidas y exigibles hasta hoy</option><option value="all">Todas las cuotas pendientes, incluidas las futuras</option></select>') +
                field('Nombre de la cartera (opcional)', '<input name="name" placeholder="Ej. Recuperación de octubre" maxlength="120" aria-label="Nombre de la cartera"/>') +
                '</div><div class="f360c-help"><i class="fa fa-info-circle" aria-hidden="true"/> El objetivo será la suma pendiente de las cuotas elegidas. Los pagos registrados medirán el avance del cobrador.</div></section>' +
                '<section data-step="2" hidden><h3>2. Busca y selecciona tus clientes uno por uno</h3><p>Busca por nombre, DNI/RUC o cuenta y marca el cliente que deseas agregar. Puedes repetir la búsqueda: los clientes seleccionados se conservan.</p>' +
                '<div class="f360c-actions f360c-search-clients"><input name="query" type="search" aria-label="Buscar clientes disponibles" placeholder="Nombre, DNI/RUC o N° de cuenta"/><button type="button" class="adt_f360__btn" data-search>Buscar clientes</button></div>' +
                '<div class="f360c-selection"><strong data-selected role="status">Ninguna cuenta seleccionada</strong><button type="button" class="adt_f360__btn is-small is-ghost" data-reset hidden>Quitar selección</button></div>' +
                '<p data-count aria-live="polite"></p><div class="f360c-candidates" aria-label="Cuentas disponibles"></div><div class="f360c-load-more"><button type="button" class="adt_f360__btn" data-load-more hidden>Cargar 50 cuentas más</button><span data-loaded role="status"></span></div></section>' +
                '<section data-step="3" hidden><h3>3. Revisa antes de asignar</h3><p>Comprueba el responsable, los clientes y el importe que se medirá como objetivo.</p><div class="f360c-review"></div><div class="f360c-help"><i class="fa fa-check-circle" aria-hidden="true"/> Al confirmar, el cobrador encontrará estos clientes y sus indicadores en <strong>Mi cartera</strong>.</div></section>' +
                '<p class="f360c-wizard-error" data-error role="alert" tabindex="-1"></p><footer class="f360c-wizard-footer"><button type="button" class="adt_f360__btn is-ghost" data-cancel>Cancelar</button><div class="f360c-actions"><button type="button" class="adt_f360__btn" data-back hidden>Volver</button><button type="button" class="adt_f360__btn is-primary" data-forward>Continuar: elegir clientes</button></div></footer>');
            function error(message, input) {
                $body.find('[data-error]').text(message);
                (input ? $body.find('[name="' + input + '"]') : $body.find('[data-error]')).trigger('focus');
            }
            function fail(err) { error((err.data && (err.data.message || err.data.arguments && err.data.arguments[0])) || err.message || 'No se pudo completar la operación. Intenta nuevamente.'); }
            function lock(value) { busy = value; $body.find('button, input, select').prop('disabled', value); if (!value) { count(); } }
            function currentDomain() {
                var d = [], q = $body.find('[name="query"]').val().trim();
                return q ? d.concat(['|', '|', ['reference_no', 'ilike', q], ['partner_id.name', 'ilike', q], ['partner_document', 'ilike', q]]) : d;
            }
            function count() {
                var n = selected.size;
                $body.find('[data-selected]').text(n ? n + (n === 1 ? ' cuenta seleccionada' : ' cuentas seleccionadas') : 'Ninguna cuenta seleccionada');
                $body.find('[data-count]').text('Mostrando ' + loadedRows.length + ' de ' + total + ' cuentas disponibles' + ' · Marca cada cuenta que deseas agregar.');
                $body.find('[data-reset]').prop('hidden', n === 0);
                $body.find('[data-pick]').each(function () { $(this).prop('checked', selected.has(Number(this.dataset.pick))).prop('disabled', busy); });
                $body.find('[data-load-more]').prop('hidden', offset >= total).prop('disabled', busy).text('Cargar ' + Math.min(50, Math.max(0, total - offset)) + ' cuentas más');
                $body.find('[data-loaded]').text(total && offset >= total ? 'Ya se muestran todas las cuentas disponibles.' : '');
            }
            function showStep(n) {
                step = n; $body.find('[data-error]').text('');
                $body.find('[data-step]').each(function () { this.hidden = Number(this.dataset.step) !== n; });
                $body.find('[data-step-label]').each(function () { $(this).toggleClass('is-current', Number(this.dataset.stepLabel) === n).toggleClass('is-done', Number(this.dataset.stepLabel) < n).attr('aria-current', Number(this.dataset.stepLabel) === n ? 'step' : null); });
                $body.find('[data-back]').prop('hidden', n === 1).text(n === 3 ? 'Volver a los clientes' : 'Volver al responsable');
                $body.find('[data-forward]').text(n === 1 ? 'Continuar: elegir clientes' : n === 2 ? 'Continuar: revisar asignación' : 'Confirmar y asignar cartera');
                $body.closest('.modal-body').scrollTop(0);
            }
            function preview(reset, append) {
                var seq = ++request, nextOffset = append ? offset : 0;
                if (reset) { offset = 0; loadedRows = []; total = 0; if (appliedScope && appliedScope !== $body.find('[name="scope"]').val()) { selected.clear(); } appliedDomain = currentDomain(); appliedSignature = JSON.stringify(appliedDomain); appliedScope = $body.find('[name="scope"]').val(); }
                lock(true); $body.find('[data-count]').text(append ? 'Cargando más cuentas…' : 'Buscando cuentas disponibles…');
                $body.find('[data-load-more]').text('Cargando…');
                return self._rpc({model: 'adt.flota360.cartera', method: 'candidatos', kwargs: {domain: appliedDomain, offset: nextOffset, vencidas: $body.find('[name="scope"]').val() === 'due'}}).then(function (data) {
                    if (seq !== request || dialog.isDestroyed()) { return; }
                    total = data.total;
                    var known = new Set(append ? loadedRows.map(function (r) { return r.id; }) : []);
                    var incoming = data.rows.filter(function (r) { return !known.has(r.id); });
                    loadedRows = append ? loadedRows.concat(incoming) : incoming;
                    offset = nextOffset + data.rows.length;
                    // Stop an empty page rather than offer a button that cannot make progress.
                    if (!data.rows.length) { offset = total; }
                    var html = incoming.map(function (r) { return '<label><input type="checkbox" data-pick="' + r.id + '"/><span><strong>' + esc(r.cliente) + '</strong><small>Cuenta ' + esc(r.name) + ' · ' + esc(r.placa || 'Sin placa') + '</small></span><strong class="f360c-candidate-amount">' + esc(money(r.objetivo, r.moneda)) + '</strong></label>'; }).join('');
                    if (append) { $body.find('.f360c-candidates').append(html); }
                    else { $body.find('.f360c-candidates').html(html || '<div class="f360c-empty">No hay cuentas disponibles. Prueba con otra búsqueda o vuelve al paso 1 para cambiar la deuda a cobrar.</div>'); }
                }).catch(fail).finally(function () { lock(false); });
            }
            $body.on('click', '[data-search]', function () { if (!busy) { preview(true); } });
            $body.on('keydown', '[name="query"]', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); if (!busy) { preview(true); } } });
            $body.on('click', '[data-load-more]', function () { if (!busy && offset < total) { preview(false, true); } });
            $body.on('change', '[data-pick]', function () { if (this.checked) { selected.add(Number(this.dataset.pick)); } else { selected.delete(Number(this.dataset.pick)); } count(); });
            $body.on('click', '[data-reset]', function () { selected.clear(); count(); });
            $body.on('click', '[data-cancel]', function () { if (!busy) { dialog.close(); } });
            $body.on('click', '[data-back]', function () { if (!busy) { showStep(step - 1); } });
            $body.on('click', '[data-forward]', function () {
                if (busy) { return; }
                if (step === 1) {
                    if (!$body.find('[name="user"]').val()) { error('Elige al cobrador que recibirá estos clientes.', 'user'); return; }
                    var deadline = $body.find('[name="deadline"]').val();
                    if (!deadline || deadline < localToday) { error('Indica una fecha límite desde hoy.', 'deadline'); return; }
                    showStep(2);
                    var changed = appliedSignature !== JSON.stringify(currentDomain()) || appliedScope !== $body.find('[name="scope"]').val();
                    if (changed || !loadedRows.length) { preview(changed); }
                } else if (step === 2) {
                    if (!selected.size) { error('Marca al menos una cuenta de la lista para continuar.'); return; }
                    lock(true);
                    self._rpc({model: 'adt.flota360.cartera', method: 'revisar_asignacion', kwargs: {domain: [], account_ids: Array.from(selected), vencidas: $body.find('[name="scope"]').val() === 'due'}}).then(function (data) {
                        proposal = data;
                        var user = $body.find('[name="user"] option:selected').text();
                        if (!$body.find('[name="name"]').val().trim()) { $body.find('[name="name"]').val('Cartera de ' + user + ' · ' + date($body.find('[name="deadline"]').val())); }
                        var items = [['Cobrador responsable', user], ['Nombre de la cartera', $body.find('[name="name"]').val()], ['Fecha límite', date($body.find('[name="deadline"]').val())], ['Deuda a cobrar', $body.find('[name="scope"] option:selected').text()], ['Clientes y cuentas', data.clientes + (data.clientes === 1 ? ' cliente · ' : ' clientes · ') + data.cuentas + (data.cuentas === 1 ? ' cuenta' : ' cuentas')]];
                        Object.keys(data.importes).forEach(function (c) { items.push(['Objetivo de cobro · ' + c, money(data.importes[c], c)]); });
                        $body.find('.f360c-review').html('<dl>' + items.map(function (item) { return '<div><dt>' + esc(item[0]) + '</dt><dd>' + esc(item[1]) + '</dd></div>'; }).join('') + '</dl>');
                        showStep(3);
                    }).catch(fail).finally(function () { lock(false); });
                } else {
                    lock(true); $body.find('[data-forward]').text('Asignando cartera…');
                    self._rpc({model: 'adt.flota360.cartera', method: 'asignar', kwargs: {name: $body.find('[name="name"]').val().trim(), user_id: Number($body.find('[name="user"]').val()), fecha_limite: $body.find('[name="deadline"]').val(), domain: [], account_ids: proposal.account_ids, vencidas: $body.find('[name="scope"]').val() === 'due'}}).then(function () { dialog.close(); return self._load(); }).catch(fail).finally(function () { if (!dialog.isDestroyed()) { lock(false); $body.find('[data-forward]').text('Confirmar y asignar cartera'); } });
                }
            });
            var dialog = new Dialog(this, {title: 'Asignar cartera de clientes', size: 'large', $content: $body, buttons: []}).open();
            dialog.opened(function () { showStep(1); $body.find('[name="user"]').trigger('focus'); });
            dialog.on('closed', this, function () { request++; });
        }
    });
    Flota360.include({
        events: _.extend({}, Flota360.prototype.events, {'click [data-open-carteras]': '_openCarteras'}),
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self.$('.adt_f360__top').prepend('<nav class="adt_f360__filters f360c-tabs"><button class="adt_f360__filter is-active active">Consulta 360</button><button class="adt_f360__filter" data-open-carteras>Carteras de cobranza</button></nav>');
            });
        },
        _openCarteras: function () { return this.do_action('adt_flota_360.action_carteras'); }
    });
    core.action_registry.add('adt_flota_360_carteras', Cartera);
    return Cartera;
});
