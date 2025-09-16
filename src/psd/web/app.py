from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import Counter, Gauge
from starlette.middleware.cors import CORSMiddleware

from psd.core.store import init, latest_snapshot, tail_events


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

STREAM_CLIENTS = Gauge("psd_stream_clients", "Connected SSE clients")
STREAM_EVENTS = Counter(
    "psd_stream_events_total", "SSE events sent", ["kind"]
)


@app.get("/state")
def state():
    snap = latest_snapshot()
    if not snap:
        return JSONResponse(
            {"ts": None, "positions": [], "quotes": {}, "risk": {}, "empty": True}
        )
    return JSONResponse(snap)


# SSE: text/event-stream with id/retry; proxies honor 'X-Accel-Buffering: no'.
@app.get("/stream")
async def stream(request: Request):
    # Pick up from the last event the client acknowledged (if any).
    last_event_id_header = request.headers.get("last-event-id", "").strip()
    try:
        start_event_id = int(last_event_id_header) if last_event_id_header else 0
    except ValueError:
        start_event_id = 0

    async def gen():
        STREAM_CLIENTS.inc()
        try:
            last_id = start_event_id

            # Suggest a retry window so browsers reconnect promptly on drops.
            yield "retry: 2000\n\n"

            # Push initial snapshot for great UX (no id so it is not replayed).
            snap = latest_snapshot()
            if snap:
                STREAM_EVENTS.labels("snapshot").inc()
                yield "event: snapshot\n" + "data: " + json.dumps(snap, separators=(",", ":")) + "\n\n"

            while True:
                if await request.is_disconnected():
                    break
                events = tail_events(last_id, 200)
                if events:
                    last_id = events[-1][0]
                    for event_id, kind, payload in events:
                        STREAM_EVENTS.labels(kind).inc()
                        yield (
                            f"id: {event_id}\n"
                            + f"event: {kind}\n"
                            + "data: "
                            + json.dumps(payload, separators=(",", ":"))
                            + "\n\n"
                        )
                else:
                    # keep proxies and EventSource alive
                    STREAM_EVENTS.labels("heartbeat").inc()
                    yield "event: heartbeat\n" + "data: {}\n\n"
                    await asyncio.sleep(2.0)
        finally:
            STREAM_CLIENTS.dec()

    # Hint reverse proxies not to buffer (NGINX honors X-Accel-Buffering)
    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@app.get("/metrics")
def metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    # TODO: add authentication/allowlist for production deployments.
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
def healthz():
    return {"ok": bool(latest_snapshot())}
