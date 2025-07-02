# Portfolio Exporter

This repository contains a collection of small helper scripts used to export quotes and technical data for a personal trading workflow. The scripts rely mostly on [yfinance](https://github.com/ranaroussi/yfinance) and optionally on [ib_insync](https://github.com/erdewit/ib_insync) for Interactive Brokers (IBKR) connectivity. A high level overview of the design and how the tools use IBKR and yfinance can be found in [docs/PDR.md](docs/PDR.md).

## Unified CLI

The `portfolio_exporter` is now a unified Command Line Interface (CLI) application, with `main.py` serving as the single entry point for all functionalities. The legacy scripts remain for reference but are no longer needed.

## Features

Here's an overview of the available commands and their functionalities:

*   **`pulse`**: Generates a one-row-per-ticker summary of technical indicators from an OHLCV CSV. Defaults to CSV output; use `--excel` or `--pdf` for other formats.
*   **`live`**: Takes a snapshot of real‑time quotes for tickers listed in `tickers_live.txt` (falling back to `tickers.txt`). Quotes are pulled from IBKR when available, otherwise from yfinance and FRED. Results are written to `live_quotes_YYYYMMDD_HHMM.csv`. Use `--pdf` to save a PDF report instead.
*   **`options`**: Saves a complete IBKR option chain for the portfolio or given symbols. Results are zipped into `option_chain_<DATE_TIME>.zip` and the original files are removed. Defaults to CSV; use `--excel` or `--pdf` to change the output type.
*   **`positions`**: Fetches portfolio positions from IBKR.
*   **`report`**: Exports executions and open orders from IBKR. Use `--date` to filter trades by `today`, `yesterday`, `week_to_date`, or a custom range with `--start` and `--end`. Add `--excel` or `--pdf` for formatted reports.
*   **`orchestrate`**: Runs a sequence of commands (pulse, live, options) and zips the results.
*   **`portfolio-greeks`**: Calculates and exports per-position Greeks and account totals using IBKR market data. Index underlyings (e.g. VIX, SPX) are excluded by default; use `--include-indices` to include them.

## Script Overview

| Script | Description |
| ------ | ----------- |
| `historic_prices.py` | Downloads the last 60 days of daily OHLCV data for tickers read from `tickers_live.txt` or `tickers.txt`. If IBKR is reachable, the current account holdings are used as the ticker list. |
| `live_feed.py` | Takes a snapshot of real‑time quotes for tickers. IBKR is tried first, then falls back to Yahoo Finance. |
| `tech_signals.py` | Fetches historical bars via yfinance and calculates indicators (ADX, ATR, moving averages, IV rank, RSI). |
| `tech_signals_ibkr.py` | Enhanced version that pulls data via IBKR and includes option chain information. |

## Requirements

- **Python** 3.11 or newer
- Dependencies listed in [requirements.txt](requirements.txt)

## Installation

1. Clone the repository
2. Set up a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## IBKR / TWS Gateway Setup (Optional)

To use IBKR-powered features:

1. Launch TWS or IB Gateway and log in
2. Go to **Configure → API → Settings**
3. Enable *Allow connections from localhost*
4. Note the port (default `7497` for paper trading)
5. If needed, update the `IB_HOST`, `IB_PORT`, and `IB_CID` variables in the scripts

## Usage

To see all available commands and their options, run:

```bash
python main.py --help
```

Here are some common usage examples:

```bash
# Generate a daily pulse report
python main.py pulse --tickers "AAPL,MSFT,GOOG" --output pulse.csv --output-dir ~/Downloads

# Fetch portfolio positions, grouped by combo
python main.py positions --group-by-combo

# Calculate portfolio Greeks
python main.py portfolio-greeks

# Grab a live quote snapshot
python main.py live --format pdf

# Interactively choose symbols and expiries for option chain
python main.py options --tickers SPY

# Option-chain snapshot for specific symbols and expiries
python main.py options --tickers TSLA,AAPL --expiries 20250620

# Export today's executions and open orders
python main.py report --date today

# Custom date range
python main.py report --date custom --start 2025-06-01 --end 2025-06-30
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
