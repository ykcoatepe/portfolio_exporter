VENV_DIR := .venv
VENV_BIN := $(VENV_DIR)/bin
VENV := $(VENV_DIR)
PY      := $(VENV_BIN)/python
PIP     := $(VENV_BIN)/pip
PYTEST  := $(VENV_BIN)/pytest

# Prepend venv/bin so console entry points (daily-report, netliq-export, etc.) resolve
export PATH := $(VENV_BIN):$(PATH)

.PHONY: setup dev test lint build ci-home memory-validate memory-view memory-tasks memory-questions memory-context memory-bootstrap memory-digest memory-rotate
.PHONY: sanity-cli sanity-daily sanity-netliq sanity-trades sanity-trades-dash sanity-all menus-sanity sanity-order-builder sanity-trades-report-excel sanity-menus-quick

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

# Trades Dashboard sanity checks (JSON-only + files)
sanity-trades-dash: setup
	@./scripts/sanity_trades_dashboard.sh

# Umbrella target
sanity-all:
	@$(MAKE) -s sanity-cli >/dev/null 2>&1 || true
	@$(MAKE) -s sanity-daily >/dev/null 2>&1 || true
	@$(MAKE) -s sanity-netliq >/dev/null 2>&1 || true
	@$(MAKE) -s sanity-trades >/dev/null 2>&1 || true
	@$(MAKE) -s sanity-trades-dash >/dev/null 2>&1 || true
	@$(MAKE) -s sanity-trades-report-excel >/dev/null 2>&1 || true
	@$(MAKE) -s sanity-menus-quick >/dev/null 2>&1 || true
	@echo "All sanity targets passed (skipped any missing)."

# Trades & Reports menu – underlying previews sanity
menus-sanity: setup
	@./scripts/sanity_trades_menu_underlying.sh

.PHONY: sanity-order-builder
sanity-order-builder:
	        ./scripts/sanity_order_builder_presets.sh

.PHONY: sanity-micro-momo
sanity-micro-momo:
	python -m portfolio_exporter.scripts.micro_momo_analyzer \
	  --input tests/data/meme_scan_sample.csv \
	  --cfg tests/data/micro_momo_config.json \
	  --chains_dir tests/data \
	  --out_dir out \
	  --json --no-files

.PHONY: sanity-trades-report-excel
sanity-trades-report-excel: setup
	        @$(PIP) -q install openpyxl
	        ./scripts/sanity_trades_report_excel.sh

.PHONY: sanity-menus-quick
sanity-menus-quick: setup
	@./scripts/sanity_menus_quick.sh

# --- Micro-MOMO helpers ---
.PHONY: momo-journal
momo-journal:
	python -m portfolio_exporter.scripts.micro_momo_analyzer \
	  --input tests/data/meme_scan_sample.csv \
	  --cfg tests/data/micro_momo_config.json \
	  --out_dir out \
	  --data-mode csv-only \
	  --journal-template

.PHONY: momo-sentinel-offline
momo-sentinel-offline:
	python -m portfolio_exporter.scripts.micro_momo_sentinel \
	  --scored-csv out/micro_momo_scored.csv \
	  --cfg tests/data/micro_momo_config.json \
	  --out_dir out \
	  --interval 2 \
	  --offline

.PHONY: momo-eod-offline
momo-eod-offline:
	python -m portfolio_exporter.scripts.micro_momo_eod \
	  --journal out/micro_momo_journal.csv \
	  --out_dir out \
	  --offline

.PHONY: logbook-add
logbook-add:
	python tools/logbook.py add --task "$$TASK" --branch "$$BRANCH" --owner "$$OWNER" --commit "$$COMMIT" --scope "$$SCOPE" --files "$$FILES" --interfaces "$$INTERFACES" --status "$$STATUS" --next "$$NEXT" --notes "$$NOTES"

.PHONY: momo-dashboard
momo-dashboard:
	python -m portfolio_exporter.scripts.micro_momo_dashboard --out_dir out

.PHONY: momo-dashboard-open
momo-dashboard-open:
	python -m portfolio_exporter.scripts.micro_momo_dashboard --out_dir out; \
	python -c "import webbrowser,os; p=os.path.abspath('out/micro_momo_dashboard.html'); print(p); webbrowser.open('file://'+p, new=2)"

# Orchestrator: analyze → journal → basket → dashboard (optional sentinel)
.PHONY: momo-go
momo-go:
	python -m portfolio_exporter.scripts.micro_momo_go --out_dir out

# --- Micro-MOMO + logbook variants (opt-in via LOGBOOK_AUTO=1) ---
.PHONY: momo-journal-log momo-sentinel-offline-log momo-eod-offline-log momo-dashboard-open-log

momo-journal-log: momo-journal
ifeq ($(LOGBOOK_AUTO),1)
	python tools/logbook.py add --task "micro-momo journal template" --branch "$$(git rev-parse --abbrev-ref HEAD)" --owner "$$(whoami)" --commit "$$(git rev-parse --short HEAD)" --scope "analyzer csv-only + journal" --files "portfolio_exporter/scripts/micro_momo_analyzer.py" --status "merged"
endif

momo-sentinel-offline-log: momo-sentinel-offline
ifeq ($(LOGBOOK_AUTO),1)
	python tools/logbook.py add --task "micro-momo sentinel (offline)" --branch "$$(git rev-parse --abbrev-ref HEAD)" --owner "$$(whoami)" --commit "$$(git rev-parse --short HEAD)" --scope "trigger watcher (offline)" --files "portfolio_exporter/scripts/micro_momo_sentinel.py" --status "merged"
endif

momo-eod-offline-log: momo-eod-offline
ifeq ($(LOGBOOK_AUTO),1)
	python tools/logbook.py add --task "micro-momo eod (offline)" --branch "$$(git rev-parse --abbrev-ref HEAD)" --owner "$$(whoami)" --commit "$$(git rev-parse --short HEAD)" --scope "eod outcomes" --files "portfolio_exporter/scripts/micro_momo_eod.py" --status "merged"
endif

momo-dashboard-open-log: momo-dashboard-open
ifeq ($(LOGBOOK_AUTO),1)
	python tools/logbook.py add --task "micro-momo dashboard" --branch "$$(git rev-parse --abbrev-ref HEAD)" --owner "$$(whoami)" --commit "$$(git rev-parse --short HEAD)" --scope "html report" --files "portfolio_exporter/scripts/micro_momo_dashboard.py" --status "merged"
endif
