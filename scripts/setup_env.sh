#!/usr/bin/env bash
set -euo pipefail

LOCATION="root"
PYTHON_BIN="${PYTHON_BIN:-python3}"

show_help() {
  cat <<'EOF'
Uso: setup_env.sh [--root | --local] [--help]

Opciones:
  --root    Crea o reutiliza el entorno virtual en ../.venv (por defecto)
  --local   Crea o reutiliza el entorno virtual en ./.venv (dentro de auraspace/)
  --help    Muestra esta ayuda

Variables de entorno:
  PYTHON_BIN  Interprete Python base a usar (por defecto: python3)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      LOCATION="root"
      shift
      ;;
    --local)
      LOCATION="local"
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Opcion no reconocida: $1" >&2
      show_help >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/.." && pwd)"
REQUIREMENTS_PATH="$APP_DIR/requirements.txt"

if [[ "$LOCATION" == "local" ]]; then
  VENV_DIR="$APP_DIR/.venv"
else
  VENV_DIR="$REPO_ROOT/.venv"
fi

VENV_PYTHON="$VENV_DIR/bin/python"

echo "=== Configuracion del entorno QA de AuraSpace ==="
echo "Proyecto         : $APP_DIR"
echo "Entorno virtual  : $VENV_DIR"
echo "Dependencias     : $REQUIREMENTS_PATH"

if [[ ! -f "$REQUIREMENTS_PATH" ]]; then
  echo "Error: no se encontro requirements.txt en $REQUIREMENTS_PATH" >&2
  exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Creando entorno virtual..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "El entorno virtual ya existe. Se reutilizara."
fi

echo "Actualizando pip..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo "Instalando dependencias desde requirements.txt..."
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_PATH"

echo ""
echo "Nota: No se descargan navegadores de Playwright automaticamente."
echo ""
echo "=== Resumen de versiones instaladas ==="
"$VENV_PYTHON" -c "import importlib.metadata as m, sys; pkgs=['Flask','pytest','pytest-cov','pytest-html','playwright']; print(f'Python: {sys.version.split()[0]}'); [print(f'{p}: {m.version(p)}') for p in pkgs]"

echo ""
echo "Para ejecutar las pruebas desde '$APP_DIR':"
echo "  \"$VENV_PYTHON\" scripts/run_tests.py --suite base"
echo "  \"$VENV_PYTHON\" scripts/run_tests.py --suite all"
