# SPDX-License-Identifier: MIT

"""FastAPI entry point exposing normalized position snapshots."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI

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
    positions_from_records,
    quotes_from_records,
)

app = FastAPI(title="Positions Engine API", version="0.1.0")
_state = PositionsState()
_DATA_ROOT = Path(os.getenv("POSITIONS_ENGINE_DATA_DIR", "var")).expanduser()
_AUTO_REFRESH = os.getenv("POSITIONS_ENGINE_AUTO_REFRESH", "0") == "1"


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
