odoo.define('adt_comercial.fin_pct_bar_widget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    // Barra de porcentaje completa: la barra entera (0-100%) y el número visible al lado.
    var FinPctBar = AbstractField.extend({
        supportedFieldTypes: ['float', 'integer'],
        className: 'o_adt_pct_bar_field',

        _render: function () {
            var value = Math.max(0, Math.min(100, parseFloat(this.value) || 0));
            var color = (this.nodeOptions && this.nodeOptions.color) || '#2563eb';
            if (!/^#[0-9a-fA-F]{3,8}$/.test(color)) {
                color = '#2563eb';
            }
            this.$el.html(
                '<div class="o_adt_pct_bar">' +
                    '<div class="o_adt_pct_bar_track">' +
                        '<div class="o_adt_pct_bar_fill" style="width:' + value + '%;background:' + color + '"></div>' +
                    '</div>' +
                    '<span class="o_adt_pct_bar_text">' + value.toFixed(1) + '%</span>' +
                '</div>'
            );
        },
    });

    fieldRegistry.add('adt_pct_bar', FinPctBar);

    return FinPctBar;
});
