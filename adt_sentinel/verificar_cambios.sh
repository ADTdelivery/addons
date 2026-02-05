#!/bin/bash

# Script de Verificación Rápida - ADT Sentinel
# Este script verifica que los archivos modificados estén correctos

echo "=================================================="
echo "🔍 VERIFICACIÓN DEL MÓDULO ADT_SENTINEL"
echo "=================================================="
echo ""

MODULE_PATH="/Users/jhon.curi/Desktop/personal/odoo/addons/adt_sentinel"

# 1. Verificar que los archivos existen
echo "📁 Verificando archivos..."
if [ -f "$MODULE_PATH/wizard/sentinel_query_wizard.py" ]; then
    echo "  ✅ sentinel_query_wizard.py existe"
else
    echo "  ❌ sentinel_query_wizard.py NO encontrado"
fi

if [ -f "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml" ]; then
    echo "  ✅ sentinel_query_wizard_views.xml existe"
else
    echo "  ❌ sentinel_query_wizard_views.xml NO encontrado"
fi

echo ""

# 2. Verificar contenido del archivo Python
echo "🐍 Verificando método action_search en Python..."
if grep -q "view_id.*env.ref.*view_sentinel_query_wizard_form_search" "$MODULE_PATH/wizard/sentinel_query_wizard.py"; then
    echo "  ✅ Método action_search actualizado correctamente"
else
    echo "  ⚠️  Método action_search podría necesitar revisión"
fi

echo ""

# 3. Verificar contenido del archivo XML
echo "📄 Verificando vista XML..."
if grep -q "Adjuntar Imagen del Reporte" "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml"; then
    echo "  ✅ Vista de carga de imagen actualizada"
else
    echo "  ⚠️  Vista de carga de imagen podría necesitar revisión"
fi

if grep -q "new_report_image.*widget=\"binary\"" "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml"; then
    echo "  ✅ Campo de imagen configurado correctamente"
else
    echo "  ❌ Campo de imagen NO encontrado o mal configurado"
fi

echo ""

# 4. Contar las vistas definidas
NUM_VIEWS=$(grep -c "record id=\"view_sentinel_query_wizard" "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml")
echo "📊 Número de vistas definidas: $NUM_VIEWS"
if [ "$NUM_VIEWS" -eq 1 ]; then
    echo "  ✅ Vista única consolidada (correcto)"
else
    echo "  ⚠️  Se encontraron $NUM_VIEWS vistas (debería ser 1)"
fi

echo ""

# 5. Verificar sintaxis XML
echo "🔍 Verificando sintaxis XML..."
if command -v xmllint &> /dev/null; then
    if xmllint --noout "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml" 2>/dev/null; then
        echo "  ✅ Sintaxis XML válida"
    else
        echo "  ❌ ERROR en sintaxis XML"
        xmllint --noout "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml"
    fi
else
    echo "  ⚠️  xmllint no disponible (no se puede verificar sintaxis)"
fi

echo ""

# 6. Verificar sintaxis Python
echo "🐍 Verificando sintaxis Python..."
if command -v python3 &> /dev/null; then
    if python3 -m py_compile "$MODULE_PATH/wizard/sentinel_query_wizard.py" 2>/dev/null; then
        echo "  ✅ Sintaxis Python válida"
    else
        echo "  ❌ ERROR en sintaxis Python"
        python3 -m py_compile "$MODULE_PATH/wizard/sentinel_query_wizard.py"
    fi
else
    echo "  ⚠️  python3 no disponible (no se puede verificar sintaxis)"
fi

echo ""

# 7. Verificar permisos
echo "🔐 Verificando permisos de archivos..."
if [ -r "$MODULE_PATH/wizard/sentinel_query_wizard.py" ]; then
    echo "  ✅ sentinel_query_wizard.py es legible"
else
    echo "  ❌ sentinel_query_wizard.py NO es legible"
fi

if [ -r "$MODULE_PATH/wizard/sentinel_query_wizard_views.xml" ]; then
    echo "  ✅ sentinel_query_wizard_views.xml es legible"
else
    echo "  ❌ sentinel_query_wizard_views.xml NO es legible"
fi

echo ""
echo "=================================================="
echo "✅ VERIFICACIÓN COMPLETADA"
echo "=================================================="
echo ""
echo "📝 Próximos pasos:"
echo "  1. Actualizar el módulo en Odoo (ver ACTUALIZAR_MODULO.md)"
echo "  2. Probar el wizard: Sentinel > Consultar DNI"
echo "  3. Ingresar un DNI y hacer clic en Buscar"
echo ""
echo "🔗 Documentación completa: $MODULE_PATH/ACTUALIZAR_MODULO.md"
echo ""
