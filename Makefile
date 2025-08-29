VENV=.venv
PIP=$(VENV)/bin/pip
PYTEST=$(VENV)/bin/pytest

.PHONY: setup test lint build ci-home memory-validate memory-view memory-tasks memory-questions memory-context memory-bootstrap memory-digest memory-rotate
.PHONY: sanity-cli sanity-daily sanity-netliq sanity-trades sanity-all

setup:
        python -m venv $(VENV)
        $(PIP) install -r requirements.txt
        $(PIP) install -r requirements-dev.txt

dev:
        @mkdir -p .outputs
        @echo "OUTPUT_DIR=.outputs" > .env
        @echo "PE_QUIET=1" >> .env
        ruff check .
        pytest -q tests/test_json_contracts.py tests/test_doctor_preflight.py

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

# ------------------------------------------------------------------
# Sanity helpers
# ------------------------------------------------------------------

sanity-cli:
	./scripts/sanity_cli_helpers.sh

sanity-daily:
	OUTPUT_DIR=tests/data PE_QUIET=1 daily-report --expiry-window 7 --json --no-files | jq -e '.ok==true' >/dev/null

sanity-netliq:
	PE_QUIET=1 netliq-export --source fixture --fixture-csv tests/data/net_liq_fixture.csv --json --no-files | jq -e '.ok==true' >/dev/null

sanity-trades:
	PE_QUIET=1 trades-report --executions-csv tests/data/executions_fixture.csv --json --no-files | jq -e '.ok==true' >/dev/null

sanity-all: sanity-cli sanity-daily sanity-netliq sanity-trades
	@echo "All sanity targets passed."
