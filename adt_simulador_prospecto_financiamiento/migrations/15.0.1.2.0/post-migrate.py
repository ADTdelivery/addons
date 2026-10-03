def migrate(cr, version):
    """Los datos precargados son noupdate: se asigna la cuota inicial de referencia
    (2,000) a los vehículos precargados que quedaron con 0 al crear la columna."""
    cr.execute("""
        UPDATE financing_vehicle v
           SET cuota_inicial = 2000
          FROM ir_model_data d
         WHERE d.model = 'financing.vehicle'
           AND d.module = 'adt_simulador_prospecto_financiamiento'
           AND d.name IN ('vehicle_tvs_deluxe_200', 'vehicle_tvs_duramax_225')
           AND d.res_id = v.id
           AND COALESCE(v.cuota_inicial, 0) = 0
    """)
