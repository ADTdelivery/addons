odoo.define('adt_traccar_device.PasswordToggleField', function (require) {
"use strict";

/**
 * Campo de texto con un botón de "ojo" integrado en el mismo input para
 * mostrar/ocultar el valor — el mismo patrón que cualquier login típico
 * (Gmail, bancos, etc.): un solo campo, ofuscado con puntos por defecto,
 * que se revela en texto plano al hacer click en el ícono y se vuelve a
 * ofuscar al hacer click de nuevo. No depende de ningún otro campo del
 * modelo (a diferencia del truco de "duplicar el campo + checkbox aparte"
 * usado en adt_traccar/views/adt_traccar_views.xml, porque el atributo
 * `password="True"` no admite `attrs` dinámicos).
 *
 * Uso en una vista:
 *   <field name="mi_campo" widget="adt_password_toggle"/>
 */

var basicFields = require('web.basic_fields');
var fieldRegistry = require('web.field_registry');

var PasswordToggleField = basicFields.FieldChar.extend({
    className: (basicFields.FieldChar.prototype.className || '') + ' o_adt_password_toggle',
    events: _.extend({}, basicFields.FieldChar.prototype.events, {
        'click .o_adt_password_toggle_btn': '_onToggleVisibility',
    }),

    /**
     * @override
     */
    init: function () {
        this._super.apply(this, arguments);
        this._adtPasswordVisible = false;
    },

    /**
     * @override
     * Igual que el atributo password="True" nativo (que internamente hace
     * this.$input.attr('type', 'password')), pero alternable en runtime.
     */
    _renderEdit: function () {
        this._super.apply(this, arguments);
        this.$input.attr('type', this._adtPasswordVisible ? 'text' : 'password');
        this._addAdtToggleButton();
    },

    /**
     * @override
     * En modo solo-lectura no hay <input> — se ofusca el texto renderizado
     * por defecto y también se agrega el botón de alternar.
     */
    _renderReadonly: function () {
        this._super.apply(this, arguments);
        if (!this._adtPasswordVisible && this.value) {
            this.$el.text('••••••••');
        }
        this._addAdtToggleButton();
    },

    _addAdtToggleButton: function () {
        this.$('.o_adt_password_toggle_btn').remove();
        if (!this.value) {
            return;
        }
        var $btn = $('<button>', {
            type: 'button',
            class: 'o_adt_password_toggle_btn btn btn-link p-0 ml-1',
            title: this._adtPasswordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña',
        }).append($('<i>', {
            class: 'fa ' + (this._adtPasswordVisible ? 'fa-eye-slash' : 'fa-eye'),
        }));
        this.$el.append($btn);
    },

    _onToggleVisibility: function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this._adtPasswordVisible = !this._adtPasswordVisible;
        if (this.mode === 'edit') {
            this._renderEdit();
        } else {
            this._renderReadonly();
        }
    },
});

fieldRegistry.add('adt_password_toggle', PasswordToggleField);

return PasswordToggleField;

});
