# SPDX-License-Identifier: MIT

"""Combo detection utilities for option legs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
from time import perf_counter
from typing import Any, Iterable, Sequence

from ..core.marks import MarkSettings, select_equity_mark
from ..core.models import InstrumentType, Position, Quote
from ..core.pnl import option_leg_pnl
from .taxonomy import ComboStrategy


ZERO = Decimal("0")


@dataclass(frozen=True)
class OptionLegSnapshot:
    """Normalized view of an individual option leg."""

    leg_id: str
    instrument_symbol: str
    account: str
    underlying: str
    expiry: str
    dte: int
    right: str
    strike: Decimal
    quantity: Decimal
    ratio: Decimal
    multiplier: Decimal
    avg_cost: Decimal
    mark: Decimal | None
    mark_source: str
    stale_seconds: int | None
    previous_close: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    iv: Decimal | None
    day_pnl: Decimal
    total_pnl: Decimal
    day_basis: Decimal | None
    total_basis: Decimal | None
    feed_strategy_id: str | None = None
    feed_combo_id: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def direction(self) -> int:
        return -1 if self.quantity < 0 else 1

    def signature(self) -> str:
        ratio_value = self.ratio if self.ratio != ZERO else abs(self.quantity)
        ratio_text = _decimal_to_str(ratio_value)
        strike_text = _decimal_to_str(self.strike)
        return f"{self.right}:{strike_text}:{self.expiry}:{ratio_text}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "leg_id": self.leg_id,
            "symbol": self.instrument_symbol,
            "underlying": self.underlying,
            "expiry": self.expiry,
            "dte": self.dte,
            "right": self.right,
            "strike": _to_float(self.strike),
            "quantity": _to_float(self.quantity),
            "ratio": _to_float(self.ratio),
            "multiplier": _to_float(self.multiplier),
            "avg_cost": _to_float(self.avg_cost),
            "mark": _to_float(self.mark),
            "mark_source": self.mark_source,
            "stale_seconds": self.stale_seconds,
            "delta": _to_float(self.delta),
            "gamma": _to_float(self.gamma),
            "theta": _to_float(self.theta),
            "vega": _to_float(self.vega),
            "iv": _to_float(self.iv),
            "day_pnl": _to_float(self.day_pnl),
            "total_pnl": _to_float(self.total_pnl),
            "day_basis": _to_float(self.day_basis),
            "total_basis": _to_float(self.total_basis),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class OptionCombo:
    """Detected combo with aggregated analytics."""

    combo_id: str
    strategy: ComboStrategy
    account: str
    underlying: str
    dte: int
    net_price: Decimal
    sum_delta: Decimal
    sum_gamma: Decimal
    sum_theta: Decimal
    sum_vega: Decimal
    day_pnl: Decimal
    total_pnl: Decimal
    day_pnl_percent: Decimal | None
    total_pnl_percent: Decimal | None
    legs: tuple[OptionLegSnapshot, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "combo_id": self.combo_id,
            "strategy": self.strategy.value,
            "underlying": self.underlying,
            "dte": self.dte,
            "net_price": _to_float(self.net_price),
            "sum_greeks": {
                "delta": _to_float(self.sum_delta),
                "gamma": _to_float(self.sum_gamma),
                "theta": _to_float(self.sum_theta),
                "vega": _to_float(self.sum_vega),
            },
            "day_pnl_amount": _to_float(self.day_pnl),
            "total_pnl_amount": _to_float(self.total_pnl),
            "day_pnl_percent": _to_float(self.day_pnl_percent),
            "total_pnl_percent": _to_float(self.total_pnl_percent),
            "legs": [leg.to_payload() for leg in self.legs],
        }
        if self.notes:
            payload["notes"] = list(self.notes)
        return payload


@dataclass(frozen=True)
class ComboDetection:
    """Return object for combo detection."""

    combos: tuple[OptionCombo, ...]
    orphans: tuple[OptionLegSnapshot, ...]
    detection_ms: float


@dataclass(frozen=True)
class _NormalizedMetadata:
    account: str
    underlying: str
    expiry: str
    expiry_date: date
    right: str
    strike: Decimal
    ratio: Decimal
    dte: int
    previous_close: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    iv: Decimal | None
    feed_strategy_id: str | None
    feed_combo_id: str | None
    notes: tuple[str, ...]


def build_option_leg_snapshot(
    position: Position,
    quote: Quote | None,
    now: datetime,
    mark_settings: MarkSettings | None = None,
) -> OptionLegSnapshot | None:
    """Return an option leg snapshot or ``None`` if required metadata is missing."""

    if position.instrument.instrument_type != InstrumentType.OPTION:
        return None

    if mark_settings is None:
        mark_settings = MarkSettings()

    normalized = _normalize_option_metadata(position, now)
    if normalized is None:
        return None

    mark_result = select_equity_mark(quote, now, mark_settings)
    pnl = option_leg_pnl(position, mark_result.mark, normalized.previous_close)
    day_basis = _day_basis(position.quantity, position.instrument.multiplier, normalized.previous_close)
    total_basis = _total_basis(position.avg_cost, position.quantity, position.instrument.multiplier)

    leg_id = _leg_hash(
        normalized.account,
        position.instrument.symbol,
        normalized.expiry,
        normalized.right,
        normalized.strike,
        position.quantity,
    )

    return OptionLegSnapshot(
        leg_id=leg_id,
        instrument_symbol=position.instrument.symbol,
        account=normalized.account,
        underlying=normalized.underlying,
        expiry=normalized.expiry,
        dte=normalized.dte,
        right=normalized.right,
        strike=normalized.strike,
        quantity=position.quantity,
        ratio=normalized.ratio,
        multiplier=position.instrument.multiplier,
        avg_cost=position.avg_cost,
        mark=mark_result.mark,
        mark_source=mark_result.source,
        stale_seconds=mark_result.stale_seconds,
        previous_close=normalized.previous_close,
        delta=normalized.delta,
        gamma=normalized.gamma,
        theta=normalized.theta,
        vega=normalized.vega,
        iv=normalized.iv,
        day_pnl=pnl.day,
        total_pnl=pnl.total,
        day_basis=day_basis,
        total_basis=total_basis,
        feed_strategy_id=normalized.feed_strategy_id,
        feed_combo_id=normalized.feed_combo_id,
        notes=normalized.notes,
    )


def detect_option_combos(legs: Sequence[OptionLegSnapshot]) -> ComboDetection:
    """Detect option combos and orphan legs from the provided leg snapshots."""

    start = perf_counter()
    remaining_ids = {leg.leg_id for leg in legs}
    combos: list[OptionCombo] = []

    feed_combos, feed_used = _group_feed_combos(legs, remaining_ids)
    combos.extend(feed_combos)
    remaining_ids.difference_update(feed_used)

    for matcher in (
        _match_condors_and_butterflies,
        _match_verticals,
        _match_calendars,
        _match_straddles_and_strangles,
        _match_ratios,
    ):
        matched, consumed = matcher(legs, remaining_ids)
        combos.extend(matched)
        remaining_ids.difference_update(consumed)

    detection_ms = (perf_counter() - start) * 1000.0
    orphans = tuple(sorted((leg for leg in legs if leg.leg_id in remaining_ids), key=_leg_sort_key))
    combos_sorted = tuple(sorted(combos, key=lambda combo: (combo.underlying, combo.dte, combo.combo_id)))
    return ComboDetection(combos=combos_sorted, orphans=orphans, detection_ms=detection_ms)


# ---------------------------------------------------------------------------
# Internal helpers


def _normalize_option_metadata(position: Position, now: datetime) -> _NormalizedMetadata | None:
    metadata = position.metadata or {}
    account = str(metadata.get("account") or "UNKNOWN").strip() or "UNKNOWN"

    underlying = metadata.get("underlying")
    expiry_raw = metadata.get("expiry")
    right_raw = metadata.get("right")
    strike_raw = metadata.get("strike")
    ratio_raw = metadata.get("ratio")

    parsed_symbol = _parse_option_symbol(position.instrument.symbol)
    notes: list[str] = []
    if parsed_symbol is not None:
        if underlying is None:
            underlying = parsed_symbol["underlying"]
        if expiry_raw is None:
            expiry_raw = parsed_symbol["expiry"]
        if right_raw is None:
            right_raw = parsed_symbol["right"]
        if strike_raw is None:
            strike_raw = parsed_symbol["strike"]
    else:
        notes.append("symbol_parse_fallback")

    underlying = str(underlying).strip().upper() if underlying is not None else None
    right = _normalize_right(right_raw)

    try:
        strike = _ensure_decimal(strike_raw) if strike_raw is not None else None
    except ValueError:
        return None

    if underlying in (None, "") or right is None or strike is None:
        return None

    expiry_str, expiry_date = _coerce_expiry(expiry_raw)
    if expiry_str is None or expiry_date is None:
        return None

    now = _ensure_aware(now)
    dte = max((expiry_date - now.date()).days, 0)

    if ratio_raw is None:
        ratio_value = abs(position.quantity)
    else:
        try:
            ratio_value = _ensure_decimal(ratio_raw)
        except ValueError:
            ratio_value = abs(position.quantity)
    if ratio_value == ZERO:
        ratio_value = abs(position.quantity) or Decimal("1")

    previous_close = _maybe_decimal(metadata.get("previous_close"))
    delta = _maybe_decimal(metadata.get("delta"))
    gamma = _maybe_decimal(metadata.get("gamma"))
    theta = _maybe_decimal(metadata.get("theta"))
    vega = _maybe_decimal(metadata.get("vega"))
    iv = _maybe_decimal(metadata.get("iv"))

    feed_strategy_id = metadata.get("strategy_id")
    feed_combo_id = metadata.get("combo_id")

    normalized_notes = tuple(notes)
    return _NormalizedMetadata(
        account=account,
        underlying=underlying,
        expiry=expiry_str,
        expiry_date=expiry_date,
        right=right,
        strike=strike,
        ratio=ratio_value,
        dte=dte,
        previous_close=previous_close,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        iv=iv,
        feed_strategy_id=str(feed_strategy_id).strip() if feed_strategy_id else None,
        feed_combo_id=str(feed_combo_id).strip() if feed_combo_id else None,
        notes=normalized_notes,
    )


def _group_feed_combos(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
) -> tuple[list[OptionCombo], set[str]]:
    combos: list[OptionCombo] = []
    used: set[str] = set()
    buckets: dict[tuple[str, str], list[OptionLegSnapshot]] = defaultdict(list)
    for leg in legs:
        if leg.leg_id not in remaining_ids:
            continue
        feed_id = leg.feed_combo_id or leg.feed_strategy_id
        if not feed_id:
            continue
        buckets[(leg.account, feed_id)].append(leg)

    for (account, _feed_id), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        if len({leg.underlying for leg in bucket}) != 1:
            continue
        strategy = _classify_strategy(bucket)
        combo = _build_combo(account, bucket[0].underlying, bucket, strategy, notes=("feed_group",))
        combos.append(combo)
        used.update(leg.leg_id for leg in bucket)
    return combos, used


def _match_condors_and_butterflies(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
) -> tuple[list[OptionCombo], set[str]]:
    combos: list[OptionCombo] = []
    consumed: set[str] = set()
    buckets = _group_by(legs, remaining_ids, lambda leg: (leg.account, leg.underlying, leg.expiry))
    for (account, underlying, _expiry), bucket in buckets.items():
        if len(bucket) != 4:
            continue
        strategy = _looks_like_condor(bucket)
        if strategy is None:
            continue
        combo = _build_combo(account, underlying, bucket, strategy)
        combos.append(combo)
        consumed.update(leg.leg_id for leg in bucket)
    return combos, consumed


def _match_verticals(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
) -> tuple[list[OptionCombo], set[str]]:
    combos: list[OptionCombo] = []
    consumed: set[str] = set()
    buckets = _group_by(legs, remaining_ids, lambda leg: (leg.account, leg.underlying, leg.expiry, leg.right))
    for (account, underlying, _expiry, _right), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        pair = _find_vertical_pair(bucket)
        if pair is None:
            continue
        combo = _build_combo(account, underlying, pair, ComboStrategy.VERTICAL)
        combos.append(combo)
        consumed.update(leg.leg_id for leg in pair)
    return combos, consumed


def _match_calendars(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
) -> tuple[list[OptionCombo], set[str]]:
    combos: list[OptionCombo] = []
    consumed: set[str] = set()
    buckets = _group_by(legs, remaining_ids, lambda leg: (leg.account, leg.underlying, leg.right, leg.strike))
    for (account, underlying, _right, _strike), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        pair = _find_calendar_pair(bucket)
        if pair is None:
            continue
        combo = _build_combo(account, underlying, pair, ComboStrategy.CALENDAR)
        combos.append(combo)
        consumed.update(leg.leg_id for leg in pair)
    return combos, consumed


def _match_straddles_and_strangles(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
) -> tuple[list[OptionCombo], set[str]]:
    combos: list[OptionCombo] = []
    consumed: set[str] = set()
    buckets = _group_by(legs, remaining_ids, lambda leg: (leg.account, leg.underlying, leg.expiry))
    for (account, underlying, _expiry), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        pair = _find_straddle_or_strangle(bucket)
        if pair is None:
            continue
        strategy = ComboStrategy.STRADDLE if pair[0].strike == pair[1].strike else ComboStrategy.STRANGLE
        combo = _build_combo(account, underlying, pair, strategy)
        combos.append(combo)
        consumed.update(leg.leg_id for leg in pair)
    return combos, consumed


def _match_ratios(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
) -> tuple[list[OptionCombo], set[str]]:
    combos: list[OptionCombo] = []
    consumed: set[str] = set()
    buckets = _group_by(legs, remaining_ids, lambda leg: (leg.account, leg.underlying, leg.expiry, leg.right))
    for (account, underlying, _expiry, _right), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        quantities = {abs(leg.quantity) for leg in bucket}
        if len(quantities) == 1 and len(bucket) == 2:
            continue
        combo = _build_combo(account, underlying, bucket, ComboStrategy.RATIO)
        combos.append(combo)
        consumed.update(leg.leg_id for leg in bucket)
    return combos, consumed


# ---------------------------------------------------------------------------
# Classification helpers


def _classify_strategy(legs: Sequence[OptionLegSnapshot]) -> ComboStrategy:
    strategy = _looks_like_condor(legs)
    if strategy is not None:
        return strategy
    if _looks_like_vertical(legs):
        return ComboStrategy.VERTICAL
    if _looks_like_calendar(legs):
        return ComboStrategy.CALENDAR
    if _looks_like_straddle_or_strangle(legs):
        return ComboStrategy.STRADDLE if _same_strike(legs) else ComboStrategy.STRANGLE
    if _looks_like_ratio(legs):
        return ComboStrategy.RATIO
    return ComboStrategy.UNKNOWN


def _looks_like_condor(legs: Sequence[OptionLegSnapshot]) -> ComboStrategy | None:
    if len(legs) != 4:
        return None
    if len({leg.expiry for leg in legs}) != 1:
        return None
    rights = [leg.right for leg in legs]
    if rights.count("CALL") != 2 or rights.count("PUT") != 2:
        return None
    call_short, call_long = _pick_short_long(legs, "CALL")
    put_short, put_long = _pick_short_long(legs, "PUT")
    if None in (call_short, call_long, put_short, put_long):
        return None
    quantities = {abs(call_short.quantity), abs(call_long.quantity), abs(put_short.quantity), abs(put_long.quantity)}
    if len(quantities) != 1:
        return None
    return ComboStrategy.IRON_BUTTERFLY if call_short.strike == put_short.strike else ComboStrategy.IRON_CONDOR


def _looks_like_vertical(legs: Sequence[OptionLegSnapshot]) -> bool:
    if len(legs) != 2:
        return False
    a, b = legs
    if a.right != b.right:
        return False
    if a.expiry != b.expiry:
        return False
    if a.direction == b.direction:
        return False
    return abs(a.quantity) == abs(b.quantity) and a.strike != b.strike


def _looks_like_calendar(legs: Sequence[OptionLegSnapshot]) -> bool:
    if len(legs) != 2:
        return False
    a, b = legs
    if a.right != b.right:
        return False
    if a.direction == b.direction:
        return False
    if a.strike != b.strike:
        return False
    return a.expiry != b.expiry


def _looks_like_straddle_or_strangle(legs: Sequence[OptionLegSnapshot]) -> bool:
    if len(legs) != 2:
        return False
    a, b = legs
    if {a.right, b.right} != {"CALL", "PUT"}:
        return False
    return abs(a.quantity) == abs(b.quantity)


def _looks_like_ratio(legs: Sequence[OptionLegSnapshot]) -> bool:
    if len(legs) < 2:
        return False
    expiries = {leg.expiry for leg in legs}
    rights = {leg.right for leg in legs}
    if len(expiries) != 1 or len(rights) != 1:
        return False
    quantities = {abs(leg.quantity) for leg in legs}
    return len(quantities) != 1 or len(legs) > 2


def _same_strike(legs: Sequence[OptionLegSnapshot]) -> bool:
    return len({leg.strike for leg in legs}) == 1


def _pick_short_long(
    legs: Sequence[OptionLegSnapshot],
    right: str,
) -> tuple[OptionLegSnapshot | None, OptionLegSnapshot | None]:
    short = next((leg for leg in legs if leg.right == right and leg.direction < 0), None)
    long = next((leg for leg in legs if leg.right == right and leg.direction > 0), None)
    return short, long


def _find_vertical_pair(
    legs: Sequence[OptionLegSnapshot],
) -> tuple[OptionLegSnapshot, OptionLegSnapshot] | None:
    longs = [leg for leg in legs if leg.direction > 0]
    shorts = [leg for leg in legs if leg.direction < 0]
    for long_leg in sorted(longs, key=_leg_sort_key):
        for short_leg in sorted(shorts, key=_leg_sort_key):
            if abs(long_leg.quantity) == abs(short_leg.quantity) and long_leg.strike != short_leg.strike:
                return (short_leg, long_leg)
    return None


def _find_calendar_pair(
    legs: Sequence[OptionLegSnapshot],
) -> tuple[OptionLegSnapshot, OptionLegSnapshot] | None:
    longs = [leg for leg in legs if leg.direction > 0]
    shorts = [leg for leg in legs if leg.direction < 0]
    for long_leg in sorted(longs, key=_leg_sort_key):
        for short_leg in sorted(shorts, key=_leg_sort_key):
            if (
                abs(long_leg.quantity) == abs(short_leg.quantity)
                and long_leg.strike == short_leg.strike
                and long_leg.expiry != short_leg.expiry
            ):
                return (short_leg, long_leg)
    return None


def _find_straddle_or_strangle(
    legs: Sequence[OptionLegSnapshot],
) -> tuple[OptionLegSnapshot, OptionLegSnapshot] | None:
    calls = [leg for leg in legs if leg.right == "CALL"]
    puts = [leg for leg in legs if leg.right == "PUT"]
    for call_leg in sorted(calls, key=_leg_sort_key):
        for put_leg in sorted(puts, key=_leg_sort_key):
            if call_leg.expiry != put_leg.expiry:
                continue
            if abs(call_leg.quantity) != abs(put_leg.quantity):
                continue
            return (call_leg, put_leg)
    return None


def _group_by(
    legs: Sequence[OptionLegSnapshot],
    remaining_ids: set[str],
    key_fn,
) -> dict[Any, list[OptionLegSnapshot]]:
    buckets: dict[Any, list[OptionLegSnapshot]] = defaultdict(list)
    for leg in legs:
        if leg.leg_id not in remaining_ids:
            continue
        buckets[key_fn(leg)].append(leg)
    return buckets


def _build_combo(
    account: str,
    underlying: str,
    legs: Sequence[OptionLegSnapshot],
    strategy: ComboStrategy,
    notes: Sequence[str] | None = None,
) -> OptionCombo:
    ordered = tuple(sorted(legs, key=_leg_sort_key))
    combo_id = _combo_hash(account, underlying, ordered)
    net_price = sum((leg.avg_cost * leg.quantity) for leg in ordered)
    sum_delta = _sum_greek(ordered, "delta")
    sum_gamma = _sum_greek(ordered, "gamma")
    sum_theta = _sum_greek(ordered, "theta")
    sum_vega = _sum_greek(ordered, "vega")
    day_pnl = sum((leg.day_pnl for leg in ordered), ZERO)
    total_pnl = sum((leg.total_pnl for leg in ordered), ZERO)
    day_basis = _sum_optionals(leg.day_basis for leg in ordered)
    total_basis = _sum_optionals(leg.total_basis for leg in ordered)
    day_pct = _percent(day_pnl, day_basis)
    total_pct = _percent(total_pnl, total_basis)
    combo_notes = tuple(notes) if notes else tuple()
    dte = min((leg.dte for leg in ordered), default=0)
    return OptionCombo(
        combo_id=combo_id,
        strategy=strategy,
        account=account,
        underlying=underlying,
        dte=dte,
        net_price=net_price,
        sum_delta=sum_delta,
        sum_gamma=sum_gamma,
        sum_theta=sum_theta,
        sum_vega=sum_vega,
        day_pnl=day_pnl,
        total_pnl=total_pnl,
        day_pnl_percent=day_pct,
        total_pnl_percent=total_pct,
        legs=ordered,
        notes=combo_notes,
    )


def _combo_hash(account: str, underlying: str, legs: Sequence[OptionLegSnapshot]) -> str:
    leg_signatures = sorted(leg.signature() for leg in legs)
    payload = "PSD|" + account + "|" + underlying + "|" + "|".join(leg_signatures)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _leg_hash(
    account: str,
    symbol: str,
    expiry: str,
    right: str,
    strike: Decimal,
    quantity: Decimal,
) -> str:
    strike_text = _decimal_to_str(strike)
    qty_text = _decimal_to_str(abs(quantity))
    payload = f"PSDL|{account}|{symbol}|{expiry}|{right}|{strike_text}|{qty_text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _sum_greek(legs: Sequence[OptionLegSnapshot], attr: str) -> Decimal:
    total = ZERO
    for leg in legs:
        value = getattr(leg, attr)
        if value is None:
            continue
        total += value * leg.quantity * leg.multiplier
    return total


def _sum_optionals(values: Iterable[Decimal | None]) -> Decimal | None:
    total = ZERO
    has_value = False
    for value in values:
        if value is None:
            continue
        total += value
        has_value = True
    return total if has_value else None


def _day_basis(quantity: Decimal, multiplier: Decimal, previous_close: Decimal | None) -> Decimal | None:
    if previous_close is None:
        return None
    return previous_close * quantity * multiplier


def _total_basis(avg_cost: Decimal, quantity: Decimal, multiplier: Decimal) -> Decimal | None:
    return avg_cost * quantity * multiplier


def _percent(numerator: Decimal, denominator: Decimal | None) -> Decimal | None:
    if denominator is None or denominator == ZERO:
        return None
    try:
        return (numerator / abs(denominator)) * Decimal("100")
    except (ZeroDivisionError, InvalidOperation):
        return None


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


def _maybe_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return _ensure_decimal(value)
    except ValueError:
        return None


def _ensure_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        raise ValueError("empty decimal value")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(str(value)) from exc


def _normalize_right(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"C", "CALL", "CALLS"}:
        return "CALL"
    if text in {"P", "PUT", "PUTS"}:
        return "PUT"
    return None


def _coerce_expiry(value: Any) -> tuple[str | None, date | None]:
    if value is None:
        return None, None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat(), value
    text = str(value).strip()
    if not text:
        return None, None
    digits = "".join(ch for ch in text if ch.isdigit())
    year = month = day = None
    if len(digits) == 8:
        year = int(digits[:4])
        month = int(digits[4:6])
        day = int(digits[6:8])
    elif len(digits) == 6:
        year = 2000 + int(digits[:2])
        month = int(digits[2:4])
        day = int(digits[4:6])
    else:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None, None
        else:
            return parsed.date().isoformat(), parsed.date()
    try:
        expiry_date = date(year, month, day)
    except ValueError:
        return None, None
    return expiry_date.isoformat(), expiry_date


def _parse_option_symbol(symbol: str) -> dict[str, Any] | None:
    text = symbol.strip()
    if not text:
        return None
    if len(text) >= 15 and text[6:12].isdigit():
        underlying = text[:6].strip().upper()
        expiry = text[6:12]
        right_code = text[12].upper()
        right = "CALL" if right_code == "C" else "PUT" if right_code == "P" else None
        try:
            strike = Decimal(text[13:]) / Decimal("1000")
        except (InvalidOperation, ValueError):
            strike = None
        if right is not None and strike is not None:
            return {"underlying": underlying, "expiry": expiry, "right": right, "strike": strike}
    if "-" in text:
        parts = text.split("-")
        if len(parts) >= 4:
            underlying = parts[0].upper()
            expiry = parts[1]
            right = _normalize_right(parts[3])
            try:
                strike = Decimal(parts[2])
            except (InvalidOperation, ValueError):
                strike = None
            if right is not None and strike is not None:
                return {"underlying": underlying, "expiry": expiry, "right": right, "strike": strike}
    return None


def _ensure_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _leg_sort_key(leg: OptionLegSnapshot) -> tuple[Any, ...]:
    return (
        leg.underlying,
        leg.expiry,
        0 if leg.right == "CALL" else 1,
        leg.strike,
        leg.quantity,
    )


# ---------------------------------------------------------------------------
# End helpers
