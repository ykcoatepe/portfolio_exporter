# SPDX-License-Identifier: MIT

"""FastAPI entry point exposing normalized position snapshots."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

LIBS_PATH = Path(__file__).resolve().parents[2] / "libs" / "py"
if str(LIBS_PATH) not in sys.path:
    sys.path.append(str(LIBS_PATH))

from positions_engine.core.models import Quote  # noqa: E402
from positions_engine.ingest.csv import (  # noqa: E402
    load_latest_positions,
    load_latest_quotes,
)
from positions_engine.service import (  # noqa: E402
    PositionsState,
    RulesState,
    positions_from_records,
    quotes_from_records,
)

app = FastAPI(title="Positions Engine API", version="0.1.0")
_state = PositionsState()
_rules_state = RulesState(_state)
_DATA_ROOT = Path(os.getenv("POSITIONS_ENGINE_DATA_DIR", "var")).expanduser()
_AUTO_REFRESH = os.getenv("POSITIONS_ENGINE_AUTO_REFRESH", "0") == "1"


class RulesSummaryCountersModel(BaseModel):
    total: int = Field(0, ge=0)
    critical: int = Field(0, ge=0)
    warning: int = Field(0, ge=0)
    info: int = Field(0, ge=0)


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
    counters: RulesSummaryCountersModel
    top: List[RulesSummaryTopModel]
    focus_symbols: List[str]
    rules_total: int
    evaluation_ms: float


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


@app.get("/stats", tags=["positions"])
def stats() -> dict[str, Any]:
    if _AUTO_REFRESH:
        _refresh_from_disk()
    payload = _state.stats()
    evaluation = _rules_state.evaluate()
    payload["rules_count"] = len(_rules_state.rules)
    payload["breaches_count"] = len(evaluation.breaches)
    payload["rules_eval_ms"] = round(evaluation.duration_ms, 3)
    payload.setdefault("trades_prior_positions", bool(_load_prior_positions_hint()))
    return payload


def _refresh_from_disk() -> None:
    if not _DATA_ROOT.exists():
        _state.refresh(positions=[], quotes=[])
        return
    positions_df = load_latest_positions(_DATA_ROOT)
    quotes_df = load_latest_quotes(_DATA_ROOT)
    positions = (
        positions_from_records(positions_df.to_dict("records"))
        if hasattr(positions_df, "to_dict")
        else []
    )
    quotes = (
        quotes_from_records(quotes_df.to_dict("records"))
        if hasattr(quotes_df, "to_dict")
        else []
    )
    _state.refresh(positions=positions, quotes=_guard_quotes(quotes))


def _guard_quotes(quotes: list[Quote]) -> list[Quote]:
    # Cost basis joiners downstream expect unique symbols. Last write wins.
    seen: dict[str, Quote] = {}
    for quote in quotes:
        seen[quote.symbol] = quote
    return list(seen.values())


def _load_prior_positions_hint() -> str | None:
    return os.getenv("TRADES_PRIOR_POSITIONS")


@app.get("/positions/options", tags=["positions"])
def options() -> dict[str, Any]:
    if _AUTO_REFRESH:
        _refresh_from_disk()
    return _state.options_payload()


@app.get("/rules/summary", tags=["rules"], response_model=RulesSummaryResponseModel)
def rules_summary() -> RulesSummaryResponseModel:
    if _AUTO_REFRESH:
        _refresh_from_disk()
    summary, evaluation = _rules_state.summary()
    counters = summary.get("breaches", {}) if isinstance(summary, dict) else {}
    counters_model = RulesSummaryCountersModel(
        total=int(sum(int(counters.get(key, 0)) for key in ("critical", "warning", "info"))),
        critical=int(counters.get("critical", 0) or 0),
        warning=int(counters.get("warning", 0) or 0),
        info=int(counters.get("info", 0) or 0),
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
    return RulesSummaryResponseModel(
        as_of=str(summary.get("as_of")) if isinstance(summary, dict) else datetime.now(tz=UTC).isoformat(),
        counters=counters_model,
        top=top_payload,
        focus_symbols=focus_symbols_list,
        rules_total=int(summary.get("rules_total", len(_rules_state.rules))) if isinstance(summary, dict) else len(_rules_state.rules),
        evaluation_ms=float(evaluation.duration_ms),
    )
