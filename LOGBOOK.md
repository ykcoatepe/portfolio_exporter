# 2025-09-14 • Task: PSD v0.1 implemented • Branch: feature/psd-sentinel-v0
Owner: codex (session/codex)
Scope: scan_once, memos JSONL, CLI table, rules & tests
Key files: src/psd/**, config/rules.yaml, scripts/run_sentinel.py, tests/test_*
Status: merged @ v0.1 scaffold → implementation

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
