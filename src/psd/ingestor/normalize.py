from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from psd.core.mark_router import Session, choose_mark, pnl_option, pnl_stock

_ALLOWED_SESSION: set[str] = {"RTH", "EXT", "CLOSED"}


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _compute_percent(amount: float | None, basis: float | None) -> float | None:
    if amount is None or basis is None:
        return None
    if not math.isfinite(amount) or not math.isfinite(basis):
        return None
    denominator = abs(basis)
    if denominator == 0:
        return None
    return (amount / denominator) * 100


def _extract_price_source(raw: dict[str, Any]) -> str | None:
    for key in ("price_source", "priceSource", "mark_source", "markSource"):
        source_raw = raw.get(key)
        if isinstance(source_raw, str):
            stripped = source_raw.strip()
            if stripped:
                return stripped
    return None


def _extract_stale_hint(raw: dict[str, Any]) -> float | None:
    for key in (
        "stale_s",
        "stale_seconds",
        "staleSeconds",
        "age_s",
        "ageSeconds",
        "mark_age_s",
        "mark_age_seconds",
    ):
        stale_val = _coerce_float(raw.get(key))
        if stale_val is not None:
            return max(0.0, stale_val)
    for key in (
        "mark_ts",
        "mark_timestamp",
        "markTs",
        "price_ts",
        "priceTimestamp",
    ):
        ts_val = _coerce_float(raw.get(key))
        if ts_val is None:
            continue
        return max(0.0, time.time() - ts_val)
    return None


def _extract_explicit_mark(raw: dict[str, Any]) -> tuple[float, str] | None:
    for key, label in (
        ("mark", "mark"),
        ("price", "price"),
        ("marketPrice", "marketPrice"),
        ("market_price", "market_price"),
        ("lastPrice", "lastPrice"),
        ("market_price_last", "market_price_last"),
        ("market_price_mid", "market_price_mid"),
    ):
        value = raw.get(key)
        if isinstance(value, dict):
            candidate = _coerce_float(value.get("price") or value.get("value"))
        else:
            candidate = _coerce_float(value)
        if candidate is not None:
            return candidate, label
    return None


def _normalize_session(session: str | Session) -> Session:
    if isinstance(session, str) and session.upper() in _ALLOWED_SESSION:
        return session.upper()  # type: ignore[return-value]
    return "EXT"


def _norm_one(raw: dict[str, Any], session: str | Session) -> dict[str, Any]:
    sec = (raw.get("secType") or raw.get("asset_class") or "").upper()
    underlier = raw.get("symbol") or raw.get("underlier")
    tick = raw.get("tick") if isinstance(raw.get("tick"), dict) else {}

    normalized_session = _normalize_session(session)

    explicit_mark = _extract_explicit_mark(raw)
    price_source_hint = _extract_price_source(raw)
    stale_hint = _extract_stale_hint(raw)

    mark_raw: float
    fallback_source: str | None = None
    fallback_stale: float | None = 0.0

    if explicit_mark is not None:
        mark_raw, fallback_source = explicit_mark
    else:
        mark_raw, fallback_source, fallback_stale = choose_mark(
            tick, normalized_session
        )

    price_source_candidate = price_source_hint or (fallback_source or "unknown")
    price_source = (
        price_source_candidate.strip()
        if isinstance(price_source_candidate, str)
        else "unknown"
    )
    if not price_source:
        price_source = "unknown"

    stale_value = stale_hint if stale_hint is not None else fallback_stale
    stale_s_coerced = _coerce_float(stale_value)
    stale_s = max(0.0, stale_s_coerced) if stale_s_coerced is not None else 0.0

    qty = _coerce_float(raw.get("qty"))
    if qty is None:
        qty = _coerce_float(raw.get("position"))
    qty = qty if qty is not None else 0.0

    # Prefer avg_cost_unit (per-share) over avg_cost (total=per_share*multiplier)
    # IBKR provides options avg_cost as total cost, but mark is per-share
    avg_cost = _coerce_float(raw.get("avg_cost_unit"))
    if avg_cost is None:
        avg_cost = _coerce_float(raw.get("avg_cost"))
    if avg_cost is None:
        avg_cost = _coerce_float(raw.get("average_cost"))
    avg_cost = avg_cost if avg_cost is not None else 0.0

    previous_close = _coerce_float(raw.get("previous_close"))
    if previous_close is None:
        previous_close = _coerce_float(raw.get("prior_close"))
    if previous_close is None:
        previous_close = _coerce_float(raw.get("prev_close"))
    if previous_close is None:
        previous_close = _coerce_float(raw.get("prevClose"))

    raw_day_pct = _coerce_float(raw.get("day_pnl_percent"))
    if raw_day_pct is None:
        raw_day_pct = _coerce_float(raw.get("day_pnl_pct"))

    raw_total_pct = _coerce_float(raw.get("total_pnl_percent"))
    if raw_total_pct is None:
        raw_total_pct = _coerce_float(raw.get("pnl_unrealized_percent"))
    if raw_total_pct is None:
        raw_total_pct = _coerce_float(raw.get("pnl_unrealized_pct"))

    mark_coerced = _coerce_float(mark_raw)
    mark_value = mark_coerced if mark_coerced is not None else avg_cost

    multiplier = _coerce_float(raw.get("multiplier"))
    if multiplier is None:
        multiplier = 100.0 if sec in {"OPT", "FOP"} else 1.0

    pnl_value = (
        pnl_option(mark_value, avg_cost, qty, multiplier)
        if sec in {"OPT", "FOP"}
        else pnl_stock(mark_value, avg_cost, qty)
    )

    pnl_intraday_raw = _coerce_float(raw.get("pnl_intraday"))
    if pnl_intraday_raw is None:
        pnl_intraday_raw = _coerce_float(raw.get("day_pnl"))
    if pnl_intraday_raw is None:
        pnl_intraday_raw = _coerce_float(raw.get("day_pnl_amount"))
    pnl_leg_raw = _coerce_float(raw.get("pnl_leg"))
    pnl_prev_close = None
    if previous_close is not None and mark_coerced is not None:
        pnl_prev_close = (mark_value - previous_close) * qty * multiplier

    if pnl_intraday_raw is not None:
        pnl_intraday = pnl_intraday_raw
    elif pnl_prev_close is not None:
        pnl_intraday = pnl_prev_close
    elif pnl_leg_raw is not None:
        pnl_intraday = pnl_leg_raw
    else:
        pnl_intraday = pnl_value

    base: dict[str, Any] = {
        "secType": sec,
        "conId": raw.get("conId") or raw.get("conid"),
        "symbol": underlier,
        "qty": qty,
        "avg_cost": avg_cost,
        "multiplier": multiplier,
        "mark": mark_value,
        "price_source": price_source,
        "stale_s": stale_s,
        "pnl_intraday": pnl_intraday,
        "greeks": raw.get("greeks") or {},
    }

    if previous_close is not None:
        base["previous_close"] = previous_close

    if pnl_leg_raw is not None:
        base["pnl_leg"] = pnl_leg_raw

    pnl_intraday_value = _coerce_float(base.get("pnl_intraday"))
    if pnl_intraday_value is not None:
        base["pnl_day"] = float(pnl_intraday_value)

    # Compute unrealized P&L: (mark - avg_cost) * qty * multiplier
    fallback_unrealized = (mark_value - avg_cost) * qty * multiplier
    base["pnl_unrealized"] = fallback_unrealized
    base.setdefault("__fallback_unrealized", fallback_unrealized)

    day_basis = None
    if previous_close is not None:
        day_basis = abs(qty) * previous_close * multiplier
    total_basis = abs(qty) * avg_cost * multiplier

    day_pct = raw_day_pct if raw_day_pct is not None else _compute_percent(
        pnl_intraday, day_basis
    )
    total_pct = raw_total_pct if raw_total_pct is not None else _compute_percent(
        fallback_unrealized, total_basis
    )

    if day_pct is not None:
        base["day_pnl_percent"] = day_pct
        base["day_pnl_pct"] = day_pct
    if total_pct is not None:
        base["total_pnl_percent"] = total_pct
        base["pnl_unrealized_percent"] = total_pct
        base["pnl_unrealized_pct"] = total_pct

    if sec in {"OPT", "FOP"}:
        base.update(
            {
                "right": raw.get("right"),
                "strike": raw.get("strike"),
                "expiry": raw.get("expiry"),
            }
        )
    return base


def _leg_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("symbol"),
        entry.get("secType"),
        entry.get("expiry"),
        entry.get("right"),
        entry.get("strike"),
    )


def _stable_combo_id(parts: object, prefix: str) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _aggregate_greeks(legs: Iterable[dict[str, Any]]) -> dict[str, float]:
    totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0}
    for leg in legs:
        greeks = leg.get("greeks") or {}
        totals["delta"] += float(greeks.get("delta", 0.0) or 0.0)
        totals["gamma"] += float(greeks.get("gamma", 0.0) or 0.0)
        totals["theta"] += float(greeks.get("theta", 0.0) or 0.0)
    return totals


def split_positions(
    raw_positions: list[dict[str, Any]], session: str | Session
) -> dict[str, Any]:
    normalized_session = _normalize_session(session)
    norm_rows: list[dict[str, Any]] = []
    conid_index: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    key_index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)

    for raw in raw_positions:
        try:
            entry = _norm_one(raw, normalized_session)
        except Exception:
            continue
        norm_rows.append(entry)
        conid = entry.get("conId")
        if conid is not None:
            conid_index[conid].append(entry)
        key_index[_leg_key(entry)].append(entry)

    legs_of_combo: set[int] = set()
    combos: list[dict[str, Any]] = []

    def borrow_leg(leg_ref: dict[str, Any]) -> dict[str, Any] | None:
        conid = leg_ref.get("conId") or leg_ref.get("conid")
        if conid is not None and conid in conid_index:
            bucket = conid_index[conid]
            while bucket:
                candidate = bucket.pop(0)
                if id(candidate) not in legs_of_combo:
                    return candidate
        key = _leg_key(leg_ref)
        bucket = key_index.get(key)
        if not bucket:
            return None
        for idx, candidate in enumerate(bucket):
            if id(candidate) in legs_of_combo:
                continue
            bucket.pop(idx)
            return candidate
        return None

    for raw in raw_positions:
        sec_type = (raw.get("secType") or raw.get("asset_class") or "").upper()
        if sec_type != "BAG":
            continue
        combo_legs = raw.get("combo_legs")
        if not isinstance(combo_legs, list):
            continue
        legs: list[dict[str, Any]] = []
        for leg in combo_legs:
            if not isinstance(leg, dict):
                continue
            match = borrow_leg(leg)
            if match is None:
                continue
            legs.append(match)
            legs_of_combo.add(id(match))
        if not legs:
            continue
        combo_id = _stable_combo_id(
            sorted((leg.get("conId"), leg.get("qty")) for leg in legs),
            "combo",
        )
        combos.append(
            {
                "combo_id": combo_id,
                "name": raw.get("description") or raw.get("symbol") or "Combo",
                "underlier": raw.get("symbol") or raw.get("underlier"),
                "legs": legs,
                "pnl_intraday": sum(leg.get("pnl_intraday", 0.0) for leg in legs),
                "greeks_agg": _aggregate_greeks(legs),
            }
        )

    unassigned_options = [
        entry
        for entry in norm_rows
        if entry.get("secType") in {"OPT", "FOP"} and id(entry) not in legs_of_combo
    ]

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for leg in unassigned_options:
        grouped[(leg.get("symbol"), leg.get("expiry"), leg.get("right"))].append(leg)

    for key, legs in grouped.items():
        longs = [leg for leg in legs if leg.get("qty", 0.0) > 0]
        shorts = [leg for leg in legs if leg.get("qty", 0.0) < 0]
        if not longs or not shorts:
            continue
        longs.sort(key=lambda leg: abs(float(leg.get("qty", 0.0))), reverse=True)
        shorts.sort(key=lambda leg: abs(float(leg.get("qty", 0.0))), reverse=True)
        while longs and shorts:
            long_leg = longs.pop(0)
            short_leg = shorts.pop(0)
            qty_long = abs(float(long_leg.get("qty", 0.0)))
            qty_short = abs(float(short_leg.get("qty", 0.0)))
            if not math.isclose(qty_long, qty_short, rel_tol=1e-9, abs_tol=1e-9):
                continue
            legs_of_combo.add(id(long_leg))
            legs_of_combo.add(id(short_leg))
            combo_name_parts = [str(val) for val in key if val]
            combo_name = " ".join(combo_name_parts) or "Vertical"
            combo_id = _stable_combo_id(
                (long_leg.get("conId"), short_leg.get("conId"), qty_long),
                "vertical",
            )
            combo_legs = [long_leg, short_leg]
            combos.append(
                {
                    "combo_id": combo_id,
                    "name": combo_name,
                    "underlier": key[0],
                    "legs": combo_legs,
                    "pnl_intraday": sum(
                        leg.get("pnl_intraday", 0.0) for leg in combo_legs
                    ),
                    "greeks_agg": _aggregate_greeks(combo_legs),
                }
            )

    single_options = [
        entry
        for entry in norm_rows
        if entry.get("secType") in {"OPT", "FOP"} and id(entry) not in legs_of_combo
    ]

    single_stocks = [entry for entry in norm_rows if entry.get("secType") == "STK"]

    combos.sort(key=lambda combo: combo.get("pnl_intraday", 0.0), reverse=True)
    single_options.sort(key=lambda leg: leg.get("pnl_intraday", 0.0), reverse=True)
    single_stocks.sort(key=lambda leg: leg.get("pnl_intraday", 0.0), reverse=True)

    return {
        "single_stocks": single_stocks,
        "option_combos": combos,
        "single_options": single_options,
    }
