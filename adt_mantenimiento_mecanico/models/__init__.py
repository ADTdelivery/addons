# -*- coding: utf-8 -*-

# Módulos Base
from . import adt_vehiculo          # Módulo 2: Vehículos, Marcas, Créditos
from . import adt_cliente           # Módulo 3: Cliente (res.partner)
from . import adt_mecanico          # Módulo 9: Mecánicos

# Módulo Principal
from . import adt_orden_mantenimiento  # Módulo 1: Órdenes

# Módulos del Proceso
from . import adt_inspeccion        # Módulo 4: Inspección + Módulo 5: Fluidos
from . import adt_diagnostico       # Módulo 6: Diagnóstico y Trabajos
from . import adt_repuesto          # Módulo 7: Repuestos
from . import adt_mano_obra         # Módulo 8: Mano de Obra
from . import adt_control_calidad   # Módulo 10: Control de Calidad

# Módulos Finales
from . import adt_proxima_revision  # Módulo 13: Próxima Revisión
from . import adt_autorizacion      # Módulo 14: Autorizaciones

# Nota: Módulo 11 (Estado Final) y 12 (Facturación) están integrados
# en adt_orden_mantenimiento
