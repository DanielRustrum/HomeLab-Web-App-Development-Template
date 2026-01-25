#!/usr/bin/env sh
set -eu

CACHE_DIR="/home/coder/.cache/homelab-template"
VENV_DIR="/home/coder/.venv"

mkdir -p "$CACHE_DIR"

echo "[workspace] bootstrap starting..."

# ---- Python deps ----
if [ -f backend/requirements.txt ]; then
  req_hash="$(sha256sum backend/requirements.txt | awk '{print $1}')"
  if [ ! -f "$CACHE_DIR/req.hash" ] || [ "$(cat "$CACHE_DIR/req.hash")" != "$req_hash" ]; then
    echo "[workspace] Updating Python deps..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install -U pip
    "$VENV_DIR/bin/pip" install -r backend/requirements.txt
    echo "$req_hash" > "$CACHE_DIR/req.hash"
  fi
fi

# ---- Frontend deps ----
if [ -f src/frontend/package.json ]; then
  lock_file="src/frontend/package.json"
  [ -f src/frontend/package-lock.json ] && lock_file="src/frontend/package-lock.json"

  fe_hash="$(sha256sum "$lock_file" | awk '{print $1}')"
  if [ ! -d src/frontend/node_modules ] || [ ! -f "$CACHE_DIR/fe.hash" ] || [ "$(cat "$CACHE_DIR/fe.hash")" != "$fe_hash" ]; then
    echo "[workspace] Installing frontend deps..."
    (cd frontend && ( [ -f package-lock.json ] && npm ci || npm install ))
    echo "$fe_hash" > "$CACHE_DIR/fe.hash"
  fi
fi

echo "[workspace] bootstrap done."
