odoo.define('adt_papeletas.AlertBadge', function (require) {
    "use strict";
    var fieldRegistry = require('web.field_registry');
    var basicFields = require('web.basic_fields');
    var FieldChar = basicFields.FieldChar;

    var AlertBadge = FieldChar.extend({
        _render: function () {
            this._super.apply(this, arguments);
            var value = this.value || '';
            var el = this.$el;
            el.empty();
            if (value) {
                var span = $('<span/>', {
                    text: value,
                    class: 'adt-alert-badge o_badge o_badge_danger'
                });
                el.append(span);
            }
        }
    });

    fieldRegistry.add('adt_alert_badge', AlertBadge);
});
