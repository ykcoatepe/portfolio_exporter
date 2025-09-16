# Portfolio Sentinel Dashboard (PSD)

- Quickstart: run `make psd-run` to print the scaffold message.
- Structure/Naming: sources live under `src/psd/**` (modules use snake_case; packages have `__init__.py` and a README.md placeholder).
- Dev Commands: use `make psd-*` targets (`psd-run`, `psd-scan-once`, `psd-dash`) and `make sanity-fast` for a quick Ruff+pytest pass.
- CI Gate: keep lint clean (ruff returns 0) and tests green before PR. No network I/O in tests.
- Troubleshooting: IBKR/YF credentials are not required for this scaffold; if later needed, ensure env is configured and clear caches (`.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`) when in doubt.
- Access: Menu → Portfolio Sentinel → opens the live dashboard. Auto-start runs once per session (web + browser + loop). Disable via `psd.auto.start_on_menu: false`.

## Browser

- Menu-only UX: there is no public CLI for PSD. Use the menu’s `o = Open in browser` action to start on demand when auto-start is disabled.
- Ops: for systemd/launchd, invoke `python scripts/psd_start.py`.
- Configure defaults under `config/rules.yaml` → `psd.auto`.

## Pluggable Hooks

- `PSD_SNAPSHOT_FN` and `PSD_RULES_FN` accept dotted callables like `pkg.module:func`; values load via `importlib.import_module`, which returns the requested module even for nested paths.
- Override them per-process (e.g. exporting env vars before `make psd-up`) to attach custom data sources or rule evaluators without editing the core entrypoints.
- Keep adapters side-effect free at import time so ingestion and scans stay snappy.

## Observability

- Prometheus metrics are exposed at `http://localhost:51127/metrics` when `make psd-up` is running.
- Highlights: ingest timing histogram (`psd_ingest_tick_seconds`), last-refresh age gauge (`psd_data_age_seconds`), event counters (`psd_events_total`, `psd_stream_events_total`), and active SSE clients gauge (`psd_stream_clients`).

> **SSE Troubleshooting:** If events appear in bursts, check proxy buffering or ensure `X-Accel-Buffering: no` is not ignored by `proxy_ignore_headers`.

## WAL FAQ

SQLite runs PSD in write-ahead logging mode, so expect a companion `psd.db-wal` file to appear next to the main database while ingestion is active. The WAL lets background writers avoid blocking live readers. SQLite checkpoints fold those pages back into the main file from time to time, so seeing the `-wal` file grow and then shrink again is normal.

## Prod Cutover

- Reverse proxy: use the `docs/nginx.sse.conf` snippet - `location /stream` disables proxy buffering and NGINX honors PSD's `X-Accel-Buffering: no` header so SSE frames flush immediately.
- Process model: run "gunicorn -k uvicorn.workers.UvicornWorker psd.web.server:make_app --bind 0.0.0.0:51127 --workers 2 --timeout 0" (Procfile entry mirrors this). See the [FastAPI deployment guide](https://fastapi.tiangolo.com/deployment/server-workers/) for tuning guidance.
- Readiness: `/ready` returns `200` only when a snapshot exists and `data_age_s <= PSD_READY_MAX_AGE` (default 15s, override via env). Otherwise it returns `503` with a JSON `reason`.
- References: [SSE framing & Last-Event-ID](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format) / [FastAPI lifespan contract](https://fastapi.tiangolo.com/advanced/events/)
