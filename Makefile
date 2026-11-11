.PHONY: help run api test lint typecheck coverage clean-cache clean-cache-dry docker-up docker-down

PY     ?= python
APP    ?= app.py

help: ## Show this help.
	@echo Available targets:
	@echo   make run              - launch Streamlit app
	@echo   make api              - launch FastAPI webhook
	@echo   make test             - run pytest
	@echo   make lint             - run ruff
	@echo   make typecheck        - run mypy
	@echo   make coverage         - run tests with coverage
	@echo   make docker-up        - start PostgreSQL + Redis + API + UI
	@echo   make docker-down      - stop docker compose stack
	@echo   make clean-cache      - remove all __pycache__/ and *.pyc

run: ## Run Streamlit app.
	$(PY) -m streamlit run $(APP)

api: ## Run FastAPI webhook.
	$(PY) -m uvicorn src.api.webhook:app --host 0.0.0.0 --port 8080

test: ## Run tests.
	$(PY) -m pytest -q

lint: ## Run ruff.
	$(PY) -m ruff check .

typecheck: ## Run mypy.
	$(PY) -m mypy src config app.py

coverage: ## Run tests with coverage.
	$(PY) -m pytest --cov=src --cov=config --cov-report=term-missing

clean-cache: ## Remove __pycache__ directories and .pyc/.pyo files.
	$(PY) scripts/clean_cache.py

clean-cache-dry: ## Show what clean-cache would remove.
	$(PY) scripts/clean_cache.py --dry-run

docker-up: ## Start PostgreSQL, Redis, API and UI.
	docker compose up --build -d

docker-down: ## Stop docker compose stack.
	docker compose down
