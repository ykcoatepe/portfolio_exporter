from __future__ import annotations

import asyncio
import importlib
import logging
import math
import os
import threading
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from psd.core.mark_router import Session
from psd.ingestor.normalize import split_positions

logger = logging.getLogger("portfolio_exporter.psd_adapter")


_ALLOWED_SESSIONS: set[str] = {"RTH", "EXT", "CLOSED"}


_UNSET = object()
_CACHE_SENTINEL = _UNSET  # Backward compatibility for older tests
_ENGINE_STATE_CACHE: Any = _UNSET
_ENGINE_STATE_LOCK = threading.Lock()


def _empty_positions_view() -> dict[str, list[Any]]:
    return {"single_stocks": [], "option_combos": [], "single_options": []}


def _coerce_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _coerce_int(value: Any) -> int:
    number = _coerce_float(value)
    return int(number) if number is not None else 0


def _get_positions_engine_state() -> Any | None:
    global _ENGINE_STATE_CACHE
    if _ENGINE_STATE_CACHE is not _UNSET:
        return cast(Any | None, _ENGINE_STATE_CACHE)
    with _ENGINE_STATE_LOCK:
        if _ENGINE_STATE_CACHE is not _UNSET:
            return cast(Any | None, _ENGINE_STATE_CACHE)
        try:
            module = importlib.import_module("apps.api.main")
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.debug("positions engine state unavailable: %s", exc)
            return None
        state = getattr(module, "_state", None)
        refresh = getattr(module, "_refresh_from_disk", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.debug("positions engine refresh failed: %s", exc)
            else:
                state = getattr(module, "_state", state)
        if state is None:
            return None
        _ENGINE_STATE_CACHE = state
        return cast(Any | None, _ENGINE_STATE_CACHE)


def _build_positions_view_from_engine(pe_state: Any | None = None) -> dict[str, Any]:
    state = pe_state if pe_state is not None else _get_positions_engine_state()
    if state is None:
        return _empty_positions_view()

    try:
        stocks_iter = state.stocks()  # type: ignore[attr-defined]
    except AttributeError:
        stocks_iter = state.equities_payload() if hasattr(state, "equities_payload") else []
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("positions engine stocks() failed: %s", exc)
        stocks_iter = []

    stocks_view: list[dict[str, Any]] = []
    for record in stocks_iter or []:
        if not isinstance(record, dict):
            continue
        symbol = str(record.get("symbol") or record.get("underlying") or "").strip() or "?"
        qty = _coerce_float(record.get("qty") or record.get("quantity")) or 0.0
        mark = _coerce_float(record.get("mark") or record.get("mid"))
        avg_cost = _coerce_float(record.get("avg_cost") or record.get("avg"))
        if mark is None and avg_cost is not None:
            mark = avg_cost
        pnl_unrealized = 0.0
        if mark is not None and avg_cost is not None:
            pnl_unrealized = (mark - avg_cost) * qty
        stocks_view.append(
            {
                "symbol": symbol,
                "qty": qty,
                "mark": mark if mark is not None else 0.0,
                "avg_cost": avg_cost,
                "pnl_unrealized": pnl_unrealized,
                "pnl_intraday": pnl_unrealized,
                "greeks": {"delta": 0.0, "gamma": 0.0, "theta": 0.0},
                "mark_source": record.get("mark_source"),
                "stale_seconds": _coerce_int(record.get("stale_seconds")),
            }
        )

    try:
        options_payload = state.options()  # type: ignore[attr-defined]
    except AttributeError:
        options_payload = state.options_payload() if hasattr(state, "options_payload") else {}
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("positions engine options() failed: %s", exc)
        options_payload = {}

    if not isinstance(options_payload, dict):
        options_payload = {}

    combos_view: list[dict[str, Any]] = []
    legs_view: list[dict[str, Any]] = []

    for combo in options_payload.get("combos", []) or []:
        if not isinstance(combo, dict):
            continue
        raw_legs = combo.get("legs") if isinstance(combo.get("legs"), list) else []
        legs_payload: list[dict[str, Any]] = [leg for leg in raw_legs if isinstance(leg, dict)]
        legs = []
        for leg in legs_payload:
            leg_mark = _coerce_float(leg.get("mark"))
            legs.append(
                {
                    "symbol": leg.get("symbol") or leg.get("underlying"),
                    "right": leg.get("right"),
                    "strike": _coerce_float(leg.get("strike")),
                    "expiry": leg.get("expiry"),
                    "quantity": _coerce_float(leg.get("quantity") or leg.get("qty")) or 0.0,
                    "mark": leg_mark,
                    "greeks": {
                        "delta": _coerce_float(leg.get("delta")) or 0.0,
                        "theta": _coerce_float(leg.get("theta")) or 0.0,
                    },
                    "mark_source": leg.get("mark_source"),
                    "stale_seconds": _coerce_int(leg.get("stale_seconds")),
                }
            )

        greeks_payload = combo.get("sum_greeks") or combo.get("greeks") or {}
        greeks = greeks_payload if isinstance(greeks_payload, dict) else {}
        pnl_combo = _coerce_float(combo.get("total_pnl_amount") or combo.get("day_pnl_amount")) or 0.0
        combos_view.append(
            {
                "combo_id": combo.get("combo_id") or combo.get("id"),
                "strategy": combo.get("strategy") or combo.get("name"),
                "underlying": combo.get("underlying"),
                "dte": combo.get("dte"),
                "net_price": combo.get("net_price"),
                "greeks": greeks,
                "pnl_unrealized": pnl_combo,
                "pnl_intraday": pnl_combo,
                "legs": legs,
            }
        )

    for leg in options_payload.get("legs", []) or []:
        if not isinstance(leg, dict):
            continue
        pnl_leg = _coerce_float(leg.get("total_pnl_amount") or leg.get("day_pnl_amount")) or 0.0
        legs_view.append(
            {
                "symbol": leg.get("symbol") or leg.get("underlying"),
                "underlying": leg.get("underlying"),
                "expiry": leg.get("expiry"),
                "strike": _coerce_float(leg.get("strike")),
                "right": leg.get("right"),
                "quantity": _coerce_float(leg.get("quantity") or leg.get("qty")) or 0.0,
                "mark": _coerce_float(leg.get("mark")),
                "greeks": {
                    "delta": _coerce_float(leg.get("delta")) or 0.0,
                    "theta": _coerce_float(leg.get("theta")) or 0.0,
                },
                "pnl_unrealized": pnl_leg,
                "pnl_intraday": pnl_leg,
                "mark_source": leg.get("mark_source"),
                "stale_seconds": _coerce_int(leg.get("stale_seconds")),
            }
        )

    return {
        "single_stocks": stocks_view,
        "option_combos": combos_view,
        "single_options": legs_view,
    }


def _is_positions_view_empty(view: Any) -> bool:
    if not isinstance(view, dict):
        return True
    try:
        stocks = view.get("single_stocks") or []
        combos = view.get("option_combos") or []
        singles = view.get("single_options") or []
    except AttributeError:
        return True
    return not any((stocks, combos, singles))


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
        positions_view = _empty_positions_view()

    if _is_positions_view_empty(positions_view):
        fallback_view = _build_positions_view_from_engine()
        if not _is_positions_view_empty(fallback_view):
            logger.debug("positions_view populated from engine fallback")
            positions_view = fallback_view

    return {
        "ts": ts,
        "session": session,
        "positions": positions,
        "positions_view": positions_view,
        "quotes": marks,
        "risk": risk,
    }
