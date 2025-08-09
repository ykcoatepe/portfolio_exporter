# Repository Guidelines

## Project Structure & Module Organization
- Source: `portfolio_exporter/` with submodules `config/`, `core/`, `menus/`, `scripts/`.
- Entry scripts at repo root (e.g., `market_analyzer.py`, `update_tickers.py`).
- Tests: `tests/` with `test_*.py` mirroring package paths.
- Docs & assets: `docs/`; examples in repo root (e.g., `sample_portfolio.csv`).

## Build, Test, and Development Commands
- `make setup`: Create `.venv` and install `requirements.txt` + `requirements-dev.txt`.
- `make lint`: Run Ruff using rules in `pyproject.toml`.
- `make test` or `pytest -q`: Run unit tests locally from repo root.
- `make build` or `python -m build`: Build wheel/sdist to validate packaging.
- Suggested flow: `make setup && make lint && make test`.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indent; prefer type hints on new/changed code.
- Formatting: Black (default config; line length 88).
- Linting: `ruff check .` (tests and `legacy/` excluded via `pyproject.toml`).
- Naming: modules `snake_case.py`; classes `PascalCase`; functions/vars `snake_case`.
- Keep imports tidy, remove dead code, and keep functions small and focused.

## Testing Guidelines
- Framework: `pytest`.
- Test layout: files under `tests/` named `test_*.py` mirroring package structure.
- Run locally: `pytest` or `pytest -q`.
- Tests must be deterministic; avoid network calls—stub IBKR/Yahoo; keep fast and isolated.

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject (e.g., `Add option chain helper`); include rationale when behavior changes.
- PRs: clear description, linked issues, minimal diff, and steps to test (commands + expected output). Add logs/screenshots for CLI behavior.

## Security & Configuration Tips
- Configure via environment; see `.env.example` and `pytest.ini` (e.g., `PE_QUIET=1`).
- IBKR Client Portal scripts require `CP_REFRESH_TOKEN` exported.
- Never commit secrets or local data (tokens, CSV exports). Update `.gitignore` when adding new patterns.
