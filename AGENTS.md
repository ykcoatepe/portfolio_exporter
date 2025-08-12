# Repository Guidelines

This document summarizes how to work productively in this repo. Keep changes focused, tested, and consistent with the existing style.

## Project Structure & Module Organization
- Source: `portfolio_exporter/` with subpackages `config/`, `core/`, `menus/`, `scripts/`.
- Entry scripts: repo root (e.g., `market_analyzer.py`, `update_tickers.py`), plus CLI modules under `portfolio_exporter/scripts/`.
- Tests: `tests/` as `test_*.py`, mirroring package paths. Data fixtures in `tests/data/`.
- Docs & assets: `docs/`; sample CSVs in repo root (e.g., `sample_portfolio.csv`).

## Build, Test, and Development Commands
- `make setup`: Create `.venv` and install `requirements*.txt`.
- `make lint`: Run Ruff per `pyproject.toml` rules.
- `make test` or `pytest -q`: Execute unit tests from repo root.
- `make build` or `python -m build`: Build wheel/sdist to validate packaging.
- Typical loop: `make setup && make lint && make test`.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indent, prefer type hints on new/changed code.
- Formatting: Black (88 chars). Linting: `ruff check .` (tests/legacy excluded via config).
- Naming: modules `snake_case.py`; classes `PascalCase`; functions/vars `snake_case`.
- Keep imports tidy, avoid eager imports in package `__init__` to reduce CLI startup cost.

## Testing Guidelines
- Framework: `pytest` (deterministic; no network). Stub IBKR/Yahoo; use fixtures in `tests/data/`.
- Layout: `tests/test_*.py` alongside target modules; fast and isolated.
- Run: `pytest -q` or a single file (e.g., `pytest -q tests/test_quick_chain_cli.py`).

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject (e.g., `Add option chain helper`), include rationale for behavior changes.
- PRs: clear description, linked issues, minimal diff, and local test steps (commands + expected output). Include CLI logs/screenshots when useful.

## Security & Configuration Tips
- Configure via environment; see `.env.example` and `pytest.ini` (e.g., `PE_QUIET=1`).
- IBKR Client Portal flows require `CP_REFRESH_TOKEN` exported.
- Do not commit secrets or local data (tokens, CSV/exports). Update `.gitignore` as needed.
