#!/bin/bash

# Script de Actualización Rápida del Módulo adt_sentinel
# Uso: bash actualizar_modulo.sh [nombre_base_datos]

set -e  # Salir si hay errores

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "════════════════════════════════════════════════════════════════"
echo -e "${BLUE}🔄 Actualización del Módulo adt_sentinel${NC}"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Verificar si estamos en el directorio correcto
if [ ! -f "__manifest__.py" ]; then
    echo -e "${RED}❌ Error: Debes ejecutar este script desde el directorio del módulo adt_sentinel${NC}"
    exit 1
fi

echo -e "${GREEN}✅${NC} Directorio correcto detectado"
echo ""

# Verificar archivos modificados
echo "📁 Verificando archivos modificados..."
FILES=(
    "models/sentinel.py"
    "views/sentinel_menu.xml"
    "wizard/sentinel_query_wizard.py"
    "wizard/sentinel_query_wizard_views.xml"
)

ALL_OK=true
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}  ✅${NC} $file"
    else
        echo -e "${RED}  ❌${NC} $file NO ENCONTRADO"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo -e "${RED}❌ Faltan archivos. Verifica la implementación.${NC}"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🐳 Detectando entorno de Odoo..."
echo "════════════════════════════════════════════════════════════════"
echo ""

# Ir al directorio raíz del proyecto (donde está docker-compose.yml)
cd ../../../

if [ -f "docker-compose.yml" ]; then
    echo -e "${GREEN}✅${NC} Docker Compose detectado"
    echo ""

    # Detectar nombre del contenedor
    CONTAINER=$(docker-compose ps -q web 2>/dev/null)

    if [ -z "$CONTAINER" ]; then
        echo -e "${YELLOW}⚠️  Contenedor web no está corriendo${NC}"
        echo ""
        echo "¿Deseas iniciar los contenedores? (s/n)"
        read -r response
        if [[ "$response" =~ ^[Ss]$ ]]; then
            echo "Iniciando contenedores..."
            docker-compose up -d
            sleep 5
            CONTAINER=$(docker-compose ps -q web)
        else
            echo -e "${RED}❌ Cancelado por el usuario${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}✅${NC} Contenedor web activo: $CONTAINER"
    echo ""

    # Obtener nombre de la base de datos
    if [ -z "$1" ]; then
        echo -e "${YELLOW}⚠️  No se especificó nombre de base de datos${NC}"
        echo ""
        echo "Bases de datos disponibles:"
        docker exec "$CONTAINER" psql -U odoo -l -t | grep -v "template" | grep -v "postgres" | awk '{print "  - " $1}'
        echo ""
        echo "Ingresa el nombre de la base de datos:"
        read -r DB_NAME
    else
        DB_NAME="$1"
    fi

    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo -e "${BLUE}📦 Actualizando módulo adt_sentinel en base de datos: $DB_NAME${NC}"
    echo "════════════════════════════════════════════════════════════════"
    echo ""

    # Actualizar el módulo
    echo "Ejecutando actualización..."
    docker exec "$CONTAINER" odoo -u adt_sentinel -d "$DB_NAME" --stop-after-init --log-level=info

    if [ $? -eq 0 ]; then
        echo ""
        echo "════════════════════════════════════════════════════════════════"
        echo -e "${GREEN}✅ ACTUALIZACIÓN EXITOSA${NC}"
        echo "════════════════════════════════════════════════════════════════"
        echo ""
        echo "📝 Próximos pasos:"
        echo "   1. Reiniciar el servicio web:"
        echo "      ${BLUE}docker-compose restart web${NC}"
        echo ""
        echo "   2. Probar el wizard:"
        echo "      - Ir a: Sentinel > 🔍 Consultar DNI"
        echo "      - Ingresar un DNI de 8 dígitos"
        echo "      - Hacer clic en 'Buscar'"
        echo ""
        echo "   3. Verificar logs si hay problemas:"
        echo "      ${BLUE}docker-compose logs -f web${NC}"
        echo ""

        # Preguntar si desea reiniciar
        echo "¿Deseas reiniciar el servicio web ahora? (s/n)"
        read -r response
        if [[ "$response" =~ ^[Ss]$ ]]; then
            echo ""
            echo "Reiniciando servicio web..."
            docker-compose restart web
            echo -e "${GREEN}✅ Servicio reiniciado${NC}"
        fi
    else
        echo ""
        echo "════════════════════════════════════════════════════════════════"
        echo -e "${RED}❌ ERROR EN LA ACTUALIZACIÓN${NC}"
        echo "════════════════════════════════════════════════════════════════"
        echo ""
        echo "🔍 Revisa los logs para más detalles:"
        echo "   ${BLUE}docker-compose logs web${NC}"
        echo ""
        exit 1
    fi

else
    echo -e "${YELLOW}⚠️  Docker Compose no detectado${NC}"
    echo ""
    echo "Opciones alternativas:"
    echo ""
    echo "1. Si Odoo está corriendo localmente:"
    echo "   ${BLUE}./odoo-bin -u adt_sentinel -d <database> --stop-after-init${NC}"
    echo ""
    echo "2. Si Odoo está en un contenedor diferente:"
    echo "   ${BLUE}docker exec -it <contenedor> odoo -u adt_sentinel -d <database> --stop-after-init${NC}"
    echo ""
    echo "3. Desde la interfaz web de Odoo:"
    echo "   - Ir a: Apps (Aplicaciones)"
    echo "   - Buscar: adt_sentinel"
    echo "   - Clic en: Actualizar"
    echo ""
fi

echo "════════════════════════════════════════════════════════════════"
