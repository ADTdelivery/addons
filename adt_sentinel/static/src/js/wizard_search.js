odoo.define('adt_sentinel.wizard_search', function (require) {
    "use strict";

    var FormController = require('web.FormController');

    FormController.include({
        _onButtonClicked: function (event) {
            var self = this;

            // Interceptar solo el botón específico del wizard Sentinel
            if (this.modelName === 'adt.sentinel.query.wizard' &&
                event.data.attrs.name === 'action_search_dni') {

                event.stopPropagation();

                // Obtener el valor del campo DNI del estado actual del formulario
                var currentState = this.renderer.state;
                var dniValue = currentState.data.document_number || '';
                var wizardId = currentState.res_id;

                console.log('📝 Capturando DNI:', dniValue);
                console.log('🆔 Wizard ID:', wizardId);

                // Llamar al método Python pasando el DNI
                return this._rpc({
                    model: 'adt.sentinel.query.wizard',
                    method: 'action_search_dni',
                    args: [[], wizardId, dniValue],
                }).then(function (action) {
                    console.log('✅ Respuesta del servidor:', action);
                    if (action && action.type) {
                        return self.do_action(action, {
                            on_close: function () {
                                // Recargar el formulario si es necesario
                            }
                        });
                    }
                }).guardedCatch(function (error) {
                    console.error('❌ Error:', error);
                    // El error se mostrará automáticamente
                    throw error;
                });
            }

            // Comportamiento normal para otros botones
            return this._super.apply(this, arguments);
        },
    });
});
