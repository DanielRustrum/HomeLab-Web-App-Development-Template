SHELL := /bin/sh

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3

NAMI := $(PYTHON) src/cli/nami.py

.DEFAULT_GOAL := help
.PHONY: help dev workspace build document clean

help: ## Show available targets
	@awk 'BEGIN {FS=":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Spin up the dev container used to test the nami command
	$(NAMI) dev $(DEV_ARGS)

workspace: ## Start the framework workspace container
	$(NAMI) workspace $(WORKSPACE_ARGS)

build: ## Build the nami command into releases/bin
	@bash ops/scripts/build_nami.sh

document: ## Auto-generate project docs
	@bash ops/scripts/document.sh

clean: ## Prune temp/build artifacts
	@bash ops/scripts/clean.sh
