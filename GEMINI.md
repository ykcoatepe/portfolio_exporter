# Gemini Project Brief: portfolio_exporter

This document provides project-specific context, conventions, and commands for the `portfolio_exporter` project to ensure effective collaboration with the Gemini assistant.

## Project Overview

`portfolio_exporter` is a Python-based toolkit for financial portfolio analysis, exporting data, and interacting with the Interactive Brokers (IBKR) API. It now features a unified `market_analyzer.py` script that consolidates functionalities for fetching historical prices, calculating portfolio greeks, analyzing technical signals, and managing trade reports.

## Key Technologies

- **Language:** Python 3.11
- **Dependencies:** Managed via `requirements.txt` (main) and `requirements-dev.txt` (development). Key libraries likely include `pandas`, `requests`, and the IBKR API client.
- **Testing:** `pytest`

## Project Structure

- `market_analyzer.py`: The primary script for all market analysis tasks.
- `*.py`: Other core scripts for specific data export and analysis tasks (e.g., `trades_report.py`, `net_liq_history_export.py`).
- `iv_history/`: Contains CSV files with historical volatility data for various tickers.
- `tests/`: Contains unit tests for the core scripts.
- `utils/`: Shared utility modules.
- `Makefile`: Defines setup and testing commands.

## Getting Started & Setup

To set up the development environment, run the following command. This will create a virtual environment and install all necessary dependencies.

```shell
make setup
```

## Running Tests

To run the test suite, use the following command:

```shell
make test
```

## Coding Conventions

- **Style:** Adhere to PEP 8 for all Python code.
- **Imports:** Use absolute imports where possible.
- **Modularity:** Keep scripts focused on a single responsibility. Reusable logic should be placed in the `utils/` directory.
- **Testing:** All new features or bug fixes should be accompanied by corresponding tests in the `tests/` directory.
