# Gemini Project Brief: portfolio_exporter

This document provides project-specific context, conventions, and commands for the `portfolio_exporter` project to ensure effective collaboration with the Gemini assistant.

## Project Overview

`portfolio_exporter` is a Python-based toolkit for financial portfolio analysis, exporting data, and interacting with the Interactive Brokers (IBKR) API. It has been refactored into a unified Command Line Interface (CLI) for all functionality.

## Key Technologies

- **Language:** Python 3.11
- **Dependencies:** Managed via `requirements.txt` (main) and `requirements-dev.txt` (development). Key libraries include `pandas`, `yfinance`, and `ib_insync`.
- **Testing:** `pytest`

## Project Structure

- `main.py`: The single entry point for the CLI application.
- `src/`: Contains all the core logic for the application.
  - `data_fetching.py`: Functions for fetching data from IBKR and Yahoo Finance.
  - `analysis.py`: Functions for performing financial analysis and calculating indicators.
  - `reporting.py`: Functions for generating reports in various formats.
  - `interactive.py`: Functions for handling user interaction.
- `tests/`: Contains unit tests for the core scripts.
- `utils/`: Shared utility modules.
- `Makefile`: Defines setup and testing commands.

## Getting Started & Setup

To set up the development environment, run the following command. This will create a virtual environment and install all necessary dependencies.

```shell
make setup
```

## Running the Application

The application is now run through `main.py`. Here are some examples:

- **Generate a daily pulse report:**
  ```shell
  python main.py pulse --tickers "AAPL,MSFT,GOOG" --output pulse.csv
  ```

- **See all available commands:**
  ```shell
  python main.py --help
  ```

- **Run a specific command:**
  ```shell
  python main.py <command> --help
  ```
  (e.g., `python main.py historic-prices --help`)

## Running Tests

To run the test suite, use the following command:

```shell
make test
```

## Coding Conventions

- **Style:** Adhere to PEP 8 for all Python code.
- **Imports:** Use absolute imports where possible.
- **Modularity:** All core logic is organized by function in the `src/` directory.
- **Testing:** All new features or bug fixes should be accompanied by corresponding tests in the `tests/` directory.