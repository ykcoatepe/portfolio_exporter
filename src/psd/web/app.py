from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import Counter, Gauge
from starlette.middleware.cors import CORSMiddleware

from psd.analytics.stats import compute_stats
from psd.core.store import init, latest_snapshot, max_event_id, tail_events
from psd.web.ready import router as ready_router

# Importing the ingestor module registers the psd_events_total counter so that
# /metrics exposes it even before ingestion writes events.
try:  # pragma: no cover - defensive in case optional deps change
    import psd.ingestor.main as _psd_ingestor_main  # noqa: F401
except Exception:  # pragma: no cover - metrics should still render
    _psd_ingestor_main = None

TEST_MODE = os.getenv("PSD_SSE_TEST_MODE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

log = logging.getLogger("psd.web.stats")
STALE_ALERT_THRESHOLD = 10
_DEFAULT_STATS_EMPTY = compute_stats(None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastAPI's lifespan hook is the modern place for startup/shutdown work.
    init()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ready_router)

STREAM_CLIENTS = Gauge("psd_stream_clients", "Connected SSE clients")
STREAM_EVENTS = Counter("psd_stream_events_total", "SSE events sent", ["kind"])


@app.get("/state")
def state():
    snap = latest_snapshot()
    if not snap:
        return JSONResponse({"ts": None, "positions": [], "quotes": {}, "risk": {}, "empty": True})
    return JSONResponse(snap)


@app.get("/stats")
def stats():
    snap = latest_snapshot()
    if not snap:
        payload = dict(_DEFAULT_STATS_EMPTY)
        payload.update(
            {
                "empty": True,
                "ts": None,
                "quotes_count": 0,
            }
        )
        return JSONResponse(payload)

    payload = compute_stats(snap)
    payload = dict(payload)  # ensure mutable copy
    quotes_obj = snap.get("quotes")
    payload.update(
        {
            "empty": False,
            "ts": snap.get("ts"),
            "quotes_count": len(quotes_obj) if isinstance(quotes_obj, dict) else 0,
        }
    )
    stale_count = int(payload.get("stale_quotes_count") or 0)
    if stale_count > STALE_ALERT_THRESHOLD:
        log.warning("stale_quotes_count exceeded threshold: %s", stale_count)
    return JSONResponse(payload)


# SSE stream: bootstrap snapshot (no id) followed by event/data/id frames with retry hints.
# Last-Event-ID headers resume only events with a strictly higher ledger id.
@app.get("/stream")
async def stream(request: Request):
    # Pick up from the last event the client acknowledged (if any).
    last_event_id_header = request.headers.get("last-event-id", "").strip()
    last_event_id: int | None
    try:
        last_event_id = int(last_event_id_header) if last_event_id_header else None
    except ValueError:
        last_event_id = None

    test_mode_env = os.getenv("PSD_SSE_TEST_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    test_mode = TEST_MODE or test_mode_env
    limit_ids = 0
    limit_frames = 0
    max_ms = 0.0
    idle_ms = 0.0
    if test_mode:
        q = request.query_params
        try:
            limit_ids = int(q.get("test_limit_ids", "0") or 0)
        except (TypeError, ValueError):
            limit_ids = 0
        try:
            limit_frames = int(q.get("test_limit_frames", "0") or 0)
        except (TypeError, ValueError):
            limit_frames = 0
        try:
            max_ms = float(q.get("test_max_ms", "0") or 0)
        except (TypeError, ValueError):
            max_ms = 0.0
        try:
            idle_ms = float(q.get("test_idle_ms", "0") or 0)
        except (TypeError, ValueError):
            idle_ms = 0.0
        limit_ids = max(limit_ids, 0)
        limit_frames = max(limit_frames, 0)
        max_ms = max(max_ms, 0.0)
        idle_ms = max(idle_ms, 0.0)
    ids_sent = 0
    frames_sent = 0
    t0 = time.monotonic()
    t_last = t0

    def _maybe_quit() -> bool:
        if not test_mode:
            return False
        now = time.monotonic()
        if max_ms and (now - t0) * 1000.0 >= max_ms:
            return True
        if idle_ms and (now - t_last) * 1000.0 >= idle_ms:
            return True
        if limit_ids and ids_sent >= limit_ids:
            return True
        if limit_frames and frames_sent >= limit_frames:
            return True
        return False

    async def gen():
        nonlocal ids_sent, frames_sent, t_last
        STREAM_CLIENTS.inc()
        try:
            # Suggest a retry window so browsers reconnect promptly on drops.
            yield "retry: 2000\n\n"
            frames_sent += 1
            t_last = time.monotonic()
            if _maybe_quit():
                return

            # Bootstrap snapshot without id for quick render.
            snap = latest_snapshot()
            if snap:
                STREAM_EVENTS.labels("snapshot").inc()
                yield "event: snapshot\n" + "data: " + json.dumps(snap, separators=(",", ":")) + "\n\n"
                frames_sent += 1
                t_last = time.monotonic()
                if _maybe_quit():
                    return
            last_id_local = last_event_id if last_event_id is not None else 0
            if snap and last_event_id is None:
                last_id_local = max_event_id()

            while True:
                if await request.is_disconnected():
                    break
                events = tail_events(last_id_local, 200)
                if events:
                    last_id_local = events[-1][0]
                    for event_id, kind, payload in events:
                        STREAM_EVENTS.labels(kind).inc()
                        yield (
                            f"id: {event_id}\n"
                            + f"event: {kind}\n"
                            + "data: "
                            + json.dumps(payload, separators=(",", ":"))
                            + "\n\n"
                        )
                        ids_sent += 1
                        frames_sent += 1
                        t_last = time.monotonic()
                        if _maybe_quit():
                            return
                else:
                    # keep proxies and EventSource alive
                    STREAM_EVENTS.labels("heartbeat").inc()
                    yield "event: heartbeat\n" + "data: {}\n\n"
                    frames_sent += 1
                    t_last = time.monotonic()
                    if _maybe_quit():
                        return
                    await asyncio.sleep(0.05 if test_mode else 2.0)
        finally:
            STREAM_CLIENTS.dec()

    # Hint reverse proxies not to buffer SSE frames (Cache-Control + X-Accel-Buffering cooperate).
    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@app.get("/metrics")
def metrics():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    # TODO: add authentication/allowlist for production deployments.
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
def healthz():
    return {"ok": bool(latest_snapshot())}
