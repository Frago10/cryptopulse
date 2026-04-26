#!/usr/bin/env bash
# =============================================================================
# CryptoPulse — Bootstrap para macOS / Linux / Git Bash en Windows
#
# Uso:
#   bash scripts/setup.sh            # Fase 1 (batch) - rápido
#   bash scripts/setup.sh --full     # Todo el stack
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}==> $1${NC}"; }
ok()   { echo -e "${GREEN}[OK] $1${NC}"; }
warn() { echo -e "${YELLOW}[!!] $1${NC}"; }
fail() { echo -e "${RED}[XX] $1${NC}"; exit 1; }

FULL=false
for arg in "$@"; do
  case $arg in
    --full) FULL=true ;;
  esac
done

# ---------- 1. Detectar Python ----------
step "Detectando Python 3.9+ ..."
PYTHON=""
for cand in python3.11 python3.12 python3.10 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver=$("$cand" --version 2>&1 | awk '{print $2}')
    maj=$(echo "$ver" | cut -d. -f1)
    min=$(echo "$ver" | cut -d. -f2)
    if [ "$maj" = "3" ] && [ "$min" -ge 9 ]; then
      PYTHON="$cand"
      ok "Python encontrado: $cand ($ver)"
      break
    fi
  fi
done
[ -z "$PYTHON" ] && fail "No se encontró Python 3.9+. Instálalo desde python.org"

# ---------- 2. Crear venv ----------
step "Creando venv ..."
if [ -d ".venv" ]; then
  warn ".venv ya existe; se reutiliza"
else
  "$PYTHON" -m venv .venv
  ok "venv creado"
fi

# Detectar si estamos en Windows Git Bash (Scripts) o Linux/Mac (bin)
if [ -f ".venv/Scripts/python.exe" ]; then
  VENV_PY=".venv/Scripts/python.exe"
  VENV_PIP=".venv/Scripts/pip.exe"
else
  VENV_PY=".venv/bin/python"
  VENV_PIP=".venv/bin/pip"
fi

# ---------- 3. pip upgrade ----------
step "Actualizando pip / wheel / setuptools ..."
"$VENV_PY" -m pip install --upgrade pip wheel setuptools >/dev/null
ok "pip actualizado a $("$VENV_PIP" --version | awk '{print $2}')"

# ---------- 4. Requirements ----------
REQ=$([ "$FULL" = true ] && echo "requirements.txt" || echo "requirements-batch.txt")
step "Instalando deps desde $REQ (puede tardar 1-3 min) ..."
"$VENV_PIP" install -r "$REQ"
ok "Dependencias instaladas"

# ---------- 5. Sanity check ----------
step "Verificando imports ..."
"$VENV_PY" -c "
import sys; sys.path.insert(0, '.')
from ingestion.utils.config import settings
from ingestion.utils.minio_client import MinIOClient
from ingestion.batch import coingecko_loader, fng_loader
print('imports OK — symbols:', settings.symbols_list[:3], '...')
"

echo -e "\n${GREEN}=== SETUP COMPLETO ===${NC}"
echo "Activa el venv con:"
if [ -f ".venv/Scripts/python.exe" ]; then
  echo -e "  ${YELLOW}source .venv/Scripts/activate${NC}   (Git Bash)"
else
  echo -e "  ${YELLOW}source .venv/bin/activate${NC}"
fi
echo ""
echo "Siguientes comandos:"
echo "  $VENV_PY -m pytest tests/test_coingecko_loader.py -v"
echo "  $VENV_PY -m ingestion.batch.coingecko_loader"
echo "  $VENV_PY -m ingestion.batch.fng_loader"
echo "  $VENV_PY -m ingestion.batch.run_all"
