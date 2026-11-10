SHELL := /bin/bash
API_DIR := apps/api

DEMO_DIR := $(CURDIR)/demo
DEMO_PDF ?= $(HOME)/Downloads/Manual de usuario app.pdf
PYTHON ?= python3
NODE ?= node

EVAL_DIR := $(CURDIR)/eval
API_URL ?= http://localhost:8000
LABEL ?= latest
RUNS ?= 3
EVAL_BASELINE := $(EVAL_DIR)/results/baseline-v3.json

.PHONY: help install lock dev worker test lint fmt mypy lint-arch quality up down logs ps build clean \
	demo demo-dry demo-check demo-tts demo-record demo-build demo-deps demo-clean \
	eval eval-baseline eval-compare

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
	@echo "eval        Evalúa el RAG y guarda eval/results/$(LABEL).json"
	@echo "eval-baseline  Evalúa y guarda eval/results/baseline-v3.json"
	@echo "eval-compare   Compara $(LABEL) contra baseline-v3"
	@echo "             Variables: LABEL=latest RUNS=3 API_URL=... DEMO_PDF=..."
	@echo "demo        Genera demo/out/demo.mp4 (TTS + grabación + montaje)"
	@echo "demo-dry    Recorre el flujo sin grabar (valida selectores)"
	@echo "demo-clean  Borra demo/out"
	@echo "demo-deps   Instala Playwright/Chromium y dependencias de la demo"

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

# ---------------------------------------------------------------------------
# Evaluación del RAG
# ---------------------------------------------------------------------------
eval:
	@cd $(API_DIR) && DEMO_PDF="$(DEMO_PDF)" API_URL="$(API_URL)" \
		uv run python "$(EVAL_DIR)/run_eval.py" --label "$(LABEL)" --runs "$(RUNS)" --ensure-doc

eval-baseline:
	@cd $(API_DIR) && DEMO_PDF="$(DEMO_PDF)" API_URL="$(API_URL)" \
		uv run python "$(EVAL_DIR)/run_eval.py" --label baseline-v3 --runs "$(RUNS)" --ensure-doc

eval-compare:
	@cd $(API_DIR) && uv run python "$(EVAL_DIR)/run_eval.py" \
		--label "$(LABEL)" --compare "$(EVAL_BASELINE)"

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

# ---------------------------------------------------------------------------
# Demo en video
# ---------------------------------------------------------------------------
demo:
	@$(MAKE) --no-print-directory demo-check MODE=full
	@$(MAKE) --no-print-directory demo-tts
	@$(MAKE) --no-print-directory demo-record
	@$(MAKE) --no-print-directory demo-build
	@echo ""
	@echo "Demo lista: $(DEMO_DIR)/out/demo.mp4"

demo-dry:
	@$(MAKE) --no-print-directory demo-check MODE=dry
	@DEMO_PDF="$(DEMO_PDF)" DEMO_DIR="$(DEMO_DIR)" \
		$(NODE) --experimental-strip-types --no-warnings "$(DEMO_DIR)/record.ts" --dry-run

demo-check:
	@DEMO_DIR="$(DEMO_DIR)" DEMO_PDF="$(DEMO_PDF)" PYTHON="$(PYTHON)" \
		bash "$(DEMO_DIR)/check.sh" "$(MODE)"

demo-tts:
	@DEMO_PDF="$(DEMO_PDF)" DEMO_DIR="$(DEMO_DIR)" $(PYTHON) "$(DEMO_DIR)/tts.py"

demo-record:
	@DEMO_PDF="$(DEMO_PDF)" DEMO_DIR="$(DEMO_DIR)" \
		$(NODE) --experimental-strip-types --no-warnings "$(DEMO_DIR)/record.ts"

demo-build:
	@DEMO_PDF="$(DEMO_PDF)" DEMO_DIR="$(DEMO_DIR)" bash "$(DEMO_DIR)/build.sh"

demo-deps:
	cd "$(DEMO_DIR)" && npm install
	cd "$(DEMO_DIR)" && npx playwright install chromium
	@$(PYTHON) -m pip install --user edge-tts pyyaml || \
		echo "Si pip está bloqueado por PEP 668, crea un venv e instala edge-tts y pyyaml."

demo-clean:
	rm -rf "$(DEMO_DIR)/out"
