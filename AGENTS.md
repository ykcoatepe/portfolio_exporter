Agent Guide — portfolio_exporter (Codex CLI & Cloud)

Version: 2025‑09‑11 • Owner: CodeForge AI • Scope: Contributors & Agents (Codex CLI + Cloud)

Mission: keep changes elegant, tested, safe; make agents productive with a small, auditable repo memory.

⸻

0) 90‑Second Quickstart

make setup && make lint && make test
python -m portfolio_exporter.scripts.memory bootstrap
make memory-validate && make memory-digest

Optional shell alias:

alias memory='python -m portfolio_exporter.scripts.memory'


⸻

1) Project Structure & Naming
	•	Source: portfolio_exporter/ → config/, core/, menus/, scripts/.
	•	Entry scripts: repo root (e.g., market_analyzer.py, update_tickers.py) and module invocations under portfolio_exporter/scripts/ (e.g., python -m portfolio_exporter.scripts.daily_report).
	•	Tests: tests/ with test_*.py; fixtures in tests/data/.
	•	Docs & assets: docs/; sample CSVs in repo root (e.g., sample_portfolio.csv).
	•	Style: Python 3.11+, 4‑space indent, type hints on new/changed code.
	•	Naming: modules snake_case.py; classes PascalCase; functions/vars snake_case.
	•	Imports: keep tidy; avoid eager imports in package __init__ to preserve fast CLI startup.

⸻

2) Dev Tooling & Commands
	•	Format: Black (line length 88).
	•	Lint: Ruff (ruff check .).
	•	Type‑check: mypy (strict-ish for libs; allow gradual typing in apps).
	•	Tests: pytest -q (offline, deterministic; no network I/O).
	•	Build: make build or python -m build.
	•	Make targets:
	•	make setup — creates .venv, installs requirements*.txt.
	•	make lint — runs Ruff per pyproject.toml.
	•	make test — runs unit tests.
	•	make sanity-order-builder — quick JSON-only sanity for order‑builder presets.
		•	make menus-sanity — import/preview smoke for Trades menu helpers.
		•	make sanity-micro-momo — Micro‑MOMO JSON-only sanity (CSV fixtures; no files)
		•	make memory-* — see §4.

Typical loop: make setup && make lint && make test.

Optional upgrade track (packaging): If/when we migrate to PEP 621 + pyproject.toml, prefer uv for venv/lock/sync; commit lock file and keep src/ layout for new libs.

⸻

3) Testing Guidelines
	•	Framework: pytest.
	•	Discovery: tests/test_*.py; keep unit tests fast and hermetic (no network, time fixed where needed).
	•	Structure: collocate test_*.py near target modules; share fixtures in tests/data/.
	•	Run examples:

pytest -q
pytest -q tests/test_daily_report.py
pytest -q tests/test_daily_report.py::test_summary



⸻

4) Repo Memory (Agent‑Shared)

Purpose. Lightweight, auditable context so Cloud/CLI agents keep state across sessions.

Location. Default ./.codex/memory.json (override with --path).

Privacy. No secrets. Built‑in validation scans for common secret patterns. Set MEMORY_READONLY=1 to block writes.

4.1 Features
	•	Safe writes: lockfile + atomic write (fsync then os.replace), stable/sorted JSON.
	•	Schema v1: required keys → preferences, workflows, tasks, questions, decisions, changelog.
	•	Machine output: view/list-*/digest support --json for programmatic use.
	•	Digest & rotation:
	•	digest → compact summary (prefs, workflow keys, top open tasks/questions, recent decisions, counts). --json emits schema‑stable output.
	•	rotate → move old changelog entries to memory.YYYYMM.json.

4.2 CLI Surface

Use python -m portfolio_exporter.scripts.memory … (or memory alias).

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

Options: --path <file> to target a custom memory file • MEMORY_READONLY=1 disables writes (exit 0 with note).

4.3 Operating Rules
	•	Validate before PRs: memory validate must pass.
	•	Traceability: when tasks change, consider adding a decision or changelog entry.
	•	Scope & minimalism: keep technical prefs/flows/tasks/decisions only; no sensitive data.
	•	Merge hygiene: keep JSON sorted; prefer small, atomic edits.

4.4 Make helpers
	•	make memory-context — print context (summary)
	•	make memory-digest — human‑friendly digest
	•	make memory-validate — quick schema check
	•	make memory-view — workflows overview
	•	make memory-tasks — open tasks list
	•	make memory-questions — open questions list

4.5 Wizard preferences (order builder)

Lightweight defaults live under preferences.order_builder_wizard in .codex/memory.json:

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

Writes are atomic and skipped when MEMORY_READONLY=1.

4.6 Acceptance Criteria (Memory)
	•	memory validate returns non‑zero on invalid schema; CI fails cleanly.
	•	digest text stays concise (< 800 tokens); --json remains well‑formed and stable.
	•	No JSON corruption under concurrent writes (lock + atomic write).

4.7 Trades intent preference

To improve Open/Close/Roll detection in trades_report across days, set a prior positions CSV in repo memory. The script auto‑uses this path when present and still allows CLI override.

Example (.codex/memory.json):

{
  "preferences": {
    "trades_prior_positions": "/absolute/path/to/portfolio_greeks_positions_YYYYMMDD_HHMM.csv"
  }
}

Notes:
- CLI override: --prior-positions-csv takes precedence when provided.
- Without a prior snapshot, intent still works using streaming deltas (stocks keyed by symbol) and openClose overrides, but accuracy improves with a strictly prior snapshot.

⸻

5) Security & Configuration
	•	Configure via environment; see .env.example and pytest.ini (e.g., PE_QUIET=1, OUTPUT_DIR).
	•	IBKR Client Portal flows require CP_REFRESH_TOKEN exported.
	•	Never commit secrets or local data (tokens, CSV/exports). Keep .gitignore updated.
	•	Recommended checks:
	•	Secret scanning: gitleaks locally/CI.
	•	Dependency CVEs: pip-audit (Python envs) and osv-scanner (lockfiles/SBOMs).

⸻

6) Commit & PR Discipline
	•	Commits: concise, imperative subject (e.g., Add option chain helper) + brief rationale for behavior changes.
	•	PRs: clear description, linked issues, minimal diff, and local test steps (commands + expected output). Include CLI logs/screenshots when useful.
	•	Meta: when merging notable changes, add a decision and a changelog entry.

⸻

7) CI/CD (template)

Minimal workflow gate (lint → tests → memory → security):

name: ci
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install
        run: |
          python -m pip install -U pip
          pip install -r requirements.txt
      - name: Lint
        run: ruff check .
      - name: Tests
        run: pytest -q
      - name: Memory validate & digest
        run: |
          python -m portfolio_exporter.scripts.memory validate
          python -m portfolio_exporter.scripts.memory digest | tee memory_digest.txt
      - name: Upload memory digest
        uses: actions/upload-artifact@v4
        with:
          name: memory-digest
          path: memory_digest.txt
      - name: Security (optional)
        run: |
          pip install pip-audit
          pip-audit || true  # report only

Team policy can upgrade this to fail on CVEs and integrate gitleaks/osv-scanner as needed.

⸻

8) Assistant Bootstrapping (for Codex/Cloud)

On session start, agents must run:

python -m portfolio_exporter.scripts.memory bootstrap

This ensures memory exists, logs session_start, and prints concise context (preferences, workflows, open tasks/questions, decision counts).

When making changes:
	•	After notable edits → memory add-decision … and memory changelog ….
	•	Before proposing PRs → make memory-validate and include make memory-digest output.

Micro‑MOMO notes
- v1 CSV-only is deterministic and offline; use the Makefile target above.
- v1.1 adds `--data-mode/--providers/--offline/--halts-source`. In CI/offline, prefer `--data-mode csv-only` or `--offline` to avoid network calls.

Prompt recipes (examples):
	•	Task intake → memory add-task "Refactor exporter" --labels infra --priority 2.
	•	Status update → memory update-task 7 --status in_progress --append --details "Split writer".
	•	Close task → memory close-task 7 --reason "merged".
	•	Rotate logs → memory rotate --cutoff 45d.

⸻

9) Troubleshooting
	•	MEMORY_READONLY=1 set? Writes are skipped with a note; unset to enable writes.
	•	Validation errors? Run make memory-validate to see schema issues; fix keys/ordering and retry.
	•	Concurrent writes? The command retries using a lockfile and atomic replace; re‑run if interrupted mid‑write.
	•	Slow CLI startup? Check for heavy imports in package __init__ or global network calls.

⸻

10) Doc Control
	•	Keep this file concise and actionable. Link out to deeper docs in /docs/ where needed.
	•	Propose edits via PR with example commands and, where applicable, updated make targets.

— End —
