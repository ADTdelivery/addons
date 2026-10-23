odoo.define('adt_comercial.carga_pdf_widget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var core = require('web.core');
    var fieldRegistry = require('web.field_registry');

    var SUBIDAS_EN_PARALELO = 4;
    var AGREGAR_CADA = 10;          // los PDFs subidos se vinculan al lote de 10 en 10
    var REFRESCO_PROCESO_MS = 4000;  // mientras el lote procesa, se recarga para ver el avance

    function kb(bytes) {
        if (!bytes) {
            return '';
        }
        return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(bytes / 1024)) + ' KB';
    }

    function barra(pct, clase) {
        return '<div class="o_adt_cpdf_bar ' + (clase || '') + '"><div style="width:' + pct.toFixed(1) + '%"></div></div>';
    }

    // Carga masiva de PDFs del plan de pagos: lista con el nombre de cada PDF, total que se está
    // subiendo y porcentaje de avance (subida y luego procesamiento del lote).
    var CargaPdfField = AbstractField.extend({
        supportedFieldTypes: ['many2many'],
        className: 'o_adt_cpdf',
        fieldsToFetch: {
            name: {type: 'char'},
            mimetype: {type: 'char'},
            file_size: {type: 'integer'},
        },
        events: {
            'click .o_adt_cpdf_elegir': '_onElegir',
            'change .o_adt_cpdf_input': '_onArchivos',
            'click .o_adt_cpdf_quitar': '_onQuitar',
            'dragover .o_adt_cpdf_drop': '_onDragOver',
            'dragleave .o_adt_cpdf_drop': '_onDragLeave',
            'drop .o_adt_cpdf_drop': '_onDrop',
        },

        init: function () {
            this._super.apply(this, arguments);
            this._subidas = [];
            this._porVincular = [];
            this._vinculando = Promise.resolve();
            this._activas = 0;
            this._renderLento = _.throttle(this._render.bind(this), 250);
        },

        destroy: function () {
            clearTimeout(this._timerProceso);
            this._super.apply(this, arguments);
        },

        isSet: function () {
            return true;
        },

        // ------------------------------------------------------------ render

        _render: function () {
            var self = this;
            var estadoLote = this.record.data.state;
            var editable = this.mode === 'edit' && estadoLote !== 'terminado';
            var vinculados = this.value.data.map(function (r) {
                return {id: r.data.id, name: r.data.name, size: r.data.file_size, estado: 'ok'};
            });
            var pendientes = this._subidas.filter(function (s) { return !s.vinculado; });
            var filas = vinculados.concat(pendientes);

            var html = '';
            if (editable) {
                html += '<div class="o_adt_cpdf_drop">' +
                    '<i class="fa fa-cloud-upload"></i>' +
                    '<div>Arrastra aquí los PDF del plan de pagos o ' +
                    '<button type="button" class="btn btn-link p-0 o_adt_cpdf_elegir">selecciónalos</button>' +
                    ' (puedes elegir cientos a la vez)</div>' +
                    '<input type="file" class="o_adt_cpdf_input d-none" multiple="multiple" accept=".pdf,application/pdf"/>' +
                    '</div>';
            }
            html += this._htmlSubida() + this._htmlProceso();
            html += '<div class="o_adt_cpdf_cab"><b>' + filas.length + '</b> PDF' + (filas.length === 1 ? '' : 's') +
                ' en el lote</div>';
            if (filas.length) {
                html += '<div class="o_adt_cpdf_tabla"><table class="table table-sm mb-0"><thead><tr>' +
                    '<th class="text-right">#</th><th>Nombre del PDF</th><th class="text-right">Tamaño</th>' +
                    '<th>Estado</th>' + (editable ? '<th></th>' : '') + '</tr></thead><tbody>';
                filas.forEach(function (f, i) {
                    html += '<tr class="o_adt_cpdf_' + f.estado + '">' +
                        '<td class="text-right text-muted">' + (i + 1) + '</td>' +
                        '<td class="o_adt_cpdf_nombre">' + _.escape(f.name || '') + '</td>' +
                        '<td class="text-right text-muted">' + kb(f.size) + '</td>' +
                        '<td>' + self._htmlEstado(f) + '</td>' +
                        (editable ? '<td class="text-right">' + (f.estado === 'ok' && estadoLote === 'borrador'
                            ? '<button type="button" class="btn btn-sm btn-link text-danger o_adt_cpdf_quitar" ' +
                              'data-id="' + f.id + '" title="Quitar"><i class="fa fa-times"></i></button>' : '') +
                            '</td>' : '') +
                        '</tr>';
                });
                html += '</tbody></table></div>';
            }
            this.$el.html(html);
            this._programarRefresco();
        },

        _htmlEstado: function (f) {
            if (f.estado === 'ok') {
                return '<span class="badge badge-success">Subido</span>';
            }
            if (f.estado === 'subiendo') {
                var pct = f.size ? 100 * f.cargado / f.size : 0;
                return '<span class="badge badge-info">Subiendo ' + Math.floor(pct) + '%</span>';
            }
            if (f.estado === 'error') {
                return '<span class="badge badge-danger" title="' + _.escape(f.error || '') + '">Error</span> ' +
                    '<small class="text-danger">' + _.escape(f.error || '') + '</small>';
            }
            return '<span class="badge badge-light">En cola</span>';
        },

        // Avance de la subida: por bytes (lo que de verdad falta transferir) y por archivos.
        _htmlSubida: function () {
            var s = this._subidas;
            if (!s.length) {
                return '';
            }
            var total = s.length;
            var terminados = s.filter(function (x) { return x.estado === 'ok' || x.estado === 'error'; }).length;
            var errores = s.filter(function (x) { return x.estado === 'error'; }).length;
            var bytes = 0, cargados = 0;
            s.forEach(function (x) {
                bytes += x.size || 0;
                cargados += (x.estado === 'ok' || x.estado === 'error') ? (x.size || 0) : (x.cargado || 0);
            });
            var pct = bytes ? 100 * cargados / bytes : 100 * terminados / total;
            var enCurso = terminados < total;
            var texto = enCurso
                ? 'Subiendo <b>' + terminados + ' de ' + total + '</b> PDFs · <b>' + Math.floor(pct) + '%</b> · faltan ' +
                  (total - terminados) + ' (' + (100 - Math.floor(pct)) + '%)'
                : '<b>' + (total - errores) + ' de ' + total + '</b> PDFs subidos · 100%' +
                  (errores ? ' · <span class="text-danger">' + errores + ' con error</span>' : '');
            return '<div class="o_adt_cpdf_avance">' +
                '<div class="o_adt_cpdf_avance_txt"><i class="fa ' + (enCurso ? 'fa-spinner fa-spin' : 'fa-check') + '"></i> ' +
                texto + '</div>' + barra(Math.min(pct, 100), enCurso ? '' : 'is-ok') +
                (enCurso ? '<small class="text-muted">No cierres esta ventana ni pulses «Procesar» hasta que termine la subida.</small>' : '') +
                '</div>';
        },

        // Avance del procesamiento del lote (lectura de cada PDF y carga en la moto).
        _htmlProceso: function () {
            var d = this.record.data;
            if (d.state === 'borrador' || !d.total) {
                return '';
            }
            var hechos = d.total - d.total_pendiente;
            var pct = 100 * hechos / d.total;
            var enCurso = d.state === 'procesando' && d.total_pendiente > 0;
            return '<div class="o_adt_cpdf_avance">' +
                '<div class="o_adt_cpdf_avance_txt"><i class="fa ' + (enCurso ? 'fa-cog fa-spin' : 'fa-check') + '"></i> ' +
                (enCurso
                    ? 'Procesando <b>' + hechos + ' de ' + d.total + '</b> PDFs · <b>' + Math.floor(pct) + '%</b> · faltan ' +
                      d.total_pendiente + ' (' + (100 - Math.floor(pct)) + '%)'
                    : '<b>' + d.total + '</b> PDFs procesados · 100%') +
                '</div>' + barra(pct, enCurso ? 'is-proceso' : 'is-ok') + '</div>';
        },

        _programarRefresco: function () {
            var self = this;
            clearTimeout(this._timerProceso);
            var d = this.record.data;
            if (this.mode === 'readonly' && d.state === 'procesando' && d.total_pendiente > 0) {
                this._timerProceso = setTimeout(function () {
                    self.trigger_up('reload');
                }, REFRESCO_PROCESO_MS);
            }
        },

        // ------------------------------------------------------------ subida

        _agregar: function (files) {
            var self = this;
            _.each(files, function (file) {
                var esPdf = /\.pdf$/i.test(file.name) || file.type === 'application/pdf';
                self._subidas.push({
                    file: file, name: file.name, size: file.size, cargado: 0,
                    estado: esPdf ? 'cola' : 'error', error: esPdf ? '' : 'No es un PDF',
                });
            });
            this._siguiente();
            this._render();
        },

        _siguiente: function () {
            while (this._activas < SUBIDAS_EN_PARALELO) {
                var item = _.findWhere(this._subidas, {estado: 'cola'});
                if (!item) {
                    break;
                }
                this._subir(item);
            }
            var quedan = _.some(this._subidas, function (s) { return s.estado === 'cola' || s.estado === 'subiendo'; });
            if (this._porVincular.length >= AGREGAR_CADA || (!quedan && this._porVincular.length)) {
                this._vincular();
            }
        },

        _subir: function (item) {
            var self = this;
            item.estado = 'subiendo';
            this._activas++;
            var datos = new FormData();
            datos.append('csrf_token', core.csrf_token);
            datos.append('model', this.model);
            datos.append('id', this.res_id || 0);
            datos.append('ufile', item.file, item.name);
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/web/binary/upload_attachment');
            xhr.upload.onprogress = function (ev) {
                if (ev.lengthComputable) {
                    item.cargado = ev.loaded;
                    self._renderLento();
                }
            };
            xhr.onload = function () {
                var res = null;
                try {
                    res = JSON.parse(xhr.responseText)[0];
                } catch (e) {
                    res = {error: 'Respuesta inválida del servidor (' + xhr.status + ')'};
                }
                if (xhr.status !== 200 || !res || res.error) {
                    self._fin(item, (res && res.error) || 'Error ' + xhr.status);
                } else {
                    item.id = res.id;
                    self._porVincular.push(item);
                    self._fin(item);
                }
            };
            xhr.onerror = function () {
                self._fin(item, 'Sin conexión con el servidor');
            };
            xhr.send(datos);
        },

        _fin: function (item, error) {
            this._activas--;
            item.estado = error ? 'error' : 'ok';
            item.error = error || '';
            item.file = null;
            this._siguiente();
            this._renderLento();
        },

        // Agrega al campo los PDFs ya subidos, en tandas, encadenado para no pisar valores.
        _vincular: function () {
            var self = this;
            var tanda = this._porVincular.splice(0);
            this._vinculando = this._vinculando.then(function () {
                var ids = _.union(self.value.res_ids, _.pluck(tanda, 'id'));
                return self._setValue({operation: 'REPLACE_WITH', ids: ids}).then(function () {
                    tanda.forEach(function (t) { t.vinculado = true; });
                    self._render();
                });
            });
        },

        // ------------------------------------------------------------ eventos

        _onElegir: function (ev) {
            ev.preventDefault();
            this.$('.o_adt_cpdf_input').click();
        },

        _onArchivos: function (ev) {
            this._agregar(ev.target.files);
            ev.target.value = '';
        },

        _onQuitar: function (ev) {
            var id = parseInt($(ev.currentTarget).data('id'), 10);
            this._subidas = this._subidas.filter(function (s) { return s.id !== id; });
            this._setValue({operation: 'REPLACE_WITH', ids: _.without(this.value.res_ids, id)});
        },

        _onDragOver: function (ev) {
            ev.preventDefault();
            this.$('.o_adt_cpdf_drop').addClass('is-over');
        },

        _onDragLeave: function () {
            this.$('.o_adt_cpdf_drop').removeClass('is-over');
        },

        _onDrop: function (ev) {
            ev.preventDefault();
            this.$('.o_adt_cpdf_drop').removeClass('is-over');
            var dt = ev.originalEvent.dataTransfer;
            if (dt && dt.files && dt.files.length) {
                this._agregar(dt.files);
            }
        },
    });

    fieldRegistry.add('adt_carga_pdf', CargaPdfField);

    return CargaPdfField;
});
