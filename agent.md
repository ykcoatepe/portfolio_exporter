# Portfolio Sentinel Dashboard (PSD)

- Quickstart: run `make psd-run` to print the scaffold message.
- Ops Menu: `make run-menu` opens the PSD Ops Menu (Rich TUI, no manual CLI needed).
- Structure/Naming: sources live under `src/psd/**` (modules use snake_case; packages have `__init__.py` and a README.md placeholder).
- Dev Commands: use `make psd-*` targets (`psd-run`, `psd-scan-once`, `psd-dash`) and `make sanity-fast` for a quick Ruff+pytest pass.
- CI Gate: keep lint clean (ruff returns 0) and tests green before PR. No network I/O in tests.
- Troubleshooting: IBKR/YF credentials are not required for this scaffold; if later needed, ensure env is configured and clear caches (`.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`) when in doubt.
- Access: Menu → Portfolio Sentinel → opens the live dashboard. Auto-start runs once per session (web + browser + loop). Disable via `psd.auto.start_on_menu: false`.

## Using the PSD Ops Menu

The menu orchestrates the whole live PSD stack without manual commands.

**Start (recommended)**
1. Ensure env is set (see `.env.example`): `PSD_SNAPSHOT_FN`, `PSD_RULES_FN`, `IB_HOST/IB_PORT/IB_CLIENT_ID` (unique per process), optional `PSD_PORT`.
2. Run `make run-menu` and press **4** "Start PSD".
3. Your browser opens `http://127.0.0.1:<port>`; logs stream to `run/*.log`.

**Other actions**
- **1 Status** - shows PIDs and running state.
- **2 Stop PSD** - graceful shutdown (SIGINT->SIGTERM->SIGKILL), cleans the PID file when all stopped.
- **3 Open Dashboard** - re-opens the dashboard using the saved or default port.

**Where things live**
- PID file: `run/psd-pids.json`
- Logs: `run/ingestor.log`, `run/scanner.log`, `run/web.log`

**Notes**
- Idempotent start: already-running services aren't duplicated.
- If the dashboard looks stale, check `/metrics` and `run/*.log`.
- Behind NGINX, disable buffering on `/stream` (see `docs/nginx.sse.conf`).

## Browser

- Menu-only UX: there is no public CLI for PSD. Use the menu’s `o = Open in browser` action to start on demand when auto-start is disabled.
- Ops: for systemd/launchd, invoke `python scripts/psd_start.py`.
- Configure defaults under `config/rules.yaml` → `psd.auto`.

## Pluggable Hooks

- `PSD_SNAPSHOT_FN` and `PSD_RULES_FN` accept dotted callables like `pkg.module:func`; values load via `importlib.import_module`, which returns the requested module even for nested paths.
- Override them per-process (e.g. exporting env vars before `make psd-up`) to attach custom data sources or rule evaluators without editing the core entrypoints.
- Keep adapters side-effect free at import time so ingestion and scans stay snappy.

### Environment checklist

Set these before launching PSD locally or in production:
- `PSD_SNAPSHOT_FN=portfolio_exporter.psd_adapter:snapshot_once`
- `PSD_RULES_FN=portfolio_exporter.psd_rules:evaluate`
- `IB_HOST=127.0.0.1` and `IB_PORT=7497` (override if you map Gateway to 4001/4002)
- `IB_CLIENT_ID=<unique>` per process/tool to avoid TWS collisions
- Optional: `PSD_HEARTBEAT_S=2.0` to keep the ingestor loop cadence explicit
- Leave `PSD_SSE_TEST_MODE` unset outside of tests; labs toggle it to fake SSE frames

## Observability

- Prometheus metrics are exposed at `http://localhost:51127/metrics` when `make psd-up` is running.
- Highlights: ingest timing histogram (`psd_ingest_tick_seconds`), last-refresh age gauge (`psd_data_age_seconds`), event counters (`psd_events_total`, `psd_stream_events_total`), and active SSE clients gauge (`psd_stream_clients`).

> **SSE Troubleshooting:** If events appear in bursts, check proxy buffering or ensure `X-Accel-Buffering: no` is not ignored by `proxy_ignore_headers`.

## WAL FAQ

SQLite runs PSD in write-ahead logging mode, so expect a companion `psd.db-wal` file to appear next to the main database while ingestion is active. The WAL lets background writers avoid blocking live readers. SQLite checkpoints fold those pages back into the main file from time to time, so seeing the `-wal` file grow and then shrink again is normal.

## Prod Cutover

- Reverse proxy: use the `docs/nginx.sse.conf` snippet - `location /stream` disables proxy buffering and NGINX honors PSD's `X-Accel-Buffering: no` header so SSE frames flush immediately.
- Process model: run "gunicorn -k uvicorn.workers.UvicornWorker psd.web.server:make_app --bind 0.0.0.0:51127 --workers 2 --timeout 0" (Procfile entry mirrors this). See the [FastAPI deployment guide](https://fastapi.tiangolo.com/deployment/server-workers/) for tuning guidance.
- Readiness: `/ready` returns JSON `{ "ok": true, "data_age_s": <float>, "threshold_s": <float> }` when a snapshot exists and the latest health row is fresher than `PSD_READY_MAX_AGE` (default 15s, override via env). Stale or missing data responds `503` with `{ "ok": false, "reason": "...", "data_age_s": <float|null> }` for load balancer gating.
- References: [SSE framing & Last-Event-ID](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format) / [FastAPI lifespan contract](https://fastapi.tiangolo.com/advanced/events/)

## SSE Latency Check

- Local guard: `make sse-check URL=http://127.0.0.1:51127/stream THRESH=3` runs `tools/check_sse.sh` and passes when the median inter-arrival is below the threshold (seconds).
- CI smoke: `.github/workflows/psd-smoke.yml` runs the same script against `${{ secrets.PSD_SSE_URL }}` via `workflow_dispatch` for staging checks.
