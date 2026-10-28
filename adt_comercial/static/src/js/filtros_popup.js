odoo.define('adt_comercial.FiltrosPopup', function (require) {
    'use strict';

    /**
     * Popup de filtros para las vistas .adt_cart (Cartera y financieras, Indicadores SAT…),
     * igual que el de Flota 360: un botón «Filtros» con la cantidad aplicada, un popup con
     * una sección por criterio donde se elige sobre un borrador y se aplica con «Aplicar»,
     * y los filtros aplicados como chips que se quitan con su ×.
     *
     * La vista hace `AbstractAction.extend(FiltrosPopup.mixin, {...})`, suma
     * `FiltrosPopup.events` a sus eventos, tiene en su plantilla un contenedor
     * data-ref="fpop" (botón y popup) y otro data-ref="aplicados" (chips), e implementa:
     *   _fpopValores()          valores actuales {clave: valor}
     *   _fpopDefecto()          valores sin filtrar {clave: valor}
     *   _fpopSecciones(valores) [{clave, icono, titulo, opciones: [{valor, name, n, punto}]}];
     *                           la primera opción es «Todos» (el valor por defecto) y los
     *                           contadores son los de la vista actual
     *   _fpopAplicar(valores)   aplica los valores y vuelve a pintar
     */
    var esc = _.escape;

    function entero(n) {
        return (n || 0).toLocaleString('es-PE');
    }

    var events = {
        'click [data-fpop="abrir"]': '_fpopOnAbrir',
        'click [data-fpop="cerrar"]': '_fpopCerrar',
        'click [data-fpop="limpiar"]': '_fpopOnLimpiar',
        'click [data-fpop="aplicar"]': '_fpopOnAplicar',
        'click [data-fpop-sel]': '_fpopOnSel',
        'click [data-fpop-quitar]': '_fpopOnQuitar',
        'click [data-fpop="quitar-todos"]': '_fpopOnQuitarTodos',
    };

    var mixin = {
        // Pinta el botón, el popup (si está abierto) y los chips de los filtros aplicados.
        _fpopRender: function () {
            var activos = this._fpopAplicados();
            var abierto = !!this._fpopBorrador;
            this.$('[data-ref="fpop"]').html(
                '<button type="button" class="adt_cart__fpop-btn' + (activos.length ? ' is-filtered' : '') + (abierto ? ' is-open' : '') +
                    '" data-fpop="abrir" aria-haspopup="dialog" aria-expanded="' + abierto + '">' +
                    '<i class="fa fa-sliders" aria-hidden="true"></i>Filtros' +
                    (activos.length ? '<span class="adt_cart__fpop-badge">' + activos.length + '</span>' : '') + '</button>' +
                (abierto ? this._fpopHtml() : ''));
            this.$('[data-ref="aplicados"]').html(activos.length ? activos.map(function (f) {
                return '<span class="adt_cart__achip"><i class="fa ' + f.icono + '" aria-hidden="true"></i>' +
                    '<span class="adt_cart__achip-k">' + esc(f.titulo) + '</span>' + esc(f.valor) +
                    '<button type="button" data-fpop-quitar="' + esc(f.clave) + '" title="Quitar filtro" aria-label="Quitar filtro ' +
                    esc(f.titulo) + '"><i class="fa fa-times" aria-hidden="true"></i></button></span>';
            }).join('') + '<button type="button" class="adt_cart__applied-clear" data-fpop="quitar-todos">Quitar filtros</button>' : '');
        },

        _fpopAplicados: function () {
            var valores = this._fpopValores();
            var defecto = this._fpopDefecto();
            return this._fpopSecciones(valores).filter(function (s) {
                return !_.isEqual(valores[s.clave], defecto[s.clave]);
            }).map(function (s) {
                var o = _.find(s.opciones, function (x) { return _.isEqual(x.valor, valores[s.clave]); });
                return {clave: s.clave, icono: s.icono, titulo: s.titulo, valor: o ? o.name : 'Seleccionado'};
            });
        },

        _fpopHtml: function () {
            var b = this._fpopBorrador;
            var secciones = this._fpopSecciones(b).filter(function (s) { return s.opciones.length > 1; }).map(function (s) {
                return '<section class="adt_cart__fpop-sec"><span class="adt_cart__facet-label"><i class="fa ' + s.icono +
                    '" aria-hidden="true"></i>' + esc(s.titulo) + '</span><div class="adt_cart__fpop-chips">' +
                    s.opciones.map(function (o, i) {
                        var activo = _.isEqual(o.valor, b[s.clave]);
                        return '<button type="button" class="adt_cart__fchip' + (activo ? ' is-active' : '') + (!o.n && !activo ? ' is-zero' : '') +
                            '" data-fpop-sel="' + esc(s.clave) + '" data-fpop-i="' + i + '" aria-pressed="' + activo + '">' +
                            (o.punto ? '<i class="adt_cart__fchip-dot is-' + esc(String(o.punto)) + '" aria-hidden="true"></i>' : '') +
                            esc(o.name) + '<span class="adt_cart__fchip-n">' + entero(o.n) + '</span></button>';
                    }).join('') + '</div></section>';
            });
            return '<div class="adt_cart__fpop" role="dialog" aria-label="Filtros">' +
                '<div class="adt_cart__fpop-head"><span>Filtros</span>' +
                    '<button type="button" class="adt_cart__fpop-x" data-fpop="cerrar" title="Cerrar (Esc)" aria-label="Cerrar filtros">' +
                    '<i class="fa fa-times" aria-hidden="true"></i></button></div>' +
                '<div class="adt_cart__fpop-body">' + secciones.join('') + '</div>' +
                '<div class="adt_cart__fpop-foot">' +
                    '<button type="button" class="adt_cart__fpop-reset" data-fpop="limpiar">Limpiar</button>' +
                    '<button type="button" class="adt_cart__btn adt_cart__btn--ghost" data-fpop="cerrar">Cancelar</button>' +
                    '<button type="button" class="adt_cart__btn" data-fpop="aplicar">Aplicar</button>' +
                '</div></div>';
        },

        _fpopOnAbrir: function () {
            if (this._fpopBorrador) {
                this._fpopCerrar();
                return;
            }
            this._fpopBorrador = _.clone(this._fpopValores());
            // Clic fuera o Esc cierran sin aplicar.
            var self = this;
            this._fpopFuera = function (ev) {
                if (self.isDestroyed()) {
                    self._fpopQuitarEscuchas();
                } else if (ev.type === 'keydown' ? ev.key === 'Escape' : !$(ev.target).closest('[data-ref="fpop"]').length) {
                    self._fpopCerrar();
                }
            };
            document.addEventListener('click', this._fpopFuera, true);
            document.addEventListener('keydown', this._fpopFuera, true);
            this._fpopRender();
        },

        _fpopQuitarEscuchas: function () {
            if (this._fpopFuera) {
                document.removeEventListener('click', this._fpopFuera, true);
                document.removeEventListener('keydown', this._fpopFuera, true);
                this._fpopFuera = null;
            }
        },

        // Cierra el popup sin aplicar lo elegido.
        _fpopCerrar: function () {
            this._fpopBorrador = null;
            this._fpopQuitarEscuchas();
            this._fpopRender();
        },

        // Elegir una opción ya marcada la desmarca (vuelve a «Todos»).
        _fpopOnSel: function (ev) {
            var clave = ev.currentTarget.getAttribute('data-fpop-sel');
            var seccion = _.findWhere(this._fpopSecciones(this._fpopBorrador), {clave: clave});
            var opcion = seccion && seccion.opciones[parseInt(ev.currentTarget.getAttribute('data-fpop-i'), 10)];
            if (!opcion) {
                return;
            }
            this._fpopBorrador[clave] = _.isEqual(opcion.valor, this._fpopBorrador[clave]) ? this._fpopDefecto()[clave] : opcion.valor;
            this._fpopRender();
        },

        _fpopOnLimpiar: function () {
            this._fpopBorrador = _.clone(this._fpopDefecto());
            this._fpopRender();
        },

        _fpopOnAplicar: function () {
            var valores = this._fpopBorrador;
            var cambio = !_.isEqual(valores, this._fpopValores());
            this._fpopBorrador = null;
            this._fpopQuitarEscuchas();
            if (cambio) {
                this._fpopAplicar(valores);
            } else {
                this._fpopRender();
            }
        },

        _fpopOnQuitar: function (ev) {
            var clave = ev.currentTarget.getAttribute('data-fpop-quitar');
            var valores = _.clone(this._fpopValores());
            valores[clave] = this._fpopDefecto()[clave];
            this._fpopAplicar(valores);
        },

        _fpopOnQuitarTodos: function () {
            this._fpopAplicar(_.clone(this._fpopDefecto()));
        },
    };

    return {mixin: mixin, events: events};
});
