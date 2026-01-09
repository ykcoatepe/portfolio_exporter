# PSD

## Quickstart
- `make setup` provisions the Python environment and installs PSD into `.venv`.
- `make web-build` compiles the SPA into `apps/web/dist`, which the API serves at `/psd`.
- `PSD_SNAPSHOT_FN=portfolio_exporter.psd_adapter:snapshot_once python -m psd.ingestor.main` seeds the store with demo snapshots; swap the callable for live data.
- Preferred entrypoint: `python main.py` (or `make run`) → choose **Portfolio Sentinel**.
- Ops-only: `uvicorn --factory psd.web.server:make_app --host 0.0.0.0 --port 51127`.
- Visit `http://127.0.0.1:51127/psd` to confirm the dashboard renders and streams updates over SSE.

## Data Flow
- The ingestor resolves `PSD_SNAPSHOT_FN`, persists each snapshot via `psd.core.store`, and emits ledger events for diffs.
- `psd.sentinel` and analytics consumers read from the same store, enriching risk state and publishing breach events.
- `psd.web.server` exposes REST endpoints, mounts the SPA assets from `apps/web/dist`, and delegates SSE to `psd.web.app`.
- The SPA hydrates from `/state`, listens to `/stream`, and issues targeted REST calls for rules, combos, and metrics.
- A daily MSB scheduler runs on Turkey business days at 17:30 (Europe/Istanbul), loading vendor CSVs, persisting the latest reading exactly once per date, emitting `sentinel.alert` SSE frames, and refreshing the Live Status Bar hedge CSV.

## MSB
- Endpoints: `/msb/current`, `/msb/history?days=365`, `/msb/history.csv`, `/msb/history.parquet`, `/sse` (`event: "msb.update"`).
- Scheduler: 17:30 TRT business-days, idempotent (skips writes when today already exists).
- Metrics: `psd_msb_scheduler_runs_total`, `psd_msb_alerts_total{rule}`, `psd_livebar_rows_total`.

## API Surfaces
- `GET /psd` returns the compiled dashboard; other static assets flow from `apps/web/dist`.
- `GET /stream` emits server-sent events (bootstrap snapshot, then diffs and breaches) for the UI and automation hooks.
- `GET /sse` streams lightweight events (`msb.update`, `psd.stats.update`) with heartbeats for automation consumers.
- `GET /state` returns the normalized portfolio state (preferred).
- `GET /positions/legs` and `/positions/combos` are lightweight legacy helpers.
- `GET /positions/options` is a compatibility stub (returns empty arrays when no option data is present).
- `GET /stats/current` returns the last-good portfolio stats regardless of trading session; append `?fresh_within_sec=N` to require freshness in seconds.
- `GET /rules/summary`, `/rules/catalog`, and `/metrics` surface sentinel findings and Prometheus counters.
- `GET /msb/current` and `/msb/history?days=N` expose the Market Stress Barometer as JSON for dashboards and scripts.
- `POST /msb/broadcast` triggers an `msb.update` SSE when the latest reading is available (used by the `msb_emit` CLI).
- `/metrics` exports Prometheus counters including `psd_msb_scheduler_runs_total`, `psd_msb_alerts_total{rule}`, `psd_livebar_rows_total`, `psd_stats_startup_broadcasts_total`, and `psd_stats_broadcasts_total{trigger}` for observability of the MSB pipeline.
- Standard FastAPI metadata endpoints (`/docs`, `/openapi.json`) remain available for interactive exploration.

## MSB Scheduler & Live Bar
- Vendor inputs are read from `data/vendor/hy.csv`, `vx1.csv`, `vx2.csv`, and optional `spx_ret.csv`; missing SPX input simply skips Rule A evaluations.
- Live hedges are mirrored in `data/live_status_bar.csv` with columns `Hedge, Cost % NAV, Status, Expiry, Trigger, TriggerTimeTRT, Notes`. Rule defaults (A/B staged spreads, C beta reduction) are appended, and existing LIVE rows dedupe with the note “already hedged; maintain size”.
- Trigger the same workflow manually via `make msb-run-now`, which reuses the evaluation and Live Status Bar update logic without waiting for the 17:30 TRT window.
- Configure HY source via `MSB_SOURCE`: default `vendor`, optional `fred`, `ibkr`, or `yf`. When set to `fred`, provide `FRED_API_KEY` to refresh `data/vendor/hy.csv` (offline/test modes skip the download).

## Testing
- Use `psd.web.app.create_app(Settings(test_mode=True, disable_background=True))` when exercising the API in tests to avoid background tasks and long-lived loops. The CLI `scripts/msb_emit.py` calls the live server at `/msb/broadcast`, so ensure the API is running locally (default `http://127.0.0.1:51127`).

## Troubleshooting
- Port conflicts on 51127 → override with `uvicorn --factory psd.web.server:make_app --port 8080` or adjust reverse-proxy upstreams.
- Blank dashboard → rebuild assets (`make web-build`) and confirm `apps/web/dist/index.html` exists.
- SSE stalls → verify `PSD_SNAPSHOT_FN` resolves quickly, confirm `PSD_HEARTBEAT_S` is sane, and ensure proxies disable buffering.
- Unexpected reconnects → inspect browser console for `EventSource` errors and check gateway idle timeouts or TLS termination.
