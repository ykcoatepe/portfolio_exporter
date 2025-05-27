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
| `tech_signals_ibkr.py` | Calculates technical indicators using IBKR data and includes option chain details like open interest and near‑ATM implied volatility. |
| `update_tickers.py` | Writes the current IBKR stock positions to `tickers_live.txt` so other scripts always use a fresh portfolio. |
| `portfolio_greeks.py` | Exports per-position Greeks and account totals using IBKR market data, producing `portfolio_greeks_<YYYYMMDD>.csv` and a totals file. |
| `option_chain_snapshot.py` | Saves a complete IBKR option chain to CSV for the entire portfolio or specified symbols, handling live and delayed data automatically. |
| `net_liq_history_export.py` | Creates an end-of-day Net-Liq history CSV from TWS logs or Client Portal data and can optionally plot an equity curve. |

### CP_REFRESH_TOKEN
`net_liq_history_export.py` looks for the environment variable `CP_REFRESH_TOKEN` when pulling data from the Client Portal API. Set it before running the script:

```bash
export CP_REFRESH_TOKEN=<your refresh token>
```

If the token is not present, the script will attempt to read `dailyNetLiq.csv` from Trader Workstation instead.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The scripts require Python 3.11+ and the packages listed in `requirements.txt`.
`pandas_datareader` is needed for downloading FRED data in `live_feed.py`, and `requests` is required by `net_liq_history_export.py` for accessing the IBKR Client Portal API.

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
```

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


## License

This project is licensed under the [MIT License](LICENSE).
