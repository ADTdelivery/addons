# ADT Sentinel Module - Installation Guide

## Quick Start

### 1. Installation

```bash
# Copy module to addons directory
cp -r adt_sentinel /path/to/odoo/addons/

# Restart Odoo server
sudo systemctl restart odoo
# OR
./odoo-bin -c odoo.conf --stop-after-init

# Update apps list
# Go to: Apps > Update Apps List
```

### 2. Install Module

1. Go to Apps
2. Remove "Apps" filter
3. Search "ADT Sentinel"
4. Click Install

### 3. Verify Installation

After installation, you should see:
- New menu "Sentinel" in top menu bar
- 4 submenu items:
  - 🔍 Consultar DNI
  - ✅ Reportes Vigentes
  - 📋 Todos los Reportes
  - 📚 Histórico

### 4. First Use

1. Go to: Sentinel > Consultar DNI
2. Enter a DNI (8 digits): e.g., 12345678
3. Click "Buscar"
4. If not found, upload report image
5. Done!

## Troubleshooting

### Error: "Module not found"
- Check that folder name is exactly `adt_sentinel`
- Verify `__manifest__.py` exists
- Update apps list again

### Error: "Access denied"
- Make sure you're logged in as Administrator
- Check user groups: Settings > Users & Companies > Users

### Error: "Database constraint violation"
- This is expected if trying to create duplicate report
- Search for existing report first

## Configuration

No configuration needed. Module works out of the box.

## Permissions

Default permissions:
- **All Users (group_user):** Can query, view, and upload reports
- **System Admins:** Full access + historic view

To customize:
1. Go to: Settings > Technical > Security > Access Rights
2. Search: "sentinel"
3. Edit as needed

## Backup

Images are stored in filestore:
```
/path/to/odoo/filestore/[database_name]/
```

Make sure to include filestore in backups.

## Uninstall

⚠️ WARNING: Uninstalling will NOT delete records (by design).

To uninstall:
1. Apps > Search "ADT Sentinel"
2. Click Uninstall
3. Confirm

Data remains in database table: `adt_sentinel_report`

## Support

For issues, check:
- README.md
- SECURITY_ARCHITECTURE.md
- TEST_CASES.md

Contact: ADT Development Team
