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

### Trades Report

Examples with date filters and summaries:

```bash
# Last week only, summary as text
python -m portfolio_exporter.scripts.trades_report --since 2025-08-01 --until 2025-08-08 --no-pretty

# Single day in JSON (no files written)
python -m portfolio_exporter.scripts.trades_report --since 2025-08-09 --until 2025-08-09 --summary-only --json

# Offline CSV + filter + debug combos
python -m portfolio_exporter.scripts.trades_report --executions-csv tests/data/offline_executions_combo_sample.csv --since 2025-08-01 --until 2025-08-31 --debug-combos
```

JSON summary fields: `n_total`, `n_kept`, `u_count`, `underlyings`, `net_credit_debit`, `combos_total`, `combos_by_structure`, and `outputs` (paths when written).
```

Open interest values are sourced from Yahoo Finance rather than the IBKR feed.

### Expiry hint formats

When prompted for an expiry, you may provide:

* Exact date ``YYYYMMDD``
* ``YYYYMM`` to select the third Friday of that month (or the first listed expiry)
* Month name or abbreviation (e.g. ``June`` or ``Jun``)
* Day and month like ``26 Jun``, ``Jun 26`` or ``26/06``. The script picks the
  nearest available expiry on or after that date.

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
```

Outputs:
- CSV: base chain table plus new columns: `call_same_delta_strike`, `call_same_delta_delta`, `call_same_delta_mid`, `call_same_delta_iv`, and corresponding `put_*` fields.
- HTML: optional minimal table when `--html` is provided.
- PDF: optional table when `--pdf` is provided and `reportlab` is installed.

## Contributing

See Repository Guidelines in [AGENTS.md](AGENTS.md) for project structure, style, testing, and PR expectations. In short: use Python 3.11+, run `make setup`, lint with `make lint`, test with `make test`, and keep commits small and descriptive.


## License

This project is licensed under the [MIT License](LICENSE).
