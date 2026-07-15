.PHONY: dev test crawl migrate lint fmt up down

dev:
	pip install -e ".[dev]"
	playwright install chromium

up:
	docker compose up -d

down:
	docker compose down

test:
	pytest -v

lint:
	ruff check src tests

fmt:
	ruff format src tests

# Manually crawl+extract one source end-to-end and print the resulting Launch JSON.
# Usage: make crawl SOURCE=generic_developer_demo (source name from config/sources.yaml)
crawl:
	python scripts/run_source.py --source $(SOURCE)

# TODO(phase-later): wire real Alembic migrations once db/tables.py is implemented.
migrate:
	alembic upgrade head
