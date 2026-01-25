#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN_DIR="$ROOT/releases/bin"
NAMI_SRC="$ROOT/src/cli/nami.py"
COMMANDS_SRC="$ROOT/src/cli/commands"
TEMPLATE_SRC="$ROOT/template"

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

echo "nami: executable -> $BIN_DIR/nami.py"
