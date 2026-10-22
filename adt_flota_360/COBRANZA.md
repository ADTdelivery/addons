# Carteras de cobranza

Acceso: Flota → Flota 360 → Carteras de cobranza, o pestaña en Consulta 360.

Gerencia asigna cuentas a usuarios internos con acceso a Flota. El trabajador consulta sus propias carteras y registra contactos, notas y promesas de pago. Gerencia ve el equipo completo y puede cerrar una gestión para reasignar la cuenta.

La selección es manual: se busca por nombre, DNI/RUC o referencia de cuenta y se marca cada cliente individualmente. Las selecciones se conservan entre búsquedas. La interfaz no ofrece filtros por características ni selección masiva. Las asignaciones se restringen a cuentas en curso de la empresa actual, hasta 2.000 por cartera. Las cuentas sin cuotas pendientes en el alcance elegido no generan objetivos. Una cuenta con gestión abierta no se puede asignar de nuevo.

Al asignar se fija el saldo de las cuotas vencidas/exigibles o de todas las pendientes, según la selección. El avance es el incremento neto de pagos contabilizados desde ese momento, limitado al objetivo. Se incluyen subcuotas generadas por pagos parciales. No se cuentan promesas ni cambios manuales del estado de gestión como recaudación. Los importes de distintas monedas se muestran separados. La meta se considera resuelta cuando se alcanza el importe asignado; esto no implica que toda la deuda futura del cliente esté cancelada.

Al cerrar una gestión se conserva su importe cobrado para el historial, y la cuenta queda disponible para otra asignación. El tablero se actualiza cada minuto mientras la página está visible y también al guardar gestiones o pulsar Actualizar.

Los permisos y las reglas de registros se aplican en el servidor por responsable y empresa. Para calcular el avance del trabajador solo se eleva la lectura de los pagos de sus cuotas autorizadas y se devuelve el importe agregado; no se concede acceso general a contabilidad.

Instalación/actualización: actualizar el módulo `adt_flota_360` y reiniciar Odoo para cargar los modelos nuevos. La interfaz usa JavaScript de Odoo 15; los modelos Python guardan la asignación compartida y validan permisos.

Pruebas: `odoo -d <base> -u adt_flota_360 --http-port=8079 --stop-after-init --test-enable --test-tags /adt_flota_360`.

## Perfil del cobrador

En Ajustes → Usuarios, asignar el permiso **Flota 360: Cobrador (solo su cartera)**. No requiere permisos de Flota ni de contabilidad. El usuario ingresa desde la aplicación **Mi cartera** y ve sus clientes, contactos, promesas, importes cobrados y porcentaje de avance. Para abrirla automáticamente al iniciar sesión, configurar **Mi cartera** como acción inicial del usuario.

El perfil de cobrador limita también las cuentas y cuotas de ADT Comercial en el servidor. Las carteras históricas asignadas siguen siendo consultables por su responsable. Gerencia conserva la supervisión del equipo; no asignar permisos gerenciales a un usuario que deba ver solo su propia cartera.

## Asistente de asignación

1. Elegir cobrador, fecha límite y deuda a recuperar. El nombre de la cartera es opcional y se completa automáticamente si se deja vacío.
2. Buscar y marcar cuentas una por una; repetir la búsqueda para añadir otros clientes sin perder los anteriores. La lista muestra el importe por cuenta y excluye asignaciones activas y cuentas sin deuda para el alcance elegido.
3. Revisar responsable, plazo, cantidad de clientes/cuentas e importes por moneda. Solo al pulsar **Confirmar y asignar cartera** se guardan los datos.

La revisión utiliza únicamente los identificadores de las cuentas marcadas individualmente, aunque provengan de búsquedas distintas. La asignación vuelve a validar disponibilidad y permisos en el servidor.

La lista de selección se carga automáticamente al entrar al paso 2. Muestra las primeras 50 cuentas y permite añadir bloques de hasta 50 mediante **Cargar más**, sin reemplazar filas ni perder selecciones. El contador indica las cuentas cargadas sobre el total disponible. Al volver entre pasos se conservan la lista y la selección; cambiar la búsqueda inicia una nueva lista y conserva las selecciones. Cambiar el alcance de deuda elimina la selección para volver a elegir cuentas válidas.
