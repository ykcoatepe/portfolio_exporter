# Repository Guidelines

This guide helps contributors work productively in this repository. Keep changes focused, tested, and consistent with the existing style.

## Project Structure & Module Organization
- Source: `portfolio_exporter/` with subpackages `config/`, `core/`, `menus/`, `scripts/`.
- Entry scripts: repo root (e.g., `market_analyzer.py`, `update_tickers.py`) and CLI modules under `portfolio_exporter/scripts/` (e.g., `python -m portfolio_exporter.scripts.daily_report`).
- Tests: `tests/` as `test_*.py`, fixtures in `tests/data/`.
- Docs & assets: `docs/`; sample CSVs in repo root (e.g., `sample_portfolio.csv`).

## Build, Test, and Development Commands
- `make setup`: Create `.venv` and install `requirements*.txt`.
- `make lint`: Run Ruff per `pyproject.toml` rules.
- `make test` or `pytest -q`: Run the unit tests from repo root.
- `make build` or `python -m build`: Build wheel/sdist to validate packaging.
Typical loop: `make setup && make lint && make test`.

## Coding Style & Naming Conventions
- Python 3.11+, 4‑space indent; add type hints on new/changed code.
- Formatting: Black (line length 88). Linting: `ruff check .` (tests/legacy excluded via config).
- Naming: modules `snake_case.py`; classes `PascalCase`; functions/vars `snake_case`.
- Keep imports tidy; avoid eager imports in package `__init__` to keep CLI startup fast.

## Testing Guidelines
- Framework: `pytest`; tests fast, deterministic, and isolated (no network).
- Layout: `tests/test_*.py` near target modules; use fixtures under `tests/data/`.
- Run: `pytest -q` or a single file (e.g., `pytest -q tests/test_daily_report.py`).

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject (e.g., `Add option chain helper`) and brief rationale for behavior changes.
- PRs: clear description, linked issues, minimal diff, and local test steps (commands + expected output). Include CLI logs/screenshots when useful.

## Security & Configuration Tips
- Configure via environment; see `.env.example` and `pytest.ini` (e.g., `PE_QUIET=1`, `OUTPUT_DIR`).
- IBKR Client Portal flows require `CP_REFRESH_TOKEN` exported.
- Do not commit secrets or local data (tokens, CSV/exports). Update `.gitignore` as needed.

