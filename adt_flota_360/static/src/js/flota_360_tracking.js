odoo.define('adt_flota_360.Tracking', function (require) {
    'use strict';

    /**
     * Tracking de motos en una sola vista (Flota 360 › 5). Todo se dibuja desde JS,
     * sin plantillas QWeb, con el sistema visual de Flota 360 (.adt_cart / .adt_cap).
     *
     *   · Indicadores: motos en Gambeta, Base, Fibra (por taller) y Base con fibra,
     *     más el estado de la placa. Los de taller y placa filtran el tablero.
     *   · Tablero por etapa: cada tarjeta avanza la logística y, en la misma tarjeta,
     *     inicia el trámite de placa.
     *   · Detalle de la moto (CasoTracking, drawer): logística y placa en paralelo,
     *     cada una con su paso actual y su acción, más el historial.
     *   · Configuración (ConfigTracking, drawer): etapas, talleres de fibra y
     *     parámetros de placa (solo administradores del tracking).
     *
     * Las reglas son las de adt_tracking_moto y adt_tramite_placa (adt.flota360.tracking_*).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var Widget = require('web.Widget');
    var Flota360 = require('adt_flota_360.Flota360');

    var esc = _.escape;
    var MAX_ARCHIVO = 10 * 1024 * 1024;
    var TITULO = 'Tracking de motos';
    var NIVEL_ICONO = {critico: 'fa-exclamation-circle', atencion: 'fa-clock-o', ok: 'fa-check-circle',
                       info: 'fa-info-circle', neutral: 'fa-minus-circle'};

    // ------------------------------------------------------------------
    // Utilidades
    // ------------------------------------------------------------------

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
    }

    function dias(n) {
        var v = Math.round((n || 0) * 10) / 10;
        return v.toLocaleString('es-PE', {maximumFractionDigits: 1}) + (v === 1 ? ' día' : ' días');
    }

    function fechaHora(f) {
        return f ? moment(f).format('DD/MM/YYYY HH:mm') : '—';
    }

    function fecha(f) {
        return f ? moment(f).format('DD/MM/YYYY') : '—';
    }

    function icono(nivel) {
        return '<i class="fa ' + (NIVEL_ICONO[nivel] || NIVEL_ICONO.neutral) + ' adt_cap__ico is-' + (nivel || 'neutral') +
            '" aria-hidden="true"></i>';
    }

    function chip(texto, nivel, ico) {
        return '<span class="adt_cap__chip is-' + (nivel || 'neutral') + '">' +
            (ico ? '<i class="fa ' + ico + '" aria-hidden="true"></i> ' : '') + esc(texto) + '</span>';
    }

    function dato(label, valor) {
        return valor ? '<div class="adt_cap__dato"><dt>' + esc(label) + '</dt><dd>' + valor + '</dd></div>' : '';
    }

    function placaHtml(placa) {
        return placa ? '<span class="adt_trk__plate">' + esc(placa) + '</span>'
            : '<span class="adt_trk__plate is-none">Sin placa</span>';
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
        return widget._rpc({model: 'adt.flota360', method: method, args: [], kwargs: kwargs || {}}, {shadow: true});
    }

    function silenciar(err) {
        if (err && err.event) { err.event.preventDefault(); }
    }

    // Esqueleto común de los drawers (detalle y configuración).
    var Drawer = Widget.extend({
        className: 'adt_cart adt_cap adt_trk adt_cap__overlay is-drawer-open',
        etiqueta: 'Detalle',

        init: function () {
            this._super.apply(this, arguments);
            this._onTecla = this._onTecla.bind(this);
        },

        start: function () {
            this.$el.html('<div class="adt_cap__backdrop" data-action="cerrar"></div>' +
                '<aside class="adt_cap__drawer" data-ref="drawer" role="dialog" aria-modal="true" aria-label="' +
                esc(this.etiqueta) + '"></aside>');
            this._render();
            document.addEventListener('keydown', this._onTecla);
            this.$('.adt_cap__close').focus();
            return this._super.apply(this, arguments);
        },

        destroy: function () {
            document.removeEventListener('keydown', this._onTecla);
            return this._super.apply(this, arguments);
        },

        _drawer: function () {
            return this.$('[data-ref="drawer"]');
        },

        // Redibuja sin perder la posición del scroll.
        _pintar: function (html) {
            var $d = this._drawer();
            var scroll = $d.scrollTop();
            $d.html(html);
            $d.scrollTop(scroll);
        },

        _cabecera: function (titulo, sub, herramientas) {
            return '<header class="adt_cap__drawer-head"><div class="adt_cap__caso-title"><h2>' + titulo + '</h2>' +
                (sub ? '<p>' + sub + '</p>' : '') + '</div><div class="adt_cap__drawer-tools">' + (herramientas || '') +
                '<button type="button" class="adt_cap__close" data-action="cerrar" aria-label="Cerrar" title="Cerrar (Esc)">' +
                '<i class="fa fa-times" aria-hidden="true"></i></button></div></header>';
        },

        _onTecla: function (ev) {
            if (ev.key === 'Escape' && !$('.modal:visible').length) {
                this._cerrar();
            }
        },

        _cerrar: function () {
            this.trigger_up('trk_drawer_cerrado', {cambio: !!this.cambio});
        },
    });

    // ------------------------------------------------------------------
    // Detalle de una moto
    // ------------------------------------------------------------------

    var CasoTracking = Drawer.extend({
        etiqueta: 'Detalle de la moto',

        events: {
            'click [data-action="cerrar"]': '_cerrar',
            'click [data-action="ficha"]': '_onFicha',
            'click [data-opcion]': '_onOpcion',
            'input [data-campo]': '_onCampo',
            'change [data-campo]': '_onCampo',
            'change [data-archivo]': '_onArchivo',
            'click [data-quitar]': '_onQuitar',
            'click [data-enviar]': '_onEnviar',
        },

        /**
         * @param {Number} trackingId
         * @param {Object} [opciones] enFlota360: abierto desde la ficha del vehículo
         */
        init: function (parent, trackingId, opciones) {
            this._super.apply(this, arguments);
            this.trackingId = trackingId;
            this.enFlota360 = !!(opciones && opciones.enFlota360);
            this.caso = null;
            this.cambio = false;
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._cargar()]);
        },

        _cargar: function () {
            var self = this;
            return llamar(this, 'tracking_caso', {tracking_id: this.trackingId}).then(function (caso) {
                self.caso = caso;
                self.form = {
                    valores: {taller: caso.logistica.taller_id || (caso.opciones.talleres[0] || {}).id || null,
                              placa_paso: 'finalizar', num_placa: (caso.placa.tramite && caso.placa.tramite.num_placa) || '',
                              motivo: '', notas: '', mover_etapa: '', mover_taller: caso.logistica.taller_id || null},
                    archivos: {}, error: {},
                };
            });
        },

        _recargar: function () {
            var self = this;
            this.$el.addClass('is-loading');
            return this._cargar().then(function () {
                self.$el.removeClass('is-loading');
                self._render();
            }).guardedCatch(function (err) {
                silenciar(err);
                self.$el.removeClass('is-loading');
                self.displayNotification({type: 'danger', title: TITULO, message: errorTexto(err)});
            });
        },

        _render: function () {
            var k = this.caso;
            var m = k.moto;
            var sub = esc(_.compact([k.ref, m.chasis && 'Chasis ' + m.chasis]).join(' · ')) + ' ' +
                chip(k.estado, k.estado_global === 'entregado' ? 'ok' : (k.estado_global === 'listo_asignar' ? 'info' : 'neutral')) +
                (k.demorado ? chip('Demorada', 'critico', 'fa-exclamation-triangle') : '');
            var herramientas = k.vehicle_id ? '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-action="ficha">' +
                '<i class="fa fa-motorcycle" aria-hidden="true"></i>' + (this.enFlota360 ? 'Volver a la ficha' : 'Ficha en Flota 360') +
                '</button>' : '';
            this._pintar(this._cabecera(placaHtml(m.placa) + ' ' + esc(_.compact([m.marca, m.modelo || m.nombre]).join(' ')), sub, herramientas) +
                '<div class="adt_cap__drawer-body">' + this._htmlResumen() +
                '<div class="adt_cap__caso"><div class="adt_trk__flujos">' +
                    this._htmlLogistica() + this._htmlPlaca() + this._htmlHistorial() +
                '</div><div class="adt_cap__side">' + this._htmlLateral() + '</div></div></div>');
        },

        // Cuatro cifras para entender la moto de un vistazo.
        _htmlResumen: function () {
            var k = this.caso;
            var l = k.logistica;
            var p = k.placa;
            var tarde = k.demorado;
            var stat = function (label, valor, sub, nivel, ico) {
                return '<div class="adt_trk__stat is-' + (nivel || 'neutral') + '"><span class="adt_trk__stat-label">' +
                    '<i class="fa ' + ico + '" aria-hidden="true"></i>' + esc(label) + '</span><strong>' + valor + '</strong>' +
                    (sub ? '<small>' + sub + '</small>' : '') + '</div>';
            };
            return '<section class="adt_trk__resumen">' +
                stat('Etapa actual', esc(l.etapa_nombre) + (l.taller && l.etapa === 'fibra' ? ' · ' + esc(l.taller) : ''),
                    dias(l.dias_etapa) + ' en la etapa' + (l.sla_dias ? ' · objetivo ' + dias(l.sla_dias) : ''),
                    tarde ? 'critico' : 'info', 'fa-map-marker') +
                stat('Tiempo total', dias(l.dias_totales), 'Desde el recojo', 'neutral', 'fa-hourglass-half') +
                stat('Placa', esc(p.placa || p.estado_label), p.tramite ? esc(p.tramite.ref) +
                    (p.tramite.observaciones ? ' · ' + plural(p.tramite.observaciones, 'observación', 'observaciones') : '') : '',
                    p.nivel, 'fa-id-card-o') +
                stat('Cliente', esc(k.cliente.nombre || 'En stock'), k.cliente.nombre
                    ? (k.cliente.antes_de_tiempo ? 'Asignada antes de estar lista' : 'Asignada ' + fechaHora(k.cliente.asignacion))
                    : 'Sin asignar', k.cliente.antes_de_tiempo ? 'atencion' : (k.cliente.nombre ? 'ok' : 'neutral'), 'fa-user') +
                '</section>';
        },

        _paso: function (n, titulo, estado, ayuda, cuerpo, iconoPaso) {
            var etiqueta = {hecho: 'Hecho', actual: 'Ahora', pendiente: 'Pendiente', alerta: 'Observado'}[estado];
            var clase = estado === 'alerta' ? 'actual is-alerta' : estado;
            return '<li class="adt_cap__paso is-' + clase + '"' + (estado === 'actual' || estado === 'alerta' ? ' aria-current="step"' : '') + '>' +
                '<span class="adt_cap__paso-num">' + (estado === 'hecho' ? '<i class="fa fa-check" aria-hidden="true"></i>'
                    : (iconoPaso ? '<i class="fa ' + iconoPaso + '" aria-hidden="true"></i>' : n)) + '</span>' +
                '<div class="adt_cap__paso-main"><header class="adt_cap__paso-head"><h3>' + esc(titulo) + '</h3>' +
                    '<span class="adt_cap__paso-estado">' + etiqueta + '</span></header>' +
                    (ayuda ? '<p class="adt_cap__paso-ayuda">' + ayuda + '</p>' : '') +
                    (cuerpo ? '<div class="adt_cap__paso-body">' + cuerpo + '</div>' : '') +
                '</div></li>';
        },

        _seccion: function (titulo, ico, chipHtml, contenido) {
            return '<section class="adt_trk__flujo"><header class="adt_trk__flujo-head"><h3><i class="fa ' + ico +
                '" aria-hidden="true"></i>' + esc(titulo) + '</h3>' + (chipHtml || '') + '</header>' + contenido + '</section>';
        },

        // --- Logística --------------------------------------------------------

        _htmlLogistica: function () {
            var self = this;
            var k = this.caso;
            var l = k.logistica;
            var pasos = l.pasos.map(function (p, i) {
                var ayuda;
                var cuerpo = '';
                if (p.estado === 'hecho') {
                    ayuda = esc(_.compact([fechaHora(p.fecha), p.taller, 'estuvo ' + dias(p.dias), p.usuario && 'por ' + p.usuario]).join(' · '));
                } else if (p.estado === 'actual') {
                    ayuda = esc(_.compact(['Desde ' + fechaHora(p.fecha), p.taller, dias(p.dias) + ' aquí',
                        l.sla_dias ? 'objetivo ' + dias(l.sla_dias) : '']).join(' · '));
                    if (k.demorado) {
                        cuerpo += '<p class="adt_cap__nota is-atencion">' + icono('atencion') + 'Superó el tiempo objetivo de la etapa.</p>';
                    }
                    cuerpo += self._htmlSiguiente();
                } else {
                    ayuda = esc(p.descripcion);
                }
                return self._paso(i + 1, p.nombre, p.estado, ayuda, cuerpo, p.estado === 'pendiente' ? p.icon : null);
            });
            return this._seccion('Logística', 'fa-truck', chip(l.etapa_nombre, k.demorado ? 'critico' : 'info'),
                '<ol class="adt_cap__flow">' + pasos.join('') + '</ol>');
        },

        _htmlSiguiente: function () {
            var k = this.caso;
            var s = k.logistica.siguiente;
            if (k.logistica.cerrado) {
                return '<p class="adt_cap__muted">' + icono('ok') + 'Moto entregada: el tracking está cerrado.</p>';
            }
            if (!s) {
                return k.cliente.nombre ? '<p class="adt_cap__muted">' + icono('ok') + 'Logística terminada. Falta ' +
                    (k.placa.estado === 'finalizado' ? 'registrar la entrega al cliente.' : 'la placa para entregarla.') + '</p>'
                    : '<p class="adt_cap__muted">' + icono('info') + 'Lista para asignar a un cliente.</p>';
            }
            if (!k.permisos.editar) {
                return '<p class="adt_cap__muted">' + icono('info') + 'No tienes permiso para mover la moto.</p>';
            }
            var html = '';
            if (s.requiere_taller) {
                html += this._htmlTalleres('taller');
            }
            return html + this._pie('avanzar', s.label, s.icon);
        },

        _htmlTalleres: function (campo) {
            var v = this.form.valores[campo];
            var talleres = this.caso.opciones.talleres;
            if (!talleres.length) {
                return '<p class="adt_cap__nota is-atencion">' + icono('atencion') + 'No hay talleres de fibra activos. ' +
                    'Créalos en Configuración.</p>';
            }
            return '<div class="adt_cap__campo is-wide"><span class="adt_cap__campo-label">¿A qué taller va?</span>' +
                '<div class="adt_trk__talleres" role="radiogroup">' + talleres.map(function (t) {
                    var on = t.id === v;
                    return '<button type="button" role="radio" aria-checked="' + on + '" class="adt_cap__opcion' + (on ? ' is-on' : '') +
                        '" data-opcion="' + campo + '" data-valor="' + t.id + '"><i class="fa fa-wrench" aria-hidden="true"></i>' +
                        '<span><strong>' + esc(t.nombre) + '</strong><small>' + esc(_.compact([t.codigo, t.direccion,
                            t.sla_dias ? 'objetivo ' + dias(t.sla_dias) : '']).join(' · ') || 'Taller de fibra') + '</small></span></button>';
                }).join('') + '</div></div>';
        },

        // --- Placa ------------------------------------------------------------

        _htmlPlaca: function () {
            var k = this.caso;
            var p = k.placa;
            var t = p.tramite;
            if (!p.disponible) {
                return this._seccion('Trámite de placa', 'fa-id-card-o', '',
                    '<p class="adt_cap__muted">' + icono('info') + 'El módulo de trámite de placa no está instalado.</p>');
            }
            var e = p.estado;
            var pasos = [];
            // 1. Iniciar
            pasos.push(this._paso(1, 'Iniciar el trámite', e === 'pendiente' ? 'actual' : 'hecho',
                e === 'pendiente' ? (t && t.dias_sin_iniciar ? 'Sin iniciar hace ' + dias(t.dias_sin_iniciar) + '.' :
                    'Se presenta la documentación de la moto para obtener la placa.')
                    : (t ? esc('Iniciado ' + fechaHora(t.inicio)) : 'La moto ya tenía placa.'),
                e === 'pendiente' ? (k.permisos.editar ? this._pie('placa_iniciar', 'Iniciar trámite de placa', 'fa-play') : '') : ''));
            // 2. En trámite (con observaciones)
            var estado2 = e === 'pendiente' ? 'pendiente' : (e === 'finalizado' ? 'hecho' : (e === 'observado' ? 'alerta' : 'actual'));
            var ayuda2 = '';
            var cuerpo2 = '';
            if (estado2 === 'hecho' && t) {
                ayuda2 = esc(_.compact([dias(t.dias_tramite) + ' de trámite',
                    t.observaciones ? plural(t.observaciones, 'observación', 'observaciones') : 'sin observaciones']).join(' · '));
            } else if (estado2 === 'pendiente') {
                ayuda2 = 'Seguimiento hasta que la placa salga. Si la entidad observa el trámite, se registra aquí.';
            } else if (t) {
                ayuda2 = esc(dias(t.dias_tramite) + ' en trámite' + (t.observaciones ? ' · ' + plural(t.observaciones, 'observación', 'observaciones') : ''));
                cuerpo2 = estado2 === 'alerta' ? this._htmlObservado() : this._htmlFormPlaca();
            }
            pasos.push(this._paso(2, 'En trámite', estado2, ayuda2, cuerpo2));
            // 3. Finalizado
            var cuerpo3 = '';
            if (e === 'finalizado') {
                cuerpo3 = '<div class="adt_trk__placa-ok">' + placaHtml(p.placa || (t && t.num_placa)) +
                    '<span>' + (t && t.fin ? 'Finalizado ' + esc(fechaHora(t.fin)) : 'Placa registrada en la moto') + '</span></div>' +
                    (t && t.tarjeta ? this._htmlDoc(t.tarjeta) : (t ? '<p class="adt_cap__muted">' + icono('neutral') + 'Sin tarjeta de propiedad adjunta.</p>' : '')) +
                    (t && t.notas ? '<p class="adt_cap__muted">' + esc(t.notas) + '</p>' : '') +
                    (t && k.permisos.reabrir_placa ? '<div class="adt_cap__acciones"><button type="button" class="adt_cap__link" ' +
                        'data-enviar="placa_reabrir">Reabrir el trámite</button></div>' : '');
            }
            pasos.push(this._paso(3, 'Placa lista', e === 'finalizado' ? 'hecho' : 'pendiente',
                e === 'finalizado' ? '' : 'El N° de placa y la tarjeta de propiedad pasan a la moto.', cuerpo3));
            return this._seccion('Trámite de placa', 'fa-id-card-o', chip(p.estado_label, p.nivel),
                '<ol class="adt_cap__flow">' + pasos.join('') + '</ol>');
        },

        _htmlObservado: function () {
            var t = this.caso.placa.tramite;
            return '<div class="adt_trk__obs"><strong>' + icono('atencion') + 'Trámite observado' +
                (t.ultima_observacion ? ' el ' + esc(fechaHora(t.ultima_observacion)) : '') + '</strong>' +
                '<p>' + esc(t.motivo || 'Sin motivo registrado.') + '</p></div>' +
                (this.caso.permisos.editar ? this._pie('placa_levantar', 'Observación resuelta: seguir el trámite', 'fa-undo') : '');
        },

        _htmlFormPlaca: function () {
            if (!this.caso.permisos.editar) { return ''; }
            var v = this.form.valores;
            var html = '<div class="adt_cap__campo is-wide">' + this._opciones('placa_paso', [
                {valor: 'finalizar', icono: 'fa-check', titulo: 'Salió la placa', texto: 'Registra el N° y la tarjeta de propiedad.'},
                {valor: 'observar', icono: 'fa-exclamation-triangle', titulo: 'Observaron el trámite', texto: 'Anota el motivo para darle seguimiento.', peligro: true},
            ]) + '</div>';
            if (v.placa_paso === 'observar') {
                return '<div class="adt_cap__form">' + html +
                    this._campo('Motivo de la observación', '<textarea class="adt_cap__input" rows="3" data-campo="motivo" ' +
                        'placeholder="Qué observó la entidad y qué falta">' + esc(v.motivo) + '</textarea>', '', true) +
                    '</div>' + this._pie('placa_observar', 'Registrar observación', 'fa-exclamation-triangle', true);
            }
            return '<div class="adt_cap__form">' + html +
                this._campo('N° de placa', '<input class="adt_cap__input adt_trk__input-placa" type="text" data-campo="num_placa" ' +
                    'maxlength="10" placeholder="ABC-123" value="' + esc(v.num_placa) + '"/>', 'Se guarda en mayúsculas en la moto.') +
                this._archivo('tarjeta', 'Tarjeta de propiedad (opcional)', 'image/*,application/pdf') +
                this._campo('Notas', '<textarea class="adt_cap__input" rows="2" data-campo="notas">' + esc(v.notas) + '</textarea>', '', true) +
                '</div>' + this._pie('placa_finalizar', 'Finalizar trámite', 'fa-check');
        },

        _htmlDoc: function (a) {
            return '<ul class="adt_cap__docs"><li><a href="' + a.url + '" target="_blank" rel="noopener" title="Abrir ' + esc(a.nombre) + '">' +
                (a.imagen ? '<img src="' + a.miniatura + '" alt="" loading="lazy"/>'
                    : '<span class="adt_cap__doc-ico"><i class="fa ' + (/pdf/.test(a.mimetype || '') ? 'fa-file-pdf-o' : 'fa-file-o') +
                      '" aria-hidden="true"></i></span>') +
                '<span class="adt_cap__doc-name">' + esc(a.nombre) + '</span></a>' +
                '<a class="adt_cap__doc-dl" href="' + a.descarga + '" title="Descargar" aria-label="Descargar ' + esc(a.nombre) + '">' +
                '<i class="fa fa-download" aria-hidden="true"></i></a></li></ul>';
        },

        // --- Historial y lateral ----------------------------------------------

        _htmlHistorial: function () {
            var h = this.caso.historial;
            if (!h.length) { return ''; }
            var ico = {logistica: 'fa-truck', placa: 'fa-id-card-o', hito: 'fa-flag'};
            return this._seccion('Historial', 'fa-history', '<span class="adt_cap__count">' + h.length + '</span>',
                '<ol class="adt_trk__timeline">' + h.map(function (l) {
                    return '<li class="is-' + l.flujo + (l.abierta ? ' is-abierta' : '') + '"><i class="fa ' + ico[l.flujo] +
                        '" aria-hidden="true"></i><div><strong>' + esc(l.hasta) + '</strong>' +
                        (l.desde ? '<span class="adt_cap__sub">desde ' + esc(l.desde) + '</span>' : '') +
                        '<span class="adt_cap__sub">' + esc(_.compact([fechaHora(l.fecha), l.flujo_label, l.taller, l.usuario,
                            l.abierta ? 'en curso' : (l.flujo !== 'hito' ? dias(l.dias) : '')]).join(' · ')) + '</span>' +
                        (l.nota ? '<p class="adt_trk__nota">' + esc(l.nota) + '</p>' : '') + '</div></li>';
                }).join('') + '</ol>');
        },

        _htmlLateral: function () {
            var k = this.caso;
            var m = k.moto;
            var c = k.cliente;
            var html = '<section class="adt_cap__card"><h4>Moto</h4><dl class="adt_cap__datos">' +
                dato('Modelo', esc(_.compact([m.marca, m.modelo]).join(' ') || m.nombre)) +
                dato('Chasis', '<span class="adt_cap__mono">' + esc(m.chasis) + '</span>') +
                dato('Motor', m.motor ? '<span class="adt_cap__mono">' + esc(m.motor) + '</span>' : '') +
                dato('Color', esc(m.color)) + dato('Año', esc(m.anio ? String(m.anio) : '')) +
                dato('Factura', esc(m.factura)) + dato('Proveedor', esc(m.proveedor)) + '</dl></section>';
            html += '<section class="adt_cap__card"><h4>Cliente</h4>' + (c.nombre
                ? '<dl class="adt_cap__datos">' + dato('Nombre', esc(c.nombre)) + dato('Documento', esc(c.documento)) +
                  dato('Teléfono', esc(c.telefono)) + dato('Asignada', esc(fechaHora(c.asignacion))) +
                  dato('Entrega', c.entrega ? esc(fecha(c.entrega)) : 'Pendiente') + '</dl>' +
                  (c.antes_de_tiempo ? '<p class="adt_cap__nota is-atencion">' + icono('atencion') + 'Se asignó antes de terminar la logística.</p>' : '')
                : '<p class="adt_cap__muted">' + icono('neutral') + 'En stock: aún no se asigna a un cliente.</p>') + '</section>';
            if (k.permisos.manager && !k.logistica.cerrado) {
                var v = this.form.valores;
                var destino = _.findWhere(k.opciones.etapas, {id: parseInt(v.mover_etapa, 10)});
                html += '<section class="adt_cap__card adt_trk__mover"><h4>Corregir etapa</h4>' +
                    '<p class="adt_cap__muted">Solo administradores: saltar o regresar etapas.</p>' +
                    '<select class="adt_cap__input" data-campo="mover_etapa"><option value="">Elige la etapa…</option>' +
                    k.opciones.etapas.map(function (e) {
                        return e.codigo === k.logistica.etapa ? '' : '<option value="' + e.id + '"' +
                            (String(e.id) === String(v.mover_etapa) ? ' selected="selected"' : '') + '>' + esc(e.nombre) + '</option>';
                    }).join('') + '</select>' +
                    (destino && destino.codigo === 'fibra' ? '<select class="adt_cap__input" data-campo="mover_taller">' +
                        k.opciones.talleres.map(function (t) {
                            return '<option value="' + t.id + '"' + (t.id === parseInt(v.mover_taller, 10) ? ' selected="selected"' : '') + '>' +
                                esc(t.nombre) + '</option>';
                        }).join('') + '</select>' : '') +
                    (this.form.error.mover ? '<p class="adt_cap__error" role="alert">' + esc(this.form.error.mover) + '</p>' : '') +
                    '<button type="button" class="adt_cart__btn adt_cart__btn--ghost adt_cap__full" data-enviar="mover"' +
                    (destino ? '' : ' disabled="disabled"') + '><i class="fa fa-random" aria-hidden="true"></i>Mover</button></section>';
            }
            return html;
        },

        // --- Controles --------------------------------------------------------

        _campo: function (label, control, ayuda, ancho) {
            return '<label class="adt_cap__campo' + (ancho ? ' is-wide' : '') + '"><span class="adt_cap__campo-label">' + esc(label) + '</span>' +
                control + (ayuda ? '<span class="adt_cap__campo-ayuda">' + esc(ayuda) + '</span>' : '') + '</label>';
        },

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

        _archivo: function (clave, label, accept) {
            var lista = this.form.archivos[clave] || [];
            return '<div class="adt_cap__campo"><span class="adt_cap__campo-label">' + esc(label) + '</span>' +
                '<label class="adt_cap__file"><i class="fa fa-paperclip" aria-hidden="true"></i>' +
                (lista.length ? 'Cambiar archivo' : 'Elegir archivo') +
                '<input type="file" data-archivo="' + clave + '"' + (accept ? ' accept="' + accept + '"' : '') + '/></label>' +
                (lista.length ? '<ul class="adt_cap__files">' + lista.map(function (f, i) {
                    return '<li><i class="fa fa-file-o" aria-hidden="true"></i>' + esc(f.nombre) +
                        '<button type="button" class="adt_cap__link" data-quitar="' + clave + '" data-i="' + i + '" aria-label="Quitar ' +
                        esc(f.nombre) + '"><i class="fa fa-times" aria-hidden="true"></i></button></li>';
                }).join('') + '</ul>' : '') + '</div>';
        },

        _pie: function (accion, texto, ico, peligro) {
            var error = this.form.error[accion];
            return (error ? '<p class="adt_cap__error" role="alert">' + icono('critico') + esc(error) + '</p>' : '') +
                '<div class="adt_cap__acciones"><button type="button" class="adt_cart__btn' + (peligro ? ' adt_cap__btn-peligro' : '') +
                '" data-enviar="' + accion + '">' + (ico ? '<i class="fa ' + ico + '" aria-hidden="true"></i>' : '') + esc(texto) + '</button></div>';
        },

        // ------------------------------------------------------------------
        // Envío
        // ------------------------------------------------------------------

        _envio: function (accion) {
            var k = this.caso;
            var v = this.form.valores;
            var id = k.id;
            var s = k.logistica.siguiente;
            var moto = k.moto.chasis || k.ref;
            switch (accion) {
            case 'avanzar':
                if (s.requiere_taller && !v.taller) { return {error: 'Elige el taller de fibra.'}; }
                var taller = s.requiere_taller ? _.findWhere(k.opciones.talleres, {id: v.taller}) : null;
                return {metodo: 'tracking_mover', kwargs: {tracking_id: id, etapa_id: s.etapa_id, taller_id: v.taller},
                        confirmar: '¿' + s.label + (taller ? ' (' + taller.nombre + ')' : '') + '? Moto ' + moto + '.'};
            case 'mover':
                var etapa = _.findWhere(k.opciones.etapas, {id: parseInt(v.mover_etapa, 10)});
                if (!etapa) { return {error: 'Elige la etapa.', clave: 'mover'}; }
                return {metodo: 'tracking_mover', clave: 'mover',
                        kwargs: {tracking_id: id, etapa_id: etapa.id, taller_id: parseInt(v.mover_taller, 10) || null},
                        confirmar: '¿Mover la moto ' + moto + ' a «' + etapa.nombre + '»? Quedará en el historial.'};
            case 'placa_iniciar':
                return {metodo: 'tracking_placa', kwargs: {tracking_id: id, accion: 'iniciar'},
                        confirmar: '¿Iniciar el trámite de placa de la moto ' + moto + '?'};
            case 'placa_levantar':
                return {metodo: 'tracking_placa', kwargs: {tracking_id: id, accion: 'levantar'}};
            case 'placa_observar':
                if (!(v.motivo || '').trim()) { return {error: 'Indica el motivo de la observación.'}; }
                return {metodo: 'tracking_placa', kwargs: {tracking_id: id, accion: 'observar', datos: {motivo: v.motivo}}};
            case 'placa_finalizar':
                if (!(v.num_placa || '').trim()) { return {error: 'Ingresa el N° de placa.'}; }
                return {metodo: 'tracking_placa',
                        kwargs: {tracking_id: id, accion: 'finalizar', datos: {
                            num_placa: v.num_placa, notas: v.notas, tarjeta: (this.form.archivos.tarjeta || [])[0] || null}},
                        confirmar: '¿Finalizar el trámite con la placa ' + v.num_placa.trim().toUpperCase() + '? Se registrará en la moto.'};
            case 'placa_reabrir':
                return {metodo: 'tracking_placa', kwargs: {tracking_id: id, accion: 'reabrir'},
                        confirmar: '¿Reabrir el trámite de placa? Volverá a «En trámite».'};
            }
            return null;
        },

        _onEnviar: function (ev) {
            var self = this;
            var accion = ev.currentTarget.getAttribute('data-enviar');
            var envio = this._envio(accion);
            if (!envio) { return; }
            var clave = envio.clave || accion;
            this.form.error = {};
            if (envio.error) {
                this.form.error[clave] = envio.error;
                this._render();
                return;
            }
            var enviar = function () {
                self.$('[data-enviar="' + accion + '"]').prop('disabled', true).addClass('is-busy');
                return llamar(self, envio.metodo, envio.kwargs).then(function () {
                    self.cambio = true;
                    self.displayNotification({type: 'success', title: TITULO, message: 'Listo: cambio registrado.'});
                    self.trigger_up('trk_cambio');
                    return self._recargar();
                }).guardedCatch(function (err) {
                    silenciar(err);
                    self.form.error[clave] = errorTexto(err);
                    self._render();
                });
            };
            if (envio.confirmar) {
                Dialog.confirm(this, envio.confirmar, {confirm_callback: enviar});
            } else {
                enviar();
            }
        },

        _onCampo: function (ev) {
            var name = ev.currentTarget.getAttribute('data-campo');
            this.form.valores[name] = ev.currentTarget.value;
            if (ev.type === 'change' && name === 'mover_etapa') {
                this.form.error = {};
                this._render();
            }
        },

        _onOpcion: function (ev) {
            var name = ev.currentTarget.getAttribute('data-opcion');
            var valor = ev.currentTarget.getAttribute('data-valor');
            this.form.valores[name] = /^\d+$/.test(valor) ? parseInt(valor, 10) : valor;
            this.form.error = {};
            this._render();
        },

        _onArchivo: function (ev) {
            var self = this;
            var clave = ev.currentTarget.getAttribute('data-archivo');
            Promise.all(_.toArray(ev.currentTarget.files).slice(0, 1).map(leerArchivo)).then(function (leidos) {
                self.form.archivos[clave] = leidos;
                self._render();
            }).catch(function (err) {
                self.displayNotification({type: 'danger', title: 'Archivo', message: err.message});
            });
        },

        _onQuitar: function (ev) {
            var clave = ev.currentTarget.getAttribute('data-quitar');
            this.form.archivos[clave].splice(parseInt(ev.currentTarget.getAttribute('data-i'), 10), 1);
            this._render();
        },

        _onFicha: function () {
            this.trigger_up('trk_ficha', {vehicle_id: this.caso.vehicle_id});
        },
    });

    // ------------------------------------------------------------------
    // Configuración: etapas, talleres de fibra y parámetros de placa
    // ------------------------------------------------------------------

    var SECCIONES_CONFIG = [
        ['etapas', 'Etapas del tracking', 'fa-list-ol'],
        ['talleres', 'Talleres de fibra', 'fa-wrench'],
        ['placa', 'Parámetros de placa', 'fa-id-card-o'],
    ];

    var ConfigTracking = Drawer.extend({
        className: 'adt_cart adt_cap adt_trk adt_trk__config adt_cap__overlay is-drawer-open',
        etiqueta: 'Configuración del tracking',

        events: {
            'click [data-action="cerrar"]': '_cerrar',
            'click [data-seccion]': '_onSeccion',
            'input [data-fila] [data-campo]': '_onCampo',
            'change [data-fila] [data-campo]': '_onCampo',
            'click [data-guardar]': '_onGuardar',
            'click [data-action="nuevo-taller"]': '_onNuevoTaller',
            'click [data-action="cancelar-nuevo"]': '_onCancelarNuevo',
        },

        init: function (parent, seccion) {
            this._super.apply(this, arguments);
            this.seccion = seccion || 'etapas';
            this.cambio = false;
            this.nuevo = false;
            this.editados = {};
            this.errores = {};
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._cargar()]);
        },

        _cargar: function () {
            var self = this;
            return llamar(this, 'tracking_config').then(function (cfg) {
                self.cfg = cfg;
                self.editados = {};
                self.errores = {};
            });
        },

        _render: function () {
            var self = this;
            var tabs = '<nav class="adt_trk__tabs" role="tablist">' + SECCIONES_CONFIG.map(function (s) {
                var on = s[0] === self.seccion;
                return '<button type="button" role="tab" aria-selected="' + on + '" class="adt_trk__tab' + (on ? ' is-active' : '') +
                    '" data-seccion="' + s[0] + '"><i class="fa ' + s[2] + '" aria-hidden="true"></i>' + esc(s[1]) + '</button>';
            }).join('') + '</nav>';
            var cuerpo = {etapas: this._htmlEtapas, talleres: this._htmlTalleres, placa: this._htmlPlaca}[this.seccion].call(this);
            this._pintar(this._cabecera('<i class="fa fa-cog" aria-hidden="true"></i> Configuración',
                'Etapas, talleres de fibra y parámetros de la placa') +
                '<div class="adt_cap__drawer-body">' + tabs +
                (this.cfg.manager ? '' : '<p class="adt_cap__nota is-atencion">' + icono('atencion') +
                    'Solo un administrador del tracking puede guardar cambios.</p>') + cuerpo + '</div>');
        },

        _valor: function (fila, campo, original) {
            var e = this.editados[fila];
            return e && campo in e ? e[campo] : original;
        },

        _input: function (fila, campo, original, tipo, extra) {
            var v = this._valor(fila, campo, original);
            return '<input class="adt_cap__input" type="' + (tipo || 'text') + '" data-campo="' + campo + '" value="' +
                esc(v === null || v === undefined ? '' : v) + '"' + (extra || '') + (this.cfg.manager ? '' : ' disabled="disabled"') + '/>';
        },

        _pieFila: function (fila, texto) {
            var error = this.errores[fila];
            var sucio = !!this.editados[fila];
            return (error ? '<p class="adt_cap__error" role="alert">' + icono('critico') + esc(error) + '</p>' : '') +
                (this.cfg.manager ? '<div class="adt_cap__acciones">' +
                    (fila === 'nuevo' ? '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-action="cancelar-nuevo">Cancelar</button>' : '') +
                    '<button type="button" class="adt_cart__btn" data-guardar="' + fila + '"' +
                    (sucio || fila === 'nuevo' ? '' : ' disabled="disabled"') + '>' + esc(texto || 'Guardar') + '</button></div>' : '');
        },

        _htmlEtapas: function () {
            var self = this;
            return '<p class="adt_trk__intro">Las cuatro etapas son fijas y van siempre en este orden. Puedes cambiar su nombre, ' +
                'la descripción y el tiempo objetivo (SLA): si una moto lo supera, se marca como demorada. Sin SLA, se usa ' +
                'lo que tardaron las motos de los últimos 90 días.</p><ol class="adt_trk__cfg-list">' +
                this.cfg.etapas.map(function (e, i) {
                    var fila = 'etapa-' + e.id;
                    return '<li class="adt_trk__cfg-item" data-fila="' + fila + '"><span class="adt_trk__cfg-num">' + (i + 1) + '</span>' +
                        '<div class="adt_trk__cfg-main"><div class="adt_cap__form">' +
                        self._campoCfg('Nombre', self._input(fila, 'nombre', e.nombre)) +
                        self._campoCfg('SLA (horas)', self._input(fila, 'sla_horas', e.sla_horas, 'number', ' min="0" step="1"'),
                            e.sla_horas ? '≈ ' + dias(e.sla_horas / 24) : '0 = sin objetivo fijo') +
                        self._campoCfg('Descripción', '<textarea class="adt_cap__input" rows="2" data-campo="descripcion"' +
                            (self.cfg.manager ? '' : ' disabled="disabled"') + '>' + esc(self._valor(fila, 'descripcion', e.descripcion)) +
                            '</textarea>', '', true) +
                        '</div>' + self._pieFila(fila) + '</div></li>';
                }).join('') + '</ol>';
        },

        _htmlTalleres: function () {
            var self = this;
            var html = '<p class="adt_trk__intro">Lugares a donde se envían las motos para ponerles la fibra. El SLA del ' +
                'taller reemplaza al de la etapa «Fibra». Un taller archivado ya no aparece para nuevos envíos.</p>';
            if (this.cfg.manager) {
                html += this.nuevo ? '<div class="adt_trk__cfg-item is-nuevo" data-fila="nuevo"><div class="adt_trk__cfg-main">' +
                    '<h4>Nuevo taller de fibra</h4>' + this._formTaller('nuevo', {}) + this._pieFila('nuevo', 'Crear taller') + '</div></div>'
                    : '<button type="button" class="adt_cart__btn adt_trk__nuevo" data-action="nuevo-taller">' +
                      '<i class="fa fa-plus" aria-hidden="true"></i>Agregar taller</button>';
            }
            html += '<ul class="adt_trk__cfg-list">' + this.cfg.talleres.map(function (t) {
                var fila = 'taller-' + t.id;
                return '<li class="adt_trk__cfg-item' + (t.activo ? '' : ' is-archivado') + '" data-fila="' + fila + '">' +
                    '<span class="adt_trk__cfg-num"><i class="fa fa-wrench" aria-hidden="true"></i></span><div class="adt_trk__cfg-main">' +
                    '<div class="adt_trk__cfg-head"><strong>' + esc(t.nombre) + '</strong>' +
                    chip(plural(t.motos, 'moto ahora', 'motos ahora'), t.motos ? 'info' : 'neutral') +
                    (t.activo ? '' : chip('Archivado', 'neutral')) + '</div>' +
                    self._formTaller(fila, t) + self._pieFila(fila) + '</div></li>';
            }).join('') + '</ul>';
            if (!this.cfg.talleres.length) {
                html += '<div class="adt_cart__empty">Aún no hay talleres de fibra.</div>';
            }
            return html;
        },

        _formTaller: function (fila, t) {
            var activo = this._valor(fila, 'activo', fila === 'nuevo' ? true : t.activo);
            return '<div class="adt_cap__form">' +
                this._campoCfg('Nombre', this._input(fila, 'nombre', t.nombre || '')) +
                this._campoCfg('Abreviatura', this._input(fila, 'codigo', t.codigo || '', 'text', ' maxlength="6" placeholder="VES"'),
                    'Se muestra en las tarjetas.') +
                this._campoCfg('Dirección', this._input(fila, 'direccion', t.direccion || '')) +
                this._campoCfg('SLA (horas)', this._input(fila, 'sla_horas', t.sla_horas || 0, 'number', ' min="0" step="1"'),
                    '0 = usa el de la etapa «Fibra».') +
                (fila === 'nuevo' ? '' : '<label class="adt_trk__switch"><input type="checkbox" data-campo="activo"' +
                    (activo ? ' checked="checked"' : '') + (this.cfg.manager ? '' : ' disabled="disabled"') + '/>' +
                    '<span>Activo (disponible para enviar motos)</span></label>') +
                '</div>';
        },

        _htmlPlaca: function () {
            var p = this.cfg.placa;
            if (!p.disponible) {
                return '<div class="adt_cart__empty">El módulo de trámite de placa no está instalado.</div>';
            }
            return '<p class="adt_trk__intro">Cuántos días se muestra un trámite finalizado antes de pasar al historial. ' +
                'El paso se revisa cada hora.</p><div class="adt_trk__cfg-item" data-fila="placa"><div class="adt_trk__cfg-main">' +
                '<div class="adt_cap__form">' +
                this._campoCfg('Días en «Finalizado»', this._input('placa', 'dias_finalizado', p.dias_finalizado, 'number', ' min="0" step="1"'),
                    '0 = pasa al historial en la siguiente revisión.') +
                '</div>' + this._pieFila('placa') + '</div></div>';
        },

        _campoCfg: function (label, control, ayuda, ancho) {
            return '<label class="adt_cap__campo' + (ancho ? ' is-wide' : '') + '"><span class="adt_cap__campo-label">' + esc(label) + '</span>' +
                control + (ayuda ? '<span class="adt_cap__campo-ayuda">' + esc(ayuda) + '</span>' : '') + '</label>';
        },

        _onSeccion: function (ev) {
            this.seccion = ev.currentTarget.getAttribute('data-seccion');
            this.editados = {};
            this.errores = {};
            this.nuevo = false;
            this._render();
            this._drawer().scrollTop(0);
        },

        _onCampo: function (ev) {
            var el = ev.currentTarget;
            var fila = $(el).closest('[data-fila]').attr('data-fila');
            var campo = el.getAttribute('data-campo');
            var e = this.editados[fila] = this.editados[fila] || {};
            e[campo] = el.type === 'checkbox' ? el.checked : el.value;
            // Habilita «Guardar» sin redibujar (no se pierde el foco al escribir).
            this.$('[data-guardar="' + fila + '"]').prop('disabled', false);
            if (el.type === 'checkbox') {
                this._render();
            }
        },

        _datosFila: function (fila) {
            var e = this.editados[fila] || {};
            if (fila === 'placa') {
                return {metodo: 'tracking_config_placa',
                        kwargs: {dias_finalizado: 'dias_finalizado' in e ? e.dias_finalizado : this.cfg.placa.dias_finalizado}};
            }
            var partes = fila.split('-');
            var id = partes[1] ? parseInt(partes[1], 10) : null;
            if (partes[0] === 'etapa') {
                var etapa = _.findWhere(this.cfg.etapas, {id: id});
                return {metodo: 'tracking_config_etapa', kwargs: {etapa_id: id, datos: _.extend(
                    _.pick(etapa, 'nombre', 'descripcion', 'sla_horas'), e)}};
            }
            var t = fila === 'nuevo' ? {} : _.findWhere(this.cfg.talleres, {id: id});
            return {metodo: 'tracking_config_taller', kwargs: {taller_id: id, datos: _.extend(
                fila === 'nuevo' ? {} : _.pick(t, 'nombre', 'codigo', 'direccion', 'sla_horas', 'activo'), e)}};
        },

        _onGuardar: function (ev) {
            var self = this;
            var fila = ev.currentTarget.getAttribute('data-guardar');
            var envio = this._datosFila(fila);
            $(ev.currentTarget).prop('disabled', true).addClass('is-busy');
            llamar(this, envio.metodo, envio.kwargs).then(function () {
                self.cambio = true;
                self.nuevo = fila === 'nuevo' ? false : self.nuevo;
                self.displayNotification({type: 'success', title: 'Configuración', message: 'Cambios guardados.'});
                return self._cargar().then(function () { self._render(); });
            }).guardedCatch(function (err) {
                silenciar(err);
                self.errores[fila] = errorTexto(err);
                self._render();
            });
        },

        _onNuevoTaller: function () {
            this.nuevo = true;
            this.editados.nuevo = {};
            this._render();
            this.$('[data-fila="nuevo"] input').first().focus();
        },

        _onCancelarNuevo: function () {
            this.nuevo = false;
            delete this.editados.nuevo;
            delete this.errores.nuevo;
            this._render();
        },
    });

    // ------------------------------------------------------------------
    // Abrir y cerrar drawers en cualquier pantalla (tablero o ficha de Flota 360)
    // ------------------------------------------------------------------

    var AbreTracking = {
        _abrirTrkDrawer: function (drawer) {
            var self = this;
            this._cerrarTrkDrawer();
            this._trkDrawer = drawer;
            return drawer.appendTo(this.$el).guardedCatch(function (err) {
                silenciar(err);
                if (self._trkDrawer === drawer) {
                    self._cerrarTrkDrawer();
                }
                self.displayNotification({type: 'danger', title: TITULO, message: errorTexto(err)});
            });
        },

        _abrirTracking: function (trackingId, opciones) {
            return this._abrirTrkDrawer(new CasoTracking(this, trackingId, opciones));
        },

        _cerrarTrkDrawer: function () {
            if (this._trkDrawer) {
                this._trkDrawer.destroy();
                this._trkDrawer = null;
            }
        },
    };

    // ------------------------------------------------------------------
    // Pantalla principal
    // ------------------------------------------------------------------

    var TrackingMotos = AbstractAction.extend(AbreTracking, {
        hasControlPanel: false,

        events: {
            'click [data-action="refresh"]': '_onRefresh',
            'click [data-action="config"]': '_onConfig',
            'click [data-kpi-etapa]': '_onKpiEtapa',
            'click [data-taller]': '_onTaller',
            'click [data-placa]': '_onPlaca',
            'click [data-cliente]': '_onCliente',
            'click [data-action="demorados"]': '_onDemorados',
            'click [data-action="limpiar"]': '_onLimpiar',
            'input [data-ref="buscar"]': '_onBuscar',
            'click [data-card]': '_onCard',
            'keydown [data-card]': '_onCardTecla',
            'click [data-avanzar]': '_onAvanzar',
            'click [data-elegir-taller]': '_onElegirTaller',
            'click [data-action="cancelar-taller"]': '_onCancelarTaller',
            'click [data-placa-accion]': '_onPlacaAccion',
        },

        custom_events: _.extend({}, AbstractAction.prototype.custom_events, {
            trk_cambio: '_onTrkCambio',
            trk_drawer_cerrado: '_onTrkCerrado',
            trk_ficha: '_onTrkFicha',
        }),

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var params = (action && action.params) || {};
            this.filtros = {buscar: '', taller_id: null, placa: null, demorados: false, cliente: null};
            this.data = null;
            this.eligiendo = null;  // tarjeta que está eligiendo el taller de fibra
            this._abrir = params.tracking_id ? parseInt(params.tracking_id, 10) : null;
            this._seq = 0;
            this._buscarDiferido = _.debounce(this._recargar.bind(this), 300);
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._load()]);
        },

        start: function () {
            var self = this;
            this.$el.addClass('adt_cart adt_find adt_cap adt_trk');
            this.$el.html('<div class="adt_cart__scroll"><header class="adt_cart__header">' +
                '<div class="adt_find__top"><div class="adt_cart__titlebar"><h1 class="adt_cart__title">' + TITULO + '</h1>' +
                '<p class="adt_cart__subtitle" data-ref="subtitle"></p></div><div class="adt_cart__actions" data-ref="tools"></div></div>' +
                '<section class="adt_trk__kpis" data-ref="kpis" aria-label="Motos por etapa"></section></header>' +
                '<div class="adt_cart__body adt_find__body" data-ref="body"><div class="adt_cart__empty">Cargando…</div></div></div>');
            return this._super.apply(this, arguments).then(function () {
                self._render();
                if (self._abrir) {
                    self._abrirTracking(self._abrir);
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

        _load: function () {
            var self = this;
            var seq = ++this._seq;
            return llamar(this, 'tracking_tablero', {
                buscar: this.filtros.buscar, taller_id: this.filtros.taller_id, placa: this.filtros.placa,
                demorados: this.filtros.demorados, cliente: this.filtros.cliente,
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
                silenciar(err);
                self.$el.removeClass('is-loading');
                self.displayNotification({type: 'danger', title: TITULO, message: errorTexto(err)});
            });
        },

        _render: function () {
            var d = this.data;
            if (!d.disponible) {
                this._ref('subtitle').text('');
                this._ref('tools').empty();
                this._ref('kpis').empty();
                this._ref('body').html('<div class="adt_cart__empty">El tracking de motos (adt_tracking_moto) no está instalado ' +
                    'o no tienes acceso. Pide el permiso «Operación de motos».</div>');
                return;
            }
            this._ref('subtitle').text(plural(d.total, 'moto en proceso', 'motos en proceso') +
                (d.demorados ? ' · ' + plural(d.demorados, 'demorada', 'demoradas') : ''));
            this._ref('tools').html(
                '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-action="refresh">' +
                    '<i class="fa fa-refresh" aria-hidden="true"></i>Actualizar</button>' +
                '<button type="button" class="adt_cart__btn adt_cart__btn--ghost adt_trk__btn-config" data-action="config"' +
                    ' title="Etapas del tracking, talleres de fibra y parámetros de placa">' +
                    '<i class="fa fa-cog" aria-hidden="true"></i>Configuración</button>');
            this._renderKpis();
            this._renderTablero();
        },

        // Indicadores: una tarjeta por etapa; la de fibra con el detalle por taller.
        _renderKpis: function () {
            var d = this.data;
            var f = this.filtros;
            var html = '<ol class="adt_trk__kpi-list">' + d.etapas.map(function (e) {
                var sub = _.compact([e.demorados ? '<span class="is-critico">' + plural(e.demorados, 'demorada', 'demoradas') + '</span>' : '',
                    e.con_cliente ? plural(e.con_cliente, 'con cliente', 'con cliente') : '']).join(' · ');
                var talleres = '';
                if (e.codigo === 'fibra' && d.talleres.length) {
                    talleres = '<ul class="adt_trk__kpi-talleres">' + d.talleres.map(function (t) {
                        var on = f.taller_id === t.id && t.id;
                        return '<li><button type="button" class="adt_trk__kpi-taller' + (on ? ' is-active' : '') + (t.n ? '' : ' is-zero') +
                            '" data-taller="' + (t.id || '') + '" aria-pressed="' + !!on + '"' + (t.id ? '' : ' disabled="disabled"') +
                            ' title="' + (t.id ? 'Ver solo las motos en ' + esc(t.nombre) : '') + '">' +
                            '<span>' + esc(t.nombre) + '</span>' +
                            (t.demorados ? '<i class="fa fa-exclamation-triangle is-critico" title="' + plural(t.demorados, 'demorada', 'demoradas') + '" aria-hidden="true"></i>' : '') +
                            '<strong>' + entero(t.n) + '</strong></button></li>';
                    }).join('') + '</ul>';
                }
                return '<li class="adt_trk__kpi is-' + e.codigo + (e.codigo === 'fibra' ? ' is-wide' : '') + '">' +
                    '<button type="button" class="adt_trk__kpi-main" data-kpi-etapa="' + e.codigo + '" title="Ir a la columna ' + esc(e.nombre) + '">' +
                    '<span class="adt_trk__kpi-ico"><i class="fa ' + e.icon + '" aria-hidden="true"></i></span>' +
                    '<span class="adt_trk__kpi-txt"><span class="adt_trk__kpi-label">' + esc(e.nombre) + '</span>' +
                    '<strong class="adt_trk__kpi-n">' + entero(e.n) + '</strong>' +
                    '<span class="adt_trk__kpi-sub">' + (sub || (e.n ? '&nbsp;' : 'Sin motos')) + '</span></span></button>' + talleres + '</li>';
            }).join('') + '</ol>';
            this._ref('kpis').html(html);
        },

        _renderTablero: function () {
            var self = this;
            var d = this.data;
            var f = this.filtros;
            var filtrando = f.buscar || f.taller_id || f.placa || f.demorados || f.cliente;
            var html = '<div class="adt_cap__toolbar adt_trk__toolbar">' +
                '<label class="adt_cap__search"><i class="fa fa-search" aria-hidden="true"></i>' +
                '<input type="search" data-ref="buscar" placeholder="Chasis, modelo, placa, cliente o TRK" value="' + esc(f.buscar) + '"/></label>' +
                '<div class="adt_cart__facet-chips" role="group" aria-label="Estado de la placa"><span class="adt_trk__facet-label">Placa</span>' +
                d.placas.map(function (p) {
                    return self._chipFiltro('data-placa', p.estado, f.placa === p.estado, p.label, p.n, p.nivel);
                }).join('') + '</div>' +
                '<div class="adt_cart__facet-chips" role="group" aria-label="Cliente">' +
                this._chipFiltro('data-cliente', 'sin', f.cliente === 'sin', 'En stock') +
                this._chipFiltro('data-cliente', 'con', f.cliente === 'con', 'Con cliente') +
                '<button type="button" class="adt_cart__fchip' + (f.demorados ? ' is-active' : '') + '" data-action="demorados" aria-pressed="' +
                    f.demorados + '"><i class="adt_cart__fchip-dot is-cancelado" aria-hidden="true"></i>Demoradas' +
                    '<span class="adt_cart__fchip-n">' + entero(d.demorados) + '</span></button></div>' +
                (filtrando ? '<button type="button" class="adt_cap__link" data-action="limpiar">Quitar filtros</button>' : '') +
                '</div>';
            if (f.taller_id) {
                var taller = _.findWhere(d.talleres, {id: f.taller_id});
                html += '<p class="adt_cap__nota">' + icono('info') + 'Mostrando solo las motos en ' + esc(taller ? taller.nombre : 'el taller') + '. ' +
                    '<button type="button" class="adt_cap__link" data-taller="' + f.taller_id + '">Ver todas</button></p>';
            }
            var porEtapa = _.groupBy(d.items, 'etapa');
            html += '<div class="adt_trk__board">' + d.etapas.map(function (e) {
                var items = porEtapa[e.codigo] || [];
                return '<section class="adt_trk__col is-' + e.codigo + '" data-col="' + e.codigo + '" aria-label="' + esc(e.nombre) + '">' +
                    '<header class="adt_trk__col-head"><span class="adt_trk__col-ico"><i class="fa ' + e.icon + '" aria-hidden="true"></i></span>' +
                    '<div><h2>' + esc(e.nombre) + '</h2>' + (e.descripcion ? '<p>' + esc(e.descripcion) + '</p>' : '') + '</div>' +
                    '<span class="adt_trk__col-n">' + entero(items.length) + '</span></header>' +
                    '<div class="adt_trk__col-body">' + (items.length ? items.map(self._htmlCard, self).join('')
                        : '<p class="adt_trk__col-empty">' + (filtrando ? 'Nada coincide con los filtros.' : 'Sin motos en esta etapa.') + '</p>') +
                    '</div></section>';
            }).join('') + '</div>';
            if (d.recortado) {
                html += '<p class="adt_cap__muted">Se muestran las primeras ' + entero(d.limite) + ' motos. Usa el buscador para encontrar otras.</p>';
            }
            var $buscar = this._ref('buscar');
            var foco = $buscar.length && $buscar.is(':focus');
            var scrolls = {};
            this.$('[data-col]').each(function () {
                scrolls[this.getAttribute('data-col')] = $(this).find('.adt_trk__col-body').scrollTop();
            });
            this._ref('body').html(html);
            _.each(scrolls, function (top, col) {
                self.$('[data-col="' + col + '"] .adt_trk__col-body').scrollTop(top);
            });
            if (foco) {
                var input = this._ref('buscar')[0];
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            }
        },

        _chipFiltro: function (attr, valor, activo, texto, n, nivel) {
            return '<button type="button" class="adt_cart__fchip' + (activo ? ' is-active' : '') + (n === 0 && !activo ? ' is-zero' : '') +
                '" ' + attr + '="' + esc(valor) + '" aria-pressed="' + activo + '">' +
                (nivel ? '<i class="adt_trk__dot is-' + nivel + '" aria-hidden="true"></i>' : '') + esc(texto) +
                (n === undefined ? '' : '<span class="adt_cart__fchip-n">' + entero(n) + '</span>') + '</button>';
        },

        // Una tarjeta: la moto, su avance en los dos flujos y las acciones de hoy.
        _htmlCard: function (it) {
            var orden = ['recojo', 'almacen', 'fibra', 'listo'];
            var actual = orden.indexOf(it.etapa);
            var segmentos = orden.map(function (c, i) {
                return '<span class="adt_trk__seg' + (i < actual ? ' is-done' : (i === actual ? ' is-current' : '')) + '"></span>';
            }).join('');
            var tiempo = '<span class="adt_trk__age' + (it.demorado ? ' is-late' : '') + '" title="Tiempo en la etapa' +
                (it.sla_dias ? ' (objetivo ' + dias(it.sla_dias) + ')' : '') + '"><i class="fa ' +
                (it.demorado ? 'fa-exclamation-triangle' : 'fa-clock-o') + '" aria-hidden="true"></i>' + dias(it.dias_etapa) + '</span>';
            var acciones = '';
            if (this.eligiendo === it.id) {
                acciones = '<div class="adt_trk__pick"><span>¿A qué taller?</span>' + this.data.talleres.filter(function (t) { return t.id; }).map(function (t) {
                    return '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-avanzar="' + it.id + '" data-taller-id="' + t.id + '">' +
                        esc(t.codigo || t.nombre) + '</button>';
                }).join('') + '<button type="button" class="adt_cap__link" data-action="cancelar-taller">Cancelar</button></div>';
            } else {
                if (it.siguiente) {
                    acciones += it.siguiente.requiere_taller
                        ? '<button type="button" class="adt_cart__btn" data-elegir-taller="' + it.id + '"><i class="fa ' + it.siguiente.icon +
                          '" aria-hidden="true"></i>' + esc(it.siguiente.label) + '</button>'
                        : '<button type="button" class="adt_cart__btn" data-avanzar="' + it.id + '"><i class="fa ' + it.siguiente.icon +
                          '" aria-hidden="true"></i>' + esc(it.siguiente.label) + '</button>';
                }
                if (it.accion_placa && this.data.placa_disponible) {
                    acciones += '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-placa-accion="' + it.accion_placa.accion +
                        '" data-id="' + it.id + '"><i class="fa ' + it.accion_placa.icon + '" aria-hidden="true"></i>' + esc(it.accion_placa.label) + '</button>';
                }
            }
            return '<article class="adt_trk__card' + (it.demorado ? ' is-late' : '') + '" data-card="' + it.id + '" tabindex="0" ' +
                'aria-label="' + esc(it.modelo + ' ' + it.chasis) + '">' +
                '<header class="adt_trk__card-head"><div class="adt_trk__card-title"><strong>' + esc(_.compact([it.marca, it.modelo]).join(' ')) + '</strong>' +
                    '<span class="adt_cap__sub"><span class="adt_cap__mono">' + esc(it.chasis || '—') + '</span>' + (it.color ? ' · ' + esc(it.color) : '') +
                    '</span></div>' + placaHtml(it.placa) + '</header>' +
                '<div class="adt_trk__tracks">' +
                    '<div class="adt_trk__track" title="Logística: ' + esc(it.etapa_nombre) + '"><span class="adt_trk__track-label">Logística</span>' +
                        '<span class="adt_trk__segs">' + segmentos + '</span>' + (it.taller ? '<span class="adt_trk__taller">' + esc(it.taller) + '</span>' : '') + '</div>' +
                    '<div class="adt_trk__track"><span class="adt_trk__track-label">Placa</span>' +
                        chip(it.estado_placa_label + (it.observaciones ? ' · ' + it.observaciones + ' obs.' : ''), it.nivel_placa) + '</div>' +
                '</div>' +
                '<footer class="adt_trk__card-foot">' + tiempo +
                    (it.cliente ? '<span class="adt_trk__owner" title="' + esc(it.cliente) + '"><i class="fa fa-user" aria-hidden="true"></i>' + esc(it.cliente) + '</span>'
                        : '<span class="adt_trk__owner is-stock"><i class="fa fa-cube" aria-hidden="true"></i>En stock</span>') +
                    (it.antes_de_tiempo ? chip('Antes de tiempo', 'atencion', 'fa-bolt') : '') +
                '</footer>' +
                (acciones ? '<div class="adt_trk__card-actions">' + acciones + '</div>' : '') +
                '</article>';
        },

        _item: function (id) {
            return _.findWhere(this.data.items, {id: id});
        },

        // ------------------------------------------------------------------
        // Acciones desde la tarjeta
        // ------------------------------------------------------------------

        _ejecutarTarjeta: function (metodo, kwargs, confirmar) {
            var self = this;
            var correr = function () {
                return llamar(self, metodo, kwargs).then(function () {
                    self.eligiendo = null;
                    self.displayNotification({type: 'success', title: TITULO, message: 'Listo: cambio registrado.'});
                    return self._recargar();
                }).guardedCatch(function (err) {
                    silenciar(err);
                    self.displayNotification({type: 'danger', title: TITULO, message: errorTexto(err), sticky: false});
                });
            };
            Dialog.confirm(this, confirmar, {confirm_callback: correr});
        },

        _onAvanzar: function (ev) {
            ev.stopPropagation();
            var it = this._item(parseInt(ev.currentTarget.getAttribute('data-avanzar'), 10));
            if (!it || !it.siguiente) { return; }
            var tallerId = parseInt(ev.currentTarget.getAttribute('data-taller-id'), 10) || null;
            var taller = tallerId ? _.findWhere(this.data.talleres, {id: tallerId}) : null;
            this._ejecutarTarjeta('tracking_mover', {tracking_id: it.id, etapa_id: it.siguiente.etapa_id, taller_id: tallerId},
                '¿' + it.siguiente.label + (taller ? ' (' + taller.nombre + ')' : '') + '? Moto ' + (it.chasis || it.ref) + '.');
        },

        _onElegirTaller: function (ev) {
            ev.stopPropagation();
            this.eligiendo = parseInt(ev.currentTarget.getAttribute('data-elegir-taller'), 10);
            this._renderTablero();
        },

        _onCancelarTaller: function (ev) {
            ev.stopPropagation();
            this.eligiendo = null;
            this._renderTablero();
        },

        _onPlacaAccion: function (ev) {
            ev.stopPropagation();
            var it = this._item(parseInt(ev.currentTarget.getAttribute('data-id'), 10));
            var accion = ev.currentTarget.getAttribute('data-placa-accion');
            if (!it) { return; }
            this._ejecutarTarjeta('tracking_placa', {tracking_id: it.id, accion: accion},
                accion === 'iniciar' ? '¿Iniciar el trámite de placa de la moto ' + (it.chasis || it.ref) + '?'
                    : '¿Dar por resuelta la observación de la placa y seguir el trámite?');
        },

        _onCard: function (ev) {
            if ($(ev.target).closest('button, a').length) { return; }
            this._abrirTracking(parseInt(ev.currentTarget.getAttribute('data-card'), 10));
        },

        _onCardTecla: function (ev) {
            if (ev.target !== ev.currentTarget) { return; }
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._abrirTracking(parseInt(ev.currentTarget.getAttribute('data-card'), 10));
            }
        },

        // ------------------------------------------------------------------
        // Filtros y drawers
        // ------------------------------------------------------------------

        _onKpiEtapa: function (ev) {
            var col = this.$('[data-col="' + ev.currentTarget.getAttribute('data-kpi-etapa') + '"]')[0];
            if (col) {
                col.scrollIntoView({behavior: 'smooth', block: 'nearest', inline: 'center'});
                $(col).addClass('is-flash');
                setTimeout(function () { $(col).removeClass('is-flash'); }, 900);
            }
        },

        _onTaller: function (ev) {
            var id = parseInt(ev.currentTarget.getAttribute('data-taller'), 10) || null;
            this.filtros.taller_id = this.filtros.taller_id === id ? null : id;
            this._recargar();
        },

        _onPlaca: function (ev) {
            var v = ev.currentTarget.getAttribute('data-placa');
            this.filtros.placa = this.filtros.placa === v ? null : v;
            this._recargar();
        },

        _onCliente: function (ev) {
            var v = ev.currentTarget.getAttribute('data-cliente');
            this.filtros.cliente = this.filtros.cliente === v ? null : v;
            this._recargar();
        },

        _onDemorados: function () {
            this.filtros.demorados = !this.filtros.demorados;
            this._recargar();
        },

        _onLimpiar: function () {
            this.filtros = {buscar: '', taller_id: null, placa: null, demorados: false, cliente: null};
            this._recargar();
        },

        _onBuscar: function (ev) {
            this.filtros.buscar = ev.currentTarget.value;
            this._buscarDiferido();
        },

        _onRefresh: function () {
            return this._recargar();
        },

        _onConfig: function () {
            return this._abrirTrkDrawer(new ConfigTracking(this));
        },

        _onTrkCambio: function () {
            var self = this;
            this._load().then(function () { self._render(); });
        },

        _onTrkCerrado: function (ev) {
            this._cerrarTrkDrawer();
            if (ev.data && ev.data.cambio) {
                this._recargar();
            }
        },

        _onTrkFicha: function (ev) {
            this.do_action({
                type: 'ir.actions.client', tag: 'adt_flota_360', name: 'Flota 360',
                params: {vehicle_id: ev.data.vehicle_id, tab: 'placa'},
            });
        },
    });

    // Ficha del vehículo en Flota 360: «Ver tracking y placa» abre el mismo detalle.
    Flota360.include(_.extend({}, AbreTracking, {
        custom_events: _.extend({}, Flota360.prototype.custom_events, {
            trk_cambio: '_onTrkCambio',
            trk_drawer_cerrado: '_onTrkCerrado',
            trk_ficha: '_onTrkFicha',
        }),

        _ejecutar: function (a) {
            if (a && a.tipo === 'tracking') {
                return this._abrirTracking(a.tracking_id, {enFlota360: true});
            }
            return this._super.apply(this, arguments);
        },

        _onTrkCambio: function () {
            this._trkCambio = true;
        },

        _onTrkCerrado: function () {
            this._cerrarTrkDrawer();
            if (this._trkCambio) {
                this._trkCambio = false;
                this._recargar();
            }
        },

        _onTrkFicha: function () {
            this._onTrkCerrado();
        },

        // Con el drawer abierto, Escape lo cierra a él y no a la ficha.
        _onGlobalKey: function () {
            if (this._trkDrawer) {
                return;
            }
            return this._super.apply(this, arguments);
        },
    }));

    core.action_registry.add('adt_flota_360_tracking', TrackingMotos);
    return {TrackingMotos: TrackingMotos, CasoTracking: CasoTracking, ConfigTracking: ConfigTracking};
});
