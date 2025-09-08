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
 - `make sanity-order-builder`: Quick JSON-only sanity for order builder presets.
 - `make menus-sanity`: Import and preview smoke for Trades menu helpers.
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

## Assistant Bootstrapping
- On session start: run `python -m portfolio_exporter.scripts.memory bootstrap`.
  - Ensures memory exists, logs `session_start`, prints concise context (preferences, workflows, open tasks/questions, decisions_count).
- After notable changes: add a decision and a changelog entry.
- For summaries: run `python -m portfolio_exporter.scripts.memory digest` (`--json` for machine output).
- Useful commands:
  - `make memory-context` → print context (summary)
  - `make memory-digest` → human-friendly digest
  - `make memory-validate` → quick schema check
  - `make memory-view` → workflows overview
  - `make memory-tasks` → open tasks list
  - `make memory-questions` → open questions list
  - Full CLI: `python -m portfolio_exporter.scripts.memory --help`

---

# 17 · Repo Memory (Agent-Shared)

Purpose. Lightweight, auditable repo “memory” so Cloud/CLI agents keep context across sessions.
Location. Default `.codex/memory.json` (override with `--path`).
Privacy. No secrets; validation scans for common patterns. Set `MEMORY_READONLY=1` to block writes.

## 17.1 Features

- Safe writes: Lockfile + atomic write (`fsync` → `os.replace`), stable/sorted JSON.
- Schema v1: required keys → `preferences, workflows, tasks, questions, decisions, changelog`.
- Machine output: read/list commands support `--json`.
- Digest & rotation:
  - `digest` → compact summary (prefs, workflow keys, top open tasks/questions, recent decisions, counts). Text or `--json`.
  - `rotate` → move old changelog entries to `memory.YYYYMM.json`.

## 17.2 CLI Surface

Note: use `python -m portfolio_exporter.scripts.memory …` (or the `memory` alias below).

```
memory
  bootstrap | validate
  view [--section preferences|workflows|tasks|questions|decisions|changelog] [--json]
  list-tasks [--status open|in_progress|blocked|closed] [--owner name] [--json]
  add-task "Title" [--details "..."] [--labels a,b] [--priority N] [--owner name]
  update-task <id> [--status ...] [--title ...] [--details ...] [--append] [--priority N] [--labels a,b]
  close-task <id> [--reason "..."]
  add-decision "Title" "Decision" [--rationale "..."] [--context "..."]
  changelog "Event" [--details "..."] | session-end
  digest [--max-tokens 800] [--json] | rotate [--cutoff 30d]
  format
```

Options: `--path <file>` to target a custom memory file • `MEMORY_READONLY=1` disables writes (exit 0 with note).

## 17.3 Operating Rules

- Validate before PRs: `memory validate` must pass.
- Traceability: when tasks change, consider adding a decision or changelog entry.
- Scope & minimalism: keep technical prefs/flows/tasks/decisions only; no sensitive data.
- Merge hygiene: keep JSON sorted; prefer small, atomic edits.

## 17.4 CI/Hooks

- Pre-commit: run `memory validate` (and optional JSON formatter).
- CI gates: include `make memory-validate`.
- Optional reporting: print `make memory-digest` in CI logs for quick context.

## 17.5 Examples

```bash
# Snapshot & validate
make memory-validate
memory digest
memory digest --json > memory_digest.json

# Task flow
memory add-task "Refactor exporter" --labels infra --priority 2
memory update-task 1 --status in_progress --details "split writer"
memory close-task 1 --reason "merged"

# Session & rotation
memory session-end
memory rotate --cutoff 45d
```

### 17.5.1 Wizard preferences

The order builder wizard persists lightweight defaults under
`preferences.order_builder_wizard` in `.codex/memory.json`:

```
{
  "preferences": {
    "order_builder_wizard": {
      "profile": "balanced",
      "avoid_earnings": true,
      "min_oi": 200,
      "min_volume": 50,
      "max_spread_pct": 0.02,
      "risk_budget_pct": 2
    }
  }
}
```

These are updated interactively when you use the wizard’s Auto flow. Writes are
atomic (`fsync` + `os.replace`) and skipped if `MEMORY_READONLY=1`.

## 17.6 Acceptance Criteria

- Validation passes; no schema/secret issues.
- `digest` text stays concise (< 800 tokens) and `--json` is well-formed.
- No JSON corruption under concurrent writes (lock + atomic write).
- PR checklist includes “memory validate”.

## 17.7 Shell Alias (optional)

To use the short form `memory` locally, add to your shell profile (`~/.zshrc`/`~/.bashrc`):

```sh
alias memory='python -m portfolio_exporter.scripts.memory'
```

Reload your shell, then run `memory --help`.
