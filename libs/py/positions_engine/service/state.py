# SPDX-License-Identifier: MIT

"""In-memory joiner for normalized position snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

from ..combos import ComboDetection, build_option_leg_snapshot, detect_option_combos
from ..core.marks import MarkResult, MarkSettings, select_equity_mark
from ..core.models import InstrumentType, Position, Quote
from ..core.pnl import equity_pnl


class PositionsState:
    """Cache positions + quotes and emit normalized equity payloads."""

    def __init__(self, mark_settings: MarkSettings | None = None) -> None:
        self._mark_settings = mark_settings or MarkSettings()
        self._positions: dict[str, Position] = {}
        self._quotes: dict[str, Quote] = {}
        self._positions_version = 0
        self._quotes_version = 0
        self._options_cache: dict[str, Any] | None = None
        self._snapshot_override: datetime | None = None
        self._data_source: str = "unknown"

    def refresh(
        self,
        positions: Iterable[Position] | None = None,
        quotes: Iterable[Quote] | None = None,
        snapshot_at: datetime | None = None,
        data_source: str | None = None,
    ) -> None:
        if positions is not None:
            self._positions_version += 1
            self._positions = {p.instrument.symbol: p for p in positions}
        if quotes is not None:
            self._quotes_version += 1
            self._quotes = {q.symbol: q for q in quotes}
        if positions is not None or quotes is not None:
            self._options_cache = None
        if snapshot_at is not None:
            self._snapshot_override = _ensure_aware(snapshot_at)
        elif quotes is not None:
            self._snapshot_override = None
        if data_source is not None:
            self._data_source = data_source

    def snapshot_updated_at(self) -> datetime | None:
        """Return the freshest quote timestamp available, if any."""

        if self._snapshot_override is not None:
            return self._snapshot_override

        latest: datetime | None = None
        for quote in self._quotes.values():
            if quote.updated_at is None:
                continue
            candidate = _ensure_aware(quote.updated_at)
            if latest is None or candidate > latest:
                latest = candidate
        return latest

    def equities_payload(self, now: datetime | None = None) -> list[dict[str, Any]]:
        rows, _ = self._rows(now)
        return rows

    def options_payload(self, now: datetime | None = None) -> dict[str, Any]:
        detection, as_of = self._ensure_options_detection(now)
        return {
            "as_of": _isoformat(as_of),
            "combos": [combo.to_payload() for combo in detection.combos],
            "legs": [leg.to_payload() for leg in detection.orphans],
        }

    def options_detection(self, now: datetime | None = None) -> ComboDetection:
        detection, _ = self._ensure_options_detection(now)
        return detection

    def stats(self, now: datetime | None = None) -> dict[str, int | float]:
        rows, stale = self._rows(now)
        detection, _ = self._ensure_options_detection(now)
        legs_count = sum(len(combo.legs) for combo in detection.combos) + len(detection.orphans)
        return {
            "equity_count": len(rows),
            "quote_count": len(self._quotes),
            "stale_quotes_count": stale,
            "option_legs_count": legs_count,
            "combos_matched": len(detection.combos),
            "combos_detection_ms": detection.detection_ms,
            "data_source": self._data_source,
        }

    @property
    def data_source(self) -> str:
        return self._data_source

    def _rows(self, now: datetime | None) -> tuple[list[dict[str, Any]], int]:
        now = _ensure_aware(now)
        rows: list[dict[str, Any]] = []
        stale = 0
        for symbol, position in sorted(self._positions.items()):
            if position.instrument.instrument_type != InstrumentType.EQUITY:
                continue
            quote = self._quotes.get(symbol)
            mark = select_equity_mark(quote, now, self._mark_settings)
            mark_value = _mark_or_fallback(mark, position)
            if mark.is_stale:
                stale += 1
            prev_close = quote.previous_close if quote else None
            pnl = equity_pnl(position, mark.mark, prev_close)
            day_basis = _day_basis(position, prev_close)
            total_basis = _total_basis(position)
            rows.append(
                {
                    "symbol": symbol,
                    "qty": float(position.quantity),
                    "avg_cost": float(position.avg_cost),
                    "mark": float(mark_value),
                    "mark_source": mark.source,
                    "day_pnl": float(pnl.day),
                    "day_pnl_percent": _maybe_float(_percent(pnl.day, day_basis)),
                    "total_pnl": float(pnl.total),
                    "total_pnl_percent": _maybe_float(_percent(pnl.total, total_basis)),
                    "stale_seconds": mark.stale_seconds,
                }
            )
        return rows, stale

    def _ensure_options_detection(self, now: datetime | None) -> tuple[ComboDetection, datetime]:
        now = _ensure_aware(now)
        cache = self._options_cache or {}
        cache_day = now.date()
        if (
            cache
            and cache.get("positions_version") == self._positions_version
            and cache.get("quotes_version") == self._quotes_version
            and cache.get("day") == cache_day
        ):
            detection = cache["detection"]
        else:
            legs = []
            for position in self._positions.values():
                leg = build_option_leg_snapshot(
                    position,
                    self._quotes.get(position.instrument.symbol),
                    now,
                    self._mark_settings,
                )
                if leg is not None:
                    legs.append(leg)
            detection = detect_option_combos(legs)
            self._options_cache = {
                "positions_version": self._positions_version,
                "quotes_version": self._quotes_version,
                "day": cache_day,
                "detection": detection,
            }
        return detection, now


def _day_basis(position: Position, previous_close: Decimal | None) -> Decimal | None:
    if previous_close is None:
        return None
    return previous_close * position.quantity * position.multiplier


def _total_basis(position: Position) -> Decimal | None:
    return position.avg_cost * position.quantity * position.multiplier


def _percent(numerator: Decimal, basis: Decimal | None) -> Decimal | None:
    if basis is None:
        return None
    if basis == 0:
        return None
    denominator = abs(basis)
    if denominator == 0:
        return None
    try:
        return (numerator / denominator) * Decimal("100")
    except (DivisionByZero, InvalidOperation):
        return None


def _maybe_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _mark_or_fallback(mark: MarkResult, position: Position) -> Decimal:
    return Decimal(mark.mark) if mark.mark is not None else position.avg_cost


def _ensure_aware(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.now(tz=UTC)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _isoformat(ts: datetime) -> str:
    ts = _ensure_aware(ts)
    text = ts.isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text
