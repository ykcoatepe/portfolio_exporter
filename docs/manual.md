# Repo Manual (stub)

## Market Stress Barometer Rule (MSB)

**Purpose.** Detect early market stress by combining credit risk (HY-OAS) with short-term vol pressure (VIX term structure). Drive timely hedges before panic is obvious.

**Inputs & Sources.**
- HY-OAS: ICE BofA US High Yield OAS (daily close). Pulled nightly; cached to `data/vendor/hy.csv`.
- VIX futures: VX1 (front) & VX2 (next) closes. From IBKR/YF; cached under `data/vendor/`.
- Optional SPX daily return for Rule A.
- Licensing: vendor CSVs are cached locally and **not** committed.

**Data Hygiene.**
- Business-day index (B). Forward-fill gaps ≤2B.
- Winsorize HY per rolling window to [1st, 99th] percentile; log clipped counts.
- Primary window **252B**; fallback **63B** if data sparse.

**Metrics.**
- HY z-score: `z_hy = (HY - μ_252B) / σ_252B` (fallback 63B for early window).
- Term structure (three views):
  - Ratio: `term_ratio = (VX1 / VX2) − 1`.
  - Calendar %: `(VX1 − VX2) / VX2`.
  - Calendar abs: `VX1 − VX2`.
- Saturation flag: when VX1 ≥ 40, `term_ratio` ~flat (|Δ|<0.005), but abs spread ↑.

**Scoring (0–100).**
- HY score (0–50): runtime-calibrated so `q50→25`, `q90→80`, `q99→95`; fallback linear `12*z_hy + 25`; clamp [0,50].
- VIX score (0–50): max of calibrated ratio% and abs tracks; +3 if saturated; clamp [0,50].
- MSB = HY score + VIX score (0–100).
- Colors: 0–29 **Green**, 30–49 **Yellow**, 50–69 **Orange**, 70–100 **Red**.
- Sanity check: 2020/2022 replays should reach ≥80 (Red) and calm periods sit near 20–35.

**Triggers & Actions.**
- **Rule A — VIX Backwardation Probe.** Condition: `VX1 > VX2` **and** SPX daily return < 0.
  - Action: Stage **VIX 25/35 call spread (2–6w)**, cost **0.10–0.35% NAV**.
- **Rule B — HY Shock.** Condition: HY-OAS **+25 bps d/d** or **+60 bps in 5B**.
  - Action: Add downside hedge (e.g., **SPX/IWM put spread 2–4w**, cost **0.15–0.40% NAV**).
- **Rule C — Persistent Stress.** Condition: **MSB ≥ 60** for **3 consecutive B-days**.
  - Action: Reduce equity beta **−20–40%** and increase delta hedge.
  - **Cooldown:** Do **not** re-fire C for **5 B-days** after first trigger.

**Cadence & Plumbing.**
- Schedule: **daily 17:30 TRT** via paced scheduler.
- Persist: last row stored in SQLite `msb_readings`; history export at `/msb/history(.csv)`.
- Live update: SSE `msb.update` to UI & tools.
- Live Status Bar: append/update a hedge row with columns `Hedge | Cost % NAV | Status | Expiry | Trigger | TriggerTimeTRT | Notes`.

**Operator Checklist (daily).**
1) Check vendor CSV freshness; if missing, backfill and rerun `make msb-run-now`.
2) Confirm `/metrics` counters advanced: `psd_msb_scheduler_runs_total`, `psd_msb_alerts_total{rule}`.
3) If **Rule C** fired and **within cooldown**, **do not** restage; update notes instead.
4) Ensure Live Status Bar shows the staged hedge row; set `Status` to LIVE only after execution.
5) Export `/msb/history.csv` (attach to journal if any triggers fired).

**Rollback.**
- Disable feature with `PSD_MSB=0` (hides API/UI; scheduler stops).
- Remove staged hedge rows from Live Bar if rule withdrawn.

**KPIs & Gates.**
- Compute p95 < **50 ms** for ~1k points; SSE payload < **1 KiB**.
- CI gates: SPA build present; UI unit tests pass; memory digest < **800 tokens**; gitleaks/osv clean.

## Portfolio Sentinel

**Startup.**
- `PSD_API_STARTUP_TIMEOUT_S` controls how long the launcher waits for the API to bind
  (default 20s). Increase it if the API needs more time to initialize.
