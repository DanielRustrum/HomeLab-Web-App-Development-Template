#!/usr/bin/env bash
set -euo pipefail

# Build a production image for this repo using ops/docker/build.dockerfile
# Defaults:
#   IMAGE_NAME=homelab-app
#   IMAGE_TAG=latest
# Usage examples:
#   ./ops/scripts/build.sh
#   IMAGE_TAG=dev ./ops/scripts/build.sh
#   PLATFORMS=linux/amd64 ./ops/scripts/build.sh
#   PLATFORMS=linux/amd64,linux/arm64 PUSH=1 ./ops/scripts/build.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DOCKER_BIN="${DOCKER_BIN:-docker}"
IMAGE_NAME="${IMAGE_NAME:-homelab-app}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-ops/docker/build.dockerfile}"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

if [[ ! -f "$DOCKERFILE" ]]; then
  echo "ERROR: Dockerfile not found: $DOCKERFILE"
  exit 1
fi

echo "==> Repo root:  $ROOT"
echo "==> Dockerfile: $DOCKERFILE"
echo "==> Image:      $FULL_IMAGE"

# Your compose snippet mounts ./db/init, but the template commonly keeps SQL under src/db/init.
# Create ./db/init once (non-destructive) so compose works out of the box.
if [[ "${COPY_DB_INIT:-1}" == "1" ]]; then
  if [[ ! -d "$ROOT/db/init" ]]; then
    if [[ -d "$ROOT/src/db/init" ]]; then
      echo "==> Creating ./db/init from ./src/db/init (compose compatibility)"
      mkdir -p "$ROOT/db/init"
      cp -a "$ROOT/src/db/init/." "$ROOT/db/init/"
    else
      echo "!! WARNING: ./src/db/init not found; compose db init mount may fail."
    fi
  fi
fi

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"
BUILD_DATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

PLATFORMS="${PLATFORMS:-}"   # e.g. "linux/amd64" or "linux/amd64,linux/arm64"
PUSH="${PUSH:-0}"            # 1 to push (required for multi-platform buildx)
LOAD="${LOAD:-1}"            # 1 to load into local docker (single-platform buildx)

if [[ -n "$PLATFORMS" ]]; then
  echo "==> Using buildx (platforms: $PLATFORMS)"

  if ! $DOCKER_BIN buildx version >/dev/null 2>&1; then
    echo "ERROR: docker buildx not available."
    exit 1
  fi

  OUT_FLAG="--load"
  if [[ "$PUSH" == "1" ]]; then
    OUT_FLAG="--push"
  else
    # buildx cannot --load multi-platform manifests
    if [[ "$PLATFORMS" == *","* ]]; then
      echo "ERROR: Multi-platform build requires PUSH=1 (or set a single platform)."
      exit 1
    fi
    if [[ "$LOAD" != "1" ]]; then
      OUT_FLAG="--output=type=docker"
    fi
  fi

  $DOCKER_BIN buildx build \
    --platform "$PLATFORMS" \
    -f "$DOCKERFILE" \
    -t "$FULL_IMAGE" \
    --build-arg "VCS_REF=${GIT_SHA}" \
    --build-arg "BUILD_DATE=${BUILD_DATE}" \
    . \
    $OUT_FLAG
else
  echo "==> Using docker build (single-platform)"
  $DOCKER_BIN build \
    -f "$DOCKERFILE" \
    -t "$FULL_IMAGE" \
    --build-arg "VCS_REF=${GIT_SHA}" \
    --build-arg "BUILD_DATE=${BUILD_DATE}" \
    .
fi

echo "==> Done: $FULL_IMAGE"
