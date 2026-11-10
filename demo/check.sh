#!/usr/bin/env bash
# Comprueba dependencias y servicios antes de grabar o construir la demo.
set -euo pipefail

MODE="${1:-full}"
DEMO_DIR="${DEMO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
DEMO_PDF="${DEMO_PDF:-${HOME}/Downloads/Manual de usuario app.pdf}"
PYTHON="${PYTHON:-python3}"

fail() {
  printf '\n[demo-check] ERROR: %s\n\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Falta \`$1\`. $2"
}

need_cmd node "Instala Node.js 22.6+ (recomendado Node 24)."
node -e "const major=Number(process.versions.node.split('.')[0]); if (major < 22) process.exit(1)" \
  || fail "Node.js es demasiado antiguo: $(node -v). Se necesita 22.6+ para ejecutar TypeScript sin compilar."

[[ -d "${DEMO_DIR}/node_modules/@playwright/test" ]] \
  || fail "Faltan dependencias Node. Ejecuta: cd demo && npm install"
[[ -d "${DEMO_DIR}/node_modules/yaml" ]] \
  || fail "Falta el paquete yaml. Ejecuta: cd demo && npm install"

if [[ "$MODE" != "dry" ]]; then
  FFMPEG="${FFMPEG:-ffmpeg}"
  FFPROBE="${FFPROBE:-ffprobe}"
  need_cmd "$FFMPEG" "Instala ffmpeg con: sudo apt install ffmpeg (o brew install ffmpeg)."
  need_cmd "$FFPROBE" "Instala ffmpeg con: sudo apt install ffmpeg (o brew install ffmpeg)."
  "$PYTHON" -c "import edge_tts" 2>/dev/null \
    || fail "Falta edge-tts. Ejecuta: $PYTHON -m pip install --user edge-tts"
  "$PYTHON" -c "import yaml" 2>/dev/null \
    || fail "Falta PyYAML. Ejecuta: $PYTHON -m pip install --user pyyaml"
fi

[[ -f "$DEMO_PDF" ]] \
  || fail "No existe el PDF de demo: $DEMO_PDF\nDefine DEMO_PDF con la ruta absoluta del manual."

APP_URL="${APP_URL:-http://localhost:4200}"
API_URL="${API_URL:-http://localhost:8000/v1}"

curl -fsS --max-time 5 "${APP_URL}/" >/dev/null 2>&1 \
  || fail "El frontend no responde en ${APP_URL}. Levanta el stack con: docker compose up -d --build"
curl -fsS --max-time 5 "${API_URL}/health" >/dev/null 2>&1 \
  || fail "La API no responde en ${API_URL}/health. Levanta el stack con: docker compose up -d --build"

printf '[demo-check] OK: %s\n' "$MODE"
printf '[demo-check] PDF: %s\n' "$DEMO_PDF"
printf '[demo-check] web: %s · api: %s\n' "$APP_URL" "$API_URL"
