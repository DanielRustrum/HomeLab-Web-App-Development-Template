.PHONY: help dev-start dev-logs dev-stop dev-workspace dev-restart-frontend dev-restart-backend build-start run-start

help:
	@echo "Targets:"
	@echo "  dev-db        Start local Postgres (docker)"
	@echo "  dev-backend   Run backend (host)"
	@echo "  dev-frontend  Run frontend (host)"
	@echo "  dev-docker    Run db + app + ui in docker"
	@echo "  build-image   Build production docker image"
	@echo "  up-prod       Start production compose"
	@echo "  down          Stop all compose services"

dev-start:
	docker compose up --build -d

dev-logs:
	echo "Not Implemented"

dev-workspace:
	docker compose \
		--project-directory . \
		-f docker/compose.dev.yaml \
		-f docker/compose.workspace.yaml \
		up -d --build

dev-stop:
	docker compose down

dev-restart-frontend:
	docker compose restart frontend

dev-restart-backend:
	docker compose restart backend

build-start:
	echo "Not Implemented"

run-start:
	echo "Not Implemented"
