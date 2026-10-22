odoo.define('adt_comercial.CandidatoDetalle', function (require) {
    'use strict';
    var Candidatos = require('adt_comercial.FlotaClientes').CandidatosPrestamo;
    var esc = _.escape;
    function date(v) { return v ? moment(v).format('DD/MM/YYYY') : 'No registrada'; }
    function datetime(v) { return v ? moment.utc(v).local().format('DD/MM/YYYY HH:mm') : 'No registrada'; }
    function money(v, currency) { return (currency || 'PEN') + ' ' + Number(v || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    function badge(label, kind) { return '<span class="adt_cf__badge is-' + (kind || 'neutral') + '">' + esc(label) + '</span>'; }
    function block(title, body, id) { return '<section class="adt_cf__sec adt_cf__risk-section"' + (id ? ' data-risk-section="' + id + '"' : '') + '><h3>' + title + '</h3>' + body + '</section>'; }
    function empty(text) { return '<p class="adt_cf__risk-empty">' + esc(text) + '</p>'; }
    function facts(items, currency) {
        return '<dl class="adt_cf__risk-facts">' + items.map(function (f) {
            var value = f.tipo === 'date' ? date(f.valor) : f.tipo === 'datetime' ? datetime(f.valor) : f.tipo === 'monetary' ? money(f.valor, currency) : String(f.valor);
            return '<div><dt>' + esc(f.label) + '</dt><dd>' + esc(value) + '</dd></div>';
        }).join('') + '</dl>';
    }
    Candidatos.include({
        events: _.extend({}, Candidatos.prototype.events, {
            'click [data-risk-retry]': '_recargarRiesgo',
            'click [data-risk-file]': '_verRiesgoArchivo',
            'click [data-risk-view-close]': '_cerrarRiesgoArchivo',
            'click [data-risk-jump]': '_saltarRiesgo',
            'click [data-risk-copy]': '_copiarRiesgo'
        }),
        _renderPanel: function () {
            this._super.apply(this, arguments);
            var client = this.clientesPorId[this.abierto];
            if (!client) { return; }
            this._riskFiles = [];
            var $side = this._ref('side');
            $side.addClass('adt_cf__side--risk');
            // Replace the account links with the full inline dossier.
            $side.find('[data-cuenta]').closest('.adt_cf__sec').remove();
            $side.find('[data-action="historial"]').remove();
            $side.find('.adt_cf__side-body').prepend(
                '<section class="adt_cf__sec adt_cf__risk-explanation"><h3>' + (client.segmento === 'no_prestar' ? '¿Por qué aparece como No apto?' : 'Detalle de la evaluación') + '</h3>' +
                '<p>' + esc(this._explicarClasificacion(client)) + '</p><p class="adt_cf__sub">El detalle muestra los registros accesibles en las empresas seleccionadas.</p></section>' +
                '<nav class="adt_cf__risk-nav" aria-label="Detalle del historial"><button type="button" class="adt_cf__btn" data-risk-jump="capturas">Capturas</button><button type="button" class="adt_cf__btn" data-risk-jump="papeletas">Papeletas</button><button type="button" class="adt_cf__btn" data-risk-jump="creditos">Cuotas y pagos</button></nav>' +
                '<div data-risk-detail aria-live="polite"><p class="adt_cf__risk-loading"><i class="fa fa-spinner fa-spin" aria-hidden="true"/> Cargando capturas, evidencias y deuda del cliente…</p></div>');
            $side.append('<section class="adt_cf__risk-viewer" data-risk-view hidden role="dialog" aria-modal="false" aria-label="Vista previa de evidencia"></section>');
            this._cargarRiesgo();
        },
        _explicarClasificacion: function (c) {
            var s = c.seguimiento || {};
            if (s.clasificacion_manual === 'no_prestar') {
                return 'La clasificación No apto fue registrada manualmente.' + (s.motivo_manual ? ' Motivo: ' + s.motivo_manual : ' No se registró un motivo.') + ' El puntaje actual es ' + c.puntaje + ' de 100.';
            }
            if (c.bloqueos.length) {
                return 'El tablero lo clasifica como No apto por los siguientes motivos: ' + c.bloqueos.join('; ') + '. Su puntaje es ' + c.puntaje + ' de 100. Abajo puedes revisar los registros que sustentan su historial.';
            }
            return 'El puntaje de este cliente es ' + c.puntaje + ' de 100. Revisa las capturas, papeletas y cuotas para entender su historial antes de continuar la evaluación.';
        },
        _cargarRiesgo: function () {
            var self = this, id = this.abierto, seq = (this._riskSeq || 0) + 1;
            this._riskSeq = seq;
            return this._rpc({model: 'adt.comercial.clientes.dashboard', method: 'detalle_candidato', args: [id]}, {shadow: true}).then(function (data) {
                if (self.isDestroyed() || self.abierto !== id || self._riskSeq !== seq) { return; }
                self._riskData = data;
                self._riskFiles = [];
                self._ref('side').find('[data-risk-detail]').html(self._htmlRiesgo(self.clientesPorId[id], data));
            }).guardedCatch(function (error) {
                if (error && error.event) { error.event.preventDefault(); }
                if (self.isDestroyed() || self.abierto !== id || self._riskSeq !== seq) { return; }
                self._ref('side').find('[data-risk-detail]').html('<div class="adt_cf__sec"><p class="adt_cf__error">No se pudo cargar el historial detallado. Los datos no se han interpretado como ausencia de deuda.</p><button class="adt_cf__btn" type="button" data-risk-retry>Volver a cargar el detalle</button></div>');
            });
        },
        _recargarRiesgo: function () { this._ref('side').find('[data-risk-detail]').html('<p class="adt_cf__risk-loading">Actualizando historial…</p>'); return this._cargarRiesgo(); },
        _riesgoEvidencias: function (files) {
            var self = this;
            if (!files.length) { return empty('Sin evidencias adjuntas disponibles para tu usuario.'); }
            return '<div class="adt_cf__risk-files">' + files.map(function (f) {
                var index = self._riskFiles.push(f) - 1;
                return '<button type="button" class="adt_cf__risk-file" data-risk-file="' + index + '">' +
                    (f.miniatura ? '<img src="' + esc(f.miniatura) + '" alt="" loading="lazy"/>' : '<i class="fa ' + (f.mime.indexOf('video/') === 0 ? 'fa-file-video-o' : f.mime === 'application/pdf' ? 'fa-file-pdf-o' : 'fa-file-o') + '" aria-hidden="true"/>') +
                    '<span>' + esc(f.nombre) + '</span><small>Ver aquí</small></button>';
            }).join('') + '</div>';
        },
        _riesgoHistorial: function (events) {
            var self = this;
            return events.length ? '<details class="adt_cf__risk-history"><summary>Fechas y movimientos registrados (' + events.length + ')</summary><ol>' + events.map(function (e) {
                return '<li><strong>' + datetime(e.fecha) + '</strong> <span>' + esc(e.autor) + '</span>' +
                    (e.texto ? '<p class="adt_cf__risk-text">' + esc(e.texto) + '</p>' : '') +
                    (e.cambios.length ? '<ul>' + e.cambios.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul>' : '') +
                    (e.evidencias.length ? self._riesgoEvidencias(e.evidencias) : '') + '</li>';
            }).join('') + '</ol></details>' : empty('Sin movimientos adicionales visibles para tu usuario.');
        },
        _htmlRiesgo: function (client, data) {
            var self = this, caps = data.capturas, papers = data.papeletas;
            var messages = [], amounts = Object.keys(data.totales);
            if (caps.disponible && caps.items.length) {
                messages.push('Su historial contiene ' + caps.items.length + ' registros de captura: ' + caps.activas + ' activos y ' + caps.canceladas + ' cancelados. Revisa el motivo, las fechas y las evidencias de cada registro.');
            }
            amounts.forEach(function (currency) {
                var t = data.totales[currency];
                if (t.vencido > 0) { messages.push('Tiene ' + money(t.vencido, currency) + ' de capital vencido en su cronograma. Las cuotas y sus fechas aparecen en el detalle de cada crédito.'); }
                if (t.papeletas > 0) { messages.push('Tiene ' + money(t.papeletas, currency) + ' pendiente en papeletas del periodo de sus créditos. El importe toma en cuenta las cuotas pagadas de los fraccionamientos.'); }
                if (t.mora > 0) { messages.push('Además del capital, se registra ' + money(t.mora, currency) + ' de mora pendiente.'); }
            });
            if (!messages.length) { messages.push('Revisa los motivos de clasificación y el historial disponible. La ausencia de movimientos visibles no permite concluir que no existan incidencias.'); }
            this._riskCopyText = this._explicarClasificacion(client) + '\n\n' + messages.join('\n');
            var summary = block('Explicación sugerida', '<p class="adt_cf__sub">Redacción basada en los datos registrados. No modifica la clasificación ni reemplaza la revisión del expediente.</p><ul class="adt_cf__risk-messages">' + messages.map(function (m) { return '<li>' + esc(m) + '</li>'; }).join('') + '</ul><button type="button" class="adt_cf__btn is-small" data-risk-copy><i class="fa fa-copy" aria-hidden="true"/> Copiar explicación</button><span data-copy-status role="status"></span>');
            summary += amounts.length ? block('Deuda actual por moneda (cuentas en curso y papeletas)', '<div class="adt_cf__risk-totals">' + amounts.map(function (c) {
                var t = data.totales[c];
                return '<article><strong>' + esc(c) + '</strong>' + facts([
                    {label: 'Capital pendiente (incluye cuotas futuras)', valor: t.saldo, tipo: 'monetary'},
                    {label: 'De ese capital, vencido', valor: t.vencido, tipo: 'monetary'},
                    {label: 'Mora pendiente', valor: data.pagos_disponibles ? money(t.mora, c) : 'Sin permiso para consultar pagos'},
                    {label: 'Papeletas pendientes', valor: papers.disponible ? money(t.papeletas, c) : 'Sin acceso al detalle'}], c) + '</article>';
            }).join('') + '</div>') : '';
            var captures = !caps.disponible ? empty(caps.motivo) : (caps.items.length ? '<p class="adt_cf__sub">' + caps.items.length + ' registros · ' + caps.activas + ' activos · ' + caps.canceladas + ' cancelados. Se incluyen los cancelados para conservar la trazabilidad.</p>' + caps.items.map(function (c, index) {
                return '<details class="adt_cf__risk-record"' + (index === 0 ? ' open' : '') + '><summary><span><strong>' + esc(c.numero) + '</strong> · ' + esc(c.cuenta) + '<small>Registrada el ' + datetime(c.fecha) + ' · ' + esc(c.placa || 'Sin placa') + '</small></span>' + badge(c.estado, c.estado_clave === 'capturado' || c.estado_clave === 'disolucion_contrato' ? 'critico' : 'neutral') + '</summary><div class="adt_cf__risk-record-body"><h4>¿Por qué se registró la captura?</h4><p><strong>Origen:</strong> ' + esc(c.origen) + '</p><p class="adt_cf__risk-text">' + esc(c.motivo || 'Motivo de la captura no registrado. No se infiere una causa a partir del puntaje.') + '</p>' + facts(c.campos, c.moneda) + '<h4>Evidencias y documentos</h4>' + self._riesgoEvidencias(c.evidencias) + c.apelaciones.map(function (a) { return '<h4>Apelación · ' + datetime(a.fecha) + '</h4><p class="adt_cf__risk-text">' + esc(a.motivo) + '</p>' + self._riesgoEvidencias(a.evidencias); }).join('') + self._riesgoHistorial(c.historial) + '</div></details>';
            }).join('') : empty('No hay registros de captura accesibles para las cuentas de este cliente.'));
            var tickets = !papers.disponible ? empty(papers.motivo) : papers.items.map(function (p, index) {
                return '<details class="adt_cf__risk-record"' + (p.saldo > 0 && index === 0 ? ' open' : '') + '><summary><span><strong>Papeleta ' + esc(p.numero) + '</strong><small>' + date(p.fecha) + ' · ' + esc(p.placa) + ' · ' + esc(p.cuentas.join(', ')) + '</small></span>' + badge(p.estado, p.saldo > 0 ? 'atencion' : 'ok') + '</summary><div class="adt_cf__risk-record-body"><p class="adt_cf__risk-text">' + esc(p.detalle) + '</p>' + facts([{label: 'Importe original', valor: p.importe, tipo: 'monetary'}, {label: 'Saldo pendiente', valor: p.saldo, tipo: 'monetary'}].concat(p.campos), p.moneda) + (p.cuotas.length ? '<h4>Fraccionamiento de la papeleta</h4><div class="adt_cf__risk-scroll"><table class="adt_cf__risk-table"><thead><tr><th>Cuota</th><th>Vence</th><th>Importe</th><th>Estado</th></tr></thead><tbody>' + p.cuotas.map(function (q) { return '<tr><td>' + esc(q.nombre) + '</td><td>' + date(q.fecha) + '</td><td>' + money(q.monto, p.moneda) + '</td><td>' + esc(q.estado) + '</td></tr>'; }).join('') + '</tbody></table></div>' : '') + '<h4>Evidencias</h4>' + self._riesgoEvidencias(p.evidencias) + self._riesgoHistorial(p.historial) + '</div></details>';
            }).join('') || empty('No hay papeletas accesibles atribuibles al periodo de sus créditos.');
            var credits = data.creditos.items.map(function (c) {
                return '<details class="adt_cf__risk-record" data-risk-credit="' + c.id + '" open><summary><span><strong>' + esc(c.referencia) + '</strong><small>' + esc(c.placa || 'Sin placa') + ' · Desembolso ' + date(c.fecha_desembolso) + '</small></span>' + badge(c.estado, c.recuperado ? 'critico' : 'neutral') + '</summary><div class="adt_cf__risk-record-body">' + facts([{label: c.estado_clave === 'cancelado' ? 'Saldo histórico del cronograma (cuenta cerrada)' : 'Capital pendiente', valor: c.saldo, tipo: 'monetary'}, {label: 'Capital vencido', valor: c.vencido, tipo: 'monetary'}, {label: 'Mora pendiente', valor: c.mora === null ? 'Sin permiso para consultar pagos' : money(c.mora, c.moneda)}], c.moneda) + '<h4>Cronograma completo · ' + c.cuotas.length + ' cuotas</h4>' + (!c.pagos_disponibles ? empty('No tienes permiso para consultar los pagos aplicados. Los saldos del cronograma se muestran por separado.') : '') + c.cuotas.map(function (q) { return self._riesgoCuota(q, c.moneda); }).join('') + (c.evidencias.length ? '<h4>Documentos de la cuenta</h4>' + self._riesgoEvidencias(c.evidencias) : '') + self._riesgoHistorial(c.historial) + '</div></details>';
            }).join('') || empty('Sin cuentas accesibles.');
            return summary + block('Capturas: motivos, fechas y evidencias', captures, 'capturas') + block('Papeletas y deuda pendiente', tickets, 'papeletas') + block('Créditos, cuotas y pagos', credits, 'creditos') + (data.seguimiento_historial.length ? block('Historial de evaluación comercial', this._riesgoHistorial(data.seguimiento_historial)) : '') + '<p class="adt_cf__risk-updated">Actualizado: ' + datetime(data.actualizado) + '</p>';
        },
        _riesgoCuota: function (q, currency) {
            var self = this;
            return '<details class="adt_cf__risk-quota"><summary><span><strong>' + esc(q.nombre) + (q.subcuota ? ' · subcuota' : '') + '</strong><small>Vence ' + date(q.fecha) + (q.atraso_dias ? ' · ' + q.atraso_dias + ' días de atraso' : '') + '</small></span><span>' + esc(money(q.saldo, currency)) + '<small>' + esc(q.estado) + '</small></span></summary><div class="adt_cf__risk-record-body">' + facts([{label: 'Monto de la cuota', valor: q.monto, tipo: 'monetary'}, {label: 'Saldo pendiente', valor: q.saldo, tipo: 'monetary'}, {label: 'Mora pendiente', valor: q.mora === null ? 'No disponible' : money(q.mora, currency)}], currency) + '<h4>Pagos aplicados (' + q.pagos.length + ')</h4>' + (q.pagos.length ? '<div class="adt_cf__risk-scroll"><table class="adt_cf__risk-table"><thead><tr><th>Fecha</th><th>Importe</th><th>Operación</th><th>Diario</th><th>Estado</th><th>Mora</th></tr></thead><tbody>' + q.pagos.map(function (p) { return '<tr><td>' + date(p.fecha) + '</td><td>' + esc(money(p.importe, currency)) + '</td><td>' + esc(p.operacion || 'Sin operación registrada') + '</td><td>' + esc(p.diario) + '</td><td>' + esc(p.estado) + '</td><td>' + esc(money(p.mora, currency)) + '<small>' + esc(p.mora_estado) + (p.mora_pagada_parcial ? ' · abonado ' + esc(money(p.mora_pagada_parcial, currency)) : '') + '</small></td></tr>'; }).join('') + '</tbody></table></div>' : empty('No hay pagos visibles registrados en esta cuota.')) + q.observaciones.map(function (o) { return '<h4>Observación · ' + date(o.fecha) + '</h4><p class="adt_cf__risk-text">' + esc(o.texto) + '</p>' + (o.evidencias.length ? self._riesgoEvidencias(o.evidencias) : ''); }).join('') + (q.evidencias.length ? '<h4>Voucher</h4>' + this._riesgoEvidencias(q.evidencias) : '') + '</div></details>';
        },
        _onAbrirCuenta: function (ev) {
            ev.preventDefault(); ev.stopPropagation();
            var id = Number(ev.currentTarget.getAttribute('data-cuenta'));
            var $credit = this._ref('side').find('[data-risk-credit="' + id + '"]');
            if ($credit.length) { $credit.prop('open', true)[0].scrollIntoView({behavior: 'smooth', block: 'start'}); }
        },
        _saltarRiesgo: function (ev) { var $section = this._ref('side').find('[data-risk-section="' + ev.currentTarget.dataset.riskJump + '"]'); if ($section.length) { $section[0].scrollIntoView({behavior: 'smooth', block: 'start'}); } },
        _verRiesgoArchivo: function (ev) {
            var file = this._riskFiles[Number(ev.currentTarget.dataset.riskFile)];
            if (!file) { return; }
            var preview = file.mime.indexOf('image/') === 0 ? '<img src="' + esc(file.url) + '" alt="' + esc(file.nombre) + '"/>' : file.mime.indexOf('video/') === 0 ? '<video controls src="' + esc(file.url) + '"></video>' : file.mime === 'application/pdf' ? '<iframe title="' + esc(file.nombre) + '" src="' + esc(file.url) + '"></iframe>' : '<p>Este formato no dispone de vista previa en el navegador. Puedes descargar el archivo.</p>';
            this._ref('side').find('[data-risk-view]').prop('hidden', false).html('<header><strong>' + esc(file.nombre) + '</strong><button type="button" class="adt_cf__btn is-icon" data-risk-view-close aria-label="Cerrar evidencia"><i class="fa fa-times"/></button></header><div class="adt_cf__risk-preview">' + preview + '</div><footer><a class="adt_cf__btn" href="' + esc(file.descarga) + '" download>Descargar archivo</a><button type="button" class="adt_cf__btn" data-risk-view-close>Volver al detalle</button></footer>');
            this._ref('side').find('[data-risk-view-close]').first().trigger('focus');
        },
        _cerrarRiesgoArchivo: function () { this._ref('side').find('[data-risk-view]').prop('hidden', true).empty(); },
        _onKeydown: function (ev) { if (ev.key === 'Escape' && !this._ref('side').find('[data-risk-view]').prop('hidden')) { ev.stopPropagation(); this._cerrarRiesgoArchivo(); return; } return this._super.apply(this, arguments); },
        _copiarRiesgo: function () {
            var self = this;
            if (!navigator.clipboard) { this._ref('side').find('[data-copy-status]').text('Selecciona el texto de la explicación para copiarlo.'); return; }
            navigator.clipboard.writeText(this._riskCopyText).then(function () { self._ref('side').find('[data-copy-status]').text('Explicación copiada.'); }).catch(function () { self._ref('side').find('[data-copy-status]').text('No se pudo copiar. Puedes seleccionar el texto manualmente.'); });
        }
    });
});
