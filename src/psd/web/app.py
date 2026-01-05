from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import Counter, Gauge
from pydantic import BaseModel, ConfigDict
from starlette.middleware.cors import CORSMiddleware

from psd.analytics.stats import compute_stats
from psd.core.store import (
    init,
    latest_snapshot,
    max_event_id,
    read_last_stats,
    read_msb_current,
    read_msb_history,
    tail_events,
)
from psd.sentinel.sched import start_msb_scheduler, stop_msb_scheduler
from psd.ui.exporters import export_snapshot
from psd.web.config import Settings, get_settings
from psd.web.ready import router as ready_router
from psd.web.sse import SseManager, sse_endpoint

# Importing the ingestor module registers the psd_events_total counter so that
# /metrics exposes it even before ingestion writes events.
try:  # pragma: no cover - defensive in case optional deps change
    import psd.ingestor.main as _psd_ingestor_main  # noqa: F401
except Exception:  # pragma: no cover - metrics should still render
    _psd_ingestor_main = None

log = logging.getLogger("psd.web.stats")
STALE_ALERT_THRESHOLD = 10
_DEFAULT_STATS_EMPTY = compute_stats(None)

STREAM_CLIENTS = Gauge("psd_stream_clients", "Connected SSE clients")
STREAM_EVENTS = Counter("psd_stream_events_total", "SSE events sent", ["kind"])
STATS_STARTUP_BROADCASTS = Counter(
    "psd_stats_startup_broadcasts_total",
    "Initial stats broadcasts emitted during application startup",
)
STATS_BROADCASTS = Counter(
    "psd_stats_broadcasts_total",
    "Portfolio stats SSE broadcasts emitted",
    ["trigger"],
)

router = APIRouter()


class MsbDTO(BaseModel):
    """JSON representation of an MSB reading."""

    date: str
    hy: float
    vx1: float
    vx2: float
    z_hy: float | None = None
    term_ratio: float | None = None
    cal_spread_pct: float | None = None
    cal_spread_abs: float | None = None
    saturated: bool
    hy_score: int
    vix_score: int
    msb: int
    color: str
    triggers: list[str]
    winsor_clipped_n: int
    cooldown_until: str | None = None

    model_config = ConfigDict(extra="ignore")


def _create_lifespan(settings: Settings) -> Any:
    if settings.disable_background:
        return None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init()
        start_msb_scheduler(_app)
        try:
            if broadcast_latest_stats(_app, trigger="startup"):
                STATS_STARTUP_BROADCASTS.inc()
        except Exception:
            log.debug("initial stats broadcast failed", exc_info=True)
        try:
            yield
        finally:
            stop_msb_scheduler()

    return lifespan


@router.get("/state")
def state() -> JSONResponse:
    snap = latest_snapshot()
    if not snap:
        return JSONResponse(
            {"ts": None, "positions": [], "quotes": {}, "risk": {}, "empty": True}
        )
    return JSONResponse(snap)


@router.get("/stats")
def stats() -> JSONResponse:
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
    payload = dict(payload)
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


def _parse_updated_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text.rstrip("Z") + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _build_stats_payload(now: datetime | None = None) -> dict[str, Any] | None:
    stats = read_last_stats()
    if not stats:
        return None
    payload = dict(stats)
    reference = now or datetime.now(tz=UTC)
    updated_at = _parse_updated_at(payload.get("updated_at"))
    staleness = None
    if updated_at is not None:
        staleness = max(0.0, (reference - updated_at).total_seconds())
    payload["staleness_sec"] = staleness
    payload["served_at"] = reference.isoformat()
    return payload


@router.get("/stats/current")
def stats_current(fresh_within_sec: float | None = None) -> Response:
    payload = _build_stats_payload()
    if payload is None:
        raise HTTPException(status_code=404, detail="Stats unavailable")
    staleness = payload.get("staleness_sec")
    if staleness is not None and fresh_within_sec is not None:
        try:
            threshold = float(fresh_within_sec)
        except (TypeError, ValueError):
            threshold = None
        else:
            if threshold < 0:
                threshold = 0.0
        if threshold is not None and staleness > threshold:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(payload)


@router.get("/stream")
async def stream(
    request: Request,
    settings: Settings = Depends(get_settings),  # noqa: B008
):
    last_event_id_header = request.headers.get("last-event-id", "").strip()
    last_event_id: int | None
    try:
        last_event_id = int(last_event_id_header) if last_event_id_header else None
    except ValueError:
        last_event_id = None

    test_mode = bool(settings.test_mode)
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
            yield "retry: 2000\n\n"
            frames_sent += 1
            t_last = time.monotonic()
            if _maybe_quit():
                return

            snapshot_head = max_event_id()
            snap = latest_snapshot()
            if snap:
                STREAM_EVENTS.labels("snapshot").inc()
                yield (
                    "event: snapshot\n"
                    + "data: "
                    + json.dumps(snap, separators=(",", ":"))
                    + "\n\n"
                )
                frames_sent += 1
                t_last = time.monotonic()
                if _maybe_quit():
                    return
            last_id_local = last_event_id if last_event_id is not None else 0
            if snap and last_event_id is None:
                last_id_local = snapshot_head

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
                    STREAM_EVENTS.labels("heartbeat").inc()
                    yield "event: heartbeat\n" + "data: {}\n\n"
                    frames_sent += 1
                    t_last = time.monotonic()
                    if _maybe_quit():
                        return
                    await asyncio.sleep(0.05 if test_mode else 2.0)
        finally:
            STREAM_CLIENTS.dec()

    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@router.get("/metrics")
def metrics():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/healthz")
def healthz():
    return {"ok": bool(latest_snapshot())}


@router.get("/msb/current", response_model=MsbDTO)
def msb_current() -> MsbDTO:
    record = read_msb_current()
    if not record:
        raise HTTPException(status_code=404, detail="MSB reading unavailable")
    return MsbDTO.model_validate(record)


@router.get("/msb/history", response_model=list[MsbDTO])
def msb_history(days: int = 365) -> list[MsbDTO]:
    history = read_msb_history(days)
    return [MsbDTO.model_validate(entry) for entry in history]


@router.get("/msb/history.csv")
def msb_history_csv(days: int = 365) -> Response:
    history = read_msb_history(days)
    content, media_type, filename = export_snapshot(history, fmt="csv")
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/msb/history.parquet")
def msb_history_parquet(days: int = 365) -> Response:
    history = read_msb_history(days)
    content, media_type, filename = export_snapshot(history, fmt="parquet")
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type=media_type, headers=headers)


@router.post("/msb/broadcast", status_code=status.HTTP_200_OK)
async def msb_broadcast(request: Request) -> JSONResponse:
    success = broadcast_latest_msb(request.app)
    if not success:
        raise HTTPException(status_code=404, detail="MSB reading unavailable")
    return JSONResponse({"ok": True})


def broadcast_latest_msb(app: FastAPI) -> bool:
    manager = getattr(app.state, "sse", None)
    if not isinstance(manager, SseManager):
        raise RuntimeError("SSE manager not attached to FastAPI application")
    record = read_msb_current()
    if not record:
        return False
    dto = MsbDTO.model_validate(record).model_dump(mode="json")
    manager.broadcast("msb.update", dto)
    try:
        broadcast_latest_stats(app, trigger="msb")
    except Exception:  # pragma: no cover - defensive logging path
        log.debug("stats broadcast after msb update failed", exc_info=True)
    return True


def broadcast_latest_stats(app: FastAPI, *, trigger: str = "manual") -> bool:
    manager = getattr(app.state, "sse", None)
    if not isinstance(manager, SseManager):
        raise RuntimeError("SSE manager not attached to FastAPI application")
    payload = _build_stats_payload()
    if payload is None:
        return False
    manager.broadcast("psd.stats.update", payload)
    try:
        label = str(trigger or "manual")
    except Exception:  # pragma: no cover - extremely defensive
        label = "manual"
    STATS_BROADCASTS.labels(trigger=label).inc()
    return True


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    lifespan = _create_lifespan(resolved)
    if lifespan is None:
        init()
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ready_router)
    app.include_router(router)

    manager = SseManager(heartbeat_interval=resolved.sse_heartbeat_sec)
    app.state.sse = manager
    app.state.settings = resolved
    app.dependency_overrides[get_settings] = lambda: resolved

    @app.get("/sse")
    async def _sse_route(
        request: Request,
        current: Settings = Depends(get_settings),  # noqa: B008
    ):
        manager_in_state = getattr(app.state, "sse", None)
        if not isinstance(manager_in_state, SseManager):
            raise HTTPException(status_code=503, detail="SSE manager unavailable")
        if manager_in_state.heartbeat_interval != max(
            1, int(current.sse_heartbeat_sec)
        ):
            app.state.sse = SseManager(heartbeat_interval=current.sse_heartbeat_sec)
            manager_in_state = app.state.sse
        return await sse_endpoint(request, manager_in_state)

    return app


app = create_app()
