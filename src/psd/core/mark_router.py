from __future__ import annotations

import math
import time
from typing import Any, Literal

Session = Literal["RTH", "EXT", "CLOSED"]


def _coerce_tick_value(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    try:
        number = float(value)  # pragma: no cover - defensive for string numbers
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def choose_mark(tick: dict[str, Any] | None, session: Session) -> tuple[float, str, float]:
    """Select an appropriate mark price for the given tick snapshot."""
    snapshot = tick or {}
    try:
        ts_raw = snapshot.get("ts", time.time())
        ts_value = float(ts_raw)
    except (TypeError, ValueError):
        ts_value = time.time()
    now = time.time()
    stale_s = float(max(0.0, now - ts_value))

    order = ["mid", "model", "yahoo"] if session != "RTH" else ["last", "mid", "model", "yahoo"]

    for key in order:
        candidate = _coerce_tick_value(snapshot.get(key))
        if candidate is not None:
            return candidate, key, stale_s

    fallback = _coerce_tick_value(snapshot.get("last_close"))
    return (fallback if fallback is not None else float("nan"), "last_close", stale_s)


def pnl_stock(mark: float, avg_cost: float, qty: float) -> float:
    return (mark - avg_cost) * qty


def pnl_option(mark: float, avg_cost: float, qty: float, multiplier: float) -> float:
    return (mark - avg_cost) * qty * multiplier
