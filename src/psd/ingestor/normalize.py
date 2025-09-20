from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from psd.core.mark_router import Session, choose_mark, pnl_option, pnl_stock

_ALLOWED_SESSION: set[str] = {"RTH", "EXT", "CLOSED"}


def _normalize_session(session: str | Session) -> Session:
    if isinstance(session, str) and session.upper() in _ALLOWED_SESSION:
        return session.upper()  # type: ignore[return-value]
    return "EXT"


def _norm_one(raw: dict[str, Any], session: str | Session) -> dict[str, Any]:
    sec = (raw.get("secType") or raw.get("asset_class") or "").upper()
    underlier = raw.get("symbol") or raw.get("underlier")
    tick = raw.get("tick") if isinstance(raw.get("tick"), dict) else {}

    normalized_session = _normalize_session(session)
    mark_raw, source, stale_s = choose_mark(tick, normalized_session)

    qty = float(raw.get("qty", raw.get("position", 0.0)) or 0.0)
    avg_cost = float(raw.get("avg_cost", raw.get("average_cost", 0.0)) or 0.0)
    mark_value = mark_raw if math.isfinite(mark_raw) else avg_cost

    multiplier = 1.0
    if sec in {"OPT", "FOP"}:
        multiplier = float(raw.get("multiplier", 100.0) or 100.0)

    pnl_value = (
        pnl_option(mark_value, avg_cost, qty, multiplier)
        if sec in {"OPT", "FOP"}
        else pnl_stock(mark_value, avg_cost, qty)
    )

    base: dict[str, Any] = {
        "secType": sec,
        "conId": raw.get("conId") or raw.get("conid"),
        "symbol": underlier,
        "qty": qty,
        "avg_cost": avg_cost,
        "multiplier": multiplier,
        "mark": mark_value,
        "price_source": source,
        "stale_s": stale_s,
        "pnl_intraday": pnl_value,
        "greeks": raw.get("greeks") or {},
    }

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


def _aggregate_greeks(legs: Iterable[dict[str, Any]]) -> dict[str, float]:
    totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0}
    for leg in legs:
        greeks = leg.get("greeks") or {}
        totals["delta"] += float(greeks.get("delta", 0.0) or 0.0)
        totals["gamma"] += float(greeks.get("gamma", 0.0) or 0.0)
        totals["theta"] += float(greeks.get("theta", 0.0) or 0.0)
    return totals


def split_positions(raw_positions: list[dict[str, Any]], session: str | Session) -> dict[str, Any]:
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
        combo_id = str(hash(tuple(sorted((leg.get("conId"), leg.get("qty")) for leg in legs))))
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
            combo_id = f"vertical:{hash((long_leg.get('conId'), short_leg.get('conId'), qty_long))}"
            combo_legs = [long_leg, short_leg]
            combos.append(
                {
                    "combo_id": combo_id,
                    "name": combo_name,
                    "underlier": key[0],
                    "legs": combo_legs,
                    "pnl_intraday": sum(leg.get("pnl_intraday", 0.0) for leg in combo_legs),
                    "greeks_agg": _aggregate_greeks(combo_legs),
                }
            )

    single_options = [
        entry
        for entry in norm_rows
        if entry.get("secType") in {"OPT", "FOP"} and id(entry) not in legs_of_combo
    ]

    single_stocks = [
        entry for entry in norm_rows if entry.get("secType") == "STK"
    ]

    combos.sort(key=lambda combo: combo.get("pnl_intraday", 0.0), reverse=True)
    single_options.sort(key=lambda leg: leg.get("pnl_intraday", 0.0), reverse=True)
    single_stocks.sort(key=lambda leg: leg.get("pnl_intraday", 0.0), reverse=True)

    return {
        "single_stocks": single_stocks,
        "option_combos": combos,
        "single_options": single_options,
    }
