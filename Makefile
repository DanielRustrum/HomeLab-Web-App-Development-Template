.PHONY: help dev-start dev-logs dev-stop dev-workspace dev-restart-frontend dev-restart-backend build-start run-start

help:
	@echo "Targets:"
	@echo "  dev-start       		Start starts services for development"
	@echo "  dev-logs        		Starts Logging for Services"
	@echo "  dev-workspace   		Starts a docker container used for easy development"
	@echo "  dev-stop        		Stops all services"
	@echo "  clean        			Wipes all data and logs"
	@echo "  dev-restart-frontend		restarts frontent services"
	@echo "  dev-restart-backend		restarts backend services"
	@echo "  build-start      		build project to docker image"
	@echo "  run-start        		runs built project"


dev-start:
	docker compose \
		--project-directory . \
		-f ops/docker/dev.compose.yaml \
		up -d --build

dev-logs:
	echo "Not Implemented"

dev-workspace:
	docker compose \
		--project-directory . \
		-f ops/docker/workspace.compose.yaml \
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
