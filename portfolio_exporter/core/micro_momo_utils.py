from __future__ import annotations


def clamp(x: float, lo: float, hi: float) -> float:
    if lo > hi:
        lo, hi = hi, lo
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def scale(x: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return clamp((x - lo) / (hi - lo), 0.0, 1.0)


def inv_scale(x: float, lo: float, hi: float) -> float:
    return 1.0 - scale(x, lo, hi)


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"1", "true", "y", "yes", "on"}


def safe_float(x: object, default: float = 0.0) -> float:
    try:
        return float(x)  # type: ignore[call-arg]
    except Exception:
        return default


def spread_pct(bid: float, ask: float) -> float | None:
    if bid <= 0 or ask <= 0:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return (ask - bid) / mid
