{
    "name": "ADT Sentinel",
    "version": "1.0.0",
    "summary": "Repositorio inteligente de consultas crediticias Sentinel",
    "description": """
        Módulo Sentinel - Repositorio de Consultas Crediticias
        ========================================================

        IMPORTANTE: Este módulo NO calcula ni interpreta scores crediticios.

        Funcionalidad:
        - Almacena imágenes de reportes crediticios
        - Controla vigencia mensual (1 consulta por DNI por mes)
        - Evita consultas duplicadas
        - Reduce costos operativos (S/ 10 por consulta)
        - Mantiene histórico completo

        Reglas de negocio:
        - Vigencia: Solo el mes actual
        - Reutilización: Todos los usuarios comparten el reporte del mes
        - Histórico: Se conservan todos los registros
        - Trazabilidad: Usuario y fecha de cada consulta
    """,
    "category": "Accounting",
    "author": "ADT",
    "depends": ["base", "contacts"],
    "data": [
        'security/ir.model.access.csv',
        'wizard/sentinel_query_wizard_views.xml',
        'views/sentinel_report_views.xml',
        'views/sentinel_menu.xml',
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
