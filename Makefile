# Veritas in Docker: the database, the API and the web app (see docker-compose.yml).
# `make help` lists the targets. DEPLOY.md explains the server around it.

COMPOSE ?= docker compose

# WEB_PORT and POSTGRES_PASSWORD live in .env, which docker compose reads too.
-include .env
WEB_PORT ?= 8110

.DEFAULT_GOAL := help
.PHONY: help env up down build restart ps logs logs-api health seed migrate psql

help: ## List the targets
	@grep -hE '^[a-z-]+:.*## ' Makefile | awk 'BEGIN {FS = ":.*## "} {printf "  make %-10s %s\n", $$1, $$2}'

env: ## First time only: make .env and deploy/veritas.env from the examples, with fresh secrets
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 24)/" .env; \
		echo "made .env"; \
	else echo ".env exists, left as it is"; fi
	@if [ ! -f deploy/veritas.env ]; then \
		cp deploy/veritas.env.example deploy/veritas.env; \
		sed -i "s/^VERITAS_SECRET_KEY=.*/VERITAS_SECRET_KEY=$$(openssl rand -hex 32)/" deploy/veritas.env; \
		echo "made deploy/veritas.env: set VERITAS_WEB_APP_URL and, for the assistant, VERITAS_OPENAI_API_KEY"; \
	else echo "deploy/veritas.env exists, left as it is"; fi

up: ## Build and start everything, on 127.0.0.1:WEB_PORT (8110)
	$(COMPOSE) up -d --build

down: ## Stop and remove the containers (the data volumes stay)
	$(COMPOSE) down

build: ## Build the images without starting them
	$(COMPOSE) build

restart: ## Restart the API and the web app
	$(COMPOSE) restart api web

ps: ## Show the containers and their health
	$(COMPOSE) ps

logs: ## Follow every container's log
	$(COMPOSE) logs -f --tail=100

logs-api: ## Follow the API's log
	$(COMPOSE) logs -f --tail=100 api

health: ## Check the site, the API and the database through the web app
	@curl -fsS -o /dev/null -w "web    %{http_code}\n" http://127.0.0.1:$(WEB_PORT)/
	@curl -fsS http://127.0.0.1:$(WEB_PORT)/health/ready && echo

seed: ## Reset the judges' demo account (admin@gmail.com / admin1234)
	$(COMPOSE) exec api python scripts/seed_demo.py

migrate: ## Run the database migrations (the API also runs them when it starts)
	$(COMPOSE) exec api alembic upgrade head

psql: ## Open a database shell
	$(COMPOSE) exec db psql -U veritas veritas
