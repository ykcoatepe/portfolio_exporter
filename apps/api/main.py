# SPDX-License-Identifier: MIT

"""FastAPI entry point exposing normalized position snapshots."""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import FileResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles

MODULE_PATH = Path(__file__).resolve()
_API_DIR = MODULE_PATH.parent
REPO_ROOT = _API_DIR.parents[1]
LIBS_PATH = REPO_ROOT / "libs" / "py"
if str(LIBS_PATH) not in sys.path:
    sys.path.append(str(LIBS_PATH))

from positions_engine.core.models import InstrumentType, Quote  # noqa: E402
from positions_engine.core.session import SessionInfo, detect_session  # noqa: E402
from positions_engine.ingest import (  # noqa: E402
    choose_provider,
    last_provider_info,
    load_demo_dataset,
)
from positions_engine.rules.catalog import (  # noqa: E402
    CatalogError,
    CatalogValidationError,
)
from positions_engine.service import (  # noqa: E402
    PositionsState,
    RefreshLoop,
    RulesCatalogState,
    RulesState,
    positions_from_records,
    quotes_from_records,
)

logger = logging.getLogger(__name__)

_state = PositionsState()
_rules_state = RulesState(_state)
_catalog_state = RulesCatalogState(_state, _rules_state)
refresh_loop = RefreshLoop(tick=_state.refresh_live_snapshot)
_greeks_interval = int(os.getenv("PSD_GREEKS_INTERVAL_S", "60"))
_greeks_refresh_loop = (
    RefreshLoop(
        tick=_state.refresh_live_greeks,
        interval_s=_greeks_interval,
        env_var="PSD_GREEKS_INTERVAL_S",
    )
    if _greeks_interval > 0
    else None
)
_AUTO_REFRESH = os.getenv("POSITIONS_ENGINE_AUTO_REFRESH", "0") == "1"
WEB_DIST = (REPO_ROOT / "apps" / "web" / "dist").resolve()
INDEX_HTML = WEB_DIST / "index.html"
_DEMO_OVERRIDE: bool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _kickoff_startup_refresh()
    refresh_loop.start()
    if _greeks_refresh_loop is not None:
        _greeks_refresh_loop.start()
    try:
        yield
    finally:
        refresh_loop.stop()
        if _greeks_refresh_loop is not None:
            _greeks_refresh_loop.stop()


app = FastAPI(title="Positions Engine API", version="0.1.0", lifespan=lifespan)


def _resolve_data_root() -> Path:
    return Path(os.getenv("POSITIONS_ENGINE_DATA_DIR", "var")).expanduser()


def _isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    iso = value.astimezone(UTC).isoformat()
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _ensure_utc(parsed)


def _max_datetime(values: list[datetime | None]) -> datetime | None:
    latest: datetime | None = None
    for value in values:
        candidate = _ensure_utc(value)
        if candidate is None:
            continue
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _latest_quote_timestamp_for_symbols(
    quotes: dict[str, Quote], symbols: set[str]
) -> datetime | None:
    if not quotes or not symbols:
        return None
    latest: datetime | None = None
    for symbol in symbols:
        quote = quotes.get(symbol)
        if quote is None:
            continue
        candidates = (
            quote.updated_at,
            quote.bid_ts,
            quote.ask_ts,
            quote.last_ts,
            quote.previous_close_ts,
        )
        candidate = _max_datetime(list(candidates))
        if candidate is None:
            continue
        if latest is None or candidate > latest:
            latest = candidate
    return latest


class BreachCountsModel(BaseModel):
    critical: int = Field(0, ge=0)
    warning: int = Field(0, ge=0)
    info: int = Field(0, ge=0)

    @property
    def total(self) -> int:
        return self.critical + self.warning + self.info


class RulesSummaryTopModel(BaseModel):
    id: str
    rule: str
    severity: str
    subject: str
    symbol: str | None = None
    occurred_at: str
    description: str | None = None
    status: str | None = None


class RulesSummaryResponseModel(BaseModel):
    as_of: str
    rules_total: int
    breaches: BreachCountsModel = Field(default_factory=BreachCountsModel)
    top: list[RulesSummaryTopModel] = Field(default_factory=list)
    focus_symbols: list[str] = Field(default_factory=list)
    evaluation_ms: float
    fundamentals: dict[str, Any] = Field(default_factory=dict)


class CatalogTextRequest(BaseModel):
    catalog_text: str = Field(..., min_length=1)


class CatalogPublishRequest(CatalogTextRequest):
    author: str | None = Field(default=None, max_length=256)


class RulesCatalogResponseModel(BaseModel):
    version: int
    updated_at: str
    updated_by: str | None = None
    rules: list[dict[str, Any]]


class CatalogDiffModel(BaseModel):
    added: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    changed: list[dict[str, Any]]


class RulesCatalogValidationResponseModel(BaseModel):
    ok: bool
    counters: dict[str, int]
    top: list[dict[str, Any]]
    errors: list[str]


class RulesCatalogPreviewResponseModel(RulesCatalogValidationResponseModel):
    diff: CatalogDiffModel


class RulesCatalogPublishResponseModel(BaseModel):
    version: int
    updated_at: str
    updated_by: str | None = None


class SessionResponseModel(BaseModel):
    exchange: str
    tz: str
    state: Literal["RTH", "ETH", "CLOSED"]
    as_of: str
    rth_open: str | None = None
    rth_close: str | None = None
    source: str = "fallback"
    note: str | None = None

    @classmethod
    def from_info(cls, info: SessionInfo) -> SessionResponseModel:
        return cls(**asdict(info))


class StatsResponse(BaseModel):
    equity_count: int
    quote_count: int | None = None
    option_legs_count: int
    combos_matched: int
    stale_quotes_count: int
    rules_count: int | None = None
    breaches_count: int | None = None
    rules_eval_ms: float | None = None
    combos_detection_ms: float | None = None
    net_liq: float | None = None
    var95_1d_pct: float | None = None
    margin_used_pct: float | None = None
    updated_at: datetime | None = None
    trades_prior_positions: bool | None = None
    data_source: str | None = None
    session: SessionResponseModel | None = None

    model_config = ConfigDict(extra="allow")


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, Any]:
    return {"ok": True, "ts": datetime.now(tz=UTC).isoformat()}


@app.post("/refresh", tags=["debug"])
def refresh_now() -> dict[str, Any]:
    _state.refresh_live_snapshot()
    _state.refresh_live_greeks()
    return {"ok": True, "ts": datetime.now(tz=UTC).isoformat()}


@app.get("/positions/stocks", tags=["positions"])
def equities() -> list[dict[str, Any]]:
    if _AUTO_REFRESH:
        _refresh_from_providers()
    return _state.equities_payload()


@app.get("/state", tags=["positions"])
def state_snapshot() -> dict[str, Any]:
    if _AUTO_REFRESH:
        _refresh_from_providers()
    payload = _state.snapshot_payload()
    session_info = asdict(detect_session())

    if not isinstance(payload.get("session"), str):
        payload["session"] = session_info["state"]

    meta = payload.get("meta")
    if isinstance(meta, dict):
        meta["session"] = session_info
    payload["session_info"] = session_info

    return payload


@app.get(
    "/stats",
    tags=["positions"],
    response_model=StatsResponse,
    response_model_exclude_none=True,
)
def stats() -> StatsResponse:
    if _AUTO_REFRESH:
        _refresh_from_providers()
    payload: dict[str, Any] = dict(_state.stats())
    evaluation = _rules_state.evaluate()
    payload["rules_count"] = len(_rules_state.rules)
    payload["breaches_count"] = len(evaluation.breaches)
    payload["rules_eval_ms"] = round(evaluation.duration_ms, 3)
    payload.setdefault("trades_prior_positions", bool(_load_prior_positions_hint()))
    payload.setdefault("net_liq", None)
    payload.setdefault("var95_1d_pct", None)
    payload.setdefault("margin_used_pct", None)
    payload["data_source"] = _state.data_source

    session_info = detect_session()
    session_payload = dataclasses.asdict(session_info)
    payload["session"] = session_payload
    if "session_info" not in payload or not isinstance(payload["session_info"], dict):
        payload["session_info"] = session_payload

    quotes_snapshot = _state.quotes_snapshot()
    positions_map = getattr(_state, "_positions", {})
    equity_symbols: set[str] = set()
    option_symbols: set[str] = set()
    if isinstance(positions_map, dict):
        for symbol, position in positions_map.items():
            instrument_type = getattr(position.instrument, "instrument_type", None)
            if instrument_type == InstrumentType.EQUITY:
                equity_symbols.add(symbol)
            elif instrument_type == InstrumentType.OPTION:
                option_symbols.add(symbol)

    equity_latest = _latest_quote_timestamp_for_symbols(quotes_snapshot, equity_symbols)
    option_latest = _latest_quote_timestamp_for_symbols(quotes_snapshot, option_symbols)
    session_latest = _parse_iso_datetime(session_info.as_of)
    latest_ts = _max_datetime([equity_latest, option_latest, session_latest])
    if latest_ts is not None:
        meta_payload = payload.get("meta")
        if not isinstance(meta_payload, dict):
            meta_payload = {}
            payload["meta"] = meta_payload
        meta_payload.setdefault("latest_ts", _isoformat_utc(latest_ts))

    snapshot_at = _state.snapshot_updated_at()
    if snapshot_at is not None and not payload.get("updated_at"):
        payload["updated_at"] = snapshot_at

    return StatsResponse(**payload)


def _refresh_from_providers() -> None:
    data_root = _resolve_data_root()
    allow_empty = os.getenv("POSITIONS_ENGINE_ALLOW_EMPTY", "0") == "1"
    demo_env_enabled = os.getenv("POSITIONS_ENGINE_DEMO", "0") == "1"
    include_demo = demo_env_enabled or not allow_empty

    positions_records, quotes_records, source_name = choose_provider(data_root)
    provider_info = last_provider_info() or {}

    if _DEMO_OVERRIDE is True:
        positions_records, quotes_records = load_demo_dataset()
        source_name = "demo"
        provider_info = {"name": "demo", "detail": "override"}
    elif _DEMO_OVERRIDE is False and source_name == "demo":
        positions_records, quotes_records = [], []
        source_name = None
        provider_info = {}

    if (
        (not positions_records and not quotes_records)
        and include_demo
        and _DEMO_OVERRIDE is not False
    ):
        positions_records, quotes_records = load_demo_dataset()
        source_name = "demo"
        if "detail" not in provider_info:
            provider_info = {"name": "demo"}

    data_source = source_name or "live"

    positions = positions_from_records(positions_records)
    quotes = _guard_quotes(quotes_from_records(quotes_records))

    if (
        data_source == "live"
        and not positions
        and not quotes
        and include_demo
        and _DEMO_OVERRIDE is False
    ):
        logger.info(
            "[ingest] Live dataset empty; demo override disabled. Provide CSVs or enable POSITIONS_ENGINE_DEMO=1 for fallback"
        )

    snapshot_at = _latest_quote_timestamp(quotes)
    positions_view_payload = (
        provider_info.get("positions_view") if isinstance(provider_info, dict) else None
    )
    _state.refresh(
        positions=positions,
        quotes=quotes,
        snapshot_at=snapshot_at,
        data_source=data_source,
        positions_view=positions_view_payload,
    )

    equity_positions = [
        position
        for position in positions
        if position.instrument.instrument_type == InstrumentType.EQUITY
    ]
    option_positions = [
        position
        for position in positions
        if position.instrument.instrument_type == InstrumentType.OPTION
    ]

    detail_hint: str | None = None
    rows_summary = "-"
    if data_source == "internal":
        detail_hint = provider_info.get("detail") or provider_info.get("name")
    elif data_source == "csv":
        metadata = provider_info.get("metadata") or {}
        detail_hint = metadata.get("positions_path") or metadata.get("data_root")
        rows_summary = (
            f"{metadata.get('positions_rows', 0)}/{metadata.get('quotes_rows', 0)}"
        )
    elif data_source == "demo":
        detail_hint = provider_info.get("detail", "demo")

    if data_source == "live" and not positions and not quotes and not include_demo:
        detail_hint = detail_hint or "empty"

    logger.info(
        "[ingest] data_source=%s equities=%d option_legs=%d quotes=%d detail=%s rows=%s",
        data_source,
        len(equity_positions),
        len(option_positions),
        len(quotes),
        detail_hint or "-",
        rows_summary,
    )


def _refresh_from_disk() -> None:
    _refresh_from_providers()


def _kickoff_startup_refresh() -> None:
    """Run the initial provider refresh without blocking API startup."""

    def _runner() -> None:
        try:
            _refresh_from_providers()
        except Exception:  # pragma: no cover - defensive
            logger.info("[startup] provider refresh failed", exc_info=True)

    thread = threading.Thread(target=_runner, name="psd-startup-refresh", daemon=True)
    thread.start()


def _guard_quotes(quotes: list[Quote]) -> list[Quote]:
    # Cost basis joiners downstream expect unique symbols. Last write wins.
    seen: dict[str, Quote] = {}
    for quote in quotes:
        seen[quote.symbol] = quote
    return list(seen.values())


def _latest_quote_timestamp(quotes: list[Quote]) -> datetime | None:
    snapshot_at: datetime | None = None
    for quote in quotes:
        ts = quote.updated_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        else:
            ts = ts.astimezone(UTC)
        if snapshot_at is None or ts > snapshot_at:
            snapshot_at = ts
    return snapshot_at


def _load_prior_positions_hint() -> str | None:
    return os.getenv("TRADES_PRIOR_POSITIONS")


@app.get("/session", tags=["meta"], response_model=SessionResponseModel)
def session_endpoint() -> SessionResponseModel:
    return SessionResponseModel.from_info(detect_session())


@app.get("/positions/options", tags=["positions"])
def options() -> dict[str, Any]:
    if _AUTO_REFRESH:
        _refresh_from_providers()
    return _state.options_payload()


@app.get("/debug/session/override/{state}", include_in_schema=False)
def override_session(state: str) -> SessionResponseModel:
    override_state = state.strip().upper()
    os.environ["FORCE_SESSION_STATE"] = override_state
    return SessionResponseModel.from_info(detect_session())


@app.get("/debug/session/clear", include_in_schema=False)
def clear_session_override() -> SessionResponseModel:
    os.environ.pop("FORCE_SESSION_STATE", None)
    return SessionResponseModel.from_info(detect_session())


@app.get("/debug/demo/enable", include_in_schema=False)
def enable_demo() -> dict[str, bool]:
    global _DEMO_OVERRIDE
    _DEMO_OVERRIDE = True
    _refresh_from_providers()
    return {"demo": True}


@app.get("/debug/demo/disable", include_in_schema=False)
def disable_demo() -> dict[str, bool]:
    global _DEMO_OVERRIDE
    _DEMO_OVERRIDE = False
    _refresh_from_providers()
    return {"demo": False}


@app.get("/rules/summary", tags=["rules"], response_model=RulesSummaryResponseModel)
def rules_summary() -> RulesSummaryResponseModel:
    if _AUTO_REFRESH:
        _refresh_from_providers()
    summary, evaluation = _rules_state.summary()
    breaches_raw = summary.get("breaches", {}) if isinstance(summary, dict) else {}
    breaches_model = BreachCountsModel(
        critical=int(breaches_raw.get("critical", 0) or 0),
        warning=int(breaches_raw.get("warning", 0) or 0),
        info=int(breaches_raw.get("info", 0) or 0),
    )

    rules_index = {rule.rule_id: rule for rule in _rules_state.rules}
    focus_symbols: set[str] = set()
    top_payload: list[RulesSummaryTopModel] = []

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
            RulesSummaryTopModel(
                id=str(breach.get("breach_id") or f"{rule_id}-{subject}"),
                rule=rule.name if rule else str(rule_id),
                severity=severity,
                subject=str(subject),
                symbol=symbol if isinstance(symbol, str) else None,
                occurred_at=(
                    str(occurred_at)
                    if occurred_at is not None
                    else datetime.now(tz=UTC).isoformat()
                ),
                description=breach.get("notes"),
                status=breach.get("status"),
            )
        )

    focus_symbols_list = sorted(focus_symbols)
    if not focus_symbols_list and isinstance(summary, dict):
        fallback_symbols = summary.get("focus_symbols", [])
        if isinstance(fallback_symbols, list):
            focus_symbols_list = sorted(
                {
                    str(symbol)
                    for symbol in fallback_symbols
                    if isinstance(symbol, str) and symbol
                }
            )
    fundamentals_raw = (
        summary.get("fundamentals", {}) if isinstance(summary, dict) else {}
    )
    fundamentals_map = fundamentals_raw if isinstance(fundamentals_raw, dict) else {}
    return RulesSummaryResponseModel(
        as_of=(
            str(summary.get("as_of"))
            if isinstance(summary, dict)
            else datetime.now(tz=UTC).isoformat()
        ),
        rules_total=(
            int(summary.get("rules_total", len(_rules_state.rules)))
            if isinstance(summary, dict)
            else len(_rules_state.rules)
        ),
        breaches=breaches_model,
        top=top_payload,
        focus_symbols=focus_symbols_list,
        evaluation_ms=float(evaluation.duration_ms),
        fundamentals=fundamentals_map,
    )


@app.get("/rules/catalog", tags=["rules"], response_model=RulesCatalogResponseModel)
def rules_catalog() -> RulesCatalogResponseModel:
    return RulesCatalogResponseModel(**_catalog_state.as_dict())


@app.post(
    "/rules/validate",
    tags=["rules"],
    response_model=RulesCatalogValidationResponseModel,
)
def rules_validate(payload: CatalogTextRequest) -> RulesCatalogValidationResponseModel:
    result = _catalog_state.validate_catalog_text(payload.catalog_text)
    return RulesCatalogValidationResponseModel(
        ok=result.ok,
        counters=result.counters,
        top=result.top,
        errors=result.errors,
    )


@app.post(
    "/rules/preview", tags=["rules"], response_model=RulesCatalogPreviewResponseModel
)
def rules_preview(payload: CatalogTextRequest) -> RulesCatalogPreviewResponseModel:
    validation, diff = _catalog_state.preview_catalog(payload.catalog_text)
    diff_model = CatalogDiffModel(**diff)
    return RulesCatalogPreviewResponseModel(
        ok=validation.ok,
        counters=validation.counters,
        top=validation.top,
        errors=validation.errors,
        diff=diff_model,
    )


@app.post(
    "/rules/publish", tags=["rules"], response_model=RulesCatalogPublishResponseModel
)
def rules_publish(payload: CatalogPublishRequest) -> RulesCatalogPublishResponseModel:
    try:
        catalog = _catalog_state.publish_catalog(
            payload.catalog_text, author=payload.author
        )
    except CatalogValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CatalogError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc))
    return RulesCatalogPublishResponseModel(
        version=catalog.version,
        updated_at=_isoformat_utc(catalog.updated_at),
        updated_by=catalog.updated_by,
    )


@app.post("/rules/reload", tags=["rules"], response_model=RulesCatalogResponseModel)
def rules_reload() -> RulesCatalogResponseModel:
    _catalog_state.reload()
    return RulesCatalogResponseModel(**_catalog_state.as_dict())


if WEB_DIST.is_dir() and INDEX_HTML.exists():
    logger.info("[web] Serving SPA from %s", WEB_DIST)
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
else:
    logger.info("[web] SPA dist not found at %s; API-only mode", WEB_DIST)


@app.middleware("http")
async def _spa_fallback(request: Request, call_next):  # pragma: no cover - thin wrapper
    response = await call_next(request)
    if response.status_code != 404 or request.method.upper() != "GET":
        return response

    path = request.url.path
    if path.startswith(
        (
            "/docs",
            "/openapi",
            "/redoc",
            "/healthz",
            "/stats",
            "/positions",
            "/rules",
            "/state",
            "/static",
            "/favicon.ico",
        )
    ):
        return response

    if not INDEX_HTML.exists():
        return PlainTextResponse(
            "PSD bundle not built; run `npm run build` in apps/web.",
            status_code=404,
        )

    return FileResponse(INDEX_HTML)
