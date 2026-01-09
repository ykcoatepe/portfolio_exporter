# 2025-09-14 • Task: PSD v0.1 implemented • Branch: feature/psd-sentinel-v0
Owner: codex (session/codex)
Scope: scan_once, memos JSONL, CLI table, rules & tests
Key files: src/psd/**, config/rules.yaml, scripts/run_sentinel.py, tests/test_*
Status: merged @ v0.1 scaffold → implementation

# 2025-10-23 • Task: MSB sentinel scheduler & live bar • Branch: feature/msb-api-sse-v1
Owner: codex (session/ai)
Scope: TRT 17:30 scheduler, Rule A/B/C evaluation w/ cooldown, SSE alerts, live hedge CSV, Prometheus metrics, docs/tests
Key files: src/psd/sentinel/sched.py, src/psd/sentinel/msb_actions.py, src/psd/ui/livebar.py, tests/test_msb_*.py
Status: open → PR #173
Next: monitor metrics rollout, consider UI surfacing of live bar
Risks/Notes: Vendor CSV freshness gates scheduler; live bar CSV ignored by git, ensure ops collects artifacts

# 2025-09-14 • Task: Scaffold PSD (v0.1) • Branch: feature/psd-sentinel-v0
Owner: codex (session/codex)
Scope: Create structure and placeholders for PSD; no logic yet
Key files: src/psd/**, config/rules.yaml, scripts/run_sentinel.py, Makefile
Interfaces: ibkr@v1 (positions/prices), yfinance@v1 (VIX/history)
Status: open @ initial scaffold
Next: v0.1 implement scan_once + memos; CLI table
Risks/Notes: keep files ≤150 LOC; no orphan-leg logic yet

# Project Logbook

### 2025-09-13T19:28:46+03:00 • Task: micro-momo analyzer • Branch: dev_yordam2
**Owner:** codex

**Scope:** analyze+score+journal

**Key files:** portfolio_exporter/scripts/micro_momo_analyzer.py

**Interfaces:** -

**Status:** merged

**Next:** 

**Notes:** 

### 2025-09-24T05:50:52Z • Task: PSD PnL diagnostics • Branch: codex/combo-group-playbook
**Owner:** codex

**Scope:** Investigate PSD dashboard zero P&L and staleness

**Key files:** libs/py/positions_engine/ingest/internal.py, libs/py/positions_engine/service/state.py, apps/web/src/hooks/usePortfolioMetrics.ts

**Interfaces:** /state snapshot, /stats API

**Status:** open

**Next:** Confirm upstream snapshot coverage for avg_cost + timestamps

**Notes:** Capture repro scripts in debug/psd_logs.txt and document findings under debug/.

### 2025-09-24T08:48:11Z • Task: PSD PnL diagnostic • Branch: feature/psd-diagnostic
**Owner:** codex

**Scope:** Confirm PSD zero P&L and stale badge regressions; capture repro artifacts.

**Key files:** libs/py/positions_engine/ingest/internal.py, libs/py/positions_engine/service/state.py, libs/py/positions_engine/combos/detector.py, apps/web/src/hooks/usePortfolioMetrics.ts

**Interfaces:** PSD snapshot ingest, /api/psd/state, OptionLegsTable UI

**Status:** in_progress

**Next:** Draft remediation plan for avg_cost defaults, timestamp propagation, and quote backfill heuristics.

**Notes:** Evidence pack under debug/: psd_diagnose.md, psd_trace_map.md, psd_fail_repros.sh, psd_logs.txt, psd_checklist.json.

### 2025-10-23 • Task: PSD v0.1 Hardening • Branch: feature/psd-v0-1-hardening
**Owner:** session/ai

**Scope:** dataclass fix + SPA build + docs

**Interfaces:** none (non-functional changes)

**Status:** open → merged @ <sha>

**Next:** MSB feature

**Notes:** CI gate now builds SPA  |  Ref: <PR link>

### 2025-10-24 • Task: MSB docs & ops polish • Branch: docs/msb-playbook-v1
**Owner:** session/ai  |  **Scope:** manual.md rule block, agent.md quickstart, README endpoint notes, CI web-test

**Interfaces:** /msb/*, /sse, Make targets

**Status:** open → merged @ <sha>  |  **Next:** tag psd-v0.1

**Risks/Notes:** vendor CSV freshness; cooldown governance

### 2025-10-24 • Task: v0.1 Release Cut • Branch: release/psd-v0.1
**Owner:** session/ai | **Scope:** versions, changelog, gitleaks/osv gates, artifacts, tag
**Interfaces:** /msb/*, /sse
**Status:** open → tagged @ <sha> | **Next:** v0.1.1 deps bump (pypdf/vite/fast-redact)

### 2025-10-24 • Task: v0.1.1 Deps + FRED Parquet • Branch: release/v0.1.1-msb-fred-parquet-deps
**Owner:** session/ai | **Scope:** pypdf/vite bumps, FRED HY toggle, Parquet export
**Interfaces:** /msb/history(.csv|.parquet)
**Status:** open → merged @ <sha> | **Next:** monitor FRED rate limits & front-end parquet UX

### 2026-01-06 • Task: PSD dashboard API compatibility • Branch: feature/fix-psd-live-data
**Owner:** session/ai | **Scope:** options/session hooks from snapshot, /state positions_view fallback, rules catalog gating, StatsRibbon test waits
**Interfaces:** /state, /rules/summary
**Status:** open
**Risks/Notes:** rules catalog actions disabled unless VITE_RULES_CATALOG=true

### 2026-01-07 • Task: PSD stocks grid cleanup • Branch: feature/fix-psd-live-data
**Owner:** session/ai | **Scope:** drop stale delta column from PSD stocks grid; run checks

**Interfaces:** none

**Status:** open

**Notes:** pytest -q, bun run typecheck/test/build, python -m build

### 2026-01-07 • Task: PSD snapshot timestamp normalize • Branch: feature/fix-psd-live-data
**Owner:** session/ai | **Scope:** normalize /state ts for options as_of in web hook

**Interfaces:** /state

**Status:** open

### 2026-01-08 • Task: PSD entrypoint + port cleanup • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** make `python main.py` the primary PSD entrypoint, remove port 8000 docs, align Make targets to 51127

**Interfaces:** /psd, /stream, /metrics

**Status:** open

### 2026-01-08 • Task: Powerlaw wiring fix • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** fix plke_band_alpha key, add /powerlaw/refresh API route, proxy /powerlaw in Vite

**Interfaces:** /state, /powerlaw/refresh

**Status:** open

**Notes:** pytest -q tests/test_psd_powerlaw.py tests/test_psd_adapter_powerlaw.py tests/test_psd_state_powerlaw.py; cd apps/web && bun run test

### 2026-01-08 • Task: PSD API base URL fix • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** use window origin for API base to avoid /psd prefix

**Interfaces:** /state, /msb, /powerlaw

**Status:** open

**Notes:** cd apps/web && bun run test

### 2026-01-08 • Task: PSD metrics registration guard • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** reuse Prometheus collectors to avoid duplicate registry errors in pytest

**Interfaces:** /metrics

**Status:** open

**Notes:** make test (initially failed on duplicate psd_stream_clients); rerun pending full pytest

### 2026-01-08 • Task: PSD stock marks fallback • Branch: local
**Owner:** session/ai | **Scope:** enrich PSD snapshot positions with quote/YF marks so day/total P&L compute

**Interfaces:** psd_adapter.snapshot_once

**Status:** open

**Notes:** pytest -vv -k snapshot_once_roundtrip / delayed_marks / fills_missing_marks (tests/tests_psd_adapter.py)
