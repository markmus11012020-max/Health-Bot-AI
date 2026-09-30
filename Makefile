.PHONY: help clean-cache clean-cache-dry run test

PY     ?= python
APP    ?= app.py

help: ## Show this help.
	@echo Available targets:
	@echo   make run              - launch Streamlit app
	@echo   make clean-cache      - remove all __pycache__/ and *.pyc under the project
	@echo   make clean-cache-dry  - dry-run (show what would be removed)

run: ## Run Streamlit app.
	$(PY) -m streamlit run $(APP)

clean-cache: ## Remove __pycache__ directories and .pyc/.pyo files.
	$(PY) scripts/clean_cache.py

clean-cache-dry: ## Show what clean-cache would remove.
	$(PY) scripts/clean_cache.py --dry-run
