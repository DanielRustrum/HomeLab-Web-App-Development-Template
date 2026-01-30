SHELL := /bin/sh

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3

NAMI := $(PYTHON) src/cli/nami.py
USER_BIN ?= $(HOME)/.local/bin
NAMI_USER_TARGET := $(USER_BIN)/nami
NAMI_REPO_BIN := $(ROOT)/releases/bin

.DEFAULT_GOAL := help
.PHONY: help dev dev-stop workspace build document clean nami nami-install nami-remove nami-update

ifneq ($(filter nami,$(MAKECMDGOALS)),)
ARGS := $(filter-out nami,$(MAKECMDGOALS))
%:
	@:
endif

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
	@releases/bin/nami.py $(ARGS)

nami-install: ## Install nami into the user's bin directory
	@mkdir -p $(USER_BIN)
	@if [ -f $(NAMI_REPO_BIN)/nami.py ]; then \
		printf '%s\n' '#!/bin/sh' \
			'export PYTHONPATH="$(NAMI_REPO_BIN)$${PYTHONPATH:+:}$${PYTHONPATH}"' \
			'exec /usr/bin/env python3 "$(NAMI_REPO_BIN)/nami.py" "$$@"' \
			> $(NAMI_USER_TARGET); \
		chmod 755 $(NAMI_USER_TARGET); \
	else \
		echo "nami-install: missing $(NAMI_REPO_BIN)/nami.py; run make build"; \
		exit 1; \
	fi
	@echo "nami: installed -> $(NAMI_USER_TARGET)"

nami-update: ## Update nami in the user's bin directory
	@$(MAKE) nami-install

nami-remove: ## Remove nami from the user's bin directory
	@if [ -f $(NAMI_USER_TARGET) ]; then \
		rm -f $(NAMI_USER_TARGET); \
		echo "nami: removed -> $(NAMI_USER_TARGET)"; \
	else \
		echo "nami: not installed -> $(NAMI_USER_TARGET)"; \
	fi

workspace: ## Start the framework workspace for feature development
	@docker compose -f ops/docker/workspace.compose.yaml up -d --build

build: ## Build the nami command into releases/bin
	@NAMI_BUILD_USE_DOCKER=1 bash ops/scripts/build_nami.sh

document: ## Auto-generate project docs
	@bash ops/scripts/document.sh

clean: ## Prune temp/build artifacts
	@bash ops/scripts/clean.sh
