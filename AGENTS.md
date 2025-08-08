# Repository Guidelines

## Project Structure & Module Organization
- Source: `portfolio_exporter/` (submodules: `config/`, `core/`, `menus/`, `scripts/`).
- Entry scripts: top-level Python files (e.g., `market_analyzer.py`, `update_tickers.py`).
- Tests: `tests/` with `test_*.py` modules mirroring package structure.
- Docs & assets: `docs/`, examples in repo root (e.g., `sample_portfolio.csv`).

## Build, Test, and Development Commands
- `make setup`: Create `.venv` and install `requirements.txt` + `requirements-dev.txt`.
- `make lint`: Run Ruff against the repo (config in `pyproject.toml`).
- `make test` or `pytest -q`: Run unit tests locally.
- `make build` or `python -m build`: Build a wheel/sdist to validate packaging.
- Example flow: `make setup && make lint && make test`.

## Coding Style & Naming Conventions
- Python 3.11+; 4-space indent; prefer type hints for new/changed code.
- Formatting: `black` (default config; line length 88).
- Linting: `ruff check .` with rules from `pyproject.toml` (tests and `legacy/` excluded).
- Naming: modules `snake_case.py`, classes `PascalCase`, functions/vars `snake_case`.
- Clean imports; remove unused code; keep functions small and focused.

## Testing Guidelines
- Framework: `pytest` with tests under `tests/` named `test_*.py`.
- Write deterministic tests; avoid network calls—use fixtures/stubs for IBKR/Yahoo.
- Keep unit tests fast; prefer small, isolated inputs and clear assertions.
- Run from repo root: `pytest` or `pytest -q`.

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject (e.g., `Add option chain helper`).
- Scope commits narrowly; include rationale when behavior changes.
- PRs: clear description, linked issues, minimal diff, steps to test (commands + expected output). Add logs/screenshots when relevant for CLI behavior.

## Security & Configuration Tips
- Configuration via environment: see `.env.example` and `pytest.ini` (e.g., `PE_QUIET=1`).
- IBKR Client Portal: export `CP_REFRESH_TOKEN` for scripts that require it.
- Do not commit secrets or local data (tokens, CSV exports). Add new ignore patterns to `.gitignore` as needed.
