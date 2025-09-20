# SPDX-License-Identifier: MIT

"""FastAPI entry point exposing normalized position snapshots."""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles

MODULE_PATH = Path(__file__).resolve()
_API_DIR = MODULE_PATH.parent
REPO_ROOT = _API_DIR.parents[1]
LIBS_PATH = REPO_ROOT / "libs" / "py"
if str(LIBS_PATH) not in sys.path:
    sys.path.append(str(LIBS_PATH))

logger = logging.getLogger(__name__)

from positions_engine.core.models import InstrumentType, Quote  # noqa: E402
from positions_engine.ingest import load_csv_records, load_demo_dataset  # noqa: E402
from positions_engine.rules.catalog import CatalogError, CatalogValidationError  # noqa: E402
from positions_engine.service import (  # noqa: E402
    PositionsState,
    RulesCatalogState,
    RulesState,
    positions_from_records,
    quotes_from_records,
)

app = FastAPI(title="Positions Engine API", version="0.1.0")
_state = PositionsState()
_rules_state = RulesState(_state)
_catalog_state = RulesCatalogState(_state, _rules_state)
_AUTO_REFRESH = os.getenv("POSITIONS_ENGINE_AUTO_REFRESH", "0") == "1"
WEB_DIST = (REPO_ROOT / "apps" / "web" / "dist").resolve()
INDEX_HTML = WEB_DIST / "index.html"
_DEMO_OVERRIDE: bool | None = None


def _resolve_data_root() -> Path:
    return Path(os.getenv("POSITIONS_ENGINE_DATA_DIR", "var")).expanduser()


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

    class Config:
        extra = "allow"


@app.on_event("startup")
async def _on_startup() -> None:  # pragma: no cover - exercised by integration tests
    _refresh_from_disk()


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, Any]:
    return {"ok": True, "ts": datetime.now(tz=UTC).isoformat()}


@app.get("/positions/stocks", tags=["positions"])
def equities() -> list[dict[str, Any]]:
    if _AUTO_REFRESH:
        _refresh_from_disk()
    return _state.equities_payload()


@app.get(
    "/stats",
    tags=["positions"],
    response_model=StatsResponse,
    response_model_exclude_none=True,
)
def stats() -> StatsResponse:
    if _AUTO_REFRESH:
        _refresh_from_disk()
    payload: dict[str, Any] = dict(_state.stats())
    evaluation = _rules_state.evaluate()
    payload["rules_count"] = len(_rules_state.rules)
    payload["breaches_count"] = len(evaluation.breaches)
    payload["rules_eval_ms"] = round(evaluation.duration_ms, 3)
    payload.setdefault("trades_prior_positions", bool(_load_prior_positions_hint()))
    payload.setdefault("net_liq", None)
    payload.setdefault("var95_1d_pct", None)
    payload.setdefault("margin_used_pct", None)
    payload.setdefault("data_source", _state.data_source)

    snapshot_at = _state.snapshot_updated_at()
    if snapshot_at is not None and not payload.get("updated_at"):
        payload["updated_at"] = snapshot_at

    return StatsResponse(**payload)


def _refresh_from_disk() -> None:
    data_root = _resolve_data_root()
    csv_result = load_csv_records(data_root)
    metadata = csv_result.metadata
    logger.info(
        "[ingest] DATA_ROOT=%s positions_rows=%d quotes_rows=%d greeks_rows=%d",
        metadata.get("data_root"),
        metadata.get("positions_rows", 0),
        metadata.get("quotes_rows", 0),
        metadata.get("greeks_rows", 0),
    )

    positions_records = csv_result.positions
    quotes_records = csv_result.quotes

    positions = positions_from_records(positions_records)
    quotes = _guard_quotes(quotes_from_records(quotes_records))

    equity_positions = [
        position for position in positions if position.instrument.instrument_type == InstrumentType.EQUITY
    ]
    option_positions = [
        position for position in positions if position.instrument.instrument_type == InstrumentType.OPTION
    ]

    demo_env_enabled = os.getenv("POSITIONS_ENGINE_DEMO", "0") == "1"
    allow_empty = os.getenv("POSITIONS_ENGINE_ALLOW_EMPTY", "0") == "1"
    apply_demo = False
    demo_reason: str | None = None

    if _DEMO_OVERRIDE is True:
        apply_demo = True
        demo_reason = "debug override"
    elif _DEMO_OVERRIDE is False:
        apply_demo = False
    elif not equity_positions and not option_positions:
        if demo_env_enabled or not allow_empty:
            apply_demo = True
            demo_reason = "POSITIONS_ENGINE_DEMO=1" if demo_env_enabled else "ALLOW_EMPTY disabled"

    data_source = "csv" if csv_result.has_data else "live"

    if apply_demo:
        demo_positions, demo_quotes = load_demo_dataset()
        positions = positions_from_records(demo_positions)
        quotes = _guard_quotes(quotes_from_records(demo_quotes))
        equity_positions = [
            position for position in positions if position.instrument.instrument_type == InstrumentType.EQUITY
        ]
        option_positions = [
            position for position in positions if position.instrument.instrument_type == InstrumentType.OPTION
        ]
        data_source = "demo"
        logger.info(
            "[demo] Loaded fallback dataset equities=%d option_positions=%d reason=%s",
            len(equity_positions),
            len(option_positions),
            demo_reason or "auto",
        )
    elif not positions and not quotes:
        if not allow_empty and not demo_env_enabled:
            logger.info(
                "[ingest] No data available; set POSITIONS_ENGINE_DEMO=1 or POSITIONS_ENGINE_ALLOW_EMPTY=1 to control fallback"
            )
        # keep data_source as "live" to indicate no sample was injected

    snapshot_at = _latest_quote_timestamp(quotes)
    _state.refresh(positions=positions, quotes=quotes, snapshot_at=snapshot_at, data_source=data_source)


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


@app.get("/positions/options", tags=["positions"])
def options() -> dict[str, Any]:
    if _AUTO_REFRESH:
        _refresh_from_disk()
    return _state.options_payload()


@app.get("/debug/demo/enable", include_in_schema=False)
def enable_demo() -> dict[str, bool]:
    global _DEMO_OVERRIDE
    _DEMO_OVERRIDE = True
    _refresh_from_disk()
    return {"demo": True}


@app.get("/debug/demo/disable", include_in_schema=False)
def disable_demo() -> dict[str, bool]:
    global _DEMO_OVERRIDE
    _DEMO_OVERRIDE = False
    _refresh_from_disk()
    return {"demo": False}


@app.get("/rules/summary", tags=["rules"], response_model=RulesSummaryResponseModel)
def rules_summary() -> RulesSummaryResponseModel:
    if _AUTO_REFRESH:
        _refresh_from_disk()
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
                occurred_at=str(occurred_at) if occurred_at is not None else datetime.now(tz=UTC).isoformat(),
                description=breach.get("notes"),
                status=breach.get("status"),
            )
        )

    focus_symbols_list = sorted(focus_symbols)
    if not focus_symbols_list and isinstance(summary, dict):
        fallback_symbols = summary.get("focus_symbols", [])
        if isinstance(fallback_symbols, list):
            focus_symbols_list = sorted(
                {str(symbol) for symbol in fallback_symbols if isinstance(symbol, str) and symbol}
            )
    fundamentals_raw = summary.get("fundamentals", {}) if isinstance(summary, dict) else {}
    fundamentals_map = fundamentals_raw if isinstance(fundamentals_raw, dict) else {}
    return RulesSummaryResponseModel(
        as_of=str(summary.get("as_of")) if isinstance(summary, dict) else datetime.now(tz=UTC).isoformat(),
        rules_total=int(summary.get("rules_total", len(_rules_state.rules)))
        if isinstance(summary, dict)
        else len(_rules_state.rules),
        breaches=breaches_model,
        top=top_payload,
        focus_symbols=focus_symbols_list,
        evaluation_ms=float(evaluation.duration_ms),
        fundamentals=fundamentals_map,
    )


@app.get("/rules/catalog", tags=["rules"], response_model=RulesCatalogResponseModel)
def rules_catalog() -> RulesCatalogResponseModel:
    return RulesCatalogResponseModel(**_catalog_state.as_dict())


@app.post("/rules/validate", tags=["rules"], response_model=RulesCatalogValidationResponseModel)
def rules_validate(payload: CatalogTextRequest) -> RulesCatalogValidationResponseModel:
    result = _catalog_state.validate_catalog_text(payload.catalog_text)
    return RulesCatalogValidationResponseModel(
        ok=result.ok,
        counters=result.counters,
        top=result.top,
        errors=result.errors,
    )


@app.post("/rules/preview", tags=["rules"], response_model=RulesCatalogPreviewResponseModel)
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


@app.post("/rules/publish", tags=["rules"], response_model=RulesCatalogPublishResponseModel)
def rules_publish(payload: CatalogPublishRequest) -> RulesCatalogPublishResponseModel:
    try:
        catalog = _catalog_state.publish_catalog(payload.catalog_text, author=payload.author)
    except CatalogValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CatalogError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc))
    return RulesCatalogPublishResponseModel(
        version=catalog.version,
        updated_at=catalog.updated_at.isoformat(),
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
    if path.startswith((
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
    )):
        return response

    if not INDEX_HTML.exists():
        return PlainTextResponse(
            "PSD bundle not built; run `npm run build` in apps/web.",
            status_code=404,
        )

    return FileResponse(INDEX_HTML)
