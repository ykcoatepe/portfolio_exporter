VENV_DIR := .venv
VENV_BIN := $(VENV_DIR)/bin
VENV := $(VENV_DIR)
PY      := $(VENV_BIN)/python
PIP     := $(VENV_BIN)/pip
PYTEST  := $(VENV_BIN)/pytest

# Prepend venv/bin so console entry points (daily-report, netliq-export, etc.) resolve
export PATH := $(VENV_BIN):$(PATH)

.PHONY: setup dev test lint build ci-home memory-validate memory-view memory-tasks memory-questions memory-context memory-bootstrap memory-digest memory-rotate
.PHONY: sanity-cli sanity-daily sanity-netliq sanity-trades sanity-all menus-sanity

setup:
	@test -d $(VENV_DIR) || python3 -m venv $(VENV_DIR)
	@$(PIP) -q install -U pip
	@$(PIP) -q install -e .
	@[ -f requirements-dev.txt ] && $(PIP) -q install -r requirements-dev.txt || true
	@echo "Venv ready → $(VENV_BIN)"

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

# Runs the full CLI flags/JSON drift sanity script (uses jq)
sanity-cli: setup
	@PATH="$(VENV_BIN):$$PATH" ./scripts/sanity_cli_helpers.sh

# JSON-only smoke for daily-report (no files)
sanity-daily: setup
	@OUTPUT_DIR=tests/data PE_QUIET=1 daily-report --expiry-window 7 --json --no-files | jq -e '.ok==true' >/dev/null
	@echo "PASS daily-report json-only"

sanity-netliq: setup
	@PE_QUIET=1 netliq-export --source fixture --fixture-csv tests/data/net_liq_fixture.csv --json --no-files | jq -e '.ok==true' >/dev/null
	@echo "PASS netliq-export json-only"

sanity-trades: setup
	@PE_QUIET=1 trades-report --executions-csv tests/data/executions_fixture.csv --json --no-files | jq -e '.ok==true' >/dev/null
	@echo "PASS trades-report json-only"

# Umbrella target
sanity-all: sanity-cli sanity-daily sanity-netliq sanity-trades
	@echo "All sanity targets passed."

# Trades & Reports menu – underlying previews sanity
menus-sanity: setup
	@./scripts/sanity_trades_menu_underlying.sh
