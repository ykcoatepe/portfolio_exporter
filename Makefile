VENV=.venv
PIP=$(VENV)/bin/pip
PYTEST=$(VENV)/bin/pytest

.PHONY: setup test lint build ci-home

setup:
	python -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

# ------------------------------------------------------------------
# Home-lab CI pipeline (single-thread, minimal RAM)
# ------------------------------------------------------------------
ci-home: lint test build
	@echo "✅  ci-home complete"

lint:
	# Ruff will pick up settings from pyproject.toml
	$(VENV)/bin/ruff check .

test:
	$(PYTEST) -q

build:
	python -m build
