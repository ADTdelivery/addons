odoo.define('adt_flota_360.Flota360', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var session = require('web.session');

    var esc = _.escape;
    var PAGINA = 40;
    var ESPERA_BUSQUEDA = 280;

    var NIVEL_LABEL = {critico: 'Crítico', atencion: 'Atención', ok: 'Al día', info: 'Info', neutral: ''};

    // Columnas de módulos en la tabla de resultados (en este orden).
    var COLUMNAS = [
        {key: 'cuentas', titulo: 'Deuda', num: true},
        {key: 'papeletas', titulo: 'Papeletas', num: true},
        {key: 'gps', titulo: 'GPS'},
        {key: 'placa', titulo: 'Placa'},
        {key: 'expediente', titulo: 'Expediente'},
    ];

    // Navegación de la ficha, agrupada por área. Solo se muestran las secciones que
    // el servidor devuelve (módulos instalados y con acceso).
    // Cronograma de pagos: cuotas que se muestran al inicio (el resto, a pedido).
    var CUOTAS_INICIO = 6;
    // Operaciones de una cuota en el panel «Gestionar pago»: grupo y qué hace cada una.
    var OP_CUOTA = {
        action_register_payment: ['cobrar', 'Total o parcial; registra la mora a la fecha.'],
        action_pagar_mora: ['cobrar', 'Cobra la mora registrada pendiente.'],
        reprogramar: ['cambiar', 'Al final, después de otra cuota o en una fecha.'],
        trasladar: ['cambiar', 'Su saldo se suma a otra cuota.'],
        mora: ['cambiar', 'Perdonarla, fijar un monto o cobrarla aparte.'],
        action_editar_mora: ['cambiar', 'Cambiar la mora calculada.'],
        registrar_observacion: ['registro', 'Nota con fecha y adjuntos.'],
        action_open_image_gallery: ['registro', 'Vouchers subidos para esta cuota.'],
        action_delete_payment: ['quitar', 'Anula los pagos registrados en la cuota.'],
        eliminar: ['quitar', 'Se quita del cronograma; se puede deshacer.'],
    };
    var GRUPOS_CUOTA = [['cobrar', 'Cobrar'], ['cambiar', 'Cambiar la cuota'], ['registro', 'Registro'], ['otros', 'Otros'], ['quitar', 'Quitar o eliminar']];

    var NAV = [
        {titulo: 'General', items: [['resumen', 'Resumen', 'fa-th-large']]},
        {titulo: 'Cliente', items: [['cliente', 'Datos del cliente', 'fa-user'], ['expediente', 'Expediente', 'fa-folder-open-o']]},
        {titulo: 'Crédito y cobranza', items: [['cronograma', 'Cronograma de pagos', 'fa-sliders'],
            ['rentabilidad', 'Rentabilidad', 'fa-line-chart'], ['financiera', 'Financiera', 'fa-university'],
            ['papeletas', 'Papeletas', 'fa-file-text-o'], ['capturas', 'Capturas', 'fa-lock']]},
        {titulo: 'Vehículo', items: [['vehiculo', 'Vehículo', 'fa-motorcycle'], ['documentos', 'Documentos', 'fa-file-text-o'],
            ['placa', 'Placa y entrega', 'fa-id-card-o'], ['gps', 'GPS', 'fa-map-marker'],
            ['taller', 'Taller y mantenimiento', 'fa-wrench']]},
    ];

    var DOC_ESTADO = {
        aceptado: ['ok', 'Aceptado'], rechazado: ['critico', 'Rechazado'],
        incompleto: ['atencion', 'Incompleto'], falta: ['neutral', 'Sin cargar'],
        cubierto: ['info', 'En el archivo único'],
    };
    var MAX_ARCHIVO_MB = 15;
    // Expediente en un solo archivo (PDF o Word): ver CONSOLIDADO en flota_360_ops.py.
    var CONSOLIDADO = 'archivo_consolidado';
    var MAX_CONSOLIDADO_MB = 40;
    var ACEPTA_DOCUMENTO = 'image/*,application/pdf';
    var ACEPTA_CONSOLIDADO = '.pdf,.doc,.docx,application/pdf,application/msword,' +
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    var ICONO_SECCION = {
        'Identificación': 'fa-id-card-o', 'Datos personales': 'fa-user-o', 'Contacto': 'fa-phone',
        'Dirección': 'fa-map-marker', 'Vehículo': 'fa-motorcycle',
    };
    // Visor PDF incluido en Odoo: muestra el archivo aunque el servidor lo entregue como descarga.
    var VISOR_PDF = '/web/static/lib/pdfjs/web/viewer.html?file=';

    var FILTROS_CRONO = [['por_cobrar', 'Por cobrar'], ['todas', 'Todas'], ['pagadas', 'Pagadas']];

    // ------------------------------------------------------------------
    // Formato
    // ------------------------------------------------------------------

    function soles(n) {
        return 'S/ ' + (n || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function solesCorto(n) {
        return 'S/ ' + Math.round(n || 0).toLocaleString('es-PE');
    }

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    function fecha(iso) {
        if (!iso) {
            return '—';
        }
        var p = iso.slice(0, 10).split('-');
        return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : iso;
    }

    function fechaHora(utc) {
        if (!utc) {
            return '—';
        }
        var d = new Date(utc.replace(' ', 'T') + 'Z');
        return d.toLocaleDateString('es-PE', {day: '2-digit', month: '2-digit', year: 'numeric'}) + ' ' +
            d.toLocaleTimeString('es-PE', {hour: '2-digit', minute: '2-digit'});
    }

    // Datetime UTC de Odoo ("YYYY-MM-DD HH:MM:SS") → "hace 5 min".
    function hace(utc) {
        if (!utc) {
            return 'sin reporte';
        }
        var min = Math.round((Date.now() - new Date(utc.replace(' ', 'T') + 'Z').getTime()) / 60000);
        if (min < 1) { return 'hace instantes'; }
        if (min < 60) { return 'hace ' + min + ' min'; }
        var h = Math.round(min / 60);
        if (h < 24) { return 'hace ' + h + ' h'; }
        var d = Math.round(h / 24);
        return 'hace ' + d + (d === 1 ? ' día' : ' días');
    }

    function tamano(bytes) {
        if (bytes < 1024 * 1024) {
            return Math.max(1, Math.round(bytes / 1024)) + ' KB';
        }
        return (bytes / (1024 * 1024)).toFixed(1).replace('.', ',') + ' MB';
    }

    function plural(n, uno, varios) {
        return entero(n) + ' ' + (n === 1 ? uno : varios);
    }

    // Resalta el término buscado dentro de un texto.
    function marcar(texto, termino) {
        var t = esc(texto || '');
        var q = (termino || '').trim();
        if (q.length < 2) {
            return t;
        }
        var re = new RegExp('(' + esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
        return t.replace(re, '<mark>$1</mark>');
    }

    // Indicador de estado: punto de color + texto (el color nunca va solo).
    function estado(nivel, texto) {
        return '<span class="adt_f360__st is-' + (nivel || 'neutral') + '"><i aria-hidden="true"></i>' + esc(texto) + '</span>';
    }

    // Datetime UTC de Odoo <-> valor de <input type="datetime-local"> (hora local).
    function utcALocal(utc) {
        if (!utc) {
            return '';
        }
        var d = new Date(utc.replace(' ', 'T') + 'Z');
        var dos = function (n) { return (n < 10 ? '0' : '') + n; };
        return d.getFullYear() + '-' + dos(d.getMonth() + 1) + '-' + dos(d.getDate()) + 'T' + dos(d.getHours()) + ':' + dos(d.getMinutes());
    }

    function localAUtc(local) {
        if (!local) {
            return false;
        }
        return new Date(local).toISOString().slice(0, 19).replace('T', ' ');
    }

    // File -> {nombre, datos (base64 sin encabezado)}; rechaza los que exceden el límite.
    function leerArchivo(file, limiteMb) {
        limiteMb = limiteMb || MAX_ARCHIVO_MB;
        return new Promise(function (resolve, reject) {
            if (file.size > limiteMb * 1024 * 1024) {
                reject(new Error('«' + file.name + '» supera los ' + limiteMb + ' MB permitidos.'));
                return;
            }
            var lector = new FileReader();
            lector.onload = function () {
                resolve({nombre: file.name, datos: String(lector.result).split(',')[1] || ''});
            };
            lector.onerror = function () { reject(new Error('No se pudo leer «' + file.name + '».')); };
            lector.readAsDataURL(file);
        });
    }

    function badge(nivel, texto) {
        return '<span class="adt_f360__badge is-' + (nivel || 'neutral') + '">' + esc(texto) + '</span>';
    }

    var Flota360 = AbstractAction.extend({
        template: 'adt_flota_360.Main',
        hasControlPanel: false,

        events: {
            'input [data-ref="q"]': '_onInput',
            'keydown [data-ref="q"]': '_onSearchKey',
            'click [data-action="clear"]': '_onClear',
            'click [data-filtro]': '_onFiltro',
            'click [data-financiera]': '_onFinanciera',
            'click [data-estado]': '_onEstado',
            'click [data-grupo]': '_onGrupo',
            'click [data-action="clear-facetas"]': '_onClearFacetas',
            'click [data-row]': '_onRow',
            'keydown [data-row]': '_onRowKey',
            'click [data-action="more"]': '_onMore',
            'click [data-action="close"]': '_closeDrawer',
            'click [data-tab]': '_onTab',
            'click [data-accion]': '_onAccion',
            'click [data-menu]': '_onMenu',
            'click [data-ptab]': '_onPestana',
            'click [data-crono]': '_onFiltroCrono',
            'click [data-crono-sel]': '_onCronoSel',
            'keydown tr[data-crono-sel]': '_onCronoSelKey',
            'click [data-crono-ir]': '_onCronoIr',
            'click [data-crono-ver]': '_onCronoVer',
            'click [data-cuota-gestionar]': '_onCuotaGestionar',
            'click [data-detalle-abrir]': '_onDetalleAbrir',
            'click [data-detalle-cerrar]': '_onDetalleCerrar',
            'click [data-contrato-subir]': '_onContratoSubir',
            'click [data-contrato-quitar]': '_onContratoQuitar',
            'dragover [data-contrato-zona]': '_onDragOver',
            'dragleave [data-contrato-zona]': '_onDragLeave',
            'drop [data-contrato-zona]': '_onDrop',
            'click [data-expandir]': '_onExpandir',
            'click [data-subir]': '_onSubir',
            'change [data-ref="archivo"]': '_onArchivo',
            'dragover [data-subir-zona]': '_onDragOver',
            'dragleave [data-subir-zona]': '_onDragLeave',
            'drop [data-subir-zona]': '_onDrop',
            'click [data-ver]': '_onVer',
            'click [data-quitar]': '_onQuitar',
            'click [data-aceptar]': '_onAceptar',
            'click [data-rechazar]': '_onRechazar',
            'click [data-exp]': '_onExpediente',
            'click [data-pap]': '_onPapeleta',
            'click [data-pap-close]': '_cerrarPapeleta',
            'click [data-cap]': '_onCaptura',
            'click [data-cap-close]': '_cerrarCaptura',
            'click [data-cuenta-sel]': '_onCuentaSel',
            'click [data-cuota]': '_onCuota',
            'keydown tr[data-cuota]': '_onCuotaKey',
            'click [data-cuota-close]': '_cerrarCuota',
            'click [data-cobrar]': '_onCobrar',
            'click [data-modal-close]': '_cerrarModal',
            'submit [data-ref="modal"] form': '_onSubmitModal',
            'click [data-guardar]': '_onSubmitModal',
            'input [data-campo]': '_onCampo',
            'change [data-campo]': '_onCampo',
            'focusout [data-campo]': '_onCampoBlur',
            'click [data-seg-campo]': '_onSegmento',
            'mousedown [data-m2o-opcion]': '_onM2oOpcion',
            'mousedown [data-m2o-crear]': '_onM2oCrear',
            'click [data-m2o-limpiar]': '_onM2oLimpiar',
            'keydown [data-m2o] input': '_onM2oKey',
            'focus [data-m2o] input': '_onM2oFocus',
            'focusout [data-m2o]': '_onM2oBlur',
            'click [data-modo]': '_onModoCredito',
            'click [data-credito-paso]': '_onPasoCredito',
            'click [data-credito-cambiar]': '_onCambiarClienteCredito',
            'click [data-credito-nuevo]': '_onNuevoClienteCredito',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.termino = '';
            this.filtro = 'todos';
            this.filtros = [];
            this.financiera = null;  // id de la financiera de la cuenta activa; 0 = cuenta activa sin financiera; null = todas
            this.financieras = [];
            this.estado = null;  // estado del cronograma de la cuenta; 'sin_cuenta' = sin cronograma; null = todos
            this.estados = [];
            this.grupo = null;  // 'clientes' (con dueño), 'stock' (sin dueño) o null = todos
            this.grupos = {};
            this.items = [];
            this.total = 0;
            this.contadores = {};
            this.cartera = {};
            this.detalle = null;
            this.tab = 'resumen';
            // Estado de la vista de deuda: se conserva al recargar la ficha tras una operación.
            this.vistas = {};
            this.filtroCrono = {};
            this.expandidas = {};
            this.expSel = null;
            this.papSel = null;
            this.capSel = null;
            this.cuentaSel = null;
            this.cuotaSel = null;
            this._modal = null;
            this._acciones = [];
            this._seq = 0;
            this._listaSucia = false;
            this._buscarDiferido = _.debounce(this._buscar.bind(this, false), ESPERA_BUSQUEDA);
            this._onGlobalKey = this._onGlobalKey.bind(this);
            this._onGlobalClick = this._onGlobalClick.bind(this);
        },

        willStart: function () {
            var self = this;
            this._simularDiferido = _.debounce(this._simularCredito.bind(this), 250);
            this._buscarOpcionesDiferido = _.debounce(this._buscarOpciones.bind(this), 220);
            var filtros = this._rpc({model: 'adt.flota360', method: 'get_filtros', args: []}).then(function (f) {
                self.filtros = f;
            });
            return Promise.all([this._super.apply(this, arguments), filtros]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                document.addEventListener('keydown', self._onGlobalKey);
                document.addEventListener('click', self._onGlobalClick, true);
                self._renderFiltros();
                self._buscar(false);
            });
        },

        on_attach_callback: function () {
            this._ref('q').trigger('focus');
        },

        destroy: function () {
            document.removeEventListener('keydown', this._onGlobalKey);
            if (this._obsModal) {
                this._obsModal.disconnect();
                window.removeEventListener('resize', this._marcarDesborde);
            }
            document.removeEventListener('click', this._onGlobalClick, true);
            this._super.apply(this, arguments);
        },

        _ref: function (name) {
            return this.$('[data-ref="' + name + '"]');
        },

        // ------------------------------------------------------------------
        // Datos
        // ------------------------------------------------------------------

        _buscar: function (agregar) {
            var self = this;
            var seq = ++this._seq;
            if (!agregar) {
                this._renderCargando();
            }
            return this._rpc({
                model: 'adt.flota360',
                method: 'buscar',
                kwargs: {
                    termino: this.termino,
                    filtro: this.filtro,
                    financiera: this.financiera,
                    estado: this.estado,
                    grupo: this.grupo,
                    offset: agregar ? this.items.length : 0,
                    limit: PAGINA,
                },
            }).then(function (res) {
                if (seq !== self._seq) {
                    return; // llegó una búsqueda más reciente
                }
                self.items = agregar ? self.items.concat(res.items) : res.items;
                self.total = res.total;
                self.contadores = res.contadores;
                self.cartera = res.cartera || {};
                self.financieras = res.financieras || [];
                self.estados = res.estados || [];
                self.grupos = res.grupos || {};
                self.truncado = res.truncado;
                self._renderFiltros();
                self._renderCartera();
                self._renderLista();
            });
        },

        _cargarDetalle: function (id) {
            var self = this;
            return this._rpc({model: 'adt.flota360', method: 'detalle', args: [id]}).then(function (d) {
                if (id !== self._drawerId) {
                    return;
                }
                self.detalle = d;
                self._renderDrawer();
            });
        },

        // ------------------------------------------------------------------
        // Render: búsqueda, cifras y tabla
        // ------------------------------------------------------------------

        _renderFiltros: function () {
            var self = this;
            this._ref('filtros').html(this.filtros.map(function (f) {
                var n = self.contadores[f.key];
                var activo = f.key === self.filtro;
                var alerta = f.key !== 'todos' && n > 0;
                return '<button type="button" class="adt_f360__filter' + (activo ? ' is-active' : '') +
                    '" data-filtro="' + f.key + '" aria-pressed="' + activo + '">' + esc(f.label) +
                    (n === undefined ? '' : '<span class="adt_f360__count' + (alerta ? ' is-alert' : '') + '">' + entero(n) + '</span>') +
                    '</button>';
            }).join(''));
            this.$el.toggleClass('has-query', !!this.termino);
            this._renderFacetas();
        },

        // Filas bajo los filtros: financiera y estado del cronograma de pagos, con sus vehículos
        // en la búsqueda actual.
        // Selector junto al buscador: separa las motos con cliente de las que están en stock.
        _renderGrupos: function () {
            var self = this;
            var g = this.grupos;
            if (g.clientes === undefined) {
                this._ref('grupos').empty();
                return;
            }
            var opciones = [
                [null, 'Todos', g.clientes + g.stock, 'fa-th-large'],
                ['clientes', 'Con cliente', g.clientes, 'fa-user'],
                ['stock', 'En stock', g.stock, 'fa-cubes'],
            ];
            this._ref('grupos').html(opciones.map(function (o) {
                var activo = o[0] === self.grupo;
                return '<button type="button" class="adt_f360__group' + (activo ? ' is-active' : '') + (o[0] ? ' is-' + o[0] : '') +
                    '" data-grupo="' + (o[0] || 'todos') + '" aria-pressed="' + activo + '">' +
                    '<i class="fa ' + o[3] + '" aria-hidden="true"></i>' + o[1] +
                    '<span class="adt_f360__group-n">' + entero(o[2]) + '</span></button>';
            }).join(''));
        },

        _renderFacetas: function () {
            this._renderGrupos();
            this._renderFaceta('financieras', 'financiera', 'fa-university', 'Financiera', 'Todas', this.financieras, this.financiera);
            this._renderFaceta('estados', 'estado', 'fa-calendar-check-o', 'Cronograma', 'Todos', this.estados, this.estado, true);
            this._ref('facetas')
                .toggleClass('is-empty', !this.financieras.length && !this.estados.length)
                .toggleClass('is-filtered', this.financiera !== null || this.estado !== null);
        },

        // Una fila: etiqueta fija a la izquierda y opciones en una franja desplazable.
        // Las opciones sin vehículos se atenúan; con punto, cada estado lleva su color.
        _renderFaceta: function (ref, atributo, icono, titulo, todos, opciones, actual, punto) {
            if (!opciones.length) {
                this._ref(ref).empty();
                return;
            }
            var total = opciones.reduce(function (s, o) { return s + (o.n || 0); }, 0);
            var chip = function (valor, nombre, n) {
                var activo = valor === actual;
                var clases = 'adt_f360__fchip' + (activo ? ' is-active' : '') + (!n && !activo ? ' is-zero' : '');
                return '<button type="button" class="' + clases + '" data-' + atributo + '="' +
                    (valor === null ? 'todas' : esc(String(valor))) + '" aria-pressed="' + activo + '">' +
                    (punto && valor !== null ? '<i class="adt_f360__fchip-dot is-' + esc(String(valor)) + '" aria-hidden="true"></i>' : '') +
                    esc(nombre) + '<span class="adt_f360__fchip-n">' + entero(n || 0) + '</span></button>';
            };
            this._ref(ref).html(
                '<span class="adt_f360__facet-label"><i class="fa ' + icono + '" aria-hidden="true"></i>' + titulo + '</span>' +
                '<div class="adt_f360__facet-chips">' + chip(null, todos, total) +
                opciones.map(function (o) { return chip(o.id, o.name, o.n); }).join('') + '</div>');
        },

        _renderCartera: function () {
            var c = this.cartera;
            var n = this.contadores;
            var celdas = [
                this._celdaVehiculos(n.todos),
                ['Cartera vencida', soles(c.vencido), plural(n.mora || 0, 'vehículo con atraso', 'vehículos con atraso'), c.vencido > 0 ? 'critico' : ''],
                ['Mora por cobrar', soles(c.mora), 'Registrada en las cuentas', c.mora > 0 ? 'atencion' : ''],
                ['Papeletas pendientes', soles(c.papeletas), plural(n.papeletas || 0, 'vehículo', 'vehículos'), c.papeletas > 0 ? 'atencion' : ''],
                ['Capturados', entero(n.capturas), 'Captura o disolución en curso', n.capturas > 0 ? 'critico' : ''],
            ];
            this._ref('cartera').html(celdas.map(function (x) {
                return '<div class="adt_f360__figure' + (x[3] ? ' is-' + x[3] : '') + '">' +
                    '<span class="adt_f360__figure-label">' + esc(x[0]) + '</span>' +
                    '<span class="adt_f360__figure-value">' + esc(x[1]) + '</span>' +
                    '<span class="adt_f360__figure-sub">' + esc(x[2]) + '</span></div>';
            }).join(''));
        },

        // Total de vehículos con el desglose clientes / stock, para no presentar el stock como flota colocada.
        _celdaVehiculos: function (total) {
            var g = this.grupos;
            if (this.grupo === 'stock') {
                return ['Vehículos en stock', entero(total), 'Sin dueño, disponibles para venta'];
            }
            if (this.grupo === 'clientes') {
                return ['Vehículos con cliente', entero(total), this.termino ? 'Coinciden con la búsqueda' : 'Flota colocada, sin stock'];
            }
            if (g.clientes === undefined) {
                return ['Vehículos', entero(total), this.termino ? 'Coinciden con la búsqueda' : 'Total de la flota'];
            }
            return ['Vehículos', entero(total), entero(g.clientes) + ' con cliente · ' + entero(g.stock) + ' en stock'];
        },

        _cabeceraTabla: function () {
            return '<thead><tr><th class="is-status">Estado</th><th>Placa</th><th>Vehículo</th><th>Cliente</th>' +
                COLUMNAS.map(function (c) {
                    return '<th' + (c.num ? ' class="is-num"' : '') + '>' + c.titulo + '</th>';
                }).join('') + '<th>Alertas</th></tr></thead>';
        },

        _renderCargando: function () {
            var fila = '<tr class="is-loading">' + new Array(COLUMNAS.length + 6).join('<td><span class="adt_f360__sk"></span></td>') + '</tr>';
            this._ref('grid').html('<table class="adt_f360__table">' + this._cabeceraTabla() +
                '<tbody>' + new Array(9).join(fila) + '</tbody></table>');
            this._ref('more').empty();
        },

        _renderLista: function () {
            var self = this;
            if (!this.items.length) {
                this._ref('grid').html(
                    '<div class="adt_f360__empty"><h3>Sin resultados' + (this.termino ? ' para «' + esc(this.termino) + '»' : '') + '</h3>' +
                    '<p>Prueba con la placa sin guion, solo el número de documento o parte del nombre del cliente.</p></div>');
                this._ref('more').empty();
                return;
            }
            this._ref('grid').html('<table class="adt_f360__table">' + this._cabeceraTabla() + '<tbody>' +
                this.items.map(function (it) { return self._htmlFila(it); }).join('') + '</tbody></table>');

            var faltan = this.total - this.items.length;
            this._ref('more').html(
                '<span class="adt_f360__muted">' + entero(this.items.length) + ' de ' + entero(this.total) +
                ' · ordenados por prioridad' + (this.truncado ? ' · se evaluaron los primeros 5.000, afina la búsqueda' : '') + '</span>' +
                (faltan > 0 ? '<button type="button" class="adt_f360__btn" data-action="more">Cargar ' + Math.min(faltan, PAGINA) + ' más</button>' : ''));
        },

        _htmlPlaca: function (it, grande) {
            return it.tiene_placa
                ? '<span class="adt_f360__plate' + (grande ? ' is-large' : '') + '">' + marcar(it.placa, this.termino) + '</span>'
                : '<span class="adt_f360__plate is-empty' + (grande ? ' is-large' : '') + '">Sin placa</span>';
        },

        _celdaModulo: function (m) {
            if (!m) {
                return '<td class="adt_f360__muted">—</td>';
            }
            var principal, sub = '';
            if (m.key === 'cuentas') {
                if (m.nivel === 'critico' || m.nivel === 'atencion') {
                    principal = '<span class="adt_f360__amount is-' + m.nivel + '">' + soles(m.monto) + '</span>';
                    sub = esc(m.texto) + (m.dias ? ' · ' + m.dias + ' d de atraso' : '');
                } else {
                    principal = estado(m.nivel, m.texto);
                    sub = esc(m.referencia || '');
                }
                return '<td class="is-num">' + principal + '<div class="adt_f360__sub">' + sub + '</div></td>';
            }
            if (m.key === 'papeletas') {
                principal = m.monto ? '<span class="adt_f360__amount is-' + m.nivel + '">' + soles(m.monto) + '</span>' : estado(m.nivel, m.texto);
                return '<td class="is-num">' + principal + (m.monto ? '<div class="adt_f360__sub">' + esc(m.texto) + '</div>' : '') + '</td>';
            }
            if (m.key === 'gps') {
                return '<td>' + estado(m.nivel, m.texto) + (m.desde ? '<div class="adt_f360__sub">' + hace(m.desde) + '</div>' : '') + '</td>';
            }
            return '<td>' + estado(m.nivel, m.texto) + '</td>';
        },

        _htmlFila: function (it) {
            var self = this;
            var c = it.cliente || {};
            var q = this.termino;
            var mods = _.indexBy(it.modulos, 'key');
            var etiquetas = it.modulos.filter(function (m) {
                return m.key === 'capturas' || m.key === 'taller';
            }).map(function (m) { return badge(m.nivel, m.texto); }).join('');
            var alerta = it.alertas.length
                ? '<div class="adt_f360__alert-text is-' + it.alertas[0].nivel + '">' + esc(it.alertas[0].texto) +
                  (it.alertas.length > 1 ? ' <span class="adt_f360__muted">+' + (it.alertas.length - 1) + '</span>' : '') + '</div>'
                : '';
            return '<tr data-row="' + it.id + '" tabindex="0" class="is-' + it.salud.nivel + (it.stock ? ' is-stock' : '') +
                (this.detalle && this.detalle.id === it.id ? ' is-selected' : '') + '">' +
                '<td class="is-status">' + estado(it.salud.nivel, it.salud.texto) + '</td>' +
                '<td>' + this._htmlPlaca(it) + '</td>' +
                '<td><div class="adt_f360__strong">' + esc([it.marca, it.modelo].filter(Boolean).join(' ') || 'Sin modelo') + '</div>' +
                    '<div class="adt_f360__sub">' + [esc(it.anio), esc(it.color), it.chasis ? 'VIN ' + marcar(it.chasis, q) : ''].filter(Boolean).join(' · ') + '</div></td>' +
                '<td>' + (c.nombre
                    ? '<div class="adt_f360__strong">' + marcar(c.nombre, q) + '</div><div class="adt_f360__sub">' +
                      [c.documento ? marcar(c.documento, q) : '', c.telefono ? marcar(c.telefono, q) : ''].filter(Boolean).join(' · ') + '</div>'
                    : it.stock
                        ? '<span class="adt_f360__stock-tag"><i class="fa fa-cubes" aria-hidden="true"></i> En stock</span>'
                        : '<span class="adt_f360__muted">Sin cliente</span>') + '</td>' +
                COLUMNAS.map(function (col) { return self._celdaModulo(mods[col.key]); }).join('') +
                '<td class="is-alerts">' + etiquetas + alerta + '</td>' +
                '</tr>';
        },

        // ------------------------------------------------------------------
        // Render: ficha (panel lateral)
        // ------------------------------------------------------------------

        _accion: function (a, extraCls) {
            this._acciones.push(a);
            return '<button type="button" class="adt_f360__btn' + (a.primary ? ' is-primary' : '') + (a.danger ? ' is-danger' : '') +
                (a.accent ? ' is-accent' : '') + (extraCls || '') + '" data-accion="' + (this._acciones.length - 1) + '">' +
                (a.icon ? '<i class="fa ' + esc(a.icon) + '" aria-hidden="true"></i>' : '') + '<span>' + esc(a.label) + '</span></button>';
        },

        // Acceso al centro de control con la cuota ya elegida.
        _botonGestionar: function (cuentaId, cuotaId) {
            return '<button type="button" class="adt_f360__btn is-small is-ghost" data-crono-ir="' + (cuotaId || '') + '" data-cuenta="' + cuentaId +
                '" title="Reprogramar, trasladar, mora, eliminar y más en Cronograma de pagos"><i class="fa fa-sliders" aria-hidden="true"></i><span>Gestionar</span></button>';
        },

        _accionCorta: function (a) {
            this._acciones.push(a);
            return '<button type="button" class="adt_f360__btn is-small is-ghost' + (a.danger ? ' is-danger' : '') +
                '" data-accion="' + (this._acciones.length - 1) + '" title="' + esc(a.label) + '">' +
                '<i class="fa ' + esc(a.icon || 'fa-circle-o') + '" aria-hidden="true"></i><span>' + esc(a.corto || a.label) + '</span></button>';
        },

        _acciones_html: function (lista, cls) {
            var self = this;
            return (lista || []).map(function (a) { return self._accion(a, cls); }).join('');
        },

        // Menú desplegable "Más" con operaciones secundarias.
        _menu: function (lista, etiqueta, cls) {
            var self = this;
            if (!lista || !lista.length) {
                return '';
            }
            return '<div class="adt_f360__menu-wrap">' +
                '<button type="button" class="adt_f360__btn' + (cls || '') + '" data-menu aria-haspopup="true" aria-expanded="false">' +
                (etiqueta ? '<span>' + esc(etiqueta) + '</span><i class="fa fa-caret-down" aria-hidden="true"></i>'
                          : '<i class="fa fa-ellipsis-h" aria-hidden="true"></i><span class="sr-only">Más operaciones</span>') +
                '</button><div class="adt_f360__menu" role="menu">' +
                lista.map(function (a) {
                    self._acciones.push(a);
                    return '<button type="button" role="menuitem" class="adt_f360__menu-item' + (a.danger ? ' is-danger' : '') +
                        '" data-accion="' + (self._acciones.length - 1) + '"><i class="fa ' + esc(a.icon || 'fa-circle-o') +
                        '" aria-hidden="true"></i>' + esc(a.label) + '</button>';
                }).join('') + '</div></div>';
        },

        // Menú "⋯" con grupos titulados: [{titulo, acciones}]. Las peligrosas van en rojo.
        _menuGrupos: function (grupos, cls) {
            var self = this;
            grupos = (grupos || []).filter(function (g) { return g.acciones.length; });
            if (!grupos.length) {
                return '';
            }
            return '<div class="adt_f360__menu-wrap">' +
                '<button type="button" class="adt_f360__btn' + (cls || '') + '" data-menu aria-haspopup="true" aria-expanded="false" title="Más operaciones">' +
                '<i class="fa fa-ellipsis-h" aria-hidden="true"></i><span class="sr-only">Más operaciones</span></button>' +
                '<div class="adt_f360__menu is-grouped" role="menu">' + grupos.map(function (g) {
                    return '<div class="adt_f360__menu-group" role="presentation">' + esc(g.titulo) + '</div>' + g.acciones.map(function (a) {
                        self._acciones.push(a);
                        return '<button type="button" role="menuitem" class="adt_f360__menu-item' + (a.danger ? ' is-danger' : '') +
                            '" data-accion="' + (self._acciones.length - 1) + '"><i class="fa ' + esc(a.icon || 'fa-circle-o') +
                            '" aria-hidden="true"></i>' + esc(a.label) + '</button>';
                    }).join('');
                }).join('') + '</div></div>';
        },

        _abrirDrawer: function (id) {
            this.detalle = null;
            this.tab = 'resumen';
            this.vistas = {};
            this.filtroCrono = {};
            this.expandidas = {};
            this.expSel = null;
            this.papSel = null;
            this.capSel = null;
            this.cuentaSel = null;
            this.cuotaSel = null;
            this._drawerId = id;
            this._ref('drawer').html(this._htmlAviso('Cargando ficha…'));
            this.$el.addClass('is-drawer-open');
            this.$('[data-row]').removeClass('is-selected').filter('[data-row="' + id + '"]').addClass('is-selected');
            return this._cargarDetalle(id);
        },

        _htmlAviso: function (texto) {
            return '<div class="adt_f360__drawer-loading"><button type="button" class="adt_f360__btn" data-action="close">' +
                '<i class="fa fa-arrow-left" aria-hidden="true"></i>Volver</button><p>' + esc(texto) + '</p></div>';
        },

        _closeDrawer: function () {
            if (!this.$el.hasClass('is-drawer-open')) {
                return;
            }
            this.$el.removeClass('is-drawer-open');
            this.$('[data-row].is-selected').removeClass('is-selected');
            var id = this._drawerId;
            this.detalle = null;
            this._drawerId = null;
            if (this._listaSucia) {
                this._listaSucia = false;
                this._buscar(false);
            } else if (id) {
                this.$('[data-row="' + id + '"]').trigger('focus');
            }
        },

        _renderDrawer: function () {
            var d = this.detalle;
            if (this.tab === 'cuentas') {
                this.tab = 'cronograma';
            }
            var $drawer = this._ref('drawer');
            var scroll = $drawer.find('.adt_f360__db').scrollTop() || 0;
            var scrollPanel = $drawer.find('.adt_f360__sheet-body').scrollTop() || 0;
            this._acciones = [];
            if (!d) {
                $drawer.html(this._htmlAviso('El vehículo ya no existe o no tienes acceso.'));
                return;
            }
            var seccion = _.findWhere(d.secciones, {key: this.tab === 'cronograma' ? 'cuentas' : this.tab});
            var body;
            this._tituloExtra = '';  // la sección puede agregar controles junto al título
            if (this.tab === 'cronograma' && seccion) {
                body = this._htmlControlCronograma(seccion);
            } else if (this.tab === 'resumen' || !seccion) {
                body = this._htmlResumen(d);
            } else if (seccion.deuda) {
                body = this._htmlDeuda(seccion);
            } else if (seccion.key === 'expediente') {
                body = this._htmlExpedientes(seccion);
            } else if (seccion.key === 'documentos') {
                body = this._htmlDocumentosVehiculo(seccion);
            } else if (seccion.key === 'cliente') {
                body = this._htmlCliente(seccion);
            } else if (seccion.key === 'papeletas') {
                body = this._htmlPapeletas(seccion);
            } else if (seccion.key === 'capturas') {
                body = this._htmlCapturas(seccion);
            } else if (seccion.key === 'rentabilidad') {
                body = this._htmlRentabilidad(seccion);
            } else if (seccion.key === 'financiera') {
                body = this._htmlFinanciera(seccion);
            } else if (seccion.key === 'taller') {
                body = this._htmlTaller(seccion);
            } else if (seccion.key === 'placa') {
                body = this._htmlPlacaSeccion(seccion);
            } else if (seccion.key === 'gps') {
                body = this._htmlGpsSeccion(seccion);
            } else if (seccion.key === 'vehiculo') {
                body = this._htmlVehiculoSeccion(seccion);
            } else {
                body = this._htmlSeccion(seccion);
            }
            var titulo = this.tab === 'resumen' || !seccion ? 'Resumen' : (this.tab === 'cronograma' ? 'Cronograma de pagos' : seccion.titulo);
            // Sin cabecera: la identidad del vehículo va arriba del menú lateral para dejar
            // toda la altura al contenido.
            $drawer.html('<div class="adt_f360__layout">' + this._htmlNav(d) +
                '<div class="adt_f360__db"><div class="adt_f360__db-inner">' +
                '<div class="adt_f360__page-head"><h2 class="adt_f360__page-title">' + esc(titulo) + '</h2>' + this._tituloExtra + '</div>' +
                body + '</div></div></div>' +
                this._htmlPanelPapeleta(seccion) + this._htmlPanelCaptura(seccion) + this._htmlPanelCuota(seccion) +
                this._htmlPanelDetalle(seccion));
            $drawer.find('.adt_f360__db').scrollTop(scroll);
            $drawer.find('.adt_f360__sheet-body').scrollTop(scrollPanel);
        },

        // Menú lateral agrupado. El punto de color marca las secciones con pendientes.
        _htmlNav: function (d) {
            var self = this;
            var secciones = _.indexBy(d.secciones, 'key');
            var mods = _.indexBy(d.modulos, 'key');
            var pasos = {};
            (d.recorrido || []).forEach(function (p) {
                if (p.tab && (p.nivel === 'critico' || p.nivel === 'atencion') && pasos[p.tab] !== 'critico') {
                    pasos[p.tab] = p.nivel;
                }
            });
            // Arriba del menú solo volver y la placa (referencia al navegar); el detalle del
            // vehículo, el cliente y el estado están en la cabecera del Resumen.
            var identidad = '<div class="adt_f360__nav-id">' +
                '<div class="adt_f360__nav-id-top">' +
                    '<button type="button" class="adt_f360__icon-btn" data-action="close" title="Volver a la lista (Esc)" aria-label="Volver a la lista">' +
                        '<i class="fa fa-arrow-left" aria-hidden="true"></i></button>' +
                    this._htmlPlaca(d) + '</div></div>';
            return '<nav class="adt_f360__nav" aria-label="Secciones de la ficha">' + identidad + NAV.map(function (g) {
                var items = g.items.filter(function (it) {
                    // «Cronograma de pagos» usa los datos de «Crédito y cuotas».
                    return it[0] === 'resumen' || secciones[it[0]] || (it[0] === 'cronograma' && secciones.cuentas);
                });
                if (!items.length) {
                    return '';
                }
                return '<div class="adt_f360__nav-group"><div class="adt_f360__nav-title">' + esc(g.titulo) + '</div>' +
                    items.map(function (it) {
                        // «Cronograma de pagos» reemplaza a «Crédito y cuotas»: usa su indicador.
                        var clave = it[0] === 'cronograma' ? 'cuentas' : it[0];
                        var m = mods[clave];
                        var nivel = m && (m.nivel === 'critico' || m.nivel === 'atencion') ? m.nivel : (pasos[clave] || pasos[it[0]]);
                        var activo = self.tab === it[0];
                        return '<button type="button" class="adt_f360__nav-item' + (activo ? ' is-active' : '') + '" data-tab="' + it[0] +
                            '"' + (activo ? ' aria-current="page"' : '') + '><i class="fa ' + it[2] + '" aria-hidden="true"></i>' +
                            '<span>' + esc(it[1]) + '</span>' +
                            (nivel ? '<i class="adt_f360__tab-dot is-' + nivel + '" title="' + NIVEL_LABEL[nivel] + '"></i>' : '') +
                            '</button>';
                    }).join('') + '</div>';
            }).join('') + '</nav>';
        },

        _panel: function (titulo, contenido, acciones, extra) {
            return '<section class="adt_f360__panel' + (extra || '') + '">' +
                '<header class="adt_f360__panel-head"><h3>' + esc(titulo) + '</h3>' +
                (acciones ? '<div class="adt_f360__panel-actions">' + acciones + '</div>' : '') + '</header>' +
                '<div class="adt_f360__panel-body">' + contenido + '</div></section>';
        },

        _htmlResumen: function (d) {
            var vehiculo = _.findWhere(d.secciones, {key: 'vehiculo'}), imprimir = [];
            (vehiculo && vehiculo.menu || []).forEach(function (grupo) {
                (grupo.acciones || []).forEach(function (a) {
                    if (a.method === 'action_print_acta_vehicular' || a.method === 'action_print_contrato_tvs') { imprimir.push(a); }
                });
            });
            var documentos = imprimir.length ? '<section class="adt_f360__panel"><header class="adt_f360__panel-head">' +
                '<h3><i class="fa fa-print" aria-hidden="true"></i> Imprimir documentos</h3>' +
                '<div class="adt_f360__summary-print">' + this._acciones_html(imprimir) + '</div></header></section>' : '';
            return this._htmlResumenCabecera(d) + documentos + this._htmlIndicadores(d);
        },

        // Cabecera del Resumen: vehículo (placa y modelo), cliente (documento y teléfono) y el
        // estado general como distintivo de color con sus motivos (alertas más graves).
        _htmlResumenCabecera: function (d) {
            var c = d.cliente || {};
            var nivel = d.salud.nivel || 'neutral';
            var ICONO = {critico: 'fa-exclamation-circle', atencion: 'fa-exclamation-triangle', ok: 'fa-check-circle'};
            var motivos = (d.alertas || []).slice(0, 3);
            var resto = (d.alertas || []).length - motivos.length;
            var vehiculo = [d.anio, d.color].filter(Boolean).join(' · ');
            var telefono = c.telefono ? String(c.telefono).replace(/[^\d+]/g, '') : '';
            return '<section class="adt_f360__panel adt_f360__sumhead is-' + nivel + '">' +
                '<div class="adt_f360__sumhead-col">' +
                    '<span class="adt_f360__sumhead-label"><i class="fa fa-motorcycle" aria-hidden="true"></i>Vehículo</span>' +
                    this._htmlPlaca(d, true) +
                    '<span class="adt_f360__sumhead-main">' + esc([d.marca, d.modelo].filter(Boolean).join(' ') || 'Vehículo') + '</span>' +
                    (vehiculo ? '<span class="adt_f360__sub">' + esc(vehiculo) + '</span>' : '') +
                '</div>' +
                '<div class="adt_f360__sumhead-col">' +
                    '<span class="adt_f360__sumhead-label"><i class="fa fa-user-o" aria-hidden="true"></i>Cliente</span>' +
                    '<span class="adt_f360__sumhead-main' + (c.nombre ? '' : ' is-empty') + '">' + esc(c.nombre || 'Sin cliente asignado') + '</span>' +
                    (c.documento || telefono ? '<span class="adt_f360__sumhead-chips">' +
                        (c.documento ? '<span><i class="fa fa-id-card-o" aria-hidden="true"></i>' + esc(c.documento) + '</span>' : '') +
                        (telefono ? '<a href="tel:' + esc(telefono) + '" title="Llamar"><i class="fa fa-phone" aria-hidden="true"></i>' + esc(c.telefono) + '</a>' : '') +
                    '</span>' : '') +
                '</div>' +
                '<div class="adt_f360__sumhead-flag" role="status">' +
                    '<span class="adt_f360__sumhead-flag-top"><i class="fa ' + (ICONO[nivel] || 'fa-circle-o') + '" aria-hidden="true"></i>' +
                        '<span><small>Estado</small><b>' + esc(d.salud.texto || 'Sin datos') + '</b></span></span>' +
                    (motivos.length ? '<ul>' + motivos.map(function (a) {
                        return '<li>' + esc(a.texto) + '</li>';
                    }).join('') + (resto > 0 ? '<li class="is-more">y ' + plural(resto, 'alerta más', 'alertas más') + '</li>' : '') + '</ul>'
                        : '<p>Sin alertas.</p>') +
                '</div>' +
            '</section>';
        },

        // Un cuadro por área: estado, una cifra, una línea de contexto y, si hay, la alerta principal.
        // El detalle completo está en cada sección (el cuadro lleva a ella).
        _htmlIndicadores: function (d) {
            var sec = _.indexBy(d.secciones, 'key');
            var mods = _.indexBy(d.modulos, 'key');
            var alertas = _.groupBy(d.alertas, 'modulo');
            var tiles = [];
            // t: {tab, modulo?, icono, titulo, nivel, estado, valor, sub, pct}
            var add = function (t) {
                if (sec[t.tab]) {
                    t.alerta = (alertas[t.modulo || t.tab] || [])[0];
                    // Mismo mensaje que la frase de estado de la sección.
                    var f = t.frase && sec[t.tab].frase;
                    if (f) {
                        t.nivel = f.nivel;
                        t.estado = '';
                        t.sub = f.texto + (f.detalle ? ' · ' + f.detalle : '');
                    }
                    tiles.push(t);
                }
            };

            var cuenta = sec.cuentas && sec.cuentas.deuda && sec.cuentas.deuda[0];
            if (cuenta) {
                var f = cuenta.cifras;
                add({tab: 'cuentas', icono: 'fa-credit-card', titulo: 'Crédito', estado: cuenta.estado,
                    nivel: f.vencidas >= 3 ? 'critico' : (f.al_dia > 0 || cuenta.state === 'borrador' ? 'atencion' : 'ok'),
                    valor: f.al_dia > 0 ? soles(f.al_dia) : 'Al día',
                    sub: f.al_dia > 0 ? 'Vencido · ' + plural(f.dias_atraso, 'día', 'días') + ' de atraso'
                        : (cuenta.proxima ? 'Próxima cuota ' + fecha(cuenta.proxima.fecha) : 'Sin cuotas por vencer'),
                    pct: f.total_cuotas ? Math.round(f.pagadas * 100 / f.total_cuotas) : null,
                    pctLabel: f.pagadas + ' de ' + f.total_cuotas + ' cuotas pagadas'});
            } else if (sec.cuentas) {
                add({tab: 'cuentas', icono: 'fa-credit-card', titulo: 'Crédito', nivel: 'neutral', estado: 'Sin cuenta',
                    valor: 'Sin crédito', sub: 'Créalo con «Nuevo crédito»'});
            }

            var historial = d.historial_crediticio;
            if (historial && sec.cuentas) {
                var disponible = historial.disponible;
                add({tab: 'cuentas', icono: 'fa-refresh', titulo: 'Refinanciamientos',
                    nivel: disponible ? (historial.refinanciamientos ? 'atencion' : 'neutral') : 'neutral',
                    estado: disponible ? (historial.refinanciamientos ? 'Detectados' : 'Sin indicios') : 'Sin acceso',
                    valor: disponible ? String(historial.refinanciamientos) : '—',
                    sub: disponible ? 'Según el historial de cuotas' : 'Historial no disponible'});
                add({tab: 'cuentas', icono: 'fa-users', titulo: 'Dueños / titulares',
                    nivel: disponible && historial.duenos > 1 ? 'atencion' : 'neutral',
                    estado: disponible ? 'Registrados' : 'Sin acceso',
                    valor: disponible ? String(historial.duenos) : '—',
                    sub: disponible ? 'Clientes distintos en los créditos' : 'Historial no disponible'});
            }

            var exp = sec.expediente;
            if (exp) {
                var e = exp.expedientes && exp.expedientes[0];
                add(e ? {tab: 'expediente', icono: 'fa-folder-open-o', titulo: 'Expediente', nivel: e.nivel, estado: e.estado,
                    valor: e.avance.completos + ' / ' + e.avance.requeridos, sub: 'documentos aceptados',
                    pct: e.avance.requeridos ? Math.round(e.avance.completos * 100 / e.avance.requeridos) : null}
                    : {tab: 'expediente', icono: 'fa-folder-open-o', titulo: 'Expediente', nivel: 'atencion', estado: 'Pendiente',
                    valor: 'Sin expediente', sub: 'Recomendado antes del crédito'});
            }

            if (sec.papeletas) {
                var mp = mods.papeletas || {};
                add({tab: 'papeletas', frase: true, icono: 'fa-file-text-o', titulo: 'Papeletas', nivel: mp.nivel || 'ok',
                    estado: mp.monto ? mp.texto : 'Al día', valor: mp.monto ? soles(mp.monto) : 'S/ 0.00',
                    sub: mp.monto ? 'por pagar' : 'Sin papeletas pendientes'});
            }

            if (sec.vehiculo) {
                var docs = ((sec.documentos || {}).documentos_vehiculo || []).filter(function (x) { return x.obligatorio; });
                var listos = docs.filter(function (x) { return x.estado === 'aceptado'; }).length;
                var mpl = mods.placa || {};
                // Con documentos pendientes el cuadro lleva a Documentos; si no, a los datos del vehículo.
                add({tab: docs.length && listos < docs.length ? 'documentos' : 'vehiculo', modulo: 'placa', icono: 'fa-motorcycle', titulo: 'Vehículo',
                    nivel: docs.length && listos < docs.length ? 'atencion' : (mpl.nivel || 'ok'),
                    estado: docs.length ? listos + '/' + docs.length + ' documentos' : (mpl.texto || ''),
                    valor: d.tiene_placa ? d.placa : 'Sin placa',
                    sub: [d.marca, d.modelo, d.anio].filter(Boolean).join(' ') || 'Vehículo',
                    pct: docs.length ? Math.round(listos * 100 / docs.length) : null,
                    pctLabel: docs.length ? 'Documentos del vehículo' : ''});
            }

            if (sec.gps) {
                var mg = mods.gps || {};
                add({tab: 'gps', frase: true, icono: 'fa-map-marker', titulo: 'GPS', nivel: mg.nivel || 'neutral', estado: '',
                    valor: mg.texto || 'Sin registrar', sub: mg.desde ? 'Último reporte ' + hace(mg.desde) : 'Sin reportes'});
            }
            if (mods.capturas) {
                add({tab: 'capturas', frase: true, icono: 'fa-lock', titulo: 'Captura', nivel: 'critico', estado: '',
                    valor: mods.capturas.texto, sub: 'Vehículo retenido'});
            }
            if (mods.taller) {
                add({tab: 'taller', frase: true, icono: 'fa-wrench', titulo: 'Taller', nivel: mods.taller.nivel, estado: '',
                    valor: mods.taller.texto, sub: 'En el taller'});
            }

            if (!tiles.length) {
                return '<p class="adt_f360__muted">No hay información de los módulos para este vehículo.</p>';
            }
            return '<div class="adt_f360__tiles">' + tiles.map(function (t) {
                var n = t.nivel || 'neutral';
                return '<button type="button" class="adt_f360__tile is-' + n + '" data-tab="' + t.tab + '">' +
                    '<span class="adt_f360__tile-head"><i class="fa ' + t.icono + '" aria-hidden="true"></i><span>' + esc(t.titulo) + '</span>' +
                    (t.estado ? estado(n, t.estado) : '') + '</span>' +
                    '<span class="adt_f360__tile-value">' + esc(t.valor) + '</span>' +
                    '<span class="adt_f360__tile-sub">' + esc(t.sub) + '</span>' +
                    (t.pct !== null && t.pct !== undefined ? '<span class="adt_f360__tile-progress">' +
                        '<span class="adt_f360__tile-bar"><span style="width:' + t.pct + '%"></span></span>' +
                        (t.pctLabel ? '<span class="adt_f360__tile-sub">' + esc(t.pctLabel) + '</span>' : '') + '</span>' : '') +
                    (t.alerta ? '<span class="adt_f360__tile-alert is-' + t.alerta.nivel + '"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i>' +
                        esc(t.alerta.texto) + '</span>' : '') +
                    '</button>';
            }).join('') + '</div>';
        },

        // Cliente: perfil con contacto rápido, datos por grupo e historial de titulares. El titular
        // solo cambia con el crédito (Crédito y cuotas): aquí no hay acciones de titularidad.
        _htmlCliente: function (s) {
            var self = this;
            var historial = s.historial || [];
            var lista = historial.length
                ? '<ol class="adt_f360__owners">' + historial.map(function (h) {
                    var periodo = h.desde || h.hasta
                        ? fecha(h.desde) + ' – ' + (h.actual ? 'a la fecha' : fecha(h.hasta))
                        : (h.actual ? 'Sin fecha de inicio registrada' : '');
                    return '<li class="adt_f360__owner' + (h.actual ? ' is-current' : '') + '">' +
                        '<i class="adt_f360__owner-dot" aria-hidden="true"></i>' +
                        '<div class="adt_f360__owner-body">' +
                            '<div class="adt_f360__owner-name"><span class="adt_f360__strong">' + esc(h.nombre) + '</span>' +
                                (h.actual ? badge('ok', 'Actual') : '') + '</div>' +
                            '<div class="adt_f360__sub">' + [h.documento ? esc(h.documento) : '', esc(periodo)].filter(Boolean).join(' · ') + '</div>' +
                            ((h.creditos || []).length ? '<div class="adt_f360__owner-credits">' + h.creditos.map(function (c) {
                                return '<span class="adt_f360__owner-credit"><i class="fa fa-credit-card" aria-hidden="true"></i>' +
                                    '<span class="adt_f360__mono">' + esc(c.referencia) + '</span>' + badge(c.nivel, c.texto) + '</span>';
                            }).join('') + '</div>' : '') +
                        '</div></li>';
                }).join('') + '</ol>'
                : '<p class="adt_f360__muted">Sin titulares registrados.</p>';

            if (!s.perfil) {
                return '<section class="adt_f360__panel adt_f360__cempty">' +
                        '<div class="adt_f360__cempty-head"><span class="adt_f360__avatar is-empty" aria-hidden="true"><i class="fa fa-user-o"></i></span>' +
                        '<div><h3>Sin cliente</h3><p class="adt_f360__muted">' + esc(s.vacio) + '</p></div></div></section>' +
                    this._panel('Historial de titulares', lista);
            }

            var p = s.perfil;
            var contacto = (s.contacto || []).map(function (a) {
                self._acciones.push(a);
                return '<button type="button" class="adt_f360__icon-btn is-contact is-' + esc(a.icon.replace('fa-', '')) +
                    '" data-accion="' + (self._acciones.length - 1) + '" title="' + esc(a.label) + '" aria-label="' + esc(a.label) + '">' +
                    '<i class="fa ' + esc(a.icon) + '" aria-hidden="true"></i></button>';
            }).join('');
            var tarjeta = this._htmlTarjeta({
                avatar: this._iniciales(p.nombre), empresa: p.empresa, titulo: p.nombre,
                chips: [p.documento && ['fa-id-card-o', (p.tipo_documento ? p.tipo_documento + ' ' : '') + p.documento],
                        p.telefono && ['fa-mobile', p.telefono], p.email && ['fa-envelope-o', p.email]].filter(Boolean),
                frase: p.titular
                    ? {nivel: 'ok', texto: 'Titular actual de la moto', detalle: p.desde ? 'desde el ' + fecha(p.desde) : ''}
                    : {nivel: 'neutral', texto: 'No es el titular actual', detalle: ''},
                extra: contacto + (contacto ? '<span class="adt_f360__sep" aria-hidden="true"></span>' : '') +
                    (s.editar ? this._accion(s.editar) : ''),
            });
            return tarjeta + this._htmlPestanas('cliente', [
                {key: 'datos', label: 'Datos', icon: 'fa-address-card-o'},
                {key: 'titulares', label: 'Historial de titulares', icon: 'fa-history', n: historial.length},
            ], function (key) {
                if (key === 'titulares') {
                    return '<div class="adt_f360__pad">' + lista + '</div>';
                }
                return '<div class="adt_f360__cgroups">' + (s.grupos || []).map(function (g) {
                    return '<section class="adt_f360__cgroup"><h4 class="adt_f360__cgroup-title">' +
                        '<i class="fa ' + (ICONO_SECCION[g.titulo] || 'fa-circle-o') + '" aria-hidden="true"></i>' + esc(g.titulo) + '</h4>' +
                        self._htmlCampos(g.campos) + '</section>';
                }).join('') + '</div>';
            });
        },

        _htmlDocumentosVehiculo: function (s) {
            var docs = s.documentos_vehiculo || [];
            if (!docs.length) {
                return '<p class="adt_f360__muted">Este vehículo no tiene documentos configurados.</p>';
            }
            var cargados = docs.filter(function (x) { return x.estado === 'aceptado'; }).length;
            return (s.frase ? this._htmlTarjeta({frase: s.frase, cifras: [
                    {label: 'Cargados', valor: cargados + ' de ' + docs.length, icon: 'fa-files-o', principal: true,
                     nivel: cargados === docs.length ? 'ok' : 'atencion'}]}) : '') + this._panel('Archivos',
                '<p class="adt_f360__muted adt_f360__docs-hint">' + cargados + ' de ' + docs.length +
                ' cargados. Arrastra un archivo sobre un documento o usa «Subir». Imágenes o PDF de hasta ' + MAX_ARCHIVO_MB + ' MB.</p>' +
                this._htmlDocs(docs, {modelo: s.modelo, res_id: s.res_id}));
        },

        // ------------------------------------------------------------------
        // Render: expediente y documentos
        // ------------------------------------------------------------------

        _htmlSinExpediente: function (s) {
            var accion = (s.acciones || [])[0];
            return '<div class="adt_f360__flag">' +
                '<i class="fa fa-folder-open-o adt_f360__flag-icon" aria-hidden="true"></i>' +
                '<div><div class="adt_f360__flag-title">Sin expediente</div>' +
                '<p>' + esc(s.vacio) + '</p></div>' +
                (accion ? '<div>' + this._accion(_.extend({}, accion, {primary: true})) + '</div>' : '') + '</div>';
        },

        _htmlExpedientes: function (s) {
            var self = this;
            var lista = s.expedientes || [];
            if (!lista.length) {
                return this._htmlSinExpediente(s);
            }
            var actual = _.findWhere(lista, {id: this.expSel}) || lista[0];
            var otros = lista.length > 1
                ? '<div class="adt_f360__exp-switch"><span class="adt_f360__label">Expedientes del cliente</span>' +
                  lista.map(function (e) {
                      return '<button type="button" class="adt_f360__chip' + (e.id === actual.id ? ' is-active' : '') + '" data-exp="' + e.id + '">' +
                          esc(e.titulo.replace('Expediente del ', '')) + (e.vigente ? ' · vigente' : '') + '</button>';
                  }).join('') + '</div>'
                : '';
            var av = actual.avance;
            var cons = actual.consolidado;
            var tarjeta = this._htmlTarjeta({
                icono: 'fa-folder-open-o', titulo: actual.titulo,
                chips: [['fa-flag', actual.estado], actual.cliente && ['fa-user-o', actual.cliente]].filter(Boolean),
                frase: actual.frase, cifras: actual.cifras,
                acciones: actual.acciones, menu: [{titulo: 'Cambiar estado', acciones: actual.mas}],
            });
            var ctx = {modelo: 'adt.expediente', res_id: actual.id, expediente: actual.id};
            var individuales = actual.grupos.map(function (g) {
                return '<section class="adt_f360__docgroup"><h4>' + esc(g.titulo) + '</h4>' + self._htmlDocs(g.documentos, ctx) + '</section>';
            }).join('');
            // Con el archivo único los documentos por separado ya no se piden: quedan plegados, a mano si se quieren ver.
            var clave = 'docs' + actual.id;
            var abiertos = !!this.expandidas[clave];
            var documentos = (cons ? this._htmlConsolidado(cons, ctx, av.cubierto) : '') + (av.cubierto
                ? '<button type="button" class="adt_f360__pap-toggle adt_f360__docs-toggle" data-expandir="' + clave + '" aria-expanded="' + abiertos + '">' +
                    '<i class="fa fa-angle-' + (abiertos ? 'down' : 'right') + '" aria-hidden="true"></i>' +
                    'Documentos por separado <span class="adt_f360__muted">(opcional, no son necesarios)</span></button>' +
                  (abiertos ? individuales : '')
                : individuales);
            var dat = actual.datos;
            var datos = this._htmlCampos(dat.campos) +
                this._htmlRevision('Dirección', dat.direccion_estado, dat.direccion_obs) +
                '<div class="adt_f360__label adt_f360__docs-title">Referencias</div>' +
                (dat.referencias.length ? '<ul class="adt_f360__refs">' + dat.referencias.map(function (r) {
                    return '<li>' + esc(r) + '</li>';
                }).join('') + '</ul>' : '<p class="adt_f360__muted">Sin referencias registradas.</p>') +
                this._htmlRevision('Referencias', dat.referencias_estado, dat.referencias_obs);
            var nDocs = actual.grupos.reduce(function (n, g) { return n + g.documentos.length; }, 0);
            return otros + tarjeta + this._htmlPestanas('expediente' + actual.id, [
                {key: 'documentos', label: 'Documentos', icon: 'fa-files-o', n: nDocs},
                {key: 'datos', label: 'Datos declarados', icon: 'fa-address-card-o'},
            ], function (key) {
                return '<div class="adt_f360__pad">' + (key === 'datos' ? datos : documentos) + '</div>';
            });
        },

        // Expediente en un solo archivo: alternativa a cargar cada documento. Si está cargado
        // y no rechazado, los requisitos que falten se dan por cubiertos.
        _htmlConsolidado: function (d, ctx, cubierto) {
            var cargado = d.archivos[0] && d.archivos[0].cargado;
            var texto = !cargado
                ? '¿El cliente entregó todo en un solo PDF o Word? Súbelo aquí y los requisitos se darán por completos ' +
                  'sin cargar cada foto. Hasta ' + MAX_CONSOLIDADO_MB + ' MB.'
                : (cubierto
                    ? 'Este archivo reemplaza a los documentos por separado: ya no es necesario cargarlos.'
                    : 'Archivo rechazado: los requisitos vuelven a exigirse por separado hasta que se cargue uno válido.');
            var autor = cargado && (d.cargado_por || d.cargado_el)
                ? '<span class="adt_f360__sub">Cargado' + (d.cargado_por ? ' por ' + esc(d.cargado_por) : '') +
                  (d.cargado_el ? ' el ' + esc(fechaHora(d.cargado_el)) : '') + '</span>'
                : '';
            return '<section class="adt_f360__single' + (cargado ? (cubierto ? ' is-covered' : ' is-rejected') : '') + '">' +
                '<div class="adt_f360__single-head">' +
                    '<i class="fa ' + (cargado ? 'fa-files-o' : 'fa-file-text-o') + ' adt_f360__single-icon" aria-hidden="true"></i>' +
                    '<div><h4>Expediente en un solo archivo <span class="adt_f360__muted">(opcional)</span></h4>' +
                    '<p>' + esc(texto) + '</p>' + autor + '</div>' +
                '</div>' +
                this._htmlDocs([d], ctx) + '</section>';
        },

        _htmlRevision: function (label, valor, obs) {
            if (valor !== 'rechazado') {
                return '';
            }
            return '<div class="adt_f360__note is-critico">' + esc(label) + ' rechazada' + (obs ? ': ' + esc(obs) : '') + '</div>';
        },

        // Tarjetas de documentos con vista previa y operaciones.
        // ctx: {modelo, res_id, expediente?}
        _htmlDocs: function (docs, ctx) {
            var self = this;
            return '<div class="adt_f360__doccards">' + docs.map(function (d) {
                var est = DOC_ESTADO[d.estado] || DOC_ESTADO.falta;
                var cargados = d.archivos.filter(function (a) { return a.cargado; }).length;
                var archivos = d.archivos.map(function (a) { return self._htmlArchivo(d, a, ctx); }).join('');
                var revision = '';
                if (ctx.expediente && d.revisable && d.clave) {
                    var ref = ctx.expediente + '|' + d.clave;
                    revision = '<footer class="adt_f360__doc-review">' +
                        // Los documentos cargados quedan aceptados por defecto: "Aceptar" solo revierte un rechazo.
                        (d.estado === 'rechazado' ? '<button type="button" class="adt_f360__btn is-small" data-aceptar="' + ref + '"><i class="fa fa-check" aria-hidden="true"></i>Aceptar</button>' : '') +
                        (d.estado !== 'rechazado' ? '<button type="button" class="adt_f360__btn is-small is-danger" data-rechazar="' + ref + '"><i class="fa fa-times" aria-hidden="true"></i>Rechazar</button>' : '') +
                        '</footer>';
                }
                return '<article class="adt_f360__doc is-' + d.estado + '">' +
                    '<header class="adt_f360__doc-head">' +
                        '<div class="adt_f360__doc-title"><h4 class="adt_f360__doc-name">' + esc(d.label) + '</h4>' +
                            '<span class="adt_f360__doc-req">' + (d.obligatorio ? 'Obligatorio' : 'Opcional') +
                            (d.archivos.length > 1 ? ' · ' + cargados + ' de ' + d.archivos.length + ' archivos' : '') + '</span></div>' +
                        badge(est[0], est[1]) +
                    '</header>' +
                    '<div class="adt_f360__doc-files' + (d.archivos.length > 1 ? ' is-multi' : '') + '">' + archivos + '</div>' +
                    (d.obs && d.estado === 'rechazado'
                        ? '<div class="adt_f360__doc-obs"><i class="fa fa-exclamation-circle" aria-hidden="true"></i><span>' + esc(d.obs) + '</span></div>'
                        : '') +
                    revision + '</article>';
            }).join('') + '</div>';
        },

        // Un archivo del documento: vista previa (o zona para subir) y barra con su lado, fecha y acciones.
        _htmlArchivo: function (d, a, ctx) {
            var ref = ctx.modelo + '|' + ctx.res_id + '|' + a.campo;
            var titulo = d.label + (a.lado ? ' - ' + a.lado : '');
            var ver = function (tipo) {
                return ' data-ver="' + esc(a.url) + '|' + tipo + '|' + esc(titulo) + '|' + esc(a.descarga) + '"';
            };
            var capa = '<span class="adt_f360__thumb-overlay"><span class="adt_f360__thumb-pill"><i class="fa fa-eye" aria-hidden="true"></i>Ver</span></span>';
            var vista;
            if (!a.cargado) {
                vista = '<button type="button" class="adt_f360__thumb is-empty" data-subir="' + ref + '" title="Subir ' + esc(titulo) + '">' +
                    '<span class="adt_f360__thumb-icon"><i class="fa fa-cloud-upload" aria-hidden="true"></i></span>' +
                    '<span class="adt_f360__thumb-cta">Subir archivo</span>' +
                    '<span class="adt_f360__thumb-note">o arrastra aquí</span></button>';
            } else if (a.imagen) {
                vista = '<button type="button" class="adt_f360__thumb"' + ver(1) + ' title="Ver ' + esc(titulo) + '">' +
                    '<img src="' + esc(a.miniatura) + '" alt="' + esc(titulo) + '" loading="lazy"/>' + capa + '</button>';
            } else {
                var pdf = a.mimetype === 'application/pdf';
                // Word no se puede previsualizar en el navegador: se descarga.
                vista = '<button type="button" class="adt_f360__thumb is-file' + (pdf ? ' is-pdf' : '') + (a.word ? ' is-word' : '') + '"' + ver(pdf ? 2 : 0) +
                    ' title="' + (pdf ? 'Ver ' : (a.word ? 'Descargar ' : 'Abrir ')) + esc(titulo) + '">' +
                    '<span class="adt_f360__thumb-page"><i class="fa ' + (pdf ? 'fa-file-pdf-o' : (a.word ? 'fa-file-word-o' : 'fa-file-o')) + '" aria-hidden="true"></i>' +
                        '<b>' + (pdf ? 'PDF' : (a.word ? 'Word' : 'Archivo')) + '</b></span>' +
                    '<span class="adt_f360__thumb-name">' + esc(a.nombre || titulo) + '</span>' +
                    (a.tamano ? '<span class="adt_f360__thumb-note">' + tamano(a.tamano) + '</span>' : '') +
                    (pdf ? capa : '') + '</button>';
            }
            var meta = (a.lado ? '<b>' + esc(a.lado) + '</b>' : '') + (a.cargado ? '<span>' + esc(fechaHora(a.fecha)) + '</span>' : '');
            return '<div class="adt_f360__file" data-subir-zona="' + ref + '">' + vista +
                (meta || a.cargado
                    ? '<div class="adt_f360__file-bar"><span class="adt_f360__file-meta">' + meta + '</span>' +
                      (a.cargado ? '<span class="adt_f360__file-actions">' +
                        '<button type="button" class="adt_f360__icon-btn is-small" data-subir="' + ref + '" title="Reemplazar"><i class="fa fa-refresh" aria-hidden="true"></i></button>' +
                        '<a class="adt_f360__icon-btn is-small" href="' + esc(a.descarga) + '" title="Descargar"><i class="fa fa-download" aria-hidden="true"></i></a>' +
                        '<button type="button" class="adt_f360__icon-btn is-small is-danger" data-quitar="' + ref + '" title="Quitar"><i class="fa fa-trash-o" aria-hidden="true"></i></button>' +
                      '</span>' : '') + '</div>'
                    : '') +
                '</div>';
        },

        _htmlCampos: function (campos) {
            if (!campos || !campos.length) {
                return '';
            }
            return '<dl class="adt_f360__fields">' + campos.map(function (c) {
                return '<div><dt>' + esc(c[0]) + '</dt><dd>' + esc(c[1]) + '</dd></div>';
            }).join('') + '</dl>';
        },

        _htmlKpis: function (kpis) {
            if (!kpis || !kpis.length) {
                return '';
            }
            return '<dl class="adt_f360__facts">' + kpis.map(function (k) {
                var valor = k.monto !== undefined ? soles(k.monto) : (k.fecha !== undefined ? fecha(k.fecha) : esc(k.texto));
                return '<div' + (k.nivel ? ' class="is-' + k.nivel + '"' : '') + '><dt>' + esc(k.label) + '</dt><dd>' + valor +
                    (k.sub ? ' <span class="adt_f360__muted">' + esc(k.sub) + '</span>' : '') + '</dd></div>';
            }).join('') + '</dl>';
        },

        // Documentos del expediente: rechazados (con observación) y sin cargar primero.
        _htmlDocumentos: function (docs) {
            if (!docs || !docs.length) {
                return '';
            }
            var NIV = {rechazado: ['critico', 'Rechazado'], aceptado: ['ok', 'Aceptado']};
            // Los no cargados se resumen en una línea: varios no aplican según el tipo de cliente.
            var faltan = docs.filter(function (d) { return d.estado === 'falta'; });
            var cargados = docs.filter(function (d) { return d.estado !== 'falta'; });
            return '<div class="adt_f360__label adt_f360__docs-title">Documentos</div>' +
                (cargados.length ? '<ul class="adt_f360__doclist">' + cargados.map(function (d) {
                    var n = NIV[d.estado];
                    return '<li class="is-' + d.estado + '"><span class="adt_f360__doclist-name">' + esc(d.label) + '</span>' +
                        estado(n[0], n[1]) + (d.obs ? '<div class="adt_f360__doclist-obs">' + esc(d.obs) + '</div>' : '') + '</li>';
                }).join('') + '</ul>' : '<p class="adt_f360__muted">Aún no se cargan documentos.</p>') +
                (faltan.length ? '<div class="adt_f360__doclist-missing"><b>Sin cargar:</b> ' +
                    faltan.map(function (d) { return esc(d.label); }).join(', ') + '</div>' : '');
        },

        _htmlItem: function (it) {
            return '<article class="adt_f360__item">' +
                '<div class="adt_f360__item-head"><div><span class="adt_f360__strong">' + esc(it.titulo) + '</span>' +
                (it.badge ? ' ' + badge(it.badge.nivel, it.badge.texto) : '') +
                (it.subtitulo ? '<div class="adt_f360__sub">' + esc(it.subtitulo) + '</div>' : '') + '</div>' +
                ((it.acciones && it.acciones.length) || (it.mas && it.mas.length)
                    ? '<div class="adt_f360__item-actions">' + this._acciones_html(it.acciones, ' is-small') +
                      this._menu(it.mas, 'Más', ' is-small') + '</div>' : '') +
                '</div>' +
                this._htmlKpis(it.kpis) +
                (it.nota ? '<div class="adt_f360__note">' + esc(it.nota) + '</div>' : '') +
                this._htmlDocumentos(it.documentos) +
                '</article>';
        },

        _htmlSeccion: function (s) {
            if (!s) {
                return '';
            }
            var self = this;
            var contenido = this._htmlCampos(s.campos);
            if (s.documentos && s.documentos.length) {
                contenido += '<div class="adt_f360__docs"><span class="adt_f360__label">Documentos</span>' + s.documentos.map(function (doc) {
                    return estado(doc.ok ? 'ok' : 'neutral', doc.label + (doc.ok ? '' : ' (falta)'));
                }).join('') + '</div>';
            }
            contenido += this._htmlKpis(s.kpis);
            if (s.items) {
                contenido += s.items.length
                    ? s.items.map(function (it) { return self._htmlItem(it); }).join('')
                    : '<p class="adt_f360__muted">' + esc(s.vacio || 'Sin registros.') + '</p>';
            } else if (s.vacio && !s.campos) {
                contenido += '<p class="adt_f360__muted">' + esc(s.vacio) + '</p>';
            }
            return this._panel(s.titulo, contenido, this._acciones_html(s.acciones, ' is-small'));
        },

        // ------------------------------------------------------------------
        // Render: papeletas (mismo detalle que su formulario)
        // ------------------------------------------------------------------

        // ------------------------------------------------------------------
        // Secciones con el patrón común
        // ------------------------------------------------------------------

        // Lista de filas (papeletas, capturas) dentro de una pestaña.
        _htmlFilasLista: function (items, fila, vacio) {
            return items.length ? '<ul class="adt_f360__paps is-flush">' + items.map(fila).join('') + '</ul>' : this._vacio(vacio, 'fa-check-circle');
        },

        _htmlPapeletas: function (s) {
            var self = this;
            var tarjeta = this._htmlTarjeta({frase: s.frase, cifras: s.cifras, acciones: s.acciones});
            if (!s.papeletas.length) {
                return tarjeta;
            }
            var pendientes = s.papeletas.filter(function (p) { return p.editable; });
            var pagadas = s.papeletas.filter(function (p) { return !p.editable; });
            var fila = function (p) { return self._htmlPapeletaFila(p); };
            return tarjeta + this._htmlPestanas('papeletas', [
                {key: 'pendientes', label: 'Pendientes', icon: 'fa-clock-o', n: pendientes.length, alerta: true},
                {key: 'pagadas', label: 'Pagadas', icon: 'fa-check-circle', n: pagadas.length},
            ], function (key) {
                return key === 'pagadas'
                    ? self._htmlFilasLista(pagadas, fila, 'Aún no hay papeletas pagadas.')
                    : self._htmlFilasLista(pendientes, fila, 'Sin papeletas pendientes.');
            }, pendientes.length ? 'pendientes' : 'pagadas');
        },

        _htmlCapturas: function (s) {
            var self = this;
            var tarjeta = this._htmlTarjeta({frase: s.frase, cifras: s.cifras, acciones: s.acciones});
            if (!s.capturas.length) {
                return tarjeta;
            }
            var activas = s.capturas.filter(function (c) { return c.activa; });
            var anteriores = s.capturas.filter(function (c) { return !c.activa; });
            var fila = function (c) { return self._htmlCapturaFila(c); };
            return tarjeta + this._htmlPestanas('capturas', [
                {key: 'activas', label: 'Activas', icon: 'fa-lock', n: activas.length, alerta: true},
                {key: 'anteriores', label: 'Anteriores', icon: 'fa-history', n: anteriores.length},
            ], function (key) {
                return key === 'anteriores'
                    ? self._htmlFilasLista(anteriores, fila, 'No hay capturas anteriores.')
                    : self._htmlFilasLista(activas, fila, 'El vehículo no está capturado.');
            }, activas.length ? 'activas' : 'anteriores');
        },

        _htmlTaller: function (s) {
            var self = this;
            var grupo = function (g) { return s.items.filter(function (i) { return i.grupo === g; }); };
            var abiertas = grupo('abiertas');
            var historial = grupo('historial');
            var preventivo = grupo('preventivo');
            var lista = function (items, vacio) {
                return items.length ? '<div class="adt_f360__pad">' + items.map(function (it) { return self._htmlItem(it); }).join('') + '</div>'
                    : self._vacio(vacio, 'fa-check-circle');
            };
            return this._htmlTarjeta({frase: s.frase, cifras: s.cifras, acciones: s.acciones}) + this._htmlPestanas('taller', [
                {key: 'abiertas', label: 'En taller', icon: 'fa-wrench', n: abiertas.length, alerta: true},
                preventivo.length && {key: 'preventivo', label: 'Preventivo', icon: 'fa-calendar-check-o', n: preventivo.length, alerta: true},
                {key: 'historial', label: 'Historial', icon: 'fa-history', n: historial.length},
            ].filter(Boolean), function (key) {
                if (key === 'preventivo') { return lista(preventivo, 'Sin mantenimientos preventivos pendientes.'); }
                if (key === 'historial') { return lista(historial, 'Sin órdenes terminadas.'); }
                return lista(abiertas, 'El vehículo no tiene órdenes abiertas.');
            }, abiertas.length ? 'abiertas' : (preventivo.length ? 'preventivo' : 'historial'));
        },

        _htmlPlacaSeccion: function (s) {
            var self = this;
            var tramite = _.findWhere(s.items, {clave: 'tramite'});
            var entrega = _.findWhere(s.items, {clave: 'entrega'});
            var tarjeta = this._htmlTarjeta({frase: s.frase});
            if (!tramite && !entrega) {
                return tarjeta;
            }
            return tarjeta + this._htmlPestanas('placa', [
                {key: 'tramite', label: 'Trámite de placa', icon: 'fa-id-card-o'},
                {key: 'entrega', label: 'Entrega', icon: 'fa-truck'},
            ], function (key) {
                var it = key === 'entrega' ? entrega : tramite;
                return it ? '<div class="adt_f360__pad">' + self._htmlItem(it) + '</div>'
                    : self._vacio(key === 'entrega' ? 'Sin seguimiento de entrega.' : 'Sin trámite de placa registrado.');
            }, tramite ? 'tramite' : 'entrega');
        },

        _htmlGpsSeccion: function (s) {
            if (!s.gps) {
                return this._htmlTarjeta({frase: {nivel: 'neutral', texto: 'Sin GPS registrado', detalle: s.vacio}, acciones: s.acciones});
            }
            var g = s.gps;
            var ICONO = {Velocidad: 'fa-tachometer', 'Batería': 'fa-battery-three-quarters', Km: 'fa-road', IMEI: 'fa-microchip'};
            var cifras = [{label: 'Último reporte', valor: hace(g.ultimo), icon: 'fa-clock-o', principal: true,
                           nivel: s.frase.nivel === 'ok' ? 'ok' : (s.frase.nivel === 'critico' ? 'critico' : ''),
                           sub: g.refrescado ? 'consultado ' + hace(g.refrescado) : ''}]
                .concat((s.kpis || []).filter(function (k) { return k.label !== 'IMEI'; }).map(function (k) {
                    return {label: k.label === 'Km' ? 'Kilometraje' : k.label, valor: k.texto, icon: ICONO[k.label] || 'fa-circle-o'};
                }));
            var imei = _.findWhere(s.kpis || [], {label: 'IMEI'});
            var mapa = '';
            if (g.lat && g.lon) {
                var d = 0.006;
                var bbox = [g.lon - d, g.lat - d, g.lon + d, g.lat + d].join(',');
                mapa = '<iframe class="adt_f360__map" loading="lazy" title="Ubicación del vehículo" ' +
                    'src="https://www.openstreetmap.org/export/embed.html?bbox=' + encodeURIComponent(bbox) +
                    '&amp;layer=mapnik&amp;marker=' + encodeURIComponent(g.lat + ',' + g.lon) + '"></iframe>';
            }
            return this._htmlTarjeta({frase: s.frase, cifras: cifras, acciones: s.acciones}) +
                '<section class="adt_f360__panel"><header class="adt_f360__panel-head"><h3><i class="fa fa-map-marker" aria-hidden="true"></i> Ubicación</h3>' +
                    (imei ? '<span class="adt_f360__muted adt_f360__mono">IMEI ' + esc(imei.texto) + '</span>' : '') + '</header>' +
                '<div class="adt_f360__panel-body">' + (g.direccion ? '<p class="adt_f360__gps-addr">' + esc(g.direccion) + '</p>' : '') +
                    (mapa || '<p class="adt_f360__muted">El equipo todavía no reportó una ubicación.</p>') + '</div></section>';
        },

        _htmlVehiculoSeccion: function (s) {
            var e = s.encabezado;
            var datos = '<section class="adt_f360__panel"><header class="adt_f360__panel-head"><h3>Datos del vehículo</h3></header>' +
                '<div class="adt_f360__panel-body adt_f360__cgroups">' + s.grupos.map(function (g) {
                    return '<section class="adt_f360__cgroup"><h4 class="adt_f360__cgroup-title"><i class="fa ' +
                        (g.titulo === 'Modelo' ? 'fa-motorcycle' : 'fa-barcode') + '" aria-hidden="true"></i>' + esc(g.titulo) + '</h4>' +
                        this._htmlCampos(g.campos) + '</section>';
                }, this).join('') + '</div></section>';
            return this._htmlTarjeta({icono: 'fa-motorcycle', titulo: e.titulo, ref: e.ref, chips: e.chips,
                                      frase: s.frase, cifras: s.cifras, acciones: s.acciones, menu: s.menu}) + datos;
        },

        _htmlPapeletaFila: function (p) {
            var monto = _.findWhere(p.kpis, {label: 'Monto'});
            var vence = _.findWhere(p.kpis, {label: 'Vence'});
            var n = p.evidencias.length + (p.fraccionamiento ? p.fraccionamiento.evidencias.length : 0);
            var alerta = p.alertas[0];
            return '<li class="adt_f360__papf is-' + p.badge.nivel + (p.id === this.papSel ? ' is-selected' : '') + '">' +
                '<button type="button" class="adt_f360__papf-btn" data-pap="' + p.id + '" title="Ver el detalle de la ' + esc(p.titulo.toLowerCase()) + '">' +
                    '<span class="adt_f360__papf-main">' +
                        '<span class="adt_f360__pap-title"><span class="adt_f360__strong">' + esc(p.titulo) + '</span>' +
                            badge(p.badge.nivel, p.badge.texto) +
                            p.marcas.map(function (m) { return badge(m.nivel, m.texto); }).join('') + '</span>' +
                        (alerta ? '<span class="adt_f360__papf-alert is-' + alerta.nivel + '">' + esc(alerta.texto) + '</span>'
                                : (p.detalle ? '<span class="adt_f360__sub adt_f360__papf-det">' + esc(p.detalle) + '</span>' : '')) +
                    '</span>' +
                    '<span class="adt_f360__papf-fig"><span class="adt_f360__strong">' + soles(monto ? monto.monto : 0) + '</span>' +
                        '<span class="adt_f360__sub">Vence ' + fecha(vence && vence.fecha) + '</span></span>' +
                    '<span class="adt_f360__papf-evid' + (n ? '' : ' is-empty') + '" title="' + plural(n, 'evidencia', 'evidencias') + '">' +
                        '<i class="fa fa-paperclip" aria-hidden="true"></i>' + n + '</span>' +
                    '<span class="adt_f360__papf-go">Ver detalle<i class="fa fa-angle-right" aria-hidden="true"></i></span>' +
                '</button></li>';
        },

        // Panel lateral con todo lo del formulario de la papeleta. Se vuelve a
        // dibujar con cada recarga, así refleja al instante pagos y ediciones.
        _htmlPanelPapeleta: function (seccion) {
            if (!this.papSel || this.tab !== 'papeletas' || !seccion || !seccion.papeletas) {
                return '';
            }
            var p = _.findWhere(seccion.papeletas, {id: this.papSel});
            if (!p) {
                this.papSel = null;
                return '';
            }
            var clave = 'pap' + p.id;
            var abierta = !!this.expandidas[clave];
            var cuerpo = p.alertas.map(function (a) {
                    return '<div class="adt_f360__note is-' + a.nivel + '">' + esc(a.texto) + '</div>';
                }).join('') +
                this._htmlKpis(p.kpis) +
                this._htmlCampos(p.campos) +
                (p.detalle ? '<div class="adt_f360__pap-block"><div class="adt_f360__label">Detalle</div>' +
                    '<p class="adt_f360__pap-text">' + esc(p.detalle) + '</p></div>' : '') +
                this._htmlEvidencias('Evidencia de papeleta', p.evidencias, p.editable && p.id) +
                (p.fraccionamiento ? this._htmlFraccionamiento(p) : '') +
                '<div class="adt_f360__pap-block">' +
                    '<button type="button" class="adt_f360__pap-toggle" data-expandir="' + clave + '" aria-expanded="' + abierta + '">' +
                        '<i class="fa fa-angle-' + (abierta ? 'down' : 'right') + '" aria-hidden="true"></i>' +
                        'Historial <span class="adt_f360__muted">(' + p.historial.length + ')</span></button>' +
                    (abierta ? (p.historial.length ? this._htmlHistorial(p.historial)
                        : '<p class="adt_f360__muted adt_f360__pad">Sin movimientos registrados.</p>') : '') +
                '</div>';
            var acciones = this._acciones_html(p.acciones, ' is-small') + this._menu(p.mas, 'Más', ' is-small');
            // Solo se anima al abrirlo, no en cada recarga.
            var entrada = this._papAnimar ? ' is-entering' : '';
            this._papAnimar = false;
            return '<div class="adt_f360__sheet-backdrop' + entrada + '" data-pap-close></div>' +
                '<aside class="adt_f360__sheet is-' + p.badge.nivel + entrada + '" role="dialog" aria-modal="true" aria-labelledby="adt_f360_pap_t">' +
                    '<header class="adt_f360__sheet-head">' +
                        '<div class="adt_f360__sheet-title"><h2 id="adt_f360_pap_t">' + esc(p.titulo) + '</h2>' +
                            '<div class="adt_f360__pap-title">' + badge(p.badge.nivel, p.badge.texto) +
                            p.marcas.map(function (m) { return badge(m.nivel, m.texto); }).join('') + '</div></div>' +
                        '<button type="button" class="adt_f360__icon-btn" data-pap-close title="Cerrar (Esc)">' +
                            '<i class="fa fa-times" aria-hidden="true"></i></button>' +
                    '</header>' +
                    (acciones ? '<div class="adt_f360__sheet-actions">' + acciones + '</div>' : '') +
                    '<div class="adt_f360__sheet-body">' + cuerpo + '</div>' +
                '</aside>';
        },

        // ------------------------------------------------------------------
        // Render: capturas (mismo detalle que su formulario)
        // ------------------------------------------------------------------

        _htmlCapturaFila: function (c) {
            var monto = _.findWhere(c.kpis, {label: 'Intervención'});
            var pago = _.findWhere(c.kpis, {label: 'Pago'});
            var captura = _.findWhere(c.kpis, {label: 'Fecha de captura'});
            var n = c.evidencias.length + c.documentos.length;
            var alerta = c.alertas[0];
            return '<li class="adt_f360__papf is-' + c.badge.nivel + (c.id === this.capSel ? ' is-selected' : '') + '">' +
                '<button type="button" class="adt_f360__papf-btn" data-cap="' + c.id + '" title="Ver el detalle de la ' + esc(c.titulo.toLowerCase()) + '">' +
                    '<span class="adt_f360__papf-main">' +
                        '<span class="adt_f360__pap-title"><span class="adt_f360__strong">' + esc(c.titulo) + '</span>' +
                            badge(c.badge.nivel, c.badge.texto) +
                            c.marcas.map(function (m) { return badge(m.nivel, m.texto); }).join('') + '</span>' +
                        (alerta ? '<span class="adt_f360__papf-alert is-' + alerta.nivel + '">' + esc(alerta.texto) + '</span>'
                                : '<span class="adt_f360__sub adt_f360__papf-det">Capturado el ' + fecha(captura && captura.fecha) + '</span>') +
                    '</span>' +
                    '<span class="adt_f360__papf-fig"><span class="adt_f360__strong">' + soles(monto ? monto.monto : 0) + '</span>' +
                        '<span class="adt_f360__sub">Pago ' + esc(((pago && pago.texto) || '').toLowerCase()) + '</span></span>' +
                    '<span class="adt_f360__papf-evid' + (n ? '' : ' is-empty') + '" title="' + plural(n, 'archivo', 'archivos') + '">' +
                        '<i class="fa fa-paperclip" aria-hidden="true"></i>' + n + '</span>' +
                    '<span class="adt_f360__papf-go">Ver detalle<i class="fa fa-angle-right" aria-hidden="true"></i></span>' +
                '</button></li>';
        },

        // Panel lateral con todo lo del formulario de la captura. Se vuelve a
        // dibujar con cada recarga, así refleja al instante pagos y liberaciones.
        _htmlPanelCaptura: function (seccion) {
            var self = this;
            if (!this.capSel || this.tab !== 'capturas' || !seccion || !seccion.capturas) {
                return '';
            }
            var c = _.findWhere(seccion.capturas, {id: this.capSel});
            if (!c) {
                this.capSel = null;
                return '';
            }
            var grupos = c.grupos.map(function (g) {
                return '<div class="adt_f360__pap-block"><div class="adt_f360__label">' + esc(g.titulo) + '</div>' +
                    self._htmlCampos(g.campos) +
                    g.textos.map(function (t) {
                        return '<div class="adt_f360__cap-text"><div class="adt_f360__sub">' + esc(t[0]) + '</div>' +
                            '<p class="adt_f360__pap-text">' + esc(t[1]) + '</p></div>';
                    }).join('') + '</div>';
            }).join('');
            var apelaciones = c.apelaciones.length
                ? '<div class="adt_f360__pap-block"><div class="adt_f360__label">Apelaciones (' + c.apelaciones.length + ')</div>' +
                    '<ul class="adt_f360__doclist">' + c.apelaciones.map(function (a) {
                        return '<li><span class="adt_f360__doclist-name">' + esc(a.motivo) + '</span>' +
                            (a.archivo ? '<a class="adt_f360__icon-btn is-small" href="' + esc(a.archivo.descarga) +
                                '" title="Descargar evidencia"><i class="fa fa-download" aria-hidden="true"></i></a>'
                                : '<span class="adt_f360__muted">Sin evidencia</span>') + '</li>';
                    }).join('') + '</ul></div>'
                : '';
            var cuerpo = c.alertas.map(function (a) {
                    return '<div class="adt_f360__note is-' + a.nivel + '">' + esc(a.texto) + '</div>';
                }).join('') +
                this._htmlKpis(c.kpis) +
                grupos +
                this._htmlEvidencias('Evidencias de la captura', c.evidencias, false) +
                (c.documentos.length ? this._htmlEvidencias('Voucher y documentos', c.documentos, false) : '') +
                apelaciones +
                this._htmlDesplegable('capc' + c.id, 'Cuotas pendientes', c.cuotas.length,
                    c.cuotas.length ? this._htmlCuotasCaptura(c.cuotas) : '<p class="adt_f360__muted adt_f360__pad">La cuenta no tiene cuotas pendientes.</p>') +
                this._htmlDesplegable('caph' + c.id, 'Historial', c.historial.length,
                    c.historial.length ? this._htmlHistorial(c.historial) : '<p class="adt_f360__muted adt_f360__pad">Sin movimientos registrados.</p>');
            var acciones = this._acciones_html(c.acciones, ' is-small') + this._menu(c.mas, 'Más', ' is-small');
            // Solo se anima al abrirlo, no en cada recarga.
            var entrada = this._capAnimar ? ' is-entering' : '';
            this._capAnimar = false;
            return '<div class="adt_f360__sheet-backdrop' + entrada + '" data-cap-close></div>' +
                '<aside class="adt_f360__sheet is-wide is-' + c.badge.nivel + entrada + '" role="dialog" aria-modal="true" aria-labelledby="adt_f360_cap_t">' +
                    '<header class="adt_f360__sheet-head">' +
                        '<div class="adt_f360__sheet-title"><h2 id="adt_f360_cap_t">' + esc(c.titulo) + '</h2>' +
                            '<div class="adt_f360__pap-title">' + badge(c.badge.nivel, c.badge.texto) +
                            c.marcas.map(function (m) { return badge(m.nivel, m.texto); }).join('') + '</div></div>' +
                        '<button type="button" class="adt_f360__icon-btn" data-cap-close title="Cerrar (Esc)">' +
                            '<i class="fa fa-times" aria-hidden="true"></i></button>' +
                    '</header>' +
                    (acciones ? '<div class="adt_f360__sheet-actions">' + acciones + '</div>' : '') +
                    '<div class="adt_f360__sheet-body">' + cuerpo + '</div>' +
                '</aside>';
        },

        // Bloque plegable (el contenido solo se arma si está abierto).
        _htmlDesplegable: function (clave, titulo, cantidad, contenido) {
            var abierta = !!this.expandidas[clave];
            return '<div class="adt_f360__pap-block">' +
                '<button type="button" class="adt_f360__pap-toggle" data-expandir="' + clave + '" aria-expanded="' + abierta + '">' +
                    '<i class="fa fa-angle-' + (abierta ? 'down' : 'right') + '" aria-hidden="true"></i>' +
                    esc(titulo) + ' <span class="adt_f360__muted">(' + cantidad + ')</span></button>' +
                (abierta ? contenido : '') + '</div>';
        },

        _htmlCuotasCaptura: function (cuotas) {
            return '<div class="adt_f360__table-wrap"><table class="adt_f360__dtable"><thead><tr>' +
                '<th>Cuota</th><th>Vence</th><th class="is-num">Monto</th><th class="is-num">Saldo</th><th>Estado</th>' +
                '<th class="is-num">Mora</th><th class="is-num">Días mora</th><th>Estado mora</th><th>Operación mora</th>' +
                '<th>Pagada el</th><th>Periodicidad</th><th>Asesora</th></tr></thead><tbody>' +
                cuotas.map(function (q) {
                    return '<tr><td class="adt_f360__strong">' + esc(q.nombre) + '</td><td>' + fecha(q.fecha) + '</td>' +
                        '<td class="is-num">' + soles(q.monto) + '</td><td class="is-num">' + soles(q.saldo) + '</td>' +
                        '<td>' + estado(q.nivel, q.estado) + '</td>' +
                        '<td class="is-num">' + (q.mora_total ? soles(q.mora_total) : '—') + '</td>' +
                        '<td class="is-num">' + (q.mora_dias || '—') + '</td>' +
                        '<td>' + esc(q.mora_estado || '—') + '</td><td>' + esc(q.mora_operacion || '—') + '</td>' +
                        '<td>' + (q.pago ? fecha(q.pago) : '—') + '</td>' +
                        '<td>' + esc(q.periodicidad || '—') + '</td><td>' + esc(q.asesora || '—') + '</td></tr>';
                }).join('') + '</tbody></table></div>';
        },

        // Galería de adjuntos: las imágenes se abren en el visor; el resto, en otra pestaña.
        _htmlEvidencias: function (titulo, evidencias, papeletaId) {
            var agregar = papeletaId
                ? this._accion({tipo: 'form', form: 'papeleta', res_id: papeletaId, params: {},
                                label: 'Agregar', icon: 'fa-cloud-upload'}, ' is-small')
                : '';
            var lista = evidencias.length
                ? '<div class="adt_f360__evid">' + evidencias.map(function (a) {
                    var ver = esc(a.url) + '|' + (a.imagen ? '1' : (a.mimetype === 'application/pdf' ? '2' : '0')) + '|' + esc(a.nombre) + '|' + esc(a.descarga);
                    var icono = a.mimetype === 'application/pdf' ? 'fa-file-pdf-o'
                        : (a.mimetype.indexOf('video/') === 0 ? 'fa-file-video-o' : 'fa-file-o');
                    return '<div class="adt_f360__file">' +
                        (a.imagen
                            ? '<button type="button" class="adt_f360__thumb" data-ver="' + ver + '" title="Ver ' + esc(a.nombre) + '">' +
                                '<img src="' + esc(a.miniatura) + '" alt="' + esc(a.nombre) + '" loading="lazy"/></button>'
                            : '<button type="button" class="adt_f360__thumb is-file" data-ver="' + ver + '" title="Abrir ' + esc(a.nombre) + '">' +
                                '<i class="fa ' + icono + '" aria-hidden="true"></i><span>' + esc(a.nombre) + '</span></button>') +
                        '<div class="adt_f360__evid-meta"><span class="adt_f360__muted" title="' + esc(a.nombre) + '">' + fechaHora(a.fecha) + '</span>' +
                            '<a class="adt_f360__icon-btn is-small" href="' + esc(a.descarga) + '" title="Descargar ' + esc(a.nombre) + '">' +
                            '<i class="fa fa-download" aria-hidden="true"></i></a></div>' +
                        '</div>';
                }).join('') + '</div>'
                : '<p class="adt_f360__muted">Sin evidencias cargadas.</p>';
            return '<div class="adt_f360__pap-block"><div class="adt_f360__pap-block-head"><div class="adt_f360__label">' + esc(titulo) +
                (evidencias.length ? ' (' + evidencias.length + ')' : '') + '</div>' + agregar + '</div>' + lista + '</div>';
        },

        _htmlFraccionamiento: function (p) {
            var self = this;
            var f = p.fraccionamiento;
            var resumen = f.total
                ? f.pagadas + ' de ' + f.total + ' cuotas pagadas' + (f.saldo ? ' · ' + soles(f.saldo) + ' por pagar' : '')
                : 'Cuotas sin generar' + (f.cantidad ? ' (' + plural(f.cantidad, 'cuota', 'cuotas') + ' desde ' + fecha(f.inicio) + '): usa Más › Generar cuotas.' : '; indica la cantidad en Editar.');
            var tabla = f.cuotas.length
                ? '<div class="adt_f360__table-wrap"><table class="adt_f360__dtable"><thead><tr>' +
                    '<th>Cuota</th><th>Vence</th><th class="is-num">Monto</th><th>Estado</th><th></th></tr></thead><tbody>' +
                    f.cuotas.map(function (c) {
                        return '<tr><td class="adt_f360__strong">' + esc(c.nombre) + '</td><td>' + fecha(c.fecha) + '</td>' +
                            '<td class="is-num">' + soles(c.monto) + '</td><td>' + estado(c.nivel, c.estado) + '</td>' +
                            '<td class="is-num">' + (c.accion ? self._accion(c.accion, ' is-small') : '') + '</td></tr>';
                    }).join('') + '</tbody></table></div>'
                : '';
            return '<div class="adt_f360__pap-block"><div class="adt_f360__label">Fraccionamiento</div>' +
                '<p class="adt_f360__sub adt_f360__pap-resumen">' + resumen + '</p>' + tabla + '</div>' +
                this._htmlEvidencias('Evidencias del fraccionamiento', f.evidencias, p.editable && p.id);
        },

        // ------------------------------------------------------------------
        // Render: deuda
        // ------------------------------------------------------------------

        // Crédito y cuotas: lista de cuentas por titular (si hay varias) y el resumen de una cuenta:
        // frase de estado, tres cifras, mapa de cuotas, pendientes y el detalle completo a pedido.
        // ------------------------------------------------------------------
        // Patrón común de las secciones: tarjeta (cabecera, frase de estado y
        // cifras), pestañas con contador y panel lateral para el detalle.
        // ------------------------------------------------------------------

        // o: {avatar | icono, pasado, empresa, titulo, ref, chips: [[icono, texto]], datos: [{icon, label, valor}],
        //     frase, cifras, acciones, menu (grupos), extra (HTML antes de las acciones), clase}
        // `datos` va en una franja con etiquetas bajo la cabecera.
        // La acción principal de cada sección va en naranja (accent).
        _htmlTarjeta: function (o) {
            var acciones = (o.extra || '') + this._acciones_html((o.acciones || []).map(function (a) {
                return a.primary ? _.extend({}, a, {primary: false, accent: true}) : a;
            })) + this._menuGrupos(o.menu, ' is-icon');
            var identidad = o.avatar !== undefined
                ? '<span class="adt_f360__avatar is-large' + (o.pasado ? ' is-past' : '') + (o.empresa ? ' is-company' : '') +
                  '" aria-hidden="true">' + esc(o.avatar) + '</span>'
                : (o.icono ? '<span class="adt_f360__hcard-icon" aria-hidden="true"><i class="fa ' + esc(o.icono) + '"></i></span>' : '');
            var cabecera = o.titulo
                ? '<header class="adt_f360__hcard-head">' + identidad +
                    '<div class="adt_f360__hcard-who"><h3>' + esc(o.titulo) +
                        (o.ref ? ' <span class="adt_f360__mono adt_f360__muted">' + esc(o.ref) + '</span>' : '') + '</h3>' +
                    ((o.chips || []).length ? '<div class="adt_f360__hcard-chips">' + o.chips.map(function (x) {
                        return '<span><i class="fa ' + esc(x[0]) + '" aria-hidden="true"></i>' + esc(x[1]) + '</span>';
                    }).join('') + '</div>' : '') + '</div>' +
                    (acciones ? '<div class="adt_f360__hcard-actions">' + acciones + '</div>' : '') + '</header>'
                : '';
            var datos = (o.datos || []).length ? '<dl class="adt_f360__hcard-facts">' + o.datos.map(function (x) {
                return '<div><dt><i class="fa ' + esc(x.icon) + '" aria-hidden="true"></i>' + esc(x.label) + '</dt><dd>' + esc(x.valor) + '</dd></div>';
            }).join('') + '</dl>' : '';
            // Sin título (la sección ya lo tiene arriba): la frase encabeza y las acciones van a su lado.
            var frase = o.frase ? this._htmlFrase(o.frase, !o.titulo && acciones ? acciones : '') : '';
            return '<section class="adt_f360__panel adt_f360__hcard' + (o.titulo ? '' : ' is-plain') + (o.clase ? ' ' + o.clase : '') + '">' +
                cabecera + datos + frase + this._htmlCifras(o.cifras) + '</section>';
        },

        _htmlFrase: function (f, acciones) {
            var ICONO = {critico: 'fa-exclamation-triangle', atencion: 'fa-exclamation-circle', ok: 'fa-check-circle', info: 'fa-info-circle'};
            return '<div class="adt_f360__status-row"><div class="adt_f360__status is-' + (f.nivel || 'neutral') + '" role="status">' +
                '<i class="fa ' + (ICONO[f.nivel] || 'fa-circle-o') + '" aria-hidden="true"></i>' +
                '<b>' + esc(f.texto) + '</b>' + (f.detalle ? '<span>' + esc(f.detalle) + '</span>' : '') + '</div>' +
                (acciones ? '<div class="adt_f360__hcard-actions">' + acciones + '</div>' : '') + '</div>';
        },

        // cifras: [{label, valor, icon, sub, nivel, principal, extra, detalle, title}]. La principal va resaltada;
        // `detalle` (HTML) se muestra en una fila a todo el ancho debajo de las cifras.
        _htmlCifras: function (cifras) {
            if (!cifras || !cifras.length) {
                return '';
            }
            var detalles = cifras.map(function (k) { return k.detalle || ''; }).join('');
            return '<div class="adt_f360__kpis is-' + cifras.length + '">' + cifras.map(function (k) {
                var cls = (k.principal ? ' is-hero' : '') + (k.nivel ? ' is-' + k.nivel : (k.principal ? ' is-neutral' : ''));
                return '<div class="adt_f360__kpi' + cls + '"' + (k.title ? ' title="' + esc(k.title) + '"' : '') + '>' +
                    '<span class="adt_f360__kpi-label"><i class="fa ' + esc(k.icon || 'fa-circle-o') + '" aria-hidden="true"></i>' + esc(k.label) + '</span>' +
                    '<b class="adt_f360__kpi-value">' + esc(k.valor) + '</b>' +
                    (k.sub ? '<span class="adt_f360__kpi-sub">' + esc(k.sub) + '</span>' : '') + (k.extra || '') + '</div>';
            }).join('') + (detalles ? '<div class="adt_f360__kpi-detail">' + detalles + '</div>' : '') + '</div>';
        },

        // pestanas: [{key, label, icon, n, alerta}]; render(key) devuelve el contenido.
        // La pestaña elegida se recuerda por `clave` mientras la ficha esté abierta.
        _htmlPestanas: function (clave, pestanas, render, defecto) {
            var actual = this.vistas[clave];
            if (!_.findWhere(pestanas, {key: actual})) {
                actual = defecto && _.findWhere(pestanas, {key: defecto}) ? defecto : pestanas[0].key;
            }
            var barra = '<div class="adt_f360__ptabs" role="tablist">' + pestanas.map(function (p) {
                return '<button type="button" role="tab" aria-selected="' + (actual === p.key) + '" class="adt_f360__ptab' +
                    (actual === p.key ? ' is-active' : '') + '" data-ptab="' + esc(p.key) + '" data-pclave="' + esc(clave) + '">' +
                    '<i class="fa ' + esc(p.icon) + '" aria-hidden="true"></i>' + esc(p.label) +
                    (p.n !== undefined ? '<span class="adt_f360__ptab-n' + (p.alerta && p.n ? ' is-alert' : '') + '">' + p.n + '</span>' : '') + '</button>';
            }).join('') + '</div>';
            return '<section class="adt_f360__panel adt_f360__ptabpanel">' + barra +
                '<div class="adt_f360__ptab-body" role="tabpanel">' + render(actual) + '</div></section>';
        },

        _vacio: function (texto, icono) {
            return '<div class="adt_f360__empty"><i class="fa ' + (icono || 'fa-inbox') + '" aria-hidden="true"></i><span>' + esc(texto) + '</span></div>';
        },

        // Crédito y cuotas: primero la lista de todas las cuentas que tuvo la moto (una por titular);
        // al elegir una se entra a su detalle.
        _htmlDeuda: function (s) {
            if (!s.deuda.length) {
                return this._panel('Cuentas de la moto', '<p class="adt_f360__muted">' + esc(s.vacio) + '</p>', this._acciones_html(s.acciones, ' is-small'));
            }
            var avisos = (s.avisos || []).map(function (t) {
                return '<div class="adt_f360__note is-critico adt_f360__acc-warn"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i> ' + esc(t) + '</div>';
            }).join('');
            var sel = _.findWhere(s.deuda, {id: this.cuentaSel});
            if (!sel) {
                this.cuentaSel = null;
                return avisos + this._htmlListaCuentas(s);
            }
            // Volver a la lista va en la misma línea que el título de la sección (_renderDrawer).
            this._tituloExtra = '<button type="button" class="adt_f360__btn is-small" data-cuenta-sel="0">' +
                    '<i class="fa fa-arrow-left" aria-hidden="true"></i>Todas las cuentas</button>' +
                (s.deuda.length > 1 ? '<span class="adt_f360__muted">Cuenta ' + (s.deuda.indexOf(sel) + 1) + ' de ' + s.deuda.length + '</span>' : '');
            return avisos + this._htmlCuenta(sel);
        },

        // Rentabilidad: lo que la moto recaudó con todos sus clientes, lo que falta cobrar al actual
        // (proyección) y el resultado tras restar lo que ADT paga a la financiera, explicado paso a paso.
        _htmlRentabilidad: function (s) {
            var t = s.totales;
            var creditos = s.creditos;
            var actual = _.find(creditos, function (c) { return c.vigente; });
            var frase = actual
                ? {nivel: 'info', texto: 'Proyección ' + soles(t.proyectado),
                   detalle: 'si ' + actual.titular + ' termina de pagar su cronograma · ' + plural(creditos.length, 'crédito', 'créditos') +
                       ' con ' + plural(t.clientes, 'cliente', 'clientes')}
                : {nivel: 'neutral', texto: 'Sin crédito vigente',
                   detalle: 'Recaudado con ' + plural(t.clientes, 'cliente', 'clientes') + ': no hay más por cobrar.'};
            var cifras = [
                {label: 'Recaudado a la fecha', valor: soles(t.recaudado), icon: 'fa-money', principal: true, nivel: 'ok',
                 sub: 'lo que ya pagaron los clientes'},
                {label: 'Por cobrar', valor: soles(t.por_cobrar), icon: 'fa-hourglass-half',
                 sub: actual ? 'lo que le falta pagar al cliente actual' : 'sin crédito vigente'},
                {label: 'Proyección total', valor: soles(t.proyectado), icon: 'fa-line-chart', sub: 'recaudado + por cobrar'},
                {label: 'Resultado proyectado', valor: soles(t.margen), icon: 'fa-balance-scale',
                 nivel: t.margen < 0 ? 'critico' : '', sub: 'proyección − pagos a la financiera'},
            ];

            // ¿Cómo se calcula? La cuenta completa, paso a paso, con cada monto y de dónde sale.
            var paso = function (signo, titulo, monto, explica, cls) {
                return '<li class="adt_f360__rent-step' + (cls ? ' ' + cls : '') + '">' +
                    '<span class="adt_f360__rent-op" aria-hidden="true">' + signo + '</span>' +
                    '<span class="adt_f360__rent-what"><b>' + esc(titulo) + '</b>' + (explica ? '<small>' + explica + '</small>' : '') + '</span>' +
                    '<span class="adt_f360__rent-amount">' + soles(monto) + '</span></li>';
            };
            var calculo = '<section class="adt_f360__panel adt_f360__rent-calc">' +
                '<header class="adt_f360__panel-head"><h3><i class="fa fa-calculator" aria-hidden="true"></i> ¿Cómo se calcula el resultado proyectado?</h3></header>' +
                '<ol class="adt_f360__rent-steps">' +
                    paso('', 'Recaudado a la fecha', t.recaudado,
                        'Lo que pagaron los ' + plural(t.clientes, 'cliente', 'clientes') + ' de esta moto: iniciales ' + esc(soles(t.inicial_cobrada)) +
                        ' + cuotas ' + esc(soles(t.cuotas_cobradas)) + ' + cargos y mora ' + esc(soles(t.cargos)) + '.') +
                    paso('+', 'Por cobrar', t.por_cobrar, actual
                        ? 'Lo que le falta pagar a ' + esc(actual.titular) + ' (' + esc(actual.referencia) + ') para terminar su cronograma.'
                        : 'No hay crédito vigente: no queda nada por cobrar.') +
                    paso('=', 'Proyección total', t.proyectado, 'Todo lo que la moto habrá recaudado si el cliente actual termina de pagar.', 'is-subtotal') +
                    paso('−', 'Pagos a la financiera', t.financiera, s.planes.length
                        ? 'Total del plan de pagos de la financiera por esta moto (capital + intereses + seguros y cargos), contado una vez: ' +
                          s.planes.map(function (p) {
                              return (p.financiera ? esc(p.financiera) + ' ' : '') + (p.solicitud ? 'solicitud N° ' + esc(p.solicitud) + ' ' : '') +
                                  esc(soles(p.total)) + (p.anteriores ? ' (incluye ' + plural(p.anteriores, 'cuota anterior al PDF estimada', 'cuotas anteriores al PDF estimadas') + ')' : '');
                          }).join('; ') + '.'
                        : 'La moto no tiene cargado el plan de pagos de la financiera.') +
                    paso('=', 'Resultado proyectado', t.margen, t.margen < 0
                        ? 'Lo que la moto deja después de pagarle a la financiera: es negativo, se recauda menos de lo que se le paga.'
                        : 'Lo que la moto deja después de pagarle a la financiera.', 'is-total' + (t.margen < 0 ? ' is-neg' : '')) +
                '</ol>' +
                (!s.planes.length ? '<p class="adt_f360__rent-warn"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i> ' +
                    'Sin el plan de la financiera no se resta nada y el resultado sale más alto de lo real. ' +
                    '<button type="button" class="adt_f360__btn is-small" data-tab="financiera">Cargarlo en Financiera</button></p>' : '') +
                '</section>';

            // Barras con una sola escala: riel = pactado, sólido = recaudado, claro = por cobrar.
            var escala = _.max(creditos.map(function (c) { return Math.max(c.pactado, c.proyectado); }).concat([1]));
            var pct = function (x) { return Math.max(x * 100 / escala, 0).toFixed(2) + '%'; };
            var barras = creditos.map(function (c) {
                return '<li class="adt_f360__rent-row' + (c.vigente ? ' is-current' : '') + '">' +
                    '<div class="adt_f360__rent-who"><span class="adt_f360__rent-n">' + c.orden + '</span>' +
                        '<span><span class="adt_f360__strong">' + esc(c.titular || 'Sin titular') + '</span>' +
                        '<span class="adt_f360__sub"><span class="adt_f360__mono">' + esc(c.referencia) + '</span> · ' +
                            fecha(c.desde) + ' – ' + (c.vigente ? 'hoy' : fecha(c.hasta)) + '</span></span>' +
                        badge(c.nivel, c.estado) + '</div>' +
                    '<div class="adt_f360__rent-bar" title="Pactado ' + esc(soles(c.pactado)) + ' · recaudado ' + esc(soles(c.recaudado)) +
                        (c.por_cobrar ? ' · por cobrar ' + esc(soles(c.por_cobrar)) : '') + '">' +
                        '<span class="adt_f360__rent-track" style="width:' + pct(c.pactado) + '"></span>' +
                        '<span class="adt_f360__rent-paid" style="width:' + pct(c.recaudado) + '"></span>' +
                        (c.por_cobrar ? '<span class="adt_f360__rent-due" style="left:' + pct(c.recaudado) + ';width:' + pct(c.por_cobrar) + '"></span>' : '') +
                    '</div>' +
                    '<div class="adt_f360__rent-num"><b>' + soles(c.recaudado) + '</b>' +
                        '<span class="adt_f360__sub">de ' + soles(c.pactado) + ' pactado · ' + c.pct + '%</span>' +
                        (c.por_cobrar ? '<span class="adt_f360__sub">Falta ' + soles(c.por_cobrar) + '</span>' : '') + '</div>' +
                    '</li>';
            }).join('');
            var leyenda = '<div class="adt_f360__rent-legend">' +
                '<span><i class="adt_f360__rent-key is-paid" aria-hidden="true"></i>Recaudado</span>' +
                '<span><i class="adt_f360__rent-key is-due" aria-hidden="true"></i>Por cobrar (proyección)</span>' +
                '<span><i class="adt_f360__rent-key is-track" aria-hidden="true"></i>Pactado en el cronograma</span></div>';
            var comparativo = '<section class="adt_f360__panel adt_f360__rent">' +
                '<header class="adt_f360__panel-head"><h3><i class="fa fa-bar-chart" aria-hidden="true"></i> Pactado vs. recaudado por crédito</h3>' +
                    '<span class="adt_f360__muted">' + plural(creditos.length, 'crédito', 'créditos') + ', del primero al actual</span></header>' +
                leyenda + '<ol class="adt_f360__rent-list">' + barras + '</ol></section>';

            var num = function (x) { return '<td class="is-num">' + soles(x) + '</td>'; };
            var tabla = '<section class="adt_f360__panel">' +
                '<header class="adt_f360__panel-head"><h3><i class="fa fa-table" aria-hidden="true"></i> Detalle por crédito</h3></header>' +
                '<div class="adt_f360__scroll-x"><table class="adt_f360__dtable adt_f360__rent-table"><thead><tr>' +
                    '<th>Crédito</th><th>Estado</th><th class="is-num">Inicial</th><th class="is-num">Cronograma</th><th class="is-num">Pactado</th>' +
                    '<th class="is-num">Recaudado</th><th class="is-num">%</th><th class="is-num">Por cobrar</th><th class="is-num">Proyectado</th>' +
                    '</tr></thead><tbody>' +
                    creditos.map(function (c) {
                        return '<tr><td><span class="adt_f360__strong">' + c.orden + '. ' + esc(c.titular || 'Sin titular') + '</span>' +
                            '<div class="adt_f360__sub adt_f360__mono">' + esc(c.referencia) + '</div></td>' +
                            '<td>' + badge(c.nivel, c.estado) + '</td>' + num(c.inicial) + num(c.cronograma) + num(c.pactado) +
                            '<td class="is-num adt_f360__strong">' + soles(c.recaudado) + '</td><td class="is-num">' + c.pct + '%</td>' +
                            num(c.por_cobrar) + num(c.proyectado) + '</tr>';
                    }).join('') + '</tbody><tfoot><tr><td colspan="2">Total del vehículo</td>' + num(t.inicial) + '<td></td>' + num(t.pactado) +
                    '<td class="is-num">' + soles(t.recaudado) + '</td><td class="is-num">' + (t.pactado ? Math.round(t.recaudado * 100 / t.pactado) : 0) + '%</td>' +
                    num(t.por_cobrar) + num(t.proyectado) + '</tr></tfoot></table></div></section>';

            var notas = '<ul class="adt_f360__rent-notes">' +
                '<li>La inicial se cuenta como pagada desde que la cuenta se aprueba (se paga al entregar la moto).</li>' +
                '<li>Pactado = inicial + total de las cuotas del cronograma ADT de cada crédito.</li></ul>';
            return this._htmlTarjeta({frase: frase, cifras: cifras}) + calculo + comparativo + tabla + notas;
        },

        _iniciales: function (nombre) {
            return (nombre || '').split(/\s+/).filter(Boolean).slice(0, 2).map(function (x) { return x[0]; }).join('').toUpperCase() || '?';
        },

        // Todas las cuentas de la moto, de la vigente a la más antigua: titular, periodo, cuotas,
        // saldo y cómo terminó (recuperada, pagada, anulada).
        _htmlListaCuentas: function (s) {
            var self = this;
            var abiertas = s.deuda.filter(function (c) { return c.vigente; }).length;
            var resumen = plural(s.deuda.length, 'cuenta', 'cuentas') +
                (abiertas ? ' · ' + plural(abiertas, 'abierta', 'abiertas') : ' · ninguna abierta') +
                (s.deuda.length - abiertas ? ' · ' + plural(s.deuda.length - abiertas, 'cerrada', 'cerradas') : '');
            var filas = s.deuda.map(function (c) {
                var f = c.cifras;
                var pct = f.total_cuotas ? Math.round(f.pagadas * 100 / f.total_cuotas) : 0;
                var saldo;
                if (c.state === 'borrador') {
                    saldo = ['', soles(f.financiado), 'por aprobar'];
                } else if (c.vigente) {
                    saldo = f.al_dia > 0 ? ['is-critico', soles(f.al_dia), 'vencido + mora'] : ['is-ok', 'Al día', soles(f.capital) + ' por pagar'];
                } else {
                    saldo = f.capital > 0 ? ['is-critico', soles(f.capital), 'quedó sin cobrar'] : ['is-ok', 'S/ 0.00', 'sin deuda'];
                }
                var periodo = c.periodo.desde ? fecha(c.periodo.desde) + ' – ' + (c.vigente ? 'hoy' : fecha(c.periodo.hasta)) : '—';
                return '<button type="button" class="adt_f360__accrow' + (c.vigente ? '' : ' is-closed') + ' is-' + c.situacion.nivel +
                        '" data-cuenta-sel="' + c.id + '" title="Ver la cuenta ' + esc(c.referencia) + '">' +
                    '<span class="adt_f360__accrow-who">' +
                        '<span class="adt_f360__avatar' + (c.vigente ? '' : ' is-past') + '" aria-hidden="true">' + esc(self._iniciales(c.titular.nombre)) + '</span>' +
                        '<span class="adt_f360__accrow-main">' +
                            '<span class="adt_f360__accrow-name">' + esc(c.titular.nombre || 'Sin titular') + '</span>' +
                            '<span class="adt_f360__accrow-meta">' + (c.titular.actual ? badge('ok', 'Dueño actual') : '') +
                                (c.titular.documento ? '<span>' + esc(c.titular.documento) + '</span>' : '') + '</span>' +
                        '</span></span>' +
                    '<span class="adt_f360__accrow-col" data-label="Cuenta"><span class="adt_f360__mono">' + esc(c.referencia) + '</span>' +
                        '<small><i class="fa fa-calendar" aria-hidden="true"></i>' + periodo + '</small></span>' +
                    '<span class="adt_f360__accrow-col" data-label="Cuotas pagadas"><span><b>' + f.pagadas + '</b> de ' + f.total_cuotas + '</span>' +
                        '<span class="adt_f360__minibar" aria-hidden="true"><span style="width:' + pct + '%"></span></span></span>' +
                    '<span class="adt_f360__accrow-col adt_f360__accrow-money ' + saldo[0] + '" data-label="Saldo"><b>' + esc(saldo[1]) + '</b><small>' + esc(saldo[2]) + '</small></span>' +
                    '<span class="adt_f360__accrow-col adt_f360__accrow-state" data-label="Estado">' + badge(c.situacion.nivel, c.situacion.texto) +
                        (c.situacion.detalle ? '<small>' + esc(c.situacion.detalle) + '</small>' : '') + '</span>' +
                    '<i class="fa fa-angle-right adt_f360__accrow-go" aria-hidden="true"></i>' +
                '</button>';
            }).join('');
            return '<section class="adt_f360__panel adt_f360__accounts">' +
                '<header class="adt_f360__panel-head"><h3><i class="fa fa-credit-card" aria-hidden="true"></i> Cuentas de la moto ' +
                    '<span class="adt_f360__muted">' + esc(resumen) + '</span></h3>' +
                    (s.acciones && s.acciones.length ? '<div class="adt_f360__panel-actions">' + this._acciones_html(s.acciones, ' is-small') + '</div>' : '') +
                '</header>' +
                '<div class="adt_f360__accrow-head" aria-hidden="true"><span>Titular</span><span>Cuenta</span><span>Cuotas pagadas</span>' +
                    '<span>Saldo</span><span>Estado</span><span></span></div>' +
                filas + '</section>';
        },

        _htmlCuenta: function (c) {
            return this._htmlTarjeta({
                avatar: this._iniciales(c.titular.nombre), pasado: !c.vigente,
                titulo: c.titular.nombre || 'Sin titular', ref: c.referencia, datos: c.condiciones,
                chips: [['fa-circle', c.situacion.texto]],
                frase: c.frase, cifras: this._cifrasCuenta(c),
                extra: (c.cobrar.length ? '<button type="button" class="adt_f360__btn is-accent" data-cobrar="' + c.id + '">' +
                    '<i class="fa fa-money" aria-hidden="true"></i><span>Cobrar</span></button>' : '') +
                    '<button type="button" class="adt_f360__btn" data-crono-ir="" data-cuenta="' + c.id + '" title="Pagar, refinanciar, agregar o eliminar cuotas y el historial de ajustes">' +
                    '<i class="fa fa-sliders" aria-hidden="true"></i><span>Gestionar cronograma</span></button>',
                clase: c.vigente ? '' : 'is-historic',
            }) + this._htmlPestanasCuenta(c);
        },

        // Tres cifras, una protagonista. El resto (capital, mora, mora registrada) en "Ver desglose".
        _cifrasCuenta: function (c) {
            var f = c.cifras;
            var k = function (label, valor, icon, sub, nivel, principal, extra, detalle) {
                return {label: label, valor: valor, icon: icon, sub: sub, nivel: nivel, principal: principal, extra: extra, detalle: detalle};
            };
            var proxima = c.proxima
                ? [soles(c.proxima.monto), fecha(c.proxima.fecha) + ' · ' + (c.proxima.dias === 0 ? 'hoy' : 'en ' + plural(c.proxima.dias, 'día', 'días'))]
                : ['—', 'Sin cuotas por vencer'];
            if (c.state === 'borrador') {
                return [k('Monto fraccionado', soles(f.financiado), 'fa-money'),
                        k('Monto de cuota', soles(f.cuota), 'fa-calendar', plural(f.total_cuotas, 'cuota', 'cuotas'))];
            }
            if (!c.vigente) {
                return [k('Pagado', soles(f.pagado), 'fa-check-circle', 'de ' + soles(f.financiado)),
                        k('Quedó sin cobrar', soles(f.capital), 'fa-exclamation-circle', '', f.capital > 0 ? 'critico' : 'ok', true),
                        k('Cuotas pagadas', f.pagadas + ' de ' + f.total_cuotas, 'fa-list-ol')];
            }
            var abierto = !!this.expandidas['desglose' + c.id];
            var desglose = '<button type="button" class="adt_f360__kpi-more" data-expandir="desglose' + c.id + '" aria-expanded="' + abierto + '">' +
                (abierto ? 'Ocultar desglose' : 'Ver desglose') + '<i class="fa fa-angle-' + (abierto ? 'up' : 'down') + '" aria-hidden="true"></i></button>';
            // El desglose ocupa una fila propia bajo las cifras (no dentro de la principal).
            var detalle = abierto ? '<dl class="adt_f360__kpi-breakdown">' + [
                ['Cuotas vencidas', soles(f.al_dia - f.mora), 'fa-calendar-times-o'],
                ['Mora a hoy', soles(f.mora), 'fa-hourglass-half'],
                ['Mora ya registrada', soles(f.mora_registrada), 'fa-file-text-o'],
                ['Capital pendiente', soles(f.capital), 'fa-money'],
            ].map(function (x) {
                return '<div><dt><i class="fa ' + x[2] + '" aria-hidden="true"></i>' + x[0] + '</dt><dd>' + x[1] + '</dd></div>';
            }).join('') + '</dl>' : '';
            var cancelar = k('Para cancelar hoy', soles(f.cancelar_hoy), 'fa-flag-checkered', 'todo el crédito');
            cancelar.title = f.cancelar_nota;
            return f.al_dia > 0
                ? [k('Para ponerse al día', soles(f.al_dia), 'fa-exclamation-triangle',
                     plural(f.vencidas, 'cuota vencida', 'cuotas vencidas') + (f.mora ? ' + mora' : ''), 'critico', true, desglose, detalle),
                   k('Próxima cuota', proxima[0], 'fa-clock-o', proxima[1]), cancelar]
                : [k('Próxima cuota', proxima[0], 'fa-clock-o', proxima[1], 'ok', true, desglose, detalle),
                   k('Pagado', soles(f.pagado), 'fa-check-circle', 'de ' + soles(f.financiado)), cancelar];
        },

        // Pestañas del detalle de la cuenta. Arriba queda siempre el estado y las tres cifras.
        _htmlPestanasCuenta: function (c) {
            var self = this;
            var pendientes = c.vigente && c.state !== 'borrador';
            var pestanas = [
                pendientes && {key: 'pendientes', label: 'Requiere atención', icon: 'fa-bolt', n: c.pendientes.length, alerta: true},
                {key: 'detalle', label: 'Detalle del crédito', icon: 'fa-file-text-o'},
                {key: 'documentos', label: 'Contrato y documentos', icon: 'fa-folder-open-o',
                 n: (c.ficha.documentos || []).length + (c.ficha.adjuntos || []).length},
                {key: 'pagos', label: 'Pagos', icon: 'fa-money', n: c.pagos.length},
                {key: 'historial', label: 'Historial', icon: 'fa-history', n: c.historial.length},
            ].filter(Boolean);
            return this._htmlPestanas('cuenta' + c.id, pestanas, function (key) {
                if (key === 'pendientes') { return self._htmlPendientes(c); }
                if (key === 'pagos') { return self._htmlPagos(c.pagos); }
                if (key === 'detalle') { return self._htmlDetalleCredito(c); }
                if (key === 'documentos') { return self._htmlDocumentosCuenta(c.ficha); }
                if (key === 'historial') { return self._htmlHistorial(c.historial); }
                return self._htmlDetalleCredito(c);
            }, pendientes && c.pendientes.length ? 'pendientes' : 'detalle');
        },

        // Pestañas adicionales de la cuenta ({key, label, icon, n, render}); las agregan otros módulos.
        _pestanasCuentaExtra: function () {
            return [];
        },

        // Detalle del crédito: solo lo pactado con el cliente (ADT). El plan de la financiera
        // está en la sección «Financiera» y los documentos en «Contrato y documentos».
        _htmlDetalleCredito: function (c) {
            var f = c.ficha;
            var a = f.avance;
            var lista = function (campos) {
                return '<dl class="adt_f360__cdetail-list">' + campos.map(function (x) {
                    return '<div><dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd></div>';
                }).join('') + '</dl>';
            };
            var tarjeta = function (titulo, icono, cuerpo) {
                return '<section class="adt_f360__cdetail-card"><h4 class="adt_f360__cgroup-title">' +
                    '<i class="fa ' + esc(icono) + '" aria-hidden="true"></i>' + esc(titulo) + '</h4>' + cuerpo + '</section>';
            };
            var adt = '<div class="adt_f360__cdetail-progress">' +
                    '<div class="adt_f360__cdetail-progress-head"><span class="adt_f360__label">Avance de pago del cliente</span>' +
                        '<span><b>' + soles(a.pagado) + '</b> de ' + soles(a.total) + ' · ' + a.pct + '%</span></div>' +
                    '<span class="adt_f360__minibar is-large" aria-hidden="true"><span style="width:' + Math.min(a.pct, 100) + '%"></span></span>' +
                    '<div class="adt_f360__sub">' + c.cifras.pagadas + ' de ' + plural(c.cifras.total_cuotas, 'cuota pagada', 'cuotas pagadas') + '</div></div>' +
                '<div class="adt_f360__cdetail-grid">' + f.grupos.map(function (g) {
                    return tarjeta(g.titulo, g.icon, lista(g.campos));
                }).join('') + '</div>';
            return '<div class="adt_f360__cdetail">' + adt + '</div>';
        },

        // Pestaña «Contrato y documentos»: contrato, cronograma impreso y adjuntos de la cuenta.
        _htmlDocumentosCuenta: function (f) {
            var self = this;
            var docs = f.documentos || [];
            var adjuntos = f.adjuntos || [];
            if (!docs.length && !adjuntos.length) {
                return this._vacio('La cuenta no tiene documentos.', 'fa-folder-open-o');
            }
            var filas = docs.map(function (a) {
                self._acciones.push(a);
                return '<button type="button" class="adt_f360__docrow" data-accion="' + (self._acciones.length - 1) + '">' +
                    '<span class="adt_f360__docrow-icon"><i class="fa ' + esc(a.icon || 'fa-file-o') + '" aria-hidden="true"></i></span>' +
                    '<span class="adt_f360__docrow-text"><span class="adt_f360__strong">' + esc(a.label) + '</span>' +
                        (a.descripcion ? '<span class="adt_f360__sub">' + esc(a.descripcion) + '</span>' : '') + '</span>' +
                    '<i class="fa fa-angle-right adt_f360__docrow-go" aria-hidden="true"></i></button>';
            }).join('');
            var archivos = adjuntos.length
                ? '<div class="adt_f360__cdetail-card"><h4 class="adt_f360__cgroup-title"><i class="fa fa-paperclip" aria-hidden="true"></i>' +
                    'Adjuntos de la cuenta · ' + adjuntos.length + '</h4><div class="adt_f360__evid">' + adjuntos.map(function (a) {
                        var ver = esc(a.url) + '|' + (a.imagen ? '1' : (a.mimetype === 'application/pdf' ? '2' : '0')) + '|' + esc(a.nombre) + '|' + esc(a.descarga);
                        return '<div class="adt_f360__file">' + (a.imagen
                            ? '<button type="button" class="adt_f360__thumb" data-ver="' + ver + '" title="Ver ' + esc(a.nombre) + '">' +
                                '<img src="' + esc(a.miniatura) + '" alt="' + esc(a.nombre) + '" loading="lazy"/></button>'
                            : '<button type="button" class="adt_f360__thumb is-file" data-ver="' + ver + '" title="Abrir ' + esc(a.nombre) + '">' +
                                '<i class="fa ' + (a.mimetype === 'application/pdf' ? 'fa-file-pdf-o' : 'fa-file-o') + '" aria-hidden="true"></i>' +
                                '<span>' + esc(a.nombre) + '</span></button>') +
                            '<div class="adt_f360__evid-meta"><span class="adt_f360__muted" title="' + esc(a.nombre) + '">' + fechaHora(a.fecha) + '</span>' +
                            '<a class="adt_f360__icon-btn is-small" href="' + esc(a.descarga) + '" title="Descargar ' + esc(a.nombre) + '">' +
                            '<i class="fa fa-download" aria-hidden="true"></i></a></div></div>';
                    }).join('') + '</div></div>'
                : '';
            return '<div class="adt_f360__cdocs-body">' + (filas ? '<div class="adt_f360__docrows">' + filas + '</div>' : '') + archivos + '</div>';
        },

        // Financiera: plan de pagos de la financiera de la moto (se financia una vez). Se sube el PDF,
        // se lee y genera su cronograma (adt_comercial); todas las cuentas de la moto lo usan.
        _htmlFinanciera: function (fin) {
            var ref = 'fleet.vehicle|' + fin.vehicle_id + '|cf_pdf';
            var de = fin.nombre ? ' de ' + esc(fin.nombre) : ' de la financiera';
            if (!fin.pdf.cargado) {
                return this._htmlTarjeta({frase: {nivel: 'atencion', texto: 'Sin plan de pagos',
                        detalle: 'Súbelo una sola vez: es de la moto y lo usan todas sus cuentas y la Rentabilidad.'}}) +
                    '<section class="adt_f360__panel"><div class="adt_f360__pad"><div class="adt_f360__fin-drop" data-subir-zona="' + ref + '">' +
                    '<i class="fa fa-file-pdf-o" aria-hidden="true"></i>' +
                    '<div><b>Sube el plan de pagos' + de + '</b>' +
                    '<span class="adt_f360__sub">PDF. Se lee automáticamente y genera el cronograma de la financiera.</span></div>' +
                    '<button type="button" class="adt_f360__btn is-small is-primary" data-subir="' + ref + '">' +
                        '<i class="fa fa-cloud-upload" aria-hidden="true"></i>Subir PDF</button>' +
                    '</div></div></section>';
            }
            var lectura = fin.lectura.estado
                ? badge(fin.lectura.estado === 'valido' ? 'ok' : 'atencion', 'Lectura ' + fin.lectura.texto.toLowerCase() +
                    (fin.lectura.confianza ? ' · ' + Math.round(fin.lectura.confianza) + '%' : ''))
                : '';
            var tarjeta = this._htmlTarjeta({
                frase: {nivel: 'info', texto: 'Plan de pagos' + de,
                        detalle: 'Es de la moto: lo usan todas sus cuentas.' + (fin.cuenta ? ' En los reportes lo lleva la cuenta ' + fin.cuenta + '.' : '')},
                cifras: [
                    {label: 'Total del plan', valor: soles(fin.total_plan), icon: 'fa-university', principal: true,
                     sub: fin.anteriores ? 'cuotas del PDF + ' + plural(fin.anteriores, 'cuota anterior estimada', 'cuotas anteriores estimadas')
                         : 'suma de las cuotas del PDF'},
                    {label: 'Cuotas en el PDF', valor: String(fin.cuotas.length), icon: 'fa-list-ol',
                     sub: fin.cuotas.length ? 'de la ' + fin.cuotas[0].nro + ' a la ' + fin.cuotas[fin.cuotas.length - 1].nro : ''},
                ],
            });
            var tabla = fin.cuotas.length
                ? '<div class="adt_f360__label adt_f360__fin-title">Cronograma de la financiera · ' + plural(fin.cuotas.length, 'cuota', 'cuotas') + '</div>' +
                  '<div class="adt_f360__scroll-x adt_f360__fin-table"><table class="adt_f360__dtable"><thead><tr><th>Cuota</th><th>Vence</th>' +
                    '<th class="is-num">Capital</th><th class="is-num">Interés</th><th class="is-num">Otros</th><th class="is-num">Total</th><th>Estado</th></tr></thead><tbody>' +
                    fin.cuotas.map(function (q) {
                        return '<tr><td class="adt_f360__strong">' + q.nro + '</td><td>' + fecha(q.fecha) + '</td>' +
                            '<td class="is-num">' + soles(q.capital) + '</td><td class="is-num">' + soles(q.interes) + '</td>' +
                            '<td class="is-num">' + (q.otros ? soles(q.otros) : '—') + '</td><td class="is-num adt_f360__strong">' + soles(q.total) + '</td>' +
                            '<td>' + esc(q.estado) + '</td></tr>';
                    }).join('') + '</tbody></table></div>'
                : '<p class="adt_f360__muted adt_f360__fin-empty">El PDF no generó cuotas. Revisa que sea el plan de pagos y usa «Volver a leer».</p>';
            return tarjeta + '<section class="adt_f360__panel"><div class="adt_f360__pad">' +
                '<div class="adt_f360__fin-file">' +
                    '<i class="fa fa-file-pdf-o" aria-hidden="true"></i>' +
                    '<div><b>' + esc(fin.pdf.nombre) + '</b><span class="adt_f360__sub">' +
                        (fin.nombre ? esc(fin.nombre) + ' · ' : '') + (fin.pdf.fecha ? 'cargado ' + fechaHora(fin.pdf.fecha) : '') + '</span></div>' +
                    lectura +
                    '<span class="adt_f360__fin-actions">' +
                        '<button type="button" class="adt_f360__btn is-small" data-ver="' + esc(fin.pdf.url) + '|2|' + esc(fin.pdf.nombre) + '|' + esc(fin.pdf.descarga) + '">' +
                            '<i class="fa fa-eye" aria-hidden="true"></i>Ver PDF</button>' +
                        '<button type="button" class="adt_f360__btn is-small" data-subir="' + ref + '" title="Subir otro PDF del plan de pagos">' +
                            '<i class="fa fa-cloud-upload" aria-hidden="true"></i>Reemplazar</button>' +
                        (fin.leer ? this._accion(fin.leer, ' is-small') : '') +
                    '</span>' +
                '</div>' +
                this._htmlCampos(fin.datos) + tabla + '</div></section>';
        },

        // Lo que hay que hacer hoy en la cuenta, cada cosa con un solo botón.
        _htmlPendientes: function (c) {
            var self = this;
            var lista = c.pendientes;
            var filas = _.indexBy(c.cuotas, 'id');
            if (!lista.length) {
                return '<div class="adt_f360__pad"><div class="adt_f360__allgood"><i class="fa fa-check-circle" aria-hidden="true"></i><b>Todo al día.</b> ' +
                    '<span>No hay cuotas vencidas ni pagos a cuenta por completar.</span></div></div>';
            }
            return '<ul class="adt_f360__todo">' + lista.map(function (p) {
                return '<li class="adt_f360__todo-item">' +
                    '<span class="adt_f360__todo-icon is-' + p.nivel + '"><i class="fa ' + esc(p.icon) + '" aria-hidden="true"></i></span>' +
                    (p.cuota
                        ? '<button type="button" class="adt_f360__todo-what" data-cuota="' + p.cuota + '" title="Ver la cuota">'
                        : '<span class="adt_f360__todo-what">') +
                        '<b>' + esc(p.titulo) + '</b><small>' + esc(p.detalle) + '</small>' + (p.cuota ? '</button>' : '</span>') +
                    '<div class="adt_f360__qactions">' + (p.accion ? self._accion(p.accion, ' is-small') : '') +
                        (p.cuota && filas[p.cuota] ? self._botonGestionar(c.id, p.cuota) : '') + '</div>' +
                    '</li>';
            }).join('') + '</ul>';
        },

        _htmlFiltroCrono: function (c) {
            var actual = this.filtroCrono[c.id] || 'por_cobrar';
            return '<div class="adt_f360__seg">' + FILTROS_CRONO.map(function (x) {
                return '<button type="button" class="' + (actual === x[0] ? 'is-active' : '') + '" data-crono="' + x[0] +
                    '" data-cuenta="' + c.id + '">' + x[1] + '</button>';
            }).join('') + '</div>';
        },

        // ------------------------------------------------------------------
        // Cronograma de pagos: centro de control. Todo lo que se hace sobre el cronograma
        // en un solo lugar: elegir una cuota y operar sobre ella, operaciones de la cuenta
        // (cobrar, cancelar el crédito, agregar cuotas, refinanciar, cerrar) e historial.
        // ------------------------------------------------------------------

        // Cuenta elegida en la lista de cuentas de la moto (como en «Crédito y cuotas»).
        _cuentaControl: function (s) {
            return _.findWhere(s.deuda || [], {id: this.cuentaSel}) || null;
        },

        _htmlControlCronograma: function (s) {
            if (!(s.deuda || []).length) {
                return this._panel('Cuentas de la moto', '<p class="adt_f360__muted">' + esc(s.vacio || 'El vehículo no tiene cuentas.') + '</p>',
                    this._acciones_html(s.acciones, ' is-small'));
            }
            var avisos = (s.avisos || []).map(function (t) {
                return '<div class="adt_f360__note is-critico adt_f360__acc-warn"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i> ' + esc(t) + '</div>';
            }).join('');
            // Primero la lista de cuentas de la moto; al elegir una, su cronograma.
            var c = this._cuentaControl(s);
            if (!c) {
                this.cuentaSel = null;
                return avisos + this._htmlListaCuentas(s);
            }
            this._tituloExtra = '<button type="button" class="adt_f360__btn is-small" data-cuenta-sel="0">' +
                    '<i class="fa fa-arrow-left" aria-hidden="true"></i>Todas las cuentas</button>' +
                (s.deuda.length > 1 ? '<span class="adt_f360__muted">Cuenta ' + (s.deuda.indexOf(c) + 1) + ' de ' + s.deuda.length + '</span>' : '');
            var q = this.cronoSel ? _.findWhere(c.cuotas, {id: this.cronoSel}) : null;
            if (!q) {
                this.cronoSel = null;
            }
            var pendientes = c.cuotas.filter(function (x) { return x.saldo > 0; });
            var vencidas = pendientes.filter(function (x) { return x.grupo === 'vencida'; });
            var cifra = function (etiqueta, valor, sub, nivel) {
                return '<div class="adt_f360__cc-kpi' + (nivel ? ' is-' + nivel : '') + '"><span>' + esc(etiqueta) + '</span><b>' + valor + '</b>' +
                    (sub ? '<small>' + sub + '</small>' : '') + '</div>';
            };
            // Encabezado: quién, cifras y, a la vista, todo lo que se puede hacer con la cuenta.
            var atrasada = vencidas.length > 0;
            var cabecera = '<section class="adt_f360__panel adt_f360__cc-head' + (atrasada ? ' is-atrasada' : '') + '">' +
                '<div class="adt_f360__cc-who"><span class="adt_f360__avatar" aria-hidden="true">' + esc(this._iniciales(c.titular.nombre)) + '</span>' +
                    '<div><b>' + esc(c.titular.nombre || 'Sin titular') + '</b> <span class="adt_f360__mono adt_f360__muted">' + esc(c.referencia) + '</span>' +
                    '<div class="adt_f360__sub">' + badge(c.nivel, c.estado) + '</div></div>' +
                    '<button type="button" class="adt_f360__btn is-small" data-detalle-abrir title="Condiciones, contrato, documentos, pagos, notas e historial de la cuenta">' +
                        '<i class="fa fa-file-text-o" aria-hidden="true"></i><span>Ver detalle del crédito</span></button>' +
                    this._acciones_html(s.acciones, ' is-small') + '</div>' +
                // Estado en una frase; en rojo si está atrasada.
                this._htmlFrase(c.frase) +
                '<div class="adt_f360__cc-kpis">' +
                    cifra('Deuda pendiente', soles(c.cifras.capital), plural(pendientes.length, 'cuota', 'cuotas') + ' por cobrar') +
                    cifra('Vencido', soles(c.cifras.al_dia), plural(vencidas.length, 'cuota vencida', 'cuotas vencidas') + (c.cifras.mora ? ' + mora' : ''), atrasada ? 'critico' : '') +
                    cifra('Mora', soles(c.cifras.mora), c.cifras.dias_atraso ? c.cifras.dias_atraso + ' días de atraso' : '', atrasada ? 'critico' : (c.cifras.mora ? 'atencion' : '')) +
                    cifra('Próxima cuota', c.proxima ? soles(c.proxima.monto) : '—', c.proxima ? fecha(c.proxima.fecha) : '') +
                    cifra('Para cancelar hoy', soles(c.cifras.cancelar_hoy), 'todo el crédito') +
                '</div>' + this._htmlCcCuenta(c) + '</section>';
            var tabla = '<section class="adt_f360__panel adt_f360__cc-main"><header class="adt_f360__panel-head"><h3>Cuotas</h3>' +
                '<div class="adt_f360__panel-actions">' + this._htmlFiltroCrono(c) + '</div></header>' + this._htmlCronogramaSel(c) + '</section>';
            return '<div class="adt_f360__cc">' + avisos + cabecera + tabla + '</div>';
        },

        // Tabla del cronograma con selección de cuota. Muestra las primeras cuotas y se amplía a pedido.
        _htmlCronogramaSel: function (c) {
            var self = this;
            var filtro = this.filtroCrono[c.id] || 'por_cobrar';
            var filas = c.cuotas.filter(function (q) {
                if (filtro === 'pagadas') { return q.grupo === 'pagada'; }
                if (filtro === 'por_cobrar') { return q.grupo === 'vencida' || q.grupo === 'a_cuenta' || q.grupo === 'por_vencer' || q.mora > 0; }
                return true;
            });
            if (!filas.length) {
                return '<p class="adt_f360__muted adt_f360__pad">' + (filtro === 'por_cobrar' ? 'No hay cuotas por cobrar en esta cuenta.' : 'Sin cuotas para mostrar.') + '</p>';
            }
            this.cronoVer = this.cronoVer || {};
            var limite = this.cronoVer[c.id] || CUOTAS_INICIO;
            var elegida = _.findIndex(filas, {id: this.cronoSel});
            if (elegida >= limite) {
                limite = elegida + 1;  // la cuota elegida siempre se ve
            }
            var visibles = filas.slice(0, limite);
            var t = {monto: 0, pagado: 0, saldo: 0, mora: 0};
            filas.forEach(function (q) { _.each(t, function (v, k) { t[k] += q[k] || 0; }); });
            var cuerpo = visibles.map(function (q) {
                var sel = q.id === self.cronoSel;
                var marcas = (q.reportes.length ? '<i class="fa fa-mobile is-info" title="Pago informado desde la app por validar"></i>' : '') +
                    (q.observaciones.length ? '<i class="fa fa-comment-o" title="' + q.observaciones.length + ' observación(es)"></i>' : '') +
                    (q.aviso ? '<i class="fa fa-info-circle is-info" title="' + esc(q.aviso) + '"></i>' : '');
                return '<tr class="is-' + q.grupo + (q.subcuota ? ' is-sub' : '') + (sel ? ' is-selected' : '') + '" data-crono-sel="' + q.id +
                    '" tabindex="0" aria-selected="' + sel + '">' +
                    '<td><span class="adt_f360__strong">' + esc(q.nombre) + '</span>' + (q.tipo ? ' ' + badge('info', q.tipo) : '') +
                        (marcas ? '<span class="adt_f360__marks">' + marcas + '</span>' : '') + '</td>' +
                    '<td>' + fecha(q.fecha) + '</td>' +
                    '<td class="is-num">' + soles(q.monto) + '</td>' +
                    '<td class="is-num">' + (q.pagado ? soles(q.pagado) : '<span class="adt_f360__muted">—</span>') + '</td>' +
                    '<td class="is-num adt_f360__strong">' + (q.saldo ? soles(q.saldo) : '—') + '</td>' +
                    '<td class="is-num">' + (q.mora ? '<span class="adt_f360__crono-mora">' + soles(q.mora) + '</span>' : '<span class="adt_f360__muted">—</span>') + '</td>' +
                    '<td>' + badge(q.nivel, q.estado + (q.grupo === 'vencida' && q.mora_dias ? ' · ' + q.mora_dias + ' d' : '')) + '</td>' +
                    '<td class="adt_f360__crono-pago">' + (q.pago_fecha ? fecha(q.pago_fecha) + (q.pago_ref ? '<small class="adt_f360__mono">' + esc(q.pago_ref) + '</small>' : '')
                        : '<span class="adt_f360__muted">—</span>') + '</td>' +
                    '<td class="adt_f360__cc-gcol"><button type="button" class="adt_f360__btn is-small is-primary" data-cuota-gestionar="' + q.id + '">' +
                        '<i class="fa fa-sliders" aria-hidden="true"></i><span>Gestionar pago</span></button></td></tr>';
            }).join('');
            var resto = filas.length - visibles.length;
            var mas = resto > 0 ? '<div class="adt_f360__cc-more"><span class="adt_f360__muted">Mostrando ' + visibles.length + ' de ' + filas.length + ' cuotas</span>' +
                '<button type="button" class="adt_f360__btn is-small" data-crono-ver="' + Math.min(visibles.length + CUOTAS_INICIO, filas.length) + '" data-cuenta="' + c.id + '">' +
                    '<i class="fa fa-angle-down" aria-hidden="true"></i><span>Ver ' + Math.min(CUOTAS_INICIO, resto) + ' más</span></button>' +
                (resto > CUOTAS_INICIO ? '<button type="button" class="adt_f360__btn is-small is-ghost" data-crono-ver="' + filas.length + '" data-cuenta="' + c.id + '">' +
                    '<span>Ver todas (' + filas.length + ')</span></button>' : '') + '</div>'
                : (filas.length > CUOTAS_INICIO ? '<div class="adt_f360__cc-more"><button type="button" class="adt_f360__btn is-small is-ghost" data-crono-ver="' + CUOTAS_INICIO +
                    '" data-cuenta="' + c.id + '"><i class="fa fa-angle-up" aria-hidden="true"></i><span>Ver menos</span></button></div>' : '');
            return '<div class="adt_f360__scroll-x"><table class="adt_f360__dtable adt_f360__crono2 adt_f360__cc-table"><thead><tr><th>Cuota</th><th>Vence</th>' +
                '<th class="is-num">Monto</th><th class="is-num">Pagado</th><th class="is-num">Saldo</th><th class="is-num">Mora</th><th>Estado</th>' +
                '<th>Último pago</th><th></th></tr></thead><tbody>' + cuerpo + '</tbody>' +
                '<tfoot><tr><td colspan="2">Total · ' + plural(filas.length, 'cuota', 'cuotas') + '</td><td class="is-num">' + soles(t.monto) +
                '</td><td class="is-num">' + soles(t.pagado) + '</td><td class="is-num">' + soles(t.saldo) + '</td><td class="is-num">' + soles(t.mora) +
                '</td><td colspan="3"></td></tr></tfoot></table></div>' + mas;
        },

        // Detalle del crédito en un panel lateral: condiciones, contrato (ver y subir), documentos, pagos y notas.
        _htmlPanelDetalle: function (seccion) {
            if (!this.detAbierto || this.tab !== 'cronograma' || !seccion || !seccion.deuda) {
                return '';
            }
            var self = this, c = this._cuentaControl(seccion);
            if (!c) {
                return '';
            }
            var entrada = this._detAnimar ? ' is-entering' : '';
            this._detAnimar = false;
            var contrato = c.ficha.contrato;
            var pestanas = [
                {key: 'detalle', label: 'Detalle', icon: 'fa-file-text-o'},
                contrato !== null && contrato !== undefined && {key: 'contrato', label: 'Contrato', icon: 'fa-file-pdf-o', n: contrato.length},
                {key: 'documentos', label: 'Documentos', icon: 'fa-folder-open-o', n: (c.ficha.documentos || []).length + (c.ficha.adjuntos || []).length},
                {key: 'pagos', label: 'Pagos', icon: 'fa-money', n: c.pagos.length},
                {key: 'notas', label: 'Notas', icon: 'fa-comments-o', n: c.historial.length},
            ].filter(Boolean).concat(this._pestanasCuentaExtra(c).map(function (x) {
                // Historial de ajustes y refinanciamientos (adt_cobranza_ajustes).
                return _.extend({}, x, {label: 'Historial', icon: 'fa-history'});
            }));
            return '<div class="adt_f360__sheet-backdrop' + entrada + '" data-detalle-cerrar></div>' +
                '<aside class="adt_f360__sheet is-wide' + entrada + '" role="dialog" aria-modal="true" aria-labelledby="adt_f360_det_t">' +
                    '<header class="adt_f360__sheet-head"><div class="adt_f360__sheet-title"><h2 id="adt_f360_det_t">Detalle del crédito</h2>' +
                        '<div class="adt_f360__pap-title">' + badge(c.nivel, c.estado) + '<span class="adt_f360__muted">' + esc(c.titular.nombre || '') + '</span>' +
                        '<span class="adt_f360__muted adt_f360__mono">' + esc(c.referencia) + '</span></div></div>' +
                        '<button type="button" class="adt_f360__icon-btn" data-detalle-cerrar title="Cerrar (Esc)"><i class="fa fa-times" aria-hidden="true"></i></button>' +
                    '</header>' +
                    '<div class="adt_f360__sheet-body adt_f360__det-body">' + this._htmlPestanas('det' + c.id, pestanas, function (key) {
                        var extra = _.findWhere(pestanas, {key: key});
                        if (extra && extra.render) { return '<div class="adt_f360__hist-body">' + extra.render() + '</div>'; }
                        if (key === 'contrato') { return self._htmlContrato(c); }
                        if (key === 'documentos') { return self._htmlDocumentosCuenta(c.ficha); }
                        if (key === 'pagos') { return self._htmlPagos(c.pagos); }
                        if (key === 'notas') { return self._htmlHistorial(c.historial); }
                        return self._htmlDetalleCredito(c);
                    }, contrato && !contrato.length ? 'contrato' : 'detalle') + '</div>' +
                '</aside>';
        },

        // Contrato firmado: los archivos cargados y la zona para subir otro (PDF o Word).
        _htmlContrato: function (c) {
            var archivos = c.ficha.contrato || [];
            var lista = archivos.length ? '<div class="adt_f360__evid">' + archivos.map(function (a) {
                var ver = esc(a.url) + '|' + (a.imagen ? '1' : (a.mimetype === 'application/pdf' ? '2' : '0')) + '|' + esc(a.nombre) + '|' + esc(a.descarga);
                return '<div class="adt_f360__file"><button type="button" class="adt_f360__thumb is-file" data-ver="' + ver + '" title="Abrir ' + esc(a.nombre) + '">' +
                        '<i class="fa ' + (a.mimetype === 'application/pdf' ? 'fa-file-pdf-o' : 'fa-file-word-o') + '" aria-hidden="true"></i><span>' + esc(a.nombre) + '</span></button>' +
                    '<div class="adt_f360__evid-meta"><span class="adt_f360__muted">' + fechaHora(a.fecha) + '</span>' +
                        '<a class="adt_f360__icon-btn is-small" href="' + esc(a.descarga) + '" title="Descargar ' + esc(a.nombre) + '"><i class="fa fa-download" aria-hidden="true"></i></a>' +
                        '<button type="button" class="adt_f360__icon-btn is-small is-danger" data-contrato-quitar="' + a.id + '" data-cuenta="' + c.id + '" title="Quitar del contrato">' +
                        '<i class="fa fa-trash-o" aria-hidden="true"></i></button></div></div>';
            }).join('') + '</div>' : '<p class="adt_f360__contrato-vacio"><i class="fa fa-exclamation-circle" aria-hidden="true"></i>Aún no se ha cargado el contrato firmado por el cliente.</p>';
            return '<div class="adt_f360__contrato">' + lista +
                '<div class="adt_f360__contrato-zona" data-contrato-zona="' + c.id + '">' +
                    '<i class="fa fa-cloud-upload" aria-hidden="true"></i><span>Arrastra aquí el contrato firmado o</span>' +
                    '<button type="button" class="adt_f360__btn is-primary is-small" data-contrato-subir="' + c.id + '"><i class="fa fa-upload" aria-hidden="true"></i>' +
                        '<span>' + (archivos.length ? 'Subir otro archivo' : 'Subir contrato') + '</span></button>' +
                    '<small>PDF o Word (.doc / .docx)</small></div></div>';
        },

        _onDetalleAbrir: function () {
            this.detAbierto = true;
            this._detAnimar = true;
            this.cuotaSel = null;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__sheet [data-detalle-cerrar]').last().trigger('focus');
        },

        _onDetalleCerrar: function () {
            this.detAbierto = false;
            this._renderDrawer();
            this._ref('drawer').find('[data-detalle-abrir]').trigger('focus');
        },

        _onContratoSubir: function (ev) {
            ev.stopPropagation();
            this._subirA = {contrato: parseInt(ev.currentTarget.getAttribute('data-contrato-subir'), 10)};
            this._ref('archivo').attr('accept', '.pdf,.doc,.docx,application/pdf').val('').trigger('click');
        },

        _subirContrato: function (cuentaId, archivo) {
            var self = this;
            if (!/\.(pdf|docx?)$/i.test(archivo.name)) {
                this.displayNotification({type: 'danger', title: 'Formato no admitido', message: 'El contrato debe ser PDF o Word (.doc / .docx).'});
                return Promise.resolve();
            }
            var $zona = this.$('[data-contrato-zona="' + cuentaId + '"]').addClass('is-loading');
            return leerArchivo(archivo).then(function (leido) {
                return self._llamar('subir_contrato', {vehicle_id: self._drawerId, cuenta_id: cuentaId, nombre: leido.nombre, datos: leido.datos});
            }).then(function () {
                self.displayNotification({type: 'success', message: 'Contrato cargado.'});
                self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                $zona.removeClass('is-loading');
                self.displayNotification({type: 'danger', title: 'No se pudo cargar', message: err instanceof Error ? err.message : self._error(err)});
            });
        },

        _onContratoQuitar: function (ev) {
            var self = this, el = ev.currentTarget;
            var cuenta = parseInt(el.getAttribute('data-cuenta'), 10), adjunto = parseInt(el.getAttribute('data-contrato-quitar'), 10);
            Dialog.confirm(this, '¿Quitar este archivo del contrato? Queda registrado en las notas de la cuenta.', {
                title: 'Quitar del contrato',
                confirm_callback: function () {
                    return self._llamar('quitar_contrato', {vehicle_id: self._drawerId, cuenta_id: cuenta, adjunto_id: adjunto}).then(function () {
                        self._recargar();
                    }).catch(function (err) {
                        if (err && err.event) { err.event.preventDefault(); }
                        self.displayNotification({type: 'danger', title: 'No se pudo quitar', message: self._error(err)});
                    });
                },
            });
        },

        // «Gestionar pago» de una fila (o clic en la fila): abre el panel con todo lo que se puede hacer con la cuota.
        _onCuotaGestionar: function (ev) {
            ev.stopPropagation();
            var id = parseInt(ev.currentTarget.getAttribute('data-cuota-gestionar') || ev.currentTarget.getAttribute('data-crono-sel'), 10);
            if (!id) {
                return;
            }
            this.cronoSel = id;
            this.cuotaSel = id;
            this.detAbierto = false;
            this._cuotaAnimar = true;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__sheet [data-cuota-close]').last().trigger('focus');
        },

        // Operación como tarjeta: icono, nombre y qué hace. Más visible que un botón plano.
        _accionTarjeta: function (a, desc) {
            this._acciones.push(a);
            desc = a.descripcion || desc;
            return '<button type="button" class="adt_f360__act' + (a.danger ? ' is-danger' : '') + (a.sugerida || a.primary ? ' is-main' : '') +
                '" data-accion="' + (this._acciones.length - 1) + '"><span class="adt_f360__act-ico"><i class="fa ' + esc(a.icon || 'fa-circle-o') + '" aria-hidden="true"></i></span>' +
                '<span class="adt_f360__act-txt"><b>' + esc(a.label) + '</b>' + (desc ? '<small>' + esc(desc) + '</small>' : '') + '</span></button>';
        },

        // Todas las operaciones de una cuota, agrupadas, para el panel «Gestionar pago».
        _htmlOpsCuota: function (q) {
            var self = this, grupos = {};
            q.acciones.concat(q.mas).forEach(function (a) {
                var clave = a.method || (a.params && a.params.tipo) || '';
                var info = OP_CUOTA[clave] || [a.danger ? 'quitar' : 'otros', ''];
                (grupos[info[0]] = grupos[info[0]] || []).push(self._accionTarjeta(a, info[1]));
            });
            return GRUPOS_CUOTA.filter(function (g) { return grupos[g[0]]; }).map(function (g) {
                return '<div class="adt_f360__qops-g' + (g[0] === 'quitar' ? ' is-danger' : '') + '"><div class="adt_f360__label">' + g[1] + '</div>' +
                    '<div class="adt_f360__qops-b">' + grupos[g[0]].join('') + '</div></div>';
            }).join('');
        },

        // Operaciones de la cuenta en el encabezado, agrupadas: cobrar, cronograma, documentos y cierre.
        _htmlCcCuenta: function (c) {
            var self = this;
            var grupos = [];
            if (c.cobrar.length) {
                grupos.push({titulo: 'Cobrar', acciones: c.cobrar});
            }
            (c.menu || []).forEach(function (g) { grupos.push(g); });
            if (c.acciones.length) {
                grupos.push({titulo: c.state === 'borrador' ? 'Cuenta' : 'Documentos', acciones: c.acciones});
            }
            // Lo irreversible (cerrar la cuenta) al final.
            grupos = _.sortBy(grupos.filter(function (g) { return g.acciones.length; }), function (g) {
                return _.every(g.acciones, function (a) { return a.danger; }) ? 1 : 0;
            });
            if (!grupos.length) {
                return '';
            }
            return '<div class="adt_f360__cc-ops-head">' + grupos.map(function (g) {
                var peligro = _.every(g.acciones, function (a) { return a.danger; });
                return '<div class="adt_f360__cc-group is-span-' + Math.min(g.acciones.length, 4) + (peligro ? ' is-danger' : '') + '"><div class="adt_f360__cc-group-t">' + esc(g.titulo) + '</div>' +
                    '<div class="adt_f360__cc-group-b">' + g.acciones.map(function (a) { return self._accionTarjeta(a); }).join('') + '</div></div>';
            }).join('') + '</div>';
        },

        _onCronoVer: function (ev) {
            this.cronoVer = this.cronoVer || {};
            this.cronoVer[ev.currentTarget.getAttribute('data-cuenta')] = parseInt(ev.currentTarget.getAttribute('data-crono-ver'), 10);
            this._renderDrawer();
        },

        _onCronoSel: function (ev) {
            return this._onCuotaGestionar(ev);
        },

        _onCronoSelKey: function (ev) {
            if (ev.target === ev.currentTarget && (ev.key === 'Enter' || ev.key === ' ')) {
                ev.preventDefault();
                this._onCronoSel(ev);
            }
        },


        // Abre el centro de control (con la cuota elegida, si viene).
        _onCronoIr: function (ev) {
            ev.stopPropagation();
            var cuota = parseInt(ev.currentTarget.getAttribute('data-crono-ir'), 10) || null;
            var cuenta = parseInt(ev.currentTarget.getAttribute('data-cuenta'), 10) || null;
            this._irA('cronograma');
            this.cuentaSel = cuenta;
            this.cronoSel = cuota;
            this.cuotaSel = cuota;
            this._cuotaAnimar = !!cuota;
            if (cuota) {
                // Que la cuota se vea aunque el filtro «Por cobrar» la ocultara.
                var s = _.findWhere(this.detalle.secciones, {key: 'cuentas'});
                var c = s && _.findWhere(s.deuda, {id: cuenta});
                var q = c && _.findWhere(c.cuotas, {id: cuota});
                if (q && q.grupo === 'pagada') {
                    this.filtroCrono[cuenta] = 'todas';
                }
            }
            this._renderDrawer();
            var $fila = this._ref('drawer').find('tr[data-crono-sel="' + cuota + '"]');
            if ($fila.length) {
                $fila[0].scrollIntoView({block: 'center'});
                $fila.trigger('focus');
            }
        },

        // Panel lateral de una cuota: montos, pagos, observaciones, reportes de la app y sus acciones.
        _htmlPanelCuota: function (seccion) {
            if (!this.cuotaSel || (this.tab !== 'cuentas' && this.tab !== 'cronograma') || !seccion || !seccion.deuda) {
                return '';
            }
            var q = null;
            var cuenta = null;
            seccion.deuda.forEach(function (c) {
                var x = _.findWhere(c.cuotas, {id: this.cuotaSel});
                if (x) { q = x; cuenta = c; }
            }, this);
            if (!q) {
                this.cuotaSel = null;
                return '';
            }
            var entrada = this._cuotaAnimar ? ' is-entering' : '';
            this._cuotaAnimar = false;
            var dato = function (cls, etiqueta, valor) {
                return '<div' + (cls ? ' class="' + cls + '"' : '') + '><dt>' + esc(etiqueta) + '</dt><dd>' + valor + '</dd></div>';
            };
            var hechos = '<dl class="adt_f360__qfacts">' +
                dato(q.saldo ? 'is-strong' : '', 'Saldo', q.saldo ? soles(q.saldo) : '—') +
                dato(q.grupo === 'vencida' ? 'is-critico' : '', 'Vence', fecha(q.fecha)) +
                dato(q.mora ? 'is-critico' : '', 'Mora a hoy', q.mora ? soles(q.mora) + ' <small>' + q.mora_dias + ' d</small>' : '—') +
                dato('', 'Monto', soles(q.monto)) +
                dato('', 'Pagado', q.pagado ? soles(q.pagado) : '—') +
                dato('', 'Mora registrada', q.mora_registrada ? soles(q.mora_registrada) : '—') +
                '</dl>';
            var self = this;
            var reportes = q.reportes.length ? '<div class="adt_f360__qblock"><div class="adt_f360__label">Pago informado desde la app</div>' +
                q.reportes.map(function (r) {
                    return '<div class="adt_f360__qreport"><i class="fa fa-mobile" aria-hidden="true"></i><div>' +
                        '<b>' + soles(r.monto) + (r.operacion ? ' · op. ' + esc(r.operacion) : '') + '</b>' +
                        '<span class="adt_f360__sub">' + fechaHora(r.fecha) + ' · ' + plural(r.comprobantes, 'comprobante', 'comprobantes') +
                        (r.mora ? ' · mora ' + soles(r.mora) : '') + '</span>' +
                        (r.comentario ? '<span class="adt_f360__sub">' + esc(r.comentario) + '</span>' : '') +
                        '<div class="adt_f360__qreport-actions">' + self._acciones_html(r.acciones, ' is-small') + '</div></div></div>';
                }).join('') + '</div>' : '';
            var pagos = '<div class="adt_f360__qblock"><div class="adt_f360__label">Pagos aplicados</div>' +
                (q.pagos.length ? this._htmlPagos(q.pagos, true) : '<p class="adt_f360__muted">Sin pagos registrados.</p>') + '</div>';
            var obs = '<div class="adt_f360__qblock"><div class="adt_f360__label">Observaciones</div>' + (q.observaciones.length
                ? '<ul class="adt_f360__obs">' + q.observaciones.map(function (o) {
                    return '<li><span class="adt_f360__muted">' + fecha(o.fecha) + '</span> ' + esc(o.texto) +
                        (o.adjuntos ? ' <span class="adt_f360__muted">· ' + plural(o.adjuntos, 'adjunto', 'adjuntos') + '</span>' : '') + '</li>';
                }).join('') + '</ul>'
                : '<p class="adt_f360__muted">Sin observaciones.</p>') + '</div>';
            // En el cronograma, el panel es «Gestionar pago»: todas las operaciones de la cuota.
            var gestion = this.tab === 'cronograma';
            var acciones = gestion ? '' : this._acciones_html(q.acciones, ' is-small') + this._botonGestionar(cuenta.id, q.id);
            var operaciones = gestion ? '<div class="adt_f360__qblock adt_f360__qops"><div class="adt_f360__qops-t">¿Qué quieres hacer con esta cuota?</div>' +
                this._htmlOpsCuota(q) + '</div>' : '';
            return '<div class="adt_f360__sheet-backdrop' + entrada + '" data-cuota-close></div>' +
                '<aside class="adt_f360__sheet is-' + q.nivel + entrada + '" role="dialog" aria-modal="true" aria-labelledby="adt_f360_cuota_t">' +
                    '<header class="adt_f360__sheet-head">' +
                        '<div class="adt_f360__sheet-title"><h2 id="adt_f360_cuota_t">' + (gestion ? 'Gestionar pago · ' : '') + esc(q.nombre) + '</h2>' +
                            '<div class="adt_f360__pap-title">' + badge(q.nivel, q.estado) + (q.tipo ? badge('info', q.tipo) : '') +
                            (q.reportes.length ? badge('info', 'Pago informado en la app') : '') +
                            '<span class="adt_f360__muted adt_f360__mono">' + esc(cuenta.referencia) + '</span></div></div>' +
                        '<button type="button" class="adt_f360__icon-btn" data-cuota-close title="Cerrar (Esc)">' +
                            '<i class="fa fa-times" aria-hidden="true"></i></button>' +
                    '</header>' +
                    (acciones ? '<div class="adt_f360__sheet-actions">' + acciones + '</div>' : '') +
                    '<div class="adt_f360__sheet-body">' + (q.aviso ? '<p class="adt_f360__qaviso"><i class="fa fa-info-circle" aria-hidden="true"></i>' +
                        esc(q.aviso) + '</p>' : '') + hechos + operaciones + reportes + pagos + obs + '</div>' +
                '</aside>';
        },

        _htmlPagos: function (pagos, compacto) {
            if (!pagos.length) {
                return '<p class="adt_f360__muted adt_f360__pad">Sin pagos registrados.</p>';
            }
            var total = 0;
            var filas = pagos.map(function (p) {
                total += p.monto;
                return '<tr><td>' + fecha(p.fecha) + '</td>' + (compacto ? '' : '<td>' + esc(p.cuota) + '</td>') +
                    '<td class="is-num">' + soles(p.monto) + '</td><td class="adt_f360__mono">' + esc(p.ref || '—') + '</td>' +
                    '<td>' + esc(p.diario) + '</td>' +
                    '<td class="is-num">' + (p.mora ? soles(p.mora) : '—') + '</td>' +
                    '<td>' + (p.mora_estado ? badge(p.mora_estado === 'Pagada' ? 'ok' : 'atencion', 'Mora ' + p.mora_estado.toLowerCase()) : '') + '</td></tr>';
            }).join('');
            return '<div class="adt_f360__scroll-x"><table class="adt_f360__dtable"><thead><tr><th>Fecha</th>' + (compacto ? '' : '<th>Cuota</th>') +
                '<th class="is-num">Monto</th><th>Operación</th><th>Diario</th><th class="is-num">Mora</th><th></th></tr></thead><tbody>' + filas + '</tbody>' +
                (compacto ? '' : '<tfoot><tr><td colspan="2">' + plural(pagos.length, 'pago', 'pagos') + '</td><td class="is-num">' + soles(total) +
                    '</td><td colspan="4"></td></tr></tfoot>') + '</table></div>';
        },

        _htmlHistorial: function (eventos) {
            if (!eventos.length) {
                return this._vacio('Sin movimientos registrados.', 'fa-history');
            }
            return '<ol class="adt_f360__timeline">' + eventos.map(function (e) {
                return '<li><div class="adt_f360__timeline-meta">' + (e.autor ? '<b>' + esc(e.autor) + '</b>' : '') +
                        '<span>' + fechaHora(e.fecha) + '</span></div>' +
                    (e.texto ? '<p class="adt_f360__timeline-text">' + esc(e.texto) + '</p>' : '') +
                    (e.cambios.length ? '<ul class="adt_f360__changes">' + e.cambios.map(function (c) {
                        return '<li>' + esc(c) + '</li>';
                    }).join('') + '</ul>' : '') + '</li>';
            }).join('') + '</ol>';
        },

        // ------------------------------------------------------------------
        // Operaciones
        // ------------------------------------------------------------------

        _recargar: function () {
            this._listaSucia = true;
            if (this._drawerId && this.$el.hasClass('is-drawer-open')) {
                return this._cargarDetalle(this._drawerId);
            }
        },

        _ejecutar: function (a) {
            var self = this;
            var alCerrar = {on_close: function () { self._recargar(); }};
            if (a.tipo === 'url') {
                window.open(a.url, a.url.indexOf('tel:') === 0 ? '_self' : '_blank', 'noopener');
                return;
            }
            if (a.tipo === 'form') {
                this._abrirForm(a.form, a.res_id, a.params);
                return;
            }
            if (a.tipo === 'credito') {
                this._abrirCredito(a.cuenta_id);
                return;
            }
            if (a.tipo === 'tab') {
                this._irA(a.tab);
                return;
            }
            if (a.tipo === 'abrir') {
                this.do_action({
                    type: 'ir.actions.act_window',
                    res_model: a.model,
                    res_id: a.res_id || undefined,
                    views: [[false, 'form']],
                    target: 'new',
                    context: a.context || {},
                }, alCerrar);
                return;
            }
            var correr = function () {
                // Misma ruta que los botones de los formularios: el servidor normaliza
                // la acción devuelta (clean_action) para que el cliente pueda abrirla.
                return self._rpc({
                    route: '/web/dataset/call_button',
                    params: {
                        model: a.model,
                        method: a.method,
                        args: a.args || [[a.res_id]],
                        kwargs: {context: session.user_context},
                    },
                }).then(function (res) {
                    // Recargar la página entera sacaría al usuario de la ficha: basta con refrescarla.
                    if (res && res.type === 'ir.actions.client' && res.tag === 'reload') {
                        res = true;
                    }
                    if (res && typeof res === 'object' && res.type) {
                        return self.do_action(res, alCerrar);
                    }
                    self.displayNotification({type: 'success', message: a.label + ': operación registrada.'});
                    self._recargar();
                });
            };
            if (a.confirm) {
                Dialog.confirm(this, a.confirm, {confirm_callback: correr, title: a.label});
            } else {
                correr();
            }
        },

        _irA: function (tab) {
            this.tab = tab;
            this.papSel = null;
            this.capSel = null;
            this.cuotaSel = null;
            this.detAbierto = false;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__db').scrollTop(0);
        },

        _error: function (err) {
            var data = err && err.message && err.message.data;
            return (data && (data.message || data.arguments && data.arguments[0])) ||
                (err && err.message && err.message.message) || 'No se pudo completar la operación.';
        },

        // Llamada al servidor que muestra el error en el modal (en lugar del diálogo de Odoo).
        _llamar: function (method, kwargs) {
            return this._rpc({model: 'adt.flota360', method: method, kwargs: kwargs}, {shadow: true});
        },

        // ------------------------------------------------------------------
        // Modal propio de la vista
        // ------------------------------------------------------------------

        // modal.lateral: se abre como panel a la derecha (formularios largos).
        _mostrarModal: function (modal, html) {
            this._vigilarDesborde();
            this._modal = modal;
            this._ref('modal').html(
                '<div class="adt_f360__modal-backdrop" data-modal-close></div>' +
                '<div class="adt_f360__modal' + (modal.ancho ? ' is-wide' : '') + (modal.lateral ? ' is-side' : '') +
                '" role="dialog" aria-modal="true" aria-labelledby="adt_f360_modal_t">' +
                html + '</div>').addClass('is-open').toggleClass('is-side', !!modal.lateral);
            var $primero = this._ref('modal').find('input:not([type=hidden]):not([type=file]), select, textarea').first();
            ($primero.length ? $primero : this._ref('modal').find('[data-modal-close]').last()).trigger('focus');
        },

        // Marca las zonas desplazables del modal que tienen contenido más abajo (aviso «Hay más abajo»).
        _vigilarDesborde: function () {
            if (this._obsModal) {
                return;
            }
            var raiz = this._ref('modal')[0];
            var marcar = _.throttle(function () {
                $(raiz).find('.adt_f360__modal-body, .adt_f360__modal-side, .adt_f360__ajlines').each(function () {
                    var mas = this.scrollHeight - this.scrollTop - this.clientHeight > 8;
                    var arriba = this.scrollTop > 8;
                    if (this.classList.contains('has-more') !== mas) {
                        this.classList.toggle('has-more', mas);
                    }
                    if (this.classList.contains('has-above') !== arriba) {
                        this.classList.toggle('has-above', arriba);
                    }
                });
            }, 100);
            this._marcarDesborde = marcar;
            raiz.addEventListener('scroll', marcar, true);
            window.addEventListener('resize', marcar);
            this._obsModal = new MutationObserver(marcar);
            this._obsModal.observe(raiz, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
        },

        // forzar === true: cierre tras guardar (sin preguntar por cambios pendientes).
        // forzar === 'descartar': el usuario ya confirmó descartar; se cierra y se respeta modal.volver.
        // modal.volver: al cancelar se regresa a donde se abrió (p. ej. el asistente de crédito).
        _cerrarModal: function (forzar) {
            var self = this;
            if (!this._modal) {
                return;
            }
            if (forzar !== true && forzar !== 'descartar' && this._modal.tipo === 'form' && this._modal.sucio) {
                Dialog.confirm(this, 'Tienes cambios sin guardar en «' + this._modal.spec.titulo + '». ¿Descartarlos?', {
                    title: 'Descartar cambios',
                    confirm_callback: function () { self._cerrarModal('descartar'); },
                });
                return;
            }
            var volver = forzar !== true && this._modal.volver;
            this._modal = null;
            this._ref('modal').removeClass('is-open is-side').empty();
            if (volver) {
                volver();
            }
        },

        _modalCabecera: function (titulo, ayuda) {
            return '<header class="adt_f360__modal-head"><div><h2 id="adt_f360_modal_t">' + esc(titulo) + '</h2>' +
                (ayuda ? '<p>' + esc(ayuda) + '</p>' : '') + '</div>' +
                '<button type="button" class="adt_f360__icon-btn" data-modal-close title="Cerrar (Esc)"><i class="fa fa-times" aria-hidden="true"></i></button></header>';
        },

        _modalPie: function (botones) {
            return '<footer class="adt_f360__modal-foot"><div class="adt_f360__modal-error" data-ref="modal-error" role="alert"></div>' +
                '<button type="button" class="adt_f360__btn" data-modal-close>Cancelar</button>' + botones + '</footer>';
        },

        // Pie del asistente: el error arriba a todo el ancho; abajo, a la izquierda volver/cancelar
        // y a la derecha las acciones que avanzan (la principal al final).
        _pieAsistente: function (inicio, fin) {
            return '<footer class="adt_f360__modal-foot is-wizard">' +
                '<div class="adt_f360__modal-error" data-ref="modal-error" role="alert"></div>' +
                '<div class="adt_f360__wfoot"><div class="adt_f360__wfoot-start">' + inicio + '</div>' +
                '<div class="adt_f360__wfoot-end">' + fin + '</div></div></footer>';
        },

        _modalError: function (texto) {
            this._ref('modal').find('[data-ref="modal-error"]').text(texto || '');
            this._ref('modal').find('[data-guardar]').prop('disabled', false).removeClass('is-loading');
        },

        // ------------------------------------------------------------------
        // Formularios genéricos (descritos por el servidor)
        // ------------------------------------------------------------------

        // opciones: {volver, alGuardar(res)} para formularios abiertos desde otro (alta de cliente del crédito).
        _abrirForm: function (clave, resId, params, opciones) {
            var self = this;
            opciones = opciones || {};
            return this._llamar('formulario', {
                clave: clave, vehicle_id: this._drawerId, res_id: resId || false, params: params || {},
            }).then(function (spec) {
                var valores = _.clone(spec.valores);
                var nuevo = !spec.res_id;
                self._mostrarModal({tipo: 'form', spec: spec, valores: valores, params: params || {}, archivos: {},
                                    lateral: spec.lateral, sucio: false, volver: opciones.volver, alGuardar: opciones.alGuardar},
                    self._modalCabecera(spec.titulo, spec.ayuda) +
                    (spec.clave === 'cliente' ? '<div class="adt_f360__fpreview" data-ref="fpreview"></div>' : '') +
                    '<form class="adt_f360__modal-body" novalidate="novalidate">' +
                    spec.secciones.map(function (sec, i) {
                        return '<section class="adt_f360__fieldset" data-fsec="' + i + '">' + (sec.titulo
                            ? '<h3 class="adt_f360__legend"><i class="fa ' + (ICONO_SECCION[sec.titulo] || 'fa-circle-o') +
                              '" aria-hidden="true"></i>' + esc(sec.titulo) + '</h3>' : '') +
                            '<div class="adt_f360__form-grid">' + sec.campos.map(function (c) {
                                return self._htmlInput(c, valores[c.name]);
                            }).join('') + '</div></section>';
                    }).join('') + '<button type="submit" class="d-none"></button></form>' +
                    self._modalPie('<button type="button" class="adt_f360__btn is-primary" data-guardar>' +
                        '<i class="fa fa-check" aria-hidden="true"></i><span>' +
                        (nuevo && spec.clave === 'cliente' ? 'Crear cliente' : 'Guardar') + '</span></button>'));
                self._aplicarVisibilidad();
                self._actualizarForm();
            }).guardedCatch(function (err) {
                self.displayNotification({type: 'danger', title: 'No disponible', message: self._error(err)});
                if (err && err.event) { err.event.preventDefault(); }
                if (opciones.volver) { opciones.volver(); }
            });
        },

        _htmlInput: function (c, valor) {
            var id = 'f360_' + c.name;
            var req = c.required ? ' required="required" aria-required="true"' : '';
            var ph = c.placeholder ? ' placeholder="' + esc(c.placeholder) + '"' : '';
            var attrs = ' id="' + id + '" name="' + c.name + '" data-campo="' + c.name + '" aria-describedby="' + id + '_err"' + req;
            var control;
            switch (c.type) {
                case 'text':
                    control = '<textarea class="adt_f360__input" rows="3"' + attrs + ph + '>' + esc(valor || '') + '</textarea>';
                    break;
                case 'date':
                    control = '<input type="date" class="adt_f360__input"' + attrs + ' value="' + esc(valor || '') + '"/>';
                    break;
                case 'datetime':
                    control = '<input type="datetime-local" class="adt_f360__input"' + attrs + ' value="' + esc(utcALocal(valor)) + '"/>';
                    break;
                case 'float': case 'monetary': case 'integer':
                    control = '<input type="number" class="adt_f360__input is-num"' + attrs + ph + ' step="' + (c.type === 'integer' ? '1' : '0.01') +
                        '" value="' + esc(valor === false || valor === undefined ? '' : valor) + '"/>';
                    break;
                case 'selection':
                    // Pocas opciones: botones segmentados (un clic, todas a la vista).
                    if (c.segmentado) {
                        control = '<div class="adt_f360__seg is-block" role="radiogroup" aria-labelledby="' + id + '_lbl">' +
                            (c.options || []).map(function (o) {
                                var activo = String(o[0]) === String(valor);
                                return '<button type="button" role="radio" aria-checked="' + activo + '"' + (activo ? ' class="is-active"' : '') +
                                    ' data-seg-campo="' + c.name + '" data-seg-valor="' + esc(o[0]) + '">' + esc(o[1]) + '</button>';
                            }).join('') + '</div>';
                        break;
                    }
                    control = '<select class="adt_f360__input"' + attrs + '>' + (c.required ? '' : '<option value="">—</option>') +
                        (c.options || []).map(function (o) {
                            return '<option value="' + esc(o[0]) + '"' + (String(o[0]) === String(valor) ? ' selected="selected"' : '') + '>' + esc(o[1]) + '</option>';
                        }).join('') + '</select>';
                    break;
                case 'boolean':
                    return '<label class="adt_f360__check' + (c.col === 2 ? ' is-full' : '') + '" data-campo-wrap="' + c.name + '">' +
                        '<input type="checkbox"' + attrs + (valor ? ' checked="checked"' : '') + '/><span>' + esc(c.label) + '</span></label>';
                case 'many2one':
                    control = '<div class="adt_f360__m2o" data-m2o="' + c.name + '" data-model="' + esc(c.model) + '">' +
                        '<i class="fa fa-search adt_f360__m2o-icon" aria-hidden="true"></i>' +
                        '<input type="text" class="adt_f360__input" autocomplete="off" role="combobox" aria-expanded="false" aria-autocomplete="list"' +
                            attrs + ' value="' + esc(valor ? valor[1] : '') + '" placeholder="' + esc(c.placeholder || 'Buscar…') + '"/>' +
                        '<button type="button" class="adt_f360__m2o-clear" data-m2o-limpiar="' + c.name + '" title="Quitar" tabindex="-1">' +
                            '<i class="fa fa-times" aria-hidden="true"></i></button>' +
                        '<ul class="adt_f360__m2o-list" role="listbox"></ul></div>';
                    break;
                case 'file':
                    control = '<input type="file" class="adt_f360__input" accept="' + esc(c.accept || ACEPTA_DOCUMENTO) + '"' + attrs + '/>' +
                        (valor ? '<span class="adt_f360__help">Ya hay un archivo cargado; elige otro para reemplazarlo.</span>' : '');
                    break;
                case 'adjuntos':
                    control = '<input type="file" multiple="multiple" class="adt_f360__input" accept="image/*,application/pdf,video/*"' + attrs + '/>' +
                        '<span class="adt_f360__help">Puedes seleccionar varios archivos (máx. ' + MAX_ARCHIVO_MB + ' MB c/u).</span>';
                    break;
                default:
                    control = '<input type="' + (c.input || 'text') + '" class="adt_f360__input"' + attrs + ph +
                        (c.input === 'tel' ? ' inputmode="tel"' : '') + ' value="' + esc(valor || '') + '"/>';
            }
            return '<div class="adt_f360__field' + (c.col === 2 ? ' is-full' : '') + '" data-campo-wrap="' + c.name + '">' +
                '<label for="' + id + '" id="' + id + '_lbl">' + esc(c.label) + (c.required ? ' <span class="adt_f360__req" aria-hidden="true">*</span>' : '') + '</label>' +
                control + (c.help && c.type !== 'adjuntos' ? '<span class="adt_f360__help">' + esc(c.help) + '</span>' : '') +
                '<span class="adt_f360__ferr" id="' + id + '_err" role="alert"></span></div>';
        },

        // Campos condicionados: visible = [campo] (si tiene valor) o [campo, valor].
        // Listas encadenadas (c.filtros): deshabilitadas hasta elegir el campo del que dependen.
        _aplicarVisibilidad: function () {
            var self = this;
            var m = this._modal;
            if (!m || m.tipo !== 'form') {
                return;
            }
            var $modal = this._ref('modal');
            m.spec.secciones.forEach(function (sec) {
                sec.campos.forEach(function (c) {
                    if (c.visible) {
                        var v = m.valores[c.visible[0]];
                        // visible = [campo], [campo, valor] o [campo, [valores]].
                        var ok = c.visible.length < 2 ? !!v : (_.isArray(c.visible[1])
                            ? _.contains(c.visible[1].map(String), String(v)) : String(v) === String(c.visible[1]));
                        $modal.find('[data-campo-wrap="' + c.name + '"]').toggleClass('d-none', !ok);
                    }
                    if (c.type === 'many2one' && c.filtros) {
                        var padre = _.find(_.values(c.filtros), function (n) { return !m.valores[n]; });
                        var spec = padre && self._specCampo(padre);
                        $modal.find('[data-m2o="' + c.name + '"] input').prop('disabled', !!padre)
                            .attr('placeholder', spec ? 'Primero elige ' + spec.label.toLowerCase() : (c.placeholder || 'Buscar…'));
                    }
                });
            });
        },

        // Vista previa del cliente mientras se completa el formulario.
        _actualizarForm: function () {
            var m = this._modal;
            if (!m || m.tipo !== 'form') {
                return;
            }
            var $prev = this._ref('fpreview');
            if ($prev.length) {
                var v = m.valores;
                var nombre = (v.name || '').trim();
                var iniciales = nombre.split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p[0]; }).join('').toUpperCase();
                var empresa = v.company_type === 'company';
                var dato = [v.vat || v.document_number, v.mobile || v.phone].filter(Boolean).map(esc).join(' · ');
                $prev.html('<span class="adt_f360__avatar' + (empresa ? ' is-company' : '') + '" aria-hidden="true">' +
                        (iniciales ? esc(iniciales) : '<i class="fa ' + (empresa ? 'fa-building-o' : 'fa-user') + '"></i>') + '</span>' +
                    '<span class="adt_f360__fpreview-text"><span class="adt_f360__strong">' + esc(nombre || 'Nombre del cliente') + '</span>' +
                    '<span class="adt_f360__sub">' + (dato || (empresa ? 'Empresa' : 'Persona')) + '</span></span>');
            }
        },

        // Mensaje de error de un campo, o '' si es válido.
        _errorCampo: function (c, v) {
            var vacio = v === false || v === '' || v === undefined || v === null;
            if (vacio) {
                return c.required && !c.virtual && c.type !== 'file' && c.type !== 'adjuntos' ? 'Este campo es obligatorio.' : '';
            }
            if (c.input === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(v).trim())) {
                return 'Escribe un correo válido, p. ej. nombre@dominio.com.';
            }
            if (c.input === 'tel' && String(v).replace(/\D/g, '').length < 6) {
                return 'El número parece incompleto.';
            }
            return '';
        },

        _marcarCampo: function (c, forzar) {
            var m = this._modal;
            var $wrap = this._ref('modal').find('[data-campo-wrap="' + c.name + '"]');
            // Solo se muestra el error tras salir del campo o al guardar, no mientras se escribe.
            if (!forzar && !$wrap.hasClass('is-invalid') && !$wrap.hasClass('is-touched')) {
                return '';
            }
            var error = $wrap.hasClass('d-none') ? '' : this._errorCampo(c, m.valores[c.name]);
            $wrap.toggleClass('is-invalid', !!error).find('.adt_f360__ferr').text(error);
            $wrap.find('[data-campo]').attr('aria-invalid', error ? 'true' : null);
            return error;
        },

        _onCampoBlur: function (ev) {
            var m = this._modal;
            var nombre = ev.currentTarget.getAttribute('data-campo');
            var c = m && m.tipo === 'form' && this._specCampo(nombre);
            if (!c || c.type === 'many2one') {
                return;
            }
            this._ref('modal').find('[data-campo-wrap="' + nombre + '"]').addClass('is-touched');
            this._marcarCampo(c);
            this._actualizarForm();
        },

        _onSegmento: function (ev) {
            var m = this._modal;
            var $b = $(ev.currentTarget);
            if (!m || m.tipo !== 'form') {
                return;
            }
            m.valores[$b.attr('data-seg-campo')] = $b.attr('data-seg-valor');
            m.sucio = true;
            $b.addClass('is-active').attr('aria-checked', 'true').siblings().removeClass('is-active').attr('aria-checked', 'false');
            this._aplicarVisibilidad();
            this._actualizarForm();
        },

        _specCampo: function (nombre) {
            var m = this._modal;
            var encontrado = null;
            (m && m.spec ? m.spec.secciones : []).forEach(function (sec) {
                sec.campos.forEach(function (c) { if (c.name === nombre) { encontrado = c; } });
            });
            return encontrado;
        },

        _onCampo: function (ev) {
            var m = this._modal;
            if (!m) {
                return;
            }
            var el = ev.currentTarget;
            var nombre = el.getAttribute('data-campo');
            if (m.tipo === 'credito') {
                return this._onCampoCredito(el, nombre, ev.type);
            }
            var c = this._specCampo(nombre);
            if (!c) {
                return;
            }
            m.sucio = true;
            if (c.type === 'many2one') {
                if (ev.type === 'input') {
                    m.valores[nombre] = false;
                    this._buscarOpcionesDiferido(el, c.model);
                }
                return;
            }
            if (c.type === 'file' || c.type === 'adjuntos') {
                m.archivos[nombre] = el.files ? _.toArray(el.files) : [];
                return;
            }
            m.valores[nombre] = c.type === 'boolean' ? el.checked : el.value;
            this._aplicarVisibilidad();
            this._marcarCampo(c);
            this._actualizarForm();
        },

        // --- Selector de registros (many2one) ------------------------------

        _buscarOpciones: function (input, modelo) {
            var $wrap = $(input).closest('[data-m2o]');
            // Listas encadenadas: c.filtros = {campo del modelo: campo del formulario}.
            var m = this._modal;
            var c = m && m.tipo === 'form' ? this._specCampo($wrap.attr('data-m2o'))
                : (m && m.tipo === 'credito' && $wrap.attr('data-m2o') === 'partner_id' ? {crear: 'cliente'} : null);
            var filtros = {};
            var valores = this._modal ? this._modal.valores : {};
            _.each(c && c.filtros, function (campoForm, campoModelo) {
                var v = valores[campoForm];
                if (v) {
                    filtros[campoModelo] = v[0];
                }
            });
            var termino = input.value.trim();
            this._llamar('opciones', {modelo: modelo, termino: input.value, filtros: filtros}).then(function (res) {
                // c.crear: al final de la lista, crear el registro con lo escrito (p. ej. un cliente nuevo).
                var crear = c && c.crear
                    ? '<li role="option" class="is-create" data-m2o-crear="' + esc(c.crear) + '">' +
                      '<i class="fa fa-plus-circle" aria-hidden="true"></i>' +
                      (termino ? 'Crear cliente «' + esc(termino) + '»' : 'Crear cliente nuevo') + '</li>'
                    : '';
                $wrap.find('.adt_f360__m2o-list').html((res.length ? res.map(function (r, i) {
                    return '<li role="option" id="f360_opt_' + i + '" data-m2o-opcion="' + r[0] + '">' + marcar(r[1], termino) + '</li>';
                }).join('') : '<li class="is-empty">Sin coincidencias' + (termino ? ' para «' + esc(termino) + '»' : '') + '</li>') + crear)
                    .addClass('is-open');
                $wrap.find('input').attr('aria-expanded', 'true');
            });
        },

        _onM2oOpcion: function (ev) {
            ev.preventDefault();  // mousedown: el campo conserva el foco
            this._elegirOpcion($(ev.currentTarget));
        },

        _elegirOpcion: function ($li) {
            var $wrap = $li.closest('[data-m2o]');
            var nombre = $wrap.attr('data-m2o');
            var valor = [parseInt($li.attr('data-m2o-opcion'), 10), $li.text()];
            $wrap.find('input').val(valor[1]).attr('aria-expanded', 'false');
            $wrap.find('.adt_f360__m2o-list').removeClass('is-open').empty();
            if (this._modal) {
                var original = $wrap.data('original');
                this._modal.valores[nombre] = valor;
                this._modal.sucio = true;
                // Solo se vacían los campos dependientes si el valor realmente cambió.
                if (!original || original[0] !== valor[0]) {
                    this._limpiarDependientes(nombre);
                }
                $wrap.data('original', valor);
                if (this._modal.tipo === 'credito' && nombre === 'partner_id') {
                    this._cargarClienteCredito();
                    this._renderCredito();
                } else if (this._modal.tipo === 'credito') {
                    this._simularDiferido();
                } else {
                    this._aplicarVisibilidad();
                    var c = this._specCampo(nombre);
                    if (c) { this._marcarCampo(c); }
                    this._actualizarForm();
                }
            }
        },

        _onM2oFocus: function (ev) {
            var $wrap = $(ev.currentTarget).closest('[data-m2o]');
            var m = this._modal;
            if (m && !$wrap.data('original')) {
                $wrap.data('original', m.valores[$wrap.attr('data-m2o')] || null);
            }
        },

        // Flechas para recorrer la lista, Enter para elegir, Escape para cerrarla.
        _onM2oKey: function (ev) {
            var $wrap = $(ev.currentTarget).closest('[data-m2o]');
            var $lista = $wrap.find('.adt_f360__m2o-list');
            var $ops = $lista.find('[data-m2o-opcion], [data-m2o-crear]');
            var abierta = $lista.hasClass('is-open') && $ops.length;
            var i = $ops.index($ops.filter('.is-active'));
            if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
                ev.preventDefault();
                if (!abierta) {
                    return this._buscarOpcionesDiferido(ev.currentTarget, $wrap.attr('data-model'));
                }
                i = ev.key === 'ArrowDown' ? Math.min(i + 1, $ops.length - 1) : Math.max(i - 1, 0);
                $ops.removeClass('is-active').eq(i).addClass('is-active');
                $ops[i].scrollIntoView({block: 'nearest'});
                $(ev.currentTarget).attr('aria-activedescendant', $ops.eq(i).attr('id') || null);
            } else if (ev.key === 'Enter' && abierta) {
                ev.preventDefault();
                var $sel = $ops.eq(i >= 0 ? i : 0);
                if ($sel.is('[data-m2o-crear]')) {
                    this._crearDesdeSelector($sel);
                } else {
                    this._elegirOpcion($sel);
                }
            } else if (ev.key === 'Escape' && abierta) {
                ev.preventDefault();
                ev.stopPropagation();
                $lista.removeClass('is-open');
                $(ev.currentTarget).attr('aria-expanded', 'false');
            }
        },

        _onM2oLimpiar: function (ev) {
            var nombre = ev.currentTarget.getAttribute('data-m2o-limpiar');
            var m = this._modal;
            var $wrap = $(ev.currentTarget).closest('[data-m2o]');
            if (!m) {
                return;
            }
            m.valores[nombre] = false;
            m.sucio = true;
            $wrap.data('original', null).find('input').val('').trigger('focus');
            if (m.tipo === 'form') {
                this._limpiarDependientes(nombre);
                this._aplicarVisibilidad();
                this._actualizarForm();
            } else if (m.tipo === 'credito') {
                this._simularDiferido();
            }
        },

        _onM2oCrear: function (ev) {
            ev.preventDefault();
            this._crearDesdeSelector($(ev.currentTarget));
        },

        // Cambia al formulario de alta (p. ej. cliente) con lo escrito como nombre.
        // Desde el asistente de crédito, al guardar se vuelve a él con el cliente elegido.
        _crearDesdeSelector: function ($li) {
            var m = this._modal;
            var texto = $li.closest('[data-m2o]').find('input').val().trim();
            if (m && m.tipo === 'credito') {
                return this._nuevoClienteCredito(texto);
            }
            var abrir = this._abrirForm.bind(this, $li.attr('data-m2o-crear'), false, {nombre: texto});
            if (m) {
                m.sucio = false;
            }
            this._cerrarModal(true);
            abrir();
        },

        // Al cambiar el país (o la provincia…) se vacían los campos que dependen de él.
        _limpiarDependientes: function (nombre) {
            var self = this;
            var m = this._modal;
            if (!m || m.tipo !== 'form') {
                return;
            }
            m.spec.secciones.forEach(function (sec) {
                sec.campos.forEach(function (c) {
                    if (c.filtros && _.contains(_.values(c.filtros), nombre) && m.valores[c.name]) {
                        m.valores[c.name] = false;
                        self._ref('modal').find('[data-m2o="' + c.name + '"]').data('original', null).find('input').val('');
                        self._limpiarDependientes(c.name);
                    }
                });
            });
        },

        _onM2oBlur: function (ev) {
            var self = this;
            var $wrap = $(ev.currentTarget);
            setTimeout(function () {
                $wrap.find('.adt_f360__m2o-list').removeClass('is-open');
                $wrap.find('input').attr('aria-expanded', 'false');
                var m = self._modal;
                var nombre = $wrap.attr('data-m2o');
                if (!m || m.tipo !== 'form' || !$.contains(document, $wrap[0])) {
                    return;
                }
                // Texto escrito sin elegir una opción: se recupera la selección anterior.
                var $input = $wrap.find('input');
                var original = $wrap.data('original');
                if (!m.valores[nombre] && $input.val().trim() && original) {
                    m.valores[nombre] = original;
                    $input.val(original[1]);
                } else if (!m.valores[nombre] && $input.val().trim()) {
                    $input.val('');
                }
                $wrap.closest('[data-campo-wrap]').addClass('is-touched');
                var c = self._specCampo(nombre);
                if (c) {
                    self._marcarCampo(c);
                }
                self._aplicarVisibilidad();
                self._actualizarForm();
            }, 150);
        },

        // --- Envío ---------------------------------------------------------

        _onSubmitModal: function (ev) {
            ev.preventDefault();
            var m = this._modal;
            if (!m) {
                return;
            }
            if (m.tipo === 'credito') {
                var boton = ev.currentTarget.getAttribute('data-guardar');
                // Enter dentro del asistente no guarda: se elige explícitamente borrador o aprobar.
                return boton ? this._guardarCredito(boton === 'aprobar') : undefined;
            }
            if (m.tipo !== 'form') {
                return;
            }
            var self = this;
            var invalidos = [];
            m.spec.secciones.forEach(function (sec) {
                sec.campos.forEach(function (c) {
                    if (self._marcarCampo(c, true)) {
                        invalidos.push(c);
                    }
                });
            });
            this._actualizarForm();
            if (invalidos.length) {
                var $primero = this._ref('modal').find('[data-campo-wrap="' + invalidos[0].name + '"]');
                $primero[0].scrollIntoView({behavior: 'smooth', block: 'center'});
                $primero.find('input:not(:disabled), select, textarea').first().trigger('focus');
                return this._modalError(invalidos.length === 1 ? 'Revisa el campo ' + invalidos[0].label + '.'
                    : 'Revisa ' + invalidos.length + ' campos marcados en rojo.');
            }
            this._ref('modal').find('[data-guardar]').prop('disabled', true).addClass('is-loading');
            this._modalError('');
            var valores = {};
            _.each(m.valores, function (v, k) {
                var c = self._specCampo(k);
                if (!c || c.type === 'file' || c.type === 'adjuntos') {
                    return;
                }
                valores[k] = c.type === 'datetime' ? localAUtc(v) : (c.type === 'many2one' ? (v ? v[0] : false) : v);
            });
            var lecturas = _.map(m.archivos, function (files, nombre) {
                var c = self._specCampo(nombre);
                return Promise.all(files.map(function (f) { return leerArchivo(f, c.limite_mb); })).then(function (leidos) {
                    valores[nombre] = c.type === 'file' ? (leidos[0] || undefined) : leidos;
                });
            });
            Promise.all(lecturas).then(function () {
                return self._llamar('guardar', {
                    clave: m.spec.clave, vehicle_id: self._drawerId, valores: valores,
                    res_id: m.spec.res_id || false, params: m.params,
                });
            }).then(function (res) {
                self._cerrarModal(true);
                self.displayNotification({type: 'success', message: m.spec.titulo + ': guardado.'});
                if (m.alGuardar) {
                    return m.alGuardar(res);
                }
                if (m.spec.clave === 'expediente') {
                    self.tab = 'expediente';
                }
                self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                self._modalError(err instanceof Error ? err.message : self._error(err));
            });
        },

        // ------------------------------------------------------------------
        // Documentos
        // ------------------------------------------------------------------

        _ref3: function (valor) {
            var p = (valor || '').split('|');
            return {modelo: p[0], res_id: parseInt(p[1], 10), campo: p[2]};
        },

        _onSubir: function (ev) {
            ev.stopPropagation();
            this._subirA = this._ref3(ev.currentTarget.getAttribute('data-subir'));
            this._ref('archivo').attr('accept', this._subirA.campo === CONSOLIDADO ? ACEPTA_CONSOLIDADO
                : (this._subirA.campo === 'cf_pdf' ? '.pdf,application/pdf' : ACEPTA_DOCUMENTO))
                .val('').trigger('click');
        },

        _onArchivo: function (ev) {
            var archivo = ev.currentTarget.files && ev.currentTarget.files[0];
            if (archivo && this._subirA && this._subirA.contrato) {
                this._subirContrato(this._subirA.contrato, archivo);
            } else if (archivo && this._subirA) {
                this._subirArchivo(this._subirA, archivo);
            }
        },

        _onDragOver: function (ev) {
            ev.preventDefault();
            $(ev.currentTarget).addClass('is-drop');
        },

        _onDragLeave: function (ev) {
            $(ev.currentTarget).removeClass('is-drop');
        },

        _onDrop: function (ev) {
            ev.preventDefault();
            var $zona = $(ev.currentTarget).removeClass('is-drop');
            var dt = ev.originalEvent && ev.originalEvent.dataTransfer;
            var archivo = dt && dt.files && dt.files[0];
            if (archivo && $zona.attr('data-contrato-zona')) {
                this._subirContrato(parseInt($zona.attr('data-contrato-zona'), 10), archivo);
            } else if (archivo) {
                this._subirArchivo(this._ref3($zona.attr('data-subir-zona')), archivo);
            }
        },

        _subirArchivo: function (destino, archivo) {
            var self = this;
            var consolidado = destino.campo === CONSOLIDADO;
            if (destino.campo === 'cf_pdf' && !/\.pdf$/i.test(archivo.name)) {
                this.displayNotification({type: 'danger', title: 'Formato no admitido', message: 'El plan de pagos debe ser un PDF.'});
                return Promise.resolve();
            }
            if (consolidado && !/\.(pdf|docx?)$/i.test(archivo.name)) {
                this.displayNotification({type: 'danger', title: 'Formato no admitido',
                    message: 'El expediente en un solo archivo debe ser PDF o Word (.doc / .docx).'});
                return Promise.resolve();
            }
            var $zona = this.$('[data-subir-zona="' + destino.modelo + '|' + destino.res_id + '|' + destino.campo + '"]').addClass('is-loading');
            return leerArchivo(archivo, consolidado ? MAX_CONSOLIDADO_MB : MAX_ARCHIVO_MB).then(function (leido) {
                return self._llamar('subir_documento', {
                    modelo: destino.modelo, res_id: destino.res_id, campo: destino.campo, nombre: leido.nombre, datos: leido.datos,
                });
            }).then(function () {
                self.displayNotification({type: 'success', message: destino.campo === 'cf_pdf'
                    ? 'Plan de pagos leído: se generó el cronograma de la financiera.' : 'Documento cargado.'});
                self._recargar();
            }).catch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                $zona.removeClass('is-loading');
                self.displayNotification({type: 'danger', title: 'No se pudo cargar', message: err instanceof Error ? err.message : self._error(err)});
            });
        },

        _onQuitar: function (ev) {
            var self = this;
            var destino = this._ref3(ev.currentTarget.getAttribute('data-quitar'));
            Dialog.confirm(this, '¿Quitar este archivo? Tendrás que volver a cargarlo.', {
                title: 'Quitar documento',
                confirm_callback: function () {
                    return self._llamar('quitar_documento', destino).then(function () { self._recargar(); });
                },
            });
        },

        _onAceptar: function (ev) {
            var self = this;
            var p = ev.currentTarget.getAttribute('data-aceptar').split('|');
            this._llamar('revisar_documento', {expediente_id: parseInt(p[0], 10), clave: p[1], estado: 'aceptado'}).then(function () {
                self._recargar();
            });
        },

        _onRechazar: function (ev) {
            var p = ev.currentTarget.getAttribute('data-rechazar').split('|');
            this._abrirForm('rechazo_documento', parseInt(p[0], 10), {clave: p[1]});
        },

        // data-ver = "url|tipo|título|descarga"; tipo: 1 imagen, 2 PDF, 0 otro archivo.
        _onVer: function (ev) {
            var p = ev.currentTarget.getAttribute('data-ver').split('|');
            if (p[1] === '0') {
                window.open(p[0], '_blank', 'noopener');
                return;
            }
            var esPdf = p[1] === '2';
            var abrir = esPdf ? VISOR_PDF + encodeURIComponent(p[0]) : p[0];
            this._mostrarModal({tipo: 'visor', ancho: true},
                this._modalCabecera(p[2]) +
                (esPdf
                    ? '<div class="adt_f360__viewer is-pdf"><iframe src="' + esc(abrir) + '" title="' + esc(p[2]) + '"></iframe></div>'
                    : '<div class="adt_f360__viewer"><img src="' + esc(p[0]) + '" alt="' + esc(p[2]) + '"/></div>') +
                '<footer class="adt_f360__modal-foot"><div class="adt_f360__modal-error"></div>' +
                '<a class="adt_f360__btn" href="' + esc(abrir) + '" target="_blank" rel="noopener"><i class="fa fa-external-link" aria-hidden="true"></i>Abrir en otra pestaña</a>' +
                '<a class="adt_f360__btn" href="' + esc(p[3]) + '"><i class="fa fa-download" aria-hidden="true"></i>Descargar</a>' +
                '<button type="button" class="adt_f360__btn is-primary" data-modal-close>Cerrar</button></footer>');
        },

        // data-cuenta-sel="0" vuelve a la lista de cuentas.
        _onCuentaSel: function (ev) {
            this.cuentaSel = parseInt(ev.currentTarget.getAttribute('data-cuenta-sel'), 10) || null;
            this.cuotaSel = null;
            this.cronoSel = null;
            this.detAbierto = false;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__db').scrollTop(0);
        },

        _onCuota: function (ev) {
            ev.stopPropagation();
            this.cuotaSel = parseInt(ev.currentTarget.getAttribute('data-cuota'), 10);
            this._cuotaAnimar = true;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__sheet [data-cuota-close]').last().trigger('focus');
        },

        _onCuotaKey: function (ev) {
            if (ev.target !== ev.currentTarget) {
                return;
            }
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onCuota(ev);
            }
        },

        _cerrarCuota: function () {
            var id = this.cuotaSel;
            this.cuotaSel = null;
            this._renderDrawer();
            this._ref('drawer').find('[data-cuota="' + id + '"]').first().trigger('focus');
        },

        // "Cobrar": elige cuota, cascada o mora; el adaptador de pagos abre el popup nativo.
        _onCobrar: function (ev) {
            var self = this;
            var s = _.findWhere(this.detalle.secciones, {key: 'cuentas'});
            var c = s && _.findWhere(s.deuda, {id: parseInt(ev.currentTarget.getAttribute('data-cobrar'), 10)});
            if (!c) {
                return;
            }
            this._mostrarModal({tipo: 'opciones'},
                this._modalCabecera('¿Qué vas a cobrar?', c.titular.nombre + ' · ' + c.referencia) +
                '<div class="adt_f360__modal-body"><div class="adt_f360__optcards is-stack">' + c.cobrar.map(function (a) {
                    self._acciones.push(a);
                    return '<button type="button" class="adt_f360__optcard' + (a.sugerida ? ' is-main' : '') + '" data-accion="' + (self._acciones.length - 1) + '">' +
                        '<i class="fa ' + esc(a.icon) + ' adt_f360__optcard-icon" aria-hidden="true"></i>' +
                        '<span><span class="adt_f360__strong">' + esc(a.label) + (a.sugerida ? ' ' + badge('atencion', 'Sugerido') : '') + '</span>' +
                        '<span class="adt_f360__sub">' + esc(a.descripcion || '') + '</span></span>' +
                        '<i class="fa fa-angle-right adt_f360__optcard-go" aria-hidden="true"></i></button>';
                }).join('') + '</div></div>' +
                '<footer class="adt_f360__modal-foot"><div class="adt_f360__modal-error"></div>' +
                '<button type="button" class="adt_f360__btn" data-modal-close>Cancelar</button></footer>');
        },

        _onPapeleta: function (ev) {
            this.papSel = parseInt(ev.currentTarget.getAttribute('data-pap'), 10);
            this._papAnimar = true;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__sheet [data-pap-close]').last().trigger('focus');
        },

        _cerrarPapeleta: function () {
            var id = this.papSel;
            this.papSel = null;
            this._renderDrawer();
            this._ref('drawer').find('[data-pap="' + id + '"]').first().trigger('focus');
        },

        _onCaptura: function (ev) {
            this.capSel = parseInt(ev.currentTarget.getAttribute('data-cap'), 10);
            this._capAnimar = true;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__sheet [data-cap-close]').last().trigger('focus');
        },

        _cerrarCaptura: function () {
            var id = this.capSel;
            this.capSel = null;
            this._renderDrawer();
            this._ref('drawer').find('[data-cap="' + id + '"]').first().trigger('focus');
        },

        _onExpediente: function (ev) {
            this.expSel = parseInt(ev.currentTarget.getAttribute('data-exp'), 10);
            this._renderDrawer();
        },

        // ------------------------------------------------------------------
        // Crédito: nueva cuenta con cronograma
        // ------------------------------------------------------------------

        // Drawer en dos pasos: 1) cliente (buscarlo o registrarlo) y 2) condiciones y cronograma.
        // Es el único lugar donde se asigna el cliente (titular) del vehículo.
        _abrirCredito: function (cuentaId) {
            var self = this;
            return this._llamar('cuenta_inicial', {vehicle_id: this._drawerId, cuenta_id: cuentaId || false}).then(function (ini) {
                var v = ini.valores;
                // El cliente es [id, nombre] o nada.
                if (!_.isArray(v.partner_id) || !v.partner_id.length) {
                    v.partner_id = false;
                }
                self._mostrarModal({tipo: 'credito', ancho: true, lateral: true, ini: ini, valores: v, cuenta_id: ini.cuenta_id,
                    fraccionadoManual: !!(cuentaId && v.monto_fraccionado !== (v.monto_total || 0) - (v.monto_inicial || 0)),
                    sim: ini.simulacion, paso: cuentaId ? 'credito' : 'cliente'}, '');
                self._cargarClienteCredito();
                self._renderCredito();
            }).guardedCatch(function (err) {
                if (err && err.event) { err.event.preventDefault(); }
                self.displayNotification({type: 'warning', title: 'Crédito', message: self._error(err)});
            });
        },

        _renderCredito: function () {
            var m = this._modal;
            var borrador = !!m.cuenta_id;
            var cuerpo, pie;
            if (m.paso === 'cliente') {
                cuerpo = '<form class="adt_f360__modal-body" novalidate="novalidate"><div class="adt_f360__wclient">' +
                    this._htmlCreditoCliente() + '</div><button type="submit" class="d-none"></button></form>';
                pie = this._pieAsistente(
                    '<button type="button" class="adt_f360__btn is-ghost" data-modal-close>Cancelar</button>',
                    (m.valores.partner_id ? '' : '<span class="adt_f360__wfoot-hint">Elige o registra al socio para continuar.</span>') +
                    '<button type="button" class="adt_f360__btn is-primary" data-credito-paso="credito"' +
                        (m.valores.partner_id ? '' : ' disabled="disabled"') + '>Siguiente: datos del crédito' +
                        '<i class="fa fa-arrow-right" aria-hidden="true"></i></button>');
            } else {
                cuerpo = '<form class="adt_f360__modal-body adt_f360__credit" novalidate="novalidate">' +
                        '<div class="adt_f360__credit-form">' + this._htmlCreditoForm(m.ini, m.valores) + '</div>' +
                        '<div class="adt_f360__credit-preview" data-ref="credito-preview"></div>' +
                    '<button type="submit" class="d-none"></button></form>';
                // Izquierda: volver y cancelar. Derecha: las dos formas de guardar, cada una diciendo qué hace;
                // la que genera el cronograma es la principal y va al final.
                pie = this._pieAsistente(
                    '<button type="button" class="adt_f360__btn" data-credito-paso="cliente">' +
                        '<i class="fa fa-arrow-left" aria-hidden="true"></i>Volver al socio</button>' +
                    '<button type="button" class="adt_f360__btn is-ghost" data-modal-close>Cancelar</button>',
                    '<button type="button" class="adt_f360__actbtn" data-guardar="borrador">' +
                        '<i class="fa fa-floppy-o" aria-hidden="true"></i><span><b>' + (borrador ? 'Guardar cambios' : 'Guardar como borrador') + '</b>' +
                        '<small>Sin generar cuotas · podrás editarlo después</small></span></button>' +
                    '<button type="button" class="adt_f360__actbtn is-primary" data-guardar="aprobar">' +
                        '<i class="fa fa-check-circle" aria-hidden="true"></i><span><b>' + (borrador ? 'Guardar y aprobar' : 'Crear y aprobar') + '</b>' +
                        '<small data-ref="aprobar-detalle">Genera el cronograma y asigna el titular</small></span></button>');
            }
            var pasos = [['cliente', 'Cliente'], ['credito', 'Crédito y cronograma']];
            var actual = m.paso === 'cliente' ? 0 : 1;
            var stepper = '<ol class="adt_f360__wsteps">' + pasos.map(function (p, i) {
                return '<li class="' + (i === actual ? 'is-active' : (i < actual ? 'is-done' : '')) + '"' +
                    (i === actual ? ' aria-current="step"' : '') + '><span class="adt_f360__wsteps-n">' +
                    (i < actual ? '<i class="fa fa-check" aria-hidden="true"></i>' : i + 1) + '</span>' + esc(p[1]) + '</li>';
            }).join('') + '</ol>';
            var $m = this._ref('modal').find('.adt_f360__modal');
            $m.html(this._modalCabecera(borrador ? 'Crédito en borrador' : 'Nuevo crédito',
                    'Vehículo ' + m.ini.vehiculo + (m.paso === 'cliente'
                        ? '. Elige al cliente: al aprobar el crédito quedará como titular del vehículo.'
                        : '. El cronograma se genera al aprobar; la vista previa muestra exactamente las cuotas que se crearán.')) +
                stepper + cuerpo + pie);
            if (m.paso === 'credito') {
                this._renderSimulacion();
            }
            var $primero = $m.find('.adt_f360__modal-body input:not([type=hidden]):not([type=file]), .adt_f360__modal-body select').first();
            ($primero.length ? $primero : $m.find('.adt_f360__modal-foot .is-primary')).trigger('focus');
        },

        // Paso 1: buscar al cliente o registrarlo; ya elegido, su ficha resumida con avisos.
        _htmlCreditoCliente: function () {
            var m = this._modal;
            var partner = m.valores.partner_id;
            if (!partner) {
                return '<section class="adt_f360__fieldset"><h3 class="adt_f360__legend"><i class="fa fa-search" aria-hidden="true"></i>' +
                        'Buscar cliente registrado</h3><div class="adt_f360__form-grid">' +
                        this._htmlInput({name: 'partner_id', label: 'Cliente', type: 'many2one', model: 'res.partner', col: 2,
                                         placeholder: 'Busca por nombre, DNI o RUC'}, false) + '</div></section>' +
                    '<div class="adt_f360__wclient-or"><span>o</span></div>' +
                    '<div class="adt_f360__optcards is-stack"><button type="button" class="adt_f360__optcard" data-credito-nuevo>' +
                        '<i class="fa fa-user-plus adt_f360__optcard-icon" aria-hidden="true"></i>' +
                        '<span><span class="adt_f360__strong">Registrar cliente nuevo</span>' +
                        '<span class="adt_f360__sub">Si aún no está en Contactos, completa sus datos; al guardarlo vuelves aquí con él elegido.</span></span>' +
                        '<i class="fa fa-angle-right adt_f360__optcard-go" aria-hidden="true"></i></button></div>';
            }
            var c = m.cliente && m.cliente.id === partner[0] ? m.cliente : null;
            var chips = c ? [c.documento && ['fa-id-card-o', c.documento], c.telefono && ['fa-mobile', c.telefono],
                             c.email && ['fa-envelope-o', c.email]].filter(Boolean) : [];
            var exp = c && c.expediente;
            var estado = '';
            if (exp) {
                estado = '<div class="adt_f360__wclient-row"><span class="adt_f360__muted"><i class="fa fa-folder-open-o" aria-hidden="true"></i> Expediente</span>' +
                    (exp.estado ? badge(exp.nivel, exp.estado) : badge('atencion', 'Sin expediente')) + '</div>';
            }
            return '<section class="adt_f360__panel adt_f360__wclient-card">' +
                    '<header class="adt_f360__hcard-head"><span class="adt_f360__avatar is-large' + (c && c.empresa ? ' is-company' : '') + '" aria-hidden="true">' +
                        esc(this._iniciales(partner[1])) + '</span>' +
                    '<div class="adt_f360__hcard-who"><h3>' + esc(c ? c.nombre : partner[1]) + (c && c.titular ? ' ' + badge('ok', 'Titular actual') : '') + '</h3>' +
                        (chips.length ? '<div class="adt_f360__hcard-chips">' + chips.map(function (x) {
                            return '<span><i class="fa ' + x[0] + '" aria-hidden="true"></i>' + esc(x[1]) + '</span>';
                        }).join('') + '</div>' : (c ? '' : '<div class="adt_f360__sub">Cargando datos del cliente…</div>')) + '</div>' +
                    '<div class="adt_f360__hcard-actions"><button type="button" class="adt_f360__btn is-small" data-credito-cambiar>' +
                        '<i class="fa fa-exchange" aria-hidden="true"></i>Cambiar cliente</button></div></header>' +
                    estado + '</section>' +
                (c ? (c.avisos || []).map(function (t) {
                    return '<div class="adt_f360__note"><i class="fa fa-info-circle" aria-hidden="true"></i> ' + esc(t) + '</div>';
                }).join('') : '');
        },

        _cargarClienteCredito: function () {
            var self = this;
            var m = this._modal;
            var partner = m.valores.partner_id;
            m.cliente = null;
            if (!partner) {
                return;
            }
            this._llamar('cliente_credito', {vehicle_id: this._drawerId, partner_id: partner[0]}).then(function (c) {
                var actual = m.valores.partner_id;
                if (self._modal === m && actual && actual[0] === c.id) {
                    m.cliente = c;
                    if (m.paso === 'cliente') {
                        self._renderCredito();
                    }
                }
            });
        },

        _onPasoCredito: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'credito') {
                return;
            }
            var paso = ev.currentTarget.getAttribute('data-credito-paso');
            if (paso === 'credito' && !m.valores.partner_id) {
                return this._modalError('Elige o registra al cliente del crédito.');
            }
            m.paso = paso;
            this._renderCredito();
        },

        _onCambiarClienteCredito: function () {
            var m = this._modal;
            m.valores.partner_id = false;
            m.cliente = null;
            m.paso = 'cliente';
            this._renderCredito();
        },

        _onNuevoClienteCredito: function () {
            this._nuevoClienteCredito('');
        },

        // Alta del cliente en su propio drawer; al guardarlo (o cancelar) se vuelve al asistente
        // con lo ya cargado y, si se creó, con el cliente elegido.
        _nuevoClienteCredito: function (nombre) {
            var self = this;
            var m = this._modal;
            var volver = function (partner) {
                if (partner) {
                    m.valores.partner_id = partner;
                }
                m.paso = 'cliente';
                self._mostrarModal(m, '');
                self._cargarClienteCredito();
                self._renderCredito();
            };
            m.seq = (m.seq || 0) + 1;  // descarta simulaciones en curso
            this._cerrarModal(true);
            return this._abrirForm('cliente', false, {credito: true, nombre: nombre || ''}, {
                volver: function () { volver(); },
                alGuardar: function (res) { volver([res.id, res.nombre]); },
            });
        },

        _htmlCreditoForm: function (ini, v) {
            var self = this;
            // Un elemento puede ser un campo o un bloque HTML ya armado (p. ej. el selector del cálculo).
            var campo = function (c) { return typeof c === 'string' ? c : self._htmlInput(c, v[c.name]); };
            var seccion = function (titulo, campos, antes) {
                return '<section class="adt_f360__fieldset"><h3 class="adt_f360__legend">' + titulo + '</h3><div class="adt_f360__form-grid">' +
                    (antes || '') + campos.map(campo).join('') + '</div></section>';
            };
            var modo = '<div class="adt_f360__field is-full"><label>¿Cómo se calcula el monto de cuota?</label><div class="adt_f360__seg is-block">' +
                [['cuotas', 'Según el total de cuotas'], ['monto', 'Lo indico yo']].map(function (x) {
                    return '<button type="button" class="' + (v.modo === x[0] ? 'is-active' : '') + '" data-modo="' + x[0] + '">' + x[1] + '</button>';
                }).join('') + '</div><span class="adt_f360__help">«Según el total de cuotas» divide el monto fraccionado en partes iguales; ' +
                '«Lo indico yo» usa el monto de cuota que escribas.</span></div>';
            // El socio (cliente) se eligió en el paso 1: aquí solo se muestra, con acceso a cambiarlo.
            // Nombres, orden y secciones iguales a la pestaña «Crédito» de la cuenta en Comercial.
            var cliente = '<div class="adt_f360__field is-full"><label>Socio</label><div class="adt_f360__wclient-chip">' +
                '<span class="adt_f360__avatar" aria-hidden="true">' + esc(this._iniciales(v.partner_id && v.partner_id[1])) + '</span>' +
                '<span class="adt_f360__strong">' + esc(v.partner_id ? v.partner_id[1] : '') + '</span>' +
                '<button type="button" class="adt_f360__btn is-small" data-credito-paso="cliente">Cambiar</button></div></div>';
            return (ini.disponible ? '' : '<div class="adt_f360__note">El vehículo figura como no disponible; revisa que no tenga otro crédito activo.</div>') +
                seccion('Cuenta', [
                    {name: 'tipo_financiera_id', label: 'Tipo de Financiera', type: 'selection', options: ini.financieras},
                    {name: 'user_id', label: 'Vendedor', type: 'many2one', model: 'res.users', required: true},
                    {name: 'is_available_pay_mora', label: '¿Paga Mora?', type: 'boolean'},
                ], cliente) +
                seccion('Fechas', [
                    {name: 'fecha_desembolso', label: 'Fecha de desembolso', type: 'date'},
                    {name: 'fecha_entrega', label: 'Fecha de entrega', type: 'date'},
                    {name: 'fecha_cierre', label: 'Fecha de cierre', type: 'integer',
                        help: (ini.simulacion && ini.simulacion.mensaje_cierre) || 'Día de cierre; se sugiere según la fecha de desembolso.'},
                ]) +
                seccion('Montos y cuotas', [
                    {name: 'monto_total', label: 'Valor total del vehículo', type: 'monetary'},
                    {name: 'monto_inicial', label: 'Inicial', type: 'monetary'},
                    {name: 'monto_fraccionado', label: 'Monto fraccionado', type: 'monetary', required: true,
                        help: 'Valor total del vehículo − inicial; puedes ajustarlo.'},
                    {name: 'cuota_gracia', label: 'Cuota de gracia', type: 'monetary', help: 'Opcional. Se cobra en la fecha de gracia.'},
                    {name: 'fecha_gracia', label: 'Fecha de gracia', type: 'date', required: true,
                        help: 'Inicio del cronograma: la cuota 1 vence un periodo después.'},
                    {name: 'periodicidad', label: 'Periodo', type: 'selection', options: ini.periodicidades, required: true},
                    modo,
                    {name: 'qty_cuotas', label: 'Total de cuotas', type: 'integer', required: true},
                    {name: 'monto_cuota', label: 'Monto de cuota', type: 'monetary', required: true},
                ]);
        },

        _onModoCredito: function (ev) {
            var m = this._modal;
            if (!m || m.tipo !== 'credito') {
                return;
            }
            m.valores.modo = ev.currentTarget.getAttribute('data-modo');
            $(ev.currentTarget).addClass('is-active').siblings().removeClass('is-active');
            this._toggleMontoCuota();
            this._simularDiferido();
        },

        _toggleMontoCuota: function () {
            var m = this._modal;
            this._ref('modal').find('[data-campo-wrap="monto_cuota"]').toggleClass('d-none', m.valores.modo !== 'monto');
        },

        _onCampoCredito: function (el, nombre, tipo) {
            var m = this._modal;
            var numericos = ['monto_total', 'monto_inicial', 'monto_fraccionado', 'cuota_gracia', 'monto_cuota', 'qty_cuotas', 'fecha_cierre'];
            if (nombre === 'partner_id' || nombre === 'user_id') {
                if (tipo === 'input') {
                    m.valores[nombre] = false;
                    this._buscarOpcionesDiferido(el, nombre === 'partner_id' ? 'res.partner' : 'res.users');
                }
                return;
            }
            var valor = el.type === 'checkbox' ? el.checked : el.value;
            m.valores[nombre] = numericos.indexOf(nombre) >= 0 ? (parseFloat(valor) || 0) : valor;
            if (nombre === 'monto_fraccionado') {
                m.fraccionadoManual = true;
            }
            if (nombre === 'fecha_cierre') {
                m.cierreManual = true;
            }
            if ((nombre === 'monto_total' || nombre === 'monto_inicial') && !m.fraccionadoManual) {
                m.valores.monto_fraccionado = Math.max((m.valores.monto_total || 0) - (m.valores.monto_inicial || 0), 0);
                this._ref('modal').find('[data-campo="monto_fraccionado"]').val(m.valores.monto_fraccionado.toFixed(2));
            }
            this._simularDiferido();
        },

        _simularCredito: function () {
            var self = this;
            var m = this._modal;
            if (!m || m.tipo !== 'credito') {
                return;
            }
            var seq = m.seq = (m.seq || 0) + 1;
            this._llamar('simular_cronograma', {params: this._paramsCredito()}).then(function (sim) {
                if (self._modal === m && m.seq === seq) {
                    m.sim = sim;
                    // Fecha de cierre: la sugerida por Comercial para la fecha de desembolso, salvo que se haya escrito a mano.
                    if (!m.cierreManual && sim.fecha_cierre && sim.fecha_cierre !== m.valores.fecha_cierre) {
                        m.valores.fecha_cierre = sim.fecha_cierre;
                        self._ref('modal').find('[data-campo="fecha_cierre"]').val(sim.fecha_cierre);
                    }
                    if (sim.mensaje_cierre) {
                        self._ref('modal').find('[data-campo-wrap="fecha_cierre"] .adt_f360__help').text(sim.mensaje_cierre);
                    }
                    self._renderSimulacion();
                }
            });
        },

        _paramsCredito: function () {
            var v = _.clone(this._modal.valores);
            v.partner_id = v.partner_id ? v.partner_id[0] : false;
            v.user_id = v.user_id ? v.user_id[0] : false;
            return v;
        },

        _renderSimulacion: function () {
            var m = this._modal;
            this._toggleMontoCuota();
            var sim = m.sim || {cuotas: [], errores: []};
            var $p = this._ref('modal').find('[data-ref="credito-preview"]');
            // El botón principal dice exactamente qué hará con estos datos.
            this._ref('modal').find('[data-ref="aprobar-detalle"]').text(sim.cuotas.length
                ? 'Genera ' + plural(sim.cuotas.length, 'cuota', 'cuotas') + ' y asigna el titular'
                : 'Genera el cronograma y asigna el titular');
            var resumen = sim.cuotas.length
                ? '<div class="adt_f360__credit-figures">' + [
                    ['Monto de cuota', soles(sim.cuota)],
                    ['Total de cuotas', entero(m.valores.qty_cuotas)],
                    ['Total a cobrar', soles(sim.total)],
                    ['Última cuota', fecha(sim.ultima)],
                ].map(function (x) {
                    return '<div><span>' + x[0] + '</span><b>' + esc(x[1]) + '</b></div>';
                }).join('') + '</div>'
                : '';
            var mensajes = (sim.errores || []).map(function (e) { return '<div class="adt_f360__note is-critico">' + esc(e) + '</div>'; }).join('') +
                (sim.avisos || []).map(function (e) { return '<div class="adt_f360__note">' + esc(e) + '</div>'; }).join('');
            var tabla = sim.cuotas.length
                ? '<div class="adt_f360__credit-table"><table class="adt_f360__dtable"><thead><tr><th>Cuota</th><th>Vence</th><th class="is-num">Monto</th></tr></thead><tbody>' +
                  sim.cuotas.map(function (q) {
                      return '<tr><td>' + esc(q.nombre) + '</td><td>' + fecha(q.fecha) + '</td><td class="is-num">' + soles(q.monto) + '</td></tr>';
                  }).join('') + '</tbody></table></div>'
                : '<p class="adt_f360__muted adt_f360__pad">Completa los montos para ver el cronograma.</p>';
            $p.html('<div class="adt_f360__label">Vista previa del cronograma</div>' + resumen + mensajes + tabla);
        },

        _guardarCredito: function (aprobar) {
            var self = this;
            var m = this._modal;
            if (!m.valores.partner_id) {
                m.paso = 'cliente';
                this._renderCredito();
                return this._modalError('Elige o registra al cliente del crédito.');
            }
            if (m.sim && m.sim.errores && m.sim.errores.length) {
                return this._modalError(m.sim.errores[0]);
            }
            var correr = function () {
                self._ref('modal').find('[data-guardar]').prop('disabled', true);
                self._modalError('');
                return self._llamar('guardar_cuenta', {
                    vehicle_id: self._drawerId, params: self._paramsCredito(), aprobar: aprobar, cuenta_id: m.cuenta_id || false,
                }).then(function (res) {
                    self._cerrarModal();
                    self.displayNotification({type: 'success', message: aprobar
                        ? 'Cuenta ' + (res.referencia || '') + ' aprobada con su cronograma.'
                        : 'Cuenta guardada como borrador.'});
                    self.tab = 'cuentas';
                    self._recargar();
                }).guardedCatch(function (err) {
                    if (err && err.event) { err.event.preventDefault(); }
                    self._modalError(self._error(err));
                });
            };
            if (aprobar) {
                Dialog.confirm(this, '¿Aprobar la cuenta? Se generarán ' + (m.sim ? m.sim.cuotas.length : '') +
                    ' cuotas y ' + m.valores.partner_id[1] + ' quedará como titular del vehículo.', {title: 'Aprobar cuenta', confirm_callback: correr});
            } else {
                correr();
            }
        },

        // ------------------------------------------------------------------
        // Eventos
        // ------------------------------------------------------------------

        _onInput: function (ev) {
            this.termino = ev.currentTarget.value;
            this.$el.toggleClass('has-query', !!this.termino);
            this._buscarDiferido();
        },

        _onSearchKey: function (ev) {
            var self = this;
            if (ev.key === 'Enter') {
                this._buscarDiferido.cancel();
                this._buscar(false).then(function () {
                    if (self.items.length === 1) {
                        self._abrirDrawer(self.items[0].id);
                    }
                });
            } else if (ev.key === 'ArrowDown') {
                ev.preventDefault();
                this.$('[data-row]').first().trigger('focus');
            } else if (ev.key === 'Escape' && this.termino) {
                ev.stopPropagation();
                this._onClear();
            }
        },

        _onClear: function () {
            this.termino = '';
            this._ref('q').val('').trigger('focus');
            this._buscarDiferido.cancel();
            this._buscar(false);
        },

        _onFiltro: function (ev) {
            var key = ev.currentTarget.getAttribute('data-filtro');
            this.filtro = key === this.filtro && key !== 'todos' ? 'todos' : key;
            this._renderFiltros();
            this._buscar(false);
        },

        _onFinanciera: function (ev) {
            var valor = ev.currentTarget.getAttribute('data-financiera');
            var id = valor === 'todas' ? null : parseInt(valor, 10);
            this.financiera = id === this.financiera ? null : id;
            this._renderFacetas();
            this._buscar(false);
        },

        _onGrupo: function (ev) {
            var valor = ev.currentTarget.getAttribute('data-grupo');
            this.grupo = valor === 'todos' ? null : valor;
            this._renderGrupos();
            this._buscar(false);
        },

        _onClearFacetas: function () {
            this.financiera = null;
            this.estado = null;
            this._renderFacetas();
            this._buscar(false);
        },

        _onEstado: function (ev) {
            var valor = ev.currentTarget.getAttribute('data-estado');
            var estado = valor === 'todas' ? null : valor;
            this.estado = estado === this.estado ? null : estado;
            this._renderFacetas();
            this._buscar(false);
        },

        _onRow: function (ev) {
            this._abrirDrawer(parseInt(ev.currentTarget.getAttribute('data-row'), 10));
        },

        // ↑/↓ recorren la tabla; Enter abre la ficha.
        _onRowKey: function (ev) {
            var $row = $(ev.currentTarget);
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._onRow(ev);
            } else if (ev.key === 'ArrowDown') {
                ev.preventDefault();
                $row.next('[data-row]').trigger('focus');
            } else if (ev.key === 'ArrowUp') {
                ev.preventDefault();
                var $prev = $row.prev('[data-row]');
                ($prev.length ? $prev : this._ref('q')).trigger('focus');
            }
        },

        _onMore: function () {
            this._ref('more').find('button').prop('disabled', true).text('Cargando…');
            this._buscar(true);
        },

        _onTab: function (ev) {
            var tab = ev.currentTarget.getAttribute('data-tab');
            tab = tab === 'cuentas' ? 'cronograma' : tab;
            var clave = tab === 'cronograma' ? 'cuentas' : tab;
            if (!this.detalle || (tab !== 'resumen' && !_.findWhere(this.detalle.secciones, {key: clave}))) {
                return;
            }
            this.tab = tab;
            this.papSel = null;
            this.capSel = null;
            this.cuotaSel = null;
            this.detAbierto = false;
            this._renderDrawer();
            this._ref('drawer').find('.adt_f360__db').scrollTop(0);
        },

        _onPestana: function (ev) {
            this.vistas[ev.currentTarget.getAttribute('data-pclave')] = ev.currentTarget.getAttribute('data-ptab');
            this.cuotaSel = null;
            this._renderDrawer();
        },

        _onFiltroCrono: function (ev) {
            this.filtroCrono[ev.currentTarget.getAttribute('data-cuenta')] = ev.currentTarget.getAttribute('data-crono');
            if (this.cronoVer) {
                delete this.cronoVer[ev.currentTarget.getAttribute('data-cuenta')];
            }
            this._renderDrawer();
        },

        _onExpandir: function (ev) {
            var id = ev.currentTarget.getAttribute('data-expandir');
            this.expandidas[id] = !this.expandidas[id];
            this._renderDrawer();
        },

        _onMenu: function (ev) {
            ev.stopPropagation();
            var $wrap = $(ev.currentTarget).closest('.adt_f360__menu-wrap');
            var abrir = !$wrap.hasClass('is-open');
            this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open').find('[data-menu]').attr('aria-expanded', 'false');
            if (abrir) {
                $wrap.addClass('is-open').find('[data-menu]').attr('aria-expanded', 'true');
                // Abrir hacia arriba si no hay espacio debajo.
                var rect = $wrap[0].getBoundingClientRect();
                $wrap.toggleClass('is-up', window.innerHeight - rect.bottom < 260 && rect.top > 260);
            }
        },

        _onAccion: function (ev) {
            ev.stopPropagation();
            this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
            var a = this._acciones[parseInt(ev.currentTarget.getAttribute('data-accion'), 10)];
            if (this._modal && this._modal.tipo === 'opciones') {
                this._cerrarModal(true);
            }
            if (a) {
                this._ejecutar(a);
            }
        },

        _onGlobalClick: function (ev) {
            if (this.$el && !$(ev.target).closest('.adt_f360__menu-wrap').length) {
                this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
            }
        },

        _onGlobalKey: function (ev) {
            if (!this.$el || !this.$el.is(':visible') || $('.modal:visible').length) {
                return;
            }
            var enInput = /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName) || ev.target.isContentEditable;
            if (ev.key === 'Escape') {
                if (this._modal) {
                    this._cerrarModal();
                } else if (this.$('.adt_f360__menu-wrap.is-open').length) {
                    this.$('.adt_f360__menu-wrap.is-open').removeClass('is-open');
                } else if (this.papSel) {
                    this._cerrarPapeleta();
                } else if (this.capSel) {
                    this._cerrarCaptura();
                } else if (this.detAbierto && this.tab === 'cronograma') {
                    this._onDetalleCerrar();
                } else if (this.cuotaSel) {
                    this._cerrarCuota();
                } else {
                    this._closeDrawer();
                }
            } else if (this._modal) {
                return;
            } else if (ev.key === '/' && !enInput) {
                ev.preventDefault();
                this._closeDrawer();
                this._ref('q').trigger('focus').trigger('select');
            } else if ((ev.key === 'Enter' || ev.key === ' ') && !enInput && $(ev.target).is('[data-tab]:not(button)')) {
                ev.preventDefault();
                $(ev.target).trigger('click');
            }
        },
    });

    core.action_registry.add('adt_flota_360', Flota360);

    return Flota360;
});
