# SPDX-License-Identifier: MIT

"""Helpers for grouping duplicate option combos and generating labels."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence

from .detector import OptionCombo, OptionLegSnapshot
from .taxonomy import ComboStrategy

ZERO = Decimal("0")
_MARK_SOURCE_PRIORITY = {"MID": 0, "LAST": 1, "PREV": 2, "MISSING": 3}


@dataclass(frozen=True)
class LegDisplay:
    """Friendly text for rendering individual legs."""

    leg_label: str
    short_ul: str
    expiry_short: str | None


@dataclass(frozen=True)
class ComboDisplay:
    """Friendly text for rendering grouped combos."""

    combo_label: str
    short_ul: str
    expiry_short: str | None


@dataclass
class _LegAccumulator:
    symbol: str
    right: str
    strike: Decimal
    expiry: str
    quantity: Decimal = ZERO
    delta: Decimal = ZERO
    gamma: Decimal = ZERO
    theta: Decimal = ZERO
    vega: Decimal = ZERO
    mark_sum: Decimal = ZERO
    mark_weight: Decimal = ZERO
    mark_source: str = "MISSING"
    stale_seconds: int | None = None

    def add(self, leg: OptionLegSnapshot) -> None:
        self.quantity += leg.quantity
        self.delta += leg.delta * leg.quantity * leg.multiplier if leg.delta is not None else ZERO
        self.gamma += leg.gamma * leg.quantity * leg.multiplier if leg.gamma is not None else ZERO
        self.theta += leg.theta * leg.quantity * leg.multiplier if leg.theta is not None else ZERO
        self.vega += leg.vega * leg.quantity * leg.multiplier if leg.vega is not None else ZERO
        if leg.mark is not None:
            weight = abs(leg.quantity)
            self.mark_sum += leg.mark * weight
            self.mark_weight += weight
        self.mark_source = _choose_mark_source(self.mark_source, leg.mark_source)
        self.stale_seconds = _max_staleness(self.stale_seconds, leg.stale_seconds)

    def to_payload(self, display: LegDisplay, combo_group_id: str) -> dict[str, Any]:
        mark = (self.mark_sum / self.mark_weight) if self.mark_weight > 0 else None
        return {
            "symbol": self.symbol,
            "underlying": display.short_ul,
            "right": self.right,
            "strike": _to_float(self.strike),
            "expiry": self.expiry,
            "quantity": _to_float(self.quantity),
            "sum_greeks": {
                "delta": _to_float(self.delta),
                "gamma": _to_float(self.gamma),
                "theta": _to_float(self.theta),
                "vega": _to_float(self.vega),
            },
            "mark": _to_float(mark),
            "mark_source": self.mark_source,
            "stale_seconds": self.stale_seconds,
            "combo_group_id": combo_group_id,
            "display": {
                "leg_label": display.leg_label,
                "short_ul": display.short_ul,
                "expiry_short": display.expiry_short,
            },
        }


@dataclass(frozen=True)
class _LabelLeg:
    right: str
    strike: Decimal
    expiry: str


@dataclass
class ComboGroup:
    """Aggregated combo group with convenience labels."""

    combo_group_id: str
    strategy: ComboStrategy
    underlying: str
    group_qty: Decimal
    net_price_weighted: Decimal
    weight_total: Decimal
    dte_min: int
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    mark_source: str
    stale_seconds: int | None
    leg_accumulators: dict[tuple[str, str, Decimal], _LegAccumulator] = field(default_factory=dict)
    display: ComboDisplay | None = None

    def to_payload(self) -> dict[str, Any]:
        net_price = self.net_price_weighted / self.weight_total if self.weight_total else ZERO
        label_legs = [
            _LabelLeg(right=acc.right, strike=acc.strike, expiry=acc.expiry)
            for acc in self.leg_accumulators.values()
        ]
        label_text = format_combo_label(self.strategy, label_legs, self.dte_min, net_price, self.underlying)
        short_ul = self.display.short_ul if self.display else self.underlying.upper()
        expiry_short = self.display.expiry_short if self.display else None
        if expiry_short is None:
            expiry_short = next((format_expiry_short(acc.expiry) for acc in self.leg_accumulators.values()), None)

        payload = {
            "combo_group_id": self.combo_group_id,
            "strategy": self.strategy.value,
            "underlying": self.underlying,
            "group_qty": _to_float(self.group_qty),
            "group_net_price": _to_float(net_price),
            "dte": self.dte_min,
            "sum_greeks": {
                "delta": _to_float(self.delta),
                "gamma": _to_float(self.gamma),
                "theta": _to_float(self.theta),
                "vega": _to_float(self.vega),
            },
            "mark_source": self.mark_source,
            "stale_seconds": self.stale_seconds,
            "label": label_text,
            "display": {
                "combo_label": label_text,
                "short_ul": short_ul,
                "expiry_short": expiry_short,
            },
        }
        legs_payload: list[dict[str, Any]] = []
        for acc in self.leg_accumulators.values():
            leg_display = build_leg_display(self.underlying, acc.strike, acc.right, acc.expiry)
            legs_payload.append(acc.to_payload(leg_display, self.combo_group_id))
        payload["legs"] = sorted(
            legs_payload,
            key=lambda row: (row["expiry"], row["right"], row["strike"]),
        )
        return payload


@dataclass(frozen=True)
class GroupingResult:
    """Result bundle returned by :func:`group_option_combos`."""

    groups: tuple[ComboGroup, ...]
    combo_extras: dict[str, dict[str, Any]]
    leg_extras: dict[str, dict[str, Any]]


def group_option_combos(combos: Sequence[OptionCombo]) -> GroupingResult:
    """Group semantically identical combos and prepare display helpers."""

    grouped: dict[str, ComboGroup] = {}
    combo_extras: dict[str, dict[str, Any]] = {}
    leg_extras: dict[str, dict[str, Any]] = {}

    for combo in combos:
        group_id = build_combo_group_id(combo)
        combo_qty = _combo_net_quantity(combo)
        weight = abs(combo_qty) if combo_qty != ZERO else Decimal("1")
        group = grouped.get(group_id)
        if group is None:
            group = ComboGroup(
                combo_group_id=group_id,
                strategy=combo.strategy,
                underlying=combo.underlying,
                group_qty=ZERO,
                net_price_weighted=ZERO,
                weight_total=ZERO,
                dte_min=combo.dte,
                delta=ZERO,
                gamma=ZERO,
                theta=ZERO,
                vega=ZERO,
                mark_source="MISSING",
                stale_seconds=None,
            )
            grouped[group_id] = group

        group.group_qty += combo_qty
        group.net_price_weighted += combo.net_price * weight
        group.weight_total += weight
        group.dte_min = min(group.dte_min, combo.dte)
        group.delta += combo.sum_delta
        group.gamma += combo.sum_gamma
        group.theta += combo.sum_theta
        group.vega += combo.sum_vega

        combo_mark_source = _combo_mark_source(combo)
        group.mark_source = _choose_mark_source(group.mark_source, combo_mark_source)
        group.stale_seconds = _max_staleness(group.stale_seconds, _combo_staleness(combo))

        # Accumulate leg analytics
        for leg in combo.legs:
            leg_key = (leg.expiry, leg.right, leg.strike)
            acc = group.leg_accumulators.get(leg_key)
            if acc is None:
                acc = _LegAccumulator(
                    symbol=leg.instrument_symbol,
                    right=_right_code(leg.right),
                    strike=leg.strike,
                    expiry=leg.expiry,
                )
                group.leg_accumulators[leg_key] = acc
            acc.add(leg)
            leg_display = build_leg_display(combo.underlying, leg.strike, leg.right, leg.expiry)
            leg_extras[leg.leg_id] = {
                "combo_group_id": group_id,
                "label": leg_display.leg_label,
                "display": {
                    "leg_label": leg_display.leg_label,
                    "short_ul": leg_display.short_ul,
                    "expiry_short": leg_display.expiry_short,
                },
            }

        combo_display = build_combo_display(combo, combo_qty)
        combo_extras[combo.combo_id] = {
            "combo_group_id": group_id,
            "combo_qty": _to_float(combo_qty),
            "label": combo_display.combo_label,
            "display": {
                "combo_label": combo_display.combo_label,
                "short_ul": combo_display.short_ul,
                "expiry_short": combo_display.expiry_short,
            },
        }
        group.display = _combine_displays(group.display, combo_display)

    groups_payload = tuple(
        grouped[group_id]
        for group_id in sorted(grouped.keys())
    )
    return GroupingResult(groups=groups_payload, combo_extras=combo_extras, leg_extras=leg_extras)


def build_combo_group_id(combo: OptionCombo) -> str:
    """Return a stable grouping identifier for the provided combo."""

    parts: list[str] = []
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for leg in combo.legs:
        expiry = leg.expiry
        right = _right_code(leg.right)
        strike_text = _decimal_to_str(abs(leg.strike))
        buckets[(right, expiry)].append(strike_text)
    for (right, expiry), strikes in sorted(buckets.items()):
        unique = sorted({strike for strike in strikes})
        parts.append(f"{right}:{'/'.join(unique)}@{expiry}")
    strategy = combo.strategy.value
    underlying = combo.underlying
    return f"{strategy}|{underlying}|{'|'.join(parts)}"


def build_leg_display(
    underlying: str,
    strike: Decimal,
    right: str,
    expiry: str,
) -> LegDisplay:
    short_ul = underlying.upper()
    expiry_short = format_expiry_short(expiry)
    strike_text = _decimal_to_str(abs(strike))
    leg_label = f"{short_ul} {strike_text}{_right_code(right)} • {expiry_short or expiry}"
    return LegDisplay(leg_label=leg_label, short_ul=short_ul, expiry_short=expiry_short)


def build_combo_display(combo: OptionCombo, combo_qty: Decimal) -> ComboDisplay:
    short_ul = combo.underlying.upper()
    expiry_short = _combo_expiry_short(combo)
    net_price = combo.net_price
    label = format_combo_label(combo.strategy, combo.legs, combo.dte, net_price, short_ul)
    return ComboDisplay(combo_label=label, short_ul=short_ul, expiry_short=expiry_short)


def format_combo_label(
    strategy: ComboStrategy,
    legs: Sequence[OptionLegSnapshot],
    dte: int,
    net_price: Decimal,
    underlying: str,
) -> str:
    dte_text = f"{dte}d" if dte >= 0 else "0d"
    credit_or_debit = "Credit" if net_price > ZERO else "Debit" if net_price < ZERO else "Even"
    price_text = f"{abs(float(net_price)):.2f}"
    if strategy == ComboStrategy.VERTICAL:
        return _format_vertical_label(legs, underlying, dte_text, credit_or_debit, price_text)
    if strategy == ComboStrategy.IRON_CONDOR:
        return _format_condor_label(legs, underlying, dte_text, credit_or_debit, price_text)
    if strategy == ComboStrategy.CALENDAR:
        return _format_calendar_label(legs, underlying, dte_text, credit_or_debit, price_text)
    if strategy == ComboStrategy.STRADDLE:
        return _format_straddle_label(legs, underlying, dte_text)
    if strategy == ComboStrategy.STRANGLE:
        return _format_strangle_label(legs, underlying, dte_text)
    return f"{underlying} {strategy.value.title()} • {dte_text} • {credit_or_debit} {price_text}"


def format_expiry_short(expiry: str) -> str | None:
    parsed = _parse_expiry(expiry)
    if parsed is None:
        return None
    month = parsed.strftime("%b")
    day = parsed.day
    year_suffix = parsed.strftime("%y")
    return f"{month} {day} '{year_suffix}"


# ---------------------------------------------------------------------------
# Internal helpers


def _combo_net_quantity(combo: OptionCombo) -> Decimal:
    """Return +1 for debit (long) combos, -1 for credit (short) combos, else 0."""

    net_price = combo.net_price
    if net_price is None:
        return ZERO
    if net_price < ZERO:
        return Decimal("1")
    if net_price > ZERO:
        return Decimal("-1")
    return ZERO


def _combo_mark_source(combo: OptionCombo) -> str:
    source = "MISSING"
    for leg in combo.legs:
        source = _choose_mark_source(source, leg.mark_source)
    return source


def _combo_staleness(combo: OptionCombo) -> int | None:
    stale: int | None = None
    for leg in combo.legs:
        stale = _max_staleness(stale, leg.stale_seconds)
    return stale


def _choose_mark_source(current: str, candidate: str) -> str:
    """Prefer NBBO midpoint when available, fall back to last trade, and use prior close as a baseline."""

    current_key = (str(current).strip() or "MISSING").upper()
    candidate_key = (str(candidate).strip() or "MISSING").upper()
    current_rank = _MARK_SOURCE_PRIORITY.get(current_key, 99)
    candidate_rank = _MARK_SOURCE_PRIORITY.get(candidate_key, 99)
    if candidate_rank < current_rank:
        return candidate_key
    return current_key


def _max_staleness(existing: int | None, candidate: int | None) -> int | None:
    if existing is None:
        return candidate
    if candidate is None:
        return existing
    return max(existing, candidate)


def _right_code(value: str) -> str:
    text = value.upper()
    if text.startswith("C"):
        return "C"
    if text.startswith("P"):
        return "P"
    return text[:1]


def _combo_expiry_short(combo: OptionCombo) -> str | None:
    expiries = sorted({leg.expiry for leg in combo.legs})
    if not expiries:
        return None
    short_list = [format_expiry_short(expiry) or expiry for expiry in expiries]
    if len(short_list) == 1:
        return short_list[0]
    return "→".join(short_list[:2])


def _format_vertical_label(
    legs: Sequence[OptionLegSnapshot],
    underlying: str,
    dte_text: str,
    credit_or_debit: str,
    price_text: str,
) -> str:
    puts = [leg for leg in legs if _right_code(leg.right) == "P"]
    calls = [leg for leg in legs if _right_code(leg.right) == "C"]
    if len(puts) == 2:
        strikes = sorted(_decimal_to_str(abs(leg.strike)) for leg in puts)
        return f"{underlying} {strikes[0]}/{strikes[1]}P • {dte_text} • {credit_or_debit} {price_text}"
    if len(calls) == 2:
        strikes = sorted(_decimal_to_str(abs(leg.strike)) for leg in calls)
        return f"{underlying} {strikes[0]}/{strikes[1]}C • {dte_text} • {credit_or_debit} {price_text}"
    return f"{underlying} Vertical • {dte_text} • {credit_or_debit} {price_text}"


def _format_condor_label(
    legs: Sequence[OptionLegSnapshot],
    underlying: str,
    dte_text: str,
    credit_or_debit: str,
    price_text: str,
) -> str:
    puts = sorted(_decimal_to_str(abs(leg.strike)) for leg in legs if _right_code(leg.right) == "P")
    calls = sorted(_decimal_to_str(abs(leg.strike)) for leg in legs if _right_code(leg.right) == "C")
    left = f"{puts[0]}/{puts[-1]}P" if puts else "P"
    right = f"{calls[0]}/{calls[-1]}C" if calls else "C"
    return f"{underlying} {left} + {right} • {dte_text} • {credit_or_debit} {price_text}"


def _format_calendar_label(
    legs: Sequence[OptionLegSnapshot],
    underlying: str,
    dte_text: str,
    credit_or_debit: str,
    price_text: str,
) -> str:
    strikes = {abs(leg.strike) for leg in legs}
    strike_text = _decimal_to_str(next(iter(strikes))) if len(strikes) == 1 else _decimal_to_str(min(strikes))
    rights = {_right_code(leg.right) for leg in legs}
    right_text = next(iter(rights)) if len(rights) == 1 else "?"
    sorted_months: list[str] = []
    seen: set[str] = set()
    for leg in sorted(legs, key=lambda item: (_parse_expiry(item.expiry) or date.max)):
        month = format_month_short(leg.expiry)
        if month and month not in seen:
            seen.add(month)
            sorted_months.append(month)
            if len(sorted_months) == 2:
                break
    month_span = "→".join(sorted_months)
    return f"{underlying} {strike_text}{right_text} CAL • {month_span} • {credit_or_debit} {price_text}"


def _format_straddle_label(
    legs: Sequence[OptionLegSnapshot],
    underlying: str,
    dte_text: str,
) -> str:
    strikes = {abs(leg.strike) for leg in legs}
    strike_text = _decimal_to_str(next(iter(strikes))) if strikes else "?"
    return f"{underlying} {strike_text}C+P • {dte_text}"


def _format_strangle_label(
    legs: Sequence[OptionLegSnapshot],
    underlying: str,
    dte_text: str,
) -> str:
    call_strike = _decimal_to_str(
        max((abs(leg.strike) for leg in legs if _right_code(leg.right) == "C"), default=ZERO)
    )
    put_strike = _decimal_to_str(
        min((abs(leg.strike) for leg in legs if _right_code(leg.right) == "P"), default=ZERO)
    )
    return f"{underlying} {put_strike}P/{call_strike}C • {dte_text}"


def _combine_displays(existing: ComboDisplay | None, latest: ComboDisplay) -> ComboDisplay:
    return latest if existing is None else existing


def _decimal_to_str(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_expiry(expiry: str) -> date | None:
    text = (expiry or "").strip()
    if not text:
        return None
    try:
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        return date.fromisoformat(text)
    except (ValueError, InvalidOperation):
        return None


def format_month_short(expiry: str) -> str | None:
    parsed = _parse_expiry(expiry)
    if parsed is None:
        return None
    return parsed.strftime("%b")
