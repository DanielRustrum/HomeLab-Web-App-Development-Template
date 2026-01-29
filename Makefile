SHELL := /bin/sh

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3

NAMI := $(PYTHON) src/cli/nami.py

.DEFAULT_GOAL := help
.PHONY: help dev dev-stop workspace build document clean nami

help: ## Show available targets
	@awk 'BEGIN {FS=":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Spin up a contained env to test the nami CLI itself
	@docker compose -f ops/docker/nami-dev.compose.yaml up -d --build
	@docker compose -f ops/docker/nami-dev.compose.yaml exec -T nami-dev sh -c '\
		if [ -x /workspace/releases/bin/nami ]; then \
			install -m 755 /workspace/releases/bin/nami /usr/bin/nami; \
		elif [ -f /workspace/releases/bin/nami.py ]; then \
			install -m 755 /workspace/ops/scripts/nami-wrapper.sh /usr/bin/nami; \
		else \
			echo "nami: missing /workspace/releases/bin/nami(.py); run make build"; \
		fi'
	@docker compose -f ops/docker/nami-dev.compose.yaml exec -it nami-dev /bin/bash

dev-stop: ## Stop the nami dev container
	@docker compose -f ops/docker/nami-dev.compose.yaml down

nami: ## Run the nami CLI from releases/bin
	@releases/bin/nami.py $$@

workspace: ## Start the framework workspace for feature development
	@docker compose -f ops/docker/workspace.compose.yaml up -d --build

build: ## Build the nami command into releases/bin
	@bash ops/scripts/build_nami.sh

document: ## Auto-generate project docs
	@bash ops/scripts/document.sh

clean: ## Prune temp/build artifacts
	@bash ops/scripts/clean.sh
