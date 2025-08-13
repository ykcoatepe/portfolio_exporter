VENV=.venv
PIP=$(VENV)/bin/pip
PYTEST=$(VENV)/bin/pytest

.PHONY: setup test lint build ci-home memory-validate memory-view memory-tasks memory-questions memory-context memory-bootstrap memory-digest memory-rotate

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

# ------------------------------------------------------------------
# Assistant memory helpers
# ------------------------------------------------------------------
memory-validate:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory validate

memory-view:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory view --section workflows

memory-tasks:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory list-tasks --status open

memory-questions:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory list-questions

memory-context:
	@$(VENV)/bin/python -m portfolio_exporter.scripts.memory validate >/dev/null && echo "--- preferences" && $(VENV)/bin/python -m portfolio_exporter.scripts.memory view --section preferences && echo "--- workflows" && $(VENV)/bin/python -m portfolio_exporter.scripts.memory view --section workflows && echo "--- tasks" && $(VENV)/bin/python -m portfolio_exporter.scripts.memory list-tasks --status open && echo "--- questions" && $(VENV)/bin/python -m portfolio_exporter.scripts.memory list-questions

memory-bootstrap:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory bootstrap

memory-digest:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory digest

memory-rotate:
	$(VENV)/bin/python -m portfolio_exporter.scripts.memory rotate --cutoff 30d
