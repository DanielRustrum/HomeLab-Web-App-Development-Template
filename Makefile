SHELL := /bin/sh

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3

NAMI := $(PYTHON) src/cli/nami.py

.DEFAULT_GOAL := help
.PHONY: help dev workspace build document clean

help: ## Show available targets
	@awk 'BEGIN {FS=":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Spin up a contained env to test the nami CLI itself
	@docker compose -f ops/docker/nami-dev.compose.yaml up -d --build

workspace: ## Start the framework workspace for feature development
	@docker compose -f ops/docker/workspace.compose.yaml up -d --build

build: ## Build the nami command into releases/bin
	@bash ops/scripts/build_nami.sh

document: ## Auto-generate project docs
	@bash ops/scripts/document.sh

clean: ## Prune temp/build artifacts
	@bash ops/scripts/clean.sh
