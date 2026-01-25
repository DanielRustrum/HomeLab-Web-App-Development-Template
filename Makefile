# -----------------------------------------------------------------------------
# Makefile — Local Dev Commands
#
# Goals:
#   - Make commands work no matter where you run `make` from (repo-root anchored)
#   - Provide ergonomic wrappers around docker compose
#   - Keep common knobs configurable via variables (SVC, TAIL, SINCE, etc.)
#
# Notes:
#   - Docker Compose is increasingly Bake-first. Some environments may require
#     Bake; others may choke on path resolution. We keep the knob available.
#     (You can remove COMPOSE_BAKE usage later once your paths are fixed.)
# -----------------------------------------------------------------------------

# (Legacy) Disable Bake if you still need it in your environment.
# Newer docker/compose warns this is deprecated.
export COMPOSE_BAKE := false

SHELL := /usr/bin/env bash

# Absolute path to repo root (directory containing this Makefile)
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# Compose files
DEV_YAML  := $(ROOT)/ops/docker/dev.compose.yaml
WORK_YAML := $(ROOT)/ops/docker/workspace.compose.yaml

# -----------------------------------------------------------------------------#
# User-tunable variables (defaults)
# -----------------------------------------------------------------------------#

# Logs
TAIL  ?= 200     # number of log lines to show initially
SINCE ?=         # e.g. 10m, 1h
SVC   ?=         # optional service name (frontend/app/db/etc.)

# Clean options
NOCACHE  ?=      # set to 1 to prune docker builder cache
NUKELocal ?=     # set to 1 to delete local dev artifacts

.PHONY: help dev-start dev-logs dev-workspace dev-stop dev-restart build-start run-start clean

# -----------------------------------------------------------------------------#
# Help
# -----------------------------------------------------------------------------#
help:
	@echo ""
	@echo "HomeLab Dev Make Targets"
	@echo "Repo: $(ROOT)"
	@echo ""
	@echo "Usage:"
	@echo "  make <target> [VAR=value]"
	@echo ""
	@echo "Targets:"
	@printf "  %-18s %s\n" "dev-start"      "Start dev services (build if needed) and run in background"
	@printf "  %-18s %s\n" "dev-logs"       "Tail logs (optionally filter by service)"
	@printf "  %-18s %s\n" "dev-workspace"  "Start the dev workspace container(s)"
	@printf "  %-18s %s\n" "dev-stop"       "Stop dev + workspace stacks (keeps named volumes)"
	@printf "  %-18s %s\n" "dev-restart"    "Restart a single service (default: SVC=$(if $(SVC),$(SVC),<none>))"
	@printf "  %-18s %s\n" "build-start"    "Run ops/scripts/build.sh (your image build pipeline)"
	@printf "  %-18s %s\n" "run-start"      "Start using compose without rebuild (uses dev compose)"
	@printf "  %-18s %s\n" "clean"          "Stop dev stack and remove named volumes (DATA WIPE)"
	@echo ""
	@echo "Variables:"
	@printf "  %-10s %s\n" "SVC"      "Service name (used by dev-logs/dev-restart). Example: SVC=frontend"
	@printf "  %-10s %s\n" "TAIL"     "Log tail lines (default: $(TAIL))"
	@printf "  %-10s %s\n" "SINCE"    "Show logs since duration. Example: SINCE=10m"
	@printf "  %-10s %s\n" "NOCACHE"  "If set, clean also prunes docker builder cache. Example: NOCACHE=1"
	@printf "  %-10s %s\n" "NUKELocal""If set, clean also deletes local artifacts. Example: NUKELocal=1"
	@echo ""
	@echo "Examples:"
	@echo "  make dev-start"
	@echo "  make dev-logs"
	@echo "  make dev-logs SVC=app TAIL=50"
	@echo "  make dev-logs SINCE=10m"
	@echo "  make dev-restart SVC=frontend"
	@echo "  make clean NOCACHE=1"
	@echo ""

# -----------------------------------------------------------------------------#
# Dev stack
# -----------------------------------------------------------------------------#

dev-start:
	cd "$(ROOT)" && COMPOSE_BAKE=false docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" up -d --build
	@echo "➜  Local:   http://localhost:5173/"

dev-logs:
	cd "$(ROOT)" && \
	ARGS="-f --tail=$(TAIL)"; \
	if [ -n "$(SINCE)" ]; then ARGS="$$ARGS --since=$(SINCE)"; fi; \
	docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" logs $$ARGS $(SVC)

dev-workspace:
	cd "$(ROOT)" && COMPOSE_BAKE=false docker compose --project-directory "$(ROOT)" -f "$(WORK_YAML)" up -d --build

dev-workspace-stop:
	cd "$(ROOT)" && docker compose --project-directory "$(ROOT)" -f "$(WORK_YAML)" down --remove-orphans; \
	echo "✅ Stopped."

dev-stop:
	@set -e; \
	echo "Stopping dev stack..."; \
	cd "$(ROOT)" && docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" down --remove-orphans; \
	echo "✅ Stopped."

dev-restart:
	cd "$(ROOT)" && docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" restart $(SVC)

# -----------------------------------------------------------------------------#
# Build/run
# -----------------------------------------------------------------------------#

build-start:
	./ops/scripts/build.sh

run-start:
	cd "$(ROOT)" && COMPOSE_BAKE=false docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" up -d

# -----------------------------------------------------------------------------#
# Clean (destructive)
#   - Removes named volumes for dev compose (wipes DB/data)
# -----------------------------------------------------------------------------#

clean:
	@set -e; \
	echo "Stopping dev stack (if running)..."; \
	cd "$(ROOT)" && docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" down --remove-orphans; \
	echo "Removing dev stack containers/networks + named volumes..."; \
	cd "$(ROOT)" && docker compose --project-directory "$(ROOT)" -f "$(DEV_YAML)" down -v --remove-orphans; \
	if [ -n "$(NOCACHE)" ]; then \
		echo "Pruning build cache..."; \
		docker builder prune -f; \
	fi; \
	if [ -n "$(NUKELocal)" ]; then \
		echo "Deleting local dev artifacts..."; \
		rm -rf "$(ROOT)/workspace" "$(ROOT)/.workspace" "$(ROOT)/.cache" "$(ROOT)/tmp" "$(ROOT)/logs" || true; \
	fi; \
	echo "✅ Clean complete."
