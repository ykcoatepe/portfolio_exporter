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

### 2026-01-12 • Task: MSB config knobs + IB datasource + edge-case tests • Branch: local
**Owner:** codex

**Scope:** MSBConfig defaults, calendar/ffill policy, Rule B raw deltas w/ clip guard, IBKR VX/SPX refresh with fallback, msb_refresh CLI, scheduler auto-refresh, new unit tests, docs/msb.md refresh.

**Key files:** src/psd/analytics/msb.py, src/psd/datasources/msb_vendor.py, src/psd/sentinel/sched.py, scripts/msb_compute.py, scripts/msb_refresh.py, tests/test_msb_compute.py, tests/test_msb_vendor_refresh.py, docs/manual.md, docs/msb.md

**Interfaces:** MSB compute CLI, MSB analytics

**Status:** open

**Next:** run make lint && make test; confirm calibration golden expectations.

**Notes:** legacy behavior available via MSBConfig.legacy() or CLI flags.

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

### 2026-01-09 • Task: Powerlaw stale lag allowance • Branch: local
**Owner:** session/ai | **Scope:** allow 1 trading-day lag for Powerlaw staleness; update tests
**Interfaces:** /state
**Status:** open
**Notes:** pytest -q tests/test_psd_powerlaw.py

### 2026-01-09 • Task: Default PSD stocks grid to sortable table • Branch: local
**Owner:** session/ai | **Scope:** default PSD stocks grid to the new sortable data grid
**Interfaces:** none
**Status:** open
**Notes:** fallback grid mode now returns "new"; query/localStorage/env overrides still apply

### 2026-01-09 • Task: Remove legacy PSD stocks grid path • Branch: local
**Owner:** session/ai | **Scope:** always render PsdStocksGrid for Single Stocks when positions_view exists
**Interfaces:** none
**Status:** open
**Notes:** removed grid mode branching/parity/legacy table in StocksSectionWithGrid

### 2026-01-09 • Task: PSD options singles grid sorting • Branch: local
**Owner:** session/ai | **Scope:** render PsdOptionLegsGrid for Options — Singles with sortable headers
**Interfaces:** none
**Status:** open
**Notes:** added PSD option-leg columns + sorting state; map option labels via buildFriendlyLegDisplay

### 2026-01-09 • Task: Portfolio stats alignment • Branch: local
**Owner:** session/ai | **Scope:** prefer snapshot-derived metrics for Day/Unrealized P&L and greeks; keep stats for risk fields
**Interfaces:** /stats/current, /state
**Status:** open
**Notes:** staleness now reflects max of snapshot + stats sources

### 2026-01-12 • Task: Restore intraday P&L fallbacks • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** keep non-option day P&L populated when broker omits day_pnl fields
**Interfaces:** src/psd/ingestor/normalize.py
**Status:** open
**Notes:** restored pnl_leg/prev_close/value fallback order; web unit tests currently failing (PSD tab order, PsdDataGrid selection test timeout); per user request, tests not rerun

### 2026-01-12 • Task: Fix PSD options singles symbol sorting freeze • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** make options singles sort key safe + label-based
**Interfaces:** apps/web
**Status:** open
**Notes:** symbol header now sorts on label/symbol fallback; option-legs sorting state moved into grid to avoid full-page rerenders

### 2026-01-12 • Task: Stabilize PSD options singles sorting • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** bypass TanStack sorting for option legs and apply manual sorting
**Interfaces:** apps/web
**Status:** open
**Notes:** options singles grid now pre-sorts data for supported columns and uses manual sorting to avoid UI lockups

### 2026-01-12 • Task: Harden PSD options singles row identity • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** ensure unique option-leg row IDs and prevent sorting auto-reset loops
**Interfaces:** apps/web
**Status:** open
**Notes:** option leg ids now include expiry/right/strike fallback to avoid duplicate row IDs

### 2026-01-12 • Task: Stabilize PSD options singles sorting state • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** avoid controlled sorting loops by using internal table state and stable empty filters
**Interfaces:** apps/web
**Status:** open
**Notes:** options grid now relies on internal sorting state; default column filter array is stable per table FAQ guidance

### 2026-01-12 • Task: Normalize MSB refresh + trigger labels • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** default MSB vendor refresh + API/SSE trigger normalization
**Interfaces:** src/psd, docs
**Status:** done
**Notes:** scheduler now always attempts vendor refresh (disabled via PSD_MSB_AUTO_REFRESH=0); MSB API/SSE outputs map A/B/C triggers to RULE_* labels; docs updated

### 2026-01-12 • Task: Auto-seed MSB vendor data on PSD start • Branch: main
**Owner:** session/ai | **Scope:** seed MSB vendor CSVs before launching PSD services
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** PSD start now checks data/vendor for HY/VX1/VX2 and triggers refresh using IBKR/FRED/Yahoo fallbacks; warns when FRED_API_KEY is missing

### 2026-01-12 • Task: Fix msb-run-now Makefile helper • Branch: main
**Owner:** session/ai | **Scope:** ensure msb-run-now executes in one shell
**Interfaces:** Makefile
**Status:** done
**Notes:** replaced here-doc with python -c to avoid per-line shell execution errors in make

### 2026-01-12 • Task: Run MSB scheduler from make target • Branch: main
**Owner:** session/ai | **Scope:** compute+store MSB readings and load .env for FRED
**Interfaces:** Makefile, src/psd/sentinel/sched.py
**Status:** done
**Notes:** msb-run-now now loads .env and calls run_msb_scheduler_once; scheduler log payload key fixed to avoid duplicate status arg

### 2026-01-12 • Task: Auto MSB refresh + IBKR/Yahoo fallback update • Branch: main
**Owner:** session/ai | **Scope:** auto-refresh MSB on PSD start, add MSB refresh button, improve datasource fallbacks
**Interfaces:** src/psd/datasources/msb_vendor.py, src/psd/sentinel/sched.py, src/psd/web/app.py, apps/web/src/components/MSBActionBox.tsx, apps/web/src/lib/msb.ts
**Status:** done
**Notes:** default IBKR VIX futures root set to VIX with VX fallback; Yahoo fallback uses ^VIX/^VIX3M lists; MSB refresh endpoint + UI button added; startup triggers background MSB refresh; scheduler skips gracefully when vendor files missing

### 2026-01-13 • Task: Fix PSD ops process checks + uvicorn spawn • Branch: main
**Owner:** session/ai | **Scope:** avoid zombie PID false-positives and ensure web starts via python -m uvicorn
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** treat zombie/defunct PIDs as dead; spawn uvicorn via sys.executable to avoid exec format errors

### 2026-01-13 • Task: Make MSB refresh accept stale vendor data • Branch: main
**Owner:** session/ai | **Scope:** ensure MSB populates even when vendor data is behind today
**Interfaces:** src/psd/sentinel/sched.py, src/psd/web/app.py, apps/web/src/components/MSBActionBox.tsx, apps/web/src/lib/msb.ts, src/psd/datasources/msb_vendor.py, Makefile
**Status:** done
**Notes:** refresh endpoint + startup refresh now force vendor refresh and accept latest available date; MSB refresh UI shows skip status; IBKR MSB vendor defaults to useRTH=False

### 2026-01-13 • Task: Add MSB status badge + status API • Branch: main
**Owner:** session/ai | **Scope:** show MSB refresh status + last date on dashboard
**Interfaces:** src/psd/web/app.py, apps/web/src/components/MSBCard.tsx, apps/web/src/hooks/useMsbStatus.ts, apps/web/src/lib/msb.ts, apps/web/src/lib/types.ts
**Status:** done
**Notes:** new /msb/status endpoint stores last refresh state; UI badge shows status and last MSB date

### 2026-01-13 • Task: Backfill MSB history from vendor data • Branch: main
**Owner:** session/ai | **Scope:** populate MSB history on first successful refresh
**Interfaces:** src/psd/sentinel/sched.py, tests/test_msb_scheduler_once.py
**Status:** done
**Notes:** when no MSB rows exist, scheduler now stores full vendor history instead of only latest row

### 2026-01-13 • Task: Backfill MSB when only one row exists • Branch: main
**Owner:** session/ai | **Scope:** backfill MSB history when DB has only a single row
**Interfaces:** src/psd/sentinel/sched.py
**Status:** done
**Notes:** refresh now backfills full vendor history if history has <=1 row and vendor data has more

### 2026-01-13 • Task: Drop null MSB rows before backfill • Branch: main
**Owner:** session/ai | **Scope:** prevent DB constraint errors during MSB backfill
**Interfaces:** src/psd/sentinel/sched.py
**Status:** done
**Notes:** backfill now drops rows missing hy/vx1/vx2 to avoid NOT NULL violations

### 2026-01-13 • Task: Fix MSB help loading • Branch: main
**Owner:** session/ai | **Scope:** ensure MSB help tooltip can load server-side
**Interfaces:** src/psd/web/app.py
**Status:** done
**Notes:** add missing os import so /msb/help no longer 500s

### 2026-01-13 • Task: Extend MSB help definitions • Branch: main
**Owner:** session/ai | **Scope:** expand MSB tooltip to cover barometer terms and surface it on MSB card
**Interfaces:** apps/web/src/components/MSBCard.tsx, config/msb_signals_help.json, src/psd/web/app.py
**Status:** done
**Notes:** added help tooltip in MSB card header and new help section for HY/VIX scores, term ratio, cal spread, and stress bands

### 2026-01-13 • Task: Add tooltips for MSB stat cards • Branch: main
**Owner:** session/ai | **Scope:** add per-stat help for HY/VIX score, term ratio, and cal spread
**Interfaces:** apps/web/src/components/MSBCard.tsx, apps/web/src/lib/msb.ts, apps/web/src/lib/types.ts, config/msb_signals_help.json, src/psd/web/app.py
**Status:** done
**Notes:** added optional terms metadata for MSB help and rendered hover tooltips on each stat label

### 2026-01-13 • Task: Resolve MSB help config path • Branch: main
**Owner:** session/ai | **Scope:** ensure MSB help terms load regardless of PSD working directory
**Interfaces:** src/psd/web/app.py
**Status:** done
**Notes:** resolve msb_signals_help.json relative to repo root when relative path not found

### 2026-01-13 • Task: Add MSB chart style alternates • Branch: main
**Owner:** session/ai | **Scope:** improve MSB mini chart readability with focus vs range views
**Interfaces:** apps/web/src/components/MSBMiniCharts.tsx
**Status:** done
**Notes:** added style toggle, latest/1D/range labels, median and baseline reference lines, and last-point markers

### 2026-01-13 • Task: Add main flow diagrams • Branch: main
**Owner:** session/ai | **Scope:** document main.py menu + task flows with Mermaid + SVG renders
**Interfaces:** docs/diagrams/main_menu_flow.mmd, docs/diagrams/main_menu_flow.svg, docs/diagrams/main_tasks_flow.mmd, docs/diagrams/main_tasks_flow.svg
**Status:** done
**Notes:** added two flowcharts (menu + tasks) and generated SVG renders

### 2026-01-13 • Task: Create MSB chart mockups • Branch: main
**Owner:** session/ai | **Scope:** static PSD-themed mockups for MSB chart readability options
**Interfaces:** docs/mockups/index.html, docs/mockups/msb_option_a.html, docs/mockups/msb_option_b.html, docs/mockups/msb_option_f.html
**Status:** done
**Notes:** generated static HTML previews for options A, B, and F without touching PSD code

### 2026-01-13 • Task: Embed flow diagrams in README • Branch: main
**Owner:** session/ai | **Scope:** document main.py flows in README
**Interfaces:** README.md
**Status:** done
**Notes:** embedded menu and task flow SVGs in README

### 2026-01-13 • Task: Implement MSB mini charts (Option A) • Branch: main
**Owner:** session/ai | **Scope:** add key value + delta + range layout for MSB mini charts and remove mockups
**Interfaces:** apps/web/src/components/MSBMiniCharts.tsx
**Status:** done
**Notes:** shows last value, 1D delta, range, and last-point marker for HY-OAS and VX1/VX2; removed docs/mockups

### 2026-01-13 • Task: Powerlaw info bundles + data quality fixes • Branch: main
**Owner:** session/ai | **Scope:** add Powerlaw help bundles in PSD UI, load help from powerlaw repo, and populate data_quality details
**Interfaces:** apps/web/src/components/PowerlawPanel.tsx, apps/web/src/lib/powerlaw.ts, apps/web/src/hooks/usePowerlawSignalsHelp.ts, src/psd/web/app.py, portfolio_exporter/psd_powerlaw.py, ../codeforge-powerlaw-trader/scripts/run_trader_v5_daily.py, ../codeforge-powerlaw-trader/docs/powerlaw_signals_help.json
**Status:** done
**Notes:** added /powerlaw/help endpoint + UI tooltips; data_quality now emits OK/WARN with detail list; tests updated

### 2026-01-13 • Task: Stabilize PSD unit tests • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** align PSD tests with data grid structure and MSB actions focus order
**Interfaces:** apps/web/src/pages/PSD.test.tsx
**Status:** done
**Notes:** reset psd ui state in tests, updated grid row assertions, and accounted for Refresh MSB in tab order

### 2026-01-13 • Task: Fix PSD menu dashboard launch • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** ensure PSD menu opens the React UI by detecting dev server and building dist when missing
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** auto-detect Vite dev server, build apps/web bundle with bun if needed, then open /psd

### 2026-01-13 • Task: PSD menu starts UI + backend • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** start UI dev server (optional) and ensure uvicorn deps when launching PSD from menu 4
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** menu 4 now installs uvicorn deps if missing, starts UI dev server when PSD_DEV_MODE=1, waits for web port before opening

### 2026-01-13 • Task: PSD menu dev/user modes • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** add explicit dev/user mode choices for PSD startup
**Interfaces:** portfolio_exporter/menus/psd.py, src/psd/menus/ops.py
**Status:** done
**Notes:** menu 4 now prompts for dev vs user mode; ops menu shows separate start options

### 2026-01-13 • Task: Keep PSD services alive • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** detach PSD child processes to prevent SIGINT shutdowns
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** start PSD services in a new session so uvicorn doesn't exit on parent terminal interrupts

### 2026-01-13 • Task: Restart PSD web when port closed • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** ensure menu start restarts web if PID is stale but port is closed
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** detect alive-but-closed web process and respawn before opening dashboard

### 2026-01-13 • Task: Wait before opening PSD dashboard • Branch: main
**Owner:** session/ai | **Scope:** avoid opening browser until PSD web is responsive in user mode
**Interfaces:** portfolio_exporter/menus/psd.py, src/psd/menus/ops.py
**Status:** done
**Notes:** start PSD without auto-opening, then wait for port and open or print manual URL

### 2026-01-13 • Task: Anchor PSD runtime paths to repo root • Branch: main
**Owner:** session/ai | **Scope:** make PSD menu resilient to non-repo CWD when launching services
**Interfaces:** src/psd/menus/ops.py
**Status:** done
**Notes:** resolve run dir and vendor data from repo root, set PYTHONPATH to include src, and spawn services from repo root

### 2026-01-13 • Task: Powerlaw info bundles + data quality fallback • Branch: feature/psd-powerlaw
**Owner:** session/ai | **Scope:** surface Powerlaw help tooltips and avoid N/A data quality labels
**Interfaces:** apps/web/src/lib/queryPersistence.ts, portfolio_exporter/psd_powerlaw.py, ../codeforge-powerlaw-trader/docs/powerlaw_signals_help.json
**Status:** done
**Notes:** added powerlaw help JSON in powerlaw repo, default data_quality based on staleness, cast QueryClient for persistence typing, rebuilt apps/web bundle

### 2026-01-13 • Task: Populate PSD single option greeks from flat fields • Branch: fix/psd-single-greeks
**Owner:** session/ai | **Scope:** ensure PSD single option greeks show when upstream data uses flat delta/gamma/theta/vega fields
**Interfaces:** src/psd/ingestor/normalize.py, tests/tests_positions_norm.py
**Status:** done
**Notes:** fill greeks from flat fields during normalization and add coverage

### 2026-01-13 • Task: Flag missing greeks in Options — Singles • Branch: fix/psd-single-greeks
**Owner:** session/ai | **Scope:** surface a PSD data-quality chip when delta/gamma/theta are missing for option legs
**Interfaces:** apps/web/src/pages/PSD.tsx, apps/web/src/pages/PSD.test.tsx
**Status:** done
**Notes:** added greeks-missing chip and test assertion

### 2026-01-13 • Task: Aggregate combos greeks and P&L from legs • Branch: fix/psd-single-greeks
**Owner:** session/ai | **Scope:** compute combo greeks and P&L summaries from component legs when portfolio has no combo aggregates
**Interfaces:** src/psd/ingestor/normalize.py, apps/web/src/pages/PSD.tsx, tests/tests_positions_norm.py
**Status:** done
**Notes:** aggregate leg greeks (delta/gamma/theta/vega), sum day/total P&L with percent bases; add missing-greeks chip for combos

### 2026-01-13 • Task: Speed up local test loop with tiers • Branch: fix/psd-single-greeks
**Owner:** session/codex | **Scope:** add pytest markers for cli/integration/slow, add test-fast/test-parallel targets, add pytest-xdist
**Interfaces:** Makefile, pytest.ini, tests/*, requirements-dev.*, README.md
**Status:** done
**Notes:** fast suite skips cli/integration/slow; full suite unchanged
