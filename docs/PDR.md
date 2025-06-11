# Portfolio Exporter Design Rationale

This document outlines the goals of the project and provides a high level overview of the main scripts. All utilities revolve around exporting market and portfolio data either from **Interactive Brokers** (IBKR) via `ib_insync` or from **yfinance** for tickers that cannot be served by IBKR.

## Goals

* Keep a lightweight toolkit to pull snapshots of historical prices, live quotes and portfolio Greeks.
* Prefer IBKR market data when available but gracefully fall back to yfinance and FRED for public data.
* Store results as timestamped CSV files under the Downloads directory so they can be easily analysed elsewhere. Most scripts also support Excel (`--excel`) and PDF (`--pdf`) output.

## Script Interaction

| Script | IBKR Usage | yfinance Usage |
| ------ | ---------- | -------------- |
| `historic_prices.py` | fetches tickers from the account and optionally pulls quotes via IBKR | downloads OHLCV data when IBKR is unavailable |
| `live_feed.py` | pulls real‑time quotes and option positions from IBKR; missing tickers fall back to FRED/yfinance | used for tickers not served by IBKR |
| `tech_signals_ibkr.py` | computes technical indicators using IBKR data and option chains | fetches historical prices and market data when IBKR connection fails |
| `update_tickers.py` | saves the list of stock tickers held in the IBKR account | – |
| `portfolio_greeks.py` | retrieves option positions and Greeks from IBKR | – |
| `option_chain_snapshot.py` | exports the full IBKR option chain for each underlying | – |
| `net_liq_history_export.py` | reads TWS logs or queries the Client Portal for account net‑liquidation history | – |

These scripts share a common approach: IBKR is queried first for portfolio aware data; if connectivity is not available or the ticker is unsupported, they use public APIs such as yfinance. This makes the tools useful even without a running IBKR gateway.


