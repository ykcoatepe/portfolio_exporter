# SPDX-License-Identifier: MIT

"""Playbook evaluation helpers for option combos and single legs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any, Mapping, Sequence

from ..core.models import Quote
from .detector import OptionCombo, OptionLegSnapshot
from .taxonomy import ComboStrategy

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
HUNDRED = Decimal("100")

LOW_BAND = (Decimal("0.50"), Decimal("0.70"))
MID_BAND = (Decimal("0.40"), Decimal("0.60"))
HIGH_BAND = (Decimal("0.30"), Decimal("0.50"))

CREDIT_STRATEGIES = {
    ComboStrategy.IRON_CONDOR,
    ComboStrategy.IRON_BUTTERFLY,
    ComboStrategy.VERTICAL,
}


@dataclass(frozen=True)
class PlaybookEvaluation:
    """Bundle of playbook metrics for combos and single legs."""

    combo_targets: dict[str, dict[str, Any]]
    leg_targets: dict[str, dict[str, Any]]
    meta: dict[str, Any]


def evaluate_playbook_targets(
    combos: Sequence[OptionCombo],
    legs: Sequence[OptionLegSnapshot],
    quotes: Mapping[str, Quote],
) -> PlaybookEvaluation:
    """Return per-instrument playbook guidance derived from the combo snapshot."""

    vix_source, vix_value = _resolve_vix(quotes)
    band_low, band_high = _band_for_vix(vix_value)
    meta: dict[str, Any] = {}
    band_payload = _band_payload(band_low, band_high)
    if band_payload is not None or vix_value is not None:
        meta = {
            "vix": _to_float(vix_value),
            "vix_source": vix_source,
            "tp_band_pct": band_payload,
        }

    combo_targets: dict[str, dict[str, Any]] = {}
    for combo in combos:
        combo_targets[combo.combo_id] = _evaluate_combo(combo, band_low, band_high)

    leg_targets: dict[str, dict[str, Any]] = {}
    for leg in legs:
        leg_targets[leg.leg_id] = _evaluate_single_leg(leg, band_low, band_high)

    return PlaybookEvaluation(combo_targets=combo_targets, leg_targets=leg_targets, meta=meta)


def _evaluate_combo(combo: OptionCombo, band_low: Decimal, band_high: Decimal) -> dict[str, Any]:
    payload = _default_payload()
    band = _band_payload(band_low, band_high)
    payload["tp_band_pct"] = band
    if band:
        payload["tp_band_low_pct"], payload["tp_band_high_pct"] = band

    contracts = _combo_contracts(combo)
    multiplier = _combo_multiplier(combo)
    pnl = combo.total_pnl

    if contracts <= ZERO or multiplier <= ZERO or pnl is None:
        return payload

    if combo.net_price < ZERO and combo.strategy in CREDIT_STRATEGIES:
        return _eval_credit_combo(combo, contracts, multiplier, pnl, band_low, band_high)

    if combo.net_price > ZERO and combo.strategy == ComboStrategy.VERTICAL:
        return _eval_debit_combo(combo, multiplier, pnl)

    return payload


def _eval_credit_combo(
    combo: OptionCombo,
    contracts: Decimal,
    multiplier: Decimal,
    pnl: Decimal,
    band_low: Decimal,
    band_high: Decimal,
) -> dict[str, Any]:
    payload = _default_payload()
    band = _band_payload(band_low, band_high)
    payload["tp_band_pct"] = band
    if band:
        payload["tp_band_low_pct"], payload["tp_band_high_pct"] = band
    payload["sl_r"] = 1.0

    max_profit_total = abs(combo.net_price) * multiplier
    credit_per_share = _safe_div(abs(combo.net_price), contracts)
    widths = _combo_widths(combo)
    max_width = max(widths) if widths else None
    max_loss_total: Decimal | None = None
    if max_width is not None and credit_per_share is not None:
        loss_per_share = max_width - credit_per_share
        if loss_per_share > ZERO:
            max_loss_total = loss_per_share * multiplier * contracts
        else:
            max_loss_total = ZERO

    goal_low = band_low * max_profit_total
    goal_high = band_high * max_profit_total
    tp_hit = pnl >= goal_low
    tp_done = pnl >= goal_high
    sl_hit = bool(max_loss_total is not None and pnl <= -max_loss_total)

    pct_goal = _safe_div(pnl, goal_high)
    pct_max = _safe_div(pnl, max_profit_total)
    payload.update(
        {
            "tp_hit": tp_hit,
            "tp_done": tp_done,
            "sl_hit": sl_hit,
            "exit_as_unit": tp_done or sl_hit,
            "progress_pct_of_goal": _to_float(pct_goal),
            "progress_pct_of_max": _to_float(pct_max),
            "progress": {
                "pct_of_goal": _to_float(pct_goal),
                "pct_of_max_profit_or_r": _to_float(pct_max),
            },
            "next_action": _next_action(tp_done=tp_done, tp_hit=tp_hit, sl_hit=sl_hit),
        }
    )
    if max_loss_total is not None and max_loss_total > ZERO:
        payload["sl_r"] = 1.0
    else:
        payload["sl_r"] = None
    return payload


def _eval_debit_combo(combo: OptionCombo, multiplier: Decimal, pnl: Decimal) -> dict[str, Any]:
    payload = _default_payload()
    band = [_to_float(ONE), _to_float(TWO)]
    payload["tp_band_pct"] = band
    payload["tp_band_low_pct"], payload["tp_band_high_pct"] = band
    r_total = combo.net_price * multiplier
    if r_total <= ZERO:
        return payload

    target = r_total * TWO
    tp_hit = pnl >= r_total
    tp_done = pnl >= target
    sl_hit = pnl <= -r_total

    pct_goal = _safe_div(pnl, target)
    pct_max = _safe_div(pnl, r_total)
    payload.update(
        {
            "sl_r": 1.0,
            "tp_hit": tp_hit,
            "tp_done": tp_done,
            "sl_hit": sl_hit,
            "exit_as_unit": tp_done or sl_hit,
            "progress_pct_of_goal": _to_float(pct_goal),
            "progress_pct_of_max": _to_float(pct_max),
            "progress": {
                "pct_of_goal": _to_float(pct_goal),
                "pct_of_max_profit_or_r": _to_float(pct_max),
            },
            "next_action": _next_action(tp_done=tp_done, tp_hit=tp_hit, sl_hit=sl_hit),
        }
    )
    return payload


def _evaluate_single_leg(leg: OptionLegSnapshot, band_low: Decimal, band_high: Decimal) -> dict[str, Any]:
    payload = _default_payload()
    quantity = leg.quantity
    pnl = leg.total_pnl
    multiplier = abs(leg.multiplier) if leg.multiplier is not None else HUNDRED

    if quantity is None or quantity == ZERO or pnl is None or multiplier <= ZERO:
        return payload

    contracts = abs(quantity)

    if quantity < ZERO:
        band = _band_payload(band_low, band_high)
        payload["tp_band_pct"] = band
        if band:
            payload["tp_band_low_pct"], payload["tp_band_high_pct"] = band
        credit_total = _leg_credit_total(leg, multiplier)
        if credit_total <= ZERO:
            return payload
        goal_high = band_high * credit_total
        tp_hit = pnl >= band_low * credit_total
        tp_done = pnl >= goal_high
        sl_threshold = credit_total
        sl_hit = pnl <= -sl_threshold
        pct_goal = _safe_div(pnl, goal_high)
        pct_max = _safe_div(pnl, credit_total)
        payload.update(
            {
                "sl_r": 1.0,
                "tp_hit": tp_hit,
                "tp_done": tp_done,
                "sl_hit": sl_hit,
                "exit_as_unit": tp_done or sl_hit,
                "progress_pct_of_goal": _to_float(pct_goal),
                "progress_pct_of_max": _to_float(pct_max),
                "progress": {
                    "pct_of_goal": _to_float(pct_goal),
                    "pct_of_max_profit_or_r": _to_float(pct_max),
                },
                "next_action": _next_action(tp_done=tp_done, tp_hit=tp_hit, sl_hit=sl_hit),
            }
        )
        return payload

    band = [_to_float(ONE), _to_float(TWO)]
    payload["tp_band_pct"] = band
    payload["tp_band_low_pct"], payload["tp_band_high_pct"] = band
    r_total = _leg_debit_total(leg, multiplier)
    if r_total <= ZERO:
        return payload

    target = r_total * TWO
    tp_hit = pnl >= r_total
    tp_done = pnl >= target
    sl_hit = pnl <= -r_total
    pct_goal = _safe_div(pnl, target)
    pct_max = _safe_div(pnl, r_total)
    payload.update(
        {
            "sl_r": 1.0,
            "tp_hit": tp_hit,
            "tp_done": tp_done,
            "sl_hit": sl_hit,
            "exit_as_unit": tp_done or sl_hit,
            "progress_pct_of_goal": _to_float(pct_goal),
            "progress_pct_of_max": _to_float(pct_max),
            "progress": {
                "pct_of_goal": _to_float(pct_goal),
                "pct_of_max_profit_or_r": _to_float(pct_max),
            },
            "next_action": _next_action(tp_done=tp_done, tp_hit=tp_hit, sl_hit=sl_hit),
        }
    )
    return payload


def _next_action(*, tp_done: bool, tp_hit: bool, sl_hit: bool) -> str:
    if sl_hit:
        return "CUT"
    if tp_done:
        return "TAKE_PROFIT"
    if tp_hit:
        return "TRIM"
    return "HOLD"


def _default_payload() -> dict[str, Any]:
    return {
        "tp_band_pct": None,
        "tp_band_low_pct": None,
        "tp_band_high_pct": None,
        "sl_r": None,
        "tp_hit": False,
        "tp_done": False,
        "sl_hit": False,
        "progress_pct_of_goal": None,
        "progress_pct_of_max": None,
        "progress": {
            "pct_of_goal": None,
            "pct_of_max_profit_or_r": None,
        },
        "next_action": "HOLD",
        "exit_as_unit": False,
    }


def _combo_contracts(combo: OptionCombo) -> Decimal:
    quantities = [abs(leg.quantity) for leg in combo.legs if leg.quantity is not None and leg.quantity != ZERO]
    return min(quantities, default=ZERO)


def _combo_multiplier(combo: OptionCombo) -> Decimal:
    for leg in combo.legs:
        if leg.multiplier is not None and leg.multiplier != ZERO:
            return abs(leg.multiplier)
    return HUNDRED


def _combo_widths(combo: OptionCombo) -> list[Decimal]:
    call_legs = [leg for leg in combo.legs if (leg.right or "").upper().startswith("CALL")]
    put_legs = [leg for leg in combo.legs if (leg.right or "").upper().startswith("PUT")]
    widths: list[Decimal] = []
    for legs in (call_legs, put_legs):
        width = _vertical_width(legs)
        if width is not None:
            widths.append(width)
    if combo.strategy == ComboStrategy.VERTICAL:
        width = _vertical_width(combo.legs)
        if width is not None:
            widths.append(width)
    return widths


def _vertical_width(legs: Sequence[OptionLegSnapshot]) -> Decimal | None:
    short_leg = next((leg for leg in legs if leg.quantity is not None and leg.quantity < ZERO), None)
    long_leg = next((leg for leg in legs if leg.quantity is not None and leg.quantity > ZERO), None)
    if short_leg is None or long_leg is None:
        return None
    if short_leg.strike is None or long_leg.strike is None:
        return None
    return abs(short_leg.strike - long_leg.strike)


def _leg_credit_total(leg: OptionLegSnapshot, multiplier: Decimal) -> Decimal:
    basis = leg.total_basis
    if basis is not None:
        return abs(basis)
    try:
        return abs(leg.avg_cost * leg.quantity * multiplier)
    except (TypeError, InvalidOperation):
        return ZERO


def _leg_debit_total(leg: OptionLegSnapshot, multiplier: Decimal) -> Decimal:
    basis = leg.total_basis
    if basis is not None:
        return abs(basis)
    try:
        return abs(leg.avg_cost * leg.quantity * multiplier)
    except (TypeError, InvalidOperation):
        return ZERO


def _safe_div(numerator: Decimal, denominator: Decimal | None) -> Decimal | None:
    if denominator is None or denominator == ZERO:
        return None
    try:
        return numerator / denominator
    except (DivisionByZero, InvalidOperation):
        return None


def _band_for_vix(vix: Decimal | None) -> tuple[Decimal, Decimal]:
    if vix is None:
        return MID_BAND
    if vix < Decimal("15"):
        return LOW_BAND
    if vix <= Decimal("25"):
        return MID_BAND
    return HIGH_BAND


def _band_payload(low: Decimal, high: Decimal) -> list[float] | None:
    if low is None or high is None:
        return None
    return [_to_float(low), _to_float(high)]


def _resolve_vix(quotes: Mapping[str, Quote]) -> tuple[str | None, Decimal | None]:
    for symbol in ("^VIX", "VIX"):
        quote = quotes.get(symbol)
        if quote is None:
            continue
        for attr in ("last", "mid", "previous_close"):
            value = getattr(quote, attr, None)
            if value is not None and value > ZERO:
                return symbol, Decimal(value)
    return None, None


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
