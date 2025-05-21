# Portfolio Exporter

This repository contains a collection of small helper scripts used to export quotes
and technical data for a personal trading workflow. The scripts rely mostly on
[yfinance](https://github.com/ranaroussi/yfinance) and optionally on
[ib_insync](https://github.com/erdewit/ib_insync) for Interactive Brokers (IBKR)
connectivity.

## Script Overview

| Script | Description |
| ------ | ----------- |
| `historic_prices.py` | Downloads the last 60 days of daily OHLCV data for tickers read from `tickers_live.txt` or `tickers.txt`. If IBKR is reachable, the current account holdings are used as the ticker list. The output is a timestamped CSV in `~/Library/Mobile\ Documents/.../Downloads`. |
| `live_feed.py` | Takes a snapshot of real‑time quotes for tickers listed in `tickers_live.txt` (falling back to `tickers.txt`). Quotes are pulled from IBKR when available, otherwise from yfinance and FRED. Results are written to `live_quotes_YYYYMMDD_HHMM.csv`. |
| `tech_signals.py` | Fetches historical bars via yfinance only and calculates indicators such as ADX, ATR, moving averages, IV rank and RSI. Output goes to `tech_signals.csv`. |
| `tech_signals_ibkr.py` | Similar to `tech_signals.py` but pulls data via IBKR and includes option chain information like open interest and near‑ATM implied volatility. |

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The scripts require Python 3.11+ and the packages listed in `requirements.txt`.

## Usage Examples

```bash
# Fetch recent historical prices
python historic_prices.py

# Grab a live quote snapshot
python live_feed.py

# Calculate technical indicators with yfinance
python tech_signals.py

# Calculate technical indicators using IBKR data
python tech_signals_ibkr.py
```

## IBKR Setup

Scripts that use `ib_insync` (`historic_prices.py`, `live_feed.py` and
`tech_signals_ibkr.py`) expect the IBKR Trader Workstation or IB Gateway to be
running locally with API access enabled (default host `127.0.0.1` and port
`7497`). Ensure your IBKR configuration allows API connections from your machine
and that the account is logged in before running these scripts.

## License

This project is licensed under the [MIT License](LICENSE).
