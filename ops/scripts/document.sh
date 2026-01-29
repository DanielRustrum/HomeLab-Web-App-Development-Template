#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$ROOT/docs/autodoc"

mkdir -p "$OUT_DIR"

export PYTHONPATH="$ROOT/src:$ROOT/src/python_module"

modules=(
  "tsunami"
  "orchestrator"
  "routing.server"
)

echo "document: generating autodoc into $OUT_DIR"

pushd "$OUT_DIR" >/dev/null
failed=0
for mod in "${modules[@]}"; do
  if python -m pydoc -w "$mod" >/dev/null 2>&1; then
    echo "document: wrote ${mod}.html"
  else
    echo "document: failed for $mod (module not importable?)" >&2
    failed=1
  fi
done
popd >/dev/null

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi
