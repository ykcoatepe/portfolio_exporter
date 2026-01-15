from __future__ import annotations

import asyncio
import json
import logging
import os

# Add libs/py to path for positions_engine
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import REGISTRY, Counter, Gauge
from prometheus_client.metrics import MetricWrapperBase
from pydantic import BaseModel, ConfigDict
from starlette.middleware.cors import CORSMiddleware

from portfolio_exporter.psd_powerlaw import (
    load_powerlaw_snapshot,
    request_powerlaw_refresh,
)
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
from psd.datasources import resolve_msb_source
from psd.ingestor.normalize import split_positions
from psd.sentinel.msb_metrics import (
    MSB_DATA_AGE_SECONDS,
)
from psd.sentinel.sched import (
    run_msb_scheduler_once,
    start_msb_scheduler,
    stop_msb_scheduler,
)
from psd.ui.exporters import export_snapshot
from psd.web.config import Settings, get_settings
from psd.web.ready import router as ready_router
from psd.web.sse import SseManager, sse_endpoint

log = logging.getLogger("psd.web.stats")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIBS_PATH = _REPO_ROOT / "libs" / "py"
if str(_LIBS_PATH) not in sys.path:
    sys.path.insert(0, str(_LIBS_PATH))

try:
    from positions_engine.rules.catalog import load_catalog
    from positions_engine.service import PositionsState, RulesState
    _RULES_ENGINE_AVAILABLE = True
except ImportError as _import_err:
    log.debug("positions_engine import failed: %s", _import_err)
    _RULES_ENGINE_AVAILABLE = False
    PositionsState = None  # type: ignore
    RulesState = None  # type: ignore

# Importing the ingestor module registers the psd_events_total counter so that
# /metrics exposes it even before ingestion writes events.
try:  # pragma: no cover - defensive in case optional deps change
    import psd.ingestor.main as _psd_ingestor_main  # noqa: F401
except Exception:  # pragma: no cover - metrics should still render
    _psd_ingestor_main = None

STALE_ALERT_THRESHOLD = 10
_DEFAULT_STATS_EMPTY = compute_stats(None)


def _get_or_create_metric(
    factory: type[MetricWrapperBase],
    name: str,
    documentation: str,
    *args: Any,
    **kwargs: Any,
) -> MetricWrapperBase:
    try:
        return factory(name, documentation, *args, **kwargs)
    except ValueError as exc:
        if "Duplicated timeseries" not in str(exc):
            raise
        existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if existing is None:
            raise
        return existing


STREAM_CLIENTS = _get_or_create_metric(
    Gauge, "psd_stream_clients", "Connected SSE clients"
)
STREAM_EVENTS = _get_or_create_metric(
    Counter, "psd_stream_events_total", "SSE events sent", ["kind"]
)
STATS_STARTUP_BROADCASTS = _get_or_create_metric(
    Counter,
    "psd_stats_startup_broadcasts_total",
    "Initial stats broadcasts emitted during application startup",
)
STATS_BROADCASTS = _get_or_create_metric(
    Counter,
    "psd_stats_broadcasts_total",
    "Portfolio stats SSE broadcasts emitted",
    ["trigger"],
)

router = APIRouter()


def _empty_positions_view() -> dict[str, list[Any]]:
    return {"single_stocks": [], "option_combos": [], "single_options": []}


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


class MsbRefreshDTO(BaseModel):
    ok: bool
    status: str
    detail: str | None = None

    model_config = ConfigDict(extra="ignore")


class MsbStatusDTO(BaseModel):
    status: str
    refreshed_at: str | None = None
    last_date: str | None = None
    detail: str | None = None
    source: str | None = None
    data_age_seconds: float | None = None

    model_config = ConfigDict(extra="ignore")


class MsbHelpSectionDTO(BaseModel):
    """MSB help section payload."""

    title: str
    bullets: list[str]

    model_config = ConfigDict(extra="ignore")


class MsbHelpTermDTO(BaseModel):
    """MSB help term definition for stat tooltips."""

    key: str
    title: str
    body: str | None = None
    bullets: list[str] | None = None

    model_config = ConfigDict(extra="ignore")


class MsbHelpDTO(BaseModel):
    """MSB help payload for the dashboard tooltip."""

    title: str
    subtitle: str | None = None
    sections: list[MsbHelpSectionDTO]
    terms: list[MsbHelpTermDTO] | None = None
    footnotes: list[str] | None = None

    model_config = ConfigDict(extra="ignore")


class PowerlawHelpSectionDTO(BaseModel):
    """Powerlaw help section definition."""

    title: str
    bullets: list[str]

    model_config = ConfigDict(extra="ignore")


class PowerlawHelpTermDTO(BaseModel):
    """Powerlaw help term definition for stat tooltips."""

    key: str
    title: str
    body: str | None = None
    bullets: list[str] | None = None

    model_config = ConfigDict(extra="ignore")


class PowerlawHelpDTO(BaseModel):
    """Powerlaw help payload for the dashboard tooltip."""

    title: str
    subtitle: str | None = None
    sections: list[PowerlawHelpSectionDTO]
    terms: list[PowerlawHelpTermDTO] | None = None
    footnotes: list[str] | None = None

    model_config = ConfigDict(extra="ignore")


_MSB_TRIGGER_LABELS = {
    "A": "RULE_A_VIX_BACKWARDATION",
    "B": "RULE_B_HY_SHOCK",
    "C": "RULE_C_MSB_60x3D",
}


def _normalize_msb_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    triggers = payload.get("triggers")
    if isinstance(triggers, list):
        mapped: list[str] = []
        for item in triggers:
            if not isinstance(item, str):
                continue
            key = item.strip().upper()
            mapped.append(_MSB_TRIGGER_LABELS.get(key, item))
        payload["triggers"] = mapped
    return payload


_DEFAULT_MSB_HELP: dict[str, Any] = {
    "title": "MSB Signals Guide",
    "subtitle": "How to read HY-OAS and VX1/VX2 charts",
    "sections": [
        {
            "title": "HY-OAS (credit stress)",
            "bullets": [
                "Represents the option-adjusted spread for high yield credit.",
                "Rising HY-OAS signals widening credit spreads and stress.",
                "Watch for sharp 1D and 5D jumps (Rule B thresholds: +0.25 / +0.60).",
                "Falling or stable HY-OAS suggests easing credit conditions.",
            ],
        },
        {
            "title": "VX1/VX2 ratio (vol term structure)",
            "bullets": [
                "VX1 is front month VIX (or VIX index) and VX2 is next month or VIX3M.",
                "Ratio > 1.0 implies backwardation (near-term stress).",
                "Sustained > 1.05 or rising slope often precedes equity drawdowns.",
                "Rule A: backwardation plus negative SPX return triggers escalation.",
            ],
        },
        {
            "title": "Market Stress Barometer terms",
            "bullets": [
                "Stress = HY Score + VIX Score (0–100). Color bands: <30 green, 30–49 yellow, 50–69 orange, ≥70 red.",
                "HY Score (0–50) scales the HY-OAS level vs history; higher means wider credit spreads.",
                "VIX Score (0–50) tracks VIX term structure and calendar spread magnitude; higher means near-term vol stress.",
                "Term Ratio = (VX1 / VX2) − 1. Positive = backwardation, negative = contango.",
                "Cal Spread % = (VX1 − VX2) / VX2, same idea as term ratio but shown as a percent.",
            ],
        },
    ],
    "terms": [
        {
            "key": "hy",
            "title": "HY Score",
            "body": "Scaled measure of HY-OAS stress (0–50). Higher = wider credit spreads.",
            "bullets": [
                "Uses HY-OAS levels vs historical bands.",
                "Sharp daily/weekly widening lifts the score quickly.",
            ],
        },
        {
            "key": "vix",
            "title": "VIX Score",
            "body": "Scaled measure of volatility stress (0–50). Higher = near-term vol pressure.",
            "bullets": [
                "Combines calendar spread and term structure signals.",
                "Saturation adds extra points when VX1 is elevated.",
            ],
        },
        {
            "key": "term",
            "title": "Term Ratio",
            "body": "Defined as (VX1 / VX2) − 1. Positive means backwardation.",
            "bullets": [
                "Positive = short-term vol higher than longer-term (stress).",
                "Negative = contango (calmer conditions).",
            ],
        },
        {
            "key": "cal",
            "title": "Cal Spread %",
            "body": "Defined as (VX1 − VX2) / VX2. A percent view of the term spread.",
            "bullets": [
                "Large positive values suggest near-term stress.",
                "Negative values indicate contango.",
            ],
        },
    ],
    "footnotes": [
        "Rule B uses HY-OAS delta in index points (approx 25 bps in 1D or 60 bps in 5D).",
        "Rule A requires VX1 > VX2 and SPX return < 0 on the same day.",
    ],
}


_DEFAULT_POWERLAW_HELP: dict[str, Any] = {
    "title": "Powerlaw Signals Guide",
    "subtitle": "How to read PLKE, risk state, and sleeve controls",
    "sections": [
        {
            "title": "What this panel summarizes",
            "bullets": [
                "Daily snapshot after market close from the TRADER v5 pipeline.",
                "PLKE shows market criticality and its regime band.",
                "Risk State gates equity exposure and hedge sizing.",
                "Equity weights and hedge notional are target sleeve settings.",
                "Small-cap overlay shows theta target and whether new trades are allowed.",
            ],
        },
        {
            "title": "PLKE bands (Extremistan)",
            "bullets": [
                "PLKE is a 0-100 criticality index built from tail, clustering, and acceleration signals.",
                "Operational bands: Calm <30, Heating 30-60, Critical 60-80, Dragon >=80.",
                "Higher bands scale down equity exposure and tighten vega caps.",
            ],
        },
        {
            "title": "Risk State + V/VIX",
            "bullets": [
                "Risk State is ON, NEUTRAL, or OFF using VIX, VX term structure, and PLKE overlay.",
                "OFF is a hard risk-off gate; equity weights are reduced and small-cap theta goes to zero.",
                "Backwardation (VX1 > VX2) can be required for OFF depending on config.",
            ],
        },
        {
            "title": "Small-cap income overlay",
            "bullets": [
                "Theta target is the small-cap income budget as percent of NAV.",
                "New trades are blocked in Critical/Dragon or when Risk State is OFF.",
                "Heating band can block new trades if V/VIX utilization is above the cap.",
            ],
        },
        {
            "title": "Data quality",
            "bullets": [
                "OK means inputs are fresh; WARN means stale or missing inputs.",
                "Details list which symbols or data series are stale.",
                "Treat WARN snapshots as informational until data is refreshed.",
            ],
        },
    ],
    "terms": [
        {
            "key": "plke",
            "title": "PLKE (market criticality)",
            "body": "PLKE is a 0-100 measure of market stress; higher values mean higher tail risk.",
            "bullets": [
                "Bands: Calm <30, Heating 30-60, Critical 60-80, Dragon >=80.",
                "Band scales equity exposure and vega caps.",
            ],
        },
        {
            "key": "risk_state",
            "title": "Risk State",
            "body": "ON, NEUTRAL, or OFF regime derived from VIX, VX1/VX2, and PLKE overlay.",
            "bullets": [
                "OFF is a hard risk-off state; equity exposure is reduced.",
                "PLKE Critical/Dragon prevents upgrades to ON.",
            ],
        },
        {
            "key": "vutil_used",
            "title": "V/VIX Utilization",
            "body": "Active utilization used for gating and hedge sizing (real if available, else budget).",
            "bullets": [
                "Bucketed into LOW / MED / HIGH for quick read.",
                "Higher utilization tightens small-cap gating in Heating band.",
            ],
        },
        {
            "key": "vix_vvix",
            "title": "VIX / VVIX",
            "body": "Spot VIX and VVIX values used by the risk state and vega caps.",
            "bullets": [
                "Backwardation = VX1 > VX2 when VX futures are available.",
                "High VVIX can reduce vega caps.",
            ],
        },
        {
            "key": "equity_weights",
            "title": "Equity Weights",
            "body": "Target sleeve weights for SPY/QQQ/IWM after PLKE and risk overlays.",
            "bullets": [
                "Used to size core equity exposure.",
                "Scaled down further in OFF state.",
            ],
        },
        {
            "key": "hedge_notional",
            "title": "Hedge Notional",
            "body": "Target hedge sizing (notional fractions) for tail risk protection.",
            "bullets": [
                "Examples include SPX put spreads or VIX hedges.",
                "Sized from PLKE band and risk state.",
            ],
        },
        {
            "key": "small_cap_theta",
            "title": "Small-cap Theta",
            "body": "Target theta budget for the income overlay as percent of NAV.",
            "bullets": [
                "Calm: ~0.30% NAV; Heating: ~0.24%; Critical: ~0.18%; Dragon: ~0.12% or 0.",
                "Risk State OFF sets theta to 0.",
            ],
        },
        {
            "key": "small_cap_gate",
            "title": "Small-cap Gate",
            "body": "Whether new small-cap trades are allowed today.",
            "bullets": [
                "Blocked in Risk State OFF and in Critical/Dragon bands.",
                "Heating can block when V/VIX utilization exceeds the cap.",
            ],
        },
        {
            "key": "data_quality",
            "title": "Data Quality",
            "body": "Snapshot quality status based on freshness of inputs.",
            "bullets": [
                "OK: all required inputs are current.",
                "WARN: one or more inputs are stale or missing (see details).",
            ],
        },
    ],
    "footnotes": [
        "TRADER v5 snapshot is intended to run after market close using latest EOD data.",
        "PLKE band thresholds are calibrated in notebooks and used operationally in production.",
    ],
}


def _resolve_msb_help_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / candidate


def _resolve_powerlaw_repo_root() -> Path | None:
    repo_env = os.getenv("PSD_POWERLAW_REPO", "").strip()
    if repo_env:
        candidate = Path(repo_env).expanduser()
        return candidate if candidate.exists() else None
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root.parent / "codeforge-powerlaw-trader"
    return candidate if candidate.exists() else None


def _resolve_powerlaw_help_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    repo_root = _resolve_powerlaw_repo_root()
    if repo_root is not None:
        return repo_root / path
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / candidate


def _load_msb_help() -> dict[str, Any]:
    env = os.environ
    raw_json = env.get("PSD_MSB_SIGNALS_HELP_JSON")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            log.warning("invalid PSD_MSB_SIGNALS_HELP_JSON; using defaults")
    path = env.get("PSD_MSB_SIGNALS_HELP_PATH", "config/msb_signals_help.json")
    try:
        resolved = _resolve_msb_help_path(path)
        data = resolved.read_text(encoding="utf-8")
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed
    except FileNotFoundError:
        return _DEFAULT_MSB_HELP
    except Exception as exc:
        log.warning("failed to load msb help config: %s", exc)
    return _DEFAULT_MSB_HELP


def _load_powerlaw_help() -> dict[str, Any]:
    env = os.environ
    raw_json = env.get("PSD_POWERLAW_HELP_JSON")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            log.warning("invalid PSD_POWERLAW_HELP_JSON; using defaults")
    path = env.get("PSD_POWERLAW_HELP_PATH", "docs/powerlaw_signals_help.json")
    try:
        resolved = _resolve_powerlaw_help_path(path)
        data = resolved.read_text(encoding="utf-8")
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed
    except FileNotFoundError:
        return _DEFAULT_POWERLAW_HELP
    except Exception as exc:
        log.warning("failed to load powerlaw help config: %s", exc)
    return _DEFAULT_POWERLAW_HELP


def _set_msb_refresh_state(
    app: FastAPI,
    *,
    status: str,
    detail: str | None = None,
    source: str | None = None,
) -> None:
    def _record_ts(record: dict[str, Any] | None) -> datetime | None:
        if not record or "date" not in record:
            return None
        raw = record.get("date")
        if raw is None:
            return None
        try:
            dt = datetime.fromisoformat(str(raw))
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    record = read_msb_current()
    last_date = record.get("date") if record else None
    ts = _record_ts(record)
    age = max(0.0, (datetime.now(UTC) - ts).total_seconds()) if ts else None
    if age is not None:
        MSB_DATA_AGE_SECONDS.set(age)
    app.state.msb_refresh = {
        "status": status,
        "detail": detail,
        "refreshed_at": datetime.now(UTC).isoformat(),
        "last_date": last_date,
        "source": source,
        "data_age_seconds": age,
    }


def _create_lifespan(settings: Settings) -> Any:
    if settings.disable_background:
        return None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init()
        start_msb_scheduler(_app)
        if settings.msb_startup_refresh:
            def _startup_refresh() -> None:
                try:  # ensure ib_insync has an event loop inside thread
                    import asyncio

                    asyncio.set_event_loop(asyncio.new_event_loop())
                except Exception:
                    pass
                try:
                    updated = run_msb_scheduler_once(
                        _app,
                        allow_stale=True,
                        force_refresh=True,
                    )
                    _set_msb_refresh_state(
                        _app,
                        status="updated" if updated else "skipped",
                        detail=None if updated else "no new data",
                        source=resolve_msb_source(),
                    )
                except Exception as exc:  # pragma: no cover - depends on runtime IO
                    log.warning("msb startup refresh failed", exc_info=True)
                    _set_msb_refresh_state(
                        _app,
                        status="error",
                        detail=str(exc),
                        source=resolve_msb_source(),
                    )

            threading.Thread(
                target=_startup_refresh,
                name="psd-msb-startup-refresh",
                daemon=True,
            ).start()
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
    powerlaw = None
    try:
        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(load_powerlaw_snapshot)
        try:
            powerlaw = future.result(timeout=10.0)  # 10 second timeout
        except concurrent.futures.TimeoutError:
            log.warning("powerlaw snapshot load timed out (10s)")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    except Exception as exc:
        log.warning("powerlaw snapshot load failed: %s", exc)
    if not snap:
        payload = {
            "ts": None,
            "positions": [],
            "positions_view": _empty_positions_view(),
            "quotes": {},
            "risk": {},
            "empty": True,
        }
        if powerlaw is not None:
            payload["powerlaw"] = powerlaw
        return JSONResponse(payload)
    view = snap.get("positions_view")
    if not isinstance(view, dict):
        positions = snap.get("positions")
        session = snap.get("session")
        if not isinstance(session, str):
            session = "EXT"
        if isinstance(positions, list):
            try:
                view = split_positions(positions, session)
            except Exception:
                log.debug("positions_view fallback failed", exc_info=True)
                view = _empty_positions_view()
        else:
            view = _empty_positions_view()
        snap = {**snap, "positions_view": view}
    if powerlaw is not None:
        snap = {**snap, "powerlaw": powerlaw}
    return JSONResponse(snap)


@router.post("/powerlaw/refresh", status_code=status.HTTP_200_OK)
def powerlaw_refresh() -> JSONResponse:
    try:
        payload = request_powerlaw_refresh(force=True)
    except Exception as exc:
        log.warning("powerlaw refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail="powerlaw refresh failed") from exc
    return JSONResponse(payload)


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


def _snapshot_as_of_iso(snapshot: dict[str, Any]) -> str | None:
    ts = snapshot.get("ts")
    if isinstance(ts, (int, float)):
        ts_float = float(ts)
        if ts_float > 0:
            if ts_float < 1e11:
                ts_float *= 1000
            try:
                return datetime.fromtimestamp(ts_float / 1000, tz=UTC).isoformat()
            except (OverflowError, OSError, ValueError):
                return None
    return None


@router.get("/stats/current")
def stats_current(fresh_within_sec: float | None = None) -> Response:
    payload = _build_stats_payload()
    if payload is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
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
    return MsbDTO.model_validate(_normalize_msb_payload(record))


@router.get("/msb/history", response_model=list[MsbDTO])
def msb_history(days: int = 365) -> list[MsbDTO]:
    history = read_msb_history(days)
    return [MsbDTO.model_validate(_normalize_msb_payload(entry)) for entry in history]


@router.get("/positions/combos")
def positions_combos() -> list:
    """Return strategy combos (backwards compat stub)."""
    return []


@router.get("/positions/options")
def positions_options() -> dict[str, Any]:
    """Return option combos/legs (compat stub)."""
    snap = latest_snapshot()
    as_of = _snapshot_as_of_iso(snap) if snap else None
    return {
        "as_of": as_of,
        "combos": [],
        "legs": [],
        "combo_groups": [],
        "playbook": None,
    }


@router.get("/positions/legs")
def positions_legs() -> list:
    """Return option legs."""
    snap = latest_snapshot()
    if not snap:
        return []
    pos = snap.get("positions", [])
    if isinstance(pos, list):
        # Filter for options/futures options
        return [p for p in pos if p.get("secType") in ("OPT", "FOP")]
    return []


def _merge_powerlaw_msb(
    powerlaw: dict[str, Any] | None, msb: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not isinstance(powerlaw, dict) and not isinstance(msb, dict):
        return None
    merged: dict[str, Any] = dict(powerlaw) if isinstance(powerlaw, dict) else {}
    msb_signals: dict[str, Any] = {}
    if isinstance(msb, dict):
        for key in ("vx1", "vx2", "spx_ret", "spx_return", "spx_return_pct"):
            value = msb.get(key)
            if value is not None:
                msb_signals[key] = value
    if not msb_signals:
        return merged or None
    signals = merged.get("signals")
    if isinstance(signals, dict):
        updated_signals = dict(signals)
        updated_signals.update(msb_signals)
        merged["signals"] = updated_signals
        return merged
    merged.update(msb_signals)
    return merged


@router.get("/rules/summary")
def rules_summary() -> dict:
    """Return rules summary with real evaluation if engine available."""
    now = datetime.now(UTC)
    
    if not _RULES_ENGINE_AVAILABLE:
        return {
            "rules_total": 0,
            "breaches": {"critical": 0, "warning": 0, "info": 0},
            "top": [],
            "as_of": now.isoformat(),
            "focus_symbols": [],
        }
    
    # Load powerlaw snapshot for metrics
    powerlaw = None
    try:
        powerlaw = load_powerlaw_snapshot()
    except Exception:
        log.debug("powerlaw snapshot load failed for rules", exc_info=True)

    msb = None
    try:
        msb = read_msb_current()
    except Exception:
        log.debug("msb snapshot load failed for rules", exc_info=True)
    powerlaw = _merge_powerlaw_msb(powerlaw, msb)
    
    # Create positions state from latest snapshot
    snap = latest_snapshot()
    positions_raw = snap.get("positions", []) if snap else []
    positions = positions_raw if isinstance(positions_raw, list) else []
    quotes_payload = snap.get("quotes", {}) if snap else {}

    positions_state = PositionsState()
    try:
        from positions_engine.service.normalize import (
            positions_from_records,
            quotes_from_records,
        )
    except Exception as exc:
        log.warning("positions_engine normalize unavailable: %s", exc)
    else:
        quote_records: list[dict[str, Any]] = []
        if isinstance(quotes_payload, dict):
            for symbol, payload in quotes_payload.items():
                if not isinstance(payload, dict):
                    continue
                record = dict(payload)
                record.setdefault("symbol", symbol)
                if "last" not in record and "price" in record:
                    record["last"] = record.get("price")
                if "previous_close" not in record and "previousClose" in record:
                    record["previous_close"] = record.get("previousClose")
                quote_records.append(record)

        try:
            positions_state.refresh(
                positions=positions_from_records(positions),
                quotes=quotes_from_records(quote_records),
                snapshot_at=now,
                data_source=str(snap.get("data_source") or "snapshot") if snap else None,
            )
        except Exception as exc:
            log.warning("rules snapshot normalization failed: %s", exc)
            positions_state = PositionsState()
    
    try:
        catalog = load_catalog()
        rules_state = RulesState(positions_state, rules=catalog.rules)
        summary, evaluation = rules_state.summary(now, powerlaw_snapshot=powerlaw)

        # Extract metrics from summary
        metrics = summary.get("playbook_metrics") or {}

        rules_index = {rule.rule_id: rule for rule in catalog.rules}
        focus_symbols: set[str] = set()
        top_payload: list[dict[str, Any]] = []
        for breach in summary.get("top", []) if isinstance(summary, dict) else []:
            if not isinstance(breach, dict):
                continue
            rule_id = breach.get("rule_id")
            rule = rules_index.get(rule_id)
            severity = (rule.severity if rule else "INFO").lower()
            symbol = breach.get("symbol")
            if isinstance(symbol, str) and symbol:
                focus_symbols.add(symbol)
            subject = breach.get("subject_id") or symbol or rule_id or "n/a"
            occurred_at = breach.get("triggered_at")
            top_payload.append(
                {
                    "id": str(breach.get("breach_id") or f"{rule_id}-{subject}"),
                    "rule": rule.name if rule else str(rule_id),
                    "severity": severity,
                    "subject": str(subject),
                    "symbol": symbol if isinstance(symbol, str) else None,
                    "occurred_at": (
                        str(occurred_at) if occurred_at is not None else now.isoformat()
                    ),
                    "description": breach.get("notes"),
                    "status": breach.get("status"),
                }
            )

        return {
            "rules_total": summary.get("rules_total", len(catalog.rules)),
            "breaches": summary.get("breaches", {"critical": 0, "warning": 0, "info": 0}),
            "top": top_payload,
            "focus_symbols": sorted(focus_symbols),
            "as_of": now.isoformat(),
            "evaluation_ms": float(evaluation.duration_ms),
            "v_vix_utilization_pct": metrics.get("v_vix_utilization_pct"),
            "risk_state": metrics.get("risk_state"),
            "nav_ref": metrics.get("nav_ref"),
            "vix": metrics.get("vix"),
            "vvix": metrics.get("vvix"),
        }
    except Exception as exc:
        log.warning("rules evaluation failed: %s", exc, exc_info=True)
        return {
            "rules_total": 0,
            "breaches": {"critical": 0, "warning": 0, "info": 0},
            "top": [],
            "as_of": now.isoformat(),
            "focus_symbols": [],
            "error": str(exc),
        }


@router.get("/msb/history.csv")
def msb_history_csv(days: int = 365) -> Response:
    history = [_normalize_msb_payload(entry) for entry in read_msb_history(days)]
    content, media_type, filename = export_snapshot(history, fmt="csv")
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/msb/history.parquet")
def msb_history_parquet(days: int = 365) -> Response:
    history = [_normalize_msb_payload(entry) for entry in read_msb_history(days)]
    content, media_type, filename = export_snapshot(history, fmt="parquet")
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type=media_type, headers=headers)


@router.post("/msb/refresh", response_model=MsbRefreshDTO)
async def msb_refresh(request: Request) -> MsbRefreshDTO:
    try:
        updated = await asyncio.to_thread(
            run_msb_scheduler_once,
            request.app,
            allow_stale=True,
            force_refresh=True,
        )
    except Exception as exc:
        log.warning("msb refresh failed: %s", exc, exc_info=True)
        _set_msb_refresh_state(
            request.app,
            status="error",
            detail=str(exc),
            source=resolve_msb_source(),
        )
        raise HTTPException(status_code=500, detail="MSB refresh failed") from exc
    if updated:
        _set_msb_refresh_state(
            request.app,
            status="updated",
            detail=None,
            source=resolve_msb_source(),
        )
        return MsbRefreshDTO(ok=True, status="updated")
    _set_msb_refresh_state(
        request.app,
        status="skipped",
        detail="no new data",
        source=resolve_msb_source(),
    )
    return MsbRefreshDTO(ok=False, status="skipped", detail="no new data")


@router.get("/msb/status", response_model=MsbStatusDTO)
def msb_status(request: Request) -> MsbStatusDTO:
    state = getattr(request.app.state, "msb_refresh", None)
    record = read_msb_current()
    last_date = record.get("date") if record else None
    age = None
    if last_date is not None:
        try:
            ts = datetime.fromisoformat(str(last_date))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age = max(0.0, (datetime.now(UTC) - ts).total_seconds())
        except Exception:
            age = None
    if age is not None:
        MSB_DATA_AGE_SECONDS.set(age)
    if not isinstance(state, dict):
        return MsbStatusDTO(
            status="unknown",
            last_date=last_date,
            source=resolve_msb_source(),
            data_age_seconds=age,
        )
    return MsbStatusDTO(
        status=str(state.get("status") or "unknown"),
        refreshed_at=state.get("refreshed_at"),
        last_date=state.get("last_date") or last_date,
        detail=state.get("detail"),
        source=state.get("source") or resolve_msb_source(),
        data_age_seconds=age if age is not None else state.get("data_age_seconds"),
    )


@router.get("/msb/help", response_model=MsbHelpDTO)
def msb_help() -> MsbHelpDTO:
    payload = _load_msb_help()
    return MsbHelpDTO.model_validate(payload)


@router.get("/powerlaw/help", response_model=PowerlawHelpDTO)
def powerlaw_help() -> PowerlawHelpDTO:
    payload = _load_powerlaw_help()
    return PowerlawHelpDTO.model_validate(payload)


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
    dto = MsbDTO.model_validate(_normalize_msb_payload(record)).model_dump(mode="json")
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
    app.state.msb_refresh = {
        "status": "unknown",
        "detail": None,
        "refreshed_at": None,
        "last_date": None,
    }
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
