# PSD

## Quickstart
- `make setup` provisions the Python environment and installs PSD into `.venv`.
- `make web-build` compiles the SPA into `apps/web/dist`, which the API serves at `/psd`.
- `PSD_SNAPSHOT_FN=portfolio_exporter.psd_adapter:snapshot_once python -m psd.ingestor.main` seeds the store with demo snapshots; swap the callable for live data.
- In another shell, start the API with `uvicorn apps.api.main:app --host 0.0.0.0 --port 8000`.
- Visit `http://127.0.0.1:8000/psd` to confirm the dashboard renders and streams updates over SSE.

## Data Flow
- The ingestor resolves `PSD_SNAPSHOT_FN`, persists each snapshot via `psd.core.store`, and emits ledger events for diffs.
- `psd.sentinel` and analytics consumers read from the same store, enriching risk state and publishing breach events.
- `apps.api.main` exposes REST endpoints, mounts the SPA assets from `apps/web/dist`, and delegates SSE to `psd.web.app`.
- The SPA hydrates from `/state`, listens to `/stream`, and issues targeted REST calls for rules, combos, and metrics.

## API Surfaces
- `GET /psd` returns the compiled dashboard; other static assets flow from `apps/web/dist`.
- `GET /stream` emits server-sent events (bootstrap snapshot, then diffs and breaches) for the UI and automation hooks.
- `GET /sse` streams lightweight events (currently `msb.update`) with heartbeats for automation consumers.
- `GET /state`, `/positions/stocks`, `/positions/options`, and `/session` return normalized portfolio state.
- `GET /rules/summary`, `/rules/catalog`, and `/metrics` surface sentinel findings and Prometheus counters.
- `GET /msb/current` and `/msb/history?days=N` expose the Market Stress Barometer as JSON for dashboards and scripts.
- `POST /msb/broadcast` triggers an `msb.update` SSE when the latest reading is available (used by the `msb_emit` CLI).
- Standard FastAPI metadata endpoints (`/docs`, `/openapi.json`) remain available for interactive exploration.

## Testing
- Use `psd.web.app.create_app(Settings(test_mode=True, disable_background=True))` when exercising the API in tests to avoid background tasks and long-lived loops. The CLI `scripts/msb_emit.py` calls the live server at `/msb/broadcast`, so ensure the API is running locally (default `http://127.0.0.1:51127`).

## Troubleshooting
- Port conflicts on 8000 → override with `uvicorn apps.api.main:app --port 8080` or adjust reverse-proxy upstreams.
- Blank dashboard → rebuild assets (`make web-build`) and confirm `apps/web/dist/index.html` exists.
- SSE stalls → verify `PSD_SNAPSHOT_FN` resolves quickly, confirm `PSD_HEARTBEAT_S` is sane, and ensure proxies disable buffering.
- Unexpected reconnects → inspect browser console for `EventSource` errors and check gateway idle timeouts or TLS termination.
