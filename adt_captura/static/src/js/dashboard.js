// Custom JS for dashboard interactivity
odoo.define('adt_captura.dashboard', function (require) {
    "use strict";
    var core = require('web.core');
    var KanbanView = require('web.KanbanView');
    var KanbanRecord = require('web.KanbanRecord');
    var QWeb = core.qweb;

    KanbanRecord.include({
        events: _.extend({}, KanbanRecord.prototype.events, {
            'click .o_kanban_card': '_onCardClick',
        }),
        _onCardClick: function (ev) {
            var $card = $(ev.currentTarget);
            $card.toggleClass('o_kanban_card_selected');
        },
    });
});
