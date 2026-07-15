.PHONY: dev test crawl migrate lint fmt up down up-prod down-prod

# ENV_FILE selects which .env the app loads (dev by default). Override per env:
#   make crawl ENV_FILE=.env.staging
ENV_FILE ?= .env.dev
export ENV_FILE

dev:
	pip install -e ".[dev]"
	playwright install chromium

# --- Local dev stack (exposes ports on localhost) ---
up:
	docker compose up -d

down:
	docker compose down

# --- Production stack (base + prod overlay; managed/unexposed services) ---
up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

down-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

test:
	pytest -v

lint:
	ruff check src tests

fmt:
	ruff format src tests

# Manually crawl+extract one source end-to-end and print the resulting Launch JSON.
# The source registry is chosen by ENV (config/sources.<env>.yaml).
# Usage: make crawl SOURCE=generic_developer_demo
crawl:
	python scripts/run_source.py --source $(SOURCE)

# TODO(phase-later): wire real Alembic migrations once db/tables.py is implemented.
migrate:
	alembic upgrade head
