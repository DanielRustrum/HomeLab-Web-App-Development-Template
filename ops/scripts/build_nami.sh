#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN_DIR="$ROOT/releases/bin"
NAMI_SRC="$ROOT/src/cli/nami.py"
COMMANDS_SRC="$ROOT/src/cli/commands"
TEMPLATE_SRC="$ROOT/template"
TS_MODULE_SRC="$ROOT/src/ts_module"
PY_MODULE_SRC="$ROOT/src/python_module"

if [[ ! -f "$NAMI_SRC" ]]; then
  echo "nami: missing file: $NAMI_SRC" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"

cp -f "$NAMI_SRC" "$BIN_DIR/nami.py"
chmod +x "$BIN_DIR/nami.py"

if [[ -d "$COMMANDS_SRC" ]]; then
  mkdir -p "$BIN_DIR/commands"
  cp -R "$COMMANDS_SRC/." "$BIN_DIR/commands/"
fi

if [[ -d "$TEMPLATE_SRC" ]]; then
  mkdir -p "$BIN_DIR/template"
  cp -R "$TEMPLATE_SRC/." "$BIN_DIR/template/"
fi

if [[ -d "$TS_MODULE_SRC" ]]; then
  if [[ -f "$TS_MODULE_SRC/package.json" ]] && command -v npm >/dev/null; then
    (
      cd "$TS_MODULE_SRC"
      npm run -s build
    )
  else
    echo "nami: skipping ts_module build (npm or package.json not found)" >&2
  fi

  mkdir -p "$BIN_DIR/ts_module"
  cp -R "$TS_MODULE_SRC/." "$BIN_DIR/ts_module/"
fi

if [[ -d "$PY_MODULE_SRC" ]]; then
  if [[ -f "$PY_MODULE_SRC/pyproject.toml" ]] && command -v python >/dev/null; then
    if python - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("build") else 1)
PY
    then
      (
        cd "$PY_MODULE_SRC"
        python -m build
      )
    else
      echo "nami: skipping python_module build (python build module not installed)" >&2
    fi
  else
    echo "nami: skipping python_module build (python or pyproject.toml not found)" >&2
  fi

  mkdir -p "$BIN_DIR/python_module"
  cp -R "$PY_MODULE_SRC/." "$BIN_DIR/python_module/"
fi

echo "nami: executable -> $BIN_DIR/nami.py"
