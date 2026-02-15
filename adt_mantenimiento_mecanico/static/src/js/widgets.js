/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

/**
 * ADT Mantenimiento Mecánico - Widgets Personalizados
 * Siguiendo guías UX/UI del archivo UX_UI.md
 */

// Widget de Prioridad con colores
export class PriorityWidget extends Component {
    get priorityClass() {
        const priority = this.props.value;
        const classes = {
            'critica': 'badge-priority-high',
            'alta': 'badge-priority-high',
            'media': 'badge-priority-medium',
            'baja': 'badge-priority-low'
        };
        return `badge ${classes[priority] || 'badge-secondary'}`;
    }
}

// Registrar el widget
registry.category("fields").add("adt_priority", PriorityWidget);

console.log('ADT Mantenimiento Mecánico - Widgets cargados');
