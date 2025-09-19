from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from psd.core.mark_router import Session
from psd.ingestor.normalize import split_positions

logger = logging.getLogger("portfolio_exporter.psd_adapter")


_ALLOWED_SESSIONS: set[str] = {"RTH", "EXT", "CLOSED"}


def _infer_session_from_clock(now: datetime | None = None) -> Session:
    tz = ZoneInfo("America/New_York")
    reference = now.astimezone(tz) if now else datetime.now(tz)
    if reference.weekday() >= 5:
        return "CLOSED"
    start = reference.replace(hour=9, minute=30, second=0, microsecond=0)
    end = reference.replace(hour=16, minute=0, second=0, microsecond=0)
    return "RTH" if start <= reference <= end else "EXT"


def _resolve_session() -> Session:
    override = os.getenv("PSD_SESSION", "").strip().upper()
    if override in _ALLOWED_SESSIONS:
        return cast(Session, override)
    return _infer_session_from_clock()


async def load_positions() -> list[dict[str, Any]]:
    """Fetch the latest positions using the portfolio exporter data layer."""

    import pandas as pd  # type: ignore

    from portfolio_exporter.scripts import portfolio_greeks

    df = await portfolio_greeks._load_positions()  # pragma: no cover - network
    return _normalize_positions(df, pd)


def _normalize_positions(df: Any, pd_module: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if isinstance(df, pd_module.DataFrame):
        if df.empty:
            return []
        normalized = df.replace({math.nan: None})
        return normalized.to_dict(orient="records")
    try:
        return list(df)
    except Exception:
        return []


async def get_marks(positions: Iterable[dict[str, Any]]) -> dict[str, float]:
    """Return mark prices for all symbols using the resilient quotes helper."""
    symbols = sorted({str(row.get("symbol", "")).strip() for row in positions if row.get("symbol")})
    if not symbols:
        return {}
    try:
        from portfolio_exporter.core import quotes

        return await asyncio.to_thread(quotes.snapshot, symbols)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("get_marks fallback: %s", exc)
        return {}


async def compute_greeks(
    positions: Iterable[dict[str, Any]],
    marks: dict[str, float],
) -> dict[str, float]:
    """Aggregate greek exposures from the provided positions."""
    totals = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    for row in positions:
        symbol = str(row.get("symbol", ""))
        qty = float(row.get("qty", row.get("position", 0.0)) or 0.0)
        mult = float(row.get("multiplier", 1.0) or 1.0)
        delta = row.get("delta") or row.get("delta_exposure")
        gamma = row.get("gamma") or row.get("gamma_exposure")
        vega = row.get("vega") or row.get("vega_exposure")
        theta = row.get("theta") or row.get("theta_exposure")
        # When raw greeks missing, approximate deltas from mark * qty as fallback
        if delta is None:
            mark_val = marks.get(symbol)
            if isinstance(mark_val, dict):
                price = mark_val.get("price") or mark_val.get("mark")
            else:
                price = mark_val
            if price is not None:
                delta = qty * mult * float(price)
        if gamma is None:
            gamma = 0.0
        if vega is None:
            vega = 0.0
        if theta is None:
            theta = 0.0
        try:
            totals["delta"] += float(delta)
            totals["gamma"] += float(gamma)
            totals["vega"] += float(vega)
            totals["theta"] += float(theta)
        except Exception:
            continue
    return totals


async def compute_risk(
    positions: Iterable[dict[str, Any]],
    marks: dict[str, Any],
    greeks: dict[str, float],
) -> dict[str, Any]:
    """Produce a lightweight risk summary suitable for PSD consumers."""
    notional = 0.0
    margin_used = 0.0
    for row in positions:
        qty = float(row.get("qty", row.get("position", 0.0)) or 0.0)
        price = row.get("mark") or row.get("price") or row.get("lastPrice")
        if price is None:
            mark_val = marks.get(str(row.get("symbol", "")))
            if isinstance(mark_val, dict):
                price = mark_val.get("price") or mark_val.get("mark")
            elif mark_val is not None:
                price = mark_val
        mult = float(row.get("multiplier", 1.0) or 1.0)
        if price is None:
            continue
        try:
            price_val = float(price)
        except (TypeError, ValueError):
            continue
        notional += abs(qty * mult * price_val)
        margin_used += float(row.get("maintenanceMargin", 0.0) or 0.0)

    delta = float(greeks.get("delta", 0.0))
    beta = delta / notional if notional else 0.0
    risk = {
        "beta": beta,
        "var95_1d": abs(delta) * 0.01,
        "margin_pct": margin_used / notional if notional else 0.0,
        "notional": notional,
    }
    return risk


async def snapshot_once() -> dict[str, Any]:
    """Return a PSD-ready snapshot containing positions, quotes, greeks and risk."""
    ts = time.time()
    try:
        positions = await load_positions()
    except Exception as exc:
        logger.warning("snapshot positions failed: %s", exc)
        try:
            import pandas as pd  # type: ignore

            from portfolio_exporter.scripts import portfolio_greeks

            df_sync = await asyncio.to_thread(
                portfolio_greeks.load_positions_sync
            )  # pragma: no cover - network
            positions = _normalize_positions(df_sync, pd)
        except Exception as fallback_exc:
            logger.warning("load_positions sync fallback failed: %s", fallback_exc)
            positions = []
    try:
        marks = await get_marks(positions)
    except Exception as exc:
        logger.warning("snapshot marks failed: %s", exc)
        marks = {}
    try:
        greeks = await compute_greeks(positions, marks)
    except Exception as exc:
        logger.warning("snapshot greeks failed: %s", exc)
        greeks = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    try:
        risk = await compute_risk(positions, marks, greeks)
    except Exception as exc:
        logger.warning("snapshot risk failed: %s", exc)
        risk = {"beta": 0.0, "var95_1d": 0.0, "margin_pct": 0.0, "notional": 0.0}

    if not isinstance(positions, list):
        raise TypeError("positions must be a list")
    if not isinstance(marks, dict):
        raise TypeError("marks must be a dict")
    if not isinstance(risk, dict):
        raise TypeError("risk must be a dict")

    session = _resolve_session()
    try:
        positions_view = split_positions(positions, session)
    except Exception as exc:
        logger.warning("snapshot positions_view failed: %s", exc)
        positions_view = {"single_stocks": [], "option_combos": [], "single_options": []}

    return {
        "ts": ts,
        "session": session,
        "positions": positions,
        "positions_view": positions_view,
        "quotes": marks,
        "risk": risk,
    }
