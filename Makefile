.PHONY: dev test crawl migrate lint fmt up down up-prod down-prod \
	collect collect-dry dedup docker-collect docker-collect-dry docker-dedup \
	docker-collect-all

# ENV_FILE selects which .env the app loads for host-side runs. The same `.env`
# Docker Compose reads, so both paths see one set of values. Override per env:
#   make crawl ENV_FILE=.env.staging
ENV_FILE ?= .env
export ENV_FILE

dev:
	pip install -e ".[dev]"
	playwright install chromium

# --- Local dev stack (exposes ports on localhost) ---
# API on :8000 (Swagger at /docs), Postgres and Redis alongside it.
# Override a port when something already holds it, e.g.
#   make up API_HOST_PORT=8080 POSTGRES_HOST_PORT=55432
up:
	docker compose up -d --build

# Apply migrations inside the stack, against the containerised database.
migrate-docker:
	docker compose run --rm api alembic upgrade head

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

# Collect one source into the catalogue. SOURCE=nawy|property_finder
# Host-side; needs a local venv with chromium installed for nawy. On a server,
# use the containerised targets below instead.
collect:
	python scripts/collect.py --source $(SOURCE)

# Fetch and map for real, report what would be written, write nothing.
collect-dry:
	python scripts/collect.py --source $(SOURCE) --dry-run

# Link the same developer/project/area across sources.
dedup:
	python scripts/dedup.py

# Containerised collection, for hosts with no venv. Runs in the worker image,
# which carries chromium — nawy's new-launches page is JS-rendered and the api
# image deliberately has no browser.
docker-collect:
	docker compose run --rm collector python scripts/collect.py --source $(SOURCE)

docker-collect-dry:
	docker compose run --rm collector python scripts/collect.py --source $(SOURCE) --dry-run

docker-dedup:
	docker compose run --rm collector python scripts/dedup.py

# Both sources, then the dedup pass they require to be meaningful.
docker-collect-all:
	$(MAKE) docker-collect SOURCE=property_finder
	$(MAKE) docker-collect SOURCE=nawy
	$(MAKE) docker-dedup
