from __future__ import annotations

import math
import os
import time
from collections.abc import Iterable
from typing import Any, cast

from psd.analytics.combos import recognize
from psd.models import Kind, OptionLeg, Position, Sleeve

# Default staleness threshold: 15 minutes (900 seconds).
_DEFAULT_STALE_THRESHOLD = 900.0
try:
    _ENV_THRESHOLD = float(os.getenv("PSD_STALE_QUOTE_THRESHOLD", "") or _DEFAULT_STALE_THRESHOLD)
    if math.isnan(_ENV_THRESHOLD) or _ENV_THRESHOLD <= 0:
        raise ValueError
    DEFAULT_STALE_THRESHOLD = _ENV_THRESHOLD
except (TypeError, ValueError):
    DEFAULT_STALE_THRESHOLD = _DEFAULT_STALE_THRESHOLD


VALID_SLEEVES: set[str] = {"core", "momo", "alpha", "theta", "alts", "meme"}


def compute_stats(
    snapshot: dict[str, Any] | None,
    *,
    now: float | None = None,
    stale_threshold: float | None = None,
) -> dict[str, Any]:
    """Compute aggregate stats for the PSD dashboard snapshot.

    Returns a dictionary with keys:
    - positions_count
    - option_legs_count
    - combos_matched
    - stale_quotes_count
    - stale_threshold_seconds
    """
    if not isinstance(snapshot, dict):
        return {
            "positions_count": 0,
            "option_legs_count": 0,
            "combos_matched": 0,
            "stale_quotes_count": 0,
            "stale_threshold_seconds": DEFAULT_STALE_THRESHOLD,
        }

    positions_raw = snapshot.get("positions")
    if not isinstance(positions_raw, list):
        positions_raw = []
    quotes = snapshot.get("quotes")
    if not isinstance(quotes, dict):
        quotes = {}
    ts = snapshot.get("ts")

    threshold = (
        _coerce_positive_float(DEFAULT_STALE_THRESHOLD if stale_threshold is None else stale_threshold)
        or DEFAULT_STALE_THRESHOLD
    )

    now_ts = _coerce_timestamp(now)
    if now_ts is None:
        now_ts = _coerce_timestamp(ts)
    if now_ts is None:
        now_ts = time.time()

    positions: list[Position] = []
    option_leg_count = 0
    for idx, raw in enumerate(positions_raw):
        pos, leg_n = _coerce_position(raw, idx)
        option_leg_count += leg_n
        if pos is not None:
            positions.append(pos)

    combos_matched = 0
    if positions:
        try:
            combos, _orphans = recognize(positions)
            combos_matched = len(combos)
        except Exception:
            combos_matched = 0

    stale_quotes_count = _count_stale_quotes(quotes, now_ts, threshold)

    return {
        "positions_count": len(positions_raw),
        "option_legs_count": option_leg_count,
        "combos_matched": combos_matched,
        "stale_quotes_count": int(stale_quotes_count),
        "stale_threshold_seconds": threshold,
    }


def _coerce_position(raw: Any, idx: int) -> tuple[Position | None, int]:
    if not isinstance(raw, dict):
        return None, 0

    legs: list[OptionLeg] = []
    legs_raw = raw.get("legs")
    if isinstance(legs_raw, (list, tuple)):
        for leg_raw in legs_raw:
            leg = _coerce_leg(leg_raw)
            if leg is not None:
                legs.append(leg)

    leg_count = len(legs)

    symbol = str(raw.get("symbol") or raw.get("underlying") or raw.get("ticker") or "").strip()
    if not symbol:
        return None, leg_count

    uid = str(
        raw.get("uid")
        or raw.get("id")
        or raw.get("position_id")
        or raw.get("localSymbol")
        or f"{symbol}-{idx}"
    )

    sleeve_raw = str(raw.get("sleeve") or "theta").lower()
    sleeve_norm = sleeve_raw if sleeve_raw in VALID_SLEEVES else "theta"
    sleeve_value = cast(Sleeve, sleeve_norm)

    kind_raw = str(raw.get("kind") or ("option" if leg_count else "equity")).lower()
    if kind_raw not in {"equity", "option", "credit_spread", "iron_condor"}:
        kind_raw = "option" if leg_count else "equity"
    kind_value = cast(Kind, kind_raw)

    qty = _coerce_int(raw, ["qty", "quantity", "position", "contracts"], default=0)
    mark = _coerce_float(raw, ["mark", "price", "marketPrice", "lastPrice", "mid", "avg_price"])

    try:
        position = Position(
            uid=uid,
            symbol=symbol,
            sleeve=sleeve_value,
            kind=kind_value,
            qty=qty,
            mark=mark,
            legs=legs,
        )
        return position, leg_count
    except Exception:
        return None, leg_count


def _coerce_leg(raw: Any) -> OptionLeg | None:
    if not isinstance(raw, dict):
        return None

    symbol = str(raw.get("symbol") or raw.get("underlying") or "").strip()
    expiry = str(
        raw.get("expiry")
        or raw.get("expiration")
        or raw.get("lastTradeDate")
        or raw.get("exp")
        or raw.get("expiry_date")
        or ""
    ).strip()

    right_raw = str(raw.get("right") or raw.get("option_type") or raw.get("type") or "").upper()
    if right_raw.startswith("C"):
        right = "C"
    elif right_raw.startswith("P"):
        right = "P"
    else:
        return None

    qty = _coerce_int(raw, ["qty", "quantity", "position", "contracts", "size"], default=0)
    strike = _coerce_float(raw, ["strike", "strikePrice", "strike_price"])
    price = _coerce_float(raw, ["price", "mark", "mid", "entry_price", "avg_price"])

    if not symbol or not expiry or qty == 0 or strike is None or price is None:
        return None

    try:
        return OptionLeg(
            symbol=symbol,
            expiry=expiry,
            right=right,  # type: ignore[arg-type]
            strike=float(strike),
            qty=qty,
            price=float(price),
        )
    except Exception:
        return None


def _coerce_float(raw: Any, keys: Iterable[str]) -> float | None:
    if not isinstance(raw, dict):
        return None
    for key in keys:
        if key not in raw:
            continue
        val = raw.get(key)
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        if math.isnan(fval):
            continue
        return fval
    return None


def _coerce_int(raw: Any, keys: Iterable[str], *, default: int = 0) -> int:
    if isinstance(raw, dict):
        for key in keys:
            if key not in raw:
                continue
            val = raw.get(key)
            try:
                ival = int(float(val))
            except (TypeError, ValueError):
                continue
            return ival
    return default


def _coerce_timestamp(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if math.isnan(float(value)):
                return None
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            return float(stripped)
    except (TypeError, ValueError):
        return None
    return None


def _coerce_positive_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        fval = float(value)
        if math.isnan(fval) or fval <= 0:
            return None
        return fval
    except (TypeError, ValueError):
        return None


def _count_stale_quotes(quotes: dict[str, Any], now_ts: float, threshold: float) -> int:
    count = 0
    for value in quotes.values():
        if _is_stale_quote(value, now_ts, threshold):
            count += 1
    return count


def _is_stale_quote(value: Any, now_ts: float, threshold: float) -> bool:
    if isinstance(value, dict):
        if any(bool(value.get(key)) for key in ("stale", "is_stale", "stale_flag", "delayed", "isDelayed")):
            return True

        age = _coerce_float(
            value,
            [
                "age",
                "age_s",
                "age_sec",
                "age_seconds",
                "stale_seconds",
                "ageSeconds",
                "quote_age",
            ],
        )
        if age is not None and age > threshold:
            return True

        ts = None
        for key in (
            "ts",
            "timestamp",
            "quote_ts",
            "last_updated",
            "last_update",
            "updated_at",
            "quoteTimestamp",
        ):
            ts = _coerce_timestamp(value.get(key)) if key in value else None
            if ts is not None:
                break
        if ts is not None and (now_ts - ts) > threshold:
            return True

    return False
