# Quick Installation Test Guide

## Testing the Fixed Module

### Method 1: Upgrade Existing Installation
If the module is already installed but failing:

```bash
# Connect to your Odoo database
odoo-bin -d your_database_name -u adt_sentinel --log-level=debug
```

### Method 2: Fresh Installation
If installing for the first time:

```bash
# Start Odoo and install through UI
odoo-bin -d your_database_name

# Or via command line
odoo-bin -d your_database_name -i adt_sentinel --log-level=debug
```

### Method 3: Using Docker (if applicable)
```bash
# Restart the container with update flag
docker-compose restart odoo
# Then upgrade from Apps menu in Odoo UI
```

## Verification Checklist

### ✅ Step 1: Module Installation
- [ ] Module installs without errors
- [ ] No ValidationError or ParseError appears
- [ ] "ADT Sentinel" appears in Apps menu

### ✅ Step 2: Menu Access
Navigate through all menu items:
- [ ] Sentinel → 🔍 Consultar DNI
- [ ] Sentinel → ✅ Reportes Vigentes
- [ ] Sentinel → 📋 Todos los Reportes
- [ ] Sentinel → 📚 Histórico

### ✅ Step 3: Tree View
Open "Todos los Reportes":
- [ ] Tree view loads without errors
- [ ] Columns display correctly: DNI, Fecha, Usuario, Año, Estado
- [ ] State field shows as badge
- [ ] Green highlighting for "vigente" records (if any exist)
- [ ] Gray highlighting for "vencido" records (if any exist)

### ✅ Step 4: Form View
Open any report or create test data:
- [ ] Form view loads without errors
- [ ] All fields are visible and properly formatted
- [ ] Status shows correctly (✅ Vigente or 📅 Vencido)
- [ ] Image field displays properly
- [ ] No chatter section appears (as expected)

### ✅ Step 5: Wizard Flow
Test the consultation wizard:
- [ ] Click "Consultar DNI"
- [ ] Wizard opens in modal
- [ ] Enter 8-digit DNI
- [ ] Click "Buscar"
- [ ] If found: Shows existing report
- [ ] If not found: Shows upload form
- [ ] Upload form accepts image file
- [ ] Save creates new record

### ✅ Step 6: Search/Filter
In tree view, test filters:
- [ ] "Vigentes" filter works
- [ ] "Vencidos" filter works
- [ ] "Mes Actual" filter works
- [ ] "Mis Consultas" filter works
- [ ] Search by DNI works
- [ ] Group by Estado works
- [ ] Group by Usuario works

## Expected Behavior

### Tree View Colors
- **Green rows**: Reports with state = 'vigente'
- **Gray rows**: Reports with state = 'vencido'
- **Badge**: State field shows colored badge

### Form View
- Clean form without chatter
- Modern syntax (no deprecated attrs)
- Conditional visibility working on status spans

### Wizard
- Clean modern forms
- Proper validation
- Image preview working

## Troubleshooting

### If errors persist:

1. **Clear cache and restart:**
```bash
# Stop Odoo
# Remove __pycache__ directories
find /path/to/addons/adt_sentinel -type d -name "__pycache__" -exec rm -rf {} +

# Restart Odoo with update
odoo-bin -d your_db -u adt_sentinel --log-level=debug
```

2. **Check logs:**
Look for specific errors in:
- View validation errors
- Field not found errors
- Widget compatibility errors

3. **Verify model registration:**
```bash
# In Odoo shell or psql
SELECT * FROM ir_model WHERE model = 'adt.sentinel.report';
SELECT * FROM ir_model_fields WHERE model = 'adt.sentinel.report';
```

4. **Verify view records:**
```bash
# In psql
SELECT name, type, arch_db FROM ir_ui_view 
WHERE model = 'adt.sentinel.report';
```

## Success Criteria

✅ All checkboxes above are checked
✅ No errors in Odoo log
✅ Module appears as "Installed" in Apps
✅ All views render correctly
✅ Workflow completes end-to-end

## Support

If issues persist:
1. Check `/var/log/odoo/odoo.log` for detailed errors
2. Review BUGFIX_SUMMARY.md for technical details
3. Verify Odoo version compatibility (tested on 15.0)
