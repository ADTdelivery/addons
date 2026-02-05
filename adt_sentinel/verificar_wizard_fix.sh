#!/bin/bash

# Script de verificación de cambios para el wizard de Sentinel
# Ejecutar: bash verificar_wizard_fix.sh

echo "════════════════════════════════════════════════════════════════"
echo "🔍 Verificación de Corrección del Wizard Sentinel"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Archivos modificados
FILES=(
    "models/sentinel.py"
    "views/sentinel_menu.xml"
    "wizard/sentinel_query_wizard.py"
    "wizard/sentinel_query_wizard_views.xml"
)

echo "📁 Verificando archivos modificados..."
echo ""

ALL_OK=true

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅${NC} $file existe"
    else
        echo -e "${RED}❌${NC} $file NO ENCONTRADO"
        ALL_OK=false
    fi
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🔎 Verificando implementaciones clave..."
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar método action_open_sentinel_wizard
if grep -q "def action_open_sentinel_wizard" models/sentinel.py; then
    echo -e "${GREEN}✅${NC} Método action_open_sentinel_wizard() encontrado"
else
    echo -e "${RED}❌${NC} Método action_open_sentinel_wizard() NO encontrado"
    ALL_OK=false
fi

# Verificar ir.actions.server
if grep -q "ir.actions.server" views/sentinel_menu.xml; then
    echo -e "${GREEN}✅${NC} Acción de servidor configurada"
else
    echo -e "${RED}❌${NC} Acción de servidor NO configurada"
    ALL_OK=false
fi

# Verificar force_save
if grep -q "force_save=\"1\"" wizard/sentinel_query_wizard_views.xml; then
    echo -e "${GREEN}✅${NC} force_save=\"1\" aplicado al botón"
else
    echo -e "${YELLOW}⚠️${NC}  force_save=\"1\" NO encontrado (puede ser opcional)"
fi

# Verificar que no existe la acción XML antigua
if grep -q "ir.actions.act_window.*action_sentinel_query_wizard" wizard/sentinel_query_wizard_views.xml; then
    echo -e "${RED}❌${NC} Acción XML antigua todavía existe (debe eliminarse)"
    ALL_OK=false
else
    echo -e "${GREEN}✅${NC} Acción XML antigua eliminada correctamente"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"

if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}✅ VERIFICACIÓN EXITOSA${NC}"
    echo ""
    echo "📝 Próximos pasos:"
    echo "   1. Actualizar el módulo en Odoo"
    echo "   2. Ir a Apps > adt_sentinel > Actualizar"
    echo "   3. Probar el wizard desde el menú '🔍 Consultar DNI'"
else
    echo -e "${RED}❌ VERIFICACIÓN FALLIDA${NC}"
    echo ""
    echo "⚠️  Hay problemas que deben corregirse antes de actualizar"
fi

echo "════════════════════════════════════════════════════════════════"
