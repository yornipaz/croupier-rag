SHELL := /bin/bash
API_DIR := apps/api

.PHONY: help install lock dev worker test lint fmt mypy lint-arch quality up down logs ps build clean

help:
	@echo "install     Instala dependencias Python (uv + Python 3.12)"
	@echo "lock        Regenera uv.lock"
	@echo "dev         API en modo recarga (puerto 8000)"
	@echo "worker      Worker Celery"
	@echo "test        pytest"
	@echo "lint        ruff check"
	@echo "fmt         ruff format + fix"
	@echo "mypy        mypy --strict"
	@echo "lint-arch   import-linter"
	@echo "quality     lint + mypy + lint-arch + test"
	@echo "up / down   docker compose"

install:
	cd $(API_DIR) && uv sync --python 3.12

lock:
	cd $(API_DIR) && uv lock

dev:
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd $(API_DIR) && uv run celery -A app.worker worker --loglevel=INFO --concurrency=2

test:
	cd $(API_DIR) && uv run pytest

lint:
	cd $(API_DIR) && uv run ruff check .

fmt:
	cd $(API_DIR) && uv run ruff check --fix . && uv run ruff format .

mypy:
	cd $(API_DIR) && uv run mypy app

lint-arch:
	cd $(API_DIR) && uv run lint-imports

quality: lint mypy lint-arch test

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

ps:
	docker compose ps

build:
	docker compose build

clean:
	rm -rf $(API_DIR)/.venv $(API_DIR)/.mypy_cache $(API_DIR)/.ruff_cache $(API_DIR)/.pytest_cache
