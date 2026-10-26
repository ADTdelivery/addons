#!/usr/bin/env bash
# Deploy a EC2: git push -> git pull en el servidor -> actualiza modulos Odoo -> reinicia el contenedor.
#
# Uso:
#   ./deploy.sh                      # detecta automaticamente los modulos que cambiaron
#   ./deploy.sh -m adt_flota_360     # fuerza los modulos a actualizar (separados por coma)
#   ./deploy.sh -c "mensaje"         # hace commit de todo antes de subir
#   ./deploy.sh -n                   # solo pull + restart, sin actualizar modulos
set -euo pipefail

# ---------- Configuracion (ajusta estos valores) ----------
EC2_HOST="ubuntu@TU_IP_O_DNS"
SSH_KEY="$HOME/.ssh/tu-llave.pem"
REMOTE_REPO_PATH="/opt/odoo/addons"        # ruta del repo en el servidor (montada como volumen en docker)
CONTAINER="odoo"                           # nombre del contenedor (docker ps)
DB_NAME="nombre_de_tu_bd"
ODOO_CONF="/etc/odoo/odoo.conf"            # ruta del odoo.conf DENTRO del contenedor
BRANCH="main"
# ----------------------------------------------------------

MODULES=""
COMMIT_MSG=""
SKIP_UPDATE=0

while getopts "m:c:n" opt; do
  case $opt in
    m) MODULES="$OPTARG" ;;
    c) COMMIT_MSG="$OPTARG" ;;
    n) SKIP_UPDATE=1 ;;
    *) echo "Uso: $0 [-m mod1,mod2] [-c 'mensaje'] [-n]"; exit 1 ;;
  esac
done

cd "$(dirname "$0")"

if [[ -n "$COMMIT_MSG" ]]; then
  git add -A
  git commit -m "$COMMIT_MSG"
elif [[ -n "$(git status --porcelain)" ]]; then
  echo "Tienes cambios sin commit. Usa -c 'mensaje' o haz commit antes." >&2
  exit 1
fi

echo ">> git push origin $BRANCH"
git push origin "$BRANCH"

echo ">> Desplegando en $EC2_HOST"
ssh -i "$SSH_KEY" "$EC2_HOST" bash -s -- \
  "$REMOTE_REPO_PATH" "$CONTAINER" "$DB_NAME" "$ODOO_CONF" "$BRANCH" "$MODULES" "$SKIP_UPDATE" <<'REMOTE'
set -euo pipefail
REPO="$1"; CONTAINER="$2"; DB="$3"; CONF="$4"; BRANCH="$5"; MODULES="$6"; SKIP_UPDATE="$7"

cd "$REPO"
OLD=$(git rev-parse HEAD)
git pull --ff-only origin "$BRANCH"
NEW=$(git rev-parse HEAD)

# Detecta modulos cambiados: primera carpeta de cada archivo modificado que tenga __manifest__.py
if [[ -z "$MODULES" && "$OLD" != "$NEW" ]]; then
  MODULES=$(git diff --name-only "$OLD" "$NEW" | cut -d/ -f1 | sort -u | while read -r d; do
    [[ -f "$d/__manifest__.py" ]] && echo "$d"
  done | paste -sd, -)
fi

if [[ "$SKIP_UPDATE" == "0" && -n "$MODULES" ]]; then
  echo ">> Actualizando modulos: $MODULES"
  # Usa las credenciales de BD de las variables de entorno del contenedor (imagen oficial: HOST, USER, PASSWORD)
  docker exec "$CONTAINER" sh -c "odoo -c '$CONF' -d '$DB' -u '$MODULES' --stop-after-init --no-http \
    \${HOST:+--db_host=\$HOST} \${USER:+--db_user=\$USER} \${PASSWORD:+--db_password=\$PASSWORD}"
else
  echo ">> No hay modulos que actualizar"
fi

echo ">> Reiniciando contenedor $CONTAINER"
docker restart "$CONTAINER"
echo ">> Listo ($OLD -> $NEW)"
REMOTE
