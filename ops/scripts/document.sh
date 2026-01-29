#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$ROOT/docs/code/python"
TS_OUT_DIR="$ROOT/docs/code/typescript"

mkdir -p "$OUT_DIR" "$TS_OUT_DIR"

modules=(
  "tsunami"
  "orchestrator"
  "routing.server"
)

echo "document: generating autodoc into $OUT_DIR"

docker run --rm \
  -v "$ROOT:/workspace" \
  -w /workspace \
  python:3.12-slim \
  sh -lc "
    set -euo pipefail
    export PYTHONPATH=/workspace/src:/workspace/src/python_module
    python -m pip install --no-cache-dir cherrypy sqlalchemy pydantic pydantic-settings >/dev/null
    mkdir -p /workspace/docs/code/python
    cd /workspace/docs/code/python
    failed=0
    for mod in ${modules[*]}; do
      if python -m pydoc -w \"\$mod\" >/dev/null 2>&1; then
        echo \"document: wrote \${mod}.html\"
      else
        echo \"document: failed for \$mod (module not importable?)\" >&2
        failed=1
      fi
    done
    if [ \"\$failed\" -ne 0 ]; then
      exit 1
    fi
  "

echo "document: generating tsdoc into $TS_OUT_DIR"
docker run --rm \
  -v "$ROOT:/workspace" \
  -w /workspace \
  node:20 \
  sh -lc "npx --yes typedoc \
    --tsconfig src/orchestrator/vite/tsconfig.json \
    --out docs/code/typescript \
    --skipErrorChecking \
    --entryPointStrategy expand \
    src/orchestrator/vite/src/**/*.ts \
    src/orchestrator/vite/src/**/*.tsx \
    src/orchestrator/vite/vite.config.ts"
