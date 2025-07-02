# Portfolio Exporter

This repository contains a collection of small helper scripts used to export quotes
and technical data for a personal trading workflow. The scripts rely mostly on
[yfinance](https://github.com/ranaroussi/yfinance) and optionally on
[ib_insync](https://github.com/erdewit/ib_insync) for Interactive Brokers (IBKR)
connectivity. A high level overview of the design and how the tools use IBKR and
yfinance can be found in [docs/PDR.md](docs/PDR.md).

## Unified CLI

The `portfolio_exporter` is now a unified Command Line Interface (CLI) application, with `main.py` serving as the single entry point for all functionalities. The legacy scripts remain for reference but are no longer needed.

### Features

Here's an overview of the available commands and their functionalities:

*   **`pulse`**: Generates a one-row-per-ticker summary of technical indicators from an OHLCV CSV. Defaults to CSV output; use `--excel` or `--pdf` for other formats. (Replaces `daily_pulse.py`)
*   **`live`**: Takes a snapshot of real‑time quotes for tickers listed in `tickers_live.txt` (falling back to `tickers.txt`). Quotes are pulled from IBKR when available, otherwise from yfinance and FRED. Results are written to `live_quotes_YYYYMMDD_HHMM.csv`. Use `--pdf` to save a PDF report instead. (Replaces `live_feed.py`)
*   **`options`**: Saves a complete IBKR option chain for the portfolio or given symbols. Results are zipped into `option_chain_<DATE_TIME>.zip` and the original files are removed. Defaults to CSV; use `--excel` or `--pdf` to change the output type. (Replaces `option_chain_snapshot.py`)
*   **`report`**: Exports executions and open orders from IBKR to CSV for a chosen date range. Add `--excel` or `--pdf` for formatted reports. (Replaces `trades_report.py`)
*   **`orchestrate`**: Runs the main export scripts in sequence (historic prices, portfolio greeks, live feed, and daily pulse), zips the results into `dataset_<DATE_TIME>.zip`, and deletes the individual files. (Replaces `orchestrate_dataset.py`)
*   **`historic-prices`**: Downloads the last 60 days of daily OHLCV data for tickers read from `tickers_live.txt` or `tickers.txt`. If IBKR is reachable, the current account holdings are used as the ticker list. The output is a timestamped CSV in `~/Library/Mobile\ Documents/.../Downloads`. Use `--excel` or `--pdf` to save as those formats instead. (Replaces `historic_prices.py`)
*   **`tech-signals`**: Calculates technical indicators using IBKR data and includes option chain details like open interest (fetched from Yahoo Finance) and near‑ATM implied volatility. (Replaces `tech_signals_ibkr.py`)
*   **`update-tickers`**: Writes the current IBKR stock positions to `tickers_live.txt` so other scripts always use a fresh portfolio. (Replaces `update_tickers.py`)
*   **`portfolio-greeks`**: Exports per-position Greeks and account totals using IBKR market data, producing `portfolio_greeks_<YYYYMMDD_HHMM>.csv` and a totals file. Pass `--excel` or `--pdf` for alternative formats. (Replaces `portfolio_greeks.py`)
*   **`net-liq-history`**: Creates an end-of-day Net-Liq history CSV from TWS logs or Client Portal data and can optionally plot an equity curve. Supports `--excel` and `--pdf` outputs. (Replaces `net_liq_history_export.py`)

### Usage

To see all available commands and their options, run:

```bash
python main.py --help
```

Here are some common usage examples:

All major features are exposed through `main.py`. Use the sub‑commands below as a
drop‑in replacement for the old scripts:

```bash
python main.py pulse        # daily_pulse.py
python main.py live         # live_feed.py
python main.py options      # option_chain_snapshot.py
python main.py report       # trades_report.py
python main.py orchestrate  # orchestrate_dataset.py
```

The legacy scripts remain for reference but are no longer needed.

## Usage Examples

```bash
# Generate a daily pulse report
python main.py pulse --tickers "AAPL,MSFT,GOOG" --output pulse.csv

# Fetch recent historical prices
python main.py historic-prices

# Grab a live quote snapshot
python main.py live

# Refresh tickers_live.txt from IBKR
python main.py update-tickers

# Calculate technical indicators using IBKR data
python main.py tech-signals

# Interactively choose symbols and expiries
python main.py options

# Option-chain snapshot for specific symbols and expiries
python main.py options --symbol-expiries 'TSLA:20250620,20250703;AAPL:20250620'

# Export today's executions and open orders
python main.py report --today
```

### Expiry Hint Formats

When prompted for an expiry, you may provide:

*   Exact date `YYYYMMDD`
*   `YYYYMM` to select the third Friday of that month (or the first listed expiry)
*   Month name or abbreviation (e.g., `June` or `Jun`)
*   Day and month like `26 Jun`, `Jun 26`, or `26/06`. The script picks the nearest available expiry on or after that date.

Leaving the field blank automatically chooses the next weekly expiry within a week or the first Friday that is available.

## IBKR Setup

Commands that use `ib_insync` expect the IBKR Trader Workstation or IB Gateway to be running locally with API access enabled (default host `127.0.0.1` and port `7497`). Ensure your IBKR configuration allows API connections from your machine and that the account is logged in before running these commands.

## Automation

Schedule `python main.py update-tickers` with cron or another task scheduler to run daily:

```cron
0 8 * * * /usr/bin/python3 /path/to/repo/main.py update-tickers
```

This keeps `tickers_live.txt` synced with your IBKR portfolio.

## License

This project is licensed under the [MIT License](LICENSE).
