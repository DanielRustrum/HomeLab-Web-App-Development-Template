#!/usr/bin/env sh
set -u  # <-- NOT -e

echo "[workspace] entrypoint starting..."

# (optional) try to fix perms first (see step 2)
mkdir -p /app/frontend/node_modules
chown -R coder:coder /app/frontend/node_modules 2>/dev/null || true

# Run bootstrap but DO NOT crash container if it fails
if ! runuser -u coder -- /usr/local/bin/workspace-bootstrap; then
  echo "[workspace] bootstrap failed (npm EACCES). Container will keep running so you can exec in and fix it." >&2
fi

exec "$@"
