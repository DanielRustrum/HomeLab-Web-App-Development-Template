#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "clean: removing caches and build artifacts"

find "$ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" \) -delete

rm -rf \
  "$ROOT/.pytest_cache" \
  "$ROOT/.mypy_cache" \
  "$ROOT/.ruff_cache" \
  "$ROOT/.coverage" \
  "$ROOT/coverage.xml" \
  "$ROOT/htmlcov"

find "$ROOT" -type d \( -name "node_modules" -o -name "dist" -o -name ".vite" -o -name ".turbo" \) -prune -exec rm -rf {} +

# Note: Do not touch the template directory; it is used by nami to scaffold projects.

if [[ "${CLEAN_VENV:-0}" == "1" ]]; then
  rm -rf "$ROOT/.venv" "$ROOT/venv" "$ROOT/env"
fi

echo "clean: done"
