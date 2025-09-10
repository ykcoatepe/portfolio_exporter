# Portfolio Exporter

This repository contains a collection of small helper scripts used to export quotes
and technical data for a personal trading workflow. The scripts rely mostly on
[yfinance](https://github.com/ranaroussi/yfinance) and optionally on
[ib_insync](https://github.com/erdewit/ib_insync) for Interactive Brokers (IBKR)
connectivity. A high level overview of the design and how the tools use IBKR and
yfinance can be found in [docs/PDR.md](docs/PDR.md).

## Script Overview

| Script | Description |
| ------ | ----------- |
| `market_analyzer.py` | A unified tool for market analysis, including pre-market reports, live data feeds, technical signals, portfolio greeks, and option chain snapshots. Use `--mode pre-market`, `--mode live`, `--mode tech-signals`, `--greeks`, or `--option-chain <SYMBOL>`. |
| `update_tickers.py` | Writes the current IBKR stock positions to `tickers_live.txt` so other scripts always use a fresh portfolio. |
| `net_liq_history_export.py` | Creates an end-of-day Net-Liq history CSV from TWS logs or Client Portal data and can optionally plot an equity curve. Supports `--excel` and `--pdf` outputs. |
| `trades_report.py` | Exports executions and open orders from IBKR to CSV for a chosen date range. Add `--excel` or `--pdf` for formatted reports. |
| `daily_report.py` | Render a one-page HTML/PDF snapshot from the latest portfolio greeks CSVs. |

## Strike Enrichment in Combos

The `portfolio_greeks` workflow generates an additional combos CSV alongside the per‑position output. Strike details for option combos are consistently enriched across all combo sources.

- Guarantee: `portfolio_greeks_combos.csv` always includes the following columns for every combo:
  - `strikes`, `call_strikes`, `put_strikes`, `call_count`, `put_count`, `has_stock_leg`
- Sources: Works the same for `--combos-source auto`, `db`, `live`, and `engine`.
- Legs field: `legs` is always a JSON list in the CSV, and `legs_n` reflects its length.
- Enrichment order: prefers positions (conId → right/strike/secType), then falls back to DB legs when available.
- Debug mode: set `PE_DEBUG_COMBOS=1` to also write `combos_enriched_debug.csv` with a `__strike_source` per row (`pos` or `db`).
- CLI flag: `--debug-combos` is equivalent to setting `PE_DEBUG_COMBOS=1` and forces the same debug artifacts to be written.
- Edge case: if neither positions nor DB legs contain strike/right data, strike columns remain empty for that combo.

Trades pipeline
- `trades_report.py` now also emits `trades_combos.csv` with the same fields and enrichment behavior as portfolio combos. Use `--debug-combos` (or `PE_DEBUG_COMBOS=1`) to force debug artifacts (`combos_enriched_debug.csv`). Existing outputs remain unchanged.

### Golden Sample Test

Run the golden test to validate strike enrichment end-to-end with a deterministic offline sample:

```bash
pytest -q tests/test_greeks_combos_golden.py
```

This test runs `portfolio_greeks` with `--positions-csv tests/data/offline_positions_combo_sample.csv` and asserts that the combos CSV contains the required columns, has non-empty call/put strikes for at least one row each, and that `legs` parses as a JSON list with `legs_n` matching its length. If present, the debug CSV is also checked for `__strike_source` values in `{pos, db}`.

### CP_REFRESH_TOKEN
`net_liq_history_export.py` looks for the environment variable `CP_REFRESH_TOKEN` when pulling data from the Client Portal API. Set it before running the script:

```bash
export CP_REFRESH_TOKEN=<your refresh token>
```

If the token is not present, the script will attempt to read `dailyNetLiq.csv` from Trader Workstation instead.

## Installation

```bash
make setup
```

Quick start (recommended flow)
- make lint: run Ruff with project rules
- make test: run pytest locally
- make build: validate packaging
- Quiet CI runs: export `PE_QUIET=1` to suppress Rich output

Environment and configuration
- `OUTPUT_DIR`: default directory for generated files (honored via settings)
- `PE_OUTPUT_DIR`: legacy override used by some scripts (e.g., Net‑Liq CLI)
- `PE_QUIET`: when set and non‑zero, suppresses pretty console output
- `CP_REFRESH_TOKEN`: Client Portal refresh token for PortfolioAnalyst API
- `TWS_EXPORT_DIR`: path to Trader Workstation exports (for `dailyNetLiq.csv`)

See `.env.example` for a starter file; any values there are read by the app.

## Common CLI flags

Most scripts share a small set of flags for consistent ergonomics. The
helpers `portfolio_exporter.core.cli.add_common_output_args` and
`portfolio_exporter.core.cli.add_common_debug_args` register these options so
every CLI stays in sync; a drift test enforces their presence.

| Flag | Description |
| ---- | ----------- |
| `--output-dir PATH` | Directory for generated files (overrides `OUTPUT_DIR` env). |
| `--json` | Emit a compact JSON summary to STDOUT. |
| `--no-files` | Skip writing any output files. |
| `--no-pretty` | Disable rich/pretty console rendering. |
| `--preflight` | Validate inputs only (schema/header checks; no files). |
| `--debug-timings` | Capture per-stage timings (adds `timings.csv` when files are written). |

Environment variables:

| Variable | Purpose |
| -------- | ------- |
| `OUTPUT_DIR` | Default directory for exports. |
| `PE_QUIET` | When set to `1`, suppresses all pretty console output. |

JSON summaries returned by the scripts consistently use `sections` or `rows`
and include an `outputs` mapping with file paths (empty strings when skipped).

## Console entry points

```bash
daily-report --json --no-files
netliq-export --json --no-files --source fixture --fixture-csv tests/data/net_liq_fixture.csv
quick-chain --chain-csv tests/data/quick_chain_fixture.csv --json
trades-report --executions-csv tests/data/executions_fixture.csv --json
portfolio-greeks --positions-csv tests/data/positions_sample.csv --json
doctor --json --no-files
daily-report --json --no-files | validate-json
```

## Task recipes

Copy-paste snippets for common day-to-day tasks.

### Pre-market: quick-chain → daily-report

```bash
quick-chain --chain-csv tests/data/quick_chain_fixture.csv --json --no-files
daily-report --json --no-files
daily-report --output-dir pre && ls pre/daily_report.html pre/daily_report.pdf
```

### Trades review: trades-report → trades-dashboard

```bash
trades-report --executions-csv tests/data/executions_fixture.csv --symbol SPY --json --no-files
trades-dashboard --executions-csv tests/data/executions_fixture.csv --output-dir trades && ls trades/trades_dashboard.html
```

### Roll preview: roll-manager --dry-run

```bash
roll-manager --dry-run --json --no-files
roll-manager --dry-run --output-dir rolls && ls rolls/roll_manager_preview.html rolls/roll_manager_ticket.json
```

### Maintenance: combo-db-maint

```bash
combo-db-maint --json --no-files
combo-db-maint --fix --output-dir combo && ls combo
```

## Order Builder presets

`order_builder` can scaffold common option strategies without manual strike
entry. Provide a preset, symbol, expiry and quantity, then review the produced
ticket and risk summary:

```bash
python -m portfolio_exporter.scripts.order_builder \
  --preset bull_put --symbol XYZ --expiry 2025-01-17 --qty 1 --width 5 \
  --json --no-files
```

The JSON response shape is:

```json
{
  "ok": true,
  "preset": "bull_put",
  "ticket": {"underlying": "XYZ", ...},
  "risk_summary": {"max_gain": 0.0, "max_loss": 5.0, "breakevens": [95.0]},
  "outputs": [],
  "warnings": [],
  "meta": {"schema_id": "order_builder", "schema_version": "1"}
}
```

Use other presets like `bear_call`, `iron_condor`, `iron_fly` or `calendar`.

### Auto strike selection (preview)

You can preview live-data candidates for presets using `--auto`. The engine
selects strikes by target delta with liquidity and earnings filters, and emits
JSON so you can choose a candidate or feed it to other tools.

```bash
# Credit vertical example with liquidity and earnings guardrails
python -m portfolio_exporter.scripts.order_builder \
  --preset bear_call --symbol AAPL --expiry nov \
  --auto --profile balanced --earnings-window 7 \
  --min-oi 200 --min-volume 50 --max-spread-pct 0.02 \
  --json --no-files

# Debit vertical example by DTE
python -m portfolio_exporter.scripts.order_builder \
  --preset bull_call --symbol AAPL --dte 30 \
  --auto --profile conservative \
  --json --no-files

# Iron condor preview
python -m portfolio_exporter.scripts.order_builder \
  --preset iron_condor --symbol AAPL --expiry nov \
  --auto --json --no-files
```

Quick reference
- Presets: `bull_put`, `bear_call`, `bull_call`, `bear_put`, `iron_condor`, `iron_fly`, `calendar`.
- Inputs: `--symbol`, `--expiry`, `--qty`.
- Width controls: `--width` (verticals, default 5), `--wings` (iron condor/fly, default 5).
- Console entry (after install): `order-builder --preset bull_put --symbol AAPL --expiry 2025-12-19 --qty 1 --width 5 --json --no-files`.

## Menus

The interactive menus now include quick previews that avoid writing files:

```
Trades & Reports › Preview Trades Clusters (JSON-only)
Trades & Reports › Preview Roll Manager (dry-run)
Trades & Reports › Preflight Daily Report
Trades & Reports › Preflight Roll Manager
Trades & Reports › Generate Daily Report (explicit format)

Trades & Reports › Preview Daily Report (JSON-only)
Positions: 12
Combos: 3
Totals: 1
Expiry radar: {...}

Trades & Reports › Preview Roll Manager (dry-run)
Candidates: 4
TSLA Δ+1.20 +0.50
AAPL Δ-0.80 -0.30
```

### Trades Menu — Quick Actions

Quick shortcuts in the Trades & Reports menu:

- **Open last report** – launch the most recent `daily_report.html` or `trades_dashboard.html`.
- **Save filtered trades CSV** – pick filters and write a CSV, for example:

  ```
  Trades & Reports › Save filtered trades CSV… (choose filters)
  Symbols: AAPL,MSFT
  Effect: Close
  Top N: 10
  ```

- **Copy trades JSON summary** – copy a filtered summary to the clipboard (uses `pyperclip` if installed; otherwise prints the JSON).

- **Executions → intent + P&L** – after “Executions / open orders”, the menu prints:
  - Intent totals: Open/Close/Roll/Mixed/Unknown and dominant effect by underlying.
  - Top Combos by realized P&L (clustered fills in the selected window) with an Effect column.
  - If Unknown is high or a prior-snapshot warning appears, the menu prompts for a prior positions CSV and persists it for next runs.

- **Combos MTM P&L (JSON-only)** – press `m` to compute mark‑to‑market P&L per detected combo using mid quotes per leg. The JSON is copied to clipboard in interactive mode.
  - Includes `quoted_ratio` (e.g., `3/4`) and caches quotes for 30s with a small per-run time budget.

- **Format toggle** – press `t` to cycle the default output format (`csv → excel → pdf`) used by actions in this menu.

- **Open last ticket** – press `k` to print the last saved `order_ticket*.json` path and copy its JSON to the clipboard.

Preference for prior positions snapshot:

The menu auto-uses a default prior positions CSV when present under `.codex/memory.json`:

```json
{
  "preferences": {
    "trades_prior_positions": "/absolute/path/to/portfolio_greeks_positions_YYYYMMDD.csv"
  }
}
```
You can set this interactively when prompted after Executions, or edit the file directly.

Notes
- Executions intent mapping auto-picks a strictly prior snapshot by earliest fill time and uses the saved path as an override when present.
- Combos CSV/Excel now include both `pnl` (gross) and `pnl_net` (commission-aware) when data is available.

Typical fixes:

```bash
export OUTPUT_DIR=~/pe && mkdir -p "$OUTPUT_DIR"
export CP_REFRESH_TOKEN=<token>
mkdir -p ~/Jts/export && export TWS_EXPORT_DIR=~/Jts/export
pip install pandera
```

## Combo DB maintenance

`combo-db-maint` audits and repairs the combos database.

```bash
# check-only (default): analyse DB and report issues
combo-db-maint --json --no-files

# fix: apply repairs and write before/after snapshots
combo-db-maint --fix --output-dir .tmp_combo --json
```

Flags are unified across scripts: `--json`, `--no-files`, `--output-dir`,
`--no-pretty`, `--debug-timings`. When files are written a RunLog manifest is
emitted; adding `--debug-timings` also writes `timings.csv` and includes
per-stage timings in the JSON summary.

## Troubleshooting & Env

- **command not found** → `pip install -e .` ; `PATH=.venv/bin:$PATH`
- **missing ruff/pytest** → `make setup` (or `pip install -r requirements-dev.txt`)
- **reportlab missing** → PDF step skipped
- **pyperclip missing** → clipboard copy skipped

## Repo Memory (Agent-Shared)

Lightweight, auditable repo “memory” helps Cloud/CLI agents keep context across sessions.

- Location: `.codex/memory.json` (override with `--path`). No secrets; set `MEMORY_READONLY=1` to block writes.
- Safe writes: lockfile + atomic replace (fsync → os.replace), sorted JSON.
- Schema v1: required keys → preferences, workflows, tasks, questions, decisions, changelog.
- Machine output: most read/list commands support `--json`.

Common commands
- Bootstrap: `python -m portfolio_exporter.scripts.memory bootstrap`
- Validate: `make memory-validate`
- Digest: `make memory-digest` (or add `--json`)
- Rotate old changelog: `make memory-rotate` (default `--cutoff 30d`)

Task lifecycle
- Add: `memory add-task "Refactor exporter" --labels infra --priority 2`
- Update: `memory update-task 1 --status in_progress --details "split writer"`
- Close: `memory close-task 1 --reason "merged"`

Tip: add a shell alias for convenience: `alias memory='python -m portfolio_exporter.scripts.memory'`.

## Upgrading dependencies

This project uses the [pip-tools](https://github.com/jazzband/pip-tools) workflow to maintain fully pinned requirements.

1. Edit dependencies in `requirements.in` or dev dependencies in `requirements-dev.in` (e.g. adjust version specifiers).
2. Re‑compile the pinned files:

   ```bash
   pip install pip-tools
   pip-compile requirements.in requirements-dev.in
   ```

3. Re‑install dependencies and re‑run tests (or use `make setup && make test`):

   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   pytest
   ```

## Testing

After installing dev dependencies, run the test suite to verify your changes:

```bash
make test
# or, directly:
pytest
```

The scripts require Python 3.11+ and the packages listed in `requirements.txt`.
`pandas_datareader` is needed for downloading FRED data in `live_feed.py`, and `requests` is required by `net_liq_history_export.py` for accessing the IBKR Client Portal API. `xlsxwriter` enables Excel exports and `reportlab` enables PDF output. `matplotlib` is optional and only needed when using the `--plot` flag with `net_liq_history_export.py`.

## Quick Smoke

Run these from the repo root to sanity check lint, focused tests, and the three CLIs in both JSON-only and file-write modes. Where possible, smokes use offline fixtures to avoid network.

```bash
# 0) Clean tmp
rm -rf .tmp_* .outputs || true

# 1) Lint + targeted tests
ruff check portfolio_exporter/core/cli.py portfolio_exporter/core/json.py \
  portfolio_exporter/scripts/daily_report.py portfolio_exporter/scripts/net_liq_history_export.py \
  portfolio_exporter/scripts/quick_chain.py \
  tests/test_daily_report.py tests/test_net_liq_cli.py tests/test_quick_chain_cli.py

pytest -q tests/test_daily_report.py tests/test_net_liq_cli.py tests/test_quick_chain_cli.py

# 2) CLI sanity: expected behavior & minimal asserts

# daily_report — JSON-only → no files, outputs == []
PYTHONPATH=. PE_QUIET=1 OUTPUT_DIR=tests/data \
python -m portfolio_exporter.scripts.daily_report --expiry-window 7 --symbol AAPL --json --no-files \
| python - <<'PY'
import sys, json; d = json.load(sys.stdin)
assert d["ok"] and "sections" in d and d["outputs"] == [], d
print("PASS: daily_report JSON-only")
PY

# daily_report — Defaults with output dir (no explicit formats) → HTML+PDF written
PYTHONPATH=. OUTPUT_DIR=tests/data \
python -m portfolio_exporter.scripts.daily_report --expiry-window 10 --output-dir .tmp_daily >/dev/null
test -f .tmp_daily/daily_report.html && echo "PASS: daily_report HTML" || (echo "FAIL: html"; exit 1)
test -f .tmp_daily/daily_report.pdf  && echo "PASS: daily_report PDF"  || (echo "FAIL: pdf";  exit 1)

# daily_report — JSON + output dir → JSON printed AND files written (expected: HTML+PDF)
PYTHONPATH=. OUTPUT_DIR=tests/data \
python -m portfolio_exporter.scripts.daily_report --expiry-window 5 --output-dir .tmp_daily2 --json \
| python - <<'PY'
import sys, json; d = json.load(sys.stdin)
assert d["ok"] and "sections" in d, d
print("PASS: daily_report JSON printed")
PY
test -f .tmp_daily2/daily_report.html && test -f .tmp_daily2/daily_report.pdf && echo "PASS: daily_report files with --json"

# net_liq_history_export — JSON-only (fixture) → no files
PYTHONPATH=. PE_QUIET=1 \
python -m portfolio_exporter.scripts.net_liq_history_export --source fixture --fixture-csv tests/data/net_liq_fixture.csv --json \
| python - <<'PY'
import sys, json; d = json.load(sys.stdin)
assert d["ok"] and "rows" in d and d["outputs"] == [], d
print("PASS: net_liq JSON-only")
PY

# net_liq_history_export — With output dir (no explicit formats) → CSV by default
PYTHONPATH=. \
python -m portfolio_exporter.scripts.net_liq_history_export --source fixture --fixture-csv tests/data/net_liq_fixture.csv --output-dir .tmp_netliq >/dev/null
ls .tmp_netliq | grep -E '^net_liq_history_export\\.csv$' >/dev/null && echo "PASS: net_liq CSV default"

# quick_chain — JSON-only with fixture → no files
PYTHONPATH=. PE_QUIET=1 \
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --tenor all --target-delta 0.3 --json --no-files \
| python - <<'PY'
import sys, json; d = json.load(sys.stdin)
assert d["ok"] and "sections" in d and d["outputs"] == [], d
print("PASS: quick_chain JSON-only")
PY

# quick_chain — With output dir (no explicit formats) → CSV by default
PYTHONPATH=. \
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --tenor all --target-delta 0.3 --output-dir .tmp_qc >/dev/null
ls .tmp_qc | grep -E '^quick_chain\\.csv$' >/dev/null && echo "PASS: quick_chain CSV default"

# Edge cases (flags & env precedence)

# --no-files always wins
PYTHONPATH=. \
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --tenor all --target-delta 0.3 \
  --output-dir .tmp_qc_nofiles --no-files >/dev/null || true
test ! -d .tmp_qc_nofiles && echo "PASS: no-files prevents writes"

# Explicit format flags override defaults (daily_report: only HTML)
PYTHONPATH=. OUTPUT_DIR=tests/data \
python -m portfolio_exporter.scripts.daily_report --output-dir .tmp_daily_html --html >/dev/null
test -f .tmp_daily_html/daily_report.html && test ! -f .tmp_daily_html/daily_report.pdf \
  && echo "PASS: explicit format respected"

# PE_OUTPUT_DIR fallback is honored in CI by setting PE_TEST_MODE=1
rm -rf .tmp_legacy && mkdir -p .tmp_legacy
PYTHONPATH=. PE_TEST_MODE=1 PE_OUTPUT_DIR=.tmp_legacy \
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --tenor all --target-delta 0.3 --csv >/dev/null
ls .tmp_legacy | grep -E '^quick_chain\\.csv$' >/dev/null && echo "PASS: PE_OUTPUT_DIR fallback"

# Help screens (flags visible)
python -m portfolio_exporter.scripts.daily_report -h             | grep -E -- '--json|--no-files|--no-pretty|--output-dir'
python -m portfolio_exporter.scripts.net_liq_history_export -h   | grep -E -- '--json|--no-files|--no-pretty|--output-dir'
python -m portfolio_exporter.scripts.quick_chain -h              | grep -E -- '--json|--no-files|--no-pretty|--output-dir'
echo "PASS: help shows common flags"
```

### Sanity — trades_report --excel

Quick confidence for the Excel path of `trades_report`:

```bash
# Installs openpyxl into the local venv and runs the sanity script
make sanity-trades-report-excel

# Or run all sanity targets, including the Excel check
make sanity-all
```

CI: a minimal workflow is provided at `.github/workflows/sanity-excel.yml` that installs `openpyxl` and runs the same script on PRs.

JSON outputs
- outputs: an array of file paths when files are written; an empty array (`[]`) in JSON-only runs.
- manifest: when files are written, a `<script>_manifest.json` is also produced and its path is appended to `outputs`.
- timings: when `--debug-timings` is used, `meta.timings` includes per-stage durations; a `timings.csv` is written alongside other artifacts when files are written.
- meta.script: if present, matches the script name; not required for smokes.
- sections/rows: present depending on the script (`sections` for reports, `rows` for time series).

CI note
- In CI or restricted sandboxes, set `PE_TEST_MODE=1` to make `PE_OUTPUT_DIR` take precedence over `OUTPUT_DIR` for write paths. This prevents accidental writes to system locations.

## Usage Examples

```bash
# Fetch recent historical prices
python historic_prices.py

# Grab a live quote snapshot
python live_feed.py
# Refresh tickers_live.txt from IBKR
python update_tickers.py

# Calculate technical indicators using IBKR data
python tech_signals_ibkr.py

# Interactively choose symbols and expiries
python option_chain_snapshot.py

# Option-chain snapshot for specific symbols and expiries
python option_chain_snapshot.py --symbol-expiries 'TSLA:20250620,20250703;AAPL:20250620'
# Export today's executions and open orders
python trades_report.py --today

### Roll Manager CLI

```bash
python -m portfolio_exporter.scripts.roll_manager --days 28 --tenor monthly --no-pretty
python -m portfolio_exporter.scripts.roll_manager --dry-run --json --no-files
python -m portfolio_exporter.scripts.roll_manager --limit-per-underlying 1 --output-dir rolls
```

JSON-only preview:

```bash
python -m portfolio_exporter.scripts.roll_manager --dry-run --json --no-files
```

Flags are unified across CLIs: `--json`, `--no-files`, `--output-dir`, `--no-pretty` and `--debug-timings`.
When writing files, a RunLog manifest is saved; `--debug-timings` adds `timings.csv` and includes
timings data in the JSON summary.

### Trades Report

Intent tagging notes
- Prefers a positions snapshot strictly older than the earliest execution in the selected window. This improves Open/Close/Roll detection.
- Override the snapshot with `--prior-positions-csv /path/to/portfolio_greeks_positions.csv` when needed (e.g., multi‑day windows).
- Use `--debug-intent` to emit `trades_intent_debug.csv` showing per‑leg `match_mode` (id, attr_exact, attr_tol, no_match) and `prior_qty` used for decisions.
- If no strictly‑prior snapshot is found, the latest snapshot is used and a warning is emitted; accuracy may be lower in that case.

Note: Intent tagging prefers a positions snapshot strictly older than the earliest execution in your selected window to decide whether combos are Open, Close, Mixed, or Roll. Use `--debug-intent` to emit `trades_intent_debug.csv` with per‑leg matching details. If no prior snapshot exists, tagging falls back to the latest positions and accuracy may decrease.

### Trades report filters & Excel

```bash
# Last week only, summary as text
python -m portfolio_exporter.scripts.trades_report --since 2025-08-01 --until 2025-08-08 --no-pretty

# Single day in JSON (no files written)
python -m portfolio_exporter.scripts.trades_report --since 2025-08-09 --until 2025-08-09 --summary-only --json

# Offline CSV + filter + debug combos
python -m portfolio_exporter.scripts.trades_report --executions-csv tests/data/offline_executions_combo_sample.csv --since 2025-08-01 --until 2025-08-31 --debug-combos

# Write an Excel workbook alongside CSVs
python -m portfolio_exporter.scripts.trades_report --executions-csv tests/data/executions_fixture.csv --output-dir ./reports --excel
```

### Trades clustering

Group executions into clusters and compute synthetic P&L:

```bash
python -m portfolio_exporter.scripts.trades_report --executions-csv tests/data/executions_fixture.csv --json
```

JSON summary fields: `n_total`, `n_kept`, `u_count`, `underlyings`, `net_credit_debit`, `combos_total`, `combos_by_structure`, and `outputs` (paths when written).
```

Open interest values are sourced from Yahoo Finance rather than the IBKR feed.

### Trades Dashboard

Create a consolidated view from the latest trades report:

```bash
python -m portfolio_exporter.scripts.trades_dashboard --json --no-files
trades-dashboard --output-dir ./reports
```

### Daily Report

Create a one-page portfolio snapshot from the latest greeks exports:

```bash
python -m portfolio_exporter.scripts.daily_report
python -m portfolio_exporter.scripts.daily_report --json
python -m portfolio_exporter.scripts.daily_report --output-dir ./reports --html --pdf
python -m portfolio_exporter.scripts.daily_report --json --no-files   # JSON only, no files written
python -m portfolio_exporter.scripts.daily_report --expiry-window 10
python -m portfolio_exporter.scripts.daily_report --symbol AAPL
python -m portfolio_exporter.scripts.daily_report --symbol AAPL --expiry-window 7 --json --no-files --quiet
```

The script reads the newest `portfolio_greeks_positions*.csv`,
`portfolio_greeks_totals*.csv`, and `portfolio_greeks_combos*.csv` files.
`--since` and `--until` filter positions by expiry when that column exists.
`--expiry-window N` adds an "Expiry Radar" section for contracts expiring in the
next `N` days (defaults to 10 when the flag is provided without a value).
`--symbol TICKER` restricts report inputs to the given underlying (case-insensitive).

Note: `--preflight` validates CSV headers (Pandera optional; warns if missing).
Timings: add `--debug-timings` to capture per-stage durations; writes `timings.csv` when files are written and includes `meta.timings` in JSON.

#### New analytics

Daily Report now includes:

- `delta_buckets`: counts by Δ bands (-1,-0.6], (-0.6,-0.3], (-0.3,0], (0,0.3], (0.3,0.6], (0.6,1])
- `theta_decay_5d`: projected total θ over the next 5 sessions (sum of per-position θ × 5)

Available in JSON under `sections.delta_buckets` and `sections.theta_decay_5d`, and rendered in the HTML/PDF cards.

When `--json` is used, the output includes an `expiry_radar` block:

```json
{
  "expiry_radar": {
    "window_days": 7,
    "basis": "combos",
    "rows": [
      {
        "date": "YYYY-MM-DD",
        "count": 2,
        "delta_total": 0.5,
        "theta_total": -1.2,
        "by_structure": {"vertical": 1, "iron condor": 1}
      }
    ]
  },
  "filters": {"symbol": "AAPL"}
}
```

`basis` falls back to `"positions"` if combo data is unavailable. Roll-off greek
totals appear only when the relevant columns exist.

Tips
- `--no-files`: Suppress writing HTML/PDF; useful in CI/sandboxes with `--json`.
- `--output-dir`: Override the destination directory for artifacts.
- Env override: set `OUTPUT_DIR=./.outputs` in a `.env` file to change the default output path (picked up by settings).
- Quiet mode: set `PE_QUIET=1` to suppress pretty console output (same effect as adding `--no-pretty` in menus or CLI where available).

### Portfolio Greeks (CLI)

Note: `--preflight` validates CSV headers (Pandera optional; warns if missing).
Timings: add `--debug-timings` to capture per-stage durations; writes `timings.csv` when files are written and includes `meta.timings` in JSON.

### Net-Liq chart (CLI)

JSON only:

```bash
PYTHONPATH=. python -m portfolio_exporter.scripts.net_liq_history_export \
  --source fixture --fixture-csv tests/data/net_liq_fixture.csv --json --quiet
```

Multi-format to custom dir:

```bash
OUT=.tmp_nlh PYTHONPATH=. python -m portfolio_exporter.scripts.net_liq_history_export \
  --source fixture --fixture-csv tests/data/net_liq_fixture.csv \
  --csv --pdf --output-dir "$OUT" --quiet
```

Date filtering:

```bash
python -m portfolio_exporter.scripts.net_liq_history_export --start 2025-01-01 --end 2025-03-31 --json
```

### Build Order (CLI)

The non-interactive order builder creates normalized ticket JSONs for common strategies.
For verticals, you can explicitly set orientation with `--credit` or `--debit`.
If omitted, legacy defaults apply (calls default to debit, puts default to credit).

```bash
# Bull call (debit) vs. bear call (credit)
python -m portfolio_exporter.scripts.order_builder --strategy vertical --symbol SPY --right C --expiry 2025-06-20 --strikes 400,410 --qty 1 --debit
python -m portfolio_exporter.scripts.order_builder --strategy vertical --symbol SPY --right C --expiry 2025-06-20 --strikes 400,410 --qty 1 --credit

# Bull put (credit) vs. bear put (debit)
python -m portfolio_exporter.scripts.order_builder --strategy vertical --symbol SPY --right P --expiry 2025-06-20 --strikes 390,380 --qty 1 --credit
python -m portfolio_exporter.scripts.order_builder --strategy vertical --symbol SPY --right P --expiry 2025-06-20 --strikes 390,380 --qty 1 --debit

# Short vs. long iron condor (strike order auto-sorted)
python -m portfolio_exporter.scripts.order_builder --strategy iron_condor --symbol SPY --expiry 2025-06-20 --strikes 380,390,410,420 --qty -1
python -m portfolio_exporter.scripts.order_builder --strategy iron_condor --symbol SPY --expiry 2025-06-20 --strikes 380,390,410,420 --qty 1

# Long vs. short butterfly
python -m portfolio_exporter.scripts.order_builder --strategy butterfly --symbol SPY --right C --expiry 2025-06-20 --strikes 390,400,410 --qty 1
python -m portfolio_exporter.scripts.order_builder --strategy butterfly --right C --symbol SPY --expiry 2025-06-20 --strikes 390,400,410 --qty -1

# Long vs. short calendar
python -m portfolio_exporter.scripts.order_builder --strategy calendar --symbol SPY --right C --strike 400 --expiry-near 2025-05-17 --expiry-far 2025-06-20 --qty 1
python -m portfolio_exporter.scripts.order_builder --strategy calendar --symbol SPY --right C --strike 400 --expiry-near 2025-05-17 --expiry-far 2025-06-20 --qty -1

# Long vs. short straddle
python -m portfolio_exporter.scripts.order_builder --strategy straddle --symbol SPY --expiry 2025-06-20 --strike 400 --qty 1
python -m portfolio_exporter.scripts.order_builder --strategy straddle --symbol SPY --expiry 2025-06-20 --strike 400 --qty -1

# Long vs. short strangle
python -m portfolio_exporter.scripts.order_builder --strategy strangle --symbol SPY --expiry 2025-06-20 --strikes 390,410 --qty 1
python -m portfolio_exporter.scripts.order_builder --strategy strangle --symbol SPY --expiry 2025-06-20 --strikes 390,410 --qty -1

# Covered call income vs. buy-write
python -m portfolio_exporter.scripts.order_builder --strategy covered_call --symbol SPY --expiry 2025-06-20 --call-strike 410 --qty -1
python -m portfolio_exporter.scripts.order_builder --strategy covered_call --symbol SPY --expiry 2025-06-20 --call-strike 410 --qty 1
```

### Wizard Auto Mode (preview)

The interactive wizard can suggest strikes from live data for verticals
(credit/debit) and iron condors, then let you accept or tweak. It remembers
your liquidity thresholds and risk-budget defaults in `.codex/memory.json`.

CLI preview for the same wizard selection logic:

```bash
# Preview vertical credit candidates and pick the 2nd to emit a ticket
python -m portfolio_exporter.scripts.order_builder \
  --wizard --auto --strategy vertical --right P \
  --symbol AAPL --expiry nov --profile balanced \
  --min-oi 200 --min-volume 50 --max-spread-pct 0.02 \
  --earnings-window 7 --pick 2 \
  --json --no-files

# Preview iron condor candidates
python -m portfolio_exporter.scripts.order_builder \
  --wizard --auto --strategy iron_condor \
  --symbol AAPL --expiry nov \
  --json --no-files

# Preview calendar / diagonal candidates (ATM near/far with optional offset)
python -m portfolio_exporter.scripts.order_builder \
  --wizard --auto --strategy calendar --right C \
  --symbol AAPL --expiry nov --strike-offset 1 \
  --min-oi 200 --min-volume 50 --max-spread-pct 0.02 \
  --earnings-window 7 --json --no-files
```

### Stage Order (menu)

From the Trades & Reports menu, choose Build order → Preset to stage tickets.

- Auto candidates: vertical (credit/debit), iron condor, butterfly, and calendar.
- Butterfly/calendar prompt for Right (C/P). Calendar also supports a diagonal offset.
- Flow: select a preset → Symbol → Expiry (date/month/DTE) → Auto = Y → review candidates table → pick a number → ticket JSON prints with a risk summary and optional save.
- Calendar rows show near/far hints and diagonal offset (e.g., `100/105 (n/f 30/60, Δ+1)`).
- Iron fly currently uses presets/manual (no auto suggestions yet).

### Expiry hint formats

When prompted for an expiry, you may provide:

* Exact date ``YYYYMMDD``
* ``YYYYMM`` to select the third Friday of that month (or the first listed expiry)
* Month name or abbreviation (e.g. ``June`` or ``Jun``)
* Day and month like ``26 Jun``, ``Jun 26`` or ``26/06``. The script picks the
  nearest available expiry on or after that date.
* DTE number (e.g., ``30``) to add N days, then snap to the next listed expiry

Leaving the field blank automatically chooses the next weekly expiry within a
week or the first Friday that is available.

## IBKR Setup

Scripts that use `ib_insync` (`historic_prices.py`, `live_feed.py` and
`tech_signals_ibkr.py`) expect the IBKR Trader Workstation or IB Gateway to be
running locally with API access enabled (default host `127.0.0.1` and port
`7497`). Ensure your IBKR configuration allows API connections from your machine
and that the account is logged in before running these scripts.
## Automation

Schedule `update_tickers.py` with cron or another task scheduler to run daily:

```cron
0 8 * * * /usr/bin/python3 /path/to/repo/update_tickers.py
```

This keeps `tickers_live.txt` synced with your IBKR portfolio.

## Utilities

Quickly inspect where scripts write their outputs (as configured by `OUTPUT_DIR` in your environment or `.env`):

```bash
python -m portfolio_exporter.scripts.show_output_dir
python -m portfolio_exporter.scripts.show_output_dir --json
```

### Orchestrator

Run the overnight dataset orchestrator directly:

```bash
python -m portfolio_exporter.scripts.orchestrate_dataset
```

Strict mode (fail on any missing expected files):

```bash
python -m portfolio_exporter.scripts.orchestrate_dataset --strict
```

Note: By default, missing files are skipped and the archive is still produced. Use `--strict` to return a non‑zero exit code if any expected file is missing.

#### Deterministic expectations

You can supply an explicit list of expected outputs so `--strict` behaves consistently even as scripts evolve:

```bash
# JSON array
echo '["portfolio_greeks_positions.csv","portfolio_greeks_combos.csv"]' > expect.json

# or an object with a files array
echo '{"files":["portfolio_greeks_positions.csv","live_quotes.csv"]}' > expect.json

python -m portfolio_exporter.scripts.orchestrate_dataset --expect expect.json --strict
```

Relative names resolve under `OUTPUT_DIR`; absolute paths are used as‑is.

#### Pre-flight

Run pre-flight validations (environment, optional imports, and recent CSV header sanity):

```bash
python -m portfolio_exporter.scripts.orchestrate_dataset --preflight
python -m portfolio_exporter.scripts.orchestrate_dataset --preflight --preflight-strict
```

Pre-flight does not run the batch; it only reports on the environment and most recent CSVs.

### Quick-Chain v3: Same-Δ & Tenor Filters

Compute nearest-to-target delta strikes per expiry and side, and filter expiries by tenor (weekly/monthly) while preserving existing quick_chain behavior.

Examples:

```bash
# Live/demo (requires network for yfinance if IB is unavailable)
python -m portfolio_exporter.scripts.quick_chain --symbols SPY --target-delta 0.25 --side both --tenor monthly --html

# Offline fixture (no network)
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --target-delta 0.30 --side put --tenor weekly

# Override output directory
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --output-dir /tmp

# JSON summary (no files written)
python -m portfolio_exporter.scripts.quick_chain --chain-csv tests/data/quick_chain_fixture.csv --json
```

Outputs:
- CSV: base chain table plus new columns: `call_same_delta_strike`, `call_same_delta_delta`, `call_same_delta_mid`, `call_same_delta_iv`, and corresponding `put_*` fields.
- HTML: optional minimal table when `--html` is provided.
- PDF: optional table when `--pdf` is provided and `reportlab` is installed.

JSON summary schema:

```
{
  "rows": <int>,
  "underlyings": [<str>],
  "tenor": "<value or ''>",
  "target_delta": <float | null>,
  "side": "<call|put|both|''>",
  "outputs": {"csv": "<path or ''>", "html": "<path or ''>", "pdf": "<path or ''>"}
}
```

CSV-only runs skip IBKR and Yahoo Finance imports thanks to lazy dependencies.

### Net-Liq chart

```bash
python -m portfolio_exporter.scripts.net_liq_history_export --fixture-csv tests/data/net_liq_fixture.csv --json
python -m portfolio_exporter.scripts.net_liq_history_export --fixture-csv tests/data/net_liq_fixture.csv --csv --pdf --output-dir ./.tmp_nlh
```

## Documentation

- docs/CONFIGURATION.md: environment variables, default paths, and output directory behavior.
- docs/TROUBLESHOOTING.md: common issues (data sources, PDF dependency, IBKR connectivity) and how to resolve them.

## Contributing

See Repository Guidelines in [AGENTS.md](AGENTS.md) for project structure, style, testing, and PR expectations. In short: use Python 3.11+, run `make setup`, lint with `make lint`, test with `make test`, and keep commits small and descriptive.
Sources and auto‑fallback
- `--source auto` tries, in order: local TWS `dailyNetLiq.csv`, Client Portal via `CP_REFRESH_TOKEN`, explicit `--fixture-csv`, and finally the repo fixture at `tests/data/net_liq_fixture.csv` when running from this repository.
- If no source is available, the error message explains the three options and shows the expected TWS path.

Quiet/CI mode
- Export `PE_QUIET=1` to disable Rich tables in script output without changing flags.
- Most CLIs also support `--quiet` and `--no-pretty` to suppress console rendering.

Troubleshooting
- No data source: ensure one of TWS export, CP token, or a fixture CSV is available; see docs/TROUBLESHOOTING.md.
- Missing PDF output: install `reportlab` (already included in `requirements.txt` for dev) or skip `--pdf`.



## License

This project is licensed under the [MIT License](LICENSE).
