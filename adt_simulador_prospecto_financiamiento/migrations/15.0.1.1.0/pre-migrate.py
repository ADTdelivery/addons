def migrate(cr, version):
    """Las simulaciones existentes se calcularon sin cargo diario: se crea la
    columna con 0 para que no tomen el valor por defecto (5.00) sin recalcular."""
    cr.execute("""
        ALTER TABLE financing_simulation
        ADD COLUMN IF NOT EXISTS cargo_diario numeric DEFAULT 0
    """)
    cr.execute("ALTER TABLE financing_simulation ALTER COLUMN cargo_diario DROP DEFAULT")
