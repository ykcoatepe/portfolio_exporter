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

## Contributing

See Repository Guidelines in [AGENTS.md](AGENTS.md) for project structure, style, testing, and PR expectations. In short: use Python 3.11+, run `make setup`, lint with `make lint`, test with `make test`, and keep commits small and descriptive.


## License

This project is licensed under the [MIT License](LICENSE).
