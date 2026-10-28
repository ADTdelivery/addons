odoo.define('adt_flota_360.Capturas', function (require) {
    'use strict';

    /**
     * Capturas paso a paso. Arriba, las etapas del proceso (cada una con su cantidad):
     * por capturar → cobrar intervención → liberar o retener → disolución, más las cerradas.
     * Cada etapa lista sus casos. El detalle de un caso (CasoCaptura) es un drawer con la
     * prioridad de captura y el recorrido del cliente, con lo subido en cada paso:
     *   1. Motivo: cuotas vencidas del cronograma y papeletas SAT pendientes.
     *   2. Registrar captura.  3. Cobrar intervención.  4. Liberar o retener.  5. Recolocar.
     * El mismo drawer se abre desde la ficha del vehículo en Flota 360 (acción tipo
     * "captura"). Las reglas son las de adt_captura (adt.flota360.captura_*).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var Widget = require('web.Widget');
    var Flota360 = require('adt_flota_360.Flota360');

    var esc = _.escape;
    var MAX_ARCHIVO = 10 * 1024 * 1024;
    var NIVEL_ICONO = {critico: 'fa-exclamation-circle', atencion: 'fa-clock-o', ok: 'fa-check-circle',
                       info: 'fa-info-circle', neutral: 'fa-minus-circle'};
    // Botón principal de cada etapa del tablero.
    var ETAPA_ACCION = {
        por_capturar: 'Revisar y capturar', por_cobrar: 'Cobrar intervención', por_decidir: 'Liberar o retener',
        disolucion: 'Recolocar', cerradas: 'Ver',
    };
    var ORIGEN_TEXTO = {mora: 'Cuotas vencidas', papeleta: 'Papeletas SAT', ambos: 'Cuotas y papeletas SAT'};
    // Prioridad de captura de la cuenta: valor, texto, color (nivel) y qué significa.
    var PRIORIDADES = [
        ['', 'Sin prioridad', 'neutral', 'Aún no se clasificó.'],
        ['normal', 'Normal', 'atencion', 'Capturar en la ronda habitual.'],
        ['urgente', 'Urgente', 'critico', 'Capturar cuanto antes.'],
    ];

    function prioridad(valor) {
        return _.find(PRIORIDADES, function (p) { return p[0] === (valor || ''); }) || PRIORIDADES[0];
    }

    function chipPrioridad(valor) {
        var p = prioridad(valor);
        return '<span class="adt_cap__prio-chip is-' + p[2] + '"><i class="fa fa-circle" aria-hidden="true"></i>' + esc(p[1]) + '</span>';
    }

    function soles(n) {
        return 'S/ ' + (n || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
    }

    function fecha(f) {
        return f ? moment(f).format('DD/MM/YYYY') : '—';
    }

    function icono(nivel) {
        return '<i class="fa ' + (NIVEL_ICONO[nivel] || NIVEL_ICONO.neutral) + ' adt_cap__ico is-' + (nivel || 'neutral') +
            '" aria-hidden="true"></i>';
    }

    function chip(texto, nivel) {
        return '<span class="adt_cap__chip is-' + (nivel || 'neutral') + '">' + esc(texto) + '</span>';
    }

    function dato(label, valor) {
        return valor ? '<div class="adt_cap__dato"><dt>' + esc(label) + '</dt><dd>' + valor + '</dd></div>' : '';
    }

    function leerArchivo(file) {
        return new Promise(function (resolve, reject) {
            if (file.size > MAX_ARCHIVO) {
                reject(new Error('El archivo ' + file.name + ' supera los 10 MB.'));
                return;
            }
            var reader = new FileReader();
            reader.onload = function () { resolve({nombre: file.name, datos: reader.result}); };
            reader.onerror = function () { reject(new Error('No se pudo leer el archivo ' + file.name + '.')); };
            reader.readAsDataURL(file);
        });
    }

    function errorTexto(err) {
        var data = err && err.message && err.message.data;
        return (data && (data.message || data.arguments && data.arguments[0])) ||
            (err && err.message && (err.message.message || (typeof err.message === 'string' && err.message))) ||
            'No se pudo completar la operación.';
    }

    function llamar(widget, method, kwargs) {
        return widget._rpc({model: 'adt.flota360', method: method, args: [], kwargs: kwargs}, {shadow: true});
    }

    /**
     * Detalle de un caso de captura en un drawer sobre la pantalla que lo abre.
     * Avisa a quien lo abrió con captura_cambio (se registró algo), captura_cerrada
     * y captura_ficha ({tab}: ir a la ficha del vehículo en Flota 360).
     */
    var CasoCaptura = Widget.extend({
        className: 'adt_cart adt_cap adt_cap__overlay is-drawer-open',

        events: {
            'click [data-action="volver"]': '_onVolver',
            'click [data-action="revisado"]': '_onRevisado',
            'click [data-opcion]': '_onOpcion',
            'change [data-campo]': '_onCampo',
            'input [data-campo]': '_onCampo',
            'change [data-archivo]': '_onArchivo',
            'click [data-quitar]': '_onQuitarArchivo',
            'click [data-enviar]': '_onEnviar',
            'click [data-prioridad]': '_onPrioridad',
            'click [data-action="ficha"]': '_onFicha',
            'click [data-action="cancelar-captura"]': '_onCancelarCaptura',
            'click [data-action="decidir-sin-cobro"]': '_onDecidirSinCobro',
            'click [data-abrir-captura]': '_onAbrirCaptura',
        },

        /**
         * @param {Object} kwargs {captura_id} o {cuenta_id}
         * @param {Object} [opciones] enFlota360: abierto desde la ficha del vehículo
         */
        init: function (parent, kwargs, opciones) {
            this._super.apply(this, arguments);
            this.kwargs = kwargs;
            this.enFlota360 = !!(opciones && opciones.enFlota360);
            this.caso = null;
            this.form = null;
            this._onTecla = this._onTecla.bind(this);
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._cargar(this.kwargs)]);
        },

        start: function () {
            this.$el.html('<div class="adt_cap__backdrop" data-action="volver"></div>' +
                '<aside class="adt_cap__drawer" data-ref="drawer" role="dialog" aria-modal="true" aria-label="Detalle de la captura"></aside>');
            this._render();
            document.addEventListener('keydown', this._onTecla);
            this.$('.adt_cap__close').focus();
            return this._super.apply(this, arguments);
        },

        destroy: function () {
            document.removeEventListener('keydown', this._onTecla);
            return this._super.apply(this, arguments);
        },

        _cargar: function (kwargs) {
            var self = this;
            return llamar(this, 'captura_caso', kwargs).then(function (caso) {
                self.kwargs = kwargs;
                self.caso = caso;
                // Al registrar la captura hay que revisar antes el motivo (paso 1).
                self.form = {revisado: caso.paso !== 'capturar', valores: self._valoresIniciales(caso), archivos: {}, error: {}};
            });
        },

        // Vuelve a leer el caso (después de un paso, o al abrir otra captura del historial).
        _recargarCaso: function (kwargs) {
            var self = this;
            var antes = this.caso && this.caso.captura && this.caso.captura.id;
            this.$el.addClass('is-loading');
            return this._cargar(kwargs).then(function () {
                self.$el.removeClass('is-loading');
                self._render();
                if (!self.caso.captura || self.caso.captura.id !== antes) {
                    self.$('[data-ref="drawer"]').scrollTop(0);
                }
            }).guardedCatch(function (err) {
                self.$el.removeClass('is-loading');
                if (err && err.event) { err.event.preventDefault(); }
                self.displayNotification({type: 'danger', title: 'Capturas', message: errorTexto(err)});
            });
        },

        _error: errorTexto,

        _llamar: function (method, kwargs) {
            return llamar(this, method, kwargs);
        },

        _valoresIniciales: function (caso) {
            var o = caso.opciones;
            var c = caso.captura;
            return {
                tipo: 'inmediata', compromiso: '', recogida: true, motivo_no_recogida: '', monto: o.monto_intervencion,
                comentarios: '',
                pagar: true, monto_pago: c ? c.intervencion : o.monto_intervencion, voucher_numero: '', fecha_pago: o.hoy,
                motivo_pago: '',
                decision: null, liberacion: '', observaciones: '',
                retencion: 'motivo1', fecha_retencion: o.hoy, notas_retencion: '',
            };
        },

        _render: function () {
            var k = this.caso;
            var c = k.captura;
            var $drawer = this.$('[data-ref="drawer"]');
            var scroll = $drawer.scrollTop();
            var estado = c ? chip(c.estado, c.state === 'liberado' || c.state === 'recolocada' ? 'ok' : (c.state === 'cancelado' ? 'neutral' : 'critico'))
                : chip('Por capturar', 'info');
            $drawer.html('<header class="adt_cap__drawer-head">' +
                    '<div class="adt_cap__caso-title"><h2>' + esc(k.cliente.nombre) + '</h2>' +
                        '<p>' + esc(_.compact([k.vehiculo.placa || 'Sin placa', k.cuenta.referencia, c && c.numero]).join(' · ')) + ' ' + estado + '</p></div>' +
                    '<div class="adt_cap__drawer-tools">' +
                    (c && c.state === 'capturado' && k.permisos.supervisor
                        ? '<button type="button" class="adt_cap__btn-cancelar" data-action="cancelar-captura" title="Solo si la captura se registró por error">' +
                            '<i class="fa fa-ban" aria-hidden="true"></i>Cancelar captura</button>' : '') +
                    '<button type="button" class="adt_cap__close" data-action="volver" aria-label="Cerrar" title="Cerrar (Esc)">' +
                        '<i class="fa fa-times" aria-hidden="true"></i></button></div></header>' +
                '<div class="adt_cap__drawer-body">' + this._htmlPrioridad() +
                    '<div class="adt_cap__caso"><ol class="adt_cap__flow">' + this._htmlPasos().join('') + '</ol>' +
                    '<div class="adt_cap__side">' + this._htmlLateral() + '</div></div></div>');
            $drawer.scrollTop(scroll);
        },

        // Prioridad de captura: lo primero del detalle, con su color.
        _htmlPrioridad: function () {
            var k = this.caso;
            var c = k.captura;
            var actual = prioridad(k.cuenta.prioridad);
            var editable = !c || c.state === 'capturado';
            return '<section class="adt_cap__prio is-' + actual[2] + '">' +
                '<div class="adt_cap__prio-txt"><span class="adt_cap__prio-label"><i class="fa fa-flag" aria-hidden="true"></i>Prioridad de captura</span>' +
                    '<strong>' + esc(actual[1]) + '</strong><small>' + esc(actual[3]) + '</small></div>' +
                (editable ? '<div class="adt_cap__prio-opts" role="radiogroup" aria-label="Prioridad de captura">' + PRIORIDADES.map(function (p) {
                    var on = p[0] === actual[0];
                    return '<button type="button" role="radio" aria-checked="' + on + '" class="adt_cap__prio-opt is-' + p[2] + (on ? ' is-on' : '') +
                        '" data-prioridad="' + p[0] + '"><i class="fa fa-circle" aria-hidden="true"></i>' + esc(p[1]) + '</button>';
                }).join('') + '</div>' : '') + '</section>';
        },

        // Estado de cada paso del recorrido: hecho, actual, pendiente u omitido.
        _htmlPasos: function () {
            var k = this.caso;
            var c = k.captura;
            var paso = k.paso;
            var cerrada = paso === 'cerrada';
            var pasos = [];
            pasos.push(this._paso(1, 'Revisar el motivo', k.paso === 'capturar' && !this.form.revisado ? 'actual' : 'hecho',
                'Por qué este cliente está en la lista de posibles capturas.', this._htmlMotivo()));
            var estado2 = c ? 'hecho' : (this.form.revisado ? 'actual' : 'pendiente');
            pasos.push(this._paso(2, 'Registrar la captura', estado2,
                'Tipo de captura, si se recogió la moto y las evidencias.', c ? this._htmlCapturaHecha() : (estado2 === 'actual' ? this._htmlFormCaptura() : '')));
            var pagado = c && c.pagado;
            var cancelada = c && c.state === 'cancelado';
            var estado3 = !c ? 'pendiente' : (pagado ? 'hecho' : (cancelada || cerrada ? 'omitido' : 'actual'));
            pasos.push(this._paso(3, 'Cobrar la intervención', estado3,
                'El cliente paga la intervención (' + soles(c ? c.intervencion : k.opciones.monto_intervencion) + ') o se exonera indicando el motivo.',
                estado3 === 'hecho' ? this._htmlCobroHecho() : (estado3 === 'actual' ? this._htmlFormCobro() : '')));
            var decidido = c && _.contains(['liberado', 'disolucion_contrato', 'recolocada'], c.state);
            var estado4 = decidido ? 'hecho' : (cancelada ? 'omitido' : (paso === 'decidir' || (paso === 'cobrar' && this.form.decidirSinCobro) ? 'actual' : 'pendiente'));
            var cuerpo4 = '';
            if (estado4 === 'hecho') {
                cuerpo4 = this._htmlDecisionHecha();
            } else if (estado4 === 'actual') {
                cuerpo4 = this._htmlFormDecision();
            } else if (paso === 'cobrar' && k.permisos.supervisor) {
                cuerpo4 = '<p class="adt_cap__muted">Primero registra el cobro. Si el supervisor decide sin esperar el pago: ' +
                    '<button type="button" class="adt_cap__link" data-action="decidir-sin-cobro">liberar o retener ahora</button>.</p>';
            }
            pasos.push(this._paso(4, 'Liberar o retener', estado4,
                'El supervisor devuelve el vehículo al cliente o inicia la disolución del contrato.', cuerpo4));
            if (c && _.contains(['disolucion_contrato', 'recolocada'], c.state)) {
                var estado5 = c.state === 'recolocada' ? 'hecho' : 'actual';
                pasos.push(this._paso(5, 'Recolocar el vehículo', estado5,
                    'Con la desafiliación firmada y la evidencia de la entrega. La cuenta pasa a cancelada.',
                    estado5 === 'hecho' ? '<p>' + icono('ok') + ' Vehículo recolocado; la cuenta quedó cancelada.</p>' +
                        this._htmlDocs(c.documentos.recolocar, 'Desafiliación y entrega', 'Sin documentos.') : this._htmlFormRecolocar()));
            }
            if (cerrada) {
                pasos.push('<li class="adt_cap__fin is-' + (cancelada ? 'neutral' : 'ok') + '">' + icono(cancelada ? 'neutral' : 'ok') +
                    '<strong>' + (cancelada ? 'Captura cancelada.' : 'Proceso cerrado.') + '</strong> ' +
                    (c.state === 'liberado' ? 'Vehículo liberado (' + esc(c.liberacion) + ').' : '') + '</li>');
            }
            return pasos;
        },

        _paso: function (n, titulo, estado, ayuda, cuerpo) {
            var etiqueta = {hecho: 'Hecho', actual: 'Paso actual', pendiente: 'Pendiente', omitido: 'No aplica'}[estado];
            return '<li class="adt_cap__paso is-' + estado + '"' + (estado === 'actual' ? ' aria-current="step"' : '') + '>' +
                '<span class="adt_cap__paso-num">' + (estado === 'hecho' ? '<i class="fa fa-check" aria-hidden="true"></i>' : n) + '</span>' +
                '<div class="adt_cap__paso-main"><header class="adt_cap__paso-head"><h3>' + esc(titulo) + '</h3>' +
                    '<span class="adt_cap__paso-estado">' + etiqueta + '</span></header>' +
                    (estado === 'hecho' && cuerpo ? '' : '<p class="adt_cap__paso-ayuda">' + esc(ayuda) + '</p>') +
                    (cuerpo ? '<div class="adt_cap__paso-body">' + cuerpo + '</div>' : '') +
                '</div></li>';
        },

        _htmlMotivo: function () {
            var k = this.caso;
            var html = '';
            if (k.alertas.length) {
                html += '<ul class="adt_cap__alertas">' + k.alertas.map(function (a) {
                    return '<li class="is-' + a.nivel + '">' + icono(a.nivel) + esc(a.texto) + '</li>';
                }).join('') + '</ul>';
            }
            html += '<div class="adt_cap__motivos">';
            html += '<section class="adt_cap__motivo' + (k.cuotas.length ? ' is-activo' : '') + '"><h4><i class="fa fa-calendar-times-o" aria-hidden="true"></i>' +
                'Cronograma de pagos</h4>' +
                (k.cuotas.length
                    ? '<div class="adt_cap__resumen"><strong>' + soles(k.cuotas_total) + '</strong>' +
                        '<span>' + plural(k.cuotas.length, 'cuota vencida', 'cuotas vencidas') + ' · la más antigua hace ' +
                        plural(k.cuotas[0].dias, 'día', 'días') + '</span></div>'
                    : '<div class="adt_cap__resumen is-ok"><strong>Al día</strong><span>Sin cuotas vencidas</span></div>') +
                (k.vehicle_id ? '<button type="button" class="adt_cap__link" data-action="ficha" data-tab="cronograma">' +
                    (this.enFlota360 ? 'Ver el cronograma completo' : 'Ver el cronograma en Flota 360') +
                    ' <i class="fa fa-external-link" aria-hidden="true"></i></button>' : '') + '</section>';
            var pendientes = _.where(k.papeletas, {pendiente: true});
            html += '<section class="adt_cap__motivo' + (pendientes.length ? ' is-activo' : '') + '"><h4><i class="fa fa-university" aria-hidden="true"></i>' +
                'Papeletas SAT Lima<span>' + (pendientes.length ? soles(k.papeletas_total) : 'Sin pendientes') + '</span></h4>' +
                (k.papeletas.length ? '<table class="adt_cap__mini"><thead><tr><th>Papeleta</th><th>Infracción</th><th>Estado SAT</th>' +
                    '<th class="is-num">Deuda</th></tr></thead><tbody>' + k.papeletas.map(function (p) {
                        return '<tr class="is-' + p.nivel + '"><td class="adt_cap__mono">' + esc(p.numero) + '</td><td>' + fecha(p.fecha) +
                            '<span class="adt_cap__sub">' + plural(p.dias, 'día', 'días') + '</span></td>' +
                            '<td>' + icono(p.nivel) + esc(p.pendiente ? (p.estado_sat || 'Pendiente') : 'Pagada') + '</td>' +
                            '<td class="is-num">' + soles(p.deuda) + '</td></tr>';
                    }).join('') + '</tbody></table><p class="adt_cap__muted">El pago de las papeletas se confirma solo con la ' +
                    'consulta diaria al SAT.</p>' : '<p class="adt_cap__muted">El SAT no registra papeletas pendientes.</p>') + '</section>';
            html += '</div>';
            if (k.paso === 'capturar' && !this.form.revisado) {
                html += k.permisos.capturar
                    ? '<div class="adt_cap__acciones"><button type="button" class="adt_cart__btn" data-action="revisado">' +
                        'Motivo revisado: registrar la captura <i class="fa fa-arrow-down" aria-hidden="true"></i></button></div>'
                    : '<p class="adt_cap__muted">' + icono('info') + 'Solo un capturador puede registrar la captura.</p>';
            }
            return html;
        },

        // --- Formularios -----------------------------------------------------

        _campo: function (label, control, ayuda, ancho) {
            return '<label class="adt_cap__campo' + (ancho ? ' is-wide' : '') + '"><span class="adt_cap__campo-label">' + esc(label) + '</span>' +
                control + (ayuda ? '<span class="adt_cap__campo-ayuda">' + esc(ayuda) + '</span>' : '') + '</label>';
        },

        _input: function (name, tipo, extra) {
            var v = this.form.valores[name];
            return '<input class="adt_cap__input" type="' + tipo + '" data-campo="' + name + '" value="' + esc(v === null || v === undefined ? '' : v) +
                '"' + (extra || '') + '/>';
        },

        _textarea: function (name, placeholder) {
            return '<textarea class="adt_cap__input" rows="3" data-campo="' + name + '" placeholder="' + esc(placeholder || '') + '">' +
                esc(this.form.valores[name] || '') + '</textarea>';
        },

        _select: function (name, opciones, vacio) {
            var v = this.form.valores[name];
            return '<select class="adt_cap__input" data-campo="' + name + '">' + (vacio ? '<option value="">' + esc(vacio) + '</option>' : '') +
                opciones.map(function (o) {
                    return '<option value="' + esc(o[0]) + '"' + (o[0] === v ? ' selected="selected"' : '') + '>' + esc(o[1]) + '</option>';
                }).join('') + '</select>';
        },

        // Opciones grandes (tarjetas) para las decisiones de cada paso.
        _opciones: function (name, opciones) {
            var v = this.form.valores[name];
            return '<div class="adt_cap__opciones" role="radiogroup">' + opciones.map(function (o) {
                var on = o.valor === v;
                return '<button type="button" role="radio" aria-checked="' + on + '" class="adt_cap__opcion' + (on ? ' is-on' : '') +
                    (o.peligro ? ' is-peligro' : '') + '" data-opcion="' + name + '" data-valor="' + esc(String(o.valor)) + '">' +
                    '<i class="fa ' + o.icono + '" aria-hidden="true"></i><span><strong>' + esc(o.titulo) + '</strong>' +
                    '<small>' + esc(o.texto) + '</small></span></button>';
            }).join('') + '</div>';
        },

        _archivo: function (clave, label, multiple, accept) {
            var lista = this.form.archivos[clave] || [];
            return '<div class="adt_cap__campo is-wide"><span class="adt_cap__campo-label">' + esc(label) + '</span>' +
                '<label class="adt_cap__file"><i class="fa fa-paperclip" aria-hidden="true"></i>' +
                (multiple ? 'Agregar archivos' : (lista.length ? 'Cambiar archivo' : 'Elegir archivo')) +
                '<input type="file" data-archivo="' + clave + '"' + (multiple ? ' multiple="multiple"' : '') +
                (accept ? ' accept="' + accept + '"' : '') + '/></label>' +
                (lista.length ? '<ul class="adt_cap__files">' + lista.map(function (f, i) {
                    return '<li><i class="fa fa-file-o" aria-hidden="true"></i>' + esc(f.nombre) +
                        '<button type="button" class="adt_cap__link" data-quitar="' + clave + '" data-i="' + i + '" aria-label="Quitar ' +
                        esc(f.nombre) + '"><i class="fa fa-times" aria-hidden="true"></i></button></li>';
                }).join('') + '</ul>' : '') + '</div>';
        },

        _pie: function (accion, texto, peligro) {
            var error = this.form.error[accion];
            return (error ? '<p class="adt_cap__error" role="alert">' + icono('critico') + esc(error) + '</p>' : '') +
                '<div class="adt_cap__acciones"><button type="button" class="adt_cart__btn' + (peligro ? ' adt_cap__btn-peligro' : '') +
                '" data-enviar="' + accion + '">' + esc(texto) + '</button></div>';
        },

        _htmlFormCaptura: function () {
            var v = this.form.valores;
            return '<div class="adt_cap__form">' +
                '<div class="adt_cap__campo is-wide"><span class="adt_cap__campo-label">Tipo de captura</span>' +
                this._opciones('tipo', [
                    {valor: 'inmediata', icono: 'fa-lock', titulo: 'Inmediata', texto: 'La moto queda retenida desde ahora.'},
                    {valor: 'compromiso', icono: 'fa-handshake-o', titulo: 'Compromiso de pago',
                     texto: 'El cliente se compromete a pagar hasta una fecha.'},
                ]) + '</div>' +
                (v.tipo === 'compromiso' ? this._campo('Fecha del compromiso', this._input('compromiso', 'date',
                    ' min="' + moment(this.caso.opciones.hoy).add(1, 'day').format('YYYY-MM-DD') + '"'), 'Debe ser una fecha futura.') : '') +
                '<div class="adt_cap__campo is-wide"><span class="adt_cap__campo-label">¿Se recogió la moto?</span>' +
                this._opciones('recogida', [
                    {valor: true, icono: 'fa-check', titulo: 'Sí, se recogió', texto: 'La moto está en nuestro poder.'},
                    {valor: false, icono: 'fa-times', titulo: 'No se recogió', texto: 'Indica el motivo.'},
                ]) + '</div>' +
                (v.recogida ? '' : this._campo('Motivo por el que no se recogió', this._textarea('motivo_no_recogida'), '', true)) +
                this._campo('Monto de la intervención (S/)', this._input('monto', 'number', ' min="0" step="0.01"'), 'Lo que el cliente paga por la intervención.') +
                this._campo('Comentarios de la captura', this._textarea('comentarios', 'Dónde se capturó, con quién se habló…'), '', true) +
                this._archivo('evidencias', 'Evidencias (fotos o videos)', true, 'image/*,video/*,application/pdf') +
                '</div>' + this._pie('capturar', 'Registrar captura');
        },

        _htmlCapturaHecha: function () {
            var c = this.caso.captura;
            return '<dl class="adt_cap__datos">' +
                dato('Captura', esc(c.numero) + ' · ' + fecha(c.fecha)) +
                dato('Tipo', esc(c.tipo_label) + (c.compromiso ? ' hasta ' + fecha(c.compromiso) : '')) +
                dato('Moto', c.recogida ? 'Recogida' : 'No recogida' + (c.motivo_no_recogida ? ': ' + esc(c.motivo_no_recogida) : '')) +
                dato('Capturador', esc(c.capturador)) +
                dato('Comentarios', esc(c.comentarios)) + '</dl>' +
                this._htmlDocs(c.documentos.capturar, 'Evidencias', 'No se subieron evidencias.');
        },

        _htmlFormCobro: function () {
            var k = this.caso;
            var v = this.form.valores;
            var recordatorio = [];
            if (k.cuotas.length) { recordatorio.push(soles(k.cuotas_total) + ' en cuotas vencidas'); }
            if (k.papeletas_total) { recordatorio.push(soles(k.papeletas_total) + ' en papeletas SAT'); }
            return (recordatorio.length ? '<p class="adt_cap__nota">' + icono('info') + 'Para liberar la moto el cliente también debe ponerse al día: ' +
                    esc(recordatorio.join(' y ')) + '.</p>' : '') +
                '<div class="adt_cap__form">' +
                '<div class="adt_cap__campo is-wide">' + this._opciones('pagar', [
                    {valor: true, icono: 'fa-money', titulo: 'Pagó la intervención', texto: 'Adjunta el voucher.'},
                    {valor: false, icono: 'fa-ban', titulo: 'Exonerar del pago', texto: 'No paga; indica el motivo.'},
                ]) + '</div>' +
                (v.pagar
                    ? this._campo('Monto pagado (S/)', this._input('monto_pago', 'number', ' min="0" step="0.01"')) +
                      this._campo('Fecha de pago', this._input('fecha_pago', 'date', ' max="' + k.opciones.hoy + '"')) +
                      this._campo('N° de voucher u operación', this._input('voucher_numero', 'text')) +
                      this._archivo('voucher', 'Voucher de pago', false, 'image/*,application/pdf')
                    : this._campo('Fecha', this._input('fecha_pago', 'date', ' max="' + k.opciones.hoy + '"')) +
                      this._campo('Motivo de la exoneración', this._textarea('motivo_pago'), '', true)) +
                '</div>' + this._pie('cobrar', v.pagar ? 'Registrar pago' : 'Registrar exoneración');
        },

        _htmlCobroHecho: function () {
            var c = this.caso.captura;
            return '<dl class="adt_cap__datos">' + (c.pagar_monto
                ? dato('Pagado', soles(c.intervencion) + ' · ' + fecha(c.fecha_pago)) + dato('Voucher', esc(c.voucher))
                : dato('Exonerada', fecha(c.fecha_pago)) + dato('Motivo', esc(c.motivo_no_pago))) + '</dl>' +
                (c.pagar_monto ? this._htmlDocs(c.documentos.cobrar, 'Voucher de pago', 'No se adjuntó el voucher.') : '');
        },

        _htmlFormDecision: function () {
            var k = this.caso;
            var c = k.captura;
            var v = this.form.valores;
            if (!k.permisos.supervisor) {
                return '<p class="adt_cap__nota">' + icono('info') + 'Este paso lo realiza un supervisor de captura.</p>';
            }
            var html = '';
            if (!c.pagado) {
                html += '<p class="adt_cap__nota is-atencion">' + icono('atencion') + 'La intervención de ' + soles(c.intervencion) +
                    ' aún no está cobrada.</p>';
            }
            html += '<div class="adt_cap__form"><div class="adt_cap__campo is-wide">' + this._opciones('decision', [
                {valor: 'liberar', icono: 'fa-unlock', titulo: 'Liberar el vehículo', texto: 'El cliente se puso al día o refinanció.'},
                {valor: 'retener', icono: 'fa-gavel', titulo: 'Iniciar disolución del contrato',
                 texto: 'El cliente no continuará: el vehículo se retiene para recolocarlo.', peligro: true},
            ]) + '</div>';
            if (v.decision === 'liberar') {
                html += this._campo('Motivo de la liberación', this._select('liberacion', k.opciones.liberacion, 'Elige…'),
                        v.liberacion === 'pago_papeleta_sat' && c.papeletas_sat
                            ? 'El SAT aún muestra ' + plural(c.papeletas_sat, 'papeleta pendiente', 'papeletas pendientes') +
                              ' (' + soles(c.deuda_sat) + '). Se confirmará en la próxima consulta.' : '') +
                    this._campo('Observaciones', this._textarea('observaciones'), '', true) + '</div>' +
                    this._pie('liberar', 'Liberar vehículo');
            } else if (v.decision === 'retener') {
                html += this._campo('Motivo', this._select('retencion', k.opciones.retencion)) +
                    this._campo('Fecha', this._input('fecha_retencion', 'date', ' max="' + k.opciones.hoy + '"')) +
                    this._campo('Observaciones', this._textarea('notas_retencion'),
                        v.retencion === 'otro' ? 'Obligatorio, mínimo 10 caracteres.' : '', true) + '</div>' +
                    this._pie('disolucion', 'Iniciar disolución', true);
            } else {
                html += '</div>';
            }
            return html;
        },

        _htmlDecisionHecha: function () {
            var c = this.caso.captura;
            if (c.state === 'liberado') {
                return '<dl class="adt_cap__datos">' + dato('Liberado', esc(c.liberacion)) + dato('Supervisor', esc(c.supervisor)) +
                    dato('Observaciones', esc(c.observaciones)) + '</dl>';
            }
            return '<dl class="adt_cap__datos">' + dato('Disolución', esc(c.retencion) + ' · ' + fecha(c.fecha_retencion)) +
                dato('Supervisor', esc(c.supervisor)) + dato('Observaciones', esc(c.notas_retencion)) + '</dl>' +
                (c.documentos.decidir.length ? this._htmlDocs(c.documentos.decidir, 'Apelaciones') : '');
        },

        _htmlFormRecolocar: function () {
            if (!this.caso.permisos.supervisor) {
                return '<p class="adt_cap__nota">' + icono('info') + 'Este paso lo realiza un supervisor de captura.</p>';
            }
            return '<div class="adt_cap__form">' +
                this._archivo('documento', 'Documento de desafiliación', false, 'image/*,application/pdf') +
                this._archivo('evidencia', 'Evidencia de la entrega', false, 'image/*,application/pdf') +
                '</div>' + this._pie('recolocar', 'Recolocar vehículo', true);
        },

        _htmlLateral: function () {
            var k = this.caso;
            var html = '<section class="adt_cap__card adt_cap__gps is-' + (k.vehiculo.gps ? 'ok' : 'atencion') + '"><h4>GPS</h4>' +
                '<p class="adt_cap__gps-estado">' + icono(k.vehiculo.gps ? 'ok' : 'atencion') +
                    (k.vehiculo.gps ? 'GPS activo' : 'Sin GPS activo') + '</p>' +
                (k.vehiculo.gps_chip ? '<p class="adt_cap__sub">Chip ' + esc(k.vehiculo.gps_chip) + '</p>' : '') +
                (k.vehicle_id ? '<button type="button" class="adt_cart__btn adt_cart__btn--ghost adt_cap__full" data-action="ficha">' +
                    '<i class="fa fa-motorcycle" aria-hidden="true"></i>' + (this.enFlota360 ? 'Volver a la ficha del vehículo' : 'Ver detalle en Flota 360') +
                    '</button>' : '') + '</section>';
            if (k.historial.length) {
                html += '<section class="adt_cap__card"><h4>Capturas anteriores</h4><ul class="adt_cap__hist">' + k.historial.map(function (h) {
                    return '<li><button type="button" class="adt_cap__link" data-abrir-captura="' + h.id + '">' + esc(h.numero) + '</button>' +
                        '<span>' + esc(h.estado) + ' · ' + fecha(h.fecha) + '</span></li>';
                }).join('') + '</ul></section>';
            }
            return html;
        },

        // Archivos subidos en un paso: miniatura si es imagen, ícono si no; abrir o descargar.
        _htmlDocs: function (archivos, titulo, vacio) {
            if (!archivos || !archivos.length) {
                return vacio ? '<p class="adt_cap__muted">' + icono('neutral') + esc(vacio) + '</p>' : '';
            }
            return '<div class="adt_cap__docs-grupo"><h5><i class="fa fa-paperclip" aria-hidden="true"></i>' + esc(titulo) +
                ' <span class="adt_cap__count">' + archivos.length + '</span></h5><ul class="adt_cap__docs">' + archivos.map(function (a) {
                    return '<li><a href="' + a.url + '" target="_blank" rel="noopener" title="Abrir ' + esc(a.nombre) + '">' +
                        (a.imagen ? '<img src="' + a.miniatura + '" alt="" loading="lazy"/>'
                            : '<span class="adt_cap__doc-ico"><i class="fa ' + (/pdf/.test(a.mimetype || '') ? 'fa-file-pdf-o'
                                : (/video/.test(a.mimetype || '') ? 'fa-file-video-o' : 'fa-file-o')) + '" aria-hidden="true"></i></span>') +
                        '<span class="adt_cap__doc-name">' + esc(a.nombre) + '</span></a>' +
                        '<a class="adt_cap__doc-dl" href="' + a.descarga + '" title="Descargar" aria-label="Descargar ' + esc(a.nombre) + '">' +
                            '<i class="fa fa-download" aria-hidden="true"></i></a></li>';
                }).join('') + '</ul></div>';
        },

        // ------------------------------------------------------------------
        // Envío de cada paso
        // ------------------------------------------------------------------

        _envio: function (accion) {
            var k = this.caso;
            var v = this.form.valores;
            var a = this.form.archivos;
            var id = k.captura && k.captura.id;
            var uno = function (clave) { return (a[clave] || [])[0] || null; };
            switch (accion) {
            case 'capturar':
                if (v.tipo === 'compromiso' && !v.compromiso) { return {error: 'Indica la fecha del compromiso de pago.'}; }
                if (!v.recogida && !(v.motivo_no_recogida || '').trim()) { return {error: 'Indica por qué no se recogió la moto.'}; }
                return {
                    metodo: 'captura_registrar', confirmar: '¿Registrar la captura de ' + k.cliente.nombre + '? El vehículo cambiará de estado.',
                    kwargs: {cuenta_id: k.cuenta_id, datos: {
                        tipo: v.tipo, compromiso: v.compromiso, recogida: v.recogida, motivo_no_recogida: v.motivo_no_recogida,
                        monto: v.monto, comentarios: v.comentarios, evidencias: a.evidencias || []}},
                };
            case 'cobrar':
                if (v.pagar && (!v.voucher_numero || !uno('voucher'))) { return {error: 'Indica el N° de voucher y adjunta el voucher.'}; }
                if (!v.pagar && !(v.motivo_pago || '').trim()) { return {error: 'Indica el motivo de la exoneración.'}; }
                return {metodo: 'captura_cobrar', kwargs: {captura_id: id, datos: {
                    pagar: v.pagar, monto: v.monto_pago, fecha: v.fecha_pago, voucher_numero: v.voucher_numero,
                    voucher: uno('voucher'), motivo: v.motivo_pago}}};
            case 'liberar':
                if (!v.liberacion) { return {error: 'Elige el motivo de la liberación.'}; }
                return {metodo: 'captura_liberar', confirmar: '¿Liberar el vehículo ' + (k.vehiculo.placa || '') + '?',
                        kwargs: {captura_id: id, tipo: v.liberacion, observaciones: v.observaciones}};
            case 'disolucion':
                return {metodo: 'captura_disolucion',
                        confirmar: '¿Iniciar la disolución del contrato de ' + k.cliente.nombre + '? Esta acción es irreversible.',
                        kwargs: {captura_id: id, motivo: v.retencion, fecha: v.fecha_retencion, notas: v.notas_retencion}};
            case 'recolocar':
                if (!uno('documento') || !uno('evidencia')) { return {error: 'Adjunta la desafiliación y la evidencia de la entrega.'}; }
                return {metodo: 'captura_recolocar',
                        confirmar: '¿Recolocar el vehículo? La cuenta ' + k.cuenta.referencia + ' pasará a cancelada.',
                        kwargs: {captura_id: id, documento: uno('documento'), evidencia: uno('evidencia')}};
            }
            return null;
        },

        _onEnviar: function (ev) {
            var self = this;
            var accion = ev.currentTarget.getAttribute('data-enviar');
            var envio = this._envio(accion);
            if (!envio) { return; }
            this.form.error = {};
            if (envio.error) {
                this.form.error[accion] = envio.error;
                this._render();
                return;
            }
            var enviar = function () {
                var $btn = self.$('[data-enviar="' + accion + '"]').prop('disabled', true).addClass('is-busy');
                return self._llamar(envio.metodo, envio.kwargs).then(function (res) {
                    self.displayNotification({type: 'success', title: 'Capturas', message: 'Listo: paso registrado.'});
                    var captura = (res && res.captura_id) || (self.caso.captura && self.caso.captura.id);
                    self.trigger_up('captura_cambio');
                    return self._recargarCaso(captura ? {captura_id: captura} : {cuenta_id: self.caso.cuenta_id});
                }).guardedCatch(function (err) {
                    if (err && err.event) { err.event.preventDefault(); }
                    $btn.prop('disabled', false).removeClass('is-busy');
                    self.form.error[accion] = self._error(err);
                    self._render();
                });
            };
            if (envio.confirmar) {
                Dialog.confirm(this, envio.confirmar, {confirm_callback: enviar});
            } else {
                enviar();
            }
        },

        // ------------------------------------------------------------------
        // Eventos
        // ------------------------------------------------------------------

        _onCampo: function (ev) {
            var name = ev.currentTarget.getAttribute('data-campo');
            var valor = ev.currentTarget.value;
            this.form.valores[name] = ev.currentTarget.type === 'number' ? (valor === '' ? '' : parseFloat(valor)) : valor;
            // Los selects que muestran u ocultan campos o ayudas vuelven a dibujar el formulario.
            if (ev.type === 'change' && _.contains(['liberacion', 'retencion'], name)) {
                this._render();
            }
        },

        _onOpcion: function (ev) {
            var name = ev.currentTarget.getAttribute('data-opcion');
            var valor = ev.currentTarget.getAttribute('data-valor');
            this.form.valores[name] = valor === 'true' ? true : (valor === 'false' ? false : valor);
            this.form.error = {};
            this._render();
        },

        _onArchivo: function (ev) {
            var self = this;
            var clave = ev.currentTarget.getAttribute('data-archivo');
            var multiple = ev.currentTarget.multiple;
            var files = _.toArray(ev.currentTarget.files);
            Promise.all(files.map(leerArchivo)).then(function (leidos) {
                self.form.archivos[clave] = multiple ? (self.form.archivos[clave] || []).concat(leidos) : leidos.slice(0, 1);
                self.form.error = {};
                self._render();
            }).catch(function (err) {
                self.displayNotification({type: 'danger', title: 'Archivo', message: err.message});
            });
        },

        _onQuitarArchivo: function (ev) {
            var clave = ev.currentTarget.getAttribute('data-quitar');
            var i = parseInt(ev.currentTarget.getAttribute('data-i'), 10);
            this.form.archivos[clave].splice(i, 1);
            this._render();
        },

        _onRevisado: function () {
            this.form.revisado = true;
            this._render();
        },

        _onDecidirSinCobro: function () {
            this.form.decidirSinCobro = true;
            this._render();
        },

        _onPrioridad: function (ev) {
            var self = this;
            var prioridad = ev.currentTarget.getAttribute('data-prioridad');
            this._llamar('captura_prioridad', {cuenta_id: this.caso.cuenta_id, prioridad: prioridad}).then(function () {
                self.caso.cuenta.prioridad = prioridad;
                self._render();
                self.trigger_up('captura_cambio');
            }).guardedCatch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                self.displayNotification({type: 'danger', title: 'Prioridad', message: self._error(err)});
            });
        },

        _onCancelarCaptura: function () {
            var self = this;
            var c = this.caso.captura;
            Dialog.confirm(this, '¿Cancelar la captura ' + c.numero + '? Úsalo solo si se registró por error.', {
                confirm_callback: function () {
                    return self._llamar('captura_cancelar', {captura_id: c.id}).then(function () {
                        self.trigger_up('captura_cambio');
                        return self._recargarCaso({captura_id: c.id});
                    }).guardedCatch(function (err) {
                        if (err && err.event) { err.event.preventDefault(); }
                        self.displayNotification({type: 'danger', title: 'Capturas', message: self._error(err)});
                    });
                },
            });
        },

        _onFicha: function (ev) {
            this.trigger_up('captura_ficha', {
                vehicle_id: this.caso.vehicle_id,
                tab: ev.currentTarget.getAttribute('data-tab') || (this.caso.captura ? 'capturas' : 'cronograma'),
            });
        },

        _onAbrirCaptura: function (ev) {
            this._recargarCaso({captura_id: parseInt(ev.currentTarget.getAttribute('data-abrir-captura'), 10)});
        },

        _onTecla: function (ev) {
            if (ev.key === 'Escape' && !$('.modal:visible').length) {
                this._onVolver();
            }
        },

        _onVolver: function () {
            this.trigger_up('captura_cerrada');
        },
    });

    // Abre y cierra el drawer de un caso en cualquier pantalla (tablero o ficha de Flota 360).
    var AbreCaso = {
        _abrirCaso: function (kwargs, opciones) {
            var self = this;
            this._cerrarCasoWidget();
            var caso = this._casoCaptura = new CasoCaptura(this, kwargs, opciones);
            return caso.appendTo(this.$el).guardedCatch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                if (self._casoCaptura === caso) {
                    self._cerrarCasoWidget();
                }
                self.displayNotification({type: 'danger', title: 'Capturas', message: errorTexto(err)});
            });
        },

        _cerrarCasoWidget: function () {
            if (this._casoCaptura) {
                this._casoCaptura.destroy();
                this._casoCaptura = null;
            }
        },
    };

    var Capturas = AbstractAction.extend(AbreCaso, {
        template: 'adt_flota_360.Capturas',
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-etapa]': '_onEtapa',
            'click [data-origen]': '_onOrigen',
            'click [data-action="urgentes"]': '_onUrgentes',
            'input [data-ref="buscar"]': '_onBuscar',
            'click [data-abrir-cuenta]': '_onAbrirCaso',
            'click [data-abrir-captura]': '_onAbrirCaso',
            'keydown tr[data-fila]': '_onFilaTecla',
        },

        custom_events: _.extend({}, AbstractAction.prototype.custom_events, {
            captura_cambio: '_onCapturaCambio',
            captura_cerrada: '_onCapturaCerrada',
            captura_ficha: '_onCapturaFicha',
        }),

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var params = (action && action.params) || {};
            this.etapa = params.etapa || 'por_capturar';
            this.origen = null;
            this.urgentes = false;
            this.buscar = '';
            this.data = null;
            this._abrir = params.captura_id ? {captura_id: params.captura_id}
                : (params.cuenta_id ? {cuenta_id: params.cuenta_id} : null);
            this._seq = 0;
            this._buscarDiferido = _.debounce(this._recargar.bind(this), 300);
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._render();
                if (self._abrir) {
                    self._abrirCaso(self._abrir);
                }
            });
        },

        destroy: function () {
            this._buscarDiferido.cancel();
            return this._super.apply(this, arguments);
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        _error: errorTexto,

        _llamar: function (method, kwargs) {
            return llamar(this, method, kwargs);
        },

        // ------------------------------------------------------------------
        // Tablero
        // ------------------------------------------------------------------

        _load: function () {
            var self = this;
            var seq = ++this._seq;
            return this._llamar('capturas_tablero', {
                etapa: this.etapa, origen: this.origen, buscar: this.buscar, urgentes: this.urgentes,
            }).then(function (data) {
                if (seq === self._seq) {
                    self.data = data;
                }
            });
        },

        _recargar: function () {
            var self = this;
            this.$el.addClass('is-loading');
            return this._load().then(function () {
                self.$el.removeClass('is-loading');
                self._render();
            }).guardedCatch(function (err) {
                self.$el.removeClass('is-loading');
                if (err && err.event) { err.event.preventDefault(); }
                self.displayNotification({type: 'danger', title: 'Capturas', message: self._error(err)});
            });
        },

        _render: function () {
            var d = this.data;
            if (!d.disponible) {
                this._ref('subtitle').text('');
                this._ref('steps').empty();
                this._ref('body').html('<div class="adt_cart__empty">El módulo de capturas (adt_captura) no está instalado ' +
                    'o no tienes acceso.</div>');
                return;
            }
            var activas = _.reduce(d.etapas, function (a, e) { return a + (e.key === 'cerradas' ? 0 : e.n); }, 0);
            this._ref('subtitle').text(plural(activas, 'caso abierto', 'casos abiertos') +
                ' · Las cuotas vencidas y las papeletas SAT pendientes entran solas a "Por capturar"');
            this._renderEtapas();
            this._renderLista();
        },

        _renderEtapas: function () {
            var self = this;
            // Mismo ancho para todas; las del proceso van numeradas y unidas por una flecha.
            this._ref('steps').html('<ol class="adt_cap__steps-list">' + this.data.etapas.map(function (e, i) {
                var activa = e.key === self.etapa;
                var cerradas = e.key === 'cerradas';
                return '<li class="' + (cerradas ? 'is-cerradas' : 'is-proceso') + '"><button type="button" class="adt_cap__step' +
                    (activa ? ' is-active' : '') + (e.n ? '' : ' is-zero') + '" data-etapa="' + e.key + '" aria-pressed="' + activa + '">' +
                    '<span class="adt_cap__step-num">' + (cerradas ? '<i class="fa ' + e.icon + '" aria-hidden="true"></i>' : i + 1) +
                    '</span><span class="adt_cap__step-txt"><span class="adt_cap__step-label">' + esc(e.label) + '</span>' +
                    '<span class="adt_cap__step-n">' + plural(e.n, 'caso', 'casos') + '</span></span></button></li>';
            }).join('') + '</ol>');
        },

        _renderLista: function () {
            var d = this.data;
            var etapa = _.findWhere(d.etapas, {key: d.etapa});
            var html = '<section class="adt_cap__guia"><i class="fa ' + etapa.icon + '" aria-hidden="true"></i><div>' +
                '<strong>' + esc(etapa.label) + '</strong><p>' + esc(etapa.desc) + '</p></div></section>';
            html += '<div class="adt_cap__toolbar">' +
                '<label class="adt_cap__search"><i class="fa fa-search" aria-hidden="true"></i>' +
                '<input type="search" data-ref="buscar" placeholder="Cliente, DNI, placa o cuenta" value="' + esc(this.buscar) + '"/></label>';
            if (d.etapa === 'por_capturar') {
                html += '<div class="adt_cart__facet-chips">' +
                    this._chipFiltro('data-origen', 'todos', this.origen === null, 'Todos',
                        _.reduce(d.origenes, function (a, o) { return a + o.n; }, 0)) +
                    d.origenes.map(function (o) {
                        return this._chipFiltro('data-origen', o.id, this.origen === o.id, o.name, o.n);
                    }, this).join('') +
                    '<button type="button" class="adt_cart__fchip' + (this.urgentes ? ' is-active' : '') +
                        '" data-action="urgentes" aria-pressed="' + this.urgentes + '"><i class="adt_cart__fchip-dot is-critico" aria-hidden="true"></i>' +
                        'Urgentes<span class="adt_cart__fchip-n">' + entero(d.urgentes_n) + '</span></button></div>';
            }
            html += '</div>';
            html += d.items.length ? this._htmlTabla(d.etapa, d.items) :
                '<div class="adt_cart__empty"><i class="fa fa-check-circle" aria-hidden="true"></i> ' +
                (this.buscar || this.origen || this.urgentes ? 'Nada coincide con la búsqueda.' : 'No hay casos en esta etapa.') + '</div>';
            if (d.items.length >= d.limite) {
                html += '<p class="adt_cap__muted">Se muestran los primeros ' + entero(d.limite) + '. Usa el buscador para encontrar otros.</p>';
            }
            var $buscar = this._ref('buscar');
            var foco = $buscar.length && $buscar.is(':focus');
            this._ref('body').html(html);
            if (foco) {
                var input = this._ref('buscar')[0];
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            }
        },

        _chipFiltro: function (attr, valor, activo, texto, n) {
            return '<button type="button" class="adt_cart__fchip' + (activo ? ' is-active' : '') + (!n && !activo ? ' is-zero' : '') +
                '" ' + attr + '="' + esc(valor) + '" aria-pressed="' + activo + '">' + esc(texto) +
                '<span class="adt_cart__fchip-n">' + entero(n) + '</span></button>';
        },

        _htmlTabla: function (etapa, items) {
            var accion = ETAPA_ACCION[etapa];
            var cabecera, filas;
            if (etapa === 'por_capturar') {
                cabecera = '<th>Prioridad</th><th>Cliente</th><th>Vehículo</th><th>Motivo</th><th class="is-num">Cuotas vencidas</th>' +
                    '<th class="is-num">Papeletas SAT</th><th>Situación</th><th></th>';
                filas = items.map(function (it) {
                    var situacion = (it.gps ? '' : chip('Sin GPS', 'atencion')) +
                        (it.tvs ? chip('En taller TVS · ' + plural(it.tvs_dias, 'día', 'días'), 'atencion') : '');
                    return '<tr class="is-' + it.nivel + '" data-fila tabindex="0" data-abrir-cuenta="' + it.cuenta_id + '">' +
                        '<td>' + chipPrioridad(it.prioridad) + '</td>' +
                        '<td><span class="adt_cap__strong">' + esc(it.cliente) + '</span>' +
                            '<span class="adt_cap__sub">' + esc(_.compact([it.documento, it.telefono]).join(' · ') || '—') + '</span></td>' +
                        '<td><span class="adt_cap__strong">' + esc(it.placa || 'Sin placa') + '</span>' +
                            '<span class="adt_cap__sub">' + esc(it.cuenta) + (it.asesor ? ' · ' + esc(it.asesor) : '') + '</span></td>' +
                        '<td>' + chip(ORIGEN_TEXTO[it.origen] || it.origen, it.origen === 'ambos' ? 'critico' : (it.origen === 'papeleta' ? 'info' : 'atencion')) + '</td>' +
                        '<td class="is-num">' + (it.cuotas ? '<span class="adt_cap__strong">' + soles(it.monto_vencido) + '</span>' +
                            '<span class="adt_cap__sub">' + plural(it.cuotas, 'cuota', 'cuotas') + ' · ' + plural(it.dias_mora, 'día', 'días') + '</span>' : '—') + '</td>' +
                        '<td class="is-num">' + (it.papeletas_sat ? '<span class="adt_cap__strong">' + soles(it.deuda_sat) + '</span>' +
                            '<span class="adt_cap__sub">' + plural(it.papeletas_sat, 'papeleta', 'papeletas') + ' · desde ' + fecha(it.fecha_papeleta_sat) + '</span>' : '—') + '</td>' +
                        '<td>' + (situacion || '<span class="adt_cap__muted">—</span>') + '</td>' +
                        '<td class="is-num"><button type="button" class="adt_cart__btn adt_cap__go" data-abrir-cuenta="' + it.cuenta_id + '">' +
                            esc(accion) + ' <i class="fa fa-angle-right" aria-hidden="true"></i></button></td></tr>';
                });
            } else {
                cabecera = '<th>Prioridad</th><th>Captura</th><th>Cliente</th><th>Vehículo</th><th>Tipo</th><th class="is-num">Intervención</th>' +
                    '<th class="is-num">Papeletas SAT</th><th>' + (etapa === 'cerradas' ? 'Cierre' : 'Situación') + '</th><th></th>';
                filas = items.map(function (it) {
                    var pago = it.pagado ? chip(it.exonerado ? 'Exonerada' : 'Pagada', 'ok') : chip('Por cobrar', 'critico');
                    var situacion = etapa === 'cerradas' ? chip(it.estado + (it.cierre ? ' · ' + it.cierre : ''), it.state === 'cancelado' ? 'neutral' : 'ok')
                        : (it.retraso ? chip('Compromiso vencido hace ' + plural(it.retraso, 'día', 'días'), 'critico') : '') +
                          (it.recogida ? '' : chip('Moto no recogida', 'atencion')) + (it.estado && etapa === 'disolucion' ? chip(it.estado, 'critico') : '');
                    return '<tr class="is-' + it.nivel + '" data-fila tabindex="0" data-abrir-captura="' + it.captura_id + '">' +
                        '<td>' + (etapa === 'cerradas' ? '<span class="adt_cap__muted">—</span>' : chipPrioridad(it.prioridad)) + '</td>' +
                        '<td><span class="adt_cap__strong adt_cap__mono">' + esc(it.numero) + '</span>' +
                            '<span class="adt_cap__sub">' + fecha(it.fecha) + ' · hace ' + plural(it.dias, 'día', 'días') + '</span></td>' +
                        '<td><span class="adt_cap__strong">' + esc(it.cliente) + '</span><span class="adt_cap__sub">' + esc(it.cuenta) + '</span></td>' +
                        '<td><span class="adt_cap__strong">' + esc(it.placa || 'Sin placa') + '</span></td>' +
                        '<td>' + esc(it.tipo) + (it.compromiso ? '<span class="adt_cap__sub">Hasta ' + fecha(it.compromiso) + '</span>' : '') + '</td>' +
                        '<td class="is-num"><span class="adt_cap__strong">' + soles(it.intervencion) + '</span>' + pago + '</td>' +
                        '<td class="is-num">' + (it.papeletas_sat ? '<span class="adt_cap__strong">' + soles(it.deuda_sat) + '</span>' +
                            '<span class="adt_cap__sub">' + plural(it.papeletas_sat, 'pendiente', 'pendientes') + '</span>' : '—') + '</td>' +
                        '<td>' + (situacion || '<span class="adt_cap__muted">—</span>') + '</td>' +
                        '<td class="is-num"><button type="button" class="adt_cart__btn adt_cap__go' + (etapa === 'cerradas' ? ' adt_cart__btn--ghost' : '') +
                            '" data-abrir-captura="' + it.captura_id + '">' + esc(accion) + ' <i class="fa fa-angle-right" aria-hidden="true"></i></button></td></tr>';
                });
            }
            return '<div class="adt_cap__table-wrap"><table class="adt_cap__table"><thead><tr>' + cabecera +
                '</tr></thead><tbody>' + filas.join('') + '</tbody></table></div>';
        },

        // ------------------------------------------------------------------
        // Eventos
        // ------------------------------------------------------------------

        _onCapturaCambio: function () {
            var self = this;
            this._load().then(function () {
                self._renderEtapas();
                self._renderLista();
            });
        },

        _onCapturaCerrada: function () {
            this._cerrarCasoWidget();
            this._recargar();
        },

        _onCapturaFicha: function (ev) {
            this.do_action({
                type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                params: {vehicle_id: ev.data.vehicle_id, tab: ev.data.tab},
            });
        },

        _onAbrirCaso: function (ev) {
            ev.stopPropagation();
            var el = ev.currentTarget;
            var captura = el.getAttribute('data-abrir-captura');
            this._abrirCaso(captura ? {captura_id: parseInt(captura, 10)}
                : {cuenta_id: parseInt(el.getAttribute('data-abrir-cuenta'), 10)});
        },

        _onFilaTecla: function (ev) {
            if (ev.target !== ev.currentTarget) { return; }  // Enter sobre el botón de la fila ya lo abre
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onAbrirCaso(ev);
            }
        },

        _onEtapa: function (ev) {
            this.etapa = ev.currentTarget.getAttribute('data-etapa');
            this.origen = null;
            this.urgentes = false;
            this.buscar = '';
            this._recargar();
        },

        _onOrigen: function (ev) {
            var v = ev.currentTarget.getAttribute('data-origen');
            this.origen = v === 'todos' ? null : v;
            this._recargar();
        },

        _onUrgentes: function () {
            this.urgentes = !this.urgentes;
            this._recargar();
        },

        _onBuscar: function (ev) {
            this.buscar = ev.currentTarget.value;
            this._buscarDiferido();
        },

        _onRefresh: function () {
            return this._recargar();
        },
    });

    // Ficha del vehículo en Flota 360: las acciones tipo "captura" abren el mismo drawer.
    Flota360.include(_.extend({}, AbreCaso, {
        custom_events: _.extend({}, Flota360.prototype.custom_events, {
            captura_cambio: '_onCapturaCambio',
            captura_cerrada: '_onCapturaCerrada',
            captura_ficha: '_onCapturaFicha',
        }),

        _ejecutar: function (a) {
            if (a && a.tipo === 'captura') {
                return this._abrirCaso(a.captura_id ? {captura_id: a.captura_id} : {cuenta_id: a.cuenta_id}, {enFlota360: true});
            }
            return this._super.apply(this, arguments);
        },

        _onCapturaCambio: function () {
            this._casoCambio = true;
        },

        _onCapturaCerrada: function () {
            this._cerrarCasoWidget();
            // La ficha se refresca al cerrar, no en cada paso: así no se redibuja detrás del drawer.
            if (this._casoCambio) {
                this._casoCambio = false;
                this._recargar();
            }
        },

        _onCapturaFicha: function (ev) {
            this._onCapturaCerrada();
            this._irA(ev.data.tab);
        },

        // Clic en una captura de la ficha: abre directamente su gestión paso a paso (el mismo
        // drawer que «Gestionar captura»), sin pasar por la hoja de detalle.
        _onCaptura: function (ev) {
            var id = parseInt(ev.currentTarget.getAttribute('data-cap'), 10);
            return this._abrirCaso({captura_id: id}, {enFlota360: true});
        },

        // Con el drawer de la captura abierto, Escape lo cierra a él y no a la ficha.
        _onGlobalKey: function () {
            if (this._casoCaptura) {
                return;
            }
            return this._super.apply(this, arguments);
        },
    }));

    core.action_registry.add('adt_flota_360_capturas', Capturas);
    return {Capturas: Capturas, CasoCaptura: CasoCaptura};
});
